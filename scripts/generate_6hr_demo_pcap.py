"""
Generate a 6-hour real .pcap file for the correlated demo dataset.

Timestamps are aligned to match demo_6hr_kpi.csv / demo_6hr_stats.csv
(START = now - 6h).

64 UEs across the 6-hour window with 3 injected anomaly bursts that
match the KPI/Stats anomaly windows:
  Event A (Hour 1.5-2.5) PRB_CONGESTION  → PCI_2: attach failures, RRC drops
  Event B (Hour 3.0-4.0) SNR_DEGRADATION → PCI_3: Xn/N2 handover failures
  Event C (Hour 5.0-5.75) RRC_DROP_CASCADE → PCI_1+PCI_4: auth + bearer cascade

Usage:
  python scripts/generate_6hr_demo_pcap.py
"""

import struct
import time as _time
from datetime import datetime, timedelta
from pathlib import Path

from scapy.all import Ether, IP, UDP, Raw, wrpcap

# ── Topology ─────────────────────────────────────────────────────────
AMF    = "10.0.0.1"
GNB1   = "10.0.0.2"    # source gNB (PCI_1, PCI_2)
GNB2   = "10.0.0.3"    # target gNB for Xn-HO (PCI_3)
GNB3   = "10.0.0.4"    # target gNB for N2-HO (PCI_4)
GNB_DU = "10.0.0.11"
GNB_CU = "10.0.0.10"
GNB_UP = "10.0.0.12"

# Cell → gNB mapping (matches KPI/Stats data)
CELL_GNB = {
    "PCI_1": GNB1, "PCI_2": GNB1,
    "PCI_3": GNB2, "PCI_4": GNB3,
}

# ── Timing ────────────────────────────────────────────────────────────
NOW        = datetime.now().replace(second=0, microsecond=0)
START      = NOW - timedelta(hours=6)
BASE_TS    = START.timestamp()   # absolute UNIX timestamp for pcap
DURATION_S = 6 * 3600
N_UE       = 64
STEP_S     = DURATION_S / N_UE  # ~337.5s between UE events

# Anomaly windows in seconds from BASE_TS
ANOM_A = (1.5 * 3600, 2.5 * 3600)   # PRB congestion   → PCI_2
ANOM_B = (3.0 * 3600, 4.0 * 3600)   # SNR degradation  → PCI_3
ANOM_C = (5.0 * 3600, 5.75 * 3600)  # RRC drop cascade → PCI_1, PCI_4

# ── Protocol discriminators (matches existing parser) ─────────────────
DISC_NAS  = 0x7e
DISC_NGAP = 0x3a
DISC_RRC  = 0x2b
DISC_F1AP = 0x1a
DISC_E1AP = 0x1b
DISC_XNAP = 0x1c

REQ = 0x00; RSP = 0x01; REJ = 0x02

# NAS
NAS_REG_REQ    = 0x41; NAS_REG_ACCEPT = 0x42; NAS_REG_REJECT = 0x44
NAS_AUTH_REQ   = 0x56; NAS_AUTH_RSP   = 0x57; NAS_AUTH_FAIL  = 0x59
NAS_SEC_CMD    = 0x5c; NAS_SEC_COMP   = 0x5d
NAS_PDU_REQ    = 0xc1; NAS_PDU_ACCEPT = 0xc2; NAS_PDU_REJECT = 0xc3

# NGAP
NGAP_INIT_CTX  = 0x01; NGAP_PDU_SETUP = 0x02
NGAP_UE_REL    = 0x04; NGAP_HO_PREP   = 0x05; NGAP_INIT_UE   = 0x08

# RRC
RRC_SETUP   = 0x01; RRC_REESTAB = 0x02; RRC_RECONF  = 0x03

# F1AP / E1AP / XnAP
F1AP_INIT_UL = 0x07; F1AP_UE_CTX = 0x02
E1AP_BEARER  = 0x02
XNAP_HO_REQ  = 0x02; XNAP_UE_REL = 0x03

# Causes
CAUSE_AUTH_FAIL   = 0x15; CAUSE_CONGESTION    = 0x16
CAUSE_SEMANTIC_ERR= 0x1a; CAUSE_OTHER_FAIL    = 0x01
CAUSE_RADIO_LOST  = 0x0a; CAUSE_PROC_CANCEL   = 0x0a
CAUSE_UE_CTX_REL  = 0x06; CAUSE_NO_CELLS      = 0x14
CAUSE_XNAP_RADIO  = 0x07; CAUSE_NGAP_RES      = 0x0b
CAUSE_RRC_HO_FAIL = 0x02; CAUSE_PRB_EXHAUST   = 0x1c
CAUSE_SNR_LOW     = 0x1d; CAUSE_RADIO_INTF    = 0x1e


