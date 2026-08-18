"""
Forecast evaluator — wraps forecast_eval.py rolling-origin backtest and
anomaly lead-time evaluation, saves results to files.
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_METHODS = ("prophet", "holt_winters", "lstm")
DEFAULT_HORIZON_H = 4
DEFAULT_N_ORIGINS = 8


def run_forecast_evaluation(
    parsed: Dict[str, Any],
    methods: Tuple[str, ...] = DEFAULT_METHODS,
    horizon_h: int = DEFAULT_HORIZON_H,
    n_origins: int = DEFAULT_N_ORIGINS,
    ground_truth_events: Optional[List[Dict[str, Any]]] = None,
    out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Run rolling-origin backtest and anomaly lead-time evaluation.

    Parameters
    ----------
    parsed : dict
        Output of parse_kpi_file() or parse_stats_file().
    methods : tuple
        Forecasting methods to evaluate ("prophet", "holt_winters", "lstm").
    horizon_h : int
        Forecast horizon in hours.
    n_origins : int
        Number of rolling origins.
    ground_truth_events : list, optional
        List of ground-truth event dicts with keys: cell_id, column,
        start_h, end_h, kind. Defaults to KPI_10HR_GROUND_TRUTH from
        forecast_eval.py if not provided.
    out_dir : Path, optional
        Directory to save JSON + CSV results. If None, no files are written.

    Returns
    -------
    dict with keys:
      forecast_accuracy  — list of ForecastMetrics dicts
      lead_time          — list of LeadTimeMetrics dicts
      summary_table      — per-method aggregated stats
      method_summary     — dict {method: {mae, rmse, mape}} for quick access
    """
    from src.detection.forecast_eval import (
        rolling_origin_backtest,
        evaluate_anomaly_lead_time,
        KPI_10HR_GROUND_TRUTH,
    )

    gt_events = ground_truth_events if ground_truth_events is not None else KPI_10HR_GROUND_TRUTH

    logger.info(f"Running rolling-origin backtest: methods={methods}, horizon_h={horizon_h}, n_origins={n_origins}")

    # Rolling-origin backtest
    accuracy_results = []
    for method in methods:
        try:
            results = rolling_origin_backtest(
                parsed, methods=(method,), horizon_h=horizon_h, n_origins=n_origins
            )
            accuracy_results.extend(results)
            logger.info(f"  {method}: {len(results)} series evaluated")
        except Exception as e:
            logger.warning(f"  {method} backtest failed: {e}")

    # Lead-time evaluation
    lead_time_results = []
    for method in methods:
        try:
            lt = evaluate_anomaly_lead_time(
                parsed, gt_events, methods=(method,), horizon_h=horizon_h
            )
            lead_time_results.extend(lt)
            logger.info(f"  {method} lead-time: {len(lt)} events evaluated")
        except Exception as e:
            logger.warning(f"  {method} lead-time evaluation failed: {e}")

    # Aggregate per-method summary
    method_agg: Dict[str, Dict] = {}
    for m in accuracy_results:
        d = method_agg.setdefault(m.method, {
            "mae_sum": 0.0, "rmse_sum": 0.0,
            "mape_sum": 0.0, "mape_n": 0, "n": 0
        })
        d["mae_sum"]  += m.mae
        d["rmse_sum"] += m.rmse
        d["n"]        += 1
        if m.mape is not None:
            d["mape_sum"] += m.mape
            d["mape_n"]   += 1

    summary_table = []
    method_summary: Dict[str, Dict] = {}
    for method, agg in method_agg.items():
        n = agg["n"]
        mae  = round(agg["mae_sum"] / n, 4) if n else None
        rmse = round(agg["rmse_sum"] / n, 4) if n else None
        mape = round(agg["mape_sum"] / agg["mape_n"], 2) if agg["mape_n"] else None

        lead_detected = sum(1 for lt in lead_time_results if lt.method == method and lt.detected)
        lead_total    = sum(1 for lt in lead_time_results if lt.method == method)
        false_alarms  = sum(lt.false_alarms for lt in lead_time_results if lt.method == method)

        row = {
            "method":              method,
            "n_series":            n,
            "avg_mae":             mae,
            "avg_rmse":            rmse,
            "avg_mape":            mape,
            "lead_time_detected":  lead_detected,
            "lead_time_total":     lead_total,
            "total_false_alarms":  false_alarms,
        }
        summary_table.append(row)
        method_summary[method] = {"mae": mae, "rmse": rmse, "mape": mape}

    result = {
        "forecast_accuracy": [asdict(m) for m in accuracy_results],
        "lead_time":         [asdict(m) for m in lead_time_results],
        "summary_table":     summary_table,
        "method_summary":    method_summary,
        "config": {
            "methods":    list(methods),
            "horizon_h":  horizon_h,
            "n_origins":  n_origins,
            "dataset":    parsed.get("source", "unknown"),
        },
    }

    # Save to files
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Full JSON
        json_path = out_dir / "forecast_benchmark.json"
        json_path.write_text(json.dumps(result, indent=2))
        logger.info(f"Saved: {json_path}")

        # Summary CSV
        import csv
        csv_path = out_dir / "forecast_summary.csv"
        if summary_table:
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=summary_table[0].keys())
                writer.writeheader()
                writer.writerows(summary_table)
            logger.info(f"Saved: {csv_path}")

        # Per-origin accuracy CSV
        if accuracy_results:
            origin_csv = out_dir / "origin_results.csv"
            rows = [asdict(m) for m in accuracy_results]
            with open(origin_csv, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            logger.info(f"Saved: {origin_csv}")

    return result
