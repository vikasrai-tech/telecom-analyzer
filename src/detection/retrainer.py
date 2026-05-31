"""
Nightly Retrainer — Tier 5 → Tier 3 feedback loop

Reads engineer feedback → adjusts detector parameters → saves config.
The detection layer picks up the saved config on next run.

Retraining strategy per detector type:
  ML detectors (IF, OC-SVM, LOF, EE):
    contamination / nu adjusted by per-detector FP rate from feedback.
    Formula: new_contamination = base + alpha * (fp_rate - target_fp_rate)
    Clamped to [0.02, 0.40].

  Statistical detector:
    Sensitivity multiplier adjusted: high FP rate → raise thresholds slightly.

  LSTM Autoencoder:
    Reconstruction threshold adjusted: FP rate → raise threshold.

  KPI / Stats detectors:
    Same contamination/sensitivity logic applied per-method.

Output: data/models/retrain_config.json + retraining report dict.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("data/models/retrain_config.json")

# ── Base (default) params ─────────────────────────────────────────────
BASE_PARAMS: Dict[str, Any] = {
    # PCAP detectors
    "Isolation Forest":   {"contamination": 0.15},
    "One-Class SVM":      {"nu": 0.15},
    "LOF":                {"contamination": 0.15},
    "Elliptic Envelope":  {"contamination": 0.15},
    "Statistical":        {"sensitivity": 1.0},
    "LSTM Autoencoder":   {"threshold_multiplier": 1.0},
    # KPI detectors
    "Threshold":          {"sensitivity": 1.0},
    "Peer Comparison":    {"z_threshold": 2.0},
    "Trend":              {"slope_threshold": 0.5},
    "IQR":                {"k": 3.0},
    "CUSUM":              {"threshold": 4.0},
    "Bollinger Bands":    {"k": 2.5},
}

TARGET_FP_RATE = 0.10   # desired FP rate (10%)
ALPHA          = 0.30   # learning rate for param adjustment
MIN_FEEDBACK   = 5      # minimum feedback records before adjusting


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _adjust_contamination(base: float, fp_rate: float) -> float:
    """Lower contamination when FP rate is high (detector too aggressive)."""
    delta = ALPHA * (fp_rate - TARGET_FP_RATE)
    return round(_clamp(base - delta, 0.02, 0.40), 4)


def _adjust_sensitivity(base: float, fp_rate: float) -> float:
    """Raise sensitivity multiplier when FP rate is high."""
    delta = ALPHA * (fp_rate - TARGET_FP_RATE)
    return round(_clamp(base + delta, 0.5, 2.0), 4)


def _adjust_threshold(base: float, fp_rate: float) -> float:
    """Raise threshold when FP rate is high."""
    delta = ALPHA * (fp_rate - TARGET_FP_RATE) * base
    return round(_clamp(base + delta, base * 0.5, base * 2.0), 4)


def run_retraining(
    store_path:  Optional[Path] = None,
    config_path: Path = CONFIG_PATH,
    dry_run:     bool = False,
) -> Dict[str, Any]:
    """
    Main entry point.
    Reads feedback, adjusts params, saves config.
    Returns a retraining report.
    """
    from src.feedback.store import feedback_stats, load_feedback

    if store_path is None:
        from src.feedback.store import DEFAULT_STORE
        store_path = DEFAULT_STORE

    stats   = feedback_stats(store_path=store_path)
    records = load_feedback(store_path=store_path)

    report: Dict[str, Any] = {
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "total_feedback":   stats["total"],
        "overall_precision":stats["precision"],
        "dry_run":          dry_run,
        "adjustments":      {},
        "skipped":          [],
        "status":           "ok",
    }

    if stats["total"] < MIN_FEEDBACK:
        report["status"]  = "skipped"
        report["reason"]  = f"Need ≥ {MIN_FEEDBACK} feedback records (have {stats['total']})"
        logger.info(f"[retrainer] {report['reason']}")
        return report

    # Load existing config (or start from base)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists() and config_path.stat().st_size > 0:
        with open(config_path) as f:
            current = json.load(f)
        params = current.get("params", dict(BASE_PARAMS))
    else:
        params = dict(BASE_PARAMS)

    by_det = stats.get("by_detector", {})

    for det, det_counts in by_det.items():
        total_rated = det_counts.get("correct", 0) + det_counts.get("false_positive", 0)
        if total_rated < 2:
            report["skipped"].append(det)
            continue

        fp_rate = det_counts.get("false_positive", 0) / total_rated
        old     = dict(params.get(det, BASE_PARAMS.get(det, {})))
        new     = dict(old)

        if det in ("Isolation Forest", "LOF", "Elliptic Envelope"):
            new["contamination"] = _adjust_contamination(
                old.get("contamination", 0.15), fp_rate
            )
        elif det == "One-Class SVM":
            new["nu"] = _adjust_contamination(old.get("nu", 0.15), fp_rate)

        elif det in ("Statistical", "Threshold"):
            new["sensitivity"] = _adjust_sensitivity(
                old.get("sensitivity", 1.0), fp_rate
            )
        elif det == "LSTM Autoencoder":
            new["threshold_multiplier"] = _adjust_sensitivity(
                old.get("threshold_multiplier", 1.0), fp_rate
            )
        elif det == "Peer Comparison":
            new["z_threshold"] = _adjust_threshold(
                old.get("z_threshold", 2.0), fp_rate
            )
        elif det == "Trend":
            new["slope_threshold"] = _adjust_threshold(
                old.get("slope_threshold", 0.5), fp_rate
            )
        elif det == "IQR":
            new["k"] = _adjust_threshold(old.get("k", 3.0), fp_rate)
        elif det == "CUSUM":
            new["threshold"] = _adjust_threshold(
                old.get("threshold", 4.0), fp_rate
            )
        elif det == "Bollinger Bands":
            new["k"] = _adjust_threshold(old.get("k", 2.5), fp_rate)

        params[det] = new
        report["adjustments"][det] = {
            "fp_rate":  round(fp_rate, 3),
            "before":   old,
            "after":    new,
            "changed":  old != new,
        }
        logger.info(f"[retrainer] {det}: fp_rate={fp_rate:.2f}  {old} → {new}")

    # Save config
    if not dry_run:
        new_config = {
            "updated_at":    report["timestamp"],
            "total_feedback":stats["total"],
            "precision":     stats["precision"],
            "params":        params,
        }
        with open(config_path, "w") as f:
            json.dump(new_config, f, indent=2)
        logger.info(f"[retrainer] Config saved: {config_path}")

    report["new_params"] = params
    return report


def load_retrain_config(config_path: Path = CONFIG_PATH) -> Dict[str, Any]:
    """Load saved retrain config. Returns base params if not found."""
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f)
        return cfg.get("params", BASE_PARAMS)
    return dict(BASE_PARAMS)


def get_detector_param(detector: str, param: str,
                       config_path: Path = CONFIG_PATH) -> Any:
    """Convenience: get one param for one detector from saved config."""
    cfg = load_retrain_config(config_path)
    return cfg.get(detector, BASE_PARAMS.get(detector, {})).get(
        param, BASE_PARAMS.get(detector, {}).get(param)
    )
