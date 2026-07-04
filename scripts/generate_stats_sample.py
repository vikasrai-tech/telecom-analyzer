"""
Generate a reviewer-friendly DU/CU Stats sample:
  - 4 cells (PCI_1, PCI_3, PCI_8, PCI_12)  — normal + all 3 fault types
  - 30 minutes each around the fault window
  - Two outputs:
      data/samples/du_cu_stats_sample.csv      (raw srsRAN format)
      data/samples/du_cu_stats_annotated.csv   (same + anomaly_label column)

Run: python scripts/generate_stats_sample.py
"""

from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
OUT = Path("data/samples")
OUT.mkdir(parents=True, exist_ok=True)

# ── Config ────────────────────────────────────────────────────────────
CELLS = {
    "PCI_1":  {"type": "TDD", "dl_cap": 1500, "ul_cap": 100, "fault": None},
    "PCI_3":  {"type": "TDD", "dl_cap": 1500, "ul_cap": 100, "fault": "congestion"},
    "PCI_8":  {"type": "TDD", "dl_cap": 1500, "ul_cap": 100, "fault": "drift"},
    "PCI_12": {"type": "FDD", "dl_cap": 100,  "ul_cap": 50,  "fault": "outage"},
}

# Fault windows (minute offset from 08:00)
FAULT_WINDOWS = {
    "congestion": (90, 150),    # 09:30 - 10:30
    "outage":     (240, 260),   # 12:00 - 12:20
    "drift":      (300, 360),   # 13:00 - 14:00
}

# Sample windows: 15 min before fault, fault window, 15 min after
SAMPLE_WINDOWS = {
    "PCI_1":  (0,   30),    # normal baseline
    "PCI_3":  (75,  165),   # congestion window + buffer
    "PCI_8":  (285, 360),   # drift window + buffer
    "PCI_12": (225, 275),   # outage window + buffer
}

BASE_TIME = datetime(2026, 6, 13, 8, 0, 0)


