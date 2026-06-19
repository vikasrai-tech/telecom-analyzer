"""
64 UE / 6-Hour PCAP Generator — Attach + XnAP/NGAP Handover
============================================================
Generates a 5G-NR trace for 64 UEs spread evenly across a 6-hour window
(matching the duration of generate_64ue_kpi.py / generate_64ue_stats.py):

  UE 1-32   : Full attach flow (RRC -> F1AP -> NAS -> NGAP -> RRC Reconfig),
              4 injected failures (~12.5%), mirrors generate_ue_attach_pcap.py
  UE 33-48  : Xn-based handover (gNB1 -> gNB2, intra-AMF, XnAP),
              2 injected failures (~12.5%), mirrors generate_handover_pcap.py
  UE 49-64  : N2-based handover (gNB1 -> gNB3, via AMF, NGAP),
              2 injected failures (~12.5%)

Ground Truth:
  Procedure                          Attempts  Success  Failure  Failure Cause
  ──────────────────────────────────  ────────  ───────  ───────  ─────────────
  RRC_Setup                              32        31        1     other-failure
  F1AP_InitialULRRCMessageTransfer       31        31        0     —
  NAS_Registration                       32        31        1     congestion (auth retry)
  NGAP_InitialUEMessage                  31        31        0     —
  NAS_Authentication                     32        31        1     auth-failure
  NAS_SecurityMode                       31        31        0     —
  NGAP_InitialContextSetup               31        30        1     radio-conn-lost
  F1AP_UEContextSetup                    30        29        1     procedure-cancelled
  E1AP_BearerContextSetup                29        28        1     ue-context-release
  NAS_Registration_Accept                28        28        0     —
  NAS_PDUSession_Establishment           28        27        1     semantically-incorrect
  NGAP_PDUSessionResourceSetup           27        27        0     —
  RRC_Reconfiguration (attach)           27 + 16   43        0     —  (attach + Xn HO command)
  XnAP_HandoverRequest                   16        14        2     no-suitable-cells / radio-conn-lost
  XnAP_XnUEContextRelease                14        14        0     —
  NGAP_HandoverPreparation               16        14        2     radio-resources-not-available
  NGAP_UEContextRelease                  14        14        0     —
  RRC_Reestablishment                     2         2        0     —  (fallback after HO failure)
"""

import struct
import time
from pathlib import Path

from scapy.all import Ether, IP, Raw, UDP, Packet, wrpcap

# ── Network topology ──────────────────────────────────────────────────
AMF    = "10.0.0.1"     # AMF (Core)
GNB    = "10.0.0.2"     # Source gNB (attach + handover source)
GNB2   = "10.0.0.3"     # Target gNB for Xn-based handover
GNB3   = "10.0.0.4"     # Target gNB for N2-based handover
GNB_DU = "10.0.0.11"    # gNB-DU
GNB_CU = "10.0.0.10"    # gNB-CU-CP
GNB_UP = "10.0.0.12"    # gNB-CU-UP

DURATION_S = 6 * 3600           # 6 hours
N_UE       = 64
STEP_S     = DURATION_S / N_UE  # ~337.5s between UE events

def ue_ip(ue_id: int) -> str:
    return f"10.1.0.{ue_id % 256}"

# ── Protocol discriminators ───────────────────────────────────────────
DISC_NAS  = 0x7e
DISC_NGAP = 0x3a
DISC_RRC  = 0x2b
DISC_F1AP = 0x1a
DISC_E1AP = 0x1b
DISC_XNAP = 0x1c

# ── Message categories ────────────────────────────────────────────────
REQ = 0x00
RSP = 0x01
REJ = 0x02

