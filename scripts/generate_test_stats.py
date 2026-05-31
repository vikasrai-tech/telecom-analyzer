"""
Generate synthetic DU/CU Stats CSV in srsRAN / OAI / NIST formats
for testing the Stats Parser.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

rng = np.random.default_rng(42)

CELLS  = ["PCI_1", "PCI_2", "PCI_3", "PCI_4"]
N_ROWS = 240   # 4 hours × 1-min intervals


def _timestamps(n):
    base = datetime(2024, 6, 1, 0, 0, 0)
    return [base + timedelta(minutes=i) for i in range(n)]


# ── srsRAN format ─────────────────────────────────────────────────────
def gen_srsran():
    rows = []
    ts = _timestamps(N_ROWS)
    for t in ts:
        for pci in CELLS:
            # inject anomalies in PCI_3 after t=120
            bad = (pci == "PCI_3" and t.minute >= 120)
            dl_ok   = int(rng.integers(900, 1200))
            dl_nok  = int(rng.integers(80, 250) if bad else rng.integers(5, 40))
            ul_ok   = int(rng.integers(700, 1000))
            ul_nok  = int(rng.integers(60, 180) if bad else rng.integers(3, 30))
            dl_prb  = int(rng.integers(75, 95) if bad else rng.integers(20, 65))
            ul_prb  = int(rng.integers(60, 85) if bad else rng.integers(15, 55))
            rows.append({
                "timestamp":    t.isoformat(),
                "pci":          pci,
                "nof_ue":       int(rng.integers(5, 30)),
                "dl_brate":     round(float(rng.uniform(10e6, 80e6) if not bad else rng.uniform(2e6, 15e6)), 0),
                "ul_brate":     round(float(rng.uniform(5e6,  40e6) if not bad else rng.uniform(1e6,  8e6)),  0),
                "dl_nof_ok":    dl_ok,
                "dl_nof_nok":   dl_nok,
                "ul_nof_ok":    ul_ok,
                "ul_nof_nok":   ul_nok,
                "dl_mcs":       int(rng.integers(8, 16) if not bad else rng.integers(2, 8)),
                "ul_mcs":       int(rng.integers(8, 16) if not bad else rng.integers(2, 8)),
                "dl_prb":       dl_prb,
                "ul_prb":       ul_prb,
                "pusch_snr_db": round(float(rng.uniform(5, 25) if not bad else rng.uniform(-5, 8)), 2),
                "pucch_snr_db": round(float(rng.uniform(8, 28) if not bad else rng.uniform(-3, 10)), 2),
            })
    return pd.DataFrame(rows)


# ── OAI format ────────────────────────────────────────────────────────
def gen_oai():
    rows = []
    ts = _timestamps(N_ROWS)
    for t in ts:
        for cell in CELLS:
            bad = (cell == "PCI_2" and t.minute >= 60 and t.minute < 180)
            dlsch_total  = int(rng.integers(1000, 1500))
            dlsch_errors = int(rng.integers(100, 300) if bad else rng.integers(5, 50))
            ulsch_total  = int(rng.integers(800, 1200))
            ulsch_errors = int(rng.integers(80, 200) if bad else rng.integers(3, 40))
            rows.append({
                "timestamp":     t.strftime("%Y-%m-%d %H:%M:%S"),
                "cell_id":       cell,
                "UE_ID":         int(rng.integers(1, 20)),
                "DL_MCS1":       int(rng.integers(6, 15) if not bad else rng.integers(1, 6)),
                "UL_MCS1":       int(rng.integers(6, 15) if not bad else rng.integers(1, 6)),
                "PRB_DL":        int(rng.integers(20, 70) if not bad else rng.integers(70, 95)),
                "PRB_UL":        int(rng.integers(15, 60) if not bad else rng.integers(60, 90)),
                "dlsch_total":   dlsch_total,
                "dlsch_errors":  dlsch_errors,
                "ulsch_total":   ulsch_total,
                "ulsch_errors":  ulsch_errors,
                "DL_BLER":       round(dlsch_errors / dlsch_total * 100, 2),
                "UL_BLER":       round(ulsch_errors / ulsch_total * 100, 2),
                "SNR":           round(float(rng.uniform(3, 22) if not bad else rng.uniform(-4, 7)), 2),
                "DL_bitrate":    round(float(rng.uniform(8e6, 75e6) if not bad else rng.uniform(1e6, 12e6)), 0),
                "UL_bitrate":    round(float(rng.uniform(4e6, 35e6) if not bad else rng.uniform(0.5e6, 6e6)), 0),
            })
    return pd.DataFrame(rows)


# ── NIST / generic format ─────────────────────────────────────────────
def gen_nist():
    rows = []
    ts = _timestamps(N_ROWS)
    for t in ts:
        for cell in CELLS:
            bad = (cell == "PCI_4" and t.minute >= 180)
            rows.append({
                "Time":           t.isoformat(),
                "Cell":           cell,
                "IMSI":           f"20899{rng.integers(1000000,9999999)}",
                "RSRP_dBm":       round(float(rng.uniform(-95, -70) if not bad else rng.uniform(-120, -100)), 1),
                "RSRQ_dB":        round(float(rng.uniform(-12, -6) if not bad else rng.uniform(-20, -14)), 1),
                "SNR_dB":         round(float(rng.uniform(5, 25) if not bad else rng.uniform(-5, 5)), 1),
                "DL_Throughput_Mbps": round(float(rng.uniform(10, 100) if not bad else rng.uniform(0.5, 5)), 2),
                "UL_Throughput_Mbps": round(float(rng.uniform(5, 50) if not bad else rng.uniform(0.2, 3)), 2),
                "DL_BLER_pct":    round(float(rng.uniform(1, 10) if not bad else rng.uniform(25, 60)), 2),
                "UL_BLER_pct":    round(float(rng.uniform(1, 10) if not bad else rng.uniform(20, 55)), 2),
                "PRB_Utilization_pct": round(float(rng.uniform(20, 70) if not bad else rng.uniform(80, 98)), 1),
                "DL_MCS":         int(rng.integers(8, 16) if not bad else rng.integers(1, 6)),
                "UL_MCS":         int(rng.integers(8, 16) if not bad else rng.integers(1, 6)),
                "HARQ_NACK_DL":   int(rng.integers(2, 20) if not bad else rng.integers(50, 150)),
                "HARQ_NACK_UL":   int(rng.integers(2, 15) if not bad else rng.integers(40, 120)),
            })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out = Path("data/raw")
    out.mkdir(parents=True, exist_ok=True)

    df_srsran = gen_srsran()
    df_srsran.to_csv(out / "srsran_stats.csv", index=False)
    print(f"srsRAN stats: {out/'srsran_stats.csv'}  ({len(df_srsran)} rows)")

    df_oai = gen_oai()
    df_oai.to_csv(out / "oai_stats.csv", index=False)
    print(f"OAI stats:    {out/'oai_stats.csv'}  ({len(df_oai)} rows)")

    df_nist = gen_nist()
    df_nist.to_csv(out / "nist_stats.csv", index=False)
    print(f"NIST stats:   {out/'nist_stats.csv'}  ({len(df_nist)} rows)")

    # Also save as parquet for Tier-1 parquet support test
    df_srsran.to_parquet(out / "srsran_stats.parquet", index=False)
    print(f"Parquet:      {out/'srsran_stats.parquet'}")
