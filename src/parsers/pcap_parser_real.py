"""
Real PCAP Parser — Unified Telecom Analyzer
============================================

PURPOSE:
    Replace the stub parser (pcap_parser.py) with real packet analysis.
    Uses pyshark to parse actual PCAP files and extract 5G procedure
    success/failure statistics.

WHY THIS FILE EXISTS SEPARATELY FROM pcap_parser.py:
    Incremental development principle — never break working code.
    Stub is still used by dashboard. We build and TEST this separately,
    then swap it in only when it's proven to work.
    
    This is called "Strangler Fig Pattern" in software engineering:
    new implementation grows alongside old one, replaces it gradually.

WHY PYSHARK:
    pyshark wraps tshark (Wireshark CLI). Wireshark has 3000+ protocol
    dissectors including full 5G NAS, NGAP, RRC support. We leverage
    years of Wireshark development instead of reimplementing from scratch.

ARCHITECTURE:
    PCAPParser (class)
        ├── parse()              ← main entry point
        ├── _process_pcap()      ← packet iteration
        ├── _process_packet()    ← per-packet routing
        ├── _handle_nas()        ← NAS message processing
        ├── _handle_timeouts()   ← detect missing responses
        └── _build_output()      ← format results for dashboard

3GPP REFERENCES:
    TS 24.501 — NAS protocol (Registration, Authentication, PDU Session)
    TS 38.413 — NGAP protocol (InitialContextSetup, PDUSession)
    TS 38.331 — RRC protocol (RRC Setup, Reestablishment)
"""

# ── Standard library imports ──────────────────────────────────────
import logging        # WHY: structured logging vs print() — timestamps,
                      # levels, easy to disable in production
import struct         # WHY: parse binary data from packet payloads
                      # (TMSI, cause codes are binary-encoded)
import time           # WHY: timestamp-based timeout detection
from pathlib import Path          # WHY: OS-independent file path handling
from typing import Dict, Any, Optional   # WHY: type hints = self-documenting
                                         # code, IDE autocomplete, catch bugs early
from collections import defaultdict      # WHY: auto-creates missing keys,
                                         # cleaner than "if key not in dict"
from dataclasses import dataclass, field # WHY: typed data containers,
                                         # auto __repr__ for debugging

# ── Third-party imports ───────────────────────────────────────────
import pyshark   # WHY: Python wrapper for tshark — gives us Python objects
                 # instead of raw tshark string output to parse manually

# ── Logging setup ─────────────────────────────────────────────────
# WHY BASICCONFIG HERE (not in main):
#   Module-level setup ensures logging works even when imported
#   by other modules (like the dashboard or tests)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s — %(name)s — %(levelname)s — %(message)s'
    # WHY THIS FORMAT:
    # asctime = when it happened (debug timing issues)
    # name = which module logged it (find source quickly)
    # levelname = severity (filter by level)
    # message = what happened
)
logger = logging.getLogger(__name__)
# WHY __name__:
#   Creates logger named after module ("src.parsers.pcap_parser_real")
#   If parser is imported, logs show exactly which module they came from

# ── Data Classes ──────────────────────────────────────────────────

@dataclass
class ProcedureRecord:
    """
    Tracks ONE in-progress 5G procedure waiting for response.

    WHY DATACLASS OVER DICT:
        dict would work: {"type": "NAS_Reg", "tmsi": 1001, ...}
        But dataclass gives:
        1. Type hints — IDE tells you what fields exist
        2. Auto __repr__ — print(record) shows all fields nicely
        3. Default values — field(default_factory=...) for mutable defaults
        4. Immutability option — frozen=True if needed later

    ANALOGY:
        Like a "ticket" opened when Request arrives.
        Ticket stays open until Response arrives.
        If no Response → timeout → ticket closed as failure.

    EXAMPLE LIFECYCLE:
        t=0.1s: RRC Setup Request (UE-5) arrives
                → ProcedureRecord created, added to pending dict
        t=0.3s: RRC Setup Complete (UE-5) arrives
                → ProcedureRecord found in pending, deleted
                → success count incremented
        t=never: No response for UE-7
                → After all packets processed, still in pending
                → Counted as timeout failure
    """
    procedure_type: str    # "NAS_Registration", "RRC_Setup", etc.
    transaction_key: str   # Unique key to match request with response
    start_time: float      # Unix timestamp — for timeout detection
    ue_id: Optional[str] = None  # Which UE — for debugging


