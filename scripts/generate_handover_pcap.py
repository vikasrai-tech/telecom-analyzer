"""
20 UE Handover Scenario PCAP Generator — XnAP + NGAP
=====================================================
Generates a 5G-NR trace covering both handover paths with failures injected.

Group A — UE 1-10: Xn-based handover (gNB1 -> gNB2, intra-AMF)
  Success flow:
    XnAP_HandoverRequest      REQ  gNB1 -> gNB2   TS 38.423 §8.3.1
    XnAP_HandoverRequest      RSP  gNB2 -> gNB1   (Handover Request Ack)
    RRC_Reconfiguration       REQ  gNB1 -> UE     TS 38.331 §5.3.5 (HO command)
    RRC_Reconfiguration       RSP  UE   -> gNB2   (HO complete to target)
    XnAP_XnUEContextRelease   REQ  gNB2 -> gNB1   TS 38.423 §8.3.3
    XnAP_XnUEContextRelease   RSP  gNB1 -> gNB2

  UE 9-10: target gNB rejects the handover
    XnAP_HandoverRequest      REQ  gNB1 -> gNB2
    XnAP_HandoverRequest      REJ  gNB2 -> gNB1   cause: no-suitable-cells / radio-conn-lost
    (UE stays on gNB1 — no RRC reconfig, no context release)

Group B — UE 11-20: N2-based handover (gNB1 -> gNB3, via AMF)
  Success flow:
    NGAP_HandoverPreparation  REQ  gNB1 -> AMF    TS 38.413 §8.4.5 (Handover Required)
    NGAP_HandoverPreparation  RSP  AMF  -> gNB1   (Handover Command)
    RRC_Reconfiguration       REQ  gNB1 -> UE     (HO command)
    RRC_Reconfiguration       RSP  UE   -> gNB3   (HO complete to target)
    NGAP_UEContextRelease     REQ  AMF  -> gNB1   TS 38.413 §8.3.3
    NGAP_UEContextRelease     RSP  gNB1 -> AMF

  UE 19-20: AMF rejects the handover preparation
    NGAP_HandoverPreparation  REQ  gNB1 -> AMF
    NGAP_HandoverPreparation  REJ  AMF  -> gNB1   cause: radio-resources-not-available
    RRC_Reestablishment       REQ  UE   -> gNB1   cause: handover-failure (fallback)
    RRC_Reestablishment       RSP  gNB1 -> UE     (UE stays on source cell)

Ground Truth:
  Procedure                      Attempts  Success  Failure  Failure Cause
  ─────────────────────────────  ────────  ───────  ───────  ─────────────
  XnAP_HandoverRequest               10        8        2     no-suitable-cells-in-target-cell-list /
                                                               radio-connection-with-UE-lost (UE9, UE10)
  XnAP_XnUEContextRelease              8        8        0     —
  NGAP_HandoverPreparation            10        8        2     radio-resources-not-available (UE19, UE20)
  NGAP_UEContextRelease                8        8        0     —
  RRC_Reconfiguration                 16       16        0     —
  RRC_Reestablishment                  2        2        0     —  (fallback after HO failure, succeeds)
"""

import struct
import time
from pathlib import Path

from scapy.all import Ether, IP, Raw, UDP, Packet, wrpcap

# ── Network topology ──────────────────────────────────────────────────
AMF  = "10.0.0.1"     # AMF (Core)
GNB1 = "10.0.0.2"     # Source gNB (serving cell for all 20 UEs)
GNB2 = "10.0.0.3"     # Target gNB for Xn-based handover (Group A)
GNB3 = "10.0.0.4"     # Target gNB for N2-based handover (Group B)

def ue_ip(ue_id: int) -> str:
    return f"10.1.0.{ue_id}"

# ── Protocol discriminators ───────────────────────────────────────────
DISC_NGAP = 0x3a
DISC_RRC  = 0x2b
DISC_XNAP = 0x1c

# ── Message categories ────────────────────────────────────────────────
REQ = 0x00   # Request / Initiating
RSP = 0x01   # Response / Success / Complete / Acknowledge
REJ = 0x02   # Failure / Reject

# ── Procedure codes ───────────────────────────────────────────────────
NGAP_HO_PREP    = 0x05   # NGAP_HandoverPreparation     TS 38.413 §8.4.5
NGAP_UE_REL     = 0x04   # NGAP_UEContextRelease        TS 38.413 §8.3.3
RRC_REESTAB     = 0x02   # RRC_Reestablishment          TS 38.331 §5.3.7
RRC_RECONF      = 0x03   # RRC_Reconfiguration          TS 38.331 §5.3.5
XNAP_HO_REQ     = 0x02   # XnAP_HandoverRequest         TS 38.423 §8.3.1
XNAP_UE_REL     = 0x03   # XnAP_XnUEContextRelease      TS 38.423 §8.3.3

