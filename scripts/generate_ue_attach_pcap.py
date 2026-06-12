"""
10 UE Attach Scenario PCAP Generator — Full 5G-NR Stack
========================================================
Generates a realistic 5G UE attach trace covering all 6 protocol layers.

Complete attach flow per UE (in order):
  Step 1  RRC Setup                  UE ↔ gNB              TS 38.331 §5.3.3
  Step 2  F1AP Initial UL RRC        gNB-DU → gNB-CU       TS 38.473 §8.4.2
  Step 3  NAS Registration Request   UE → AMF              TS 24.501 §8.2.6
  Step 4  NGAP Initial UE Message    gNB → AMF             TS 38.413 §8.6.1
  Step 5  NAS Authentication         AMF ↔ UE              TS 24.501 §8.2.1
  Step 6  NAS Security Mode          AMF ↔ UE              TS 24.501 §8.2.25
  Step 7  NGAP InitialContextSetup   AMF → gNB             TS 38.413 §8.3.1
  Step 8  F1AP UEContextSetup        gNB-CU → gNB-DU       TS 38.473 §8.3.1
  Step 9  E1AP BearerContextSetup    gNB-CU-CP → gNB-CU-UP TS 38.463 §8.3.1
  Step 10 NAS Registration Accept    AMF → UE              TS 24.501 §8.2.6
  Step 11 NAS PDU Session Setup      UE ↔ AMF              TS 24.501 §8.3.1
  Step 12 NGAP PDUSessionSetup       AMF → gNB             TS 38.413 §8.4.1
  Step 13 RRC Reconfiguration        gNB ↔ UE              TS 38.331 §5.3.5

10 UE Scenarios:
  UE 1-6 : Full successful attach (happy path)
  UE 7   : NAS Authentication failure  → anomaly: NAS_Authentication
  UE 8   : RRC Setup rejection         → anomaly: RRC_Setup
  UE 9   : E1AP Bearer Setup failure   → anomaly: E1AP_BearerContextSetup
  UE 10  : PDU Session rejection       → anomaly: NAS_PDUSession_Establishment

Plus: XnAP Setup + 2 Handovers for inter-gNB coverage

Ground Truth:
  Procedure                      Attempts  Success  Failure  Failure Cause
  ─────────────────────────────  ────────  ───────  ───────  ─────────────
  RRC_Setup                         10        9        1     other-failure (UE8)
  F1AP_InitialULRRCMessageTransfer   9        9        0     —
  NAS_Registration                  10        9        1     congestion (UE7 auth fails → retry)
  NGAP_InitialUEMessage              9        9        0     —
  NAS_Authentication                10        9        1     auth-failure (UE7)
  NAS_SecurityMode                   9        9        0     —
  NGAP_InitialContextSetup           9        8        1     radio-conn-lost (UE9)
  F1AP_UEContextSetup                8        7        1     procedure-cancelled (UE9)
  E1AP_BearerContextSetup            7        6        1     ue-context-release (UE9)
  NAS_Registration_Accept            8        8        0     —
  NAS_PDUSession_Establishment       8        7        1     semantically-incorrect (UE10)
  NGAP_PDUSessionResourceSetup       7        7        0     —
  RRC_Reconfiguration                7        7        0     —
  XnAP_XnSetup                       1        1        0     —
  XnAP_HandoverRequest               2        1        1     radio-connection-with-UE-lost
"""

import struct
import time
from pathlib import Path

from scapy.all import Ether, IP, Raw, UDP, Packet, wrpcap

# ── Network topology ──────────────────────────────────────────────────
AMF    = "10.0.0.1"     # AMF (Core)
GNB    = "10.0.0.2"     # gNB (source gNB)
GNB2   = "10.0.0.3"     # Neighbour gNB (for XnAP HO)
GNB_DU = "10.0.0.11"   # gNB-DU
GNB_CU = "10.0.0.10"   # gNB-CU-CP
GNB_UP = "10.0.0.12"   # gNB-CU-UP

def ue_ip(ue_id: int) -> str:
    return f"10.1.0.{ue_id}"

# ── Protocol discriminators ───────────────────────────────────────────
DISC_NAS  = 0x7e
DISC_NGAP = 0x3a
DISC_RRC  = 0x2b
DISC_F1AP = 0x1a
DISC_E1AP = 0x1b
DISC_XNAP = 0x1c

# ── Message categories ────────────────────────────────────────────────
REQ = 0x00   # Request / Initiating
RSP = 0x01   # Response / Success / Accept / Complete
REJ = 0x02   # Failure / Reject

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
NGAP_INIT_UE   = 0x08   # Initial UE Message

