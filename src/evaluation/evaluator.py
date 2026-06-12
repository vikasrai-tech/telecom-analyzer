"""
Evaluation Engine — Precision / Recall / F1 per detector

Evaluation strategy:
  Unit of evaluation = (cell_id, kpi/metric) pair.
  A detector "fires" on a pair if it returns ≥1 anomaly with matching cell_id + kpi.
  Ground truth = set of pairs with injected anomalies (from dataset.py).

  TP = pair is anomalous AND detector fired
  FP = pair is normal   AND detector fired
  FN = pair is anomalous AND detector did NOT fire
  TN = pair is normal   AND detector did NOT fire

  precision = TP / (TP + FP)    (of what we flagged, how much was real)
  recall    = TP / (TP + FN)    (of what was real, how much we found)
  f1        = 2·P·R / (P+R)

Ensemble is evaluated by union: a pair is flagged if ANY detector flagged it.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from .dataset import LabeledDataset, generate_kpi_dataset, generate_stats_dataset

logger = logging.getLogger(__name__)


# ── Result types ──────────────────────────────────────────────────────

@dataclass
class DetectorMetrics:
    name: str
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> Optional[float]:
        d = self.tp + self.fp
        return round(self.tp / d, 4) if d > 0 else None

    @property
    def recall(self) -> Optional[float]:
        d = self.tp + self.fn
        return round(self.tp / d, 4) if d > 0 else None

    @property
    def f1(self) -> Optional[float]:
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return round(2 * p * r / (p + r), 4)

    @property
    def accuracy(self) -> float:
        total = self.tp + self.fp + self.fn + self.tn
        return round((self.tp + self.tn) / total, 4) if total > 0 else 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "detector":  self.name,
            "tp":        self.tp,
            "fp":        self.fp,
            "fn":        self.fn,
            "tn":        self.tn,
            "precision": self.precision,
            "recall":    self.recall,
            "f1":        self.f1,
            "accuracy":  self.accuracy,
        }


@dataclass
class EvalReport:
    source: str                         # "kpi" or "stats"
    per_detector: List[DetectorMetrics]
    ensemble: DetectorMetrics
    n_anomaly_pairs: int
    n_normal_pairs:  int
    n_total_pairs:   int
    dataset_info: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source":           self.source,
            "n_anomaly_pairs":  self.n_anomaly_pairs,
            "n_normal_pairs":   self.n_normal_pairs,
            "n_total_pairs":    self.n_total_pairs,
            "per_detector":     [m.as_dict() for m in self.per_detector],
            "ensemble":         self.ensemble.as_dict(),
            "dataset_info":     self.dataset_info,
        }

    def best_detector(self) -> DetectorMetrics:
        scored = [m for m in self.per_detector if m.f1 is not None]
        return max(scored, key=lambda m: m.f1 or 0) if scored else self.per_detector[0]


# ── Matching helpers ──────────────────────────────────────────────────

def _fired_pairs(anomalies: List[Dict], kpi_field: str = "kpi") -> Set[Tuple[str, str]]:
    """
    Extract (cell_id, kpi) pairs that a detector flagged.
    Handles both KPI anomalies (cell_id + kpi) and Stats anomalies (cell_id + kpi).
    "Fleet-wide" cell_id is expanded to all cells if possible.
    """
    pairs: Set[Tuple[str, str]] = set()
    for a in anomalies:
        cell = str(a.get("cell_id") or a.get("cell") or "")
        kpi  = str(a.get(kpi_field) or a.get("kpi") or a.get("metric") or "")
        if cell and kpi:
            pairs.add((cell, kpi))
    return pairs


def _compute_metrics(
    name: str,
    fired: Set[Tuple[str, str]],
    ground_truth: FrozenSet[Tuple[str, str]],
    all_pairs: FrozenSet[Tuple[str, str]],
) -> DetectorMetrics:
    tp = len(fired & ground_truth)
    fp = len(fired - ground_truth)
    fn = len(ground_truth - fired)
    tn = len((all_pairs - ground_truth) - fired)
    return DetectorMetrics(name=name, tp=tp, fp=fp, fn=fn, tn=tn)


# ── KPI evaluation ────────────────────────────────────────────────────

def run_kpi_evaluation(
    n_cells: int = 5,
    n_timestamps: int = 100,
    anomaly_rate: float = 0.20,
    seed: int = 42,
) -> EvalReport:
    """
    Generate a synthetic KPI dataset, run all 6 KPI detectors, return EvalReport.
    """
    from src.detection.kpi_detector import detect_kpi_anomalies_by_detector

    labeled = generate_kpi_dataset(
        n_cells=n_cells, n_timestamps=n_timestamps,
        anomaly_rate=anomaly_rate, seed=seed,
    )
    parsed = labeled.parsed
    gt     = labeled.ground_truth

    # All evaluable (cell, kpi) pairs
    cells     = parsed["cells"]
    kpi_cols  = parsed["kpi_columns"]
    # Use all pairs; ground_truth already excludes threshold-less KPIs
    evaluable_pairs = frozenset((c, k) for c in cells for k in kpi_cols)

    logger.info(f"[eval-kpi] Ground truth: {len(gt)} anomalous pairs / {len(evaluable_pairs)} total")

    by_detector = detect_kpi_anomalies_by_detector(parsed)

    per_detector_metrics: List[DetectorMetrics] = []
    ensemble_fired: Set[Tuple[str, str]] = set()

    for det_name, anomalies in by_detector.items():
        fired = _fired_pairs(anomalies, kpi_field="kpi")
        # Restrict to evaluable pairs
        fired &= evaluable_pairs
        ensemble_fired |= fired
        metrics = _compute_metrics(det_name, fired, gt, evaluable_pairs)
        per_detector_metrics.append(metrics)
        logger.info(
            f"[eval-kpi] {det_name:35s} "
            f"P={metrics.precision or 0:.2f}  R={metrics.recall or 0:.2f}  "
            f"F1={metrics.f1 or 0:.2f}"
        )

    ensemble_fired &= evaluable_pairs
    ensemble_metrics = _compute_metrics("Ensemble (union)", ensemble_fired, gt, evaluable_pairs)
    logger.info(
        f"[eval-kpi] {'Ensemble (union)':35s} "
        f"P={ensemble_metrics.precision or 0:.2f}  R={ensemble_metrics.recall or 0:.2f}  "
        f"F1={ensemble_metrics.f1 or 0:.2f}"
    )

    return EvalReport(
        source="kpi",
        per_detector=per_detector_metrics,
        ensemble=ensemble_metrics,
        n_anomaly_pairs=labeled.n_anomaly_pairs,
        n_normal_pairs=len(evaluable_pairs) - labeled.n_anomaly_pairs,
        n_total_pairs=len(evaluable_pairs),
        dataset_info={
            "n_cells": n_cells,
            "n_timestamps": n_timestamps,
            "anomaly_rate": anomaly_rate,
            "seed": seed,
            "injected_types": list({d["type"] for d in labeled.anomaly_details}),
        },
    )


# ── Stats evaluation ──────────────────────────────────────────────────

def run_stats_evaluation(
    n_cells: int = 3,
    n_timestamps: int = 100,
    anomaly_rate: float = 0.20,
    seed: int = 99,
) -> EvalReport:
    """
    Generate a synthetic Stats dataset, run all 6 stats detectors, return EvalReport.
    """
    from src.detection.stats_detector import detect_stats_anomalies_by_detector

    labeled = generate_stats_dataset(
        n_cells=n_cells, n_timestamps=n_timestamps,
        anomaly_rate=anomaly_rate, seed=seed,
    )
    parsed = labeled.parsed
    gt     = labeled.ground_truth

    cells        = parsed["cells"]
    metric_cols  = parsed["l1l2_columns"]
    all_pairs    = frozenset((c, m) for c in cells for m in metric_cols)

    logger.info(f"[eval-stats] Ground truth: {len(gt)} anomalous pairs / {len(all_pairs)} total")

    by_detector = detect_stats_anomalies_by_detector(parsed)

    per_detector_metrics: List[DetectorMetrics] = []
    ensemble_fired: Set[Tuple[str, str]] = set()

    for det_name, anomalies in by_detector.items():
        fired = _fired_pairs(anomalies, kpi_field="kpi")
        fired &= all_pairs
        ensemble_fired |= fired
        metrics = _compute_metrics(det_name, fired, gt, all_pairs)
        per_detector_metrics.append(metrics)
        logger.info(
            f"[eval-stats] {det_name:35s} "
            f"P={metrics.precision or 0:.2f}  R={metrics.recall or 0:.2f}  "
            f"F1={metrics.f1 or 0:.2f}"
        )

    ensemble_fired &= all_pairs
    ensemble_metrics = _compute_metrics("Ensemble (union)", ensemble_fired, gt, all_pairs)
    logger.info(
        f"[eval-stats] {'Ensemble (union)':35s} "
        f"P={ensemble_metrics.precision or 0:.2f}  R={ensemble_metrics.recall or 0:.2f}  "
        f"F1={ensemble_metrics.f1 or 0:.2f}"
    )

    return EvalReport(
        source="stats",
        per_detector=per_detector_metrics,
        ensemble=ensemble_metrics,
        n_anomaly_pairs=len(gt),
        n_normal_pairs=len(all_pairs) - len(gt),
        n_total_pairs=len(all_pairs),
        dataset_info={
            "n_cells": n_cells,
            "n_timestamps": n_timestamps,
            "anomaly_rate": anomaly_rate,
            "seed": seed,
            "injected_types": list({d["type"] for d in labeled.anomaly_details}),
        },
    )