# ── NAS message types (TS 24.501) ────────────────────────────────────
NAS_REG_REQ     = 0x41
NAS_REG_ACCEPT  = 0x42
NAS_REG_REJECT  = 0x44
NAS_AUTH_REQ    = 0x56
NAS_AUTH_RSP    = 0x57
NAS_AUTH_FAIL   = 0x59
NAS_SEC_CMD     = 0x5c
NAS_SEC_COMP    = 0x5d
NAS_PDU_REQ     = 0xc1
NAS_PDU_ACCEPT  = 0xc2
NAS_PDU_REJECT  = 0xc3

# ── NGAP procedure codes ──────────────────────────────────────────────
NGAP_INIT_CTX  = 0x01
NGAP_PDU_SETUP = 0x02
NGAP_UE_REL    = 0x04
NGAP_HO_PREP   = 0x05
NGAP_INIT_UE   = 0x08

# ── RRC procedure codes ───────────────────────────────────────────────
RRC_SETUP   = 0x01
RRC_REESTAB = 0x02
RRC_RECONF  = 0x03

# ── F1AP procedure codes ──────────────────────────────────────────────
F1AP_INIT_UL_RRC = 0x07
F1AP_UE_CTX      = 0x02

# ── E1AP procedure codes ──────────────────────────────────────────────
E1AP_BEARER = 0x02

# ── XnAP procedure codes ──────────────────────────────────────────────
XNAP_HO_REQ = 0x02
XNAP_UE_REL = 0x03

# ── Cause codes ───────────────────────────────────────────────────────
CAUSE_AUTH_FAIL         = 0x15
CAUSE_CONGESTION        = 0x16
CAUSE_SEMANTIC_ERR      = 0x1a
CAUSE_OTHER_FAIL        = 0x01
CAUSE_RADIO_CONN_LOST   = 0x0a
CAUSE_PROC_CANCELLED    = 0x0a
CAUSE_UE_CTX_RELEASE    = 0x06
CAUSE_NO_SUITABLE_CELLS = 0x14
CAUSE_XNAP_RADIO_LOST   = 0x07
CAUSE_NGAP_RES_UNAVAIL  = 0x0b
CAUSE_RRC_HO_FAILURE    = 0x02


# ── Packet factory ────────────────────────────────────────────────────

def _pkt(src: str, dst: str, payload: bytes, ts: float) -> Packet:
    p = Ether() / IP(src=src, dst=dst) / UDP(sport=38412, dport=38412) / Raw(load=payload)
    p.time = ts
    return p

def nas(src, dst, msg_type, tmsi, cause=None, ts=0.0):
    pay = bytes([DISC_NAS, 0x00, msg_type]) + struct.pack('>I', tmsi)
    if cause: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def ngap(src, dst, proc, cat, ue_id, cause=None, ts=0.0):
    pay = bytes([DISC_NGAP, proc, cat]) + struct.pack('>I', ue_id)
    if cause: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def rrc(src, dst, proc, cat, ue_id, cause=None, ts=0.0):
    pay = bytes([DISC_RRC, proc, cat]) + struct.pack('>I', ue_id)
    if cause: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def f1ap(src, dst, proc, cat, ue_id, cause=None, ts=0.0):
    pay = bytes([DISC_F1AP, proc, cat]) + struct.pack('>I', ue_id)
    if cause: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def e1ap(src, dst, proc, cat, ue_id, cause=None, ts=0.0):
    pay = bytes([DISC_E1AP, proc, cat]) + struct.pack('>I', ue_id)
    if cause: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def xnap(src, dst, proc, cat, node_id, cause=None, ts=0.0):
    pay = bytes([DISC_XNAP, proc, cat]) + struct.pack('>I', node_id)
    if cause: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)


# ── UE Attach Scenario (UE 1-32) ────────────────────────────────────────

