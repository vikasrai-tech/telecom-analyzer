"""
Detection benchmark — runs 5 detection methods on the 64-UE / 6-hour dataset
and computes scenario-level (cell-level) precision, recall, and F1.

Methods:
  1. threshold_only          — KPI Threshold detector, flag any violation
  2. single_method_iqr       — KPI IQR detector only (distribution-based)
  3. full_ensemble           — All 6 KPI + 6 Stats detectors, flag any violation
  4. ensemble_with_router    — Full ensemble + EventRouter cross-source (≥2 sources)
  5. stats_count_threshold   — Stats domain, data-driven count > mean+1.5*std

Important: KPI-only methods (1, 2) show high FP because FDD cells (PCI_9-16)
generate ~727 threshold violations vs ~163 for TDD normal cells — a dataset
characteristic (different channel capacity calibration), not a method defect.
Method 5 uses Stats anomaly counts which cleanly separate fault vs normal cells.

Usage:
    cd /mnt/e/telecom-analyzer
    python scripts/run_detection_benchmark.py

Results saved to:
    results/detection/detection_metrics.json
    results/detection/detection_metrics.csv
    results/correlation/correlation_metrics.json
"""

import csv
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# -- path setup
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATA_KPI   = ROOT / "data" / "raw" / "kpi_64ue_6hr.csv"
DATA_STATS = ROOT / "data" / "raw" / "stats_64ue_6hr.csv"
OUT_DET    = ROOT / "results" / "detection"
OUT_CORR   = ROOT / "results" / "correlation"


