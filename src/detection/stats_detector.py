"""
DU/CU Stats Anomaly Detector — L1/L2 counters (PRB, BLER, MCS, HARQ, SNR).

6 methods mirroring the KPI detector ensemble:
  1. Threshold Violation  — per-row vs warning/critical limits
  2. Peer Comparison      — z-score vs other cells in same time window
  3. Trend (LinReg)       — monotonic degradation over time
  4. IQR (Tukey Fence)    — robust, no distribution assumption
  5. CUSUM                — cumulative-sum change-point detection
  6. Bollinger Bands      — rolling envelope for burst spikes

Input:  output of stats_parser.parse_stats_file()
Output: same anomaly schema as kpi_detector
"""

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.parsers.stats_parser import get_meta

logger = logging.getLogger(__name__)

SEV_ORDER = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}


def _sev(value, meta) -> str:
    w = meta.get("warning")
    c = meta.get("critical")
    if w is None:
        return "Low"
    # Direction: lower is better for BLER/PRB; higher is worse
    # Lower is worse for MCS/SNR/RSRP
    worse_when_high = meta.get("desc", "").lower() in (
        "dl block error rate", "ul block error rate",
        "dl prb utilisation", "ul prb utilisation",
        "dl harq nack rate", "ul harq nack rate",
        "dl harq nack count (raw)", "ul harq nack count (raw)",
    ) or "bler" in meta.get("desc", "").lower() or "prb" in meta.get("desc", "").lower() \
        or "nack" in meta.get("desc", "").lower()

    if worse_when_high:
        if c is not None and value >= c:
            return "Critical"
        if w is not None and value >= w:
            return "High"
    else:
        if c is not None and value <= c:
            return "Critical"
        if w is not None and value <= w:
            return "High"
    return "Low"


def _make_anomaly(col, cell, value, sev, evidence, recommendation, detector, score=0.0, **kwargs):
    meta = get_meta(col)
    return {
        "label": col,
        "category": meta.get("desc", col),
        "cell_id": str(cell),
        "gnb_id": str(cell),
        "value": round(float(value), 3) if value is not None else None,
        "unit": meta.get("unit", ""),
        "warning": meta.get("warning"),
        "critical": meta.get("critical"),
        "severity": sev,
        "evidence": evidence,
        "recommendation": recommendation,
        "detector": detector,
        "score": score,
        "source": "stats",
        **kwargs,
    }


def _get_df(parsed: Dict[str, Any]) -> pd.DataFrame:
    df = pd.DataFrame(parsed["df_records"])
    ts = parsed.get("timestamp_col", "")
    if ts and ts in df.columns:
        df[ts] = pd.to_datetime(df[ts], errors="coerce")
    return df


# ── 1. Threshold Violation ────────────────────────────────────────────

def detect_threshold(parsed: Dict[str, Any]) -> List[Dict]:
    anomalies = []
    df = _get_df(parsed)
    cols = parsed.get("l1l2_columns", [])
    cell_col = parsed.get("cell_col", "")

    for col in cols:
        meta = get_meta(col)
        if meta["warning"] is None:
            continue
        for cell, grp in df.groupby(cell_col) if cell_col else [("ALL", df)]:
            vals = grp[col].dropna()
            if vals.empty:
                continue
            mean_val = vals.mean()
            sev = _sev(mean_val, meta)
            if sev in ("Critical", "High"):
                anomalies.append(_make_anomaly(
                    col, cell, mean_val, sev,
                    evidence=f"Mean {col} = {mean_val:.2f} {meta['unit']} "
                    f"(warning={meta['warning']}, critical={meta['critical']})",
                    recommendation=f"Investigate {meta['desc']} on cell {cell}. "
                    f"Check hardware alarms and scheduler configuration.",
                    detector="Threshold",
                    score=abs(mean_val - (meta["warning"] or 0)),
                ))
    return anomalies


# ── 2. Peer Comparison ────────────────────────────────────────────────

