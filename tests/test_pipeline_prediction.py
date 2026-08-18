"""Tests for prediction-layer wiring into the CLI/API orchestrator (Milestone 2).

Prediction (Prophet/Holt-Winters/LSTM) previously only ran from the
Streamlit dashboard — run_kpi_pipeline/run_stats_pipeline never called it.
These tests assert the new run_prediction flag actually routes forecasts
into the pipeline result and the shared EventRouter, and stays a no-op by
default (regression guard).
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def _make_parsed_kpi():
    """Same 60-row synthetic fixture used in test_feedback_prediction.py."""
    rng  = np.random.default_rng(0)
    base = datetime(2024, 1, 1)
    rows = []
    for i in range(60):
        rows.append({
            "timestamp": (base + timedelta(hours=i)).isoformat(),
            "cell_id":   "PCI_1",
            "dl_prb_util": float(rng.uniform(20, 70) + i * 0.3),
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


def test_kpi_pipeline_predictions_populate_when_enabled(monkeypatch):
    import src.parsers.kpi_parser as kpi_parser_mod
    monkeypatch.setattr(kpi_parser_mod, "parse_kpi_file", lambda path: _make_parsed_kpi())

    from src.orchestrator.pipeline import run_kpi_pipeline
    result = run_kpi_pipeline(
        "dummy.csv", skip_llm=True, run_prediction=True,
        prediction_methods=["holt_winters"], prediction_horizon_h=2,
    )
    assert result["predictions"]
    assert "holt_winters" in result["predictions"]

    predicted_events = [e for e in result["events"] if e["state"] == "predicted"]
    assert len(predicted_events) == sum(len(v) for v in result["predictions"].values())
    assert all(e["lead_time_h"] == 2 for e in predicted_events)


def test_kpi_pipeline_predictions_empty_by_default(monkeypatch):
    import src.parsers.kpi_parser as kpi_parser_mod
    monkeypatch.setattr(kpi_parser_mod, "parse_kpi_file", lambda path: _make_parsed_kpi())

    from src.orchestrator.pipeline import run_kpi_pipeline
    result = run_kpi_pipeline("dummy.csv", skip_llm=True)
    assert result["predictions"] == {}
    assert all(e["state"] != "predicted" for e in result["events"])