# ── RRC procedure codes ───────────────────────────────────────────────
RRC_SETUP   = 0x01
RRC_RECONF  = 0x03
RRC_REESTAB = 0x02

# ── F1AP procedure codes ──────────────────────────────────────────────
F1AP_INIT_UL_RRC = 0x07
F1AP_UE_CTX      = 0x02
F1AP_DL_RRC      = 0x05

# ── E1AP procedure codes ──────────────────────────────────────────────
E1AP_BEARER = 0x02

# ── XnAP procedure codes ──────────────────────────────────────────────
XNAP_SETUP  = 0x01
XNAP_HO_REQ = 0x02

# ── Cause codes ───────────────────────────────────────────────────────
CAUSE_AUTH_FAIL         = 0x15   # NAS auth-failure
CAUSE_CONGESTION        = 0x16   # NAS congestion
CAUSE_SEMANTIC_ERR      = 0x1a   # NAS semantically-incorrect-message
CAUSE_OTHER_FAIL        = 0x01   # RRC other-failure
CAUSE_RLF               = 0x04   # RRC rlf-report-available
CAUSE_USER_INACTIVITY   = 0x09   # NGAP user-inactivity
CAUSE_RADIO_CONN_LOST   = 0x0a   # NGAP radio-connection-with-ue-lost
CAUSE_PROC_CANCELLED    = 0x0a   # F1AP procedure-cancelled
CAUSE_UE_CTX_RELEASE    = 0x06   # E1AP ue-context-release
CAUSE_XNAP_RADIO_LOST   = 0x07   # XnAP radio-connection-with-UE-lost


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


# ── UE Attach Scenario ────────────────────────────────────────────────

