"""
XnAP Parser — TS 38.423
========================
Xn interface: gNB ↔ gNB  (inter-node for handover, MR-DC, SON)

Handles both:
  • Real captures  — pyshark xnap layer (SCTP port 38422)
  • Synthetic PCAP — raw UDP payload with discriminator 0x1c

Synthetic payload format:
  [0x1c][proc_code:1][msg_cat:1][node_id:4][cause:1 optional]
  msg_cat: 0x00=Request  0x01=Response  0x02=Failure/Reject
"""

import logging
import struct
from typing import Dict

from .protocol_defs import XNAP_PROCS, XNAP_CAUSE_NAMES

logger = logging.getLogger(__name__)

# Real XnAP procedure codes (TS 38.423 §9.2 Table 9.2.1-1)
REAL_XNAP_PROC_MAP: Dict[int, str] = {
    1: "XnAP_HandoverPreparation",
    2: "XnAP_HandoverCancel",
    3: "XnAP_RetrieveUEContext",
    4: "XnAP_SNStatusTransfer",
    5: "XnAP_UEContextRelease",
    6: "XnAP_HandoverSuccess",
    7: "XnAP_ConditionalHandoverCancel",
    8: "XnAP_RANPaging",
    9: "XnAP_XnSetup",
    10: "XnAP_gNBXnConfigurationUpdate",
    11: "XnAP_CellActivation",
    12: "XnAP_DataForwardingAddressIndication",
    13: "XnAP_RANECGIReportRequest",
    14: "XnAP_RANECGIReportResponse",
    15: "XnAP_RANECGIReportFailure",
    16: "XnAP_RANPaging",
    17: "XnAP_SONConfigurationTransfer",
    18: "XnAP_RNLInformationTransfer",
    19: "XnAP_SecondaryRATDataUsageReport",
    20: "XnAP_SNodeAdditionRequest",
    21: "XnAP_SNodeAdditionRequestAcknowledge",
    22: "XnAP_SNodeAdditionRequestReject",
    23: "XnAP_SNodeReconfigurationComplete",
    24: "XnAP_SNodeModificationRequest",
    25: "XnAP_SNodeModificationRequestAcknowledge",
    26: "XnAP_SNodeModificationRequestReject",
    27: "XnAP_SNodeModificationRequired",
    28: "XnAP_SNodeModificationConfirm",
    29: "XnAP_SNodeModificationRefuse",
    30: "XnAP_SNodeReleaseRequest",
    31: "XnAP_SNodeReleaseRequestAcknowledge",
    32: "XnAP_SNodeReleaseRequestReject",
    33: "XnAP_SNodeReleaseRequired",
    34: "XnAP_SNodeReleaseConfirm",
    35: "XnAP_SNodeCounterCheck",
    36: "XnAP_SNodeStatusTransfer",
    37: "XnAP_RRCTransfer",
    38: "XnAP_SecondaryULHandover",
    39: "XnAP_ActivityNotification",
    40: "XnAP_ErrorIndication",
    41: "XnAP_PrivateMessage",
    42: "XnAP_F1CTransparentInformation",
    43: "XnAP_PDCPChangeIndication",
    44: "XnAP_DeactivateTrace",
    45: "XnAP_TraceStart",
    46: "XnAP_HandoverPreparation",
    47: "XnAP_AMFConfigurationUpdate",
    48: "XnAP_MobilitySettingsChange",
    49: "XnAP_FailureModeIndication",
    50: "XnAP_EarlyStatusTransfer",
    51: "XnAP_PDCP_Measurement_Result",
    52: "XnAP_IntersystemSONTransfer",
    53: "XnAP_IntersystemResourceStatusRequest",
    54: "XnAP_IntersystemResourceStatusUpdate",
    55: "XnAP_IntersystemResourceStatusFailure",
    56: "XnAP_IntersystemCellActivation",
    57: "XnAP_IntersystemUEHistory",
    58: "XnAP_MCGInformationTransfer",
    59: "XnAP_HandoverSuccess",
    60: "XnAP_ConditionalHandoverCancel",
    61: "XnAP_SuccessfulHandoverReport",
    62: "XnAP_DUtoRSMAP_Configuration",
    63: "XnAP_PrecedingMessageTransfer",
    64: "XnAP_MCPaging",
    65: "XnAP_BCInfoTransfer",
}

REQUEST_CAT = 0x00
RESPONSE_CAT = 0x01
FAILURE_CAT = 0x02


def handle_xnap_real(packet, record_request_fn, record_success_fn,
                     record_failure_fn, inc_events_fn,
                     extract_ies_fn) -> None:
    """Handle real XnAP packet via pyshark xnap layer."""
    try:
        xnap = packet.xnap
        timestamp = float(packet.sniff_timestamp)

        proc_code = None
        for field in ['procedurecode', 'procedure_code', 'procedureCode']:
            raw = getattr(xnap, field, None)
            if raw is not None:
                try:
                    proc_code = int(str(raw))
                    break
                except ValueError:
                    continue
        if proc_code is None:
            return

        proc_name = REAL_XNAP_PROC_MAP.get(proc_code, f"XnAP_Proc_{proc_code}")
        xnap_str = str(xnap).lower()

        node_id = str(getattr(xnap, 'oldNG_RAN_node_UE_XnAP_ID',
                              getattr(xnap, 'newNG_RAN_node_UE_XnAP_ID', 'unknown')))
        tx_key = f"xnap_{proc_name}_{node_id}"

        is_response = 'successfuloutcome' in xnap_str or 'acknowledge' in xnap_str
        is_failure = 'unsuccessfuloutcome' in xnap_str or 'reject' in xnap_str

        ies = extract_ies_fn(packet)

        if not is_response and not is_failure:
            record_request_fn(proc_name, tx_key, timestamp, node_id, 'XnAP', ies)
        elif is_response:
            record_success_fn(proc_name, tx_key, 'XnAP', ies)
        else:
            cause = str(getattr(xnap, 'cause', 'unknown'))
            record_failure_fn(proc_name, tx_key, cause, 'XnAP', ies)

        inc_events_fn()

    except Exception as e:
        logger.debug(f"XnAP real parse error: {e}")


def handle_xnap_raw(raw_bytes: bytes, timestamp: float,
                    record_request_fn, record_success_fn,
                    record_failure_fn, inc_events_fn) -> None:
    """Handle synthetic XnAP payload. Format: [0x1c][proc][cat][ID:4][cause?]"""
    if len(raw_bytes) < 7:
        return
    proc_code = raw_bytes[1]
    msg_cat = raw_bytes[2]
    node_id = str(struct.unpack('>I', raw_bytes[3:7])[0])
    cause_byte = raw_bytes[7] if len(raw_bytes) > 7 else None

    proc_name = XNAP_PROCS.get(proc_code, f"XnAP_Proc_{proc_code:02x}")
    tx_key = f"xnap_{proc_name}_{node_id}"

    if msg_cat == REQUEST_CAT:
        record_request_fn(proc_name, tx_key, timestamp, node_id, 'XnAP', {})
    elif msg_cat == RESPONSE_CAT:
        record_success_fn(proc_name, tx_key, 'XnAP', {})
    elif msg_cat == FAILURE_CAT:
        cause = XNAP_CAUSE_NAMES.get(cause_byte, f"unknown-0x{cause_byte:02x}") \
            if cause_byte else "unknown"
        record_failure_fn(proc_name, tx_key, cause, 'XnAP', {})

    inc_events_fn()
