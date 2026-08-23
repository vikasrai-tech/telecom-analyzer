"""
Capacity-aware throughput normalization for KPI anomaly detection.

PROBLEM BEING SOLVED
--------------------
The KPI Threshold detector uses global Mbps thresholds calibrated for TDD
cells. FDD cells have a much lower DL capacity, so healthy FDD throughput
continuously fires the TDD-calibrated warning threshold even at normal load.

SOLUTION
--------
For DL/UL throughput KPIs only, normalize observed Mbps to a percentage
of the cell's configured capacity before comparing against thresholds:

    normalized_pct = (observed_Mbps / configured_capacity_Mbps) * 100

This makes thresholds technology-agnostic:
    TDD: 769 Mbps / 1400 Mbps  ≈ 54.9%  (healthy, no alert)
    FDD:  51 Mbps /   84 Mbps  ≈ 60.7%  (healthy, no alert — FIXED)

Normalized thresholds are derived from the original TDD-calibrated Mbps
values divided by confirmed TDD DL capacity (1400 Mbps), so that TDD
detection behavior is algebraically unchanged:
    DL warning:  100/1400 * 100 = 7.1429 %  of capacity
    DL critical:  50/1400 * 100 = 3.5714 %  of capacity
    UL warning:   50/100  * 100 = 50.0   %  of capacity
    UL critical:  20/100  * 100 = 20.0   %  of capacity

NON-THROUGHPUT KPIs
-------------------
Cell Availability, RRC Success Rate, Handover Success Rate, and all other
percentage/rate/count KPIs are NOT normalized.

BACKWARD COMPATIBILITY
----------------------
Raw Mbps values are ALWAYS preserved. Normalized values are added alongside:
    raw_value           — original Mbps (unchanged, used for reporting)
    capacity_mbps       — configured cell capacity
    normalized_pct      — (raw / capacity) * 100
    normalized_unit     — "% of capacity"

CAPACITY SOURCE — AUTHORITATIVE VALUES (confirmed 2026-08-15)
---------------
    TDD: dl=1400 Mbps, ul=100 Mbps
    FDD: dl=84   Mbps, ul=50  Mbps

These values are read from the Channel_Type column in each KPI row
and must stay in sync with scripts/_ue64_config.py CAPACITY dict.
If Channel_Type is absent from a row, no normalization is applied.
"""

import logging
import math
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Channel-type → configured capacity (Mbps) ────────────────────────────────
# AUTHORITATIVE values — confirmed 2026-08-15.
# Must stay in sync with scripts/_ue64_config.py CAPACITY dict.
# TDD: DL=1400, UL=100   |   FDD: DL=84, UL=50
CHANNEL_TYPE_CAPACITY: Dict[str, Dict[str, float]] = {
    "TDD": {"dl": 1400.0, "ul": 100.0},
    "FDD": {"dl": 84.0, "ul": 50.0},
}

# ── Throughput KPI classification ─────────────────────────────────────────────
# Maps canonical KPI column name → "dl" or "ul" direction.
# Only KPIs listed here receive capacity normalization; everything else
# passes through unchanged.
THROUGHPUT_KPI_TYPE: Dict[str, str] = {
    "DL_Throughput_Mbps": "dl",
    "UL_Throughput_Mbps": "ul",
    "Cell_MAC_DL_Throughput_Mbps": "dl",
    "Cell_MAC_UL_Throughput_Mbps": "ul",
}

# ── Normalized thresholds (% of capacity) ────────────────────────────────────
# Derived from original TDD-calibrated Mbps thresholds / confirmed TDD capacity:
#   DL warning:  100 Mbps / 1400 Mbps * 100 = 7.1429 %
#   DL critical:  50 Mbps / 1400 Mbps * 100 = 3.5714 %
#   UL warning:   50 Mbps /  100 Mbps * 100 = 50.0   %
#   UL critical:  20 Mbps /  100 Mbps * 100 = 20.0   %
# TDD alert behavior is algebraically unchanged (same Mbps / same TDD capacity).
# FDD receives proportionally equivalent thresholds relative to FDD capacity.
_TDD_DL_CAP = CHANNEL_TYPE_CAPACITY["TDD"]["dl"]   # 1400.0
_TDD_UL_CAP = CHANNEL_TYPE_CAPACITY["TDD"]["ul"]   # 100.0
NORMALIZED_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "dl": {
        "warning": round(100.0 / _TDD_DL_CAP * 100, 4),   # 7.1429 %
        "critical": round(50.0 / _TDD_DL_CAP * 100, 4),   # 3.5714 %
    },
    "ul": {
        "warning": round(50.0 / _TDD_UL_CAP * 100, 4),   # 50.0 %
        "critical": round(20.0 / _TDD_UL_CAP * 100, 4),   # 20.0 %
    },
}