# ── Cause codes ───────────────────────────────────────────────────────
CAUSE_NO_SUITABLE_CELLS = 0x14   # XnAP no-suitable-cells-in-target-cell-list
CAUSE_XNAP_RADIO_LOST   = 0x07   # XnAP radio-connection-with-UE-lost
CAUSE_NGAP_RES_UNAVAIL  = 0x0b   # NGAP radio-resources-not-available
CAUSE_RRC_HO_FAILURE    = 0x02   # RRC handover-failure


# ── Packet factory ────────────────────────────────────────────────────

def _pkt(src: str, dst: str, payload: bytes, ts: float) -> Packet:
    p = Ether() / IP(src=src, dst=dst) / UDP(sport=38412, dport=38412) / Raw(load=payload)
    p.time = ts
    return p

def ngap(src, dst, proc, cat, ue_id, cause=None, ts=0.0):
    pay = bytes([DISC_NGAP, proc, cat]) + struct.pack('>I', ue_id)
    if cause: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def rrc(src, dst, proc, cat, ue_id, cause=None, ts=0.0):
    pay = bytes([DISC_RRC, proc, cat]) + struct.pack('>I', ue_id)
    if cause: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def xnap(src, dst, proc, cat, ue_id, cause=None, ts=0.0):
    pay = bytes([DISC_XNAP, proc, cat]) + struct.pack('>I', ue_id)
    if cause: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)


# ── Group A: Xn-based handover (gNB1 -> gNB2) ─────────────────────────

def xn_handover(pkts, ue_num, ue_id, t0, fail=False, fail_cause=CAUSE_NO_SUITABLE_CELLS):
    UE = ue_ip(ue_num)
    t  = t0

    print(f"\n{'─'*55}")
    print(f"  UE-{ue_num} (id={ue_id}) — Xn Handover gNB1 -> gNB2")
    print(f"{'─'*55}")

    # Step 1: XnAP Handover Request
    pkts.append(xnap(GNB1, GNB2, XNAP_HO_REQ, REQ, ue_id, ts=t))
    t += 0.02

    if fail:
        cause_name = "no-suitable-cells-in-target-cell-list" if fail_cause == CAUSE_NO_SUITABLE_CELLS else "radio-connection-with-UE-lost"
        pkts.append(xnap(GNB2, GNB1, XNAP_HO_REQ, REJ, ue_id, cause=fail_cause, ts=t))
        print(f"  Step 1  XnAP HandoverRequest    ❌ REJECT ({cause_name})")
        print(f"          UE remains on gNB1 — no RRC reconfig, no context release")
        return

    pkts.append(xnap(GNB2, GNB1, XNAP_HO_REQ, RSP, ue_id, ts=t))
    print(f"  Step 1  XnAP HandoverRequest    ✅ ACK (Handover Request Acknowledge)")
    t += 0.03

    # Step 2: RRC Reconfiguration (handover command -> UE, complete -> target gNB)
    pkts.append(rrc(GNB1, UE, RRC_RECONF, REQ, ue_id, ts=t))
    t += 0.05
    pkts.append(rrc(UE, GNB2, RRC_RECONF, RSP, ue_id, ts=t))
    print(f"  Step 2  RRC Reconfiguration     ✅ COMPLETE (UE moved to gNB2)")
    t += 0.03

    # Step 3: XnAP Xn UE Context Release (gNB2 tells gNB1 to release old context)
    pkts.append(xnap(GNB2, GNB1, XNAP_UE_REL, REQ, ue_id, ts=t))
    t += 0.02
    pkts.append(xnap(GNB1, GNB2, XNAP_UE_REL, RSP, ue_id, ts=t))
    print(f"  Step 3  XnAP XnUEContextRelease ✅ RELEASED (gNB1 context freed)")
    print(f"  ✅ UE-{ue_num} HANDED OVER (Xn)")


# ── Group B: N2-based handover (gNB1 -> gNB3 via AMF) ─────────────────

