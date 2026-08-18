"""
Correlation metrics — cross-source cluster assignment rate.

IMPORTANT: This is NOT correlation precision or recall. It measures what
fraction of ingested anomaly events share a cell_id with an event from at
least one other source domain (kpi, stats, pcap). This is referred to as
the "cross-source cluster assignment rate."

The 99.8% figure cited in PPT slides is a cluster-assignment rate, not a
measure of how accurately the router identified real vs spurious correlations.
"""

from typing import Any, Dict

from src.orchestrator.event_router import EventRouter


def compute_correlation_assignment_rate(router: EventRouter) -> Dict[str, Any]:
    """
    Compute the cross-source cluster assignment rate from an EventRouter instance.

    Returns a dict with:
      metric_name        — descriptive name (not "accuracy")
      note               — explicit disclaimer
      total_events       — total events in the router
      clustered_events   — events sharing a cell/bucket with ≥1 other source
      single_source_events — events not correlated with any other source
      assignment_rate_pct  — clustered / total * 100
      by_source            — per-source breakdown

    Parameters
    ----------
    router : EventRouter
        A populated EventRouter (after ingest calls).
    """
    all_events = router.get_events()
    total = len(all_events)

    correlated = router.get_correlated(min_sources=2)
    clustered_ids = {ev["event_id"] for ev in correlated}

    clustered = len(clustered_ids)
    single_source = total - clustered

    rate = round(clustered / total * 100, 2) if total > 0 else 0.0

    by_source: Dict[str, Dict[str, int]] = {}
    for ev in all_events:
        src = ev["source"]
        if src not in by_source:
            by_source[src] = {"total": 0, "clustered": 0}
        by_source[src]["total"] += 1
        if ev["event_id"] in clustered_ids:
            by_source[src]["clustered"] += 1

    for src in by_source:
        t = by_source[src]["total"]
        c = by_source[src]["clustered"]
        by_source[src]["rate_pct"] = round(c / t * 100, 2) if t > 0 else 0.0

    return {
        "metric_name": "cross_source_cluster_assignment_rate",
        "note": (
            "Fraction of ingested anomaly events assigned to a cross-source cell cluster. "
            "This is NOT correlation precision or recall — it reflects how many events "
            "share a cell_id with an event from another source domain (kpi, stats, or pcap). "
            "A high rate indicates multi-source agreement; it does not confirm that the "
            "correlated cluster is a true anomaly."
        ),
        "total_events":          total,
        "clustered_events":      clustered,
        "single_source_events":  single_source,
        "assignment_rate_pct":   rate,
        "by_source":             by_source,
    }
