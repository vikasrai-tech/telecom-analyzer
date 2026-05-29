"""
KPI Detector — anomaly detection on gNB KPI time-series data.

Three detection layers:
  1. Threshold violations  — per-row check against warning/critical levels
  2. Peer comparison       — cells significantly below fleet average
  3. Trend analysis        — KPIs degrading over time (linear regression slope)
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
# Orchestrator
# ═════════════════════════════════════════════════════════════════════

def detect_kpi_anomalies(parsed_kpi: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run all three KPI detectors, merge, sort by severity."""
    all_anoms = []
    all_anoms.extend(detect_threshold_violations(parsed_kpi))
    all_anoms.extend(detect_peer_outliers(parsed_kpi))
    all_anoms.extend(detect_trends(parsed_kpi))

    # Sort: Critical → High → Medium → Low, then by value deviation
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
