"""Tests for Feedback Store and Prediction Layer."""

import tempfile
from pathlib import Path
import pytest


# ── Feedback Store ────────────────────────────────────────────────────

def test_save_and_load_feedback():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        store = Path(f.name)

    from src.feedback.store import save_feedback, load_feedback
    rec = save_feedback(
        event_id="ev_001", source="kpi", anomaly_type="dl_bler",
        severity="High", detector="Threshold", cell_id="PCI_3",
        evidence="BLER=22%", verdict="correct", store_path=store,
    )
    assert rec["verdict"] == "correct"
    assert rec["event_id"] == "ev_001"

    records = load_feedback(store_path=store)
    assert len(records) == 1
    assert records[0]["source"] == "kpi"


def test_feedback_newest_first():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        store = Path(f.name)

    from src.feedback.store import save_feedback, load_feedback
    for i in range(5):
        save_feedback(f"ev_{i}", "stats", f"metric_{i}", "Medium",
                      "Trend", "PCI_1", "evidence", "correct",
                      store_path=store)

    records = load_feedback(store_path=store)
    assert records[0]["event_id"] == "ev_4"   # newest first


def test_feedback_stats():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        store = Path(f.name)

    from src.feedback.store import save_feedback, feedback_stats
    save_feedback("e1","pcap","type_a","High","IF","—","ev","correct",       store_path=store)
    save_feedback("e2","pcap","type_b","High","IF","—","ev","correct",       store_path=store)
    save_feedback("e3","pcap","type_c","Medium","IF","—","ev","false_positive", store_path=store)
    save_feedback("e4","pcap","type_d","Low","IF","—","ev","uncertain",      store_path=store)

    stats = feedback_stats(store_path=store)
    assert stats["total"]          == 4
    assert stats["correct"]        == 2
    assert stats["false_positive"] == 1
    assert stats["uncertain"]      == 1
    assert stats["precision"]      == round(2 / 3, 3)


def test_feedback_stats_empty():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        store = Path(f.name)

    from src.feedback.store import feedback_stats
    stats = feedback_stats(store_path=store)
    assert stats["total"] == 0
    assert stats["precision"] is None


def test_feedback_by_detector():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        store = Path(f.name)

    from src.feedback.store import save_feedback, feedback_stats
    save_feedback("e1","kpi","a","High","Threshold","c","e","correct",        store_path=store)
    save_feedback("e2","kpi","b","High","CUSUM",    "c","e","false_positive",  store_path=store)

    stats = feedback_stats(store_path=store)
    assert "Threshold" in stats["by_detector"]
    assert "CUSUM"     in stats["by_detector"]
    assert stats["by_detector"]["Threshold"]["correct"] == 1
    assert stats["by_detector"]["CUSUM"]["false_positive"] == 1


# ── Prediction Layer ──────────────────────────────────────────────────

def _make_parsed_kpi():
    """Small synthetic KPI parsed dict for prediction tests."""
    import pandas as pd, numpy as np
    from datetime import datetime, timedelta

    rng  = np.random.default_rng(0)
    base = datetime(2024, 1, 1)
    rows = []
    for i in range(60):
        rows.append({
            "timestamp": (base + timedelta(hours=i)).isoformat(),
            "cell_id":   "PCI_1",
            "dl_prb_util": float(rng.uniform(20, 70) + i * 0.3),  # rising trend
            "dl_bler":     float(rng.uniform(2, 8)),
        })
    df = pd.DataFrame(rows)
    return {
        "timestamp_col": "timestamp",
        "cell_col":      "cell_id",
        "l1l2_columns":  ["dl_prb_util", "dl_bler"],
        "kpi_columns":   ["dl_prb_util", "dl_bler"],
        "df_records":    df.to_dict(orient="records"),
    }


def test_prophet_returns_list():
    from src.detection.predictor import forecast_prophet
    parsed = _make_parsed_kpi()
    result = forecast_prophet(parsed, horizon_h=2)
    assert isinstance(result, list)
    for a in result:
        assert "label"      in a
        assert "severity"   in a
        assert "state"      in a
        assert a["state"]   == "predicted"
        assert a["lead_time_h"] == 2


def test_lstm_returns_list():
    from src.detection.predictor import forecast_lstm
    parsed = _make_parsed_kpi()
    result = forecast_lstm(parsed, horizon_h=2)
    assert isinstance(result, list)
    for a in result:
        assert a["state"]       == "predicted"
        assert a["lead_time_h"] == 2
        assert "LSTM" in a["detector"]


def test_run_prediction_both_methods():
    from src.detection.predictor import run_prediction
    parsed  = _make_parsed_kpi()
    results = run_prediction(parsed, horizon_h=2)
    assert "prophet" in results
    assert "lstm"    in results
    assert isinstance(results["prophet"], list)
    assert isinstance(results["lstm"],    list)


def test_run_prediction_select_method():
    from src.detection.predictor import run_prediction
    parsed = _make_parsed_kpi()
    results = run_prediction(parsed, horizon_h=2, methods=["lstm"])
    assert "lstm"    in results
    assert "prophet" not in results


def test_predicted_anomaly_schema():
    from src.detection.predictor import forecast_lstm
    parsed = _make_parsed_kpi()
    anoms  = forecast_lstm(parsed, horizon_h=3)
    for a in anoms:
        required = {"label","severity","state","lead_time_h","evidence",
                    "recommendation","detector","value"}
        assert required.issubset(a.keys()), f"Missing keys: {required - set(a.keys())}"


def test_event_router_ingests_predicted():
    """Predicted anomalies flow into EventRouter with correct state tag."""
    from src.detection.predictor import run_prediction
    from src.orchestrator.event_router import EventRouter

    parsed = _make_parsed_kpi()
    preds  = run_prediction(parsed, horizon_h=4)
    all_p  = [a for anoms in preds.values() for a in anoms]

    router = EventRouter()
    router.ingest_predicted(all_p, source="kpi", lead_time_h=4)

    predicted_events = router.get_events(state="predicted")
    assert len(predicted_events) == len(all_p)
    assert all(e["state"] == "predicted" for e in predicted_events)
    assert all(e["lead_time_h"] == 4 for e in predicted_events)