def gen_row(cell, cfg, minute):
    dl_cap = cfg["dl_cap"]
    ul_cap = cfg["ul_cap"]
    fault  = cfg["fault"]

    # Diurnal load factor
    hour   = 8 + minute / 60
    load   = 0.4 + 0.5 * np.sin(np.pi * (hour - 8) / 6)

    # Defaults (normal operation)
    nof_ue      = max(1, int(rng.normal(4 * load, 0.5)))
    dl_mbps     = max(1.0, rng.normal(dl_cap * 0.45 * load, dl_cap * 0.05))
    ul_mbps     = max(0.5, rng.normal(ul_cap * 0.45 * load, ul_cap * 0.05))
    dl_ok       = max(10,  int(rng.normal(1000 * load, 50)))
    dl_nok      = max(0,   int(rng.normal(15 * load, 5)))
    ul_ok       = max(10,  int(rng.normal(900  * load, 40)))
    ul_nok      = max(0,   int(rng.normal(10 * load, 4)))
    dl_mcs      = round(float(np.clip(rng.normal(18, 2), 6, 28)), 1)
    ul_mcs      = round(float(np.clip(rng.normal(16, 2), 4, 26)), 1)
    dl_prb      = round(float(np.clip(rng.normal(40 * load, 5), 5, 100)), 1)
    ul_prb      = round(float(np.clip(rng.normal(35 * load, 5), 5, 100)), 1)
    pusch_snr   = round(float(np.clip(rng.normal(22, 2), 5, 35)), 2)
    pucch_snr   = round(float(np.clip(rng.normal(20, 2), 5, 35)), 2)
    label       = "Normal"

    # ── Congestion fault ─────────────────────────────────────────────
    if fault == "congestion":
        fs, fe = FAULT_WINDOWS["congestion"]
        if fs <= minute < fe:
            dl_mbps  *= rng.uniform(0.20, 0.35)   # 65-80% throughput drop
            ul_mbps  *= rng.uniform(0.25, 0.40)
            dl_prb    = round(float(np.clip(rng.normal(96, 1.5), 90, 100)), 1)
            ul_prb    = round(float(np.clip(rng.normal(90, 2),   80, 100)), 1)
            dl_mcs    = round(float(np.clip(rng.normal(9,  2),   4,  14)),  1)
            ul_mcs    = round(float(np.clip(rng.normal(8,  2),   4,  12)),  1)
            dl_nok    = max(0, int(rng.normal(180, 20)))   # HARQ NACKs spike
            ul_nok    = max(0, int(rng.normal(130, 15)))
            label     = "CONGESTION"

    # ── Hard outage fault ─────────────────────────────────────────────
    if fault == "outage":
        fs, fe = FAULT_WINDOWS["outage"]
        if fs <= minute < fe:
            dl_mbps  = max(0.0, rng.normal(dl_cap * 0.005, 0.05))
            ul_mbps  = max(0.0, rng.normal(ul_cap * 0.005, 0.02))
            dl_ok    = max(0, int(rng.normal(2, 1)))
            dl_nok   = max(0, int(rng.normal(1, 1)))
            ul_ok    = max(0, int(rng.normal(1, 1)))
            ul_nok   = max(0, int(rng.normal(1, 1)))
            dl_mcs   = round(float(np.clip(rng.normal(4, 1), 0, 8)), 1)
            ul_mcs   = round(float(np.clip(rng.normal(3, 1), 0, 6)), 1)
            dl_prb   = round(float(np.clip(rng.normal(1, 0.5), 0, 5)), 1)
            ul_prb   = round(float(np.clip(rng.normal(1, 0.5), 0, 5)), 1)
            pusch_snr = round(float(np.clip(rng.normal(3, 1), 0, 8)), 2)
            pucch_snr = round(float(np.clip(rng.normal(3, 1), 0, 8)), 2)
            nof_ue   = 0
            label    = "OUTAGE"

    # ── Slow drift fault ──────────────────────────────────────────────
    if fault == "drift":
        fs, fe = FAULT_WINDOWS["drift"]
        if minute >= fs:
            frac      = min(1.0, (minute - fs) / (fe - fs))
            pusch_snr = round(float(np.clip(rng.normal(22 - 14 * frac, 1.5), 3, 30)), 2)
            pucch_snr = round(float(np.clip(rng.normal(20 - 12 * frac, 1.5), 3, 28)), 2)
            dl_mcs    = round(float(np.clip(rng.normal(18 - 10 * frac, 1.5), 4, 28)), 1)
            dl_mbps  *= (1.0 - 0.55 * frac)
            label     = f"DRIFT({frac*100:.0f}%)"

    return {
        "timestamp":    (BASE_TIME + timedelta(minutes=minute)).isoformat(),
        "pci":          cell,
        "cell_type":    cfg["type"],
        "nof_ue":       nof_ue,
        "dl_brate":     round(dl_mbps * 1e6, 0),
        "ul_brate":     round(ul_mbps * 1e6, 0),
        "dl_nof_ok":    dl_ok,
        "dl_nof_nok":   dl_nok,
        "ul_nof_ok":    ul_ok,
        "ul_nof_nok":   ul_nok,
        "dl_mcs":       dl_mcs,
        "ul_mcs":       ul_mcs,
        "dl_prb":       dl_prb,
        "ul_prb":       ul_prb,
        "pusch_snr_db": pusch_snr,
        "pucch_snr_db": pucch_snr,
        "anomaly_label": label,
    }


