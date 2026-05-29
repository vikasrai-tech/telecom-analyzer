"""
Synthetic PCAP Generator — Full 3GPP Stack
==========================================
Creates a test PCAP covering all three protocol layers:
  TS 24.501 — NAS  (Registration, Auth, SecurityMode, PDU Session)
  TS 38.413 — NGAP (InitialContextSetup, PDUSessionResourceSetup, UEContextRelease)
  TS 38.331 — RRC  (Setup, Reestablishment, Reconfiguration)

WHY SYNTHETIC DATA:
    Real 5G PCAPs are confidential. Synthetic data lets us:
    1. Control exactly which messages appear
    2. Know ground truth (exact counts) for automated verification
    3. Cover failure paths that are rare in production captures
    4. Reproduce tests exactly — no dependency on external files

PAYLOAD FORMATS (our simulation convention):
    NAS:  [0x7e][sec_hdr][msg_type][TMSI:4bytes][cause?]
    NGAP: [0x3a][proc_code][msg_cat][UE_ID:4bytes][cause?]
    RRC:  [0x2b][proc_code][msg_cat][UE_ID:4bytes][cause?]
    F1AP: [0x1a][proc_code][msg_cat][ID:4bytes][cause?]
    E1AP: [0x1b][proc_code][msg_cat][ID:4bytes][cause?]
    XnAP: [0x1c][proc_code][msg_cat][ID:4bytes][cause?]

    msg_cat: 0x00=Request/Initiating  0x01=Response/Success  0x02=Failure/Reject

GROUND TRUTH (parser must produce these exact numbers):
    NAS_Registration:            attempts=5, success=3, failure=2  (congestion×1, timeout×1)
    NAS_Authentication:          attempts=4, success=3, failure=1  (auth-failure×1)
    NAS_SecurityMode:            attempts=3, success=3, failure=0
    NAS_PDUSession_Establishment: attempts=3, success=2, failure=1 (semantically-incorrect-message×1)
    NGAP_InitialContextSetup:    attempts=4, success=3, failure=1  (user-inactivity×1)
    NGAP_PDUSessionResourceSetup: attempts=3, success=2, failure=1 (radio-connection-with-ue-lost×1)
    NGAP_UEContextRelease:      attempts=3,  success=3, failure=0
    RRC_Setup:                  attempts=5,  success=4, failure=1  (other-failure×1)
    RRC_Reestablishment:        attempts=2,  success=1, failure=1  (rlf-report-available×1)
    RRC_Reconfiguration:        attempts=4,  success=4, failure=0
"""

from scapy.all import Ether, IP, UDP, Raw, wrpcap, Packet
from pathlib import Path
import struct
import time

# ── New interface discriminators ──────────────────────────────────────
DISC_F1AP = 0x1a
DISC_E1AP = 0x1b
DISC_XNAP = 0x1c

# ── F1AP procedure codes (matches protocol_defs.py F1AP_PROCS) ───────
F1AP_F1SETUP       = 0x01
F1AP_UE_CTX_SETUP  = 0x02
F1AP_UE_CTX_REL    = 0x04
F1AP_DL_RRC        = 0x05
F1AP_UL_RRC        = 0x06
F1AP_INIT_UL_RRC   = 0x07

# ── E1AP procedure codes (matches protocol_defs.py E1AP_PROCS) ───────
E1AP_GNB_CU_UP_SETUP  = 0x01
E1AP_BEARER_CTX_SETUP = 0x02
E1AP_BEARER_CTX_REL   = 0x04

# ── XnAP procedure codes (matches protocol_defs.py XNAP_PROCS) ───────
XNAP_XN_SETUP    = 0x01
XNAP_HO_REQUEST  = 0x02
XNAP_UE_RELEASE  = 0x03
XNAP_SN_ADDITION = 0x05

# ── F1AP / E1AP / XnAP cause codes ───────────────────────────────────
F1AP_CAUSE_NORMAL_RELEASE     = 0x0b
F1AP_CAUSE_PROCEDURE_CANCELLED = 0x0a
E1AP_CAUSE_UE_CONTEXT_RELEASE  = 0x06
XNAP_CAUSE_USER_INACTIVITY     = 0x06
XNAP_CAUSE_RADIO_CONN_LOST     = 0x07

# Generic message categories
MSG_REQUEST  = 0x00
MSG_RESPONSE = 0x01
MSG_FAILURE  = 0x02

# ── Protocol discriminators ───────────────────────────────────────────
DISC_NAS  = 0x7e   # 5GMM extended protocol discriminator (TS 24.501 §9.2)
DISC_NGAP = 0x3a   # NGAP simulation marker
DISC_RRC  = 0x2b   # RRC simulation marker

