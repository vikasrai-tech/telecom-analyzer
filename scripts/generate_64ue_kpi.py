"""
64-UE / 6-Hour Network KPI Sample Generator
============================================
Generates a 1-minute-granularity KPI CSV covering a 6-hour window
(08:00-14:00) across 16 cells / 4 gNBs (4 UE/cell, 64 UEs total).

8 cells are TDD (DL capacity 1500 Mbps / UL 100 Mbps), 8 cells are FDD
(DL capacity 100 Mbps / UL 50 Mbps) — see scripts/_ue64_config.py.

Traffic follows a busy-period curve (peaks ~11:00) and every KPI that
depends on load (throughput, PRB, connected users, HO attempts) scales
with it, plus per-minute noise.

Injected anomalies (shared with generate_64ue_stats.py for cross-source
correlation):
  PCI_3  (gNB-1, TDD) 09:30-10:30  Congestion: HO/RRC success rate and
                                    throughput crash; PRB > 95%
  PCI_12 (gNB-3, FDD) 12:00-12:20  Hardware/backhaul outage: availability,
                                    throughput, RACH success rate collapse
  PCI_8  (gNB-2, TDD) 13:00-14:00  Gradual degradation: handover success
                                    rate and latency drift steadily worse
"""

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from _ue64_config import (
    START, N_MINUTES, CELLS, CAPACITY, UE_PER_CELL,
    ANOM_CONGESTION, ANOM_OUTAGE, ANOM_DRIFT, diurnal_factor,
)

rng = np.random.default_rng(11)


def clip(x, lo, hi):
    return float(np.clip(x, lo, hi))


def gen_row(cell, gnb, ctype, minute, ts):
    load = diurnal_factor(minute)
    cap  = CAPACITY[ctype]

    # ── Anomaly windows ────────────────────────────────────────────
    congestion = (cell == ANOM_CONGESTION["cell"] and ANOM_CONGESTION["start"] <= minute < ANOM_CONGESTION["end"])
    outage     = (cell == ANOM_OUTAGE["cell"]     and ANOM_OUTAGE["start"]     <= minute < ANOM_OUTAGE["end"])
    drift_frac = 0.0
    if cell == ANOM_DRIFT["cell"] and minute >= ANOM_DRIFT["start"]:
        drift_frac = (minute - ANOM_DRIFT["start"]) / (ANOM_DRIFT["end"] - ANOM_DRIFT["start"])

    # ── Accessibility ──────────────────────────────────────────────
    base_attempts = UE_PER_CELL * (8 + 22 * load)
    rrc_attempts = max(1, int(rng.normal(base_attempts, base_attempts * 0.1)))
    reject_rate  = rng.uniform(0.0005, 0.003)
    if congestion:
        reject_rate = rng.uniform(0.08, 0.15)
    rrc_rejects  = int(rrc_attempts * reject_rate)
    rrc_sr       = clip(100.0 * (1 - rrc_rejects / rrc_attempts), 0, 100)

    avg_users  = max(1, rng.normal(UE_PER_CELL * (0.4 + 0.6 * load), 0.4))
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
    ho_attempts = max(0, int(rng.normal(avg_users * 0.35, 0.5)))
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
        ho_sr   = clip(ho_sr - 15.0 * drift_frac, 0, 100)
        xn_exec = clip(xn_exec - 8.0 * drift_frac, 0, 100)

    # ── Capacity / Throughput (scaled to TDD/FDD channel capacity) ──
    dl_tput = max(0.5, rng.normal(cap["dl"] * (0.05 + 0.65 * load), cap["dl"] * 0.05))
    ul_tput = max(0.5, rng.normal(cap["ul"] * (0.05 + 0.65 * load), cap["ul"] * 0.05))

    prb_dl = clip(rng.normal(20 + 55 * load, 4), 0, 100)
    prb_ul = clip(rng.normal(15 + 45 * load, 4), 0, 100)

    if congestion:
        prb_dl  = clip(prb_dl + rng.uniform(20, 30), 0, 100)
        prb_ul  = clip(prb_ul + rng.uniform(15, 25), 0, 100)
        dl_tput = dl_tput * rng.uniform(0.20, 0.35)
        ul_tput = ul_tput * rng.uniform(0.25, 0.40)
    if outage:
        prb_dl  = clip(rng.uniform(0, 5), 0, 100)
        prb_ul  = clip(rng.uniform(0, 5), 0, 100)
        dl_tput = max(0.0, rng.normal(cap["dl"] * 0.01, cap["dl"] * 0.005))
        ul_tput = max(0.0, rng.normal(cap["ul"] * 0.01, cap["ul"] * 0.005))

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
        latency += 25.0 * drift_frac

    # ── Availability ────────────────────────────────────────────────
    avail = clip(rng.normal(99.97, 0.03), 0, 100)
    if outage:
        avail = clip(rng.uniform(55, 75), 0, 100)

    return {
        "Timestamp":                   ts.isoformat(),
        "Cell_ID":                     cell,
        "gNB_ID":                      gnb,
        "Channel_Type":                ctype,
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


def generate(output_path: str = "data/raw/kpi_64ue_6hr.csv"):
    rows = []
    for minute in range(N_MINUTES):
        ts = START + timedelta(minutes=minute)
        for cell, gnb, ctype in CELLS:
            rows.append(gen_row(cell, gnb, ctype, minute, ts))

    df = pd.DataFrame(rows)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    print("=" * 60)
    print("  64-UE / 6-Hour Network KPI Sample — 1-min granularity")
    print(f"  Window  : {START} -> {START + timedelta(minutes=N_MINUTES - 1)}")
    print(f"  Cells   : {len(CELLS)} (8 TDD: PCI_1-8, 8 FDD: PCI_9-16), 4 UE/cell = 64 UEs")
    print(f"  Rows    : {len(df)}  ({N_MINUTES} timestamps x {len(CELLS)} cells)")
    print(f"  Columns : {len(df.columns)}")
    print(f"  Written : {out}  ({out.stat().st_size / 1024:.1f} KB)")
    print("=" * 60)
    print("""
INJECTED ANOMALIES (for detector validation, shared with stats dataset):
  PCI_3   09:30-10:30  Congestion  -> HO/RRC success crash, PRB > 95% (TDD)
  PCI_12  12:00-12:20  Outage      -> availability/throughput/RACH collapse (FDD)
  PCI_8   13:00-14:00  Slow drift  -> HO success & latency degrade gradually (TDD)

TO VALIDATE:
  python -m src.orchestrator.pipeline \\
    --input data/raw/kpi_64ue_6hr.csv --no-llm
""")


if __name__ == "__main__":
    generate()