def _write_txt(df: pd.DataFrame, path: Path):
    lines = []

    def h(text):
        lines.append("=" * 72)
        lines.append(f"  {text}")
        lines.append("=" * 72)

    def sub(text):
        lines.append("")
        lines.append(f"  -- {text} --")
        lines.append("")

    lines.append("")
    h("DU / CU gNB Statistics — Sample Report")
    lines.append(f"  Generated : {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"  Format    : srsRAN L1/L2 per-cell stats (1-minute granularity)")
    lines.append(f"  Topology  : 4 cells  |  4 UEs/cell  |  TDD + FDD sites")
    lines.append(f"  Scenarios : Normal · Congestion · Hard Outage · Slow SNR Drift")
    lines.append(f"  Rows      : {len(df)} total  ({len(df[df['anomaly_label']!='Normal'])} fault rows)")
    lines.append("")

    # Column legend
    h("Column Definitions (3GPP / srsRAN)")
    col_defs = [
        ("timestamp",    "ISO-8601 measurement timestamp (1-min intervals)"),
        ("pci",          "Physical Cell Identity  (PCI_1 .. PCI_16)"),
        ("cell_type",    "TDD (Time-Division Duplex) or FDD (Freq-Division Duplex)"),
        ("nof_ue",       "Number of active UEs scheduled in this TTI window"),
        ("dl_brate",     "Downlink bit-rate  [bps]  — aggregate across all UEs"),
        ("ul_brate",     "Uplink   bit-rate  [bps]  — aggregate across all UEs"),
        ("dl_nof_ok",    "DL HARQ ACK count  — successfully decoded transport blocks"),
        ("dl_nof_nok",   "DL HARQ NACK count — failed decodes (retransmission needed)"),
        ("ul_nof_ok",    "UL HARQ ACK count"),
        ("ul_nof_nok",   "UL HARQ NACK count"),
        ("dl_mcs",       "DL Modulation & Coding Scheme index  (0-28); higher = better"),
        ("ul_mcs",       "UL Modulation & Coding Scheme index  (0-26); higher = better"),
        ("dl_prb",       "DL Physical Resource Block utilisation [%]  (0-100)"),
        ("ul_prb",       "UL Physical Resource Block utilisation [%]  (0-100)"),
        ("pusch_snr_db", "UL PUSCH Signal-to-Noise Ratio  [dB]; <10 dB = poor link"),
        ("pucch_snr_db", "UL PUCCH SNR [dB]  — control channel quality"),
        ("anomaly_label","Injected ground-truth label  (annotated file only)"),
    ]
    for col, desc in col_defs:
        lines.append(f"  {col:<18}  {desc}")
    lines.append("")

    # Per-cell sections
    FAULT_DESC = {
        "PCI_1":  ("NORMAL BASELINE",
                   "No fault injected. Diurnal traffic ramp from 08:00.\n"
                   "  MCS stays 16-20, PRB 10-40%, SNR 20-24 dB."),
        "PCI_3":  ("CONGESTION FAULT  [09:30 - 10:30]",
                   "Radio-layer overload on TDD cell.\n"
                   "  RB utilisation rises to 95-100%.\n"
                   "  DL throughput drops 65-80%.\n"
                   "  HARQ NACK rate spikes to 170-200 per minute.\n"
                   "  MCS collapses from ~18 to 6-9 (link adaptation under load)."),
        "PCI_12": ("HARD OUTAGE FAULT  [12:00 - 12:20]",
                   "Simulated unplanned site failure on FDD cell.\n"
                   "  nof_ue drops to 0 (no scheduled users).\n"
                   "  dl_brate collapses to < 1 Mbps (noise floor).\n"
                   "  dl_prb and ul_prb fall to < 2%.\n"
                   "  PUSCH SNR crashes to 1-5 dB (no signal)."),
        "PCI_8":  ("SLOW SNR DRIFT FAULT  [13:00 - 14:00]",
                   "Simulated gradual interference accumulation on TDD cell.\n"
                   "  PUSCH SNR degrades linearly: 22 dB → 8 dB over 60 min.\n"
                   "  DL MCS follows SNR downward: 18 → 7.\n"
                   "  DL throughput degrades ~55% by end of window.\n"
                   "  ** Static KPI thresholds miss this for the first 30-40 min. **\n"
                   "  Detected only by Trend-Regression and CUSUM detectors."),
    }

    for cell in ["PCI_1", "PCI_3", "PCI_12", "PCI_8"]:
        cfg   = CELLS[cell]
        title, desc = FAULT_DESC[cell]
        sub(f"{cell}  ({cfg['type']})  —  {title}")
        for dline in desc.split("\n"):
            lines.append(f"  {dline}")
        lines.append("")

        cell_df = df[df["pci"] == cell].copy()
        cell_df["dl_mbps"] = (cell_df["dl_brate"] / 1e6).round(1)
        cell_df["ul_mbps"] = (cell_df["ul_brate"] / 1e6).round(1)

        show_cols = ["timestamp", "nof_ue", "dl_mbps", "ul_mbps",
                     "dl_mcs", "dl_prb", "dl_nof_nok",
                     "pusch_snr_db", "anomaly_label"]

        # Show: first 3 normal + all fault rows (max 20) + last 2 normal
        normal = cell_df[cell_df["anomaly_label"] == "Normal"]
        fault  = cell_df[cell_df["anomaly_label"] != "Normal"]

        preview = pd.concat([
            normal.head(3),
            fault.head(20),
            normal.tail(2),
        ]).drop_duplicates()

        lines.append(f"  {'Timestamp':<22} {'UEs':>4} {'DL(Mbps)':>9} {'UL(Mbps)':>9} "
                     f"{'MCS':>5} {'PRB%':>6} {'NACKs':>6} {'SNR(dB)':>8}  Label")
        lines.append(f"  {'-'*22} {'-'*4} {'-'*9} {'-'*9} "
                     f"{'-'*5} {'-'*6} {'-'*6} {'-'*8}  {'-'*14}")

        prev_label = None
        for _, row in preview.iterrows():
            label = row["anomaly_label"]
            if prev_label is not None and prev_label != label and label != "Normal":
                lines.append(f"  {'  ... fault begins ...':<80}")
            lines.append(
                f"  {row['timestamp']:<22} {int(row['nof_ue']):>4} "
                f"{row['dl_mbps']:>9.1f} {row['ul_mbps']:>9.1f} "
                f"{row['dl_mcs']:>5.1f} {row['dl_prb']:>6.1f} "
                f"{int(row['dl_nof_nok']):>6} {row['pusch_snr_db']:>8.2f}  {label}"
            )
            prev_label = label

        fault_count = len(fault)
        if fault_count > 20:
            lines.append(f"  ... ({fault_count - 20} more fault rows in CSV) ...")
        lines.append("")

        # Stats summary
        lines.append(f"  Summary ({cell}):")
        lines.append(f"    Total rows   : {len(cell_df)}")
        lines.append(f"    Fault rows   : {fault_count}")
        if fault_count:
            lines.append(f"    DL brate normal mean : {normal['dl_mbps'].mean():.1f} Mbps")
            lines.append(f"    DL brate fault  mean : {fault['dl_mbps'].mean():.1f} Mbps")
            lines.append(f"    SNR    normal mean   : {normal['pusch_snr_db'].mean():.2f} dB")
            lines.append(f"    SNR    fault  mean   : {fault['pusch_snr_db'].mean():.2f} dB")
            lines.append(f"    NACKs  normal mean   : {normal['dl_nof_nok'].mean():.1f}")
            lines.append(f"    NACKs  fault  mean   : {fault['dl_nof_nok'].mean():.1f}")
        lines.append("")

    # Detection summary
    h("Detection Notes")
    lines.append("")
    notes = [
        ("Congestion",  "PCI_3",  "PRB > 95%, NACK spike, MCS drop",
         "Threshold · Peer-Comparison · Bollinger · CUSUM · IQR · Trend"),
        ("Hard Outage", "PCI_12", "dl_brate ≈ 0, nof_ue = 0, SNR crash",
         "Threshold · Isolation Forest · OC-SVM · LOF · Elliptic Env · LSTM-AE"),
        ("Slow Drift",  "PCI_8",  "SNR / MCS gradual decline",
         "CUSUM · Trend-Regression  (static threshold MISSES for first 30 min)"),
        ("Normal",      "PCI_1",  "No anomaly",
         "No detectors fire (baseline)"),
    ]
    lines.append(f"  {'Fault':<14} {'Cell':<8} {'Key Signal':<35} {'Detectors'}")
    lines.append(f"  {'-'*14} {'-'*8} {'-'*35} {'-'*40}")
    for fault, cell, signal, detectors in notes:
        lines.append(f"  {fault:<14} {cell:<8} {signal:<35} {detectors}")
    lines.append("")

    h("Files Generated")
    lines.append("  du_cu_stats_sample.csv     — raw srsRAN format (parser-ready)")
    lines.append("  du_cu_stats_annotated.csv  — same + anomaly_label + cell_type columns")
    lines.append("  du_cu_stats_sample.txt     — this human-readable report")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    rows = []
    for cell, cfg in CELLS.items():
        m_start, m_end = SAMPLE_WINDOWS[cell]
        for minute in range(m_start, m_end + 1):
            rows.append(gen_row(cell, cfg, minute))

    df = pd.DataFrame(rows)

    # ── Raw srsRAN format (no label column) ──────────────────────────
    raw_cols = ["timestamp","pci","nof_ue","dl_brate","ul_brate",
                "dl_nof_ok","dl_nof_nok","ul_nof_ok","ul_nof_nok",
                "dl_mcs","ul_mcs","dl_prb","ul_prb","pusch_snr_db","pucch_snr_db"]
    raw_path = OUT / "du_cu_stats_sample.csv"
    df[raw_cols].to_csv(raw_path, index=False)

    # ── Annotated format (with label + cell_type) ─────────────────────
    ann_path = OUT / "du_cu_stats_annotated.csv"
    df.to_csv(ann_path, index=False)

    # ── Human-readable TXT report ──────────────────────────────────────
    txt_path = OUT / "du_cu_stats_sample.txt"
    _write_txt(df, txt_path)

    print(f"Saved raw sample     : {raw_path}  ({len(df)} rows)")
    print(f"Saved annotated      : {ann_path}  ({len(df)} rows)")
    print(f"Saved TXT report     : {txt_path}")
    print()
    print("Columns (srsRAN format):")
    for c in raw_cols:
        print(f"  {c}")
    print()
    print("Fault summary:")
    summary = df[df["anomaly_label"] != "Normal"].groupby(["pci","anomaly_label"]).size()
    print(summary.to_string())
    print()
    print("Sample rows per cell:")
    for cell in CELLS:
        sub = df[df["pci"] == cell]
        fault_rows = sub[sub["anomaly_label"] != "Normal"]
        print(f"  {cell}: {len(sub)} rows total, {len(fault_rows)} fault rows")


if __name__ == "__main__":
    main()