def ue_attach(pkts, ue_num, tmsi, t0,
              fail_rrc=False, fail_auth=False,
              fail_bearer=False, fail_pdu=False):
    """
    Generate complete 5G attach flow for one UE.
    All failure flags inject anomalies at the specified step.
    """
    UE  = ue_ip(ue_num)
    t   = t0
    ok  = True   # track if UE reached registration accept

    label = f"UE-{ue_num} (TMSI={tmsi})"
    print(f"\n{'─'*55}")
    print(f"  {label}")
    print(f"{'─'*55}")

    # ── Step 1: RRC Setup ──────────────────────────────────────────
    pkts.append(rrc(UE, GNB, RRC_SETUP, REQ, tmsi, ts=t))
    t += 0.05
    if fail_rrc:
        pkts.append(rrc(GNB, UE, RRC_SETUP, REJ, tmsi, cause=CAUSE_OTHER_FAIL, ts=t))
        print(f"  Step 1  RRC Setup               ❌ REJECT (other-failure)")
        return   # UE cannot proceed
    pkts.append(rrc(GNB, UE, RRC_SETUP, RSP, tmsi, ts=t))
    print(f"  Step 1  RRC Setup               ✅ COMPLETE")
    t += 0.05

    # ── Step 2: F1AP Initial UL RRC ───────────────────────────────
    pkts.append(f1ap(GNB_DU, GNB_CU, F1AP_INIT_UL_RRC, REQ, tmsi, ts=t))
    t += 0.03
    pkts.append(f1ap(GNB_CU, GNB_DU, F1AP_INIT_UL_RRC, RSP, tmsi, ts=t))
    print(f"  Step 2  F1AP Initial UL RRC     ✅ FORWARDED")
    t += 0.05

    # ── Step 3: NAS Registration Request ──────────────────────────
    pkts.append(nas(UE, AMF, NAS_REG_REQ, tmsi, ts=t))
    print(f"  Step 3  NAS Registration Req    ✅ SENT")
    t += 0.05

    # ── Step 4: NGAP Initial UE Message ───────────────────────────
    pkts.append(ngap(GNB, AMF, NGAP_INIT_UE, REQ, tmsi, ts=t))
    t += 0.05
    pkts.append(ngap(AMF, GNB, NGAP_INIT_UE, RSP, tmsi, ts=t))
    print(f"  Step 4  NGAP Initial UE Message ✅ DELIVERED")
    t += 0.05

    # ── Step 5: NAS Authentication ────────────────────────────────
    pkts.append(nas(AMF, UE, NAS_AUTH_REQ, tmsi, ts=t))
    t += 0.05
    if fail_auth:
        pkts.append(nas(UE, AMF, NAS_AUTH_FAIL, tmsi, cause=CAUSE_AUTH_FAIL, ts=t))
        print(f"  Step 5  NAS Authentication      ❌ FAILURE (auth-failure)")
        # NAS Registration also fails
        pkts.append(nas(AMF, UE, NAS_REG_REJECT, tmsi, cause=CAUSE_CONGESTION, ts=t+0.05))
        print(f"          NAS Registration         ❌ REJECT (congestion → retry)")
        return
    pkts.append(nas(UE, AMF, NAS_AUTH_RSP, tmsi, ts=t))
    print(f"  Step 5  NAS Authentication      ✅ SUCCESS")
    t += 0.05

    # ── Step 6: NAS Security Mode ─────────────────────────────────
    pkts.append(nas(AMF, UE, NAS_SEC_CMD,  tmsi, ts=t))
    t += 0.05
    pkts.append(nas(UE,  AMF, NAS_SEC_COMP, tmsi, ts=t))
    print(f"  Step 6  NAS Security Mode       ✅ COMPLETE")
    t += 0.05

    # ── Step 7: NGAP InitialContextSetup ──────────────────────────
    pkts.append(ngap(AMF, GNB, NGAP_INIT_CTX, REQ, tmsi, ts=t))
    t += 0.05

    if fail_bearer:
        # Context setup fails due to bearer issue
        pkts.append(ngap(GNB, AMF, NGAP_INIT_CTX, REJ, tmsi,
                         cause=CAUSE_RADIO_CONN_LOST, ts=t))
        print(f"  Step 7  NGAP InitialContextSetup❌ FAILURE (radio-connection-lost)")

        # F1AP UE Context also fails
        pkts.append(f1ap(GNB_CU, GNB_DU, F1AP_UE_CTX, REQ, tmsi, ts=t+0.03))
        pkts.append(f1ap(GNB_DU, GNB_CU, F1AP_UE_CTX, REJ, tmsi,
                         cause=CAUSE_PROC_CANCELLED, ts=t+0.06))
        print(f"  Step 8  F1AP UEContextSetup     ❌ FAILURE (procedure-cancelled)")

        # E1AP Bearer also fails
        pkts.append(e1ap(GNB_CU, GNB_UP, E1AP_BEARER, REQ, tmsi, ts=t+0.09))
        pkts.append(e1ap(GNB_UP, GNB_CU, E1AP_BEARER, REJ, tmsi,
                         cause=CAUSE_UE_CTX_RELEASE, ts=t+0.12))
        print(f"  Step 9  E1AP BearerContextSetup ❌ FAILURE (ue-context-release)")
        return

    pkts.append(ngap(GNB, AMF, NGAP_INIT_CTX, RSP, tmsi, ts=t))
    print(f"  Step 7  NGAP InitialContextSetup✅ SUCCESS")
    t += 0.05

    # ── Step 8: F1AP UE Context Setup ─────────────────────────────
    pkts.append(f1ap(GNB_CU, GNB_DU, F1AP_UE_CTX, REQ, tmsi, ts=t))
    t += 0.05
    pkts.append(f1ap(GNB_DU, GNB_CU, F1AP_UE_CTX, RSP, tmsi, ts=t))
    print(f"  Step 8  F1AP UEContextSetup     ✅ SUCCESS")
    t += 0.05

    # ── Step 9: E1AP Bearer Context Setup ─────────────────────────
    pkts.append(e1ap(GNB_CU, GNB_UP, E1AP_BEARER, REQ, tmsi, ts=t))
    t += 0.05
    pkts.append(e1ap(GNB_UP, GNB_CU, E1AP_BEARER, RSP, tmsi, ts=t))
    print(f"  Step 9  E1AP BearerContextSetup ✅ SUCCESS")
    t += 0.05

    # ── Step 10: NAS Registration Accept ──────────────────────────
    pkts.append(nas(AMF, UE, NAS_REG_ACCEPT, tmsi, ts=t))
    print(f"  Step 10 NAS Registration Accept ✅ REGISTERED")
    t += 0.05

    # ── Step 11: NAS PDU Session Establishment ────────────────────
    pkts.append(nas(UE, AMF, NAS_PDU_REQ, tmsi, ts=t))
    t += 0.05
    if fail_pdu:
        pkts.append(nas(AMF, UE, NAS_PDU_REJECT, tmsi,
                        cause=CAUSE_SEMANTIC_ERR, ts=t))
        print(f"  Step 11 NAS PDU Session         ❌ REJECT (semantically-incorrect)")
        return
    pkts.append(nas(AMF, UE, NAS_PDU_ACCEPT, tmsi, ts=t))
    print(f"  Step 11 NAS PDU Session         ✅ ESTABLISHED")
    t += 0.05

    # ── Step 12: NGAP PDU Session Resource Setup ──────────────────
    pkts.append(ngap(AMF, GNB, NGAP_PDU_SETUP, REQ, tmsi, ts=t))
    t += 0.05
    pkts.append(ngap(GNB, AMF, NGAP_PDU_SETUP, RSP, tmsi, ts=t))
    print(f"  Step 12 NGAP PDU Session Setup  ✅ SUCCESS")
    t += 0.05

    # ── Step 13: RRC Reconfiguration (add data radio bearer) ──────
    pkts.append(rrc(GNB, UE, RRC_RECONF, REQ, tmsi, ts=t))
    t += 0.05
    pkts.append(rrc(UE, GNB, RRC_RECONF, RSP, tmsi, ts=t))
    print(f"  Step 13 RRC Reconfiguration     ✅ COMPLETE")
    print(f"  {'─'*40}")
    print(f"  ✅ UE-{ue_num} ATTACHED SUCCESSFULLY")


