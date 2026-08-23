"""
Anomaly Detector — six-detector ensemble.

Tabular detectors (procedure-level features):
  - Isolation Forest      — unsupervised tree-based
  - Statistical           — rule/threshold, telecom domain knowledge
  - One-Class SVM         — kernel boundary, non-linear normal region
  - LOF                   — local density, cluster-edge outliers
  - Elliptic Envelope     — Mahalanobis distance, Gaussian baseline

Sequential detector (message_log windows):
  - LSTM Autoencoder      — sequence reconstruction, catches order violations

The stub is kept for backward compat with existing tests.
"""

import logging
from typing import List, Dict, Any

from .detectors import (
    IsolationForestDetector,
    StatisticalDetector,
    LSTMAutoencoderDetector,
    OneClassSVMDetector,
    LOFDetector,
    EllipticEnvelopeDetector,
)

logger = logging.getLogger(__name__)

# Ordered list of all detectors: (display_name, class)
ALL_DETECTORS = [
    ("Isolation Forest", IsolationForestDetector),
    ("Statistical", StatisticalDetector),
    ("One-Class SVM", OneClassSVMDetector),
    ("LOF", LOFDetector),
    ("Elliptic Envelope", EllipticEnvelopeDetector),
    ("LSTM Autoencoder", LSTMAutoencoderDetector),
]


def detect_anomalies_by_detector(
    parsed: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Run every detector independently and return a dict keyed by detector name.
    Use this for the comparison matrix in the dashboard.
    """
    results: Dict[str, List[Dict[str, Any]]] = {}
    # Load retrained params if available
    try:
        from src.detection.retrainer import load_retrain_config
        cfg = load_retrain_config()
    except Exception:
        cfg = {}

    for name, cls in ALL_DETECTORS:
        try:
            params = cfg.get(name, {})
            if name == "Isolation Forest" and "contamination" in params:
                inst = cls(contamination=params["contamination"])
            elif name == "One-Class SVM" and "nu" in params:
                inst = cls(nu=params["nu"])
            elif name in ("LOF", "Elliptic Envelope") and "contamination" in params:
                inst = cls(contamination=params["contamination"])
            else:
                inst = cls()
            found = inst.detect(parsed)
            logger.info(f"{name}: {len(found)} anomalies")
            results[name] = found
        except Exception as e:
            logger.warning(f"{name} failed: {e}")
            results[name] = []
    return results


def merge_detector_results(
    by_detector: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Merge pre-computed per-detector results into a deduplicated anomaly list."""
    all_anomalies = [a for anoms in by_detector.values() for a in anoms]
    return _merge(all_anomalies)


def detect_anomalies(
    parsed: Dict[str, Any],
    use_if: bool = True,
    use_stat: bool = True,
    use_lstm: bool = True,
    use_ocsvm: bool = True,
    use_lof: bool = True,
    use_elliptic: bool = True,
) -> List[Dict[str, Any]]:
    """
    Run all enabled detectors and return a merged, deduplicated anomaly list.
    Each anomaly carries: type, severity, score, detector, evidence,
    procedure, layer, failure_causes, recommendation.
    """
    toggles = {
        "Isolation Forest": use_if,
        "Statistical": use_stat,
        "LSTM Autoencoder": use_lstm,
        "One-Class SVM": use_ocsvm,
        "LOF": use_lof,
        "Elliptic Envelope": use_elliptic,
    }

    all_anomalies: List[Dict[str, Any]] = []

    for name, cls in ALL_DETECTORS:
        if not toggles.get(name, True):
            continue
        try:
            results = cls().detect(parsed)
            logger.info(f"{name}: {len(results)} anomalies")
            all_anomalies.extend(results)
        except Exception as e:
            logger.warning(f"{name} failed: {e}")

    # Deduplicate: if two detectors flag the same procedure, keep the
    # highest-severity one but record that multiple detectors agreed.
    merged = _merge(all_anomalies)
    logger.info(f"Total anomalies after merge: {len(merged)}")
    return merged


def _merge(anomalies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group by (procedure, type), keep highest severity/score, tag detectors.
    Sort by severity then score descending.
    """
    SEV_RANK = {"High": 3, "Medium": 2, "Low": 1}
    groups: Dict[str, Dict[str, Any]] = {}

    for a in anomalies:
        key = f"{a.get('procedure', '?')}|{a.get('type', '?')}"
        if key not in groups:
            groups[key] = dict(a)
            groups[key]["detectors"] = [a["detector"]]
        else:
            existing = groups[key]
            # Keep highest severity
            if SEV_RANK.get(a["severity"], 0) > SEV_RANK.get(existing["severity"], 0):
                groups[key].update({
                    "severity": a["severity"],
                    "score": a["score"],
                    "evidence": a["evidence"],
                })
            existing["detectors"].append(a["detector"])
            # Deduplicate detector names
            existing["detectors"] = list(dict.fromkeys(existing["detectors"]))

    result = list(groups.values())
    # Tag multi-detector agreement
    for a in result:
        dets = a.get("detectors", [a["detector"]])
        a["detector"] = " + ".join(dets)
        a["confirmed_by"] = len(dets)

    # Sort: High → Medium → Low, then by score descending
    result.sort(key=lambda x: (SEV_RANK.get(x["severity"], 0), x["score"]), reverse=True)
    return result


# ── Backward-compat stub (used by existing tests) ─────────────────────

def detect_anomalies_stub(
    parsed: Dict[str, Any],
    detector: str = "Isolation Forest (stub)",
) -> List[Dict[str, Any]]:
    """Kept for test backward compat. New code should call detect_anomalies()."""
    procedures = parsed.get("procedures", {})
    anomalies = []
    for proc_name, stats in procedures.items():
        if stats.get("failure", 0) > 0:
            anomalies.append({
                "type": f"{proc_name} failure spike",
                "severity": "Medium" if stats["failure"] > 1 else "Low",
                "score": round(stats["failure"] / max(stats["attempts"], 1), 2),
                "detector": detector,
                "evidence": (
                    f"{stats['failure']} failures; "
                    f"success rate {stats['success_rate']}%"
                ),
            })
    return anomalies
