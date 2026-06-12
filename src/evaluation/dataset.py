"""
Synthetic Labeled Dataset Generator

Produces parsed_kpi and parsed_stats dicts (identical format to the real
parsers) with known anomalies injected at specific (cell_id, kpi) positions.

Ground truth is returned as a frozenset of (cell_id, kpi) tuples that are
anomalous — the same keys the detectors emit in their anomaly dicts.

Anomaly injection patterns (one per (cell_id, kpi) pair chosen):
  spike            — single-point 4–6× normal value
  threshold_breach — sustained values above critical threshold for 10+ rows
  drift            — linear ramp over 15 rows crossing warning then critical
  cusum_shift      — step-change in mean for last 25 rows
"""

import random
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Tuple

import numpy as np
import pandas as pd

# ── KPI dataset config ────────────────────────────────────────────────

# (kpi_name, normal_mean, normal_std, direction, warning, critical)
# direction: "lower_better" means anomaly = high value
_KPI_SPECS = [
    ("cell_avail",       99.5,  0.3,  "higher_better",  99.0, 95.0),
    ("rrc_setup_sr",     99.2,  0.4,  "higher_better",  98.0, 95.0),
    ("reg_sr",           99.1,  0.4,  "higher_better",  98.0, 95.0),
    ("session_setup_sr", 99.0,  0.5,  "higher_better",  98.0, 95.0),
    ("packet_loss_rate",  0.05, 0.02, "lower_better",    0.5,  1.0),
    ("rrc_drop_rate",     0.08, 0.03, "lower_better",    0.5,  1.0),
    ("ho_sr",            96.0,  1.0,  "higher_better",  93.0, 90.0),
    ("pdcp_ul_throughput",120.0, 20.0,"higher_better",  None, None),
]

# (metric_name, normal_mean, normal_std, direction, warning, critical)
_STATS_SPECS = [
    ("dl_bler",           3.0,  1.5,  "lower_better",   10.0, 20.0),
    ("ul_bler",           2.5,  1.2,  "lower_better",   10.0, 20.0),
    ("dl_prb_util",      55.0, 10.0,  "lower_better",   80.0, 90.0),
    ("ul_prb_util",      50.0,  9.0,  "lower_better",   80.0, 90.0),
    ("dl_harq_nack_rate", 5.0,  2.0,  "lower_better",   15.0, 25.0),
    ("pusch_snr_db",     18.0,  3.0,  "higher_better",   5.0,  0.0),
]

ANOMALY_TYPES = ("spike", "threshold_breach", "drift", "cusum_shift")

CELL_COL  = "Cell_ID"
TIME_COL  = "Timestamp"
SCELL_COL = "cell_id"
STIME_COL = "timestamp"


# ── Injection helpers ─────────────────────────────────────────────────

