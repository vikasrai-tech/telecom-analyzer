"""
Forecast benchmark — rolling-origin backtest (MAE/RMSE/MAPE) and anomaly
lead-time evaluation on data/raw/kpi_10hr_sample.csv.

Usage:
    cd /mnt/e/telecom-analyzer
    python scripts/run_forecast_benchmark.py

Results saved to:
    results/forecast/forecast_benchmark.json
    results/forecast/forecast_summary.csv
    results/forecast/origin_results.csv
    results/forecast/plots/  (matplotlib plots)
"""

import csv
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

DATA_KPI = ROOT / "data" / "raw" / "kpi_10hr_sample.csv"
OUT_DIR  = ROOT / "results" / "forecast"
PLOT_DIR = OUT_DIR / "plots"

METHODS    = ("prophet", "holt_winters", "lstm")
HORIZON_H  = 4
N_ORIGINS  = 8


def plot_method_comparison(summary_table, out_dir: Path):
    """Generate a bar chart comparing MAE/RMSE across methods."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        methods = [r["method"] for r in summary_table]
        mae_vals  = [r["avg_mae"] or 0 for r in summary_table]
        rmse_vals = [r["avg_rmse"] or 0 for r in summary_table]

        x = range(len(methods))
        width = 0.35

        fig, ax = plt.subplots(figsize=(9, 5))
        bars1 = ax.bar([i - width/2 for i in x], mae_vals,  width, label="MAE",  color="#2196F3")
        bars2 = ax.bar([i + width/2 for i in x], rmse_vals, width, label="RMSE", color="#F44336")

        ax.set_xticks(list(x))
        ax.set_xticklabels(methods)
        ax.set_ylabel("Error (KPI units)")
        ax.set_title("Forecast Accuracy — Rolling-Origin Backtest (avg across all cells/columns)")
        ax.legend()
        ax.bar_label(bars1, fmt="%.3f", padding=3)
        ax.bar_label(bars2, fmt="%.3f", padding=3)
        plt.tight_layout()

        path = out_dir / "method_comparison_mae_rmse.png"
        plt.savefig(path, dpi=150)
        plt.close()
        print(f"  Saved plot: {path}")
    except Exception as e:
        print(f"  Plot failed (non-critical): {e}")


def plot_lead_time(lead_time_results, out_dir: Path):
    """Generate a detection rate bar chart for lead-time evaluation."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from collections import defaultdict
        method_stats = defaultdict(lambda: {"detected": 0, "total": 0, "false_alarms": 0})
        for lt in lead_time_results:
            m = lt["method"]
            method_stats[m]["total"] += 1
            if lt["detected"]:
                method_stats[m]["detected"] += 1
            method_stats[m]["false_alarms"] += lt.get("false_alarms", 0)

        methods = sorted(method_stats.keys())
        det_rates = [
            method_stats[m]["detected"] / method_stats[m]["total"] * 100
            if method_stats[m]["total"] > 0 else 0
            for m in methods
        ]

        fig, ax = plt.subplots(figsize=(8, 4))
        bars = ax.bar(methods, det_rates, color=["#4CAF50", "#2196F3", "#FF9800"])
        ax.set_ylabel("Detection Rate (%)")
        ax.set_title("Anomaly Lead-Time Detection Rate\n(dataset limitation: abrupt step-changes, no precursor signals)")
        ax.set_ylim(0, 110)
        ax.bar_label(bars, fmt="%.1f%%", padding=3)
        plt.tight_layout()

        path = out_dir / "lead_time_detection_rate.png"
        plt.savefig(path, dpi=150)
        plt.close()
        print(f"  Saved plot: {path}")
    except Exception as e:
        print(f"  Plot failed (non-critical): {e}")


def main():
    print("=" * 60)
    print("FORECAST BENCHMARK — kpi_10hr_sample.csv")
    print(f"Random seed: {RANDOM_SEED}")
    print(f"Methods: {METHODS}")
    print(f"Horizon: {HORIZON_H}h, Origins: {N_ORIGINS}")
    print("=" * 60)

    # ── Parse dataset ─────────────────────────────────────────────────────
    print("\n[1/4] Parsing KPI 10hr dataset ...")
    from src.parsers.kpi_parser import parse_kpi_file
    parsed = parse_kpi_file(str(DATA_KPI))
    print(f"  Rows: {parsed['rows']}, Cells: {len(parsed['cells'])}, "
          f"KPI cols: {len(parsed['kpi_columns'])}")

    # ── Run forecast evaluation ───────────────────────────────────────────
    print("\n[2/4] Running forecast evaluation ...")
    from src.evaluation.forecast_evaluator import run_forecast_evaluation
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    results = run_forecast_evaluation(
        parsed,
        methods=METHODS,
        horizon_h=HORIZON_H,
        n_origins=N_ORIGINS,
        out_dir=OUT_DIR,
    )

    # ── Plots ────────────────────────────────────────────────────────────
    print("\n[3/4] Generating plots ...")
    plot_method_comparison(results.get("summary_table", []), PLOT_DIR)
    plot_lead_time(results.get("lead_time", []), PLOT_DIR)

    # ── Print summary ─────────────────────────────────────────────────────
    print("\n[4/4] Summary")
    print("=" * 60)
    print("FORECAST RESULTS (ACTUAL)")
    print(f"Dataset: {parsed['source']}")
    print("=" * 60)
    print(f"{'Method':<15} {'MAE':>8} {'RMSE':>8} {'MAPE':>8} {'Series':>7} {'Lead Det/Total':>15}")
    print("-" * 65)
    for row in results.get("summary_table", []):
        mape_str = f"{row.get('avg_mape'):.2f}%" if row.get("avg_mape") is not None else "  N/A"
        print(
            f"{row['method']:<15} "
            f"{str(row.get('avg_mae','N/A')):>8} "
            f"{str(row.get('avg_rmse','N/A')):>8} "
            f"{mape_str:>8} "
            f"{row.get('n_series',0):>7} "
            f"{row.get('lead_time_detected',0)}/{row.get('lead_time_total',0):>13}"
        )

    print("\nLEAD TIME NOTE: kpi_10hr_sample.csv contains abrupt step-change anomalies")
    print("with no observable precursor signal — no history-based forecaster can predict")
    print("them ahead of time. Low detection rate here is expected and documented.")
    print("\nFiles saved in results/forecast/")

    # Experiment manifest entry
    manifest_entry = {
        "script": "run_forecast_benchmark.py",
        "dataset": str(DATA_KPI.name),
        "random_seed": RANDOM_SEED,
        "methods": list(METHODS),
        "horizon_h": HORIZON_H,
        "n_origins": N_ORIGINS,
        "results_file": str(OUT_DIR / "forecast_benchmark.json"),
    }
    manifest_path = ROOT / "results" / "experiment_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass
    manifest["forecast"] = manifest_entry
    manifest_path.write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
