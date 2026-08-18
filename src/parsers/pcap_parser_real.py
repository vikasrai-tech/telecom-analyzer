"""
Real PCAP Parser — Unified Telecom Analyzer
============================================
3GPP-aligned 6-interface protocol parsing:
  TS 24.501  — NAS  (5GMM + 5GSM)       discriminator 0x7e
  TS 38.413  — NGAP (N2: gNB ↔ AMF)     discriminator 0x3a
  TS 38.331  — RRC  (Uu: UE ↔ gNB)      discriminator 0x2b
  TS 38.473  — F1AP (F1: DU ↔ CU-CP)    discriminator 0x1a
  TS 38.463  — E1AP (E1: CU-CP ↔ CU-UP) discriminator 0x1b
  TS 38.423  — XnAP (Xn: gNB ↔ gNB)     discriminator 0x1c

Note: Covers the 6 5G control-plane interfaces listed above (NAS/NGAP/RRC/F1AP/E1AP/XnAP).
MAC/PHY layer parsing is out of scope (requires I/Q or layer-1 capture format, not PCAP).

For real captures: pyshark dissects layers; full IE extraction via ie_extractor.
For synthetic PCAP: raw UDP payload with single-byte protocol discriminator.
"""

import logging
import struct
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from collections import defaultdict
from dataclasses import dataclass, field

import pyshark

from .protocol_defs import (
    NAS_5GMM_MSGS, NAS_5GSM_MSGS,
    NGAP_PROCS, REAL_NGAP_PROC_MAP,
    RRC_PROCS,
    DISC_F1AP, DISC_E1AP, DISC_XNAP,
    NAS_CAUSE_NAMES, NGAP_CAUSE_NAMES, RRC_CAUSE_NAMES,
)
from .ie_extractor import (
    extract_nas_ies, extract_ngap_ies, extract_rrc_ies,
    extract_f1ap_ies, extract_e1ap_ies, extract_xnap_ies,
    build_message_event,
)
from .f1ap_parser import handle_f1ap_real, handle_f1ap_raw, REAL_F1AP_PROC_MAP, F1AP_CAUSE_NAMES
from .e1ap_parser import handle_e1ap_real, handle_e1ap_raw, REAL_E1AP_PROC_MAP, E1AP_CAUSE_NAMES
from .xnap_parser import handle_xnap_real, handle_xnap_raw, REAL_XNAP_PROC_MAP, XNAP_CAUSE_NAMES

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s — %(name)s — %(levelname)s — %(message)s'
)
logger = logging.getLogger(__name__)

# Synthetic payload discriminators
DISC_NAS  = 0x7e
DISC_NGAP = 0x3a
DISC_RRC  = 0x2b

# NGAP / RRC synthetic message categories
MSG_REQUEST  = 0x00
MSG_RESPONSE = 0x01
MSG_FAILURE  = 0x02

# RRC-specific
RRC_REQUEST  = 0x00
RRC_COMPLETE = 0x01
RRC_REJECT   = 0x02

# IE names (as produced by ie_extractor's readable field map) that carry a
# cell identity — only populated on real pyshark-dissected captures with the
# IE present in that particular message; synthetic PCAPs never have this.
CELL_ID_IE_KEYS = ("NR-CGI",)


@dataclass
class ProcedureRecord:
    procedure_type: str
    transaction_key: str
    start_time: float
    ue_id: Optional[str] = None
    layer: str = "NAS"


@dataclass
class ProcedureStats:
    attempts: int = 0
    success: int = 0
    failure: int = 0
    failure_causes: Dict[str, int] = field(default_factory=dict)
    layer: str = "NAS"
    cell_id: Optional[str] = None

    @property
    def success_rate(self) -> float:
        if self.attempts == 0:
            return 0.0
        return round((self.success / self.attempts) * 100, 2)