# ── NAS 5GMM message types (TS 24.501 Table 9.7.1) ───────────────────
NAS_REG_REQUEST    = 0x41
NAS_REG_ACCEPT     = 0x42
NAS_REG_REJECT     = 0x44
NAS_AUTH_REQUEST   = 0x56
NAS_AUTH_RESPONSE  = 0x57
NAS_AUTH_FAILURE   = 0x59
NAS_SEC_COMMAND    = 0x5c
NAS_SEC_COMPLETE   = 0x5d
# NAS 5GSM message types (TS 24.501 Table 9.7.2)
NAS_PDU_EST_REQUEST = 0xc1
NAS_PDU_EST_ACCEPT  = 0xc2
NAS_PDU_EST_REJECT  = 0xc3

# ── NAS 5GMM Cause codes (TS 24.501 §9.11.3.2) ───────────────────────
CAUSE_AUTH_FAILURE  = 0x15
CAUSE_CONGESTION    = 0x16
CAUSE_SEMANTIC_ERR  = 0x1a   # semantically-incorrect-message

# ── NGAP procedure codes (our simulation, see pcap_parser_real.py) ────
NGAP_INITIAL_CTX   = 0x01
NGAP_PDU_SETUP     = 0x02
NGAP_UE_RELEASE    = 0x04
# NGAP message categories
NGAP_REQUEST  = 0x00
NGAP_RESPONSE = 0x01
NGAP_FAILURE  = 0x02
# NGAP Cause codes (TS 38.413 §9.3.1.2)
CAUSE_USER_INACTIVITY       = 0x09
CAUSE_RADIO_CONN_LOST       = 0x0a

# ── RRC procedure codes (our simulation, see pcap_parser_real.py) ─────
RRC_SETUP           = 0x01
RRC_REESTABLISHMENT = 0x02
RRC_RECONFIGURATION = 0x03
# RRC message categories
RRC_REQUEST  = 0x00
RRC_COMPLETE = 0x01
RRC_REJECT   = 0x02
# RRC Cause codes (TS 38.331)
CAUSE_OTHER_FAILURE    = 0x01
CAUSE_RLF_REPORT       = 0x04


# ── Packet factory functions ──────────────────────────────────────────

def _make_pkt(src_ip: str, dst_ip: str, payload: bytes, timestamp: float) -> Packet:
    """Wrap payload in Ether/IP/UDP frame on port 38412 (NGAP registered port)."""
    pkt = (
        Ether() /
        IP(src=src_ip, dst=dst_ip) /
        UDP(sport=38412, dport=38412) /
        Raw(load=payload)
    )
    pkt.time = timestamp
    return pkt


def make_nas_packet(src_ip: str, dst_ip: str, msg_type: int, tmsi: int,
                    cause: int = None, timestamp: float = 0.0) -> Packet:
    """NAS payload: [0x7e][0x00][msg_type][TMSI:4bytes][cause?]"""
    payload = bytes([DISC_NAS, 0x00, msg_type]) + struct.pack('>I', tmsi)
    if cause is not None:
        payload += bytes([cause])
    return _make_pkt(src_ip, dst_ip, payload, timestamp)


def make_ngap_packet(src_ip: str, dst_ip: str, proc_code: int, msg_cat: int,
                     ue_id: int, cause: int = None, timestamp: float = 0.0) -> Packet:
    """NGAP payload: [0x3a][proc_code][msg_cat][UE_ID:4bytes][cause?]"""
    payload = bytes([DISC_NGAP, proc_code, msg_cat]) + struct.pack('>I', ue_id)
    if cause is not None:
        payload += bytes([cause])
    return _make_pkt(src_ip, dst_ip, payload, timestamp)


def make_rrc_packet(src_ip: str, dst_ip: str, proc_code: int, msg_cat: int,
                    ue_id: int, cause: int = None, timestamp: float = 0.0) -> Packet:
    """RRC payload: [0x2b][proc_code][msg_cat][UE_ID:4bytes][cause?]"""
    payload = bytes([DISC_RRC, proc_code, msg_cat]) + struct.pack('>I', ue_id)
    if cause is not None:
        payload += bytes([cause])
    return _make_pkt(src_ip, dst_ip, payload, timestamp)


def make_f1ap_packet(src_ip: str, dst_ip: str, proc_code: int, msg_cat: int,
                     node_id: int, cause: int = None, timestamp: float = 0.0) -> Packet:
    """F1AP payload: [0x1a][proc_code][msg_cat][ID:4bytes][cause?]"""
    payload = bytes([DISC_F1AP, proc_code, msg_cat]) + struct.pack('>I', node_id)
    if cause is not None:
        payload += bytes([cause])
    return _make_pkt(src_ip, dst_ip, payload, timestamp)


