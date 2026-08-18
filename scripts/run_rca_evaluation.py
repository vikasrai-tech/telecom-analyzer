"""
RCA evaluation — rule-based root-cause analysis for the 3 injected fault cells.

No Ollama required — uses rule_based_root_cause() directly.

Usage:
    cd /mnt/e/telecom-analyzer
    python scripts/run_rca_evaluation.py

Results saved to:
    results/rca/rca_metrics.json
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATA_KPI   = ROOT / "data" / "raw" / "kpi_64ue_6hr.csv"
DATA_STATS = ROOT / "data" / "raw" / "stats_64ue_6hr.csv"
OUT_DIR    = ROOT / "results" / "rca"


def main():
    print("=" * 60)
    print("RCA EVALUATION — Rule-based (no Ollama)")
    print(f"Fault cells: PCI_3 (congestion), PCI_12 (outage), PCI_8 (drift)")
    print("=" * 60)

    # ── Parse datasets ───────────────────────────────────────────────────
    print("\n[1/4] Parsing datasets ...")
    from src.parsers.kpi_parser import parse_kpi_file
    from src.parsers.stats_parser import parse_stats_file

    kpi_parsed   = parse_kpi_file(str(DATA_KPI))
    stats_parsed = parse_stats_file(str(DATA_STATS))
    print(f"  KPI: {kpi_parsed['rows']} rows, Stats: {stats_parsed['rows']} rows")

    # ── Run detectors ─────────────────────────────────────────────────────
    print("\n[2/4] Running detectors and building EventRouter ...")
    from src.detection.kpi_detector import detect_kpi_anomalies
    from src.detection.stats_detector import detect_stats_anomalies
    from src.orchestrator.event_router import EventRouter

    kpi_anoms   = detect_kpi_anomalies(kpi_parsed)
    stats_anoms = detect_stats_anomalies(stats_parsed)

    router = EventRouter()
    router.ingest(kpi_anoms,   source="kpi")
    router.ingest(stats_anoms, source="stats")

    summary = router.summary()
    print(f"  Total events: {summary['total']}, Correlated: {summary['correlated']}")

    # ── Run RCA evaluation ────────────────────────────────────────────────
    print("\n[3/4] Running RCA for each fault cell ...")
    from src.evaluation.rca_evaluator import evaluate_rca

    rca_results = evaluate_rca(kpi_anoms, stats_anoms, router)

    # ── Save results ──────────────────────────────────────────────────────
    print("\n[4/4] Saving results ...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    n_success = sum(1 for r in rca_results if r.get("success"))

    output = {
        "dataset": {
            "kpi_file":   str(DATA_KPI.name),
            "stats_file": str(DATA_STATS.name),
            "kpi_rows":   kpi_parsed["rows"],
            "stats_rows": stats_parsed["rows"],
        },
        "rca_method":    "rule_based_root_cause() — deterministic, no LLM",
        "random_seed":   RANDOM_SEED,
        "n_fault_cells": 3,
        "n_success":     n_success,
        "success_rate":  round(n_success / 3, 4),
        "results":       rca_results,
        "evaluation_note": (
            "Keyword match evaluates whether rule_based_root_cause() output contains "
            "expected diagnostic terms for each fault type. This tests whether the "
            "rule-based engine correctly identifies the causal layer and fault type, "
            "not whether it precisely mirrors any specific human-written diagnosis."
        ),
    }

    json_path = OUT_DIR / "rca_metrics.json"
    json_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"  Saved: {json_path}")

    # ── Print summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RCA RESULTS (ACTUAL)")
    print("=" * 60)
    print(f"{'Cell':<8} {'Fault':<12} {'Events':>7} {'Keywords':>12} {'Hit Rate':>10} {'Pass':>5}")
    print("-" * 60)
    for r in rca_results:
        km = r.get("keyword_match", {})
        print(
            f"{r.get('cell_id','?'):<8} "
            f"{r.get('fault_type','?'):<12} "
            f"{r.get('event_group_size',0):>7} "
            f"{','.join(km.get('matched_keywords',[])[:3])[:12]:>12} "
            f"{km.get('keyword_hit_rate',0):>10.2f} "
            f"{'YES' if r.get('success') else 'NO':>5}"
        )
    print(f"\nOverall success: {n_success}/3 fault cells")

    # Manifest
    manifest_path = ROOT / "results" / "experiment_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass
    manifest["rca"] = {
        "script":       "run_rca_evaluation.py",
        "random_seed":  RANDOM_SEED,
        "n_fault_cells": 3,
        "n_success":    n_success,
        "results_file": str(json_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
