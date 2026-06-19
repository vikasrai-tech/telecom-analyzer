"""
64-UE / 6-Hour DU/CU Stats Generator (srsRAN format)
=====================================================
Generates a 1-minute-granularity DU stats CSV (+ Parquet) covering the same
6-hour window (08:00-14:00) and 16-cell / 64-UE topology as
generate_64ue_kpi.py, so the two datasets can be cross-correlated by
(cell/pci, time).

8 cells are TDD (DL capacity 1500 Mbps / UL 100 Mbps), 8 cells are FDD
(DL capacity 100 Mbps / UL 50 Mbps) — see scripts/_ue64_config.py.

Same 3 injected-anomaly windows as the KPI generator:
  PCI_3   09:30-10:30  Congestion  -> BLER spike, MCS drop, PRB > 95% (TDD)
  PCI_12  12:00-12:20  Outage      -> throughput/PRB collapse, SNR crash (FDD)
  PCI_8   13:00-14:00  Slow drift  -> SNR/MCS degrade gradually (TDD)
"""

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from _ue64_config import (
    START, N_MINUTES, CELLS, CAPACITY, UE_PER_CELL,
    ANOM_CONGESTION, ANOM_OUTAGE, ANOM_DRIFT, diurnal_factor,
)

rng = np.random.default_rng(23)


def clip(x, lo, hi):
    return float(np.clip(x, lo, hi))


def gen_row(cell, ctype, minute, ts):
    load = diurnal_factor(minute)
    cap  = CAPACITY[ctype]

    congestion = (cell == ANOM_CONGESTION["cell"] and ANOM_CONGESTION["start"] <= minute < ANOM_CONGESTION["end"])
    outage     = (cell == ANOM_OUTAGE["cell"]     and ANOM_OUTAGE["start"]     <= minute < ANOM_OUTAGE["end"])
    drift_frac = 0.0
    if cell == ANOM_DRIFT["cell"] and minute >= ANOM_DRIFT["start"]:
        drift_frac = (minute - ANOM_DRIFT["start"]) / (ANOM_DRIFT["end"] - ANOM_DRIFT["start"])

    bad = congestion or outage or drift_frac > 0.5

    nof_ue = max(0, int(rng.normal(UE_PER_CELL * (0.4 + 0.6 * load), 0.5)))

    # ── Throughput (Mbps -> bps), scaled to TDD/FDD channel capacity ────
    dl_mbps = max(0.5, rng.normal(cap["dl"] * (0.05 + 0.65 * load), cap["dl"] * 0.05))
    ul_mbps = max(0.5, rng.normal(cap["ul"] * (0.05 + 0.65 * load), cap["ul"] * 0.05))
    if congestion:
        dl_mbps *= rng.uniform(0.20, 0.35)
        ul_mbps *= rng.uniform(0.25, 0.40)
    if outage:
        dl_mbps = max(0.0, rng.normal(cap["dl"] * 0.01, cap["dl"] * 0.005))
        ul_mbps = max(0.0, rng.normal(cap["ul"] * 0.01, cap["ul"] * 0.005))
    if drift_frac > 0:
        dl_mbps *= (1.0 - 0.4 * drift_frac)
        ul_mbps *= (1.0 - 0.3 * drift_frac)

    # ── PRB utilization ──────────────────────────────────────────────
    dl_prb = clip(rng.normal(20 + 55 * load, 4), 0, 100)
    ul_prb = clip(rng.normal(15 + 45 * load, 4), 0, 100)
    if congestion:
        dl_prb = clip(dl_prb + rng.uniform(20, 30), 0, 100)
        ul_prb = clip(ul_prb + rng.uniform(15, 25), 0, 100)
    if outage:
        dl_prb = clip(rng.uniform(0, 5), 0, 100)
        ul_prb = clip(rng.uniform(0, 5), 0, 100)

    # ── Scheduling block counts (BLER source) ───────────────────────
    dl_total = int(rng.integers(900, 1200))
    ul_total = int(rng.integers(700, 1000))
    if bad:
        dl_nok = int(rng.integers(80, 250))
        ul_nok = int(rng.integers(60, 180))
    else:
        dl_nok = int(rng.integers(5, 40))
        ul_nok = int(rng.integers(3, 30))
    dl_ok = max(0, dl_total - dl_nok)
    ul_ok = max(0, ul_total - ul_nok)

    # ── MCS ──────────────────────────────────────────────────────────
    if bad:
        dl_mcs = int(rng.integers(2, 8))
        ul_mcs = int(rng.integers(2, 8))
    else:
        dl_mcs = int(rng.integers(8, 16))
        ul_mcs = int(rng.integers(8, 16))
    if drift_frac > 0:
        dl_mcs = max(1, int(dl_mcs - 6 * drift_frac))
        ul_mcs = max(1, int(ul_mcs - 6 * drift_frac))

    # ── SNR ──────────────────────────────────────────────────────────
    if outage:
        pusch_snr = rng.uniform(-8, -2)
        pucch_snr = rng.uniform(-6, 0)
    elif congestion:
        pusch_snr = rng.uniform(-5, 8)
        pucch_snr = rng.uniform(-3, 10)
    else:
        pusch_snr = rng.uniform(5, 25)
        pucch_snr = rng.uniform(8, 28)
    if drift_frac > 0:
        pusch_snr -= 10.0 * drift_frac
        pucch_snr -= 8.0 * drift_frac

    return {
        "timestamp":    ts.isoformat(),
        "pci":          cell,
        "nof_ue":       nof_ue,
        "dl_brate":     round(dl_mbps * 1e6, 0),
        "ul_brate":     round(ul_mbps * 1e6, 0),
        "dl_nof_ok":    dl_ok,
        "dl_nof_nok":   dl_nok,
        "ul_nof_ok":    ul_ok,
        "ul_nof_nok":   ul_nok,
        "dl_mcs":       dl_mcs,
        "ul_mcs":       ul_mcs,
        "dl_prb":       round(dl_prb, 0),
        "ul_prb":       round(ul_prb, 0),
        "pusch_snr_db": round(float(pusch_snr), 2),
        "pucch_snr_db": round(float(pucch_snr), 2),
    }