def ue_ip(n: int) -> str:
    return f"10.1.{n // 256}.{n % 256}"


# ── Packet factory ────────────────────────────────────────────────────
def _pkt(src, dst, payload, ts):
    p = Ether() / IP(src=src, dst=dst) / UDP(sport=38412, dport=38412) / Raw(load=payload)
    p.time = ts
    return p

def nas(src, dst, mt, tmsi, cause=None, ts=0.0):
    pay = bytes([DISC_NAS, 0x00, mt]) + struct.pack('>I', tmsi)
    if cause is not None: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def ngap(src, dst, proc, cat, uid, cause=None, ts=0.0):
    pay = bytes([DISC_NGAP, proc, cat]) + struct.pack('>I', uid)
    if cause is not None: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def rrc(src, dst, proc, cat, uid, cause=None, ts=0.0):
    pay = bytes([DISC_RRC, proc, cat]) + struct.pack('>I', uid)
    if cause is not None: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def f1ap(src, dst, proc, cat, uid, cause=None, ts=0.0):
    pay = bytes([DISC_F1AP, proc, cat]) + struct.pack('>I', uid)
    if cause is not None: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def e1ap(src, dst, proc, cat, uid, cause=None, ts=0.0):
    pay = bytes([DISC_E1AP, proc, cat]) + struct.pack('>I', uid)
    if cause is not None: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)

def xnap(src, dst, proc, cat, uid, cause=None, ts=0.0):
    pay = bytes([DISC_XNAP, proc, cat]) + struct.pack('>I', uid)
    if cause is not None: pay += bytes([cause])
    return _pkt(src, dst, pay, ts)


# ── Anomaly helpers ───────────────────────────────────────────────────
def _in_window(t_offset, window):
    return window[0] <= t_offset <= window[1]

def _anom_cell(t_offset):
    """Return active anomaly type and cell for this time offset."""
    if _in_window(t_offset, ANOM_A):
        return "prb_congestion", ["PCI_2"]
    if _in_window(t_offset, ANOM_B):
        return "snr_degradation", ["PCI_3"]
    if _in_window(t_offset, ANOM_C):
        return "rrc_drop_cascade", ["PCI_1", "PCI_4"]
    return None, []


