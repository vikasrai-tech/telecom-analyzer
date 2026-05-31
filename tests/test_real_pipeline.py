"""
Integration tests for the real (non-stub) pipeline.

These tests exercise actual parsers, detectors, RAG, and the orchestrator
using the checked-in test files in data/raw/.
"""

import pytest
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "raw"
PCAP_FILE = DATA / "test_5g_full.pcap"
KPI_FILE  = DATA / "5G_Network_KPI_Sample.xlsx"


# ── PCAP parser ───────────────────────────────────────────────────────

def test_real_pcap_parser_keys():
    from src.parsers.pcap_parser_real import parse_pcap
    result = parse_pcap(str(PCAP_FILE))
    assert "total_events" in result
    assert "procedures" in result
    assert "message_log" in result
    assert isinstance(result["procedures"], dict)


def test_real_pcap_parser_has_procedures():
    from src.parsers.pcap_parser_real import parse_pcap
    result = parse_pcap(str(PCAP_FILE))
    assert len(result["procedures"]) > 0, "Expected at least one procedure in test PCAP"


def test_real_pcap_procedure_schema():
    from src.parsers.pcap_parser_real import parse_pcap
    result = parse_pcap(str(PCAP_FILE))
    for name, stats in result["procedures"].items():
        assert "attempts" in stats,      f"{name} missing 'attempts'"
        assert "success"  in stats,      f"{name} missing 'success'"
        assert "failure"  in stats,      f"{name} missing 'failure'"
        assert "success_rate" in stats,  f"{name} missing 'success_rate'"


# ── PCAP detection ────────────────────────────────────────────────────

def test_real_pcap_detectors_return_dict():
    from src.parsers.pcap_parser_real import parse_pcap
    from src.detection.detector import detect_anomalies_by_detector
    parsed = parse_pcap(str(PCAP_FILE))
    by_det = detect_anomalies_by_detector(parsed)
    assert isinstance(by_det, dict)
    expected = {"Isolation Forest", "Statistical", "One-Class SVM",
                "LOF", "Elliptic Envelope", "LSTM Autoencoder"}
    assert set(by_det.keys()) == expected


def test_real_pcap_merge_results():
    from src.parsers.pcap_parser_real import parse_pcap
    from src.detection.detector import detect_anomalies_by_detector, merge_detector_results
    parsed = parse_pcap(str(PCAP_FILE))
    by_det = detect_anomalies_by_detector(parsed)
    merged = merge_detector_results(by_det)
    assert isinstance(merged, list)
    for a in merged:
        assert "type"     in a
        assert "severity" in a
        assert "score"    in a
        assert a["severity"] in ("Low", "Medium", "High", "Critical")


# ── KPI parser ────────────────────────────────────────────────────────

def test_real_kpi_parser_keys():
    from src.parsers.kpi_parser import parse_kpi_file
    result = parse_kpi_file(str(KPI_FILE))
    assert "rows" in result
    assert "cells" in result
    assert "kpi_columns" in result
    assert "df_records" in result
    assert result["rows"] > 0


def test_real_kpi_parser_has_kpis():
    from src.parsers.kpi_parser import parse_kpi_file
    result = parse_kpi_file(str(KPI_FILE))
    assert len(result["kpi_columns"]) > 0, "Expected at least one KPI column"


# ── KPI detection ─────────────────────────────────────────────────────

def test_real_kpi_detectors_return_dict():
    from src.parsers.kpi_parser import parse_kpi_file
    from src.detection.kpi_detector import detect_kpi_anomalies_by_detector
    parsed = parse_kpi_file(str(KPI_FILE))
    by_det = detect_kpi_anomalies_by_detector(parsed)
    assert isinstance(by_det, dict)
    assert len(by_det) >= 3  # at least some detectors ran


def test_real_kpi_anomaly_schema():
    from src.parsers.kpi_parser import parse_kpi_file
    from src.detection.kpi_detector import detect_kpi_anomalies
    parsed = parse_kpi_file(str(KPI_FILE))
    anomalies = detect_kpi_anomalies(parsed)
    for a in anomalies:
        assert "severity"  in a, f"Anomaly missing 'severity': {a}"
        assert "evidence"  in a, f"Anomaly missing 'evidence': {a}"
        assert "detector"  in a, f"Anomaly missing 'detector': {a}"


# ── RAG retriever ─────────────────────────────────────────────────────

def test_rag_retriever_returns_chunks():
    from src.rag.retriever import retrieve
    chunks = retrieve("NAS registration failure congestion AMF", top_k=3)
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    for c in chunks:
        assert "spec"     in c
        assert "section"  in c
        assert "text"     in c
        assert "relevance_score" in c


def test_rag_retriever_relevance_order():
    from src.rag.retriever import retrieve
    chunks = retrieve("RRC setup rejection waitTime capacity", top_k=5)
    scores = [c["relevance_score"] for c in chunks]
    assert scores == sorted(scores, reverse=True), "Chunks not sorted by relevance"


# ── LLM explainer (rule-based path — no Ollama required) ─────────────

def test_explainer_rule_based_output():
    from src.llm.explainer import explain_anomaly
    anomaly = {
        "type":           "High Failure Rate",
        "severity":       "High",
        "layer":          "NAS",
        "procedure":      "NAS_Registration",
        "evidence":       "success_rate=72.0% over 300 attempts",
        "failure_causes": {"congestion": 85, "timeout": 12},
        "detector":       "Statistical",
    }
    exp = explain_anomaly(anomaly)
    assert "hypothesis"          in exp
    assert "citations"           in exp
    assert "investigation_hints" in exp
    assert len(exp["investigation_hints"]) >= 2


# ── Orchestrator pipeline ─────────────────────────────────────────────

def test_pcap_pipeline_end_to_end():
    from src.orchestrator.pipeline import run_pcap_pipeline
    result = run_pcap_pipeline(str(PCAP_FILE), explain_top_n=1, skip_llm=False)
    assert result["pipeline"]   == "pcap"
    assert "parsed"             in result
    assert "anomalies"          in result
    assert "by_detector"        in result
    assert "explanations"       in result
    assert result["duration_s"] > 0


def test_kpi_pipeline_end_to_end():
    from src.orchestrator.pipeline import run_kpi_pipeline
    result = run_kpi_pipeline(str(KPI_FILE), explain_top_n=1, skip_llm=True)
    assert result["pipeline"]   == "kpi"
    assert "parsed"             in result
    assert "anomalies"          in result
    assert "summary_table"      in result
    assert result["duration_s"] > 0


def test_run_pipeline_auto_detects_kpi():
    from src.orchestrator.pipeline import run_pipeline
    result = run_pipeline(str(KPI_FILE), skip_llm=True)
    assert result["pipeline"] == "kpi"


def test_run_pipeline_auto_detects_pcap():
    from src.orchestrator.pipeline import run_pipeline
    result = run_pipeline(str(PCAP_FILE), skip_llm=True)
    assert result["pipeline"] == "pcap"