def ue_attach(pkts, ue_num, tmsi, t0,
              fail_rrc=False, fail_auth=False,
              fail_bearer=False, fail_pdu=False):
    UE = ue_ip(ue_num)
    t  = t0

    # Step 1: RRC Setup
    pkts.append(rrc(UE, GNB, RRC_SETUP, REQ, tmsi, ts=t))
    t += 0.05
    if fail_rrc:
        pkts.append(rrc(GNB, UE, RRC_SETUP, REJ, tmsi, cause=CAUSE_OTHER_FAIL, ts=t))
        return
    pkts.append(rrc(GNB, UE, RRC_SETUP, RSP, tmsi, ts=t))
    t += 0.05

    # Step 2: F1AP Initial UL RRC
    pkts.append(f1ap(GNB_DU, GNB_CU, F1AP_INIT_UL_RRC, REQ, tmsi, ts=t))
    t += 0.03
    pkts.append(f1ap(GNB_CU, GNB_DU, F1AP_INIT_UL_RRC, RSP, tmsi, ts=t))
    t += 0.05

    # Step 3: NAS Registration Request
    pkts.append(nas(UE, AMF, NAS_REG_REQ, tmsi, ts=t))
    t += 0.05

    # Step 4: NGAP Initial UE Message
    pkts.append(ngap(GNB, AMF, NGAP_INIT_UE, REQ, tmsi, ts=t))
    t += 0.05
    pkts.append(ngap(AMF, GNB, NGAP_INIT_UE, RSP, tmsi, ts=t))
    t += 0.05

    # Step 5: NAS Authentication
    pkts.append(nas(AMF, UE, NAS_AUTH_REQ, tmsi, ts=t))
    t += 0.05
    if fail_auth:
        pkts.append(nas(UE, AMF, NAS_AUTH_FAIL, tmsi, cause=CAUSE_AUTH_FAIL, ts=t))
        pkts.append(nas(AMF, UE, NAS_REG_REJECT, tmsi, cause=CAUSE_CONGESTION, ts=t + 0.05))
        return
    pkts.append(nas(UE, AMF, NAS_AUTH_RSP, tmsi, ts=t))
    t += 0.05

    # Step 6: NAS Security Mode
    pkts.append(nas(AMF, UE, NAS_SEC_CMD,  tmsi, ts=t))
    t += 0.05
    pkts.append(nas(UE,  AMF, NAS_SEC_COMP, tmsi, ts=t))
    t += 0.05

    # Step 7: NGAP InitialContextSetup
    pkts.append(ngap(AMF, GNB, NGAP_INIT_CTX, REQ, tmsi, ts=t))
    t += 0.05

    if fail_bearer:
        pkts.append(ngap(GNB, AMF, NGAP_INIT_CTX, REJ, tmsi, cause=CAUSE_RADIO_CONN_LOST, ts=t))
        pkts.append(f1ap(GNB_CU, GNB_DU, F1AP_UE_CTX, REQ, tmsi, ts=t + 0.03))
        pkts.append(f1ap(GNB_DU, GNB_CU, F1AP_UE_CTX, REJ, tmsi, cause=CAUSE_PROC_CANCELLED, ts=t + 0.06))
        pkts.append(e1ap(GNB_CU, GNB_UP, E1AP_BEARER, REQ, tmsi, ts=t + 0.09))
        pkts.append(e1ap(GNB_UP, GNB_CU, E1AP_BEARER, REJ, tmsi, cause=CAUSE_UE_CTX_RELEASE, ts=t + 0.12))
        return

    pkts.append(ngap(GNB, AMF, NGAP_INIT_CTX, RSP, tmsi, ts=t))
    t += 0.05

    # Step 8: F1AP UE Context Setup
    pkts.append(f1ap(GNB_CU, GNB_DU, F1AP_UE_CTX, REQ, tmsi, ts=t))
    t += 0.05
    pkts.append(f1ap(GNB_DU, GNB_CU, F1AP_UE_CTX, RSP, tmsi, ts=t))
    t += 0.05

    # Step 9: E1AP Bearer Context Setup
    pkts.append(e1ap(GNB_CU, GNB_UP, E1AP_BEARER, REQ, tmsi, ts=t))
    t += 0.05
    pkts.append(e1ap(GNB_UP, GNB_CU, E1AP_BEARER, RSP, tmsi, ts=t))
    t += 0.05

    # Step 10: NAS Registration Accept
    pkts.append(nas(AMF, UE, NAS_REG_ACCEPT, tmsi, ts=t))
    t += 0.05

    # Step 11: NAS PDU Session Establishment
    pkts.append(nas(UE, AMF, NAS_PDU_REQ, tmsi, ts=t))
    t += 0.05
    if fail_pdu:
        pkts.append(nas(AMF, UE, NAS_PDU_REJECT, tmsi, cause=CAUSE_SEMANTIC_ERR, ts=t))
        return
    pkts.append(nas(AMF, UE, NAS_PDU_ACCEPT, tmsi, ts=t))
    t += 0.05

    # Step 12: NGAP PDU Session Resource Setup
    pkts.append(ngap(AMF, GNB, NGAP_PDU_SETUP, REQ, tmsi, ts=t))
    t += 0.05
    pkts.append(ngap(GNB, AMF, NGAP_PDU_SETUP, RSP, tmsi, ts=t))
    t += 0.05

    # Step 13: RRC Reconfiguration (add data radio bearer)
    pkts.append(rrc(GNB, UE, RRC_RECONF, REQ, tmsi, ts=t))
    t += 0.05
    pkts.append(rrc(UE, GNB, RRC_RECONF, RSP, tmsi, ts=t))