def make_e1ap_packet(src_ip: str, dst_ip: str, proc_code: int, msg_cat: int,
                     ue_id: int, cause: int = None, timestamp: float = 0.0) -> Packet:
    """E1AP payload: [0x1b][proc_code][msg_cat][ID:4bytes][cause?]"""
    payload = bytes([DISC_E1AP, proc_code, msg_cat]) + struct.pack('>I', ue_id)
    if cause is not None:
        payload += bytes([cause])
    return _make_pkt(src_ip, dst_ip, payload, timestamp)


def make_xnap_packet(src_ip: str, dst_ip: str, proc_code: int, msg_cat: int,
                     node_id: int, cause: int = None, timestamp: float = 0.0) -> Packet:
    """XnAP payload: [0x1c][proc_code][msg_cat][ID:4bytes][cause?]"""
    payload = bytes([DISC_XNAP, proc_code, msg_cat]) + struct.pack('>I', node_id)
    if cause is not None:
        payload += bytes([cause])
    return _make_pkt(src_ip, dst_ip, payload, timestamp)


# ── Scenario generators ───────────────────────────────────────────────

def add_nas_registration(packets, base_time):
    """
    NAS Registration scenarios (TS 24.501 §8.2.6)
    Ground truth: attempts=5, success=3, failure=2 (congestion×1, timeout×1)
    """
    print("\n── NAS Registration (TS 24.501 §8.2.6) ──")
    amf = "10.0.0.1"
    t = base_time

    for tmsi, ue_ip, result, cause in [
        (1001, "10.0.1.1", "accept",  None),
        (1002, "10.0.1.2", "accept",  None),
        (1003, "10.0.1.3", "reject",  CAUSE_CONGESTION),
        (1004, "10.0.1.4", "accept",  None),
        (1005, "10.0.1.5", "timeout", None),
    ]:
        packets.append(make_nas_packet(ue_ip, amf, NAS_REG_REQUEST, tmsi, timestamp=t))
        print(f"  UE-{tmsi}: REG_REQUEST", end="")
        t += 0.1
        if result == "accept":
            packets.append(make_nas_packet(amf, ue_ip, NAS_REG_ACCEPT, tmsi, timestamp=t))
            print(" → ACCEPT ✓")
        elif result == "reject":
            packets.append(make_nas_packet(amf, ue_ip, NAS_REG_REJECT, tmsi, cause=cause, timestamp=t))
            print(f" → REJECT (congestion) ✗")
        else:
            print(" → (no response — timeout) ✗")
        t += 0.9


def add_nas_authentication(packets, base_time):
    """
    NAS Authentication scenarios (TS 24.501 §8.2.1)
    Ground truth: attempts=4, success=3, failure=1 (auth-failure×1)
    """
    print("\n── NAS Authentication (TS 24.501 §8.2.1) ──")
    amf = "10.0.0.1"
    t = base_time + 10.0

    for tmsi, ue_ip, result in [
        (1001, "10.0.1.1", "response"),
        (1002, "10.0.1.2", "response"),
        (1003, "10.0.1.3", "failure"),
        (1004, "10.0.1.4", "response"),
    ]:
        packets.append(make_nas_packet(amf, ue_ip, NAS_AUTH_REQUEST, tmsi, timestamp=t))
        print(f"  UE-{tmsi}: AUTH_REQUEST", end="")
        t += 0.1
        if result == "response":
            packets.append(make_nas_packet(ue_ip, amf, NAS_AUTH_RESPONSE, tmsi, timestamp=t))
            print(" → AUTH_RESPONSE ✓")
        else:
            packets.append(make_nas_packet(ue_ip, amf, NAS_AUTH_FAILURE, tmsi,
                                           cause=CAUSE_AUTH_FAILURE, timestamp=t))
            print(" → AUTH_FAILURE ✗")
        t += 0.4


def add_nas_security_mode(packets, base_time):
    """
    NAS Security Mode scenarios (TS 24.501 §8.2.25)
    Ground truth: attempts=3, success=3, failure=0
    """
    print("\n── NAS Security Mode (TS 24.501 §8.2.25) ──")
    amf = "10.0.0.1"
    t = base_time + 20.0

    for tmsi, ue_ip in [(1001, "10.0.1.1"), (1002, "10.0.1.2"), (1004, "10.0.1.4")]:
        packets.append(make_nas_packet(amf, ue_ip, NAS_SEC_COMMAND, tmsi, timestamp=t))
        t += 0.1
        packets.append(make_nas_packet(ue_ip, amf, NAS_SEC_COMPLETE, tmsi, timestamp=t))
        print(f"  UE-{tmsi}: SEC_MODE_COMMAND → SEC_MODE_COMPLETE ✓")
        t += 0.4