# ── XnAP inter-gNB handover ───────────────────────────────────────────

def xnap_setup_and_handover(pkts, base_time):
    t = base_time + 200.0
    print(f"\n{'═'*55}")
    print("  XnAP Inter-gNB Setup + Handover")
    print(f"{'═'*55}")

    # XnAP Setup between gNB and gNB2
    pkts.append(xnap(GNB, GNB2, XNAP_SETUP, REQ, 9001, ts=t))
    t += 0.05
    pkts.append(xnap(GNB2, GNB, XNAP_SETUP, RSP, 9001, ts=t))
    print("  XnAP XnSetup (gNB ↔ gNB2)       ✅ SUCCESS")
    t += 0.5

    # HO success for UE 1
    pkts.append(xnap(GNB, GNB2, XNAP_HO_REQ, REQ, 1001, ts=t))
    t += 0.1
    pkts.append(xnap(GNB2, GNB, XNAP_HO_REQ, RSP, 1001, ts=t))
    print("  XnAP Handover UE-1 → gNB2       ✅ SUCCESS")
    t += 0.5

    # HO failure for UE 2 (radio lost during HO)
    pkts.append(xnap(GNB, GNB2, XNAP_HO_REQ, REQ, 1002, ts=t))
    t += 0.1
    pkts.append(xnap(GNB2, GNB, XNAP_HO_REQ, REJ, 1002,
                     cause=CAUSE_XNAP_RADIO_LOST, ts=t))
    print("  XnAP Handover UE-2 → gNB2       ❌ FAILURE (radio-connection-with-UE-lost)")


# ── Main ──────────────────────────────────────────────────────────────

def generate(output_path: str = "data/raw/ue_attach_10.pcap"):
    pkts = []
    base = time.time()

    print("=" * 55)
    print("  10 UE Attach Scenario — Full 5G-NR Stack")
    print("  NAS · NGAP · RRC · F1AP · E1AP · XnAP")
    print("=" * 55)

    # UE 1-6: clean successful attach
    scenarios = [
        (1,  1001, False, False, False, False),
        (2,  1002, False, False, False, False),
        (3,  1003, False, False, False, False),
        (4,  1004, False, False, False, False),
        (5,  1005, False, False, False, False),
        (6,  1006, False, False, False, False),
        # UE 7: Auth fails
        (7,  1007, False, True,  False, False),
        # UE 8: RRC Setup fails
        (8,  1008, True,  False, False, False),
        # UE 9: Bearer / E1AP fails
        (9,  1009, False, False, True,  False),
        # UE 10: PDU Session rejected
        (10, 1010, False, False, False, True),
    ]

    for ue_num, tmsi, fail_rrc, fail_auth, fail_bearer, fail_pdu in scenarios:
        t_offset = base + (ue_num - 1) * 3.0   # 3 seconds between UEs
        ue_attach(pkts, ue_num, tmsi, t_offset,
                  fail_rrc=fail_rrc, fail_auth=fail_auth,
                  fail_bearer=fail_bearer, fail_pdu=fail_pdu)

    # XnAP inter-gNB setup and handovers
    xnap_setup_and_handover(pkts, base)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wrpcap(str(out), pkts)

    print(f"\n{'='*55}")
    print(f"  ✅ PCAP written: {out}")
    print(f"  Total packets : {len(pkts)}")
    print(f"{'='*55}")

    print("""
EXPECTED ANOMALIES (run through dashboard to verify):
  ┌────────────────────────────────────────────────────┐
  │  UE 7  → NAS Authentication failure (auth-failure) │
  │  UE 8  → RRC Setup rejection (other-failure)       │
  │  UE 9  → E1AP Bearer failure + NGAP cascade        │
  │  UE 10 → PDU Session rejection (semantic error)    │
  │  XnAP  → Handover failure (radio-conn-lost)        │
  └────────────────────────────────────────────────────┘

TO VALIDATE:
  python -m src.orchestrator.pipeline \\
    --input data/raw/ue_attach_10.pcap --no-llm
""")


if __name__ == "__main__":
    generate()