@dataclass
class ProcedureStats:
    """
    Accumulated statistics for ONE procedure type.

    WHY SEPARATE FROM ProcedureRecord:
        ProcedureRecord = temporary (one pending procedure)
        ProcedureStats  = permanent (accumulated results)

        Single Responsibility Principle:
        - ProcedureRecord is responsible for TRACKING
        - ProcedureStats is responsible for COUNTING

    WHY success_rate IS A PROPERTY (not stored field):
        If we stored success_rate as a field, we'd need to update it
        every time attempts or success changes — risk of inconsistency.

        Property = computed on demand from source of truth.
        Always accurate, never stale.

        This is called "Derived Attribute" pattern.

    DASHBOARD COMPATIBILITY:
        Output dict from _build_output() must match stub schema exactly:
        {
            "attempts": int,
            "success": int,
            "failure": int,
            "success_rate": float,
            "failure_causes": dict
        }
        This dataclass maps 1:1 to that schema.
    """
    attempts: int = 0
    success: int = 0
    failure: int = 0

    # WHY field(default_factory=dict):
    #   Mutable default values (like dicts) cannot be set directly
    #   in dataclasses — Python would share ONE dict across ALL instances.
    #   default_factory=dict creates a NEW dict for EACH instance.
    #   Bug without this: parser1.failure_causes and parser2.failure_causes
    #   would be the SAME dict — adding to one adds to both!
    failure_causes: Dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """
        Compute success rate — always fresh from source of truth.

        WHY GUARD AGAINST ZERO:
            Division by zero if no attempts yet.
            Returns 0.0 instead of raising ZeroDivisionError.
            Defensive programming — real data is messy.

        WHY round(..., 2):
            98.163265306... is not useful for display.
            98.16 is clean and meaningful.
            2 decimal places = standard in telecom KPI reporting.
        """
        if self.attempts == 0:
            return 0.0
        return round((self.success / self.attempts) * 100, 2)
    
    # ── Main Parser Class ─────────────────────────────────────────────

