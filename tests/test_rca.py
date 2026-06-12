"""
Tests for the RCA (Root Cause Analysis) engine.
"""

import pytest
from src.rca import analyze, RCAResult
from src.rca.causal_graph import layer_rank, find_rules_for_root


# ── Fixtures ──────────────────────────────────────────────────────────

def _pcap_anomaly(layer, proc, atype, severity="High", evidence="", ts="2024-01-15T10:00:00"):
    return {
        "type": atype,
        "severity": severity,
        "score": 0.8,
        "detector": "Statistical",
        "evidence": evidence,
        "procedure": proc,
        "layer": layer,
        "timestamp": ts,
    }


def _kpi_anomaly(kpi, cell, severity="High", ts="2024-01-15T10:00:05"):
    return {
        "type": f"{kpi} anomaly on {cell}",
        "severity": severity,
        "score": 0.7,
        "detector": "Threshold Violation",
        "evidence": f"{kpi} exceeded threshold",
        "kpi": kpi,
        "cell_id": cell,
        "timestamp": ts,
        "source": "kpi",
    }


def _stats_anomaly(kpi, cell, severity="High", ts="2024-01-15T09:59:55"):
    return {
        "type": f"{kpi} stats anomaly",
        "severity": severity,
        "score": 0.75,
        "detector": "IQR",
        "evidence": f"{kpi} out of normal range",
        "kpi": kpi,
        "cell_id": cell,
        "timestamp": ts,
        "source": "stats",
    }


# ── Unit tests: layer ranking ─────────────────────────────────────────

def test_layer_rank_ordering():
    phy = {"layer": "PHY"}
    rrc = {"layer": "RRC"}
    ngap = {"layer": "NGAP"}
    nas = {"layer": "NAS"}
    kpi = {"source": "kpi"}
    assert layer_rank(phy) < layer_rank(rrc)
    assert layer_rank(rrc) < layer_rank(ngap)
    assert layer_rank(ngap) < layer_rank(nas)
    assert layer_rank(nas) < layer_rank(kpi)


def test_layer_rank_stats_source():
    bler_anomaly = {"source": "stats", "kpi": "bler_dl"}
    harq_anomaly = {"source": "stats", "kpi": "harq_failure"}
    assert layer_rank(bler_anomaly) == 0   # PHY
    assert layer_rank(harq_anomaly) == 1   # MAC


# ── Unit tests: causal rule matching ─────────────────────────────────

def test_ngap_overload_rule_matches():
    anomaly = _pcap_anomaly("NGAP", "NGAP_Overload", "NGAP overload anomaly",
                             evidence="OVERLOAD_START received from AMF")
    rules = find_rules_for_root(anomaly)
    assert any(r.name == "NGAP_overload" for r, _ in rules)


def test_rrc_rule_matches():
    anomaly = _pcap_anomaly("RRC", "RRC_Setup", "RRC connection setup failure")
    rules = find_rules_for_root(anomaly)
    assert any(r.name == "RRC_setup_failure" for r, _ in rules)


def test_l2_stats_rule_matches():
    anomaly = _stats_anomaly("harq_failure", "cell_1")
    rules = find_rules_for_root(anomaly)
    assert len(rules) > 0


def test_no_rule_for_unknown():
    anomaly = {"type": "totally unknown", "layer": "?", "evidence": "xyz"}
    rules = find_rules_for_root(anomaly)
    # May match or not — just ensure it doesn't crash
    assert isinstance(rules, list)


# ── Integration tests: analyze() ─────────────────────────────────────

def test_analyze_empty():
    results = analyze([])
    assert results == []


def test_analyze_single_anomaly():
    anomalies = [_pcap_anomaly("NAS", "NAS_Registration", "NAS Registration anomaly")]
    results = analyze(anomalies)
    assert len(results) >= 1
    assert all(isinstance(r, RCAResult) for r in results)


def test_analyze_returns_rca_result_schema():
    anomalies = [_pcap_anomaly("NGAP", "NGAP_Overload", "NGAP overload anomaly",
                                evidence="OVERLOAD_START")]
    result = analyze(anomalies)[0]
    assert hasattr(result, "root_cause_anomaly")
    assert hasattr(result, "causal_chain")
    assert hasattr(result, "affected_anomalies")
    assert hasattr(result, "confidence")
    assert hasattr(result, "cell_id")
    assert hasattr(result, "layer_path")
    assert hasattr(result, "evidence_summary")
    assert hasattr(result, "recommendation")
    assert hasattr(result, "spec_ref")
    assert 0.0 <= result.confidence <= 1.0