def add_nas_pdu_session(packets, base_time):
    """
    NAS PDU Session Establishment (TS 24.501 §8.3.1)
    Ground truth: attempts=3, success=2, failure=1 (semantically-incorrect-message×1)
    """
    print("\n── NAS PDU Session Establishment (TS 24.501 §8.3.1) ──")
    amf = "10.0.0.1"
    t = base_time + 30.0

    for tmsi, ue_ip, result in [
        (1001, "10.0.1.1", "accept"),
        (1002, "10.0.1.2", "reject"),
        (1004, "10.0.1.4", "accept"),
    ]:
        packets.append(make_nas_packet(ue_ip, amf, NAS_PDU_EST_REQUEST, tmsi, timestamp=t))
        print(f"  UE-{tmsi}: PDU_EST_REQUEST", end="")
        t += 0.1
        if result == "accept":
            packets.append(make_nas_packet(amf, ue_ip, NAS_PDU_EST_ACCEPT, tmsi, timestamp=t))
            print(" → PDU_EST_ACCEPT ✓")
        else:
            packets.append(make_nas_packet(amf, ue_ip, NAS_PDU_EST_REJECT, tmsi,
                                           cause=CAUSE_SEMANTIC_ERR, timestamp=t))
            print(" → PDU_EST_REJECT (semantically-incorrect-message) ✗")
        t += 0.4


def add_ngap_initial_context(packets, base_time):
    """
    NGAP InitialContextSetup (TS 38.413 §8.3.1)
    Ground truth: attempts=4, success=3, failure=1 (user-inactivity×1)
    """
    print("\n── NGAP InitialContextSetup (TS 38.413 §8.3.1) ──")
    amf = "10.0.0.1"
    gnb = "10.0.0.2"
    t = base_time + 40.0

    for ue_id, result in [(1, "response"), (2, "response"), (3, "failure"), (4, "response")]:
        packets.append(make_ngap_packet(amf, gnb, NGAP_INITIAL_CTX, NGAP_REQUEST, ue_id, timestamp=t))
        print(f"  UE-{ue_id}: NGAP_InitCtxSetup_REQUEST", end="")
        t += 0.1
        if result == "response":
            packets.append(make_ngap_packet(gnb, amf, NGAP_INITIAL_CTX, NGAP_RESPONSE, ue_id, timestamp=t))
            print(" → RESPONSE ✓")
        else:
            packets.append(make_ngap_packet(gnb, amf, NGAP_INITIAL_CTX, NGAP_FAILURE, ue_id,
                                            cause=CAUSE_USER_INACTIVITY, timestamp=t))
            print(" → FAILURE (user-inactivity) ✗")
        t += 0.4


def add_ngap_pdu_session_setup(packets, base_time):
    """
    NGAP PDUSessionResourceSetup (TS 38.413 §8.4.1)
    Ground truth: attempts=3, success=2, failure=1 (radio-connection-with-ue-lost×1)
    """
    print("\n── NGAP PDUSessionResourceSetup (TS 38.413 §8.4.1) ──")
    amf = "10.0.0.1"
    gnb = "10.0.0.2"
    t = base_time + 50.0

    for ue_id, result in [(1, "response"), (2, "failure"), (4, "response")]:
        packets.append(make_ngap_packet(amf, gnb, NGAP_PDU_SETUP, NGAP_REQUEST, ue_id, timestamp=t))
        print(f"  UE-{ue_id}: NGAP_PDUSessionSetup_REQUEST", end="")
        t += 0.1
        if result == "response":
            packets.append(make_ngap_packet(gnb, amf, NGAP_PDU_SETUP, NGAP_RESPONSE, ue_id, timestamp=t))
            print(" → RESPONSE ✓")
        else:
            packets.append(make_ngap_packet(gnb, amf, NGAP_PDU_SETUP, NGAP_FAILURE, ue_id,
                                            cause=CAUSE_RADIO_CONN_LOST, timestamp=t))
            print(" → FAILURE (radio-connection-with-ue-lost) ✗")
        t += 0.4


def add_ngap_ue_context_release(packets, base_time):
    """
    NGAP UEContextRelease (TS 38.413 §8.3.3)
    Ground truth: attempts=3, success=3, failure=0
    """
    print("\n── NGAP UEContextRelease (TS 38.413 §8.3.3) ──")
    amf = "10.0.0.1"
    gnb = "10.0.0.2"
    t = base_time + 60.0

    for ue_id in [1, 2, 4]:
        packets.append(make_ngap_packet(amf, gnb, NGAP_UE_RELEASE, NGAP_REQUEST, ue_id, timestamp=t))
        t += 0.1
        packets.append(make_ngap_packet(gnb, amf, NGAP_UE_RELEASE, NGAP_RESPONSE, ue_id, timestamp=t))
        print(f"  UE-{ue_id}: UEContextRelease REQUEST → RESPONSE ✓")
        t += 0.4