# ── Xn-based handover (UE 33-48, gNB1 -> gNB2) ──────────────────────────

def xn_handover(pkts, ue_num, ue_id, t0, fail=False, fail_cause=CAUSE_NO_SUITABLE_CELLS):
    UE = ue_ip(ue_num)
    t  = t0

    pkts.append(xnap(GNB, GNB2, XNAP_HO_REQ, REQ, ue_id, ts=t))
    t += 0.02

    if fail:
        pkts.append(xnap(GNB2, GNB, XNAP_HO_REQ, REJ, ue_id, cause=fail_cause, ts=t))
        return

    pkts.append(xnap(GNB2, GNB, XNAP_HO_REQ, RSP, ue_id, ts=t))
    t += 0.03

    pkts.append(rrc(GNB, UE, RRC_RECONF, REQ, ue_id, ts=t))
    t += 0.05
    pkts.append(rrc(UE, GNB2, RRC_RECONF, RSP, ue_id, ts=t))
    t += 0.03

    pkts.append(xnap(GNB2, GNB, XNAP_UE_REL, REQ, ue_id, ts=t))
    t += 0.02
    pkts.append(xnap(GNB, GNB2, XNAP_UE_REL, RSP, ue_id, ts=t))


# ── N2-based handover (UE 49-64, gNB1 -> gNB3 via AMF) ──────────────────

def n2_handover(pkts, ue_num, ue_id, t0, fail=False):
    UE = ue_ip(ue_num)
    t  = t0

    pkts.append(ngap(GNB, AMF, NGAP_HO_PREP, REQ, ue_id, ts=t))
    t += 0.03

    if fail:
        pkts.append(ngap(AMF, GNB, NGAP_HO_PREP, REJ, ue_id, cause=CAUSE_NGAP_RES_UNAVAIL, ts=t))
        t += 0.05
        pkts.append(rrc(UE, GNB, RRC_REESTAB, REQ, ue_id, cause=CAUSE_RRC_HO_FAILURE, ts=t))
        t += 0.05
        pkts.append(rrc(GNB, UE, RRC_REESTAB, RSP, ue_id, ts=t))
        return

    pkts.append(ngap(AMF, GNB, NGAP_HO_PREP, RSP, ue_id, ts=t))
    t += 0.03

    pkts.append(rrc(GNB, UE, RRC_RECONF, REQ, ue_id, ts=t))
    t += 0.05
    pkts.append(rrc(UE, GNB3, RRC_RECONF, RSP, ue_id, ts=t))
    t += 0.03

    pkts.append(ngap(AMF, GNB, NGAP_UE_REL, REQ, ue_id, ts=t))
    t += 0.02
    pkts.append(ngap(GNB, AMF, NGAP_UE_REL, RSP, ue_id, ts=t))


