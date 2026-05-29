"""
E1AP Parser — TS 38.463
========================
E1 interface: gNB-CU-CP ↔ gNB-CU-UP

Handles both:
  • Real captures  — pyshark e1ap layer (SCTP port 38462)
  • Synthetic PCAP — raw UDP payload with discriminator 0x1b

Synthetic payload format:
  [0x1b][proc_code:1][msg_cat:1][ue_id:4][cause:1 optional]
  msg_cat: 0x00=Request  0x01=Response  0x02=Failure
"""

import logging
import struct
from typing import Dict, Any

from .protocol_defs import E1AP_PROCS, E1AP_CAUSE_NAMES, DISC_E1AP

logger = logging.getLogger(__name__)

# Real E1AP procedure codes (TS 38.463 §9.2 Table 9.2.1-1)
REAL_E1AP_PROC_MAP: Dict[int, str] = {
    1:  "E1AP_Reset",
    2:  "E1AP_ErrorIndication",
    3:  "E1AP_PrivateMessage",
    4:  "E1AP_GNBCUUPSetup",
    5:  "E1AP_GNBCUUPStatusIndication",
    6:  "E1AP_GNBCUCPConfigurationUpdate",
    7:  "E1AP_GNBCUUPConfigurationUpdate",
    8:  "E1AP_BearerContextSetup",
    9:  "E1AP_BearerContextModification",
    10: "E1AP_BearerContextModificationRequired",
    11: "E1AP_BearerContextRelease",
    12: "E1AP_BearerContextReleaseRequest",
    13: "E1AP_BearerContextInactivityNotification",
    14: "E1AP_DLDataNotification",
    15: "E1AP_ULDataNotification",
    16: "E1AP_DataUsageReport",
    17: "E1AP_GNBCUUPCounterCheck",
    18: "E1AP_GNBCUUPResourceStatusRequest",
    19: "E1AP_GNBCUUPResourceStatusUpdate",
    20: "E1AP_GNBCUUPResourceStatusFailure",
    21: "E1AP_ResourceStatusUpdate",
    22: "E1AP_IABUPConfigurationUpdate",
    23: "E1AP_CellTrafficTrace",
    24: "E1AP_EarlyForwardingSNTransfer",
    25: "E1AP_GNBCUCPMeasurementResultsInformation",
    26: "E1AP_IABPSKNotification",
    27: "E1AP_BCBearerContextSetup",
    28: "E1AP_BCBearerContextModification",
    29: "E1AP_BCBearerContextRelease",
    30: "E1AP_MCBearerContextSetup",
    31: "E1AP_MCBearerContextModification",
    32: "E1AP_MCBearerContextRelease",
    33: "E1AP_MCBearerNotification",
    34: "E1AP_MCBearerContextModificationRequired",
}

REQUEST_CAT  = 0x00
RESPONSE_CAT = 0x01
FAILURE_CAT  = 0x02


def handle_e1ap_real(packet, record_request_fn, record_success_fn,
                     record_failure_fn, inc_events_fn,
                     extract_ies_fn) -> None:
    """Handle real E1AP packet via pyshark e1ap layer."""
    try:
        e1ap = packet.e1ap
        timestamp = float(packet.sniff_timestamp)

        proc_code = None
        for field in ['procedurecode', 'procedure_code', 'procedureCode']:
            raw = getattr(e1ap, field, None)
            if raw is not None:
                try:
                    proc_code = int(str(raw))
                    break
                except ValueError:
                    continue
        if proc_code is None:
            return

        proc_name = REAL_E1AP_PROC_MAP.get(proc_code, f"E1AP_Proc_{proc_code}")
        e1ap_str  = str(e1ap).lower()

        ue_id = str(getattr(e1ap, 'gNB_CU_CP_UE_E1AP_ID',
                    getattr(e1ap, 'gNB_CU_UP_UE_E1AP_ID', 'unknown')))
        tx_key = f"e1ap_{proc_name}_{ue_id}"

        is_response = 'successfuloutcome' in e1ap_str
        is_failure  = 'unsuccessfuloutcome' in e1ap_str

        ies = extract_ies_fn(packet)

        if not is_response and not is_failure:
            record_request_fn(proc_name, tx_key, timestamp, ue_id, 'E1AP', ies)
        elif is_response:
            record_success_fn(proc_name, tx_key, 'E1AP', ies)
        else:
            cause = str(getattr(e1ap, 'cause', 'unknown'))
            record_failure_fn(proc_name, tx_key, cause, 'E1AP', ies)

        inc_events_fn()

    except Exception as e:
        logger.debug(f"E1AP real parse error: {e}")


def handle_e1ap_raw(raw_bytes: bytes, timestamp: float,
                    record_request_fn, record_success_fn,
                    record_failure_fn, inc_events_fn) -> None:
    """Handle synthetic E1AP payload. Format: [0x1b][proc][cat][ID:4][cause?]"""
    if len(raw_bytes) < 7:
        return
    proc_code  = raw_bytes[1]
    msg_cat    = raw_bytes[2]
    ue_id      = str(struct.unpack('>I', raw_bytes[3:7])[0])
    cause_byte = raw_bytes[7] if len(raw_bytes) > 7 else None

    proc_name = E1AP_PROCS.get(proc_code, f"E1AP_Proc_{proc_code:02x}")
    tx_key    = f"e1ap_{proc_name}_{ue_id}"

    if msg_cat == REQUEST_CAT:
        record_request_fn(proc_name, tx_key, timestamp, ue_id, 'E1AP', {})
    elif msg_cat == RESPONSE_CAT:
        record_success_fn(proc_name, tx_key, 'E1AP', {})
    elif msg_cat == FAILURE_CAT:
        cause = E1AP_CAUSE_NAMES.get(cause_byte, f"unknown-0x{cause_byte:02x}") \
                if cause_byte else "unknown"
        record_failure_fn(proc_name, tx_key, cause, 'E1AP', {})

    inc_events_fn()