def add_rrc_setup(packets, base_time):
    """
    RRC Setup (TS 38.331 §5.3.3)
    Ground truth: attempts=5, success=4, failure=1 (other-failure×1)
    """
    print("\n── RRC Setup (TS 38.331 §5.3.3) ──")
    gnb = "10.0.0.2"
    t = base_time + 70.0

    for ue_id, ue_ip, result in [
        (101, "10.0.1.1", "complete"),
        (102, "10.0.1.2", "complete"),
        (103, "10.0.1.3", "reject"),
        (104, "10.0.1.4", "complete"),
        (105, "10.0.1.5", "complete"),
    ]:
        packets.append(make_rrc_packet(ue_ip, gnb, RRC_SETUP, RRC_REQUEST, ue_id, timestamp=t))
        print(f"  UE-{ue_id}: RRC_Setup_REQUEST", end="")
        t += 0.05
        if result == "complete":
            packets.append(make_rrc_packet(gnb, ue_ip, RRC_SETUP, RRC_COMPLETE, ue_id, timestamp=t))
            print(" → COMPLETE ✓")
        else:
            packets.append(make_rrc_packet(gnb, ue_ip, RRC_SETUP, RRC_REJECT, ue_id,
                                           cause=CAUSE_OTHER_FAILURE, timestamp=t))
            print(" → REJECT (other-failure) ✗")
        t += 0.2


def add_rrc_reestablishment(packets, base_time):
    """
    RRC Reestablishment (TS 38.331 §5.3.7)
    Ground truth: attempts=2, success=1, failure=1 (rlf-report-available×1)
    """
    print("\n── RRC Reestablishment (TS 38.331 §5.3.7) ──")
    gnb = "10.0.0.2"
    t = base_time + 80.0

    for ue_id, ue_ip, result in [
        (101, "10.0.1.1", "complete"),
        (103, "10.0.1.3", "reject"),
    ]:
        packets.append(make_rrc_packet(ue_ip, gnb, RRC_REESTABLISHMENT, RRC_REQUEST, ue_id, timestamp=t))
        print(f"  UE-{ue_id}: RRC_Reestablishment_REQUEST", end="")
        t += 0.05
        if result == "complete":
            packets.append(make_rrc_packet(gnb, ue_ip, RRC_REESTABLISHMENT, RRC_COMPLETE, ue_id, timestamp=t))
            print(" → COMPLETE ✓")
        else:
            packets.append(make_rrc_packet(gnb, ue_ip, RRC_REESTABLISHMENT, RRC_REJECT, ue_id,
                                           cause=CAUSE_RLF_REPORT, timestamp=t))
            print(" → REJECT (rlf-report-available) ✗")
        t += 0.2


def add_rrc_reconfiguration(packets, base_time):
    """
    RRC Reconfiguration (TS 38.331 §5.3.5)
    Ground truth: attempts=4, success=4, failure=0
    """
    print("\n── RRC Reconfiguration (TS 38.331 §5.3.5) ──")
    gnb = "10.0.0.2"
    t = base_time + 90.0

    for ue_id, ue_ip in [(101, "10.0.1.1"), (102, "10.0.1.2"),
                          (104, "10.0.1.4"), (105, "10.0.1.5")]:
        packets.append(make_rrc_packet(gnb, ue_ip, RRC_RECONFIGURATION, RRC_REQUEST, ue_id, timestamp=t))
        t += 0.05
        packets.append(make_rrc_packet(ue_ip, gnb, RRC_RECONFIGURATION, RRC_COMPLETE, ue_id, timestamp=t))
        print(f"  UE-{ue_id}: RRC_Reconfiguration REQUEST → COMPLETE ✓")
        t += 0.2


# ── Main generator ────────────────────────────────────────────────────

