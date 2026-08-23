"""Deterministic (no-LLM) root-cause fallback.

Always available — matches the project's established convention
(src/llm/explainer.py's `_rule_based_explanation`) of never requiring
Ollama to produce a usable result. Unlike the ported causal-rule metadata
it walks, citations here come from a real RAG retrieval per hop (not a
hardcoded spec_ref string).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.agent.causal_rules import find_rules_for_root, layer_rank, layer_label
from src.agent.schemas import CausalHop, RootCauseResult
from src.agent.tools import query_3gpp_spec, event_timestamp

logger = logging.getLogger(__name__)


def rule_based_root_cause(
    correlated_group: List[Dict[str, Any]],
    predictions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    predictions = predictions or []
    if not correlated_group:
        return RootCauseResult(
            root_cause="No correlated events to analyze.",
            causal_chain=[], confidence=0.0, citations=[],
            recommended_action="No action needed.",
            source="rule-based (no correlated events)",
        ).as_dict()

    # Chronological order (falling back to epoch for events with no
    # resolvable timestamp), tie-broken by protocol-stack depth.
    ordered = sorted(
        correlated_group,
        key=lambda e: (event_timestamp(e) or datetime.min.replace(tzinfo=timezone.utc), layer_rank(e)),
    )
    root = min(ordered, key=layer_rank)

    rules = find_rules_for_root(root)
    top_rule = rules[0][0] if rules else None
    confidence = rules[0][1] if rules else 0.4

    hops: List[CausalHop] = []
    citations: List[Dict[str, str]] = []
    for ev in ordered:
        role = "trigger" if ev["event_id"] == root["event_id"] else "symptom"
        query = f"{ev.get('category', '')} {ev.get('evidence', '')} {ev.get('layer', '')}"
        chunks = query_3gpp_spec(query, top_k=2)
        explanation = (
            f"{ev.get('category', 'anomaly')} on cell {ev.get('cell_id', '?')} "
            f"({layer_label(ev)}, severity={ev.get('severity', '?')}): {ev.get('evidence', '')}"
        )
        hops.append(CausalHop(event_id=ev["event_id"], role=role, explanation=explanation))
        for c in chunks:
            if c.get("spec"):
                citations.append({
                    "spec": c.get("spec", ""),
                    "section": c.get("section", ""),
                    "quote": c.get("text", "")[:150].rstrip(".") + ".",
                })

    # Events strictly between the root and the last hop are contributing
    # factors rather than plain symptoms.
    if len(hops) > 2:
        for h in hops[1:-1]:
            h.role = "contributing_factor"

    root_cause_text = (
        f"Root cause: {root.get('category', 'anomaly')} at {layer_label(root)} "
        f"on cell {root.get('cell_id', '?')}. "
        + (top_rule.description + " " if top_rule else "")
        + f"This appears to have propagated to {len(ordered) - 1} downstream anomaly(ies)."
    )

    recommendation = top_rule.recommendation if top_rule else (
        "Investigate the lowest-layer anomaly in this correlated group first; "
        "it is the most likely root cause given standard 5G protocol-stack causality."
    )
    if predictions and any(p.get("cell_id") == root.get("cell_id") for p in predictions):
        recommendation += (
            " Note: a forecast also predicts continued/worsening anomalies on this "
            "cell within the prediction horizon — treat as higher priority."
        )

    # De-dup citations by (spec, section), cap at 5.
    seen = set()
    deduped: List[Dict[str, str]] = []
    for c in citations:
        key = (c["spec"], c["section"])
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    return RootCauseResult(
        root_cause=root_cause_text,
        causal_chain=hops,
        confidence=confidence,
        citations=deduped[:5],
        recommended_action=recommendation,
        source="rule-based (Ollama unavailable)",
        cell_id=str(root.get("cell_id", "")),
    ).as_dict()
