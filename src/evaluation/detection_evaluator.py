"""
Detection evaluator — runs 5 method variants and returns flagged cell sets.

Method definitions:
  1. threshold_only             — Threshold detector only (KPI domain, any violation)
  2. single_method_iqr          — IQR detector only (KPI domain, any violation)
  3. full_ensemble              — All 6 KPI + 6 Stats detectors; flag if ANY fires
  4. ensemble_with_router       — Full ensemble + EventRouter cross-source (≥2 sources)
  5. stats_count_threshold      — Stats domain; flag cells above mean + 1.5*std anomaly count
                                  (data-driven, no post-hoc tuning)

Dataset note — FDD/TDD KPI bias:
  FDD cells (PCI_9-16) generate ~727 KPI threshold anomalies vs ~163 for TDD
  normal cells (PCI_1-7), due to different channel capacity and threshold
  calibration in the generator. All FDD cells therefore appear as KPI outliers
  alongside the actual fault cells, causing high FP in KPI-only methods.
  The Stats-domain count-threshold (Method 5) is unaffected by this bias.

PCAP isolation-forest note:
  The synthetic ue_64_6hr.pcap has no cell_id IE in packet payloads
  (synthetic single-byte discriminator format). The PCAP IsolationForestDetector
  cannot produce cell-level flags from this dataset. This is an honest
  limitation documented here.
"""

import logging
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


def _cells_flagged_by_detector(
    by_detector: Dict[str, List[Dict[str, Any]]],
    detector_name: str,
    cell_col_key: str = "cell_id",
) -> Set[str]:
    """Extract the set of cells flagged by one named detector."""
    anomalies = by_detector.get(detector_name, [])
    cells = set()
    for a in anomalies:
        c = str(a.get(cell_col_key, "")).strip()
        # Skip fleet-wide / non-cell entries
        if c and c not in ("", "?", "Fleet-wide", "—", "nan"):
            cells.add(c)
    return cells


def run_method_threshold_only(
    kpi_parsed: Dict[str, Any],
    stats_parsed: Dict[str, Any] = None,
) -> Set[str]:
    """
    Method 1: Threshold detector only on KPI data.
    Returns the set of cells that have at least one Threshold anomaly.
    """
    from src.detection.kpi_detector import detect_kpi_anomalies_by_detector
    by_det = detect_kpi_anomalies_by_detector(kpi_parsed)
    cells = _cells_flagged_by_detector(by_det, "Threshold")
    logger.info(f"[threshold_only] flagged cells: {sorted(cells)}")
    return cells


def run_method_single_iqr(
    kpi_parsed: Dict[str, Any],
    stats_parsed: Dict[str, Any] = None,
) -> Set[str]:
    """
    Method 2: IQR detector only on KPI data (distribution-based single method).
    IQR (Tukey fence) is distribution-free — closest analogue to Isolation
    Forest in spirit without requiring sklearn or PCAP cell IDs.
    Returns the set of cells with at least one IQR anomaly.
    """
    from src.detection.kpi_detector import detect_kpi_anomalies_by_detector
    by_det = detect_kpi_anomalies_by_detector(kpi_parsed)
    cells = _cells_flagged_by_detector(by_det, "IQR")
    logger.info(f"[single_method_iqr] flagged cells: {sorted(cells)}")
    return cells


def run_method_full_ensemble(
    kpi_parsed: Dict[str, Any],
    stats_parsed: Dict[str, Any],
) -> Set[str]:
    """
    Method 3: All 6 KPI detectors + all 6 Stats detectors.
    A cell is flagged if ANY detector from either domain flags it.
    Returns union of all flagged cells.
    """
    from src.detection.kpi_detector import detect_kpi_anomalies_by_detector
    from src.detection.stats_detector import detect_stats_anomalies_by_detector

    kpi_by_det   = detect_kpi_anomalies_by_detector(kpi_parsed)
    stats_by_det = detect_stats_anomalies_by_detector(stats_parsed)

    cells: Set[str] = set()

    # KPI anomalies — cell_id key
    for anoms in kpi_by_det.values():
        for a in anoms:
            c = str(a.get("cell_id", "")).strip()
            if c and c not in ("", "?", "Fleet-wide", "—", "nan"):
                cells.add(c)

    # Stats anomalies — also cell_id key
    for anoms in stats_by_det.values():
        for a in anoms:
            c = str(a.get("cell_id", "")).strip()
            if c and c not in ("", "?", "Fleet-wide", "—", "nan"):
                cells.add(c)

    logger.info(f"[full_ensemble] flagged cells: {sorted(cells)}")
    return cells


def run_method_ensemble_with_router(
    kpi_parsed: Dict[str, Any],
    stats_parsed: Dict[str, Any],
) -> Set[str]:
    """
    Method 4: Full ensemble (KPI + Stats) fed through EventRouter.
    A cell qualifies ONLY if correlated events appear from ≥2 source domains.
    This is the cross-source correlation baseline.
    Returns the set of cross-source correlated cells.
    """
    from src.detection.kpi_detector import detect_kpi_anomalies
    from src.detection.stats_detector import detect_stats_anomalies
    from src.orchestrator.event_router import EventRouter

    kpi_anoms   = detect_kpi_anomalies(kpi_parsed)
    stats_anoms = detect_stats_anomalies(stats_parsed)

    router = EventRouter()
    router.ingest(kpi_anoms,   source="kpi")
    router.ingest(stats_anoms, source="stats")

    correlated = router.get_correlated(min_sources=2)
    cells: Set[str] = set()
    for ev in correlated:
        c = str(ev.get("cell_id", "")).strip()
        if c and c not in ("", "?", "—", "nan"):
            cells.add(c)

    logger.info(f"[ensemble_with_router] correlated cells: {sorted(cells)}")
    return cells, router


def run_method_stats_count_threshold(
    stats_parsed: Dict[str, Any],
    kpi_parsed: Dict[str, Any] = None,
    z_factor: float = 1.5,
) -> Set[str]:
    """
    Method 5: Stats anomaly count with data-driven threshold.

    For each cell, count total anomalies across all 6 Stats detectors.
    Flag cells whose count exceeds (mean + z_factor * std) of the fleet.
    This threshold is computed from the data itself — no manual tuning.

    Stats detectors are less affected by the FDD/TDD capacity difference
    that inflates KPI threshold counts on FDD normal cells.

    Parameters
    ----------
    z_factor : float
        Number of standard deviations above mean to set the threshold.
        Default 1.5 is standard for outlier detection (not fitted to labels).
    """
    import numpy as np
    from collections import Counter
    from src.detection.stats_detector import detect_stats_anomalies_by_detector

    stats_by_det = detect_stats_anomalies_by_detector(stats_parsed)

    # Count anomalies per cell across all detectors
    cell_counts: Counter = Counter()
    for det_anoms in stats_by_det.values():
        for a in det_anoms:
            c = str(a.get("cell_id", "")).strip()
            if c and c not in ("", "?", "Fleet-wide", "—", "nan"):
                cell_counts[c] += 1

    if not cell_counts:
        return set()

    counts = np.array(list(cell_counts.values()), dtype=float)
    threshold = counts.mean() + z_factor * counts.std()

    flagged = {cell for cell, cnt in cell_counts.items() if cnt > threshold}

    logger.info(
        f"[stats_count_threshold] fleet mean={counts.mean():.1f} "
        f"std={counts.std():.1f} threshold={threshold:.1f} "
        f"flagged={sorted(flagged)}"
    )
    return flagged