def generate_test_pcap(output_path: str) -> None:
    """
    Generate a comprehensive 5G test PCAP covering all three 3GPP layers.
    See module docstring for complete ground truth.
    """
    packets = []
    base_time = time.time()

    print("=" * 60)
    print("Generating synthetic 5G full-stack test PCAP")
    print("=" * 60)

    # NAS layer (TS 24.501)
    add_nas_registration(packets, base_time)
    add_nas_authentication(packets, base_time)
    add_nas_security_mode(packets, base_time)
    add_nas_pdu_session(packets, base_time)

    # NGAP layer (TS 38.413)
    add_ngap_initial_context(packets, base_time)
    add_ngap_pdu_session_setup(packets, base_time)
    add_ngap_ue_context_release(packets, base_time)

    # RRC layer (TS 38.331)
    add_rrc_setup(packets, base_time)
    add_rrc_reestablishment(packets, base_time)
    add_rrc_reconfiguration(packets, base_time)

    # F1AP layer (TS 38.473)
    add_f1ap_f1setup(packets, base_time)
    add_f1ap_ue_context(packets, base_time)
    add_f1ap_rrc_transfer(packets, base_time)

    # E1AP layer (TS 38.463)
    add_e1ap_gnbcuup_setup(packets, base_time)
    add_e1ap_bearer_context(packets, base_time)

    # XnAP layer (TS 38.423)
    add_xnap_setup(packets, base_time)
    add_xnap_handover(packets, base_time)
    add_xnap_sn_addition(packets, base_time)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    wrpcap(str(output), packets)

    print("\n" + "=" * 60)
    print(f"✓ PCAP written: {output}  ({len(packets)} packets)")
    print("=" * 60)
    print("\nExpected ground truth:")
    print("  Layer  Procedure                      Attempts  Success  Failure")
    print("  -----  ─────────────────────────────  ────────  ───────  ───────")
    ground_truth = [
        ("NAS",  "NAS_Registration",              5, 3, 2),
        ("NAS",  "NAS_Authentication",            4, 3, 1),
        ("NAS",  "NAS_SecurityMode",              3, 3, 0),
        ("NAS",  "NAS_PDUSession_Establishment",  3, 2, 1),
        ("NGAP", "NGAP_InitialContextSetup",      4, 3, 1),
        ("NGAP", "NGAP_PDUSessionResourceSetup",  3, 2, 1),
        ("NGAP", "NGAP_UEContextRelease",         3, 3, 0),
        ("RRC",  "RRC_Setup",                     5, 4, 1),
        ("RRC",  "RRC_Reestablishment",           2, 1, 1),
        ("RRC",  "RRC_Reconfiguration",           4, 4, 0),
        ("F1AP", "F1AP_F1Setup",                  1, 1, 0),
        ("F1AP", "F1AP_UEContextSetup",           3, 2, 1),
        ("F1AP", "F1AP_UEContextRelease",         3, 3, 0),
        ("F1AP", "F1AP_DLRRCMessageTransfer",     3, 3, 0),
        ("F1AP", "F1AP_ULRRCMessageTransfer",     3, 3, 0),
        ("E1AP", "E1AP_GNBCUUPSetup",            1, 1, 0),
        ("E1AP", "E1AP_BearerContextSetup",       3, 2, 1),
        ("E1AP", "E1AP_BearerContextRelease",     3, 3, 0),
        ("XnAP", "XnAP_XnSetup",                 1, 1, 0),
        ("XnAP", "XnAP_HandoverRequest",          3, 2, 1),
        ("XnAP", "XnAP_SecondaryNodeAddition",    2, 2, 0),
    ]
    for layer, proc, att, suc, fail in ground_truth:
        print(f"  {layer:<5}  {proc:<30}  {att:^8}  {suc:^7}  {fail:^7}")


def add_f1ap_f1setup(packets, base_time):
    """F1AP F1Setup (TS 38.473 §8.2.3). Ground truth: attempts=1, success=1, failure=0"""
    print("\n── F1AP F1Setup (TS 38.473 §8.2.3) ──")
    cu = "10.0.0.10"
    du = "10.0.0.11"
    t = base_time + 100.0
    packets.append(make_f1ap_packet(du, cu, F1AP_F1SETUP, MSG_REQUEST,  1001, timestamp=t))
    t += 0.05
    packets.append(make_f1ap_packet(cu, du, F1AP_F1SETUP, MSG_RESPONSE, 1001, timestamp=t))
    print("  gNB-DU-1001: F1Setup_REQUEST → RESPONSE ✓")


