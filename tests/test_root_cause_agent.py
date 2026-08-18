"""Tests for the LLM root-cause agent (src/agent/).

Follows tests/test_event_router.py's convention: plain pytest functions,
hand-built fixtures, no mocking of the logic under test (only Ollama
itself is mocked, and only where explicitly noted).
"""

import pytest

from src.orchestrator.event_router import EventRouter

# ── Sample anomalies ──────────────────────────────────────────────────
# Mirrors tests/test_event_router.py's KPI_ANOMS/STATS_ANOMS shape.
# "label"="dl_bler" -> EventRecord.category="dl_bler", which the causal
# rules' PHY keyword match ("bler") picks up as the deepest-layer event —
# a coherent test scenario: BLER degradation (PHY) causing a handover
# success-rate drop (KPI aggregate) on the same cell.

STATS_BLER_ANOM = {
    "label": "dl_bler", "category": "l1_quality", "cell_id": "PCI_3",
    "severity": "Critical", "value": 22.0, "unit": "%",
    "evidence": "BLER=22%, above critical threshold", "score": 6.0,
    "detector": "Threshold",
}

KPI_HO_ANOM = {
    "label": "Handover_Success_Rate_%", "category": "mobility", "cell_id": "PCI_3",
    "severity": "High", "value": 60.0, "unit": "%",
    "evidence": "HO success rate dropped to 60%", "score": 5.0,
    "detector": "Threshold",
}

NEAR_ANOM = {
    "label": "dl_prb_util", "category": "capacity", "cell_id": "PCI_9",
    "severity": "High", "value": 92.0, "unit": "%",
    "evidence": "PRB util 92%", "score": 3.0, "detector": "Threshold",
    "timestamp": "2024-01-01T12:00:00",
}
FAR_ANOM = {
    "label": "Cell_Availability_%", "category": "availability", "cell_id": "PCI_9",
    "severity": "Critical", "value": 65.0, "unit": "%",
    "evidence": "Availability dropped to 65%", "score": 7.0, "detector": "Threshold",
    "timestamp": "2024-01-01T20:00:00",  # 8h after NEAR_ANOM
}


def _correlated_group_router():
    """A router with a correlated (2-source, same-cell) group."""
    router = EventRouter()
    router.ingest([STATS_BLER_ANOM], source="stats")
    router.ingest([KPI_HO_ANOM],     source="kpi")
    return router


# ── Tools ───────────────────────────────────────────────────────────────

def test_get_event_details():
    from src.agent.tools import get_event_details

    router = _correlated_group_router()
    any_event = router.get_events()[0]
    found = get_event_details(any_event["event_id"], router)
    assert found is not None
    assert found["event_id"] == any_event["event_id"]

    assert get_event_details("nonexistent-id", router) is None


def test_get_related_events_time_window():
    from src.agent.tools import get_related_events

    router = EventRouter()
    router.ingest([NEAR_ANOM], source="kpi")
    router.ingest([FAR_ANOM],  source="stats")

    near_event = [e for e in router.get_events() if e["category"] == "dl_prb_util"][0]

    # Narrow window: the 8h-away event should be excluded.
    related_narrow = get_related_events(near_event["event_id"], router, window_h=1.0)
    assert all(e["category"] != "Cell_Availability_%" for e in related_narrow)

    # Wide window: it should be included.
    related_wide = get_related_events(near_event["event_id"], router, window_h=10.0)
    assert any(e["category"] == "Cell_Availability_%" for e in related_wide)


def test_query_3gpp_spec_returns_chunks():
    from src.agent.tools import query_3gpp_spec

    chunks = query_3gpp_spec("BLER radio link failure", top_k=2)
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    assert "spec" in chunks[0]


def test_get_predictions_for_cell():
    from src.agent.tools import get_predictions_for_cell

    router = EventRouter()
    router.ingest_predicted([KPI_HO_ANOM], source="kpi", lead_time_h=4)
    preds = get_predictions_for_cell("PCI_3", router)
    assert len(preds) == 1
    assert preds[0]["state"] == "predicted"
    assert preds[0]["lead_time_h"] == 4

    assert get_predictions_for_cell("PCI_999", router) == []


# ── Deterministic (rule-based) root-cause path — always runs ────────────

def test_rule_based_root_cause_schema():
    from src.agent.rule_based import rule_based_root_cause

    router = _correlated_group_router()
    group = router.get_correlated(min_sources=2)
    assert len(group) == 2  # both events correlate (same cell, 2 sources)

    result = rule_based_root_cause(group, predictions=[])
    required = {"root_cause", "causal_chain", "confidence", "citations",
                "recommended_action", "source", "cell_id"}
    assert required.issubset(result.keys())
    assert 0.0 <= result["confidence"] <= 1.0
    assert result["source"] == "rule-based (Ollama unavailable)"
    assert len(result["causal_chain"]) == 2


