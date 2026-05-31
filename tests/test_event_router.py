"""Tests for the Event Router — tagging, correlation, priority queue."""

from src.orchestrator.event_router import EventRouter, route_events

# ── Sample anomalies ──────────────────────────────────────────────────

PCAP_ANOMS = [
    {"type": "High Failure Rate", "severity": "High", "layer": "NAS",
     "procedure": "NAS_Registration", "evidence": "SR=72%",
     "failure_causes": {"congestion": 50}, "detector": "Statistical", "score": 0.9},
    {"type": "Timeout Storm", "severity": "Medium", "layer": "NGAP",
     "procedure": "NGAP_InitialContextSetup", "evidence": "12 timeouts",
     "failure_causes": {"timeout": 12}, "detector": "Isolation Forest", "score": 0.6},
]

KPI_ANOMS = [
    {"label": "rrc_setup_sr", "category": "RRC Setup Success Rate",
     "cell_id": "PCI_3", "severity": "Critical", "value": 88.0, "unit": "%",
     "warning": 95, "critical": 90, "evidence": "RRC SR=88%", "score": 7.0,
     "recommendation": "Check cell capacity", "detector": "Threshold"},
    {"label": "dl_prb_util", "category": "DL PRB Utilisation",
     "cell_id": "PCI_3", "severity": "High", "value": 93.0, "unit": "%",
     "warning": 80, "critical": 90, "evidence": "PRB=93%", "score": 3.0,
     "recommendation": "Add capacity", "detector": "Threshold"},
]

STATS_ANOMS = [
    {"label": "dl_bler", "category": "DL Block Error Rate",
     "cell_id": "PCI_3", "severity": "High", "value": 22.0, "unit": "%",
     "warning": 10, "critical": 20, "evidence": "BLER=22%", "score": 2.0,
     "recommendation": "Check SINR", "detector": "Threshold"},
]


# ── EventRecord structure ─────────────────────────────────────────────

def test_event_record_fields():
    router = EventRouter()
    events = router.ingest(PCAP_ANOMS, source="pcap")
    assert len(events) == 2
    ev = events[0]
    required = {"event_id", "created_at", "source", "state", "lead_time_h",
                "severity", "category", "cell_id", "evidence", "detector",
                "score", "correlated_sources", "correlation_confidence"}
    assert required.issubset(ev.keys())


def test_source_tag_pcap():
    router = EventRouter()
    events = router.ingest(PCAP_ANOMS, source="pcap")
    assert all(e["source"] == "pcap" for e in events)


def test_source_tag_kpi():
    router = EventRouter()
    events = router.ingest(KPI_ANOMS, source="kpi")
    assert all(e["source"] == "kpi" for e in events)


def test_state_defaults_to_current():
    router = EventRouter()
    events = router.ingest(KPI_ANOMS, source="kpi")
    assert all(e["state"] == "current" for e in events)
    assert all(e["lead_time_h"] == 0.0 for e in events)


def test_predicted_state():
    router = EventRouter()
    events = router.ingest_predicted(KPI_ANOMS, source="kpi", lead_time_h=2.5)
    assert all(e["state"] == "predicted" for e in events)
    assert all(e["lead_time_h"] == 2.5 for e in events)


# ── Priority ordering ─────────────────────────────────────────────────

def test_events_sorted_by_severity():
    router = EventRouter()
    router.ingest(KPI_ANOMS + STATS_ANOMS, source="kpi")
    events = router.get_events()
    sevs = [e["severity"] for e in events]
    rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
    ranks = [rank[s] for s in sevs]
    assert ranks == sorted(ranks, reverse=True)


def test_filter_by_source():
    router = EventRouter()
    router.ingest(PCAP_ANOMS,  source="pcap")
    router.ingest(KPI_ANOMS,   source="kpi")
    pcap_only = router.get_events(source="pcap")
    assert all(e["source"] == "pcap" for e in pcap_only)
    assert len(pcap_only) == len(PCAP_ANOMS)


def test_filter_by_min_severity():
    router = EventRouter()
    router.ingest(KPI_ANOMS + STATS_ANOMS, source="kpi")
    high_plus = router.get_events(min_severity="High")
    assert all(e["severity"] in ("Critical", "High") for e in high_plus)


# ── Cross-source correlation ──────────────────────────────────────────

def test_no_correlation_single_source():
    router = EventRouter()
    router.ingest(KPI_ANOMS, source="kpi")
    events = router.get_events()
    assert all(e["correlated_sources"] == [] for e in events)
    assert all(e["correlation_confidence"] == 0.0 for e in events)


def test_cross_source_correlation_detected():
    """KPI + Stats both flag PCI_3 BLER/PRB → should correlate."""
    router = EventRouter()
    router.ingest(KPI_ANOMS,   source="kpi")
    router.ingest(STATS_ANOMS, source="stats")
    correlated = router.get_correlated()
    assert len(correlated) > 0, "Expected at least one cross-source correlated event"


def test_correlation_confidence_range():
    router = EventRouter()
    router.ingest(KPI_ANOMS,   source="kpi")
    router.ingest(STATS_ANOMS, source="stats")
    for ev in router.get_events():
        assert 0.0 <= ev["correlation_confidence"] <= 1.0


def test_three_source_correlation():
    """All 3 sources flagging same cell → max confidence."""
    pcap_cell = [{"type": "High Failure Rate", "severity": "High",
                  "layer": "RRC", "procedure": "RRC_Setup", "cell_id": "PCI_3",
                  "evidence": "RRC SR low", "failure_causes": {}, "detector": "Statistical",
                  "score": 0.8}]
    router = EventRouter()
    router.ingest(pcap_cell,   source="pcap")
    router.ingest(KPI_ANOMS,   source="kpi")
    router.ingest(STATS_ANOMS, source="stats")
    correlated = router.get_correlated()
    assert len(correlated) > 0
    max_conf = max(e["correlation_confidence"] for e in correlated)
    assert max_conf >= 0.66  # 2/3 sources


# ── Summary ───────────────────────────────────────────────────────────

def test_summary_structure():
    router = EventRouter()
    router.ingest(PCAP_ANOMS,  source="pcap")
    router.ingest(KPI_ANOMS,   source="kpi")
    router.ingest(STATS_ANOMS, source="stats")
    s = router.summary()
    assert "total"       in s
    assert "correlated"  in s
    assert "by_severity" in s
    assert "by_source"   in s
    assert "top_cells"   in s
    assert s["total"] == len(PCAP_ANOMS) + len(KPI_ANOMS) + len(STATS_ANOMS)


def test_summary_counts_by_source():
    router = EventRouter()
    router.ingest(PCAP_ANOMS,  source="pcap")
    router.ingest(KPI_ANOMS,   source="kpi")
    s = router.summary()
    assert s["by_source"]["pcap"]  == len(PCAP_ANOMS)
    assert s["by_source"]["kpi"]   == len(KPI_ANOMS)
    assert s["by_source"]["stats"] == 0


# ── route_events helper ───────────────────────────────────────────────

def test_route_events_helper():
    router = route_events(
        pcap_anomalies=PCAP_ANOMS,
        kpi_anomalies=KPI_ANOMS,
    )
    assert router.summary()["total"] == len(PCAP_ANOMS) + len(KPI_ANOMS)


def test_get_by_cell():
    router = EventRouter()
    router.ingest(KPI_ANOMS,   source="kpi")
    router.ingest(STATS_ANOMS, source="stats")
    cell_events = router.get_by_cell("PCI_3")
    assert len(cell_events) > 0
    assert all(e["cell_id"] == "PCI_3" for e in cell_events)
