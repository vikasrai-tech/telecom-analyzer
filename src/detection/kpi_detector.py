"""
KPI Detector — anomaly detection on gNB KPI time-series data.

Six detection layers:
  1. Threshold violations  — per-row check against warning/critical levels
  2. Peer comparison       — cells significantly below fleet average (z-score)
  3. Trend analysis        — KPIs degrading over time (linear regression slope)
  4. IQR outlier           — robust fence-based outlier (Tukey method)
  5. CUSUM                 — cumulative-sum change-point detection
  6. Bollinger Bands       — rolling mean ± 2σ envelope, catches spikes
"""

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.parsers.kpi_defs import get_meta

logger = logging.getLogger(__name__)

SEV_RANK = {"Critical": 3, "High": 2, "Medium": 1, "Low": 0}

RECOMMENDATIONS: Dict[str, str] = {
    "RRC_Success_Rate_%":           "Check gNB RRC configuration; review RRC Setup Timeout counters and F1AP trace.",
    "Registration_Success_Rate_%":  "Verify AMF reachability and NGAP N2 link; check NAS Registration Reject causes.",
    "Handover_Success_Rate_%":      "Review Xn/NG HO preparation and execution counters; check A3 offset and TTT.",
    "PDU_Session_Success_Rate_%":   "Verify SMF/UPF connectivity; check PDU Session Establishment Reject causes.",
    "Cell_Availability_%":          "Investigate cell outage alarms; check gNB hardware faults and O&M logs.",
    "PRB_Utilization_DL_%":         "DL capacity congestion — consider load balancing, carrier aggregation, or adding sectors.",
    "PRB_Utilization_UL_%":         "UL capacity congestion — review UL scheduler and UE transmit power settings.",
    "CQI":                          "Poor DL channel quality — check antenna tilt/azimuth, MIMO config, inter-cell interference.",
    "SINR_dB":                      "Low SINR — check UL interference (IOT), UE power control, and PRACH configuration.",
    "DL_Throughput_Mbps":           "Low DL throughput — check PRB utilization, CQI, MCS distribution and scheduler.",
    "UL_Throughput_Mbps":           "Low UL throughput — check UL PRB utilization, SINR, and UE transmit power.",
    "Packet_Loss_%":                "High packet loss — check transport/backhaul link quality, GTP OOS counters, and UPF.",
    "Latency_ms":                   "High latency — check backhaul RTT, scheduler queue depth, and buffer bloat.",
}

DEFAULT_REC = "Enable detailed KPI tracing on the affected cell and review gNB logs."


def _severity(value: float, meta: Dict, direction: str) -> str:
    crit = meta.get("critical")
    warn = meta.get("warning")
    if crit is None or warn is None:
        return ""
    if direction == "higher_better":
        if value <= crit:  return "Critical"
        if value <= warn:  return "High"
    else:
        if value >= crit:  return "Critical"
        if value >= warn:  return "High"
    return ""


def _anomaly(kpi: str, cell: str, gnb: str, ts: str,
             value: float, severity: str, detector: str,
             evidence: str) -> Dict[str, Any]:
    meta = get_meta(kpi)
    return {
        "type":           f"{meta.get('label', kpi)} anomaly on {cell}",
        "severity":       severity,
        "score":          round(value, 3),
        "detector":       detector,
        "evidence":       evidence,
        "kpi":            kpi,
        "label":          meta.get("label", kpi),
        "category":       meta.get("category", "Other"),
        "unit":           meta.get("unit", ""),
        "cell_id":        cell,
        "gnb_id":         gnb,
        "timestamp":      ts,
        "value":          round(value, 3),
        "warning":        meta.get("warning"),
        "critical":       meta.get("critical"),
        "recommendation": RECOMMENDATIONS.get(kpi, DEFAULT_REC),
    }


# ═════════════════════════════════════════════════════════════════════
# 1. Threshold Violation Detector
# ═════════════════════════════════════════════════════════════════════