def test_rule_based_assigns_trigger_to_lowest_layer():
    """The PHY-level BLER event should be identified as the trigger; the
    KPI-level handover success-rate drop as the symptom."""
    from src.agent.rule_based import rule_based_root_cause

    router = _correlated_group_router()
    group = router.get_correlated(min_sources=2)
    result = rule_based_root_cause(group, predictions=[])

    trigger_hops = [h for h in result["causal_chain"] if h["role"] == "trigger"]
    assert len(trigger_hops) == 1
    trigger_event_id = trigger_hops[0]["event_id"]
    trigger_event = next(e for e in group if e["event_id"] == trigger_event_id)
    assert trigger_event["category"] == "dl_bler"

    symptom_hops = [h for h in result["causal_chain"] if h["role"] != "trigger"]
    assert len(symptom_hops) == 1


def test_rule_based_citations_from_real_retrieval():
    from src.agent.rule_based import rule_based_root_cause

    router = _correlated_group_router()
    group = router.get_correlated(min_sources=2)
    result = rule_based_root_cause(group, predictions=[])

    assert len(result["citations"]) > 0
    for c in result["citations"]:
        assert "spec" in c and "section" in c and "quote" in c


def test_rule_based_empty_group():
    from src.agent.rule_based import rule_based_root_cause

    result = rule_based_root_cause([], predictions=[])
    assert result["causal_chain"] == []
    assert result["confidence"] == 0.0


def test_rule_based_mentions_prediction_when_present():
    from src.agent.rule_based import rule_based_root_cause

    router = _correlated_group_router()
    group = router.get_correlated(min_sources=2)
    predictions = [{"cell_id": "PCI_3", "label": "Handover_Success_Rate_%", "lead_time_h": 4}]

    result = rule_based_root_cause(group, predictions=predictions)
    assert "forecast" in result["recommended_action"].lower()


# ── analyze_root_cause() — groups correlated events end-to-end ──────────

def test_analyze_root_cause_returns_result_per_group():
    from src.agent.react_agent import analyze_root_cause

    router = _correlated_group_router()
    results = analyze_root_cause(router, min_sources=2)
    assert len(results) == 1
    assert results[0]["cell_id"] == "PCI_3"


def test_analyze_root_cause_empty_when_no_correlation():
    from src.agent.react_agent import analyze_root_cause

    router = EventRouter()
    router.ingest([STATS_BLER_ANOM], source="stats")  # single source only
    results = analyze_root_cause(router, min_sources=2)
    assert results == []


# ── Ollama-guarded path ──────────────────────────────────────────────────

def _ollama_available() -> bool:
    try:
        import ollama
        return bool(ollama.list().models)
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_available(), reason="Ollama not running in this environment")
def test_run_root_cause_agent_with_real_ollama():
    from src.agent.react_agent import run_root_cause_agent

    router = _correlated_group_router()
    group = router.get_correlated(min_sources=2)
    result = run_root_cause_agent(group, router, predictions=[])
    required = {"root_cause", "causal_chain", "confidence", "citations",
                "recommended_action", "source"}
    assert required.issubset(result.keys())


def test_react_agent_falls_back_on_unparseable_model_output(monkeypatch):
    """Simulates Ollama being 'available' but producing output that never
    matches the Action/Final-Answer format on any step — the guardrail
    should walk the deterministic tool order and, after max_iterations,
    fall back to rule_based_root_cause() without raising."""
    import src.agent.react_agent as react_agent_mod

    monkeypatch.setattr(react_agent_mod, "_detect_ollama_model", lambda: "fake-model")

    class _FakeMessage:
        def __init__(self, content):
            self.content = content

    class _FakeResponse:
        def __init__(self, content):
            self.message = _FakeMessage(content)

    class _FakeOllama:
        @staticmethod
        def chat(**kwargs):
            return _FakeResponse("I am not following the expected format at all.")

    monkeypatch.setitem(__import__("sys").modules, "ollama", _FakeOllama())

    router = _correlated_group_router()
    group = router.get_correlated(min_sources=2)
    result = react_agent_mod.run_root_cause_agent(group, router, predictions=[], max_iterations=2)

    required = {"root_cause", "causal_chain", "confidence", "citations",
                "recommended_action", "source"}
    assert required.issubset(result.keys())
    assert len(result["causal_chain"]) == 2  # fell back to the deterministic rule-based result
