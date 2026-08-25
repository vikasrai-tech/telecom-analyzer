"""
Moirai-only rolling-origin backtest.

Loads existing results, adds Moirai row, rewrites summary files.
Moirai is called per-series (context_length varies per series so true
batching requires padding — we process each series independently which
is simpler and avoids padding artefacts on short series).

Usage:
    cd /mnt/e/telecom-analyzer
    python scripts/run_moirai_benchmark.py
"""

import csv
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.detection.predictor import _moirai_point_forecast  # noqa: E402

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("moirai_bench")

DATA_KPI = ROOT / "data" / "raw" / "kpi_10hr_sample.csv"
OUT_DIR = ROOT / "results" / "forecast"
HORIZON_H = 4
N_ORIGINS = 8
MIN_TRAIN_ROWS = 24
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)


# ── load moirai model (via shared singleton in predictor) ─────────────────

def load_moirai():
    from src.detection.predictor import _get_moirai
    print("[1/5] Loading Salesforce/moirai-1.1-R-small ...")
    module = _get_moirai()
    if module is None:
        raise RuntimeError("Failed to load Moirai — check uni2ts installation")
    print("      Model loaded.")
    return module


# ── rolling-origin backtest ──────────────────────────────────────────────

def rolling_origin_backtest(parsed, module):  # noqa: ARG001 — module kept for API compat; prediction uses shared singleton
    ts_col = parsed.get("timestamp_col", "")
    cell_col = parsed.get("cell_col", "")
    cols = parsed.get("kpi_columns", [])

    df = pd.DataFrame(parsed["df_records"])
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col])

    freq_s = None
    if ts_col in df.columns:
        diffs = df[ts_col].sort_values().diff().dropna()
        if len(diffs):
            freq_s = diffs.median().total_seconds()
    if not freq_s or freq_s <= 0:
        freq_s = 300.0
    horizon_periods = max(1, round(HORIZON_H * 3600 / freq_s))

    # Build all (cell, col) series
    series_map = {}
    cells = df[cell_col].unique() if cell_col and cell_col in df.columns else [None]
    for cell in cells:
        sub = df[df[cell_col] == cell] if cell is not None else df
        for col in cols:
            if col not in sub.columns:
                continue
            s = sub[[ts_col, col]].dropna(subset=[col]).sort_values(ts_col).reset_index(drop=True)
            if len(s) < MIN_TRAIN_ROWS + horizon_periods:
                continue
            series_map[(str(cell), col)] = s

    total_evals = len(series_map) * N_ORIGINS
    print(f"[2/5] {len(series_map)} series × {N_ORIGINS} origins = {total_evals} eval points")
    print(f"      horizon_periods={horizon_periods}")

    results = []
    completed = 0

    for o_idx in range(N_ORIGINS):
        import time as _time
        _t0 = _time.time()
        print(f"\n[3/5] Origin {o_idx + 1}/{N_ORIGINS} ...", flush=True)

        origin_success = 0
        for (cell, col), s in series_map.items():
            n = len(s)
            step = max(1, (n - MIN_TRAIN_ROWS - horizon_periods) // max(1, N_ORIGINS - 1))
            origin_idx = min(MIN_TRAIN_ROWS + o_idx * step, n - horizon_periods - 1)
            if origin_idx < MIN_TRAIN_ROWS:
                continue

            train_vals = s[col].values[:origin_idx].astype(float)
            actual_vals = s[col].values[origin_idx:origin_idx + horizon_periods].astype(float)

            if np.any(np.isnan(train_vals)) or len(actual_vals) < 1:
                continue

            fc = _moirai_point_forecast(train_vals, horizon_periods)
            if fc is None:
                continue

            n_actual = min(len(actual_vals), len(fc))
            if n_actual < 1:
                continue

            actual = actual_vals[:n_actual]
            pred = fc[:n_actual]
            mae = float(np.mean(np.abs(actual - pred)))
            rmse = float(np.sqrt(np.mean((actual - pred) ** 2)))
            nonzero = actual[actual != 0]
            mape = (
                float(np.mean(np.abs((actual[actual != 0] - pred[actual != 0]) / nonzero)) * 100)
                if len(nonzero) > 0 else None
            )

            results.append({
                "method": "moirai",
                "cell_id": cell,
                "column": col,
                "mae": mae,
                "rmse": rmse,
                "mape": mape,
                "n_origins": 1,
            })
            origin_success += 1
            completed += 1

        elapsed = _time.time() - _t0
        print(f"      done in {elapsed:.1f}s, {origin_success} series evaluated "
              f"({completed}/{total_evals} total)", flush=True)

    return results


# ── lead-time evaluation ─────────────────────────────────────────────────

def run_lead_time(parsed):
    from src.detection.forecast_eval import evaluate_anomaly_lead_time, KPI_10HR_GROUND_TRUTH
    try:
        lt = evaluate_anomaly_lead_time(parsed, KPI_10HR_GROUND_TRUTH, methods=("moirai",), horizon_h=HORIZON_H)
        return [{"method": r.method, "detected": r.detected, "false_alarms": r.false_alarms} for r in lt]
    except Exception as e:
        print(f"  Lead-time eval failed: {e}")
        return []


# ── aggregate metrics ────────────────────────────────────────────────────

def aggregate(results):
    if not results:
        return None
    mae_vals = [r["mae"] for r in results]
    rmse_vals = [r["rmse"] for r in results]
    mape_vals = [r["mape"] for r in results if r["mape"] is not None]
    return {
        "method": "moirai",
        "n_series": len(results),
        "n_mape": len(mape_vals),
        "avg_mae": round(float(np.mean(mae_vals)), 4),
        "avg_rmse": round(float(np.mean(rmse_vals)), 4),
        "avg_mape": round(float(np.mean(mape_vals)), 2) if mape_vals else None,
    }


# ── main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("MOIRAI BENCHMARK — Salesforce/moirai-1.1-R-small")
    print(f"Dataset : {DATA_KPI.name}")
    print(f"Horizon : {HORIZON_H}h | Origins: {N_ORIGINS} | Samples: {NUM_SAMPLES}")
    print("=" * 62)

    module = load_moirai()

    from src.parsers.kpi_parser import parse_kpi_file
    parsed = parse_kpi_file(str(DATA_KPI))
    print(f"      Rows: {parsed['rows']}, Cells: {len(parsed['cells'])}, "
          f"KPI cols: {len(parsed['kpi_columns'])}")

    raw_results = rolling_origin_backtest(parsed, module)
    print(f"\n      {len(raw_results)} successful evaluations")

    print("\n[4/5] Lead-time evaluation ...")
    lt_results = run_lead_time(parsed)
    lead_detected = sum(1 for r in lt_results if r["detected"])
    lead_total = len(lt_results)
    false_alarms = sum(r.get("false_alarms", 0) for r in lt_results)

    moirai_row = aggregate(raw_results)
    if moirai_row is None:
        print("ERROR: No Moirai results — check model loading")
        return

    moirai_row["lead_time_detected"] = lead_detected
    moirai_row["lead_time_total"] = lead_total
    moirai_row["total_false_alarms"] = false_alarms

    # ── Merge with existing results ───────────────────────────────────────
    print("\n[5/5] Merging with existing results and saving ...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    existing_json_path = OUT_DIR / "forecast_benchmark.json"
    existing = {}
    if existing_json_path.exists():
        existing = json.loads(existing_json_path.read_text())

    existing_accuracy = [r for r in existing.get("forecast_accuracy", [])
                         if r.get("method") != "moirai"]
    new_accuracy = existing_accuracy + raw_results

    existing_lt = [r for r in existing.get("lead_time", [])
                   if r.get("method") != "moirai"]
    new_lt_dicts = [{
        "method": r["method"],
        "injected_event": "",
        "cell_id": "",
        "column": "",
        "detected": r["detected"],
        "lead_time_h": None,
        "false_alarms": r.get("false_alarms", 0),
    } for r in lt_results]
    new_lt = existing_lt + new_lt_dicts

    existing_summary = [r for r in existing.get("summary_table", [])
                        if r.get("method") != "moirai"]
    new_summary = existing_summary + [moirai_row]

    merged = {
        **existing,
        "forecast_accuracy": new_accuracy,
        "lead_time": new_lt,
        "summary_table": new_summary,
    }
    if "config" in merged:
        merged["config"]["methods"] = [r["method"] for r in new_summary]

    existing_json_path.write_text(json.dumps(merged, indent=2))

    csv_path = OUT_DIR / "forecast_summary.csv"
    if new_summary:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=new_summary[0].keys())
            writer.writeheader()
            writer.writerows(new_summary)

    origin_csv = OUT_DIR / "origin_results.csv"
    existing_origins = []
    if origin_csv.exists():
        try:
            existing_origins = [r for r in csv.DictReader(open(origin_csv))
                                if r.get("method") != "moirai"]
        except Exception:
            pass
    with open(origin_csv, "w", newline="") as f:
        fieldnames = ["method", "cell_id", "column", "mae", "rmse", "mape", "n_origins"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_origins)
        writer.writerows(raw_results)

    # ── Print final comparison table ──────────────────────────────────────
    print("\n" + "=" * 72)
    print("FINAL METHOD COMPARISON — Rolling-Origin Backtest")
    print(f"Dataset: {parsed['source']}  |  Horizon: {HORIZON_H}h  |  Origins: {N_ORIGINS}")
    print("=" * 72)
    print(f"{'Method':<15} {'MAE':>9} {'RMSE':>9} {'MAPE':>9} {'Series':>8} {'Lead Det/Tot':>13}")
    print("-" * 72)
    for row in new_summary:
        mape_s = f"{row['avg_mape']:.2f}%" if row.get("avg_mape") is not None else "    N/A"
        print(
            f"{row['method']:<15} "
            f"{row['avg_mae']:>9.4f} "
            f"{row['avg_rmse']:>9.4f} "
            f"{mape_s:>9} "
            f"{row['n_series']:>8} "
            f"  {row.get('lead_time_detected', 0)}/{row.get('lead_time_total', 0)}"
        )
    print("=" * 72)
    print(f"\nMoirai row: MAE={moirai_row['avg_mae']}, "
          f"RMSE={moirai_row['avg_rmse']}, "
          f"MAPE={moirai_row.get('avg_mape')}%, "
          f"Series={moirai_row['n_series']}")
    print("\nFiles saved:")
    print(f"  {existing_json_path}")
    print(f"  {csv_path}")
    print(f"  {origin_csv}")


if __name__ == "__main__":
    main()
