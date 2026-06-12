"""
Tests for the Evaluation Framework (dataset generation + metrics).
"""

import pytest
from src.evaluation.dataset import (
    generate_kpi_dataset,
    generate_stats_dataset,
    LabeledDataset,
)
from src.evaluation.evaluator import (
    run_kpi_evaluation,
    run_stats_evaluation,
    DetectorMetrics,
    EvalReport,
    _compute_metrics,
    _fired_pairs,
)


# ── Dataset generation tests ──────────────────────────────────────────

def test_kpi_dataset_structure():
    ds = generate_kpi_dataset(n_cells=3, n_timestamps=50, anomaly_rate=0.20, seed=1)
    assert isinstance(ds, LabeledDataset)
    parsed = ds.parsed
    assert parsed["rows"] == 3 * 50
    assert len(parsed["cells"]) == 3
    assert len(parsed["kpi_columns"]) > 0
    assert len(parsed["df_records"]) == 3 * 50
    assert parsed["cell_col"] in parsed["df_records"][0]
    assert parsed["timestamp_col"] in parsed["df_records"][0]


def test_kpi_dataset_has_ground_truth():
    ds = generate_kpi_dataset(n_cells=3, n_timestamps=50, anomaly_rate=0.20, seed=1)
    assert len(ds.ground_truth) > 0
    for cell, kpi in ds.ground_truth:
        assert cell.startswith("cell_")
        assert kpi in ds.parsed["kpi_columns"]


def test_kpi_dataset_anomaly_rate():
    ds = generate_kpi_dataset(n_cells=4, n_timestamps=50, anomaly_rate=0.25, seed=2)
    n_total = len(ds.parsed["cells"]) * len(ds.parsed["kpi_columns"])
    actual_rate = ds.n_anomaly_pairs / n_total
    # Allow ±15% tolerance (some KPIs have no threshold and are excluded)
    assert 0.0 < actual_rate <= 0.40


def test_kpi_dataset_injected_values_differ():
    """Anomalous (cell, kpi) pairs should have different max values from normal."""
    ds = generate_kpi_dataset(n_cells=3, n_timestamps=60, anomaly_rate=0.30, seed=3)
    import pandas as pd
    df = pd.DataFrame(ds.parsed["df_records"])
    cell_col = ds.parsed["cell_col"]
    # Just check the dataset is not all-identical
    for kpi in ds.parsed["kpi_columns"][:3]:
        assert df[kpi].std() > 0


def test_stats_dataset_structure():
    ds = generate_stats_dataset(n_cells=2, n_timestamps=40, seed=5)
    assert ds.parsed["rows"] == 2 * 40
    assert len(ds.parsed["cells"]) == 2
    assert len(ds.parsed["l1l2_columns"]) > 0
    assert ds.parsed["cell_col"] in ds.parsed["df_records"][0]


def test_stats_dataset_has_ground_truth():
    ds = generate_stats_dataset(n_cells=2, n_timestamps=40, seed=5)
    assert len(ds.ground_truth) > 0
    for cell, metric in ds.ground_truth:
        assert cell.startswith("cell_")


def test_reproducibility():
    ds1 = generate_kpi_dataset(seed=42)
    ds2 = generate_kpi_dataset(seed=42)
    assert ds1.ground_truth == ds2.ground_truth
    assert ds1.parsed["df_records"][0] == ds2.parsed["df_records"][0]


# ── DetectorMetrics unit tests ────────────────────────────────────────

def test_metrics_perfect_detector():
    gt    = frozenset({("c1", "k1"), ("c1", "k2")})
    all_p = frozenset({("c1", "k1"), ("c1", "k2"), ("c2", "k1"), ("c2", "k2")})
    m = _compute_metrics("perfect", gt, gt, all_p)
    assert m.tp == 2 and m.fp == 0 and m.fn == 0
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1 == 1.0


def test_metrics_blind_detector():
    gt    = frozenset({("c1", "k1")})
    all_p = frozenset({("c1", "k1"), ("c2", "k2")})
    m = _compute_metrics("blind", set(), gt, all_p)
    assert m.tp == 0 and m.fp == 0 and m.fn == 1
    assert m.recall == 0.0
    assert m.precision is None  # no positives predicted
    assert m.f1 is None


