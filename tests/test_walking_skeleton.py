"""Smoke tests that the walking skeleton is wired correctly."""

from src.parsers.pcap_parser import parse_pcap_stub
from src.detection.detector import detect_anomalies_stub
from src.llm.explainer import explain_anomaly_stub


def test_parser_returns_expected_keys():
    out = parse_pcap_stub("dummy.pcap")
    assert "total_events" in out
    assert "procedures" in out
    assert "RRC_Setup" in out["procedures"]


def test_detector_returns_list():
    parsed = parse_pcap_stub("dummy.pcap")
    anomalies = detect_anomalies_stub(parsed, detector="Isolation Forest (stub)")
    assert isinstance(anomalies, list)
    assert len(anomalies) > 0
    assert "type" in anomalies[0]


def test_explainer_returns_citations():
    parsed = parse_pcap_stub("dummy.pcap")
    anomalies = detect_anomalies_stub(parsed, detector="Isolation Forest (stub)")
    explanation = explain_anomaly_stub(anomalies[0])
    assert "hypothesis" in explanation
    assert "citations" in explanation
    assert len(explanation["citations"]) > 0


def test_pipeline_end_to_end():
    """Full walking-skeleton pipeline runs without error."""
    parsed = parse_pcap_stub("test.pcap")
    anomalies = detect_anomalies_stub(parsed, detector="LSTM Autoencoder (stub)")
    for a in anomalies:
        explanation = explain_anomaly_stub(a)
        assert explanation["severity"] in {"Low", "Medium", "High"}
