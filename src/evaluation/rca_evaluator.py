"""
RCA evaluator — rule-based root-cause analysis against ground truth.

Evaluates rule_based_root_cause() (no Ollama required) for the 3 injected
fault cells: PCI_3 (congestion), PCI_12 (outage), PCI_8 (drift).

Keyword matching checks whether the rule-based output's root_cause text
contains the expected diagnostic keywords for each fault type.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ── Ground truth RCA expectations ─────────────────────────────────────────────
GROUND_TRUTH_RCA: Dict[str, Dict[str, Any]] = {
    "PCI_3": {
        "trigger_layer":              "KPI",
        "trigger_type":               "congestion",
        "expected_root_cause_keywords": [
            # Fault-specific terms only — generic tokens ('cell', 'layer') excluded
            "congestion", "PRB", "throughput", "utilization", "utilisation",
            "MAC", "HARQ", "scheduling",
        ],
        "description": "DL congestion — high PRB utilisation and RRC/throughput degradation",
    },
    "PCI_12": {
        "trigger_layer":              "KPI",
        "trigger_type":               "outage",
        "expected_root_cause_keywords": [
            # Removed 'cell' (appears in every output by template) and 'avail' (redundant)
            "outage", "availability", "RACH", "failure", "collapse",
        ],
        "description": "Cell outage — Cell_Availability collapse, RACH/NGAP failures",
    },
    "PCI_8": {
        "trigger_layer":              "KPI",
        "trigger_type":               "drift",
        "expected_root_cause_keywords": [
            # Removed 'ho' (2-char substring matches 'should', 'threshold', etc.)
            "drift", "handover", "latency", "trend", "degradation",
        ],
        "description": "Slow drift — Handover success rate and latency gradually degrade",
    },
}


def _check_keyword_match(rca_result: Dict[str, Any], expected_keywords: List[str]) -> Dict[str, Any]:
    """Check if any expected keyword appears in the RCA output text."""
    text_to_search = " ".join([
        rca_result.get("root_cause", ""),
        rca_result.get("recommended_action", ""),
        " ".join(
            hop.get("explanation", "") if isinstance(hop, dict) else ""
            for hop in rca_result.get("causal_chain", [])
        ),
    ]).lower()

    matched = [kw for kw in expected_keywords if kw.lower() in text_to_search]
    return {
        "matched_keywords": matched,
        "total_expected":   len(expected_keywords),
        "keyword_hit_rate": round(len(matched) / len(expected_keywords), 3) if expected_keywords else 0.0,
        "any_match":        len(matched) > 0,
    }


_FLEET_WIDE_SENTINEL = "Fleet-wide"
_MAX_GROUP_SIZE = 5


def build_synthetic_event_group(
    cell_id: str,
    kpi_anomalies: List[Dict[str, Any]],
    stats_anomalies: List[Dict[str, Any]],
    router=None,
) -> List[Dict[str, Any]]:
    """
    Build a correlated event group for a given cell from actual detected anomalies.
    Prioritises high-severity anomalies. Returns at most _MAX_GROUP_SIZE events.

    Router path (preferred)
    -----------------------
    Uses router.get_by_cell(cell_id). If that returns fewer than _MAX_GROUP_SIZE
    events, Fleet-wide events (e.g. from the KPI Trend detector, which emits
    cell_id='Fleet-wide') are appended as supplementary context up to the cap.
    Fleet-wide events are relevant for drift-type faults where the primary signal
    is a fleet-level trend rather than a cell-specific spike.

    Fallback path (router=None or empty)
    -------------------------------------
    Filters kpi_anomalies + stats_anomalies by cell_id. Also includes Fleet-wide
    anomalies as supplementary context when the cell-specific group is sparse.

    NOTE: The KPI Trend detector (kpi_detector.detect_trend) hardcodes
    cell_id='Fleet-wide' because it computes a regression across the fleet rather
    than per cell. Without this Fleet-wide inclusion, drift-scenario fault cells
    that are detected primarily by the Trend detector would yield an empty event
    group and silently fail RCA evaluation.
    """
    from src.orchestrator.event_router import _new_event

    sev_rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

    if router is not None:
        cell_events = router.get_by_cell(cell_id)
        if len(cell_events) >= _MAX_GROUP_SIZE:
            return cell_events[:_MAX_GROUP_SIZE]
        # Supplement with Fleet-wide events if cell-specific group is sparse
        fleet_events = router.get_by_cell(_FLEET_WIDE_SENTINEL)
        combined = cell_events + fleet_events
        combined.sort(
            key=lambda e: sev_rank.get(e.get("severity", "Low"), 0), reverse=True
        )
        return combined[:_MAX_GROUP_SIZE]

    # Fallback: build from raw anomaly lists
    combined = []
    for a in kpi_anomalies:
        cid = str(a.get("cell_id", "")).strip()
        if cid == cell_id or cid == _FLEET_WIDE_SENTINEL:
            combined.append(("kpi", a))
    for a in stats_anomalies:
        cid = str(a.get("cell_id", "")).strip()
        if cid == cell_id or cid == _FLEET_WIDE_SENTINEL:
            combined.append(("stats", a))

    # Cell-specific events rank higher than Fleet-wide
    combined.sort(
        key=lambda x: (
            0 if str(x[1].get("cell_id", "")) == _FLEET_WIDE_SENTINEL else 1,
            sev_rank.get(x[1].get("severity", "Low"), 0),
        ),
        reverse=True,
    )

    events = []
    for source, raw in combined[:_MAX_GROUP_SIZE]:
        events.append(_new_event(source=source, anomaly=raw, state="current"))
    return events


def evaluate_rca(
    kpi_anomalies: List[Dict[str, Any]],
    stats_anomalies: List[Dict[str, Any]],
    router=None,
) -> List[Dict[str, Any]]:
    """
    For each of the 3 fault cells, build an event group, run rule_based_root_cause(),
    and check whether the output contains the expected diagnostic keywords.

    Parameters
    ----------
    kpi_anomalies : list
        All KPI anomalies from detect_kpi_anomalies().
    stats_anomalies : list
        All stats anomalies from detect_stats_anomalies().
    router : EventRouter, optional
        A populated EventRouter for richer event grouping.

    Returns
    -------
    list of dicts, one per fault cell, with:
      cell_id, fault_type, keyword_match (dict), rca_result (dict),
      event_group_size, success (bool)
    """
    from src.agent.rule_based import rule_based_root_cause

    results = []
    for cell_id, gt in GROUND_TRUTH_RCA.items():
        logger.info(f"Running RCA for {cell_id} ({gt['trigger_type']}) ...")
        try:
            group = build_synthetic_event_group(cell_id, kpi_anomalies, stats_anomalies, router)

            if not group:
                logger.warning(f"  No events found for {cell_id} — skipping RCA")
                results.append({
                    "cell_id":          cell_id,
                    "fault_type":       gt["trigger_type"],
                    "description":      gt["description"],
                    "event_group_size": 0,
                    "rca_result":       None,
                    "keyword_match":    {"any_match": False, "matched_keywords": [], "keyword_hit_rate": 0.0},
                    "success":          False,
                    "error":            "No anomaly events found for this cell",
                })
                continue

            rca_result = rule_based_root_cause(group)
            keyword_match = _check_keyword_match(rca_result, gt["expected_root_cause_keywords"])

            logger.info(
                f"  {cell_id}: keywords matched={keyword_match['matched_keywords']}, "
                f"hit_rate={keyword_match['keyword_hit_rate']:.2f}"
            )

            results.append({
                "cell_id":          cell_id,
                "fault_type":       gt["trigger_type"],
                "description":      gt["description"],
                "event_group_size": len(group),
                "rca_result": {
                    "root_cause":         rca_result.get("root_cause", ""),
                    "confidence":         rca_result.get("confidence", 0.0),
                    "recommended_action": rca_result.get("recommended_action", ""),
                    "source":             rca_result.get("source", ""),
                    "n_hops":             len(rca_result.get("causal_chain", [])),
                    "n_citations":        len(rca_result.get("citations", [])),
                },
                "keyword_match": keyword_match,
                "success":       keyword_match["any_match"],
                "error":         None,
            })

        except Exception as e:
            logger.error(f"  RCA evaluation failed for {cell_id}: {e}")
            results.append({
                "cell_id":          cell_id,
                "fault_type":       gt["trigger_type"],
                "description":      gt["description"],
                "event_group_size": 0,
                "rca_result":       None,
                "keyword_match":    {"any_match": False, "matched_keywords": [], "keyword_hit_rate": 0.0},
                "success":          False,
                "error":            str(e),
            })

    return results