def detect_peer_comparison(parsed: Dict[str, Any]) -> List[Dict]:
    anomalies = []
    df = _get_df(parsed)
    cols = parsed.get("l1l2_columns", [])
    cell_col = parsed.get("cell_col", "")
    if not cell_col or df[cell_col].nunique() < 2:
        return anomalies

    for col in cols:
        meta = get_meta(col)
        cell_means = df.groupby(cell_col)[col].mean().dropna()
        if cell_means.empty or cell_means.std() == 0:
            continue
        z_scores = (cell_means - cell_means.mean()) / cell_means.std()
        for cell, z in z_scores.items():
            if abs(z) < 2.0:
                continue
            val = cell_means[cell]
            sev = "High" if abs(z) >= 3.0 else "Medium"
            anomalies.append(_make_anomaly(
                col, cell, val, sev,
                evidence=f"{col} z-score={z:.2f} (cell mean={val:.2f}, "
                f"fleet mean={cell_means.mean():.2f} {meta['unit']})",
                recommendation=f"Cell {cell} is a statistical outlier for {meta['desc']}. "
                f"Compare antenna config and scheduler settings with peer cells.",
                detector="Peer Comparison",
                score=abs(z),
            ))
    return anomalies


# ── 3. Trend (Linear Regression) ─────────────────────────────────────

def detect_trend(parsed: Dict[str, Any]) -> List[Dict]:
    anomalies = []
    df = _get_df(parsed)
    cols = parsed.get("l1l2_columns", [])
    cell_col = parsed.get("cell_col", "")
    ts_col = parsed.get("timestamp_col", "")
    if not ts_col or ts_col not in df.columns:
        return anomalies

    df["_t"] = (df[ts_col] - df[ts_col].min()).dt.total_seconds() / 3600

    for col in cols:
        meta = get_meta(col)
        for cell, grp in df.groupby(cell_col) if cell_col else [("ALL", df)]:
            sub = grp[["_t", col]].dropna()
            if len(sub) < 8:
                continue
            x = sub["_t"].values
            y = sub[col].values
            slope = np.polyfit(x, y, 1)[0]
            if abs(slope) < 0.3:
                continue
            sev = "High" if abs(slope) > 1.0 else "Medium"
            direction = "degrading" if slope > 0 else "improving"
            anomalies.append(_make_anomaly(
                col, cell, grp[col].iloc[-1], sev,
                evidence=f"{col} trend slope={slope:.3f} {meta['unit']}/hr ({direction})",
                recommendation=f"Sustained {direction} trend in {meta['desc']} on cell {cell}. "
                f"Schedule maintenance check before threshold breach.",
                detector="Trend",
                score=abs(slope),
            ))
    return anomalies


# ── 4. IQR (Tukey Fence) ─────────────────────────────────────────────

def detect_iqr(parsed: Dict[str, Any]) -> List[Dict]:
    anomalies = []
    df = _get_df(parsed)
    cols = parsed.get("l1l2_columns", [])
    cell_col = parsed.get("cell_col", "")

    for col in cols:
        meta = get_meta(col)
        for cell, grp in df.groupby(cell_col) if cell_col else [("ALL", df)]:
            vals = grp[col].dropna()
            if len(vals) < 10:
                continue
            q1, q3 = vals.quantile(0.25), vals.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
            outliers = vals[(vals < lo) | (vals > hi)]
            if outliers.empty:
                continue
            pct = len(outliers) / len(vals) * 100
            sev = "High" if pct > 5 else "Medium"
            anomalies.append(_make_anomaly(
                col, cell, outliers.mean(), sev,
                evidence=f"{col} IQR fence [{lo:.1f}, {hi:.1f}]: "
                f"{len(outliers)} outliers ({pct:.1f}%) on cell {cell}",
                recommendation=f"Distribution outliers detected in {meta['desc']}. "
                f"Check for configuration changes or hardware faults.",
                detector="IQR",
                score=pct,
            ))
    return anomalies


# ── 5. CUSUM ─────────────────────────────────────────────────────────