# ── Main ──────────────────────────────────────────────────────────────

def generate(output_path: str = "data/raw/ue_64_6hr.pcap"):
    pkts = []
    base = time.time()

    print("=" * 60)
    print("  64 UE / 6-Hour Scenario — Attach + XnAP/NGAP Handover")
    print("  UE 1-32  : Full attach (NAS/NGAP/RRC/F1AP/E1AP)")
    print("  UE 33-48 : Xn-based handover (XnAP)")
    print("  UE 49-64 : N2-based handover (NGAP)")
    print("=" * 60)

    # ── UE 1-32: Attach ──────────────────────────────────────────────
    # Failures at UE 8 (auth), UE 16 (rrc), UE 24 (bearer), UE 32 (pdu)
    for ue_num in range(1, 33):
        tmsi = 6000 + ue_num
        t0 = base + (ue_num - 1) * STEP_S
        fail_auth   = (ue_num == 8)
        fail_rrc    = (ue_num == 16)
        fail_bearer = (ue_num == 24)
        fail_pdu    = (ue_num == 32)
        ue_attach(pkts, ue_num, tmsi, t0,
                  fail_rrc=fail_rrc, fail_auth=fail_auth,
                  fail_bearer=fail_bearer, fail_pdu=fail_pdu)

    # ── UE 33-48: Xn-based handover ──────────────────────────────────
    # Failures at UE 47 (no-suitable-cells), UE 48 (radio-conn-lost)
    for ue_num in range(33, 49):
        ue_id = 7000 + ue_num
        t0 = base + (ue_num - 1) * STEP_S
        if ue_num == 47:
            xn_handover(pkts, ue_num, ue_id, t0, fail=True, fail_cause=CAUSE_NO_SUITABLE_CELLS)
        elif ue_num == 48:
            xn_handover(pkts, ue_num, ue_id, t0, fail=True, fail_cause=CAUSE_XNAP_RADIO_LOST)
        else:
            xn_handover(pkts, ue_num, ue_id, t0)

    # ── UE 49-64: N2-based handover ──────────────────────────────────
    # Failures at UE 63, UE 64 (radio-resources-not-available)
    for ue_num in range(49, 65):
        ue_id = 7000 + ue_num
        t0 = base + (ue_num - 1) * STEP_S
        fail = ue_num in (63, 64)
        n2_handover(pkts, ue_num, ue_id, t0, fail=fail)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wrpcap(str(out), pkts)

    print(f"\n{'='*60}")
    print(f"  Written: {out}")
    print(f"  Total packets : {len(pkts)}")
    print(f"  Duration      : 6 hours ({STEP_S:.1f}s between UE events)")
    print(f"{'='*60}")
    print("""
EXPECTED ANOMALIES (run through dashboard to verify):
  UE 8  -> NAS Authentication failure (auth-failure)
  UE 16 -> RRC Setup rejection (other-failure)
  UE 24 -> E1AP Bearer failure + NGAP/F1AP cascade
  UE 32 -> PDU Session rejection (semantic error)
  UE 47 -> XnAP HandoverRequest reject (no-suitable-cells)
  UE 48 -> XnAP HandoverRequest reject (radio-conn-lost)
  UE 63 -> NGAP HandoverPreparation reject (no resources) + RRC Reestablishment
  UE 64 -> NGAP HandoverPreparation reject (no resources) + RRC Reestablishment

TO VALIDATE:
  python -m src.orchestrator.pipeline \\
    --input data/raw/ue_64_6hr.pcap --no-llm
""")


if __name__ == "__main__":
    generate()