def detect_threshold_violations(parsed_kpi: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check every row against warning/critical thresholds."""
    records   = parsed_kpi.get("df_records", [])
    kpi_cols  = parsed_kpi.get("kpi_columns", [])
    ts_col    = parsed_kpi.get("timestamp_col", "Timestamp")
    cell_col  = parsed_kpi.get("cell_col", "Cell_ID")
    gnb_col   = parsed_kpi.get("gnb_col",  "gNB_ID")
    anomalies = []

    for row in records:
        cell = str(row.get(cell_col, "?"))
        gnb  = str(row.get(gnb_col,  "?"))
        ts   = str(row.get(ts_col,   "?"))

        for kpi in kpi_cols:
            val = row.get(kpi)
            if val is None or not isinstance(val, (int, float)):
                continue
            meta      = get_meta(kpi)
            direction = meta.get("direction", "higher_better")
            sev       = _severity(val, meta, direction)
            if not sev:
                continue

            warn = meta.get("warning")
            crit = meta.get("critical")
            unit = meta.get("unit", "")
            if direction == "higher_better":
                ev = (f"{meta.get('label',kpi)}={val:.2f}{unit} "
                      f"< {'critical' if sev=='Critical' else 'warning'} "
                      f"threshold {crit if sev=='Critical' else warn}{unit}")
            else:
                ev = (f"{meta.get('label',kpi)}={val:.2f}{unit} "
                      f"> {'critical' if sev=='Critical' else 'warning'} "
                      f"threshold {crit if sev=='Critical' else warn}{unit}")

            anomalies.append(_anomaly(kpi, cell, gnb, ts, val, sev,
                                      "Threshold", ev))

    logger.info(f"Threshold violations: {len(anomalies)}")
    return anomalies


# ═════════════════════════════════════════════════════════════════════
# 2. Peer Comparison — cells below fleet average by > 2 std
# ═════════════════════════════════════════════════════════════════════

def detect_peer_outliers(parsed_kpi: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flag cells whose KPI mean is > 2 std below/above the fleet mean."""
    records  = parsed_kpi.get("df_records", [])
    kpi_cols = parsed_kpi.get("kpi_columns", [])
    cell_col = parsed_kpi.get("cell_col", "Cell_ID")
    gnb_col  = parsed_kpi.get("gnb_col",  "gNB_ID")
    anomalies = []

    if not records:
        return []

    df = pd.DataFrame(records)

    for kpi in kpi_cols:
        if kpi not in df.columns:
            continue
        meta      = get_meta(kpi)
        direction = meta.get("direction", "higher_better")
        unit      = meta.get("unit", "")

        # Per-cell mean
        cell_means = df.groupby(cell_col)[kpi].mean()
        fleet_mean = cell_means.mean()
        fleet_std  = cell_means.std()
        if fleet_std == 0 or np.isnan(fleet_std):
            continue

        z_scores = (cell_means - fleet_mean) / fleet_std

        for cell, z in z_scores.items():
            # Outlier depends on direction
            if direction == "higher_better" and z < -2.0:
                val  = cell_means[cell]
                sev  = "High" if z < -3.0 else "Medium"
                gnb  = df[df[cell_col] == cell][gnb_col].iloc[0] if gnb_col in df else "?"
                ev   = (f"{meta.get('label',kpi)} cell_mean={val:.2f}{unit} "
                        f"vs fleet_mean={fleet_mean:.2f}{unit} "
                        f"(z={z:.2f}, {abs(z):.1f}σ below fleet)")
                anomalies.append(_anomaly(kpi, str(cell), str(gnb), "fleet-avg",
                                         val, sev, "Peer Comparison", ev))
            elif direction == "lower_better" and z > 2.0:
                val  = cell_means[cell]
                sev  = "High" if z > 3.0 else "Medium"
                gnb  = df[df[cell_col] == cell][gnb_col].iloc[0] if gnb_col in df else "?"
                ev   = (f"{meta.get('label',kpi)} cell_mean={val:.2f}{unit} "
                        f"vs fleet_mean={fleet_mean:.2f}{unit} "
                        f"(z={z:.2f}, {abs(z):.1f}σ above fleet)")
                anomalies.append(_anomaly(kpi, str(cell), str(gnb), "fleet-avg",
                                         val, sev, "Peer Comparison", ev))

    logger.info(f"Peer outliers: {len(anomalies)}")
    return anomalies


# ═════════════════════════════════════════════════════════════════════
# 3. Trend Detector — linear regression slope over time
# ═════════════════════════════════════════════════════════════════════

def detect_trends(parsed_kpi: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Flag KPIs with a statistically significant degrading trend across
    the full dataset (slope threshold: |slope| > 0.5 per hour).
    """
    records  = parsed_kpi.get("df_records", [])
    kpi_cols = parsed_kpi.get("kpi_columns", [])
    ts_col   = parsed_kpi.get("timestamp_col", "Timestamp")
    anomalies = []

    if not records or not ts_col:
        return []

    df = pd.DataFrame(records)
    if ts_col not in df.columns:
        return []

    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col]).sort_values(ts_col)
    if len(df) < 5:
        return []

    # Convert timestamp to hours since start (numeric x-axis)
    t0         = df[ts_col].min()
    df["_hrs"] = (df[ts_col] - t0).dt.total_seconds() / 3600.0

    for kpi in kpi_cols:
        if kpi not in df.columns:
            continue
        series = df[["_hrs", kpi]].dropna()
        if len(series) < 5:
            continue

        x = series["_hrs"].values
        y = series[kpi].values
        slope, intercept = np.polyfit(x, y, 1)

        meta      = get_meta(kpi)
        direction = meta.get("direction", "higher_better")
        unit      = meta.get("unit", "")

        # A degrading slope for higher_better = negative slope
        # A degrading slope for lower_better  = positive slope
        degrading = (
            (direction == "higher_better" and slope < -0.5) or
            (direction == "lower_better"  and slope >  0.5)
        )
        if not degrading:
            continue

        start_val = float(np.polyval([slope, intercept], x.min()))
        end_val   = float(np.polyval([slope, intercept], x.max()))
        delta     = abs(end_val - start_val)
        sev       = "High" if abs(slope) > 2.0 else "Medium"

        ev = (f"{meta.get('label',kpi)}: slope={slope:+.3f}{unit}/hr "
              f"over {x.max():.1f}hrs "
              f"(est. {start_val:.2f}→{end_val:.2f}{unit}, Δ={delta:.2f})")

        anomalies.append({
            "type":           f"{meta.get('label',kpi)} degrading trend",
            "severity":       sev,
            "score":          round(abs(slope), 3),
            "detector":       "Trend (linear regression)",
            "evidence":       ev,
            "kpi":            kpi,
            "label":          meta.get("label", kpi),
            "category":       meta.get("category", "Other"),
            "unit":           unit,
            "cell_id":        "Fleet-wide",
            "gnb_id":         "All",
            "timestamp":      "trend",
            "value":          round(slope, 4),
            "warning":        meta.get("warning"),
            "critical":       meta.get("critical"),
            "recommendation": RECOMMENDATIONS.get(kpi, DEFAULT_REC),
        })

    logger.info(f"Trend anomalies: {len(anomalies)}")
    return anomalies


# ═════════════════════════════════════════════════════════════════════
# 4. IQR Outlier Detector (Tukey Fence)
# ═════════════════════════════════════════════════════════════════════

def detect_iqr_outliers(parsed_kpi: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Tukey IQR fence: flag rows outside [Q1 - 1.5·IQR, Q3 + 1.5·IQR].

    WHY: Threshold detection uses fixed operator limits; z-score assumes
    Gaussian distribution. IQR makes NO distribution assumption and is
    robust to skew — PRB utilization is right-skewed, CQI during
    interference is left-skewed. Catches outliers the other methods miss
    without needing thresholds to be pre-configured.

    Deduplication: one alert per (kpi, cell) — most severe violation only.
    """
    records  = parsed_kpi.get("df_records", [])
    kpi_cols = parsed_kpi.get("kpi_columns", [])
    ts_col   = parsed_kpi.get("timestamp_col", "Timestamp")
    cell_col = parsed_kpi.get("cell_col", "Cell_ID")
    gnb_col  = parsed_kpi.get("gnb_col", "gNB_ID")
    anomalies: List[Dict[str, Any]] = []

    if not records:
        return []

    df = pd.DataFrame(records)

    for kpi in kpi_cols:
        if kpi not in df.columns:
            continue

        vals = df[kpi].dropna()
        if len(vals) < 4:
            continue

        meta      = get_meta(kpi)
        direction = meta.get("direction", "higher_better")
        unit      = meta.get("unit", "")

        q1  = vals.quantile(0.25)
        q3  = vals.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue

        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr

        # Collect worst violation per cell
        cell_worst: Dict[str, Dict] = {}
        for _, row in df.iterrows():
            val = row.get(kpi)
            if val is None or not isinstance(val, (int, float)) or pd.isna(val):
                continue

            cell = str(row.get(cell_col, "?"))
            gnb  = str(row.get(gnb_col,  "?"))
            ts   = str(row.get(ts_col,   "?"))

            flagged = False
            if direction == "higher_better" and val < lower_fence:
                flagged = True
                sev = "High" if val < (lower_fence - iqr) else "Medium"
                dev = lower_fence - val
                ev  = (f"{meta.get('label',kpi)}={val:.2f}{unit} below lower fence "
                       f"{lower_fence:.2f}{unit} (Q1={q1:.2f}, IQR={iqr:.2f}, dev={dev:.2f})")
            elif direction == "lower_better" and val > upper_fence:
                flagged = True
                sev = "High" if val > (upper_fence + iqr) else "Medium"
                dev = val - upper_fence
                ev  = (f"{meta.get('label',kpi)}={val:.2f}{unit} above upper fence "
                       f"{upper_fence:.2f}{unit} (Q3={q3:.2f}, IQR={iqr:.2f}, dev={dev:.2f})")
            else:
                flagged = False

            if flagged:
                if cell not in cell_worst or dev > cell_worst[cell]["dev"]:
                    cell_worst[cell] = dict(
                        val=val, sev=sev, ev=ev, gnb=gnb, ts=ts, dev=dev
                    )

        for cell, w in cell_worst.items():
            anomalies.append(
                _anomaly(kpi, cell, w["gnb"], w["ts"], w["val"],
                         w["sev"], "IQR (Tukey fence)", w["ev"])
            )

    logger.info(f"IQR outliers: {len(anomalies)}")
    return anomalies


# ═════════════════════════════════════════════════════════════════════
# 5. CUSUM — Cumulative Sum Change-Point Detection
# ═════════════════════════════════════════════════════════════════════

def detect_cusum(parsed_kpi: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Two-sided CUSUM control chart per (KPI, cell).

    WHY: Threshold, IQR and Peer Comparison all detect point-in-time
    violations. CUSUM accumulates small consistent deviations that are
    individually below any threshold but collectively signal a real shift
    (e.g. RRC SR quietly dropping from 99.5% → 98.2% over 10 intervals).
    This is the standard method in telecom NOC for early degradation warning.

    Parameters (industry standard):
      k = 0.5σ  — slack (ignore noise within half a std)
      h = 5σ    — alarm threshold (triggers after sustained drift)

    One alert per (kpi, cell) — first trigger point only.
    """
    records  = parsed_kpi.get("df_records", [])
    kpi_cols = parsed_kpi.get("kpi_columns", [])
    ts_col   = parsed_kpi.get("timestamp_col", "Timestamp")
    cell_col = parsed_kpi.get("cell_col", "Cell_ID")
    gnb_col  = parsed_kpi.get("gnb_col", "gNB_ID")
    anomalies: List[Dict[str, Any]] = []

    if not records or not ts_col:
        return []

    df = pd.DataFrame(records)
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col]).sort_values(ts_col)

    K = 0.5    # slack parameter (multiples of σ)
    H = 5.0    # alarm threshold (multiples of σ)

    for kpi in kpi_cols:
        if kpi not in df.columns:
            continue

        meta      = get_meta(kpi)
        direction = meta.get("direction", "higher_better")
        unit      = meta.get("unit", "")

        for cell, grp in df.groupby(cell_col):
            series = grp[[ts_col, kpi] + ([gnb_col] if gnb_col in grp else [])].dropna(subset=[kpi])
            if len(series) < 5:
                continue

            vals  = series[kpi].values
            mu    = vals.mean()
            sigma = vals.std()
            if sigma == 0:
                continue

            cusum_pos = 0.0
            cusum_neg = 0.0
            gnb = str(series[gnb_col].iloc[0]) if gnb_col in series else "?"

            for i, val in enumerate(vals):
                z = (val - mu) / sigma
                cusum_pos = max(0.0, cusum_pos + z - K)
                cusum_neg = max(0.0, cusum_neg - z - K)

                drift = ""
                if direction == "higher_better" and cusum_neg > H:
                    drift = "sustained downward drift"
                elif direction == "lower_better" and cusum_pos > H:
                    drift = "sustained upward drift"
                elif cusum_pos > H * 2:
                    drift = "extreme upward drift"
                elif cusum_neg > H * 2:
                    drift = "extreme downward drift"

                if drift:
                    ts  = str(series[ts_col].iloc[i])
                    sev = "High" if max(cusum_pos, cusum_neg) > H * 2 else "Medium"
                    ev  = (f"{meta.get('label',kpi)}: CUSUM {drift}; "
                           f"S+={cusum_pos:.2f}, S-={cusum_neg:.2f} > h={H}σ; "
                           f"val={val:.2f}{unit}, μ={mu:.2f}{unit}, σ={sigma:.2f}")
                    anomalies.append(
                        _anomaly(kpi, str(cell), gnb, ts, val, sev, "CUSUM", ev)
                    )
                    break  # one alert per (kpi, cell)

    logger.info(f"CUSUM anomalies: {len(anomalies)}")
    return anomalies


# ═════════════════════════════════════════════════════════════════════
# 6. Bollinger Bands — Rolling Mean ± 2σ Envelope
# ═════════════════════════════════════════════════════════════════════

def detect_bollinger_bands(parsed_kpi: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Rolling window mean ± 2σ envelope per (KPI, cell).

    WHY: Linear regression (Trend detector) catches monotonic long-term
    degradation. CUSUM catches sustained drift. Bollinger Bands catch
    SHORT-TERM spikes and sudden drops — e.g. a momentary PRB spike to
    95% in a normally 40%-loaded cell, or a CQI crash during sudden
    interference. Standard in financial market anomaly detection, proven
    effective for telecom KPI burst detection.

    Window = 5 intervals. One alert per (kpi, cell) — worst violation only.
    """
    records  = parsed_kpi.get("df_records", [])
    kpi_cols = parsed_kpi.get("kpi_columns", [])
    ts_col   = parsed_kpi.get("timestamp_col", "Timestamp")
    cell_col = parsed_kpi.get("cell_col", "Cell_ID")
    gnb_col  = parsed_kpi.get("gnb_col", "gNB_ID")
    anomalies: List[Dict[str, Any]] = []
    WINDOW = 5

    if not records or not ts_col:
        return []

    df = pd.DataFrame(records)
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col]).sort_values(ts_col)

    for kpi in kpi_cols:
        if kpi not in df.columns:
            continue

        meta      = get_meta(kpi)
        direction = meta.get("direction", "higher_better")
        unit      = meta.get("unit", "")

        for cell, grp in df.groupby(cell_col):
            sub = grp.dropna(subset=[kpi]).copy()
            if len(sub) < WINDOW + 1:
                continue

            # Lag by 1 so the current value never inflates its own band
            lagged = sub[kpi].shift(1)
            sub["_rm"]   = lagged.rolling(WINDOW, min_periods=3).mean()
            sub["_rstd"] = lagged.rolling(WINDOW, min_periods=3).std().clip(lower=0.5)
            sub["_ub"]   = sub["_rm"] + 2 * sub["_rstd"]
            sub["_lb"]   = sub["_rm"] - 2 * sub["_rstd"]

            worst_dev  = 0.0
            worst_row: Dict = {}
            gnb = str(grp[gnb_col].iloc[0]) if gnb_col in grp else "?"

            for _, row in sub.iterrows():
                val = row[kpi]
                ub  = row["_ub"]
                lb  = row["_lb"]
                rm  = row["_rm"]
                rs  = row["_rstd"]
                if pd.isna(ub) or pd.isna(lb) or rs == 0:
                    continue

                dev = 0.0
                if direction == "higher_better" and val < lb:
                    dev = lb - val
                    sev = "High" if dev > rs else "Medium"
                    ev  = (f"{meta.get('label',kpi)}={val:.2f}{unit} below lower band "
                           f"{lb:.2f}{unit} (rolling μ={rm:.2f}±{rs:.2f}, window={WINDOW})")
                elif direction == "lower_better" and val > ub:
                    dev = val - ub
                    sev = "High" if dev > rs else "Medium"
                    ev  = (f"{meta.get('label',kpi)}={val:.2f}{unit} above upper band "
                           f"{ub:.2f}{unit} (rolling μ={rm:.2f}±{rs:.2f}, window={WINDOW})")
                else:
                    continue

                if dev > worst_dev:
                    worst_dev = dev
                    worst_row = dict(val=val, sev=sev, ev=ev,
                                     ts=str(row[ts_col]))

            if worst_row:
                anomalies.append(
                    _anomaly(kpi, str(cell), gnb, worst_row["ts"],
                             worst_row["val"], worst_row["sev"],
                             "Bollinger Bands", worst_row["ev"])
                )

    logger.info(f"Bollinger Bands anomalies: {len(anomalies)}")
    return anomalies


# ═════════════════════════════════════════════════════════════════════
# Orchestrator
# ═════════════════════════════════════════════════════════════════════

# Ordered registry — name → function
KPI_DETECTORS = [
    ("Threshold",      detect_threshold_violations),
    ("Peer Comparison",detect_peer_outliers),
    ("Trend",          detect_trends),
    ("IQR",            detect_iqr_outliers),
    ("CUSUM",          detect_cusum),
    ("Bollinger Bands",detect_bollinger_bands),
]


def detect_kpi_anomalies_by_detector(
    parsed_kpi: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Run every KPI detector independently.
    Returns {detector_name: [anomalies]} for the comparison matrix.
    """
    results: Dict[str, List[Dict[str, Any]]] = {}
    for name, fn in KPI_DETECTORS:
        try:
            found = fn(parsed_kpi)
            logger.info(f"KPI {name}: {len(found)} anomalies")
            results[name] = found
        except Exception as e:
            logger.warning(f"KPI {name} failed: {e}")
            results[name] = []
    return results


def detect_kpi_anomalies(parsed_kpi: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run all six KPI detectors, merge, sort by severity."""
    all_anoms: List[Dict[str, Any]] = []
    for _, fn in KPI_DETECTORS:
        try:
            all_anoms.extend(fn(parsed_kpi))
        except Exception as e:
            logger.warning(f"KPI detector failed: {e}")

    all_anoms.sort(
        key=lambda a: (SEV_RANK.get(a["severity"], 0), a.get("score", 0)),
        reverse=True,
    )
    logger.info(f"Total KPI anomalies: {len(all_anoms)}")
    return all_anoms


def kpi_summary_table(parsed_kpi: Dict[str, Any]) -> List[Dict]:
    """
    Build a per-KPI summary row for the dashboard table.
    Includes traffic-light status based on mean vs thresholds.
    """
    summary = parsed_kpi.get("summary", {})
    rows = []
    for kpi, s in summary.items():
        mean      = s["mean"]
        direction = s.get("direction", "higher_better")
        warn      = s.get("warning")
        crit      = s.get("critical")

        if warn is None:
            status = "ℹ️"
        elif direction == "higher_better":
            status = "🔴" if mean <= crit else ("🟡" if mean <= warn else "🟢")
        else:
            status = "🔴" if mean >= crit else ("🟡" if mean >= warn else "🟢")

        rows.append({
            "Status":   status,
            "KPI":      s.get("label", kpi),
            "Category": s.get("category", "Other"),
            "Unit":     s.get("unit", ""),
            "Min":      s["min"],
            "Max":      s["max"],
            "Mean":     round(s["mean"], 2),
            "P10":      s["p10"],
            "P90":      s["p90"],
            "Warning":  warn,
            "Critical": crit,
        })

    rows.sort(key=lambda r: (r["Status"] == "🔴", r["Status"] == "🟡"), reverse=True)
    return rows
