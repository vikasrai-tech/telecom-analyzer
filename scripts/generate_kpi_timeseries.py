"""
10-Hour Network KPI Sample Generator — realistic gNB KPI export
=================================================================
Generates a 1-minute-granularity KPI CSV covering a 10-hour business-day
window (08:00-18:00) across 10 cells / 3 gNBs.

KPIs included (canonical names from src/parsers/kpi_defs.py):
  Availability   - Cell_Availability_%
  Accessibility  - RRC_Connection_Attempts, RRC_Connection_Rejects,
                    RRC_Success_Rate_%, Avg_RRC_Connected_Users,
                    Peak_RRC_Connected_Users, Registration_Success_Rate_%,
                    PDU_Session_Success_Rate_%
  Retainability  - RRC_Drop_Rate_%
  Mobility       - Handover_Success_Rate_%, Xn_HO_Prep_Success_Rate_%,
                    Xn_HO_Exec_Success_Rate_%, NG_HO_Prep_Success_Rate_%,
                    NG_HO_Exec_Success_Rate_%, Handover_Attempts
  Capacity       - PRB_Utilization_DL_%, PRB_Utilization_UL_%
  Throughput     - DL_Throughput_Mbps, UL_Throughput_Mbps, Total_Traffic_GB
  RACH           - RACH_Success_Rate_%
  Quality        - Latency_ms

Traffic follows a diurnal busy-hour curve (peaks ~13:00) and every KPI
that depends on load (throughput, PRB, connected users, HO attempts)
scales with it, plus per-minute noise.

Injected anomalies (for detector validation):
  PCI_5  (gNB-2) 12:30-13:30  Congestion: HO success rate, RRC success
                               rate and throughput crash; PRB > 95%
                               (threshold / Bollinger-band style spike)
  PCI_8  (gNB-3) 15:00-15:20  Hardware/backhaul outage: availability,
                               throughput, RACH success rate all collapse
                               (sharp step-change anomaly)
  PCI_2  (gNB-1) 16:00-18:00  Gradual degradation: handover success rate
                               and latency drift steadily worse
                               (trend / CUSUM-style slow drift)
"""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(7)

START      = datetime(2026, 6, 10, 8, 0, 0)
N_MINUTES  = 600   # 10 hours @ 1-minute granularity

CELLS = [
    ("PCI_1", "gNB-1"), ("PCI_2", "gNB-1"), ("PCI_3", "gNB-1"), ("PCI_4", "gNB-1"),
    ("PCI_5", "gNB-2"), ("PCI_6", "gNB-2"), ("PCI_7", "gNB-2"),
    ("PCI_8", "gNB-3"), ("PCI_9", "gNB-3"), ("PCI_10", "gNB-3"),
]


def diurnal_factor(minute: int) -> float:
    """Busy-hour curve over the 10-hour window, peaking around 13:00."""
    hour = 8 + minute / 60.0
    return 0.30 + 0.70 * np.sin(np.pi * (hour - 8) / 10.0) ** 1.3


def clip(x, lo, hi):
    return float(np.clip(x, lo, hi))