class PCAPParser:
    """
    Converts raw PCAP file → structured procedure statistics.

    WHY CLASS OVER FUNCTIONS:
        Parser needs to maintain STATE across multiple methods:
        - pending: dict of in-progress procedures
        - stats: accumulated results
        - counters: total packets, events

        With functions, we'd pass these as arguments to every function.
        Class encapsulates related state + behavior together.
        This is the core purpose of OOP.

    DESIGN PATTERN — Pipeline:
        parse() → _process_pcap() → _process_packet() → _handle_*()
                                                       → _build_output()
        Each stage has ONE responsibility.
        Easy to test each stage independently.
        Easy to add new protocol handlers (_handle_rrc, _handle_ngap).
    """

    # NAS Message Types (TS 24.501 Table 9.7.1)
    # WHY CLASS CONSTANTS OVER MAGIC NUMBERS:
    #   0x41 scattered in code = mystery number, hard to understand
    #   NAS_REG_REQUEST = 0x41 = self-documenting
    #   Single place to update if spec changes
    NAS_REG_REQUEST = 0x41   # Registration Request
    NAS_REG_ACCEPT  = 0x42   # Registration Accept
    NAS_REG_REJECT  = 0x44   # Registration Reject

    # 5GMM Cause codes (TS 24.501 Section 9.11.3.2)
    # WHY REVERSE MAP (value → name):
    #   Packet gives us 0x16, we want to show "congestion" to engineer
    #   Dict lookup is O(1) and readable
    CAUSE_NAMES = {
        0x02: "imsi-unknown-in-hss",
        0x03: "illegal-ue",
        0x06: "illegal-me",
        0x07: "5gs-not-allowed",
        0x09: "ue-identity-not-derived",
        0x0a: "implicitly-detached",
        0x0b: "plmn-not-allowed",
        0x0c: "ta-not-allowed",
        0x0f: "no-suitable-cells",
        0x14: "mac-failure",
        0x15: "auth-failure",        # 0x15 = 21 decimal
        0x16: "congestion",          # 0x16 = 22 decimal
        0x1a: "semantically-incorrect-message",
        0x5f: "protocol-error",
    }

    def __init__(self, timeout_seconds: int = 30):
        """
        WHY TIMEOUT PARAMETER (default 30s):
            In real networks, procedures can be abandoned silently.
            UE moves out of coverage mid-procedure — no Reject sent.
            After ALL packets processed, pending = timed out procedures.

            30s chosen because:
            - T300 (RRC Setup timer) = 1s
            - T3510 (Registration timer) = 15s
            - 30s gives margin for slow networks
            - TS 24.501 Section 10.2 defines these timers

        WHY defaultdict(ProcedureStats):
            Regular dict: if "NAS_Reg" not in stats → KeyError
            defaultdict: if "NAS_Reg" not in stats → auto-create ProcedureStats()
            Cleaner code — no "if not exists: initialize" boilerplate
        """
        self.timeout_seconds = timeout_seconds
        self.stats: Dict[str, ProcedureStats] = defaultdict(ProcedureStats)
        self.pending: Dict[str, ProcedureRecord] = {}
        self.total_packets = 0
        self.total_events = 0

    def parse(self, pcap_path: str) -> Dict[str, Any]:
        """
        Main entry point — parse PCAP, return dashboard-compatible dict.

        WHY VALIDATE PATH FIRST:
            Better to fail fast with clear error than let pyshark
            give cryptic tshark error message deep in the call stack.
            "FileNotFoundError: test.pcap" is more helpful than
            "tshark: The file 'test.pcap' doesn't exist".

        WHY LOG FILE SIZE:
            Helps engineer estimate how long parsing will take.
            100 MB file = ~30s. 1 GB file = ~5 min. Set expectations.
        """
        path = Path(pcap_path)
        if not path.exists():
            raise FileNotFoundError(f"PCAP not found: {pcap_path}")

        size_mb = path.stat().st_size / (1024 * 1024)
        logger.info(f"Parsing: {path.name} ({size_mb:.1f} MB)")

        self._process_pcap(str(path))
        self._handle_timeouts()

        return self._build_output(str(path))

    def _process_pcap(self, pcap_path: str) -> None:
        """
        WHY display_filter = 'udp.port == 38412':
            Our synthetic PCAP uses UDP port 38412 (NGAP port).
            This filter keeps only our NAS-over-UDP packets.
            In real 5G captures, you'd use 'ngap or nas-5gs'.
            We'll extend this in Phase II for real captures.

        WHY keep_packets=False:
            pyshark default caches ALL packets in RAM.
            Large PCAP (1 GB) = 1 GB RAM usage → OOM crash.
            keep_packets=False = process one packet, discard, next.
            RAM usage stays constant regardless of file size.
            Trade-off: cannot go back to previous packets.
            Acceptable because we process sequentially.

        WHY try/finally for cap.close():
            cap.close() kills the tshark subprocess.
            If exception occurs mid-parse, finally ensures cleanup.
            Without this: tshark process keeps running → resource leak.
            Rule: always close resources in finally block.
        """
        # For synthetic test PCAP: filter by our UDP port
        # For real 5G captures: use 'ngap or nas-5gs or nr-rrc'
        display_filter = "udp.port == 38412"

        logger.info(f"Filter: '{display_filter}'")
        logger.info("Loading packets (keep_packets=False = constant RAM usage)")

        cap = pyshark.FileCapture(
            pcap_path,
            display_filter=display_filter,
            keep_packets=False
        )

        try:
            for packet in cap:
                self.total_packets += 1
                self._process_packet(packet)

                # WHY LOG EVERY 100 (not every 1):
                #   Progress feedback without flooding logs.
                #   100 = good balance for small test files.
                #   Production: increase to 1000+
                if self.total_packets % 100 == 0:
                    logger.info(
                        f"Progress: {self.total_packets} packets, "
                        f"{self.total_events} NAS events found"
                    )

        except Exception as e:
            logger.error(f"Parse error at packet {self.total_packets}: {e}")
        finally:
            cap.close()
            logger.info(
                f"Done: {self.total_packets} packets, "
                f"{self.total_events} NAS events"
            )

    def _process_packet(self, packet) -> None:
        """
        WHY hasattr CHECK:
            Not every packet has every layer.
            packet.udp on non-UDP packet → AttributeError.
            hasattr() safely checks existence.

        WHY try/except PER PACKET:
            One malformed packet should NOT stop entire analysis.
            Real captures have corrupted packets, partial captures, etc.
            Log warning, skip packet, continue.
            Resilience > perfection.
        """
        try:
            if hasattr(packet, 'udp') and hasattr(packet, 'data'):
                self._handle_nas_raw(packet)

        except AttributeError as e:
            logger.debug(f"Packet {self.total_packets} attribute error: {e}")
        except Exception as e:
            logger.warning(f"Packet {self.total_packets} error: {e}")

    def _handle_nas_raw(self, packet) -> None:
        """
        Parse our synthetic NAS payload from raw UDP data.

        WHY RAW PARSING (not pyshark NAS dissector):
            Our synthetic PCAP has custom raw payload (not full NAS).
            Real pyshark NAS parsing = for real 5G captures (Phase II).
            This method handles our test data specifically.

        PAYLOAD FORMAT (defined in generate_test_pcap.py):
            Byte 0: 0x7e (5GMM discriminator)
            Byte 1: 0x00 (security header)
            Byte 2: message type (0x41/0x42/0x44)
            Bytes 3-6: TMSI (4 bytes, big-endian)
            Byte 7: cause code (only in Reject, optional)

        WHY bytes.fromhex():
            pyshark gives raw data as hex string: "7e004100000001"
            We need bytes for struct.unpack: b'\x7e\x00\x41...'
            fromhex() converts hex string → bytes.

        WHY struct.unpack('>I', ...):
            '>' = big-endian (network byte order)
            'I' = unsigned int (4 bytes)
            TMSI is 4 bytes big-endian in our payload.
        """
        try:
            # Get raw hex data from packet
            raw_hex = str(packet.data.data).replace(':', '')

            # WHY MINIMUM LENGTH CHECK (14 hex chars = 7 bytes):
            #   Our payload minimum = 7 bytes (header + type + TMSI)
            #   Shorter = malformed, skip it
            if len(raw_hex) < 14:
                return

            raw_bytes = bytes.fromhex(raw_hex)

            # Verify 5GMM discriminator
            # WHY CHECK BYTE 0:
            #   Other UDP traffic might exist on port 38412.
            #   0x7e confirms this is our NAS message, not random data.
            if raw_bytes[0] != 0x7e:
                return

            msg_type = raw_bytes[2]   # Byte 2 = message type
            tmsi = struct.unpack('>I', raw_bytes[3:7])[0]  # Bytes 3-6
            tmsi_key = f"nas_reg_{tmsi}"
            timestamp = float(packet.sniff_timestamp)

            # WHY SEPARATE IF (not elif) FOR EACH TYPE:
            #   Each message type is handled independently.
            #   A packet cannot be both Request AND Accept.
            #   elif would work too, but if is clearer for this case.

            if msg_type == self.NAS_REG_REQUEST:
                # New registration starting
                self.stats['NAS_Registration'].attempts += 1
                self.pending[tmsi_key] = ProcedureRecord(
                    procedure_type='NAS_Registration',
                    transaction_key=tmsi_key,
                    start_time=timestamp,
                    ue_id=str(tmsi)
                )
                logger.debug(f"REG REQUEST: TMSI={tmsi}")
                self.total_events += 1

            elif msg_type == self.NAS_REG_ACCEPT:
                # Registration succeeded
                if tmsi_key in self.pending:
                    self.stats['NAS_Registration'].success += 1
                    del self.pending[tmsi_key]
                    logger.debug(f"REG ACCEPT: TMSI={tmsi} ✓")
                    self.total_events += 1

            elif msg_type == self.NAS_REG_REJECT:
                # Registration failed — extract cause
                if tmsi_key in self.pending:
                    self.stats['NAS_Registration'].failure += 1

                    # Extract cause code if present
                    # WHY len CHECK:
                    #   Cause byte is optional (byte 7).
                    #   Short payload = no cause = "unknown".
                    if len(raw_bytes) > 7:
                        cause_byte = raw_bytes[7]
                        # WHY .get() with default:
                        #   Unknown cause code → don't crash, show hex value
                        cause_name = self.CAUSE_NAMES.get(
                            cause_byte,
                            f"unknown-0x{cause_byte:02x}"
                        )
                    else:
                        cause_name = "unknown"

                    # Increment cause counter
                    causes = self.stats['NAS_Registration'].failure_causes
                    causes[cause_name] = causes.get(cause_name, 0) + 1

                    del self.pending[tmsi_key]
                    logger.debug(f"REG REJECT: TMSI={tmsi} cause={cause_name} ✗")
                    self.total_events += 1

        except (ValueError, struct.error) as e:
            logger.debug(f"Raw NAS parse error: {e}")

    def _handle_timeouts(self) -> None:
        """
        Count procedures that never got a response.

        WHY AT END (not during processing):
            During streaming, we don't know if response will come later.
            Only after ALL packets processed can we say:
            "This request has no response in the entire capture."

        WHY THIS MATTERS FOR ACCURACY:
            Without timeout handling:
            - 5 requests, 3 accepts, 1 reject = 5 attempts, 3 success, 1 failure
            - But 1 request had NO response → we're undercounting failures!

            With timeout handling:
            - Same scenario → 5 attempts, 3 success, 2 failure ✓
            - Matches our ground truth exactly
        """
        if not self.pending:
            logger.info("No timed-out procedures")
            return

        logger.info(
            f"Found {len(self.pending)} procedures with no response "
            f"(counting as timeout failures)"
        )

        for key, record in self.pending.items():
            self.stats[record.procedure_type].failure += 1
            causes = self.stats[record.procedure_type].failure_causes
            causes['timeout'] = causes.get('timeout', 0) + 1
            logger.debug(f"Timeout: {record.procedure_type} UE={record.ue_id}")

        self.pending.clear()

    def _build_output(self, filename: str) -> Dict[str, Any]:
        """
        Convert internal ProcedureStats → dashboard-compatible dict.

        WHY THIS METHOD EXISTS (Adapter Pattern):
            Internal: defaultdict of ProcedureStats objects
            Dashboard expects: nested plain dicts

            If dashboard schema changes → only this method changes.
            If internal representation changes → only this method changes.
            Nothing else needs to know about either side.

        WHY parser_version FIELD:
            Dashboard can show "real_v1" vs "stub".
            Useful for debugging: "am I seeing real data or fake?"
            MLflow can log this as a run parameter.
        """
        procedures_out = {}
        for proc_name, stats in self.stats.items():
            procedures_out[proc_name] = {
                "attempts":       stats.attempts,
                "success":        stats.success,
                "failure":        stats.failure,
                "success_rate":   stats.success_rate,
                "failure_causes": dict(stats.failure_causes),
            }

        return {
            "filename":                Path(filename).name,
            "total_events":            self.total_events,
            "total_packets_processed": self.total_packets,
            "procedures":              procedures_out,
            "parser_version":          "real_v1",
        }


def parse_pcap(filepath: str) -> Dict[str, Any]:
    """
    Public API — simple function wrapping PCAPParser class.

    WHY THIS WRAPPER EXISTS (Facade Pattern):
        Dashboard calls: parse_pcap("file.pcap")
        Dashboard does NOT need to know about PCAPParser class.
        Simple function = simple public API.
        Complex class = hidden implementation detail.

        Future: swap PCAPParser internals completely,
        dashboard code doesn't change at all.
    """
    parser = PCAPParser()
    return parser.parse(filepath)