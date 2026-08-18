"""Tool-wrapper functions for the root-cause agent.

Each is a thin, individually-testable function with no LLM call inside —
callable directly by rule_based.py's deterministic path, or dispatched to
by react_agent.py's ReAct loop when Ollama proposes an Action.
"""

import logging
from typing import Any, Dict, List, Optional

from src.orchestrator.event_router import EventRouter, event_timestamp

logger = logging.getLogger(__name__)


def get_event_details(event_id: str, router: EventRouter) -> Optional[Dict[str, Any]]:
    """Look up a single event by ID."""
    for ev in router.get_events(min_severity="Low"):
        if ev["event_id"] == event_id:
            return ev
    return None


def get_related_events(
    event_id: str, router: EventRouter, window_h: float = 1.0,
) -> List[Dict[str, Any]]:
    """Events on the same cell within +/- window_h hours of this event's
    own timestamp (a narrower window than EventRouter's own correlation
    grouping, useful when the agent wants to double-check a tighter range)."""
    event = get_event_details(event_id, router)
    if event is None:
        return []
    same_cell = router.get_by_cell(event["cell_id"])
    t0 = event_timestamp(event)
    if t0 is None:
        return [e for e in same_cell if e["event_id"] != event_id]

    related = []
    for ev in same_cell:
        if ev["event_id"] == event_id:
            continue
        t = event_timestamp(ev)
        if t is None or abs((t - t0).total_seconds()) <= window_h * 3600:
            related.append(ev)
    return related


def query_3gpp_spec(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Thin pass-through to the existing RAG retriever."""
    from src.rag.retriever import retrieve
    return retrieve(query, top_k=top_k)


def get_predictions_for_cell(cell_id: str, router: EventRouter) -> List[Dict[str, Any]]:
    """Predicted (not-yet-happened) anomalies for this cell."""
    return [
        ev for ev in router.get_events(state="predicted")
        if ev["cell_id"] == cell_id
    ]