def n2_handover(pkts, ue_num, ue_id, t0, fail=False):
    UE = ue_ip(ue_num)
    t  = t0

    print(f"\n{'─'*55}")
    print(f"  UE-{ue_num} (id={ue_id}) — N2 Handover gNB1 -> gNB3 (via AMF)")
    print(f"{'─'*55}")

    # Step 1: NGAP Handover Preparation (Handover Required -> Handover Command)
    pkts.append(ngap(GNB1, AMF, NGAP_HO_PREP, REQ, ue_id, ts=t))
    t += 0.03

    if fail:
        pkts.append(ngap(AMF, GNB1, NGAP_HO_PREP, REJ, ue_id, cause=CAUSE_NGAP_RES_UNAVAIL, ts=t))
        print(f"  Step 1  NGAP HandoverPreparation❌ REJECT (radio-resources-not-available)")
        t += 0.05

        # Fallback: UE re-establishes RRC connection on the source cell
        pkts.append(rrc(UE, GNB1, RRC_REESTAB, REQ, ue_id, cause=CAUSE_RRC_HO_FAILURE, ts=t))
        t += 0.05
        pkts.append(rrc(GNB1, UE, RRC_REESTAB, RSP, ue_id, ts=t))
        print(f"  Step 2  RRC Reestablishment     ✅ COMPLETE (UE stays on gNB1)")
        return

    pkts.append(ngap(AMF, GNB1, NGAP_HO_PREP, RSP, ue_id, ts=t))
    print(f"  Step 1  NGAP HandoverPreparation✅ COMMAND (Handover Command)")
    t += 0.03

    # Step 2: RRC Reconfiguration (handover command -> UE, complete -> target gNB)
    pkts.append(rrc(GNB1, UE, RRC_RECONF, REQ, ue_id, ts=t))
    t += 0.05
    pkts.append(rrc(UE, GNB3, RRC_RECONF, RSP, ue_id, ts=t))
    print(f"  Step 2  RRC Reconfiguration     ✅ COMPLETE (UE moved to gNB3)")
    t += 0.03

    # Step 3: NGAP UE Context Release (AMF tells gNB1 to release old context)
    pkts.append(ngap(AMF, GNB1, NGAP_UE_REL, REQ, ue_id, ts=t))
    t += 0.02
    pkts.append(ngap(GNB1, AMF, NGAP_UE_REL, RSP, ue_id, ts=t))
    print(f"  Step 3  NGAP UEContextRelease   ✅ RELEASED (gNB1 context freed)")
    print(f"  ✅ UE-{ue_num} HANDED OVER (N2)")


# ── Main ──────────────────────────────────────────────────────────────

def generate(output_path: str = "data/raw/ue_handover_20.pcap"):
    pkts = []
    base = time.time()

    print("=" * 55)
    print("  20 UE Handover Scenario — XnAP + NGAP")
    print("  Group A: Xn handover (UE 1-10)")
    print("  Group B: N2 handover (UE 11-20)")
    print("=" * 55)

    # Group A — Xn-based handover (gNB1 -> gNB2)
    xn_scenarios = [
        (1,  2001, False, None),
        (2,  2002, False, None),
        (3,  2003, False, None),
        (4,  2004, False, None),
        (5,  2005, False, None),
        (6,  2006, False, None),
        (7,  2007, False, None),
        (8,  2008, False, None),
        (9,  2009, True,  CAUSE_NO_SUITABLE_CELLS),
        (10, 2010, True,  CAUSE_XNAP_RADIO_LOST),
    ]
    for ue_num, ue_id, fail, cause in xn_scenarios:
        t_offset = base + (ue_num - 1) * 2.0
        if cause is not None:
            xn_handover(pkts, ue_num, ue_id, t_offset, fail=fail, fail_cause=cause)
        else:
            xn_handover(pkts, ue_num, ue_id, t_offset, fail=fail)

    # Group B — N2-based handover (gNB1 -> gNB3, via AMF)
    n2_scenarios = [
        (11, 2011, False),
        (12, 2012, False),
        (13, 2013, False),
        (14, 2014, False),
        (15, 2015, False),
        (16, 2016, False),
        (17, 2017, False),
        (18, 2018, False),
        (19, 2019, True),
        (20, 2020, True),
    ]
    for ue_num, ue_id, fail in n2_scenarios:
        t_offset = base + (ue_num - 1) * 2.0
        n2_handover(pkts, ue_num, ue_id, t_offset, fail=fail)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wrpcap(str(out), pkts)

    print(f"\n{'='*55}")
    print(f"  ✅ PCAP written: {out}")
    print(f"  Total packets : {len(pkts)}")
    print(f"{'='*55}")

    print("""
EXPECTED ANOMALIES (run through dashboard to verify):
  ┌──────────────────────────────────────────────────────────┐
  │  UE 9  → XnAP HandoverRequest reject (no-suitable-cells)  │
  │  UE 10 → XnAP HandoverRequest reject (radio-conn-lost)    │
  │  UE 19 → NGAP HandoverPreparation reject (no resources)   │
  │  UE 20 → NGAP HandoverPreparation reject (no resources)   │
  └──────────────────────────────────────────────────────────┘

TO VALIDATE:
  python -m src.orchestrator.pipeline \\
    --input data/raw/ue_handover_20.pcap --no-llm
""")


if __name__ == "__main__":
    generate()