def get_cell_capacity(channel_type: Optional[str]) -> Optional[Dict[str, float]]:
    """
    Return {dl: Mbps, ul: Mbps} for a given Channel_Type string, or None
    if the type is unrecognised or missing.

    Parameters
    ----------
    channel_type : str or None
        Value from the Channel_Type column ("TDD", "FDD", etc.).

    Returns
    -------
    dict with 'dl' and 'ul' capacity in Mbps, or None.
    """
    if not channel_type:
        return None
    cap = CHANNEL_TYPE_CAPACITY.get(str(channel_type).strip().upper())
    if cap is None:
        logger.debug(f"Unknown channel_type '{channel_type}' — no capacity normalization")
    return cap


def build_capacity_map(
    df_records: list,
    cell_col: str = "Cell_ID",
    channel_type_col: str = "Channel_Type",
) -> Dict[str, Dict[str, float]]:
    """
    Build a mapping {cell_id: {dl: Mbps, ul: Mbps}} from df_records.

    Reads the Channel_Type column to determine capacity for each cell.
    Cells without a Channel_Type column are omitted from the map.

    Parameters
    ----------
    df_records : list of dicts
        Raw records from parse_kpi_file()["df_records"].
    cell_col : str
        Column name for cell identifier.
    channel_type_col : str
        Column name for channel type (TDD/FDD).

    Returns
    -------
    dict: {cell_id: {"dl": float, "ul": float}}
    """
    capacity_map: Dict[str, Dict[str, float]] = {}
    for row in df_records:
        cell = str(row.get(cell_col, "")).strip()
        if not cell or cell in capacity_map:
            continue
        ctype = row.get(channel_type_col)
        cap = get_cell_capacity(ctype)
        if cap is not None:
            capacity_map[cell] = cap
    logger.debug(f"Built capacity map for {len(capacity_map)} cells: {list(capacity_map)[:4]}…")
    return capacity_map


def normalize_throughput(
    kpi_name: str,
    raw_value: float,
    cell_id: str,
    capacity_map: Dict[str, Dict[str, float]],
) -> Optional[Dict[str, Any]]:
    """
    Normalize a single throughput KPI value to a percentage of cell capacity.

    Parameters
    ----------
    kpi_name : str
        Canonical KPI column name (e.g. "DL_Throughput_Mbps").
    raw_value : float
        Observed throughput in Mbps.
    cell_id : str
        Cell identifier used to look up capacity.
    capacity_map : dict
        Output of build_capacity_map().

    Returns
    -------
    dict with keys:
        raw_value       — original Mbps (unchanged)
        capacity_mbps   — configured capacity for this cell
        normalized_pct  — raw_value / capacity_mbps * 100
        normalized_unit — "%"
        direction       — "dl" or "ul"
        thresholds      — {"warning": float, "critical": float} in %
    or None if:
        - kpi_name is not a throughput KPI
        - cell capacity is unknown
        - capacity is 0 or invalid

    The caller decides whether to use raw_value (for reporting) or
    normalized_pct (for threshold comparison).
    """
    direction = THROUGHPUT_KPI_TYPE.get(kpi_name)
    if direction is None:
        return None  # not a throughput KPI — no normalization

    cap = capacity_map.get(cell_id)
    if cap is None:
        logger.debug(f"No capacity for cell '{cell_id}' — skipping normalization of {kpi_name}")
        return None

    cap_mbps = cap.get(direction, 0.0)
    if not cap_mbps or cap_mbps <= 0:
        logger.warning(f"Invalid capacity {cap_mbps} Mbps for cell {cell_id} ({direction}) — skipping")
        return None

    normalized_pct = (raw_value / cap_mbps) * 100.0

    return {
        "raw_value": raw_value,
        "capacity_mbps": cap_mbps,
        "normalized_pct": round(normalized_pct, 4),
        "normalized_unit": "% of capacity",
        "direction": direction,
        "thresholds": NORMALIZED_THRESHOLDS[direction],
    }


def normalized_severity(normalized_pct: float, direction: str) -> str:
    """
    Compute severity from a normalized throughput percentage.

    Throughput is higher_better so alerts fire when value is TOO LOW.

    Parameters
    ----------
    normalized_pct : float
        (raw_Mbps / capacity_Mbps) * 100.
    direction : str
        "dl" or "ul".

    Returns
    -------
    "Critical", "High", or "" (no alert).
    """
    t = NORMALIZED_THRESHOLDS.get(direction, {})
    crit = t.get("critical", 0.0)
    warn = t.get("warning", 0.0)
    if normalized_pct <= crit:
        return "Critical"
    if normalized_pct <= warn:
        return "High"
    return ""


def is_throughput_kpi(kpi_name: str) -> bool:
    """Return True if this KPI receives capacity normalization."""
    return kpi_name in THROUGHPUT_KPI_TYPE


