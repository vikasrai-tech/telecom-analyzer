"""
N-HiTS rolling-origin benchmark.

For each origin, all series are split at that cutoff, NeuralForecast
trains on the left window (all 220 series in one batch), and predictions
are scored against the right window. 4 origins are used (vs 8 for
Moirai) because each origin requires a full training pass.

Loads existing results, adds N-HiTS row, rewrites summary files.

Usage:
    cd /mnt/e/telecom-analyzer
    python scripts/run_nhits_benchmark.py
"""

import csv
import json
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("nhits_bench")

DATA_KPI = ROOT / "data" / "raw" / "kpi_10hr_sample.csv"
OUT_DIR = ROOT / "results" / "forecast"
HORIZON_H = 4
N_ORIGINS = 4       # fewer than Moirai because each origin = full train pass
MAX_STEPS = 100     # steps per origin (lower than live predictor for speed)
MIN_TRAIN_ROWS = 48 # minimum training rows for N-HiTS
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)


def freq_str(freq_s: float) -> str:
    secs = int(round(freq_s))
    if secs % 3600 == 0:
        return f"{secs // 3600}h"
    if secs % 60 == 0:
        return f"{secs // 60}min"
    return f"{secs}s"


def main():
    print("=" * 62)
    print("N-HiTS BENCHMARK — Nixtla neuralforecast")
    print(f"Dataset : {DATA_KPI.name}")
    print(f"Horizon : {HORIZON_H}h | Origins: {N_ORIGINS} | Steps/origin: {MAX_STEPS}")
    print("=" * 62)

    try:
        from neuralforecast import NeuralForecast
        from neuralforecast.models import NHITS
    except ImportError:
        print("ERROR: neuralforecast not installed. Run: pip install neuralforecast")
        return

    print("\n[1/5] Parsing KPI dataset ...")
    from src.parsers.kpi_parser import parse_kpi_file
    parsed = parse_kpi_file(str(DATA_KPI))
    print(f"      Rows: {parsed['rows']}, Cells: {len(parsed['cells'])}, "
          f"KPI cols: {len(parsed['kpi_columns'])}")

    ts_col = parsed.get("timestamp_col", "")
    cell_col = parsed.get("cell_col", "")
    cols = parsed.get("kpi_columns", [])

    df_all = pd.DataFrame(parsed["df_records"])
    df_all[ts_col] = pd.to_datetime(df_all[ts_col], errors="coerce")
    df_all = df_all.dropna(subset=[ts_col])

    # Infer per-cell frequency
    diffs = []
    for _, grp in df_all.groupby(cell_col) if cell_col else [("ALL", df_all)]:
        d = grp[ts_col].sort_values().diff().dropna()
        if len(d):
            diffs.append(d.median().total_seconds())
    freq_s = float(np.median(diffs)) if diffs else 300.0
    horizon_periods = max(1, round(HORIZON_H * 3600 / freq_s))
    fstr = freq_str(freq_s)
    # Context window: 2× horizon, capped at available data
    input_size = min(2 * horizon_periods, 256)

    print(f"      freq={fstr}, horizon_periods={horizon_periods}, input_size={input_size}")

    # Build per-series map
    series_map = {}   # uid → sorted DataFrame
    groups = df_all.groupby(cell_col) if cell_col else [("ALL", df_all)]
    for cell, grp in groups:
        grp_sorted = grp.sort_values(ts_col)
        for col in cols:
            sub = grp_sorted[[ts_col, col]].dropna(subset=[col]).reset_index(drop=True)
            if len(sub) < MIN_TRAIN_ROWS + horizon_periods:
                continue
            uid = f"{cell}\x00{col}"   # \x00 never appears in CSV headers/cell names
            series_map[uid] = (cell, col, sub)

    n_series = len(series_map)
    print(f"\n[2/5] {n_series} series × {N_ORIGINS} origins = {n_series * N_ORIGINS} eval points")

    # Place origins: spread across [MIN_TRAIN_ROWS, n-horizon)
    # Use the shortest series length to set safe origin indices
    min_len = min(len(s) for _, _, s in series_map.values())
    usable = min_len - horizon_periods - MIN_TRAIN_ROWS
    if usable < 1:
        print(f"ERROR: Series too short (min_len={min_len}) for horizon={horizon_periods}")
        return

    step = max(1, usable // max(1, N_ORIGINS - 1))
    origins = [MIN_TRAIN_ROWS + i * step for i in range(N_ORIGINS)]
    origins = [min(o, min_len - horizon_periods - 1) for o in origins]
    print(f"      Origin cutoffs (row indices): {origins}")

    raw_results = []
    import time as _time

    for o_idx, cutoff in enumerate(origins):
        print(f"\n[3/5] Origin {o_idx + 1}/{N_ORIGINS} (cutoff row={cutoff}) ...", flush=True)
        _t0 = _time.time()

        # Build training DataFrame for this origin
        nf_parts = []
        test_actuals = {}   # uid → actual values array
        for uid, (cell, col, sub) in series_map.items():
            n = len(sub)
            if cutoff < MIN_TRAIN_ROWS or cutoff + horizon_periods > n:
                continue
            train_sub = sub.iloc[:cutoff].copy()
            part = train_sub.rename(columns={ts_col: "ds", col: "y"})
            part["unique_id"] = uid
            nf_parts.append(part[["unique_id", "ds", "y"]])
            test_actuals[uid] = sub[col].values[cutoff:cutoff + horizon_periods].astype(float)

        if not nf_parts:
            print(f"      Skipped — no eligible series")
            continue

        nf_df = pd.concat(nf_parts, ignore_index=True)

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                nf = NeuralForecast(
                    models=[NHITS(
                        h=horizon_periods,
                        input_size=input_size,
                        max_steps=MAX_STEPS,
                        enable_progress_bar=False,
                        enable_model_summary=False,
                        random_seed=RANDOM_SEED,
                        start_padding_enabled=True,
                    )],
                    freq=fstr,
                )
                nf.fit(nf_df)
                pred_df = nf.predict().reset_index()
        except Exception as e:
            print(f"      Training failed: {e}")
            continue

        elapsed = _time.time() - _t0
        pred_col = next((c for c in pred_df.columns if "NHITS" in c.upper()), None)
        if pred_col is None:
            print(f"      No NHITS column in predictions: {list(pred_df.columns)}")
            continue

        # Compute per-series metrics
        origin_success = 0
        for uid, actual in test_actuals.items():
            uid_preds = pred_df[pred_df["unique_id"] == uid][pred_col].values if "unique_id" in pred_df.columns \
                else pred_df[pred_df.index == uid][pred_col].values
            if len(uid_preds) == 0:
                continue
            n_pts = min(len(actual), len(uid_preds))
            act = actual[:n_pts]
            prd = uid_preds[:n_pts]
            valid = ~(np.isnan(act) | np.isnan(prd))
            act, prd = act[valid], prd[valid]
            if len(act) == 0:
                continue
            err = prd - act
            mae = float(np.mean(np.abs(err)))
            rmse = float(np.sqrt(np.mean(err ** 2)))
            nonzero = act != 0
            mape = float(np.mean(np.abs(err[nonzero] / act[nonzero])) * 100) if nonzero.any() else None
            parts = uid.split("\x00", 1)
            raw_results.append({
                "method": "nhits",
                "cell_id": parts[0] if len(parts) == 2 else uid,
                "column": parts[1] if len(parts) == 2 else "",
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
                "mape": round(mape, 2) if mape is not None else None,
                "n_origins": 1,
            })
            origin_success += 1

        print(f"      done in {elapsed:.1f}s — {origin_success}/{len(test_actuals)} series scored")

    print(f"\n      Total: {len(raw_results)} successful evaluations")

    if not raw_results:
        print("ERROR: No results — check model/data configuration")
        return

    # Aggregate
    mae_vals = [r["mae"] for r in raw_results]
    rmse_vals = [r["rmse"] for r in raw_results]
    mape_vals = [r["mape"] for r in raw_results if r["mape"] is not None]
    nhits_row = {
        "method": "nhits",
        "n_series": len(raw_results),
        "n_mape": len(mape_vals),
        "avg_mae": round(float(np.mean(mae_vals)), 4),
        "avg_rmse": round(float(np.mean(rmse_vals)), 4),
        "avg_mape": round(float(np.mean(mape_vals)), 2) if mape_vals else None,
        "lead_time_detected": 0,
        "lead_time_total": 0,
        "total_false_alarms": 0,
    }

    print("\n[4/5] Lead-time evaluation ... (skipped for N-HiTS — per-origin training model)")

    # Merge with existing results
    print("\n[5/5] Merging with existing results and saving ...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    existing_json = OUT_DIR / "forecast_benchmark.json"
    existing = json.loads(existing_json.read_text()) if existing_json.exists() else {}

    new_accuracy = [r for r in existing.get("forecast_accuracy", [])
                    if r.get("method") != "nhits"] + raw_results
    new_lt = [r for r in existing.get("lead_time", []) if r.get("method") != "nhits"]
    new_summary = [r for r in existing.get("summary_table", [])
                   if r.get("method") != "nhits"] + [nhits_row]

    merged = {**existing, "forecast_accuracy": new_accuracy,
              "lead_time": new_lt, "summary_table": new_summary}
    if "config" in merged:
        merged["config"]["methods"] = [r["method"] for r in new_summary]

    existing_json.write_text(json.dumps(merged, indent=2))

    csv_path = OUT_DIR / "forecast_summary.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=new_summary[0].keys())
        writer.writeheader()
        writer.writerows(new_summary)

    origin_csv = OUT_DIR / "origin_results.csv"
    existing_origins = []
    if origin_csv.exists():
        try:
            existing_origins = [r for r in csv.DictReader(open(origin_csv))
                                if r.get("method") != "nhits"]
        except Exception:
            pass
    with open(origin_csv, "w", newline="") as f:
        fieldnames = ["method", "cell_id", "column", "mae", "rmse", "mape", "n_origins"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_origins)
        writer.writerows(raw_results)

    print("\n" + "=" * 72)
    print("FINAL METHOD COMPARISON — Rolling-Origin Backtest")
    print(f"Dataset: {parsed['source']}  |  Horizon: {HORIZON_H}h")
    print("=" * 72)
    print(f"{'Method':<15} {'MAE':>9} {'RMSE':>9} {'MAPE':>9} {'Series':>8} {'Origins':>8}")
    print("-" * 63)
    for row in new_summary:
        mape_s = f"{row['avg_mape']:.2f}%" if row.get("avg_mape") is not None else "    N/A"
        origins_s = str(row.get("n_origins", "—"))
        print(f"{row['method']:<15} {row['avg_mae']:>9.4f} {row['avg_rmse']:>9.4f} "
              f"{mape_s:>9} {row['n_series']:>8} {origins_s:>8}")
    print("=" * 72)
    print(f"\nN-HiTS: MAE={nhits_row['avg_mae']}, RMSE={nhits_row['avg_rmse']}, "
          f"MAPE={nhits_row.get('avg_mape')}%")
    print(f"Note: N-HiTS uses {N_ORIGINS} origins (vs 8 for others) — each origin requires a full training pass")
    print("\nFiles saved:")
    print(f"  {existing_json}\n  {csv_path}\n  {origin_csv}")


if __name__ == "__main__":
    main()
