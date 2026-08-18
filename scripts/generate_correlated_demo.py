"""
Generate a matched KPI + Stats demo pair that will produce a cross-source
correlated event when both are uploaded in the same dashboard session.

WHY: EventRouter correlates on cell_id within a 1-hour window
(src/orchestrator/event_router.py). KPI anomalies carry their own data
timestamp; Stats anomalies have no timestamp field and fall back to
ingestion time. So the shared bad cell's KPI anomaly must land near
"now" (script run time) for the two sources to fall inside that window
regardless of exactly when each file is uploaded.

Outputs:
  data/raw/demo_kpi_correlated.csv    (KPI format, Cell_ID column)
  data/raw/demo_stats_correlated.csv  (srsRAN stats format, pci column)

Both flag cell PCI_2 as degrading; PCI_1/3/4 stay healthy so Peer
Comparison has a clean baseline to compare against.

Usage: python scripts/generate_correlated_demo.py
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

rng = np.random.default_rng(7)

CELLS    = ["PCI_1", "PCI_2", "PCI_3", "PCI_4"]
GNBS     = {"PCI_1": "gNB-1", "PCI_2": "gNB-1", "PCI_3": "gNB-2", "PCI_4": "gNB-2"}
BAD_CELL = "PCI_2"

NOW = datetime.now().replace(microsecond=0)


def _ramp(frac_bad: float, healthy: float, critical: float) -> float:
    """0 -> healthy, 1 -> critical, linear in between."""
    return healthy + (critical - healthy) * frac_bad


# ── KPI file: 4 hours @ 5-min steps, ending at NOW ─────────────────────
def gen_kpi() -> pd.DataFrame:
    n = 49  # 4 hours / 5 min + 1
    start = NOW - timedelta(minutes=5 * (n - 1))
    rows = []
    for i in range(n):
        ts = start + timedelta(minutes=5 * i)
        # PCI_2 stays healthy for first half, then ramps to critical
        frac = max(0.0, (i - n // 2) / (n - 1 - n // 2)) if i > n // 2 else 0.0
        for cell in CELLS:
            bad = (cell == BAD_CELL)
            f = frac if bad else 0.0
            rows.append({
                "Timestamp":                    ts.isoformat(),
                "Cell_ID":                       cell,
                "gNB_ID":                        GNBS[cell],
                "Cell_Availability_%":           round(_ramp(f, 99.9, 92.0) + rng.normal(0, 0.05), 3),
                "RRC_Connection_Attempts":       int(rng.integers(260, 320)),
                "RRC_Connection_Rejects":        int(rng.integers(0, 2) if not bad else _ramp(f, 1, 25)),
                "RRC_Success_Rate_%":            round(_ramp(f, 99.9, 92.5) + rng.normal(0, 0.05), 3),
                "Avg_RRC_Connected_Users":       round(float(rng.uniform(60, 80)), 1),
                "Peak_RRC_Connected_Users":      round(float(rng.uniform(80, 95)), 1),
                "Registration_Success_Rate_%":   round(_ramp(f, 99.6, 92.0) + rng.normal(0, 0.05), 3),
                "PDU_Session_Success_Rate_%":    round(_ramp(f, 99.3, 92.5) + rng.normal(0, 0.05), 3),
                "RRC_Drop_Rate_%":               round(_ramp(f, 0.15, 6.5) + rng.normal(0, 0.02), 3),
                "Handover_Attempts":             int(rng.integers(18, 32)),
                "Handover_Success_Rate_%":       round(_ramp(f, 98.4, 90.0) + rng.normal(0, 0.1), 3),
                "Xn_HO_Prep_Success_Rate_%":     round(_ramp(f, 98.9, 91.0) + rng.normal(0, 0.1), 3),
                "Xn_HO_Exec_Success_Rate_%":     round(_ramp(f, 98.8, 91.0) + rng.normal(0, 0.1), 3),
                "NG_HO_Prep_Success_Rate_%":     round(_ramp(f, 98.4, 91.0) + rng.normal(0, 0.1), 3),
                "NG_HO_Exec_Success_Rate_%":     round(_ramp(f, 98.0, 91.0) + rng.normal(0, 0.1), 3),
                "PRB_Utilization_DL_%":          round(_ramp(f, 35.0, 96.0) + rng.normal(0, 0.5), 2),
                "PRB_Utilization_UL_%":          round(_ramp(f, 30.0, 90.0) + rng.normal(0, 0.5), 2),
                "DL_Throughput_Mbps":            round(_ramp(f, 190.0, 12.0) + rng.normal(0, 1), 2),
                "UL_Throughput_Mbps":            round(_ramp(f, 70.0, 6.0) + rng.normal(0, 1), 2),
                "Total_Traffic_GB":              round(float(rng.uniform(1.7, 2.1)), 5),
                "RACH_Success_Rate_%":           round(_ramp(f, 99.1, 90.0) + rng.normal(0, 0.1), 3),
                "Latency_ms":                    round(_ramp(f, 7.0, 55.0) + rng.normal(0, 0.3), 2),
            })
    return pd.DataFrame(rows)


# ── Stats file: 2 hours @ 1-min steps, ending at NOW (srsRAN format) ──
def gen_stats() -> pd.DataFrame:
    n = 121  # 2 hours / 1 min + 1
    start = NOW - timedelta(minutes=n - 1)
    rows = []
    for i in range(n):
        ts = start + timedelta(minutes=i)
        frac = max(0.0, (i - n // 2) / (n - 1 - n // 2)) if i > n // 2 else 0.0
        for cell in CELLS:
            bad = (cell == BAD_CELL)
            f = frac if bad else 0.0
            dl_prb  = int(round(_ramp(f, 35, 100)))
            ul_prb  = int(round(_ramp(f, 28, 92)))
            dl_ok   = int(rng.integers(900, 1200))
            dl_nok  = int(round(_ramp(f, 15, 260))) + int(rng.integers(0, 10))
            ul_ok   = int(rng.integers(700, 1000))
            ul_nok  = int(round(_ramp(f, 10, 200))) + int(rng.integers(0, 8))
            rows.append({
                "timestamp":     ts.isoformat(),
                "pci":           cell,
                "cell_type":     "TDD",
                "nof_ue":        int(rng.integers(1, 25)),
                "dl_brate":      round(float(_ramp(f, 55e6, 3e6) + rng.normal(0, 1e6)), 0),
                "ul_brate":      round(float(_ramp(f, 22e6, 1.5e6) + rng.normal(0, 0.5e6)), 0),
                "dl_nof_ok":     dl_ok,
                "dl_nof_nok":    dl_nok,
                "ul_nof_ok":     ul_ok,
                "ul_nof_nok":    ul_nok,
                "dl_mcs":        round(_ramp(f, 14.0, 2.5), 1),
                "ul_mcs":        round(_ramp(f, 13.0, 2.0), 1),
                "dl_prb":        dl_prb,
                "ul_prb":        ul_prb,
                "pusch_snr_db":  round(_ramp(f, 18.0, -3.0) + rng.normal(0, 0.3), 2),
                "pucch_snr_db":  round(_ramp(f, 20.0, -1.0) + rng.normal(0, 0.3), 2),
                "anomaly_label": "Anomaly" if f > 0.3 else "Normal",
            })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out = Path("data/raw")
    out.mkdir(parents=True, exist_ok=True)

    kpi_df = gen_kpi()
    kpi_path = out / "demo_kpi_correlated.csv"
    kpi_df.to_csv(kpi_path, index=False)

    stats_df = gen_stats()
    stats_path = out / "demo_stats_correlated.csv"
    stats_df.to_csv(stats_path, index=False)

    print(f"Wrote {len(kpi_df)} rows -> {kpi_path}")
    print(f"Wrote {len(stats_df)} rows -> {stats_path}")
    print(f"Shared degrading cell: {BAD_CELL}  (anchor time: {NOW.isoformat()})")
    print("Upload both in the SAME dashboard session (KPI tab, then Stats tab)")
    print("within about an hour of generating this data to trigger correlation.")