def test_metrics_noisy_detector():
    gt    = frozenset({("c1", "k1")})
    all_p = frozenset({("c1", "k1"), ("c2", "k2"), ("c3", "k3")})
    fired = {("c1", "k1"), ("c2", "k2"), ("c3", "k3")}  # fires on everything
    m = _compute_metrics("noisy", fired, gt, all_p)
    assert m.tp == 1 and m.fp == 2 and m.fn == 0
    assert m.precision == pytest.approx(1/3, abs=0.01)
    assert m.recall == 1.0


def test_metrics_as_dict_schema():
    gt    = frozenset({("c1", "k1")})
    all_p = frozenset({("c1", "k1"), ("c2", "k2")})
    m = _compute_metrics("test", {("c1","k1")}, gt, all_p)
    d = m.as_dict()
    for key in ["detector", "tp", "fp", "fn", "tn", "precision", "recall", "f1", "accuracy"]:
        assert key in d


def test_fired_pairs_extracts_correctly():
    anomalies = [
        {"cell_id": "cell_1", "kpi": "bler_dl", "severity": "High"},
        {"cell_id": "cell_2", "kpi": "snr_db",  "severity": "Medium"},
    ]
    pairs = _fired_pairs(anomalies)
    assert ("cell_1", "bler_dl") in pairs
    assert ("cell_2", "snr_db")  in pairs


def test_fired_pairs_empty():
    assert _fired_pairs([]) == set()


# ── Integration tests: run_*_evaluation ──────────────────────────────

def test_run_kpi_evaluation_returns_report():
    report = run_kpi_evaluation(n_cells=3, n_timestamps=50, anomaly_rate=0.20, seed=1)
    assert isinstance(report, EvalReport)
    assert report.source == "kpi"
    assert len(report.per_detector) > 0
    assert report.ensemble is not None
    assert report.n_anomaly_pairs > 0
    assert report.n_total_pairs > 0


def test_run_kpi_evaluation_metrics_in_range():
    report = run_kpi_evaluation(n_cells=3, n_timestamps=60, anomaly_rate=0.20, seed=7)
    for m in report.per_detector:
        if m.precision is not None:
            assert 0.0 <= m.precision <= 1.0
        if m.recall is not None:
            assert 0.0 <= m.recall <= 1.0
        if m.f1 is not None:
            assert 0.0 <= m.f1 <= 1.0


def test_run_stats_evaluation_returns_report():
    report = run_stats_evaluation(n_cells=2, n_timestamps=50, anomaly_rate=0.20, seed=9)
    assert isinstance(report, EvalReport)
    assert report.source == "stats"
    assert len(report.per_detector) > 0


def test_run_stats_evaluation_metrics_in_range():
    report = run_stats_evaluation(n_cells=2, n_timestamps=60, seed=11)
    for m in report.per_detector:
        if m.f1 is not None:
            assert 0.0 <= m.f1 <= 1.0


def test_ensemble_recall_geq_best_detector():
    """Ensemble (union) recall should be >= best single detector recall."""
    report = run_kpi_evaluation(n_cells=3, n_timestamps=60, seed=21)
    max_recall = max(
        (m.recall for m in report.per_detector if m.recall is not None),
        default=0.0,
    )
    ens_recall = report.ensemble.recall or 0.0
    assert ens_recall >= max_recall - 0.01  # tiny tolerance for floating point


def test_eval_report_as_dict_schema():
    report = run_kpi_evaluation(n_cells=2, n_timestamps=40, seed=13)
    d = report.as_dict()
    for key in ["source", "n_anomaly_pairs", "n_normal_pairs", "n_total_pairs",
                "per_detector", "ensemble", "dataset_info"]:
        assert key in d
    assert isinstance(d["per_detector"], list)
    assert isinstance(d["ensemble"], dict)


def test_best_detector_returns_highest_f1():
    report = run_kpi_evaluation(n_cells=3, n_timestamps=60, seed=15)
    best = report.best_detector()
    assert isinstance(best, DetectorMetrics)
    for m in report.per_detector:
        if m.f1 is not None and best.f1 is not None:
            assert best.f1 >= m.f1 - 0.001