def detect_cusum(parsed: Dict[str, Any]) -> List[Dict]:
    anomalies = []
    df = _get_df(parsed)
    cols = parsed.get("l1l2_columns", [])
    cell_col = parsed.get("cell_col", "")

    for col in cols:
        meta = get_meta(col)
        slack = 0.5
        thresh = 4.0
        for cell, grp in df.groupby(cell_col) if cell_col else [("ALL", df)]:
            vals = grp[col].dropna()
            if len(vals) < 15:
                continue
            mu = vals.mean()
            sig = vals.std() or 1.0
            z = (vals - mu) / sig
            cusum_pos = np.maximum.accumulate(np.maximum(z - slack, 0))
            cusum_neg = np.maximum.accumulate(np.maximum(-z - slack, 0))
            max_c = max(cusum_pos.max(), cusum_neg.max())
            if max_c < thresh:
                continue
            sev = "High" if max_c > thresh * 1.5 else "Medium"
            anomalies.append(_make_anomaly(
                col, cell, vals.iloc[-1], sev,
                evidence=f"{col} CUSUM={max_c:.2f} (threshold={thresh}) on cell {cell}",
                recommendation=f"Cumulative drift detected in {meta['desc']}. "
                f"Check for gradual hardware degradation or parameter drift.",
                detector="CUSUM",
                score=max_c,
            ))
    return anomalies


# ── 6. Bollinger Bands ────────────────────────────────────────────────

def detect_bollinger(parsed: Dict[str, Any]) -> List[Dict]:
    anomalies = []
    df = _get_df(parsed)
    cols = parsed.get("l1l2_columns", [])
    cell_col = parsed.get("cell_col", "")
    ts_col = parsed.get("timestamp_col", "")

    for col in cols:
        meta = get_meta(col)
        window = 5
        k = 2.5
        for cell, grp in (df.groupby(cell_col) if cell_col else [("ALL", df)]):
            if ts_col and ts_col in grp.columns:
                sub = grp.sort_values(ts_col)[col].dropna()
            else:
                sub = grp[col].dropna()
            if len(sub) < window + 2:
                continue
            mid = sub.rolling(window).mean()
            std = sub.rolling(window).std()
            upper = mid + k * std
            lower = mid - k * std
            outside = ((sub > upper) | (sub < lower)).sum()
            if outside == 0:
                continue
            pct = outside / len(sub) * 100
            if pct < 3:
                continue
            sev = "High" if pct > 8 else "Medium"
            anomalies.append(_make_anomaly(
                col, cell, sub.iloc[-1], sev,
                evidence=f"{col} Bollinger break: {outside} points ({pct:.1f}%) "
                f"outside {k}σ band on cell {cell}",
                recommendation=f"Burst anomaly detected in {meta['desc']}. "
                f"Check for interference events or transient load spikes.",
                detector="Bollinger Bands",
                score=pct,
            ))
    return anomalies


# ── Public API ────────────────────────────────────────────────────────

DETECTORS = {
    "Threshold": detect_threshold,
    "Peer Comparison": detect_peer_comparison,
    "Trend": detect_trend,
    "IQR": detect_iqr,
    "CUSUM": detect_cusum,
    "Bollinger Bands": detect_bollinger,
}


def detect_stats_anomalies_by_detector(
    parsed: Dict[str, Any],
) -> Dict[str, List[Dict]]:
    """Run all 6 detectors. Returns {detector_name: [anomaly, ...]}."""
    results = {}
    for name, fn in DETECTORS.items():
        try:
            results[name] = fn(parsed)
            logger.info(f"[stats] {name}: {len(results[name])} anomalies")
        except Exception as e:
            logger.warning(f"[stats] {name} failed: {e}")
            results[name] = []
    return results


def detect_stats_anomalies(parsed: Dict[str, Any]) -> List[Dict]:
    """Merge all detectors, deduplicate by (col, cell), keep highest severity."""
    by_det = detect_stats_anomalies_by_detector(parsed)
    seen: Dict[str, Dict] = {}
    for anoms in by_det.values():
        for a in anoms:
            key = f"{a['label']}|{a['cell_id']}"
            if key not in seen or SEV_ORDER.get(a["severity"], 0) > SEV_ORDER.get(seen[key]["severity"], 0):
                seen[key] = a
    return sorted(seen.values(),
                  key=lambda a: (SEV_ORDER.get(a["severity"], 0), a.get("score", 0)),
                  reverse=True)