# ═══════════════════════════════════════════════════════════════════════════════
# Load-aware UL threshold
# ═══════════════════════════════════════════════════════════════════════════════
#
# PROBLEM BEING SOLVED
# --------------------
# The fixed UL warning (50 % of capacity) fires at any off-peak interval:
#   TDD off-peak UL ≈ 24.5 Mbps = 24.5 % of 100 Mbps cap  (<50 % → alert)
#   FDD off-peak UL ≈ 12.2 Mbps = 24.4 % of  50 Mbps cap  (<50 % → alert)
# Both are legitimate low-load operating points, not faults.
#
# SOLUTION
# --------
# Use PRB_Utilization_UL_% (already in every KPI row) as the load signal.
# Expected UL throughput ∝ PRB_UL.  Alert only when actual UL is much lower
# than PRB allocation suggests:
#
#   efficiency = ul_norm_pct / PRB_UL_pct         (data: normal ≈ 1.07 ± 0.18)
#   dynamic_warning  = max(FLOOR_WARN, PRB_UL × EFFICIENCY_WARN)
#   dynamic_critical = max(FLOOR_CRIT, PRB_UL × EFFICIENCY_CRIT)
#
# DATA JUSTIFICATION (kpi_64ue_6hr.csv, 5760 rows, 16 cells)
# -----------------------------------------------------------
#   Normal cells:   efficiency 25th pct ≈ 0.95, min ≈ 0.28 (rare noise)
#   PCI_3 congestion (high PRB): efficiency 0.17–0.25 → caught by CRIT (0.20)
#   PCI_12 outage:  PRB_UL < 5 % → fallback absolute floor (UL_norm 0.36 %)
#   Normal cells UL_norm min ≈ 8–17 % → always above 5 % FLOOR_WARN
#
# BACKWARD COMPATIBILITY
# ----------------------
# At PRB_UL = 100 %:
#   dynamic_warning  = 100 × 0.50 = 50 % — same as former fixed warning
#   dynamic_critical = 100 × 0.20 = 20 % — same as former fixed critical
# DL throughput and all non-throughput KPIs are UNCHANGED.
# ═══════════════════════════════════════════════════════════════════════════════

_UL_MIN_PRB_FOR_CHECK: float = 5.0
_UL_EFFICIENCY_WARN: float = 0.50
_UL_EFFICIENCY_CRIT: float = 0.20
_UL_FLOOR_WARN_PCT: float = 5.0
_UL_FLOOR_CRIT_PCT: float = 2.0


def load_aware_ul_severity(
    normalized_pct: float,
    prb_ul_pct: Optional[float],
) -> Tuple[str, str]:
    """
    Return (severity, evidence_note) for a UL normalized throughput value.

    severity     : "Critical", "High", or "" (no alert)
    evidence_note: human-readable explanation appended to the anomaly evidence

    PRB-conditioned path (when PRB_UL >= 5 %)
    -----------------------------------------
    dynamic_warning  = max(_UL_FLOOR_WARN_PCT, prb_ul × _UL_EFFICIENCY_WARN)
    dynamic_critical = max(_UL_FLOOR_CRIT_PCT, prb_ul × _UL_EFFICIENCY_CRIT)

    Absolute-floor fallback (PRB_UL missing, < 5 %, NaN, or out-of-range)
    ----------------------------------------------------------------------
    Catches near-idle cells and outage events where PRB collapses alongside UL.
    Only flags when UL is catastrophically low (< 5 % warning, < 2 % critical).
    """
    use_prb = False
    prb_val: float = 0.0
    try:
        if prb_ul_pct is not None:
            v = float(prb_ul_pct)
            if not math.isnan(v) and 0.0 <= v <= 200.0 and v >= _UL_MIN_PRB_FOR_CHECK:
                use_prb = True
                prb_val = v
    except (TypeError, ValueError):
        pass

    if use_prb:
        efficiency = normalized_pct / prb_val
        dyn_warn = max(_UL_FLOOR_WARN_PCT, prb_val * _UL_EFFICIENCY_WARN)
        dyn_crit = max(_UL_FLOOR_CRIT_PCT, prb_val * _UL_EFFICIENCY_CRIT)

        if normalized_pct <= dyn_crit:
            note = (
                f"UL efficiency={efficiency:.3f} "
                f"(actual {normalized_pct:.1f}% < load-critical {dyn_crit:.1f}% "
                f"at PRB_UL={prb_val:.1f}%)"
            )
            return "Critical", note

        if normalized_pct <= dyn_warn:
            note = (
                f"UL efficiency={efficiency:.3f} "
                f"(actual {normalized_pct:.1f}% < load-warning {dyn_warn:.1f}% "
                f"at PRB_UL={prb_val:.1f}%)"
            )
            return "High", note

        return "", ""

    # ── Fallback: absolute floor ──────────────────────────────────────────────
    prb_tag = "N/A" if prb_ul_pct is None else f"{prb_ul_pct}"
    if normalized_pct <= _UL_FLOOR_CRIT_PCT:
        note = (
            f"UL={normalized_pct:.1f}% below absolute critical floor "
            f"{_UL_FLOOR_CRIT_PCT:.1f}% (PRB_UL={prb_tag}, fallback path)"
        )
        return "Critical", note
    if normalized_pct <= _UL_FLOOR_WARN_PCT:
        note = (
            f"UL={normalized_pct:.1f}% below absolute warning floor "
            f"{_UL_FLOOR_WARN_PCT:.1f}% (PRB_UL={prb_tag}, fallback path)"
        )
        return "High", note
    return "", ""