# ── UE Attach (normal + failure variants) ────────────────────────────
def attach_normal(pkts, ue_num, tmsi, t0, src_gnb=GNB1):
    UE = ue_ip(ue_num); t = t0
    pkts.append(rrc(UE, src_gnb, RRC_SETUP, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(rrc(src_gnb, UE, RRC_SETUP, RSP, tmsi, ts=t)); t += 0.05
    pkts.append(f1ap(GNB_DU, GNB_CU, F1AP_INIT_UL, REQ, tmsi, ts=t)); t += 0.03
    pkts.append(f1ap(GNB_CU, GNB_DU, F1AP_INIT_UL, RSP, tmsi, ts=t)); t += 0.05
    pkts.append(nas(UE, AMF, NAS_REG_REQ, tmsi, ts=t)); t += 0.05
    pkts.append(ngap(src_gnb, AMF, NGAP_INIT_UE, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(ngap(AMF, src_gnb, NGAP_INIT_UE, RSP, tmsi, ts=t)); t += 0.05
    pkts.append(nas(AMF, UE, NAS_AUTH_REQ, tmsi, ts=t)); t += 0.05
    pkts.append(nas(UE, AMF, NAS_AUTH_RSP, tmsi, ts=t)); t += 0.05
    pkts.append(nas(AMF, UE, NAS_SEC_CMD, tmsi, ts=t)); t += 0.05
    pkts.append(nas(UE, AMF, NAS_SEC_COMP, tmsi, ts=t)); t += 0.05
    pkts.append(ngap(AMF, src_gnb, NGAP_INIT_CTX, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(ngap(src_gnb, AMF, NGAP_INIT_CTX, RSP, tmsi, ts=t)); t += 0.05
    pkts.append(f1ap(GNB_CU, GNB_DU, F1AP_UE_CTX, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(f1ap(GNB_DU, GNB_CU, F1AP_UE_CTX, RSP, tmsi, ts=t)); t += 0.05
    pkts.append(e1ap(GNB_CU, GNB_UP, E1AP_BEARER, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(e1ap(GNB_UP, GNB_CU, E1AP_BEARER, RSP, tmsi, ts=t)); t += 0.05
    pkts.append(nas(AMF, UE, NAS_REG_ACCEPT, tmsi, ts=t)); t += 0.05
    pkts.append(nas(UE, AMF, NAS_PDU_REQ, tmsi, ts=t)); t += 0.05
    pkts.append(nas(AMF, UE, NAS_PDU_ACCEPT, tmsi, ts=t)); t += 0.05
    pkts.append(ngap(AMF, src_gnb, NGAP_PDU_SETUP, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(ngap(src_gnb, AMF, NGAP_PDU_SETUP, RSP, tmsi, ts=t)); t += 0.05
    pkts.append(rrc(src_gnb, UE, RRC_RECONF, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(rrc(UE, src_gnb, RRC_RECONF, RSP, tmsi, ts=t))

def attach_fail_rrc(pkts, ue_num, tmsi, t0, src_gnb=GNB1):
    UE = ue_ip(ue_num); t = t0
    pkts.append(rrc(UE, src_gnb, RRC_SETUP, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(rrc(src_gnb, UE, RRC_SETUP, REJ, tmsi, cause=CAUSE_RADIO_INTF, ts=t)); t += 0.05
    # Retry after drop (cascade effect)
    pkts.append(rrc(UE, src_gnb, RRC_SETUP, REQ, tmsi, ts=t+0.5)); t += 0.6
    pkts.append(rrc(src_gnb, UE, RRC_SETUP, REJ, tmsi, cause=CAUSE_PRB_EXHAUST, ts=t))

def attach_fail_auth(pkts, ue_num, tmsi, t0, src_gnb=GNB1):
    UE = ue_ip(ue_num); t = t0
    pkts.append(rrc(UE, src_gnb, RRC_SETUP, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(rrc(src_gnb, UE, RRC_SETUP, RSP, tmsi, ts=t)); t += 0.05
    pkts.append(nas(UE, AMF, NAS_REG_REQ, tmsi, ts=t)); t += 0.05
    pkts.append(ngap(src_gnb, AMF, NGAP_INIT_UE, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(nas(AMF, UE, NAS_AUTH_REQ, tmsi, ts=t)); t += 0.05
    pkts.append(nas(UE, AMF, NAS_AUTH_FAIL, tmsi, cause=CAUSE_AUTH_FAIL, ts=t)); t += 0.05
    pkts.append(nas(AMF, UE, NAS_REG_REJECT, tmsi, cause=CAUSE_CONGESTION, ts=t))

def attach_fail_bearer(pkts, ue_num, tmsi, t0, src_gnb=GNB1):
    UE = ue_ip(ue_num); t = t0
    pkts.append(rrc(UE, src_gnb, RRC_SETUP, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(rrc(src_gnb, UE, RRC_SETUP, RSP, tmsi, ts=t)); t += 0.05
    pkts.append(nas(UE, AMF, NAS_REG_REQ, tmsi, ts=t)); t += 0.05
    pkts.append(ngap(src_gnb, AMF, NGAP_INIT_UE, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(nas(AMF, UE, NAS_AUTH_REQ, tmsi, ts=t)); t += 0.05
    pkts.append(nas(UE, AMF, NAS_AUTH_RSP, tmsi, ts=t)); t += 0.05
    pkts.append(nas(AMF, UE, NAS_SEC_CMD, tmsi, ts=t)); t += 0.05
    pkts.append(nas(UE, AMF, NAS_SEC_COMP, tmsi, ts=t)); t += 0.05
    pkts.append(ngap(AMF, src_gnb, NGAP_INIT_CTX, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(ngap(src_gnb, AMF, NGAP_INIT_CTX, REJ, tmsi, cause=CAUSE_RADIO_LOST, ts=t)); t += 0.05
    pkts.append(e1ap(GNB_CU, GNB_UP, E1AP_BEARER, REQ, tmsi, ts=t)); t += 0.05
    pkts.append(e1ap(GNB_UP, GNB_CU, E1AP_BEARER, REJ, tmsi, cause=CAUSE_UE_CTX_REL, ts=t))

def attach_fail_pdu(pkts, ue_num, tmsi, t0, src_gnb=GNB1):
    UE = ue_ip(ue_num); t = t0
    attach_normal(pkts, ue_num, tmsi, t0, src_gnb)  # normal until PDU
    t = t0 + 1.3
    pkts.append(nas(UE, AMF, NAS_PDU_REQ, tmsi, ts=t)); t += 0.05
    pkts.append(nas(AMF, UE, NAS_PDU_REJECT, tmsi, cause=CAUSE_SEMANTIC_ERR, ts=t))


# ── Xn Handover ───────────────────────────────────────────────────────
def xn_ho_normal(pkts, ue_num, uid, t0):
    UE = ue_ip(ue_num); t = t0
    pkts.append(xnap(GNB1, GNB2, XNAP_HO_REQ, REQ, uid, ts=t)); t += 0.03
    pkts.append(xnap(GNB2, GNB1, XNAP_HO_REQ, RSP, uid, ts=t)); t += 0.03
    pkts.append(rrc(GNB1, UE, RRC_RECONF, REQ, uid, ts=t)); t += 0.05
    pkts.append(rrc(UE, GNB2, RRC_RECONF, RSP, uid, ts=t)); t += 0.03
    pkts.append(xnap(GNB2, GNB1, XNAP_UE_REL, REQ, uid, ts=t)); t += 0.02
    pkts.append(xnap(GNB1, GNB2, XNAP_UE_REL, RSP, uid, ts=t))

def xn_ho_fail(pkts, ue_num, uid, t0, cause=CAUSE_NO_CELLS):
    UE = ue_ip(ue_num); t = t0
    pkts.append(xnap(GNB1, GNB2, XNAP_HO_REQ, REQ, uid, ts=t)); t += 0.03
    pkts.append(xnap(GNB2, GNB1, XNAP_HO_REQ, REJ, uid, cause=cause, ts=t)); t += 0.05
    # RRC reestablishment fallback
    pkts.append(rrc(UE, GNB1, RRC_REESTAB, REQ, uid, cause=CAUSE_RRC_HO_FAIL, ts=t)); t += 0.05
    pkts.append(rrc(GNB1, UE, RRC_REESTAB, RSP, uid, ts=t))


# ── N2 Handover ───────────────────────────────────────────────────────
def n2_ho_normal(pkts, ue_num, uid, t0):
    UE = ue_ip(ue_num); t = t0
    pkts.append(ngap(GNB1, AMF, NGAP_HO_PREP, REQ, uid, ts=t)); t += 0.03
    pkts.append(ngap(AMF, GNB1, NGAP_HO_PREP, RSP, uid, ts=t)); t += 0.03
    pkts.append(rrc(GNB1, UE, RRC_RECONF, REQ, uid, ts=t)); t += 0.05
    pkts.append(rrc(UE, GNB3, RRC_RECONF, RSP, uid, ts=t)); t += 0.03
    pkts.append(ngap(AMF, GNB1, NGAP_UE_REL, REQ, uid, ts=t)); t += 0.02
    pkts.append(ngap(GNB1, AMF, NGAP_UE_REL, RSP, uid, ts=t))

def n2_ho_fail(pkts, ue_num, uid, t0):
    UE = ue_ip(ue_num); t = t0
    pkts.append(ngap(GNB1, AMF, NGAP_HO_PREP, REQ, uid, ts=t)); t += 0.03
    pkts.append(ngap(AMF, GNB1, NGAP_HO_PREP, REJ, uid, cause=CAUSE_NGAP_RES, ts=t)); t += 0.05
    pkts.append(rrc(UE, GNB1, RRC_REESTAB, REQ, uid, cause=CAUSE_RRC_HO_FAIL, ts=t)); t += 0.05
    pkts.append(rrc(GNB1, UE, RRC_REESTAB, RSP, uid, ts=t))


# ── Main ──────────────────────────────────────────────────────────────
def generate(output_path="data/raw/demo_6hr_demo.pcap"):
    pkts = []

    print(f"Base timestamp : {START.isoformat()}")
    print(f"End  timestamp : {NOW.isoformat()}")
    print(f"Generating {N_UE} UE flows across {DURATION_S/3600:.0f} hours...")
    print()

    # UE 1–16 : Attach flows on PCI_1/PCI_2 (gNB1)
    # UE 17–32: Attach flows on PCI_3/PCI_4 (gNB2/gNB3)
    # UE 33–48: Xn handover (PCI_3 target)
    # UE 49–64: N2 handover (PCI_4 target)

    for ue in range(1, N_UE + 1):
        tmsi      = 6000 + ue
        t_offset  = (ue - 1) * STEP_S          # seconds from START
        t_abs     = BASE_TS + t_offset          # absolute UNIX timestamp
        anom_type, anom_cells = _anom_cell(t_offset)

        # ── UE 1-16: Attach on gNB1 (PCI_1/PCI_2) ──────────────────
        if 1 <= ue <= 16:
            src_gnb = GNB1
            if anom_type == "prb_congestion":          # Hour 1.5-2.5
                attach_fail_rrc(pkts, ue, tmsi, t_abs, src_gnb)
            elif anom_type == "rrc_drop_cascade":      # Hour 5.0-5.75
                if ue % 3 == 0:
                    attach_fail_auth(pkts, ue, tmsi, t_abs, src_gnb)
                elif ue % 3 == 1:
                    attach_fail_bearer(pkts, ue, tmsi, t_abs, src_gnb)
                else:
                    attach_normal(pkts, ue, tmsi, t_abs, src_gnb)
            else:
                attach_normal(pkts, ue, tmsi, t_abs, src_gnb)

        # ── UE 17-32: Attach on gNB2/gNB3 (PCI_3/PCI_4) ─────────────
        elif 17 <= ue <= 32:
            src_gnb = GNB2 if ue <= 24 else GNB3
            if anom_type == "snr_degradation":         # Hour 3.0-4.0
                if ue % 2 == 0:
                    attach_fail_bearer(pkts, ue, tmsi, t_abs, src_gnb)
                else:
                    attach_fail_pdu(pkts, ue, tmsi, t_abs, src_gnb)
            elif anom_type == "rrc_drop_cascade":      # Hour 5.0-5.75
                attach_fail_rrc(pkts, ue, tmsi, t_abs, src_gnb)
            else:
                attach_normal(pkts, ue, tmsi, t_abs, src_gnb)

        # ── UE 33-48: Xn Handover (gNB1 → gNB2, PCI_3) ──────────────
        elif 33 <= ue <= 48:
            uid = 7000 + ue
            if anom_type == "snr_degradation":         # SNR → HO failures
                xn_ho_fail(pkts, ue, uid, t_abs,
                            cause=CAUSE_SNR_LOW if ue % 2 == 0 else CAUSE_NO_CELLS)
            elif anom_type == "prb_congestion":        # PRB congestion
                xn_ho_fail(pkts, ue, uid, t_abs, cause=CAUSE_PRB_EXHAUST)
            else:
                xn_ho_normal(pkts, ue, uid, t_abs)

        # ── UE 49-64: N2 Handover (gNB1 → gNB3, PCI_4) ──────────────
        else:
            uid = 7000 + ue
            if anom_type == "rrc_drop_cascade":        # RRC cascade
                n2_ho_fail(pkts, ue, uid, t_abs)
            elif anom_type == "snr_degradation":       # SNR → N2 fail
                n2_ho_fail(pkts, ue, uid, t_abs)
            else:
                n2_ho_normal(pkts, ue, uid, t_abs)

    # Sort by timestamp (scapy wrpcap expects ordered packets)
    pkts.sort(key=lambda p: float(p.time))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wrpcap(str(out), pkts)

    # Count failures
    n_fail = sum(1 for p in pkts
                 if len(p[Raw].load) >= 3 and p[Raw].load[2] == REJ)

    print(f"  ✅ Written : {out}")
    print(f"  Packets   : {len(pkts):,}")
    print(f"  Failures  : {n_fail} rejection packets")
    print(f"  Time span : {START.strftime('%Y-%m-%d %H:%M')} → {NOW.strftime('%H:%M')}")
    print()
    print("  Anomaly windows:")
    for label, window, cells in [
        ("PRB_CONGESTION",   ANOM_A, "PCI_2"),
        ("SNR_DEGRADATION",  ANOM_B, "PCI_3"),
        ("RRC_DROP_CASCADE", ANOM_C, "PCI_1, PCI_4"),
    ]:
        ts_s = START + timedelta(seconds=window[0])
        ts_e = START + timedelta(seconds=window[1])
        print(f"    • {label:22s} [{ts_s.strftime('%H:%M')} → {ts_e.strftime('%H:%M')}]  {cells}")
    print()
    print("  Upload to PCAP Analysis tab in dashboard.")
    print("  Correlates with demo_6hr_kpi.csv + demo_6hr_stats.csv")


if __name__ == "__main__":
    generate()