def add_f1ap_ue_context(packets, base_time):
    """
    F1AP UEContextSetup + UEContextRelease (TS 38.473 §8.3.1/§8.3.2)
    Ground truth:
      F1AP_UEContextSetup:   attempts=3, success=2, failure=1
      F1AP_UEContextRelease: attempts=3, success=3, failure=0
    """
    print("\n── F1AP UEContextSetup (TS 38.473 §8.3.1) ──")
    cu = "10.0.0.10"
    du = "10.0.0.11"
    t = base_time + 110.0

    for ue_id, result in [(201, "response"), (202, "failure"), (204, "response")]:
        packets.append(make_f1ap_packet(cu, du, F1AP_UE_CTX_SETUP, MSG_REQUEST, ue_id, timestamp=t))
        print(f"  UE-{ue_id}: UEContextSetup_REQUEST", end="")
        t += 0.05
        if result == "response":
            packets.append(make_f1ap_packet(du, cu, F1AP_UE_CTX_SETUP, MSG_RESPONSE, ue_id, timestamp=t))
            print(" → RESPONSE ✓")
        else:
            packets.append(make_f1ap_packet(du, cu, F1AP_UE_CTX_SETUP, MSG_FAILURE, ue_id,
                                            cause=F1AP_CAUSE_PROCEDURE_CANCELLED, timestamp=t))
            print(" → FAILURE (procedure-cancelled) ✗")
        t += 0.3

    print("\n── F1AP UEContextRelease (TS 38.473 §8.3.2) ──")
    t = base_time + 120.0
    for ue_id in [201, 202, 204]:
        packets.append(make_f1ap_packet(cu, du, F1AP_UE_CTX_REL, MSG_REQUEST,  ue_id, timestamp=t))
        t += 0.05
        packets.append(make_f1ap_packet(du, cu, F1AP_UE_CTX_REL, MSG_RESPONSE, ue_id, timestamp=t))
        print(f"  UE-{ue_id}: UEContextRelease REQUEST → RESPONSE ✓")
        t += 0.3


def add_f1ap_rrc_transfer(packets, base_time):
    """
    F1AP DL/UL RRC Message Transfer (TS 38.473 §8.4)
    Ground truth:
      F1AP_DLRRCMessageTransfer: attempts=3, success=3, failure=0 (one-way, tracked as attempts only)
      F1AP_ULRRCMessageTransfer: attempts=3, success=3, failure=0
    Note: RRC transfers are point-to-point, no ack — counted as attempts=success
    """
    print("\n── F1AP DL/UL RRC Message Transfer (TS 38.473 §8.4) ──")
    cu = "10.0.0.10"
    du = "10.0.0.11"
    t = base_time + 130.0
    for ue_id in [201, 202, 204]:
        packets.append(make_f1ap_packet(cu, du, F1AP_DL_RRC, MSG_REQUEST,  ue_id, timestamp=t))
        t += 0.02
        packets.append(make_f1ap_packet(du, cu, F1AP_UL_RRC, MSG_REQUEST,  ue_id, timestamp=t))
        # UL RRC from UE is a new "initiating" event, mark it as response so it pairs with DL
        packets.append(make_f1ap_packet(du, cu, F1AP_DL_RRC, MSG_RESPONSE, ue_id, timestamp=t + 0.01))
        packets.append(make_f1ap_packet(cu, du, F1AP_UL_RRC, MSG_RESPONSE, ue_id, timestamp=t + 0.02))
        print(f"  UE-{ue_id}: DL_RRC_Transfer ↔ UL_RRC_Transfer ✓")
        t += 0.3


def add_e1ap_gnbcuup_setup(packets, base_time):
    """E1AP GNBCUUPSetup (TS 38.463 §8.2.3). Ground truth: attempts=1, success=1, failure=0"""
    print("\n── E1AP GNBCUUPSetup (TS 38.463 §8.2.3) ──")
    cu_cp = "10.0.0.10"
    cu_up = "10.0.0.12"
    t = base_time + 140.0
    packets.append(make_e1ap_packet(cu_up, cu_cp, E1AP_GNB_CU_UP_SETUP, MSG_REQUEST,  5001, timestamp=t))
    t += 0.05
    packets.append(make_e1ap_packet(cu_cp, cu_up, E1AP_GNB_CU_UP_SETUP, MSG_RESPONSE, 5001, timestamp=t))
    print("  gNB-CU-UP-5001: GNBCUUPSetup_REQUEST → RESPONSE ✓")


