"""
F1AP Parser — TS 38.473
========================
F1 interface: gNB-DU ↔ gNB-CU-CP

Handles both:
  • Real captures  — pyshark f1ap layer (SCTP port 38472)
  • Synthetic PCAP — raw UDP payload with discriminator 0x1a

Synthetic payload format:
  [0x1a][proc_code:1][msg_cat:1][node_id:4][cause:1 optional]
  msg_cat: 0x00=Request/Initiating  0x01=Response/Success  0x02=Failure
"""

import logging
import struct
from typing import Dict, Any, Optional

from .protocol_defs import F1AP_PROCS, F1AP_CAUSE_NAMES, DISC_F1AP

logger = logging.getLogger(__name__)

# Real F1AP procedure codes (TS 38.473 §9.2 Table 9.2.1-1)
REAL_F1AP_PROC_MAP: Dict[int, str] = {
    1:  "F1AP_F1Setup",
    2:  "F1AP_gNBDUConfigurationUpdate",
    3:  "F1AP_gNBCUConfigurationUpdate",
    4:  "F1AP_UEContextSetup",
    5:  "F1AP_UEContextRelease",
    6:  "F1AP_UEContextModification",
    7:  "F1AP_UEContextModificationRequired",
    8:  "F1AP_UEContextSuspend",
    9:  "F1AP_UEContextResume",
    10: "F1AP_DLRRCMessageTransfer",
    11: "F1AP_ULRRCMessageTransfer",
    12: "F1AP_InitialULRRCMessageTransfer",
    13: "F1AP_Paging",
    14: "F1AP_Notify",
    15: "F1AP_WriteReplaceWarning",
    16: "F1AP_PWSCancel",
    17: "F1AP_ErrorIndication",
    18: "F1AP_UEInactivityNotification",
    19: "F1AP_PrivateMessage",
    20: "F1AP_SystemInformationDeliveryCommand",
    21: "F1AP_Paging",
    22: "F1AP_gNBDUResourceCoordination",
    23: "F1AP_NetworkAccessRateReduction",
    24: "F1AP_AccessAndMobilityIndication",
    25: "F1AP_CellTrafficTrace",
    26: "F1AP_DeActivateTrace",
    27: "F1AP_TraceStart",
    28: "F1AP_DLRRCMessageTransfer",
    29: "F1AP_ULRRCMessageTransfer",
    30: "F1AP_BAPMappingConfiguration",
    31: "F1AP_GNBDUResourceCoordination",
    32: "F1AP_IABTNLAddressRequest",
    33: "F1AP_IABUPConfigurationUpdate",
    34: "F1AP_ResourceStatusRequest",
    35: "F1AP_ResourceStatusUpdate",
    36: "F1AP_ResourceStatusFailure",
    37: "F1AP_PWSFailureIndication",
    38: "F1AP_PWSRestartIndication",
    39: "F1AP_GNBCUConfigurationUpdate",
    40: "F1AP_UECapabilityInfoIndication",
}

REQUEST_CAT  = 0x00
RESPONSE_CAT = 0x01
FAILURE_CAT  = 0x02


def handle_f1ap_real(packet, record_request_fn, record_success_fn,
                     record_failure_fn, inc_events_fn,
                     extract_ies_fn) -> None:
    """Handle real F1AP packet via pyshark f1ap layer."""
    try:
        f1ap = packet.f1ap
        timestamp = float(packet.sniff_timestamp)

        proc_code = None
        for field in ['procedurecode', 'procedure_code', 'procedureCode']:
            raw = getattr(f1ap, field, None)
            if raw is not None:
                try:
                    proc_code = int(str(raw))
                    break
                except ValueError:
                    continue
        if proc_code is None:
            return

        proc_name = REAL_F1AP_PROC_MAP.get(proc_code, f"F1AP_Proc_{proc_code}")
        f1ap_str = str(f1ap).lower()

        # Node identifier — prefer gNB-DU-UE-F1AP-ID, fall back to gNB-DU-ID
        node_id = str(getattr(f1ap, 'gNB_DU_UE_F1AP_ID',
                     getattr(f1ap, 'gNB_DU_ID', 'unknown')))
        tx_key = f"f1ap_{proc_name}_{node_id}"

        is_response = 'successfuloutcome' in f1ap_str
        is_failure  = 'unsuccessfuloutcome' in f1ap_str

        ies = extract_ies_fn(packet)

        if not is_response and not is_failure:
            record_request_fn(proc_name, tx_key, timestamp, node_id, 'F1AP', ies)
        elif is_response:
            record_success_fn(proc_name, tx_key, 'F1AP', ies)
        else:
            cause = str(getattr(f1ap, 'cause', 'unknown'))
            record_failure_fn(proc_name, tx_key, cause, 'F1AP', ies)

        inc_events_fn()

    except Exception as e:
        logger.debug(f"F1AP real parse error: {e}")


def handle_f1ap_raw(raw_bytes: bytes, timestamp: float,
                    record_request_fn, record_success_fn,
                    record_failure_fn, inc_events_fn) -> None:
    """Handle synthetic F1AP payload. Format: [0x1a][proc][cat][ID:4][cause?]"""
    if len(raw_bytes) < 7:
        return
    proc_code  = raw_bytes[1]
    msg_cat    = raw_bytes[2]
    node_id    = str(struct.unpack('>I', raw_bytes[3:7])[0])
    cause_byte = raw_bytes[7] if len(raw_bytes) > 7 else None

    proc_name = F1AP_PROCS.get(proc_code, f"F1AP_Proc_{proc_code:02x}")
    tx_key    = f"f1ap_{proc_name}_{node_id}"

    if msg_cat == REQUEST_CAT:
        record_request_fn(proc_name, tx_key, timestamp, node_id, 'F1AP', {})
    elif msg_cat == RESPONSE_CAT:
        record_success_fn(proc_name, tx_key, 'F1AP', {})
    elif msg_cat == FAILURE_CAT:
        cause = F1AP_CAUSE_NAMES.get(cause_byte, f"unknown-0x{cause_byte:02x}") \
                if cause_byte else "unknown"
        record_failure_fn(proc_name, tx_key, cause, 'F1AP', {})

    inc_events_fn()