def _inject(series: np.ndarray, atype: str, direction: str,
            warning: float, critical: float, rng: np.random.Generator) -> np.ndarray:
    """Return a modified copy of `series` with one anomaly pattern injected."""
    s = series.copy()
    n = len(s)
    mean = float(np.mean(s))
    std  = max(float(np.std(s)), 0.1)

    if direction == "lower_better":
        anomaly_val = critical * rng.uniform(1.2, 2.0) if critical else mean * 4
    else:
        anomaly_val = critical * rng.uniform(0.5, 0.8) if critical else mean * 0.3

    if atype == "spike":
        idx = rng.integers(10, n - 5)
        s[idx] = anomaly_val

    elif atype == "threshold_breach":
        start = rng.integers(20, n - 15)
        end   = min(start + rng.integers(10, 20), n)
        noise = rng.normal(0, std * 0.1, end - start)
        s[start:end] = anomaly_val + noise

    elif atype == "drift":
        start = rng.integers(5, n - 20)
        end   = min(start + 20, n)
        ramp  = np.linspace(mean, anomaly_val, end - start)
        s[start:end] = ramp + rng.normal(0, std * 0.05, end - start)

    elif atype == "cusum_shift":
        shift_point = rng.integers(n // 2, n - 10)
        shift_amount = (anomaly_val - mean) * 0.6
        s[shift_point:] += shift_amount

    return s


# ── Public generators ─────────────────────────────────────────────────

@dataclass
class LabeledDataset:
    parsed: Dict[str, Any]
    ground_truth: FrozenSet[Tuple[str, str]]   # (cell_id, kpi) pairs
    anomaly_details: List[Dict[str, Any]] = field(default_factory=list)
    n_normal_pairs: int = 0
    n_anomaly_pairs: int = 0


def generate_kpi_dataset(
    n_cells: int = 5,
    n_timestamps: int = 100,
    anomaly_rate: float = 0.20,
    seed: int = 42,
) -> LabeledDataset:
    """
    Generate a synthetic parsed_kpi dict with injected anomalies.

    Returns a LabeledDataset whose .ground_truth is a frozenset of
    (cell_id, kpi) pairs that contain injected anomalies.
    """
    rng = np.random.default_rng(seed)

    cells = [f"cell_{i+1}" for i in range(n_cells)]
    timestamps = pd.date_range("2024-01-15 08:00", periods=n_timestamps, freq="5min")
    kpi_names  = [s[0] for s in _KPI_SPECS]
    specs      = {s[0]: s for s in _KPI_SPECS}

    # All (cell, kpi) pairs
    all_pairs = [(c, k) for c in cells for k in kpi_names]
    n_anomaly = max(1, int(len(all_pairs) * anomaly_rate))
    anomaly_pairs = set(map(tuple, rng.choice(all_pairs, size=n_anomaly, replace=False).tolist()))

    records = []
    anomaly_details = []

    for cell in cells:
        for _, row_ts in enumerate(timestamps):
            row: Dict[str, Any] = {CELL_COL: cell, TIME_COL: str(row_ts)}
            for kpi in kpi_names:
                _, mean, std, *_ = specs[kpi]
                row[kpi] = float(rng.normal(mean, std))
            records.append(row)

    # Inject anomalies per (cell, kpi) pair
    df = pd.DataFrame(records)
    for cell, kpi in anomaly_pairs:
        _, mean, std, direction, warning, critical = specs[kpi]
        if warning is None:
            continue  # skip KPIs without thresholds (throughput)
        mask  = df[CELL_COL] == cell
        atype = str(rng.choice(ANOMALY_TYPES))
        orig  = df.loc[mask, kpi].to_numpy(dtype=float)
        inj   = _inject(orig, atype, direction, warning, critical, rng)
        df.loc[mask, kpi] = inj
        anomaly_details.append({
            "cell_id": cell, "kpi": kpi,
            "type": atype, "direction": direction,
            "warning": warning, "critical": critical,
        })

    # Rebuild records from modified df
    df[TIME_COL] = df[TIME_COL].astype(str)
    final_records = df.to_dict(orient="records")

    # Summary per KPI
    summary = {
        kpi: {
            "mean": float(df[kpi].mean()),
            "std":  float(df[kpi].std()),
            "min":  float(df[kpi].min()),
            "max":  float(df[kpi].max()),
        }
        for kpi in kpi_names
    }

    parsed = {
        "source":         "synthetic_kpi",
        "rows":           len(df),
        "cells":          cells,
        "gnbs":           [f"gnb_{i+1}" for i in range(n_cells)],
        "time_range":     f"{timestamps[0]} – {timestamps[-1]}",
        "kpi_columns":    kpi_names,
        "timestamp_col":  TIME_COL,
        "cell_col":       CELL_COL,
        "gnb_col":        "",
        "df_records":     final_records,
        "summary":        summary,
        "parser_version": "synthetic_v1",
    }

    # Only include pairs where threshold exists
    gt_pairs = frozenset(
        (c, k) for c, k in anomaly_pairs
        if specs[k][4] is not None  # has warning threshold
    )

    n_total = len(cells) * len([k for k in kpi_names if specs[k][4] is not None])
    return LabeledDataset(
        parsed=parsed,
        ground_truth=gt_pairs,
        anomaly_details=anomaly_details,
        n_normal_pairs=n_total - len(gt_pairs),
        n_anomaly_pairs=len(gt_pairs),
    )


def generate_stats_dataset(
    n_cells: int = 3,
    n_timestamps: int = 100,
    anomaly_rate: float = 0.20,
    seed: int = 99,
) -> LabeledDataset:
    """
    Generate a synthetic parsed_stats dict with injected anomalies.
    """
    rng   = np.random.default_rng(seed)
    cells = [f"cell_{i+1}" for i in range(n_cells)]
    timestamps = pd.date_range("2024-01-15 08:00", periods=n_timestamps, freq="1min")
    metric_names = [s[0] for s in _STATS_SPECS]
    specs        = {s[0]: s for s in _STATS_SPECS}

    all_pairs = [(c, m) for c in cells for m in metric_names]
    n_anomaly = max(1, int(len(all_pairs) * anomaly_rate))
    anomaly_pairs = set(map(tuple, rng.choice(all_pairs, size=n_anomaly, replace=False).tolist()))

    records = []
    anomaly_details = []

    for cell in cells:
        for ts in timestamps:
            row: Dict[str, Any] = {SCELL_COL: cell, STIME_COL: str(ts)}
            for metric in metric_names:
                _, mean, std, *_ = specs[metric]
                row[metric] = float(rng.normal(mean, std))
            records.append(row)

    df = pd.DataFrame(records)
    for cell, metric in anomaly_pairs:
        _, mean, std, direction, warning, critical = specs[metric]
        mask  = df[SCELL_COL] == cell
        atype = str(rng.choice(ANOMALY_TYPES))
        orig  = df.loc[mask, metric].to_numpy(dtype=float)
        inj   = _inject(orig, atype, direction, warning, critical, rng)
        df.loc[mask, metric] = inj
        anomaly_details.append({
            "cell_id": cell, "metric": metric,
            "type": atype, "direction": direction,
        })

    df[STIME_COL] = df[STIME_COL].astype(str)

    parsed = {
        "source":         "synthetic_stats",
        "rows":           len(df),
        "cells":          cells,
        "l1l2_columns":   metric_names,
        "timestamp_col":  STIME_COL,
        "cell_col":       SCELL_COL,
        "df_records":     df.to_dict(orient="records"),
        "vendor":         "synthetic",
        "parser_version": "synthetic_v1",
    }

    gt_pairs = frozenset(anomaly_pairs)
    n_total  = len(cells) * len(metric_names)
    return LabeledDataset(
        parsed=parsed,
        ground_truth=gt_pairs,
        anomaly_details=anomaly_details,
        n_normal_pairs=n_total - len(gt_pairs),
        n_anomaly_pairs=len(gt_pairs),
    )