def add_e1ap_bearer_context(packets, base_time):
    """
    E1AP BearerContextSetup + BearerContextRelease (TS 38.463 §8.3)
    Ground truth:
      E1AP_BearerContextSetup:   attempts=3, success=2, failure=1 (ue-context-release×1)
      E1AP_BearerContextRelease: attempts=3, success=3, failure=0
    """
    print("\n── E1AP BearerContextSetup (TS 38.463 §8.3.1) ──")
    cu_cp = "10.0.0.10"
    cu_up = "10.0.0.12"
    t = base_time + 150.0

    for ue_id, result in [(301, "response"), (302, "failure"), (304, "response")]:
        packets.append(make_e1ap_packet(cu_cp, cu_up, E1AP_BEARER_CTX_SETUP, MSG_REQUEST,  ue_id, timestamp=t))
        print(f"  UE-{ue_id}: BearerContextSetup_REQUEST", end="")
        t += 0.05
        if result == "response":
            packets.append(make_e1ap_packet(cu_up, cu_cp, E1AP_BEARER_CTX_SETUP, MSG_RESPONSE, ue_id, timestamp=t))
            print(" → RESPONSE ✓")
        else:
            packets.append(make_e1ap_packet(cu_up, cu_cp, E1AP_BEARER_CTX_SETUP, MSG_FAILURE, ue_id,
                                            cause=E1AP_CAUSE_UE_CONTEXT_RELEASE, timestamp=t))
            print(" → FAILURE (ue-context-release) ✗")
        t += 0.3

    print("\n── E1AP BearerContextRelease (TS 38.463 §8.3.2) ──")
    t = base_time + 160.0
    for ue_id in [301, 302, 304]:
        packets.append(make_e1ap_packet(cu_cp, cu_up, E1AP_BEARER_CTX_REL, MSG_REQUEST,  ue_id, timestamp=t))
        t += 0.05
        packets.append(make_e1ap_packet(cu_up, cu_cp, E1AP_BEARER_CTX_REL, MSG_RESPONSE, ue_id, timestamp=t))
        print(f"  UE-{ue_id}: BearerContextRelease REQUEST → RESPONSE ✓")
        t += 0.3


def add_xnap_setup(packets, base_time):
    """XnAP XnSetup (TS 38.423 §8.3.5). Ground truth: attempts=1, success=1, failure=0"""
    print("\n── XnAP XnSetup (TS 38.423 §8.3.5) ──")
    gnb1 = "10.0.0.2"
    gnb2 = "10.0.0.3"
    t = base_time + 170.0
    packets.append(make_xnap_packet(gnb1, gnb2, XNAP_XN_SETUP, MSG_REQUEST,  9001, timestamp=t))
    t += 0.05
    packets.append(make_xnap_packet(gnb2, gnb1, XNAP_XN_SETUP, MSG_RESPONSE, 9001, timestamp=t))
    print("  gNB-9001: XnSetup_REQUEST → RESPONSE ✓")


def add_xnap_handover(packets, base_time):
    """
    XnAP HandoverRequest (TS 38.423 §8.3.1)
    Ground truth: attempts=3, success=2, failure=1 (radio-connection-with-UE-lost×1)
    """
    print("\n── XnAP HandoverRequest (TS 38.423 §8.3.1) ──")
    gnb1 = "10.0.0.2"
    gnb2 = "10.0.0.3"
    t = base_time + 180.0

    for ue_id, result in [(401, "response"), (402, "failure"), (404, "response")]:
        packets.append(make_xnap_packet(gnb1, gnb2, XNAP_HO_REQUEST, MSG_REQUEST,  ue_id, timestamp=t))
        print(f"  UE-{ue_id}: XnAP_HO_REQUEST", end="")
        t += 0.1
        if result == "response":
            packets.append(make_xnap_packet(gnb2, gnb1, XNAP_HO_REQUEST, MSG_RESPONSE, ue_id, timestamp=t))
            print(" → RESPONSE ✓")
        else:
            packets.append(make_xnap_packet(gnb2, gnb1, XNAP_HO_REQUEST, MSG_FAILURE, ue_id,
                                            cause=XNAP_CAUSE_RADIO_CONN_LOST, timestamp=t))
            print(" → FAILURE (radio-connection-with-UE-lost) ✗")
        t += 0.4


def add_xnap_sn_addition(packets, base_time):
    """
    XnAP SecondaryNodeAddition — MR-DC (TS 38.423 §8.4.1)
    Ground truth: attempts=2, success=2, failure=0
    """
    print("\n── XnAP SecondaryNodeAddition — MR-DC (TS 38.423 §8.4.1) ──")
    mnb = "10.0.0.2"   # MN (Master Node)
    snb = "10.0.0.4"   # SN (Secondary Node)
    t = base_time + 190.0

    for ue_id in [501, 502]:
        packets.append(make_xnap_packet(mnb, snb, XNAP_SN_ADDITION, MSG_REQUEST,  ue_id, timestamp=t))
        t += 0.1
        packets.append(make_xnap_packet(snb, mnb, XNAP_SN_ADDITION, MSG_RESPONSE, ue_id, timestamp=t))
        print(f"  UE-{ue_id}: SN_Addition_REQUEST → RESPONSE ✓")
        t += 0.4


if __name__ == "__main__":
    generate_test_pcap("data/raw/test_5g_full.pcap")
    print("\nRun the parser to verify:")
    print("  python -c \"from src.parsers.pcap_parser_real import parse_pcap; "
          "import json; print(json.dumps(parse_pcap('data/raw/test_5g_full.pcap'), indent=2))\"")