def generate(output_path: str = "data/raw/stats_64ue_6hr.csv"):
    rows = []
    for minute in range(N_MINUTES):
        ts = START + timedelta(minutes=minute)
        for cell, gnb, ctype in CELLS:
            rows.append(gen_row(cell, ctype, minute, ts))

    df = pd.DataFrame(rows)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    df.to_parquet(out.with_suffix(".parquet"), index=False)

    print("=" * 60)
    print("  64-UE / 6-Hour DU Stats Sample (srsRAN format) — 1-min granularity")
    print(f"  Window  : {START} -> {START + timedelta(minutes=N_MINUTES - 1)}")
    print(f"  Cells   : {len(CELLS)} (8 TDD: PCI_1-8, 8 FDD: PCI_9-16), 4 UE/cell = 64 UEs")
    print(f"  Rows    : {len(df)}  ({N_MINUTES} timestamps x {len(CELLS)} cells)")
    print(f"  Columns : {len(df.columns)}")
    print(f"  Written : {out}  ({out.stat().st_size / 1024:.1f} KB)")
    print(f"  Written : {out.with_suffix('.parquet')}")
    print("=" * 60)
    print("""
INJECTED ANOMALIES (shared with KPI dataset for cross-source correlation):
  PCI_3   09:30-10:30  Congestion  -> BLER spike, MCS drop, PRB > 95% (TDD)
  PCI_12  12:00-12:20  Outage      -> throughput/PRB collapse, SNR crash (FDD)
  PCI_8   13:00-14:00  Slow drift  -> SNR/MCS degrade gradually (TDD)

TO VALIDATE:
  python -m src.orchestrator.pipeline \\
    --input data/raw/stats_64ue_6hr.csv --no-llm
""")


if __name__ == "__main__":
    generate()