def main():
    print("=" * 60)
    print("DETECTION BENCHMARK — 64-UE 6-hour dataset")
    print(f"Random seed: {RANDOM_SEED}")
    print("=" * 60)

    # ── Parse datasets ───────────────────────────────────────────────────
    print("\n[1/6] Parsing KPI dataset ...")
    from src.parsers.kpi_parser import parse_kpi_file
    kpi_parsed = parse_kpi_file(str(DATA_KPI))
    print(f"  KPI: {kpi_parsed['rows']} rows, {len(kpi_parsed['cells'])} cells")

    print("[2/6] Parsing Stats dataset ...")
    from src.parsers.stats_parser import parse_stats_file
    stats_parsed = parse_stats_file(str(DATA_STATS))
    print(f"  Stats: {stats_parsed['rows']} rows, {len(stats_parsed['cells'])} cells")

    # ── Ground truth ──────────────────────────────────────────────────────
    from src.evaluation.ground_truth import FAULT_CELLS, ALL_CELLS, FAULT_SCENARIOS
    fault_cells = FAULT_CELLS
    all_cells   = ALL_CELLS
    print(f"\n[3/6] Ground truth: fault cells = {sorted(fault_cells)}")
    print(f"      Total cells in dataset: {len(all_cells)}")

    # ── Run 4 methods ─────────────────────────────────────────────────────
    print("\n[4/6] Running detection methods ...")
    from src.evaluation.detection_evaluator import (
        run_method_threshold_only,
        run_method_single_iqr,
        run_method_full_ensemble,
        run_method_ensemble_with_router,
        run_method_stats_count_threshold,
    )
    from src.evaluation.detection_metrics import compute_scenario_metrics

    methods = {}

    # Method 1: Threshold only
    print("  Method 1: threshold_only (KPI) ...")
    cells_1 = run_method_threshold_only(kpi_parsed, stats_parsed)
    methods["threshold_only"] = {
        "label": "Threshold — KPI only (any violation)",
        "description": (
            "Threshold detector only on KPI data. Flags any cell with ≥1 threshold "
            "violation. Note: FDD cells (PCI_9-16) generate ~727 threshold alerts vs "
            "~163 for TDD normal cells due to dataset capacity calibration differences."
        ),
        "flagged_cells": sorted(cells_1),
        "metrics": compute_scenario_metrics(cells_1, fault_cells, all_cells),
    }

    # Method 2: IQR only
    print("  Method 2: single_method_iqr (KPI) ...")
    cells_2 = run_method_single_iqr(kpi_parsed, stats_parsed)
    methods["single_method_iqr"] = {
        "label": "IQR — KPI only (distribution-based, any violation)",
        "description": "IQR/Tukey-fence detector only on KPI data. Same FDD bias as Threshold.",
        "flagged_cells": sorted(cells_2),
        "metrics": compute_scenario_metrics(cells_2, fault_cells, all_cells),
    }

    # Method 3: Full ensemble
    print("  Method 3: full_ensemble (KPI + Stats) ...")
    cells_3 = run_method_full_ensemble(kpi_parsed, stats_parsed)
    methods["full_ensemble"] = {
        "label": "Full Ensemble — KPI+Stats (any violation)",
        "description": "All 6 KPI + 6 Stats detectors; cell flagged if any detector fires.",
        "flagged_cells": sorted(cells_3),
        "metrics": compute_scenario_metrics(cells_3, fault_cells, all_cells),
    }

    # Method 4: Ensemble + Router
    print("  Method 4: ensemble_with_router ...")
    result_4 = run_method_ensemble_with_router(kpi_parsed, stats_parsed)
    if isinstance(result_4, tuple):
        cells_4, router = result_4
    else:
        cells_4, router = result_4, None

    methods["ensemble_with_router"] = {
        "label": "Ensemble + EventRouter (≥2 source domains)",
        "description": (
            "Full ensemble (KPI + Stats) + EventRouter cross-source correlation. "
            "Cell qualifies only if ≥2 source domains (kpi AND stats) both flag it."
        ),
        "flagged_cells": sorted(cells_4),
        "metrics": compute_scenario_metrics(cells_4, fault_cells, all_cells),
    }

    # Method 5: Stats count-threshold (data-driven)
    print("  Method 5: stats_count_threshold (data-driven mean+1.5σ) ...")
    cells_5 = run_method_stats_count_threshold(stats_parsed, kpi_parsed, z_factor=1.5)
    methods["stats_count_threshold"] = {
        "label": "Stats Count-Threshold (mean + 1.5σ, data-driven)",
        "description": (
            "Flags cells whose total Stats anomaly count exceeds mean + 1.5*std across "
            "all cells. Threshold computed from data — no post-hoc label fitting. "
            "Stats domain is not affected by FDD/TDD capacity bias."
        ),
        "flagged_cells": sorted(cells_5),
        "metrics": compute_scenario_metrics(cells_5, fault_cells, all_cells),
    }

    # ── Correlation metrics ───────────────────────────────────────────────
    print("\n[5/6] Computing correlation metrics ...")
    corr_metrics = None
    if router is not None:
        from src.evaluation.correlation_metrics import compute_correlation_assignment_rate
        corr_metrics = compute_correlation_assignment_rate(router)
    else:
        print("  (No router available — re-running ensemble+router for correlation metrics)")
        from src.detection.kpi_detector import detect_kpi_anomalies
        from src.detection.stats_detector import detect_stats_anomalies
        from src.orchestrator.event_router import EventRouter
        r = EventRouter()
        r.ingest(detect_kpi_anomalies(kpi_parsed), source="kpi")
        r.ingest(detect_stats_anomalies(stats_parsed), source="stats")
        from src.evaluation.correlation_metrics import compute_correlation_assignment_rate
        corr_metrics = compute_correlation_assignment_rate(r)

    # ── Save results ──────────────────────────────────────────────────────
    print("\n[6/6] Saving results ...")
    OUT_DET.mkdir(parents=True, exist_ok=True)
    OUT_CORR.mkdir(parents=True, exist_ok=True)

    det_output = {
        "dataset": {
            "kpi_file":       str(DATA_KPI.name),
            "stats_file":     str(DATA_STATS.name),
            "kpi_rows":       kpi_parsed["rows"],
            "stats_rows":     stats_parsed["rows"],
            "n_cells":        len(all_cells),
            "fault_cells":    sorted(fault_cells),
            "n_fault_scenarios": len(FAULT_SCENARIOS),
        },
        "evaluation_type": "scenario-level / cell-level detection",
        "random_seed":     RANDOM_SEED,
        "methods":         methods,
    }

    json_path = OUT_DET / "detection_metrics.json"
    json_path.write_text(json.dumps(det_output, indent=2))
    print(f"  Saved: {json_path}")

    # CSV summary
    csv_rows = []
    for method_key, m in methods.items():
        met = m["metrics"]
        csv_rows.append({
            "method_key":   method_key,
            "method_label": m["label"],
            "TP":           met["TP"],
            "FP":           met["FP"],
            "FN":           met["FN"],
            "TN":           met["TN"],
            "precision":    met["precision"],
            "recall":       met["recall"],
            "f1":           met["f1"],
            "flagged_cells": "|".join(m["flagged_cells"]),
        })

    csv_path = OUT_DET / "detection_metrics.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"  Saved: {csv_path}")

    # Correlation
    corr_path = OUT_CORR / "correlation_metrics.json"
    corr_path.write_text(json.dumps(corr_metrics, indent=2, default=str))
    print(f"  Saved: {corr_path}")

    # ── Print summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DETECTION RESULTS (ACTUAL)")
    print("Evaluation: scenario-level / cell-level | N=3 injected faults")
    print("=" * 60)
    print(f"{'Method':<45} {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3} {'Prec':>6} {'Recall':>7} {'F1':>6}")
    print("-" * 80)
    for method_key, m in methods.items():
        met = m["metrics"]
        print(
            f"{m['label']:<45} {met['TP']:>3} {met['FP']:>3} {met['FN']:>3} {met['TN']:>3} "
            f"{met['precision']:>6.3f} {met['recall']:>7.3f} {met['f1']:>6.3f}"
        )

    print("\n" + "=" * 60)
    print("CORRELATION METRICS")
    print("=" * 60)
    if corr_metrics:
        print(f"  Metric: {corr_metrics['metric_name']}")
        print(f"  Total events: {corr_metrics['total_events']}")
        print(f"  Clustered (cross-source): {corr_metrics['clustered_events']}")
        print(f"  Assignment rate: {corr_metrics['assignment_rate_pct']:.2f}%")
        print(f"  NOTE: {corr_metrics['note'][:120]}...")


if __name__ == "__main__":
    main()