def gen_row(cell, gnb, minute, ts):
    load = diurnal_factor(minute)

    # ── Anomaly windows ────────────────────────────────────────────
    congestion = (cell == "PCI_5" and 270 <= minute < 330)   # 12:30-13:30
    outage     = (cell == "PCI_8" and 420 <= minute < 440)   # 15:00-15:20
    drift_frac = 0.0
    if cell == "PCI_2" and minute >= 480:                    # 16:00-18:00
        drift_frac = (minute - 480) / 120.0                  # 0 -> 1

    # ── Accessibility ──────────────────────────────────────────────
    rrc_attempts = max(1, int(rng.normal(120 + 600 * load, 15)))
    reject_rate  = rng.uniform(0.0005, 0.003)
    if congestion:
        reject_rate = rng.uniform(0.08, 0.15)
    rrc_rejects  = int(rrc_attempts * reject_rate)
    rrc_sr       = clip(100.0 * (1 - rrc_rejects / rrc_attempts), 0, 100)

    avg_users  = max(1, rng.normal(20 + 180 * load, 8))
    peak_users = avg_users * rng.uniform(1.15, 1.4)

    reg_sr = clip(rng.normal(99.6, 0.15), 90, 100)
    pdu_sr = clip(rng.normal(99.4, 0.2),  90, 100)
    if congestion:
        reg_sr = clip(reg_sr - rng.uniform(5, 9), 70, 100)
        pdu_sr = clip(pdu_sr - rng.uniform(6, 10), 70, 100)

    # ── Retainability ─────────────────────────────────────────────
    rrc_drop = clip(rng.normal(0.15, 0.07), 0, 100)
    if congestion:
        rrc_drop = clip(rrc_drop + rng.uniform(3, 5), 0, 100)
    if outage:
        rrc_drop = clip(rrc_drop + rng.uniform(20, 30), 0, 100)

    # ── Mobility (handover) ─────────────────────────────────────────
    ho_attempts = max(0, int(rng.normal(avg_users * 0.35, 3)))
    ho_sr     = clip(rng.normal(98.5, 0.3), 0, 100)
    xn_prep   = clip(rng.normal(99.0, 0.25), 0, 100)
    xn_exec   = clip(rng.normal(98.7, 0.3), 0, 100)
    ng_prep   = clip(rng.normal(98.3, 0.3), 0, 100)
    ng_exec   = clip(rng.normal(98.0, 0.35), 0, 100)
    if congestion:
        ho_sr   = clip(ho_sr - rng.uniform(12, 18), 0, 100)
        xn_prep = clip(xn_prep - rng.uniform(10, 16), 0, 100)
        xn_exec = clip(xn_exec - rng.uniform(10, 16), 0, 100)
    if outage:
        ho_sr   = clip(ho_sr - rng.uniform(40, 60), 0, 100)
        ng_prep = clip(ng_prep - rng.uniform(40, 60), 0, 100)
        ng_exec = clip(ng_exec - rng.uniform(40, 60), 0, 100)
    if drift_frac > 0:
        # slow drift: lose up to 15 points of HO success rate by 18:00
        ho_sr = clip(ho_sr - 15.0 * drift_frac, 0, 100)
        xn_exec = clip(xn_exec - 8.0 * drift_frac, 0, 100)

    # ── Capacity / Throughput ────────────────────────────────────────
    prb_dl = clip(rng.normal(20 + 55 * load, 4), 0, 100)
    prb_ul = clip(rng.normal(15 + 45 * load, 4), 0, 100)

    dl_tput = max(0.5, rng.normal(50 + 420 * load, 25))
    ul_tput = max(0.5, rng.normal(40 + 120 * load, 8))

    if congestion:
        prb_dl  = clip(prb_dl + rng.uniform(20, 30), 0, 100)
        prb_ul  = clip(prb_ul + rng.uniform(15, 25), 0, 100)
        dl_tput = dl_tput * rng.uniform(0.20, 0.35)
        ul_tput = ul_tput * rng.uniform(0.25, 0.40)
    if outage:
        prb_dl  = clip(rng.uniform(0, 5), 0, 100)
        prb_ul  = clip(rng.uniform(0, 5), 0, 100)
        dl_tput = max(0.0, rng.normal(2, 1))
        ul_tput = max(0.0, rng.normal(0.5, 0.3))

    # Per-minute traffic volume (Mbps -> GB over 60s)
    total_gb = (dl_tput + ul_tput) * 60.0 / 8000.0

    # ── RACH ──────────────────────────────────────────────────────
    rach_sr = clip(rng.normal(99.2, 0.25), 0, 100)
    if outage:
        rach_sr = clip(rach_sr - rng.uniform(25, 40), 0, 100)

    # ── Latency ──────────────────────────────────────────────────
    latency = max(1.0, rng.normal(8 + 6 * load, 1.5))
    if congestion:
        latency += rng.uniform(15, 25)
    if drift_frac > 0:
        latency += 25.0 * drift_frac   # creeping latency degradation

    # ── Availability ────────────────────────────────────────────────
    avail = clip(rng.normal(99.97, 0.03), 0, 100)
    if outage:
        avail = clip(rng.uniform(55, 75), 0, 100)

    return {
        "Timestamp":                   ts.isoformat(),
        "Cell_ID":                     cell,
        "gNB_ID":                      gnb,
        "Cell_Availability_%":         round(avail, 3),
        "RRC_Connection_Attempts":     rrc_attempts,
        "RRC_Connection_Rejects":      rrc_rejects,
        "RRC_Success_Rate_%":          round(rrc_sr, 3),
        "Avg_RRC_Connected_Users":     round(avg_users, 1),
        "Peak_RRC_Connected_Users":    round(peak_users, 1),
        "Registration_Success_Rate_%": round(reg_sr, 3),
        "PDU_Session_Success_Rate_%":  round(pdu_sr, 3),
        "RRC_Drop_Rate_%":             round(rrc_drop, 3),
        "Handover_Attempts":           ho_attempts,
        "Handover_Success_Rate_%":     round(ho_sr, 3),
        "Xn_HO_Prep_Success_Rate_%":   round(xn_prep, 3),
        "Xn_HO_Exec_Success_Rate_%":   round(xn_exec, 3),
        "NG_HO_Prep_Success_Rate_%":   round(ng_prep, 3),
        "NG_HO_Exec_Success_Rate_%":   round(ng_exec, 3),
        "PRB_Utilization_DL_%":        round(prb_dl, 2),
        "PRB_Utilization_UL_%":        round(prb_ul, 2),
        "DL_Throughput_Mbps":          round(dl_tput, 2),
        "UL_Throughput_Mbps":          round(ul_tput, 2),
        "Total_Traffic_GB":            round(total_gb, 5),
        "RACH_Success_Rate_%":         round(rach_sr, 3),
        "Latency_ms":                  round(latency, 2),
    }


def generate(output_path: str = "data/raw/kpi_10hr_sample.csv"):
    rows = []
    for minute in range(N_MINUTES):
        ts = START + timedelta(minutes=minute)
        for cell, gnb in CELLS:
            rows.append(gen_row(cell, gnb, minute, ts))

    df = pd.DataFrame(rows)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    print("=" * 60)
    print("  10-Hour Network KPI Sample — 1-min granularity")
    print(f"  Window  : {START} -> {START + timedelta(minutes=N_MINUTES-1)}")
    print(f"  Cells   : {len(CELLS)}  ({', '.join(c for c, _ in CELLS)})")
    print(f"  Rows    : {len(df)}  ({N_MINUTES} timestamps x {len(CELLS)} cells)")
    print(f"  Columns : {len(df.columns)}")
    print(f"  Written : {out}  ({out.stat().st_size / 1024:.1f} KB)")
    print("=" * 60)
    print("""
INJECTED ANOMALIES (for detector validation):
  PCI_5  12:30-13:30  Congestion  -> HO/RRC success crash, PRB > 95%
  PCI_8  15:00-15:20  Outage      -> availability/throughput/RACH collapse
  PCI_2  16:00-18:00  Slow drift  -> HO success & latency degrade gradually

TO VALIDATE:
  python -m src.orchestrator.pipeline \\
    --input data/raw/kpi_10hr_sample.csv --no-llm
""")


if __name__ == "__main__":
    generate()