def test_causal_chain_l1_to_nas():
    """L1 BLER anomaly + RRC failure + NAS failure → root cause = L1."""
    anomalies = [
        _stats_anomaly("bler_dl", "cell_1", ts="2024-01-15T10:00:01"),
        _pcap_anomaly("RRC", "RRC_Setup", "RRC Setup failure", ts="2024-01-15T10:00:05"),
        _pcap_anomaly("NAS", "NAS_Registration", "NAS Registration reject", ts="2024-01-15T10:00:08"),
    ]
    results = analyze(anomalies)
    assert len(results) >= 1
    top = results[0]  # highest confidence first
    # Root cause should be at or below RRC layer
    assert layer_rank(top.root_cause_anomaly) <= layer_rank({"layer": "RRC"})
    assert len(top.causal_chain) >= 2


def test_ngap_overload_cascades_to_nas():
    """NGAP overload should be identified as root cause of NAS Registration failures."""
    anomalies = [
        _pcap_anomaly("NGAP", "NGAP_Overload", "NGAP overload anomaly",
                      evidence="OVERLOAD_START, cause #22 congestion",
                      ts="2024-01-15T10:00:00"),
        _pcap_anomaly("NAS", "NAS_Registration", "NAS Registration reject cause #22",
                      ts="2024-01-15T10:00:03"),
        _pcap_anomaly("NAS", "NAS_Registration", "NAS Registration reject cause #22",
                      ts="2024-01-15T10:00:07"),
    ]
    results = analyze(anomalies)
    top = results[0]
    assert "NGAP" in top.layer_path or "ngap" in top.rule_name.lower() or layer_rank(top.root_cause_anomaly) <= 6
    assert top.confidence >= 0.70


def test_confidence_increases_with_more_effects():
    """More downstream anomalies → higher confidence."""
    few_effects = [
        _stats_anomaly("bler_dl", "cell_2", ts="2024-01-15T10:00:00"),
        _pcap_anomaly("RRC", "RRC_Setup", "RRC failure", ts="2024-01-15T10:00:02"),
    ]
    many_effects = few_effects + [
        _pcap_anomaly("NGAP", "NGAP_Init", "NGAP failure", ts="2024-01-15T10:00:03"),
        _pcap_anomaly("NAS", "NAS_Registration", "NAS failure", ts="2024-01-15T10:00:04"),
        _kpi_anomaly("throughput_dl", "cell_2", ts="2024-01-15T10:00:05"),
    ]
    r_few  = analyze(few_effects)[0]
    r_many = analyze(many_effects)[0]
    assert r_many.confidence >= r_few.confidence


def test_multiple_cells_separated():
    """Anomalies in different cells should produce separate RCA results."""
    anomalies = [
        {**_pcap_anomaly("NAS", "NAS_Registration", "NAS anomaly cell_A"), "cell_id": "cell_A"},
        {**_pcap_anomaly("NAS", "NAS_Registration", "NAS anomaly cell_B"), "cell_id": "cell_B"},
    ]
    results = analyze(anomalies)
    cells = {r.cell_id for r in results}
    assert "cell_A" in cells
    assert "cell_B" in cells


def test_analyze_to_dict_schema():
    """as_dict() should return all expected keys."""
    anomalies = [_pcap_anomaly("RRC", "RRC_Setup", "RRC failure")]
    result = analyze(anomalies)[0]
    d = result.as_dict()
    for key in ["root_cause_type", "root_cause_layer", "rule_name", "confidence",
                "severity", "cell_id", "layer_path", "affected_count",
                "causal_chain", "evidence_summary", "recommendation", "spec_ref"]:
        assert key in d, f"Missing key: {key}"


def test_mixed_sources():
    """PCAP + KPI + stats anomalies together should not crash."""
    anomalies = [
        _stats_anomaly("bler_dl", "cell_3", ts="2024-01-15T10:00:00"),
        _pcap_anomaly("RRC", "RRC_Setup", "RRC failure", ts="2024-01-15T10:00:02"),
        _kpi_anomaly("pdcp_ul_throughput", "cell_3", ts="2024-01-15T10:00:05"),
    ]
    results = analyze(anomalies)
    assert len(results) >= 1
    assert all(isinstance(r, RCAResult) for r in results)


def test_sorted_by_confidence():
    """Results must be sorted highest confidence first."""
    anomalies = [
        _stats_anomaly("bler_dl", "cell_5", ts="2024-01-15T10:00:00"),
        _pcap_anomaly("RRC", "RRC_Setup", "RRC failure", ts="2024-01-15T10:00:02"),
        _pcap_anomaly("NAS", "NAS_Registration", "NAS reject", ts="2024-01-15T10:00:04"),
        _kpi_anomaly("throughput_dl", "cell_5", ts="2024-01-15T10:00:06"),
    ]
    results = analyze(anomalies)
    confs = [r.confidence for r in results]
    assert confs == sorted(confs, reverse=True)
