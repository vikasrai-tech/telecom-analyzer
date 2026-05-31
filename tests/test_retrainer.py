"""Tests for the Nightly Retrainer."""

import json
import tempfile
from pathlib import Path

from src.detection.retrainer import (
    run_retraining, load_retrain_config, get_detector_param, BASE_PARAMS
)
from src.feedback.store import save_feedback


def _make_feedback_store(verdicts: dict) -> Path:
    """Create a temp feedback store with given {detector: [verdict, ...]} entries."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        store = Path(f.name)
    for det, vs in verdicts.items():
        for i, v in enumerate(vs):
            save_feedback(f"ev_{det}_{i}", "kpi", "metric", "High",
                          det, "PCI_1", "evidence", v, store_path=store)
    return store


def test_retrain_skipped_too_few_records():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        store = Path(f.name)
    # Only 2 records — below threshold of 5
    save_feedback("e1","kpi","m","High","Isolation Forest","c","e","correct",  store_path=store)
    save_feedback("e2","kpi","m","High","Isolation Forest","c","e","correct",  store_path=store)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cfg_path = Path(f.name)

    report = run_retraining(store_path=store, config_path=cfg_path, dry_run=True)
    assert report["status"] == "skipped"


def test_retrain_adjusts_high_fp_detector():
    """Isolation Forest with 80% FP rate → contamination should drop."""
    store = _make_feedback_store({
        "Isolation Forest": ["false_positive"] * 8 + ["correct"] * 2,
    })
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cfg_path = Path(f.name)

    report = run_retraining(store_path=store, config_path=cfg_path, dry_run=True)
    assert report["status"] == "ok"
    assert "Isolation Forest" in report["adjustments"]
    adj = report["adjustments"]["Isolation Forest"]
    # FP rate=0.8 > TARGET_FP_RATE=0.1 → contamination should decrease
    assert adj["after"]["contamination"] < adj["before"]["contamination"]


def test_retrain_adjusts_low_fp_detector():
    """Isolation Forest with 0% FP rate → contamination can increase slightly."""
    store = _make_feedback_store({
        "Isolation Forest": ["correct"] * 10,
    })
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cfg_path = Path(f.name)

    report = run_retraining(store_path=store, config_path=cfg_path, dry_run=True)
    assert "Isolation Forest" in report["adjustments"]
    adj = report["adjustments"]["Isolation Forest"]
    # FP rate=0 < TARGET_FP_RATE=0.1 → contamination can go up
    assert adj["after"]["contamination"] >= adj["before"]["contamination"]


def test_retrain_writes_config():
    store = _make_feedback_store({
        "Isolation Forest": ["false_positive"] * 5 + ["correct"] * 5,
        "Threshold":        ["correct"] * 8 + ["false_positive"] * 2,
    })
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cfg_path = Path(f.name)

    report = run_retraining(store_path=store, config_path=cfg_path, dry_run=False)
    assert report["status"] == "ok"
    assert cfg_path.exists()

    with open(cfg_path) as f:
        saved = json.load(f)
    assert "params" in saved
    assert "updated_at" in saved
    assert "Isolation Forest" in saved["params"]


def test_load_retrain_config_default_when_missing():
    cfg = load_retrain_config(Path("/tmp/nonexistent_config_xyz.json"))
    assert cfg == BASE_PARAMS


def test_load_retrain_config_reads_saved():
    store = _make_feedback_store({
        "LOF": ["false_positive"] * 7 + ["correct"] * 3,
    })
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cfg_path = Path(f.name)

    run_retraining(store_path=store, config_path=cfg_path, dry_run=False)
    cfg = load_retrain_config(cfg_path)
    # LOF contamination should have been adjusted
    assert "LOF" in cfg
    assert cfg["LOF"]["contamination"] != BASE_PARAMS["LOF"]["contamination"]


def test_get_detector_param_default():
    val = get_detector_param("Isolation Forest", "contamination",
                             Path("/tmp/no_such_config.json"))
    assert val == 0.15  # base default


def test_dry_run_does_not_write():
    store = _make_feedback_store({
        "Isolation Forest": ["false_positive"] * 5 + ["correct"] * 5,
    })
    cfg_path = Path(tempfile.mktemp(suffix=".json"))
    assert not cfg_path.exists()

    run_retraining(store_path=store, config_path=cfg_path, dry_run=True)
    assert not cfg_path.exists()


def test_contamination_clamped():
    """Ensure contamination never goes below 0.02 or above 0.40."""
    store = _make_feedback_store({
        "Isolation Forest": ["false_positive"] * 20 + ["correct"] * 1,
    })
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cfg_path = Path(f.name)

    report = run_retraining(store_path=store, config_path=cfg_path, dry_run=True)
    adj = report["adjustments"].get("Isolation Forest", {})
    if adj:
        assert adj["after"]["contamination"] >= 0.02
        assert adj["after"]["contamination"] <= 0.40