class PCAPParser:
    """
    Multi-protocol PCAP parser supporting all six 3GPP interface layers.
    Extracts full Information Elements from real captures via pyshark.
    Falls back to raw payload parsing for synthetic test PCAPs.
    """

    # NGAP synthetic procedure codes (our simulation codes)
    NGAP_PROCS = NGAP_PROCS
    # RRC synthetic procedure codes
    RRC_PROCS = RRC_PROCS

    # RRC procedure name → pyshark message string patterns for real captures
    RRC_REAL_PATTERNS: List[Tuple[str, str, str]] = [
        ('rrcSetupRequest',            'RRC_Setup',              'request'),
        ('rrcSetupComplete',           'RRC_Setup',              'complete'),
        ('rrcSetup ',                  'RRC_Setup',              'complete'),
        ('rrcReject',                  'RRC_Setup',              'reject'),
        ('rrcReestablishmentRequest',  'RRC_Reestablishment',    'request'),
        ('rrcReestablishmentComplete', 'RRC_Reestablishment',    'complete'),
        ('rrcReestablishmentReject',   'RRC_Reestablishment',    'reject'),
        ('rrcReconfigurationComplete', 'RRC_Reconfiguration',    'complete'),
        ('rrcReconfiguration ',        'RRC_Reconfiguration',    'command'),
        ('rrcRelease',                 'RRC_Release',            'command'),
        ('securityModeCommand',        'RRC_SecurityMode',       'command'),
        ('securityModeComplete',       'RRC_SecurityMode',       'complete'),
        ('securityModeFailure',        'RRC_SecurityMode',       'reject'),
        ('ueCapabilityEnquiry',        'RRC_UECapabilityEnquiry','request'),
        ('ueCapabilityInformation',    'RRC_UECapabilityEnquiry','response'),
        ('measurementReport',          'RRC_MeasurementReport',  'request'),
        ('rrcSuspend',                 'RRC_Suspend',            'command'),
        ('rrcSuspendComplete',         'RRC_Suspend',            'complete'),
        ('rrcResume',                  'RRC_Resume',             'command'),
        ('rrcResumeComplete',          'RRC_Resume',             'complete'),
    ]

    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds
        self.stats: Dict[str, ProcedureStats] = defaultdict(ProcedureStats)
        self.pending: Dict[str, ProcedureRecord] = {}
        self.message_log: List[Dict[str, Any]] = []
        self.total_packets = 0
        self.total_events = 0

    # ── Public API ────────────────────────────────────────────────────

    def parse(self, pcap_path: str) -> Dict[str, Any]:
        path = Path(pcap_path)
        if not path.exists():
            raise FileNotFoundError(f"PCAP not found: {pcap_path}")
        size_mb = path.stat().st_size / (1024 * 1024)
        logger.info(f"Parsing: {path.name} ({size_mb:.1f} MB)")
        self._process_pcap(str(path))
        self._handle_timeouts()
        return self._build_output(str(path))

    # ── PCAP iteration ────────────────────────────────────────────────

    def _process_pcap(self, pcap_path: str) -> None:
        # Real captures: nas-5gs / ngap / nr-rrc / f1ap / e1ap / xnap
        # Synthetic PCAP: udp.port == 38412
        display_filter = (
            "nas-5gs or ngap or nr-rrc or f1ap or e1ap or xnap "
            "or udp.port == 38412"
        )
        logger.info(f"Filter: '{display_filter}'")
        cap = pyshark.FileCapture(
            pcap_path, display_filter=display_filter, keep_packets=False
        )
        try:
            for packet in cap:
                self.total_packets += 1
                self._process_packet(packet)
                if self.total_packets % 100 == 0:
                    logger.info(
                        f"Progress: {self.total_packets} packets, "
                        f"{self.total_events} events"
                    )
        except Exception as e:
            logger.error(f"Parse error at packet {self.total_packets}: {e}")
        finally:
            cap.close()
            logger.info(
                f"Done: {self.total_packets} packets, {self.total_events} events"
            )

    def _process_packet(self, packet) -> None:
        try:
            handled = False
            # Real captures — pyshark dissects layers
            if hasattr(packet, 'nas_5gs'):
                self._handle_nas_5gs(packet)
                handled = True
            if hasattr(packet, 'ngap'):
                self._handle_ngap_real(packet)
                handled = True
            if hasattr(packet, 'nr_rrc'):
                self._handle_rrc_real(packet)
                handled = True
            if hasattr(packet, 'f1ap'):
                handle_f1ap_real(
                    packet,
                    self._record_request, self._record_success, self._record_failure,
                    self._inc_events, extract_f1ap_ies
                )
                handled = True
            if hasattr(packet, 'e1ap'):
                handle_e1ap_real(
                    packet,
                    self._record_request, self._record_success, self._record_failure,
                    self._inc_events, extract_e1ap_ies
                )
                handled = True
            if hasattr(packet, 'xnap'):
                handle_xnap_real(
                    packet,
                    self._record_request, self._record_success, self._record_failure,
                    self._inc_events, extract_xnap_ies
                )
                handled = True
            # Synthetic PCAP — raw UDP with discriminator byte
            if not handled and hasattr(packet, 'udp') and hasattr(packet, 'data'):
                self._handle_raw_payload(packet)
        except AttributeError as e:
            logger.debug(f"Packet {self.total_packets} attribute error: {e}")
        except Exception as e:
            logger.warning(f"Packet {self.total_packets} error: {e}")

    # ── Real capture handlers ─────────────────────────────────────────

    def _handle_nas_5gs(self, packet) -> None:
        try:
            nas = packet.nas_5gs
            timestamp = float(packet.sniff_timestamp)
            ue_id = str(getattr(getattr(packet, 'ip', None), 'src', 'unknown'))
            msg_type = None
            for fname in ['mm_msg_type', 'sm_msg_type', 'nas_5gs_mm_msg_type',
                           'nas_5gs_sm_msg_type', 'msg_type']:
                raw = getattr(nas, fname, None)
                if raw is not None:
                    try:
                        val = str(raw)
                        msg_type = int(val, 16) if val.startswith('0x') else int(val)
                        break
                    except ValueError:
                        continue
            if msg_type is None:
                return
            cause_raw = getattr(nas, 'cause', None)
            cause_byte = int(str(cause_raw)) if cause_raw is not None else None
            ies = extract_nas_ies(packet)
            self._process_nas_message(msg_type, ue_id, timestamp, cause_byte, ies)
        except Exception as e:
            logger.debug(f"NAS 5GS parse error: {e}")

    def _handle_ngap_real(self, packet) -> None:
        try:
            ngap = packet.ngap
            timestamp = float(packet.sniff_timestamp)
            proc_code = None
            for fname in ['procedurecode', 'procedure_code']:
                raw = getattr(ngap, fname, None)
                if raw is not None:
                    try:
                        proc_code = int(str(raw))
                        break
                    except ValueError:
                        continue
            if proc_code is None:
                return
            proc_name = REAL_NGAP_PROC_MAP.get(proc_code, f"NGAP_Procedure_{proc_code}")
            ue_id = str(getattr(ngap, 'amf_ue_ngap_id', 'unknown'))
            tx_key = f"ngap_{proc_name}_{ue_id}"
            ngap_str = str(ngap).lower()
            is_response = 'successfuloutcome' in ngap_str
            is_failure  = 'unsuccessfuloutcome' in ngap_str
            ies = extract_ngap_ies(packet)
            if not is_response and not is_failure:
                self._record_request(proc_name, tx_key, timestamp, ue_id, 'NGAP', ies)
            elif is_response:
                self._record_success(proc_name, tx_key, 'NGAP', ies)
            else:
                cause = str(getattr(ngap, 'cause', 'unknown'))
                self._record_failure(proc_name, tx_key, cause, 'NGAP', ies)
            self._inc_events()
        except Exception as e:
            logger.debug(f"NGAP real parse error: {e}")

    def _handle_rrc_real(self, packet) -> None:
        try:
            rrc = packet.nr_rrc
            timestamp = float(packet.sniff_timestamp)
            ue_id = str(getattr(getattr(packet, 'ip', None), 'src', 'unknown'))
            msg_str = str(rrc)
            ies = extract_rrc_ies(packet)
            for pattern, proc_name, role in self.RRC_REAL_PATTERNS:
                if pattern in msg_str:
                    tx_key = f"rrc_{proc_name}_{ue_id}"
                    self._process_role(proc_name, tx_key, role, timestamp, ue_id, 'RRC', None, ies)
                    self._inc_events()
                    break
        except Exception as e:
            logger.debug(f"RRC real parse error: {e}")

    # ── Synthetic PCAP handlers ───────────────────────────────────────

    def _handle_raw_payload(self, packet) -> None:
        try:
            raw_hex = str(packet.data.data).replace(':', '')
            if len(raw_hex) < 6:
                return
            raw_bytes = bytes.fromhex(raw_hex)
            timestamp = float(packet.sniff_timestamp)
            disc = raw_bytes[0]
            if disc == DISC_NAS:
                self._handle_nas_raw(raw_bytes, timestamp)
            elif disc == DISC_NGAP:
                self._handle_ngap_raw(raw_bytes, timestamp)
            elif disc == DISC_RRC:
                self._handle_rrc_raw(raw_bytes, timestamp)
            elif disc == DISC_F1AP:
                handle_f1ap_raw(
                    raw_bytes, timestamp,
                    self._record_request, self._record_success, self._record_failure,
                    self._inc_events
                )
            elif disc == DISC_E1AP:
                handle_e1ap_raw(
                    raw_bytes, timestamp,
                    self._record_request, self._record_success, self._record_failure,
                    self._inc_events
                )
            elif disc == DISC_XNAP:
                handle_xnap_raw(
                    raw_bytes, timestamp,
                    self._record_request, self._record_success, self._record_failure,
                    self._inc_events
                )
        except (ValueError, struct.error) as e:
            logger.debug(f"Raw payload parse error: {e}")

    def _handle_nas_raw(self, raw_bytes: bytes, timestamp: float) -> None:
        if len(raw_bytes) < 7:
            return
        msg_type   = raw_bytes[2]
        tmsi       = struct.unpack('>I', raw_bytes[3:7])[0]
        cause_byte = raw_bytes[7] if len(raw_bytes) > 7 else None
        self._process_nas_message(msg_type, str(tmsi), timestamp, cause_byte, {})

    def _handle_ngap_raw(self, raw_bytes: bytes, timestamp: float) -> None:
        if len(raw_bytes) < 7:
            return
        proc_code  = raw_bytes[1]
        msg_cat    = raw_bytes[2]
        ue_id      = str(struct.unpack('>I', raw_bytes[3:7])[0])
        cause_byte = raw_bytes[7] if len(raw_bytes) > 7 else None
        proc_name  = self.NGAP_PROCS.get(proc_code, f"NGAP_Proc_{proc_code:02x}")
        tx_key     = f"ngap_{proc_name}_{ue_id}"
        if msg_cat == MSG_REQUEST:
            self._record_request(proc_name, tx_key, timestamp, ue_id, 'NGAP', {})
        elif msg_cat == MSG_RESPONSE:
            self._record_success(proc_name, tx_key, 'NGAP', {})
        elif msg_cat == MSG_FAILURE:
            cause = NGAP_CAUSE_NAMES.get(cause_byte, f"unknown-0x{cause_byte:02x}") \
                    if cause_byte else "unknown"
            self._record_failure(proc_name, tx_key, cause, 'NGAP', {})
        self._inc_events()

    def _handle_rrc_raw(self, raw_bytes: bytes, timestamp: float) -> None:
        if len(raw_bytes) < 7:
            return
        proc_code  = raw_bytes[1]
        msg_cat    = raw_bytes[2]
        ue_id      = str(struct.unpack('>I', raw_bytes[3:7])[0])
        cause_byte = raw_bytes[7] if len(raw_bytes) > 7 else None
        proc_name  = self.RRC_PROCS.get(proc_code, f"RRC_Proc_{proc_code:02x}")
        tx_key     = f"rrc_{proc_name}_{ue_id}"
        if msg_cat == RRC_REQUEST:
            self._record_request(proc_name, tx_key, timestamp, ue_id, 'RRC', {})
        elif msg_cat == RRC_COMPLETE:
            self._record_success(proc_name, tx_key, 'RRC', {})
        elif msg_cat == RRC_REJECT:
            cause = RRC_CAUSE_NAMES.get(cause_byte, f"unknown-0x{cause_byte:02x}") \
                    if cause_byte else "unknown"
            self._record_failure(proc_name, tx_key, cause, 'RRC', {})
        self._inc_events()

    # ── Shared helpers ────────────────────────────────────────────────

    def _process_nas_message(self, msg_type: int, ue_id: str, timestamp: float,
                              cause_byte: Optional[int],
                              ies: Dict[str, str]) -> None:
        info = NAS_5GMM_MSGS.get(msg_type) or NAS_5GSM_MSGS.get(msg_type)
        if info is None:
            logger.debug(f"Unknown NAS msg_type: 0x{msg_type:02x}")
            return
        proc_name, role = info
        tx_key = f"nas_{proc_name}_{ue_id}"
        cause = None
        if role in ('reject', 'failure') and cause_byte is not None:
            cause = NAS_CAUSE_NAMES.get(cause_byte, f"unknown-0x{cause_byte:02x}")
        self._process_role(proc_name, tx_key, role, timestamp, ue_id, 'NAS', cause, ies)
        self._inc_events()

    def _process_role(self, proc_name: str, tx_key: str, role: str,
                      timestamp: float, ue_id: str, layer: str,
                      cause: Optional[str], ies: Dict[str, str]) -> None:
        if role in ('request', 'command'):
            self._record_request(proc_name, tx_key, timestamp, ue_id, layer, ies)
        elif role in ('accept', 'response', 'complete', 'result'):
            self._record_success(proc_name, tx_key, layer, ies)
        elif role in ('reject', 'failure'):
            self._record_failure(proc_name, tx_key, cause or 'unknown', layer, ies)

    def _maybe_capture_cell_id(self, proc_name: str, ies: Dict[str, str]) -> None:
        """Remember the first real cell identity IE (e.g. NR-CGI) seen for
        this procedure type, so anomalies for it can be correlated by cell
        against KPI/Stats data. Requires a real pyshark-dissected capture —
        synthetic PCAPs carry no IEs and leave this unset."""
        if self.stats[proc_name].cell_id:
            return
        for key in CELL_ID_IE_KEYS:
            if ies.get(key):
                self.stats[proc_name].cell_id = ies[key]
                return

    def _record_request(self, proc_name: str, tx_key: str, timestamp: float,
                        ue_id: str, layer: str, ies: Dict[str, str]) -> None:
        self.stats[proc_name].attempts += 1
        self.stats[proc_name].layer = layer
        self._maybe_capture_cell_id(proc_name, ies)
        self.pending[tx_key] = ProcedureRecord(
            procedure_type=proc_name, transaction_key=tx_key,
            start_time=timestamp, ue_id=ue_id, layer=layer,
        )
        self.message_log.append(
            build_message_event(layer, proc_name, 'request', ue_id, timestamp, ies)
        )
        logger.debug(f"{layer} REQUEST: {proc_name} UE={ue_id} IEs={len(ies)}")

    def _record_success(self, proc_name: str, tx_key: str,
                        layer: str, ies: Dict[str, str]) -> None:
        if tx_key in self.pending:
            rec = self.pending[tx_key]
            self.stats[proc_name].success += 1
            self.stats[proc_name].layer = layer
            self._maybe_capture_cell_id(proc_name, ies)
            self.message_log.append(
                build_message_event(layer, proc_name, 'response', rec.ue_id or 'unknown',
                                    rec.start_time, ies)
            )
            del self.pending[tx_key]
            logger.debug(f"{layer} SUCCESS: {proc_name} ✓")

    def _record_failure(self, proc_name: str, tx_key: str, cause: str,
                        layer: str, ies: Dict[str, str]) -> None:
        if tx_key in self.pending:
            rec = self.pending[tx_key]
            self.stats[proc_name].failure += 1
            self.stats[proc_name].layer = layer
            self._maybe_capture_cell_id(proc_name, ies)
            causes = self.stats[proc_name].failure_causes
            causes[cause] = causes.get(cause, 0) + 1
            ie_with_cause = dict(ies)
            ie_with_cause['Cause'] = cause
            self.message_log.append(
                build_message_event(layer, proc_name, 'failure', rec.ue_id or 'unknown',
                                    rec.start_time, ie_with_cause)
            )
            del self.pending[tx_key]
            logger.debug(f"{layer} FAILURE: {proc_name} cause={cause} ✗")

    def _inc_events(self) -> None:
        self.total_events += 1

    def _handle_timeouts(self) -> None:
        if not self.pending:
            return
        logger.info(f"Found {len(self.pending)} timed-out procedures")
        for key, record in self.pending.items():
            self.stats[record.procedure_type].failure += 1
            causes = self.stats[record.procedure_type].failure_causes
            causes['timeout'] = causes.get('timeout', 0) + 1
            self.message_log.append(
                build_message_event(record.layer, record.procedure_type, 'timeout',
                                    record.ue_id or 'unknown', record.start_time,
                                    {'Cause': 'timeout'})
            )
        self.pending.clear()

    def _build_output(self, filename: str) -> Dict[str, Any]:
        procedures_out = {}
        for proc_name, stats in self.stats.items():
            procedures_out[proc_name] = {
                "attempts":       stats.attempts,
                "success":        stats.success,
                "failure":        stats.failure,
                "success_rate":   stats.success_rate,
                "failure_causes": dict(stats.failure_causes),
                "layer":          stats.layer,
                "cell_id":        stats.cell_id or "—",
            }

        # Per-layer event counts
        layer_event_counts: Dict[str, int] = defaultdict(int)
        for evt in self.message_log:
            layer_event_counts[evt["layer"]] += 1

        return {
            "filename":                Path(filename).name,
            "total_events":            self.total_events,
            "total_packets_processed": self.total_packets,
            "procedures":              procedures_out,
            "message_log":             self.message_log,
            "layer_event_counts":      dict(layer_event_counts),
            "parser_version":          "real_v3",
            "layers_supported":        ["NAS", "NGAP", "RRC", "F1AP", "E1AP", "XnAP"],
        }


def parse_pcap(filepath: str) -> Dict[str, Any]:
    """Public API — wraps PCAPParser."""
    return PCAPParser().parse(filepath)
