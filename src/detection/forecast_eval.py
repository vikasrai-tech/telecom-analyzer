"""
Forecast Evaluation Harness — Phase II

Nothing like this existed anywhere in the repo before: Phase I's predictor
produced forecasts but never quantified whether they were any good. This
module adds two kinds of evidence:

  1. Rolling-origin backtest — MAE/RMSE/MAPE per (method, cell, column),
     computed by repeatedly training on data up to a moving origin and
     scoring the forecast against the actual held-out values.
  2. Anomaly lead-time evaluation — using the known injected-anomaly
     windows from scripts/generate_kpi_timeseries.py as ground truth,
     checks whether each method's predicted anomalies correctly flag the
     event before it starts (true positive + lead time), miss it (false
     negative), or fire when nothing is there (false alarm).

Both feed `run_benchmark_report()`, a single entry point that produces the
comparison table used to argue the Phase II "benchmark vs existing
methods" contribution.
"""

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.detection.predictor import (
    _prophet_point_forecast,
    _holt_winters_point_forecast,
    _LSTMForecaster,
    _get_timesfm,
    _moirai_point_forecast,
    _get_thresholds,
    _sev_from_forecast,
    _infer_freq_seconds,
)

logger = logging.getLogger(__name__)

# "nhits" is intentionally excluded — it requires full-dataset training and
# cannot be dispatched per-series through _point_forecast. Use
# scripts/run_nhits_benchmark.py to produce nhits benchmark numbers.
DEFAULT_METHODS = ("prophet", "holt_winters", "lstm", "timesfm", "moirai")


# ── Result schemas ──────────────────────────────────────────────────────

@dataclass
class ForecastMetrics:
    method: str
    cell_id: str
    column: str
    mae: float
    rmse: float
    mape: Optional[float]
    n_origins: int


@dataclass
class LeadTimeMetrics:
    method: str
    injected_event: str
    cell_id: str
    column: str
    detected: bool
    lead_time_h: Optional[float]
    false_alarms: int


# ── Ground truth: injected anomaly windows from generate_kpi_timeseries.py ──
# Hours are relative to the start of the series (START = 08:00 in the
# generator). Kept here as the single source of truth for what "correct"
# means when scoring lead-time detection against data/raw/kpi_10hr_sample.csv.

# NOTE on what "lead time" can honestly mean here: all three injected
# anomalies below are abrupt step-changes (congestion/outage) or a trend
# whose slope changes abruptly at onset (drift) — none of them have an
# observable precursor in the historical data *before* they start, so no
# pure history-based forecaster (Prophet, Holt-Winters, or the LSTM here)
# can predict them ahead of time; that's a property of the dataset (it was
# designed to validate anomaly *detectors*, not forecasters), not a defect
# in the forecasting methods. Genuine forecast lead time only exists for
# anomalies with a real leading trend (see
# tests/test_forecast_eval.py::test_lead_time_detects_genuine_precursor_trend
# for a positive demonstration against a synthetic series built for that).
# Against this dataset, `evaluate_anomaly_lead_time` is still useful for
# what it can honestly show: whether a method stays quiet (few false
# alarms) on the lead-up to and away from each window.
KPI_10HR_GROUND_TRUTH: List[Dict[str, Any]] = [
    {"cell_id": "PCI_5", "column": "Handover_Success_Rate_%", "start_h": 4.5, "end_h": 5.5, "kind": "congestion"},
    {"cell_id": "PCI_5", "column": "DL_Throughput_Mbps", "start_h": 4.5, "end_h": 5.5, "kind": "congestion"},
    {"cell_id": "PCI_8", "column": "Cell_Availability_%", "start_h": 7.0, "end_h": 7.33, "kind": "outage"},
    {"cell_id": "PCI_8", "column": "RACH_Success_Rate_%", "start_h": 7.0, "end_h": 7.33, "kind": "outage"},
    {"cell_id": "PCI_2", "column": "Handover_Success_Rate_%", "start_h": 8.0, "end_h": 10.0, "kind": "drift"},
    {"cell_id": "PCI_2", "column": "Latency_ms", "start_h": 8.0, "end_h": 10.0, "kind": "drift"},
]


# ── Helpers ──────────────────────────────────────────────────────────────

def _point_forecast(method: str, sub: pd.DataFrame, ts_col: str, col: str,
                    horizon_periods: int, freq_s: float) -> Optional[np.ndarray]:
    """Dispatch to the raw point-forecast helper for a given method. Returns
    a horizon-length array, or None if the method can't produce a forecast
    (missing dependency, insufficient data, fit failure)."""
    series = sub[col].values.astype(float)

    if method == "prophet":
        ds_y = sub[[ts_col, col]].rename(columns={ts_col: "ds", col: "y"})
        fc = _prophet_point_forecast(ds_y, horizon_periods, freq_s)
        return None if fc is None else fc[0]

    if method == "holt_winters":
        return _holt_winters_point_forecast(series, horizon_periods)

    if method == "lstm":
        forecaster = _LSTMForecaster()
        forecaster.fit(series, horizon_periods)
        if not forecaster.is_fitted:
            return None
        return forecaster.predict(series, horizon_periods)

    if method == "timesfm":
        tfm = _get_timesfm()
        if tfm is None:
            return None
        try:
            # Context must be a multiple of 32 (patch size), capped at 512
            ctx = min(512, max(64, (len(series) // 32) * 32))
            context = (series[-ctx:] if len(series) >= ctx else
                       np.pad(series, (ctx - len(series), 0), mode="edge"))
            point_forecasts, _ = tfm.forecast(
                horizon=horizon_periods,
                inputs=[context],
            )
            return point_forecasts[0]  # shape: (horizon_periods,)
        except Exception as e:
            logger.debug(f"[timesfm] point_forecast failed: {e}")
            return None

    if method == "moirai":
        return _moirai_point_forecast(series, horizon_periods)

    if method == "nhits":
        raise ValueError(
            "nhits requires full-dataset training and cannot be evaluated "
            "per-series in the rolling-origin harness. "
            "Use scripts/run_nhits_benchmark.py instead."
        )

    raise ValueError(f"Unknown method: {method}")


def _series_for(parsed: Dict[str, Any], cell_id: str, column: str) -> Optional[pd.DataFrame]:
    """Return a ts_col/column dataframe for one cell, sorted by time."""
    ts_col = parsed.get("timestamp_col", "")
    cell_col = parsed.get("cell_col", "")
    df = pd.DataFrame(parsed["df_records"])
    if ts_col not in df.columns or column not in df.columns:
        return None
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col, column])
    if cell_col and cell_col in df.columns:
        df = df[df[cell_col] == cell_id]
    return df[[ts_col, column]].sort_values(ts_col).reset_index(drop=True)


# ── Rolling-origin backtest ──────────────────────────────────────────────

def rolling_origin_backtest(
    parsed: Dict[str, Any],
    methods: Tuple[str, ...] = DEFAULT_METHODS,
    horizon_h: int = 4,
    n_origins: int = 8,
    step_h: int = 1,
    min_train_rows: int = 24,
) -> List[ForecastMetrics]:
    """
    For each cell/column, slide the train/test origin `n_origins` times
    (step_h apart), fit each method on data up to the origin, forecast
    horizon_h ahead, and score MAE/RMSE/MAPE against the actual held-out
    values. Returns one ForecastMetrics per (method, cell, column).
    """
    ts_col = parsed.get("timestamp_col", "")
    cell_col = parsed.get("cell_col", "")
    cols = parsed.get("l1l2_columns") or parsed.get("kpi_columns") or []
    if not ts_col or not cols:
        return []

    df_all = pd.DataFrame(parsed["df_records"])
    df_all[ts_col] = pd.to_datetime(df_all[ts_col], errors="coerce")
    df_all = df_all.dropna(subset=[ts_col])

    freq_s = _infer_freq_seconds(df_all, ts_col, cell_col)
    if not freq_s:
        return []
    horizon_periods = max(1, int(horizon_h * 3600 / freq_s))
    step_periods = max(1, int(step_h * 3600 / freq_s))

    groups = df_all.groupby(cell_col) if cell_col else [("ALL", df_all)]
    results: List[ForecastMetrics] = []

    for cell, grp in groups:
        for col in cols:
            sub = grp[[ts_col, col]].dropna().sort_values(ts_col).reset_index(drop=True)
            n = len(sub)
            if n < min_train_rows + horizon_periods + (n_origins - 1) * step_periods:
                # Not enough rows for the requested number of rolling origins —
                # shrink n_origins rather than skip the column entirely.
                usable_origins = max(
                    1, (n - min_train_rows - horizon_periods) // step_periods + 1
                )
                if usable_origins < 1:
                    continue
            else:
                usable_origins = n_origins

            for method in methods:
                errors = []
                actuals = []
                for k in range(usable_origins):
                    origin = n - horizon_periods - k * step_periods
                    if origin < min_train_rows:
                        break
                    train = sub.iloc[:origin]
                    actual = sub[col].values[origin:origin + horizon_periods]
                    if len(actual) < horizon_periods:
                        continue

                    forecast = _point_forecast(method, train, ts_col, col, horizon_periods, freq_s)
                    if forecast is None or len(forecast) != len(actual):
                        continue
                    errors.append(np.asarray(forecast) - actual)
                    actuals.append(actual)

                if not errors:
                    continue
                err = np.concatenate(errors)
                actual_concat = np.concatenate(actuals)
                mae = float(np.mean(np.abs(err)))
                rmse = float(np.sqrt(np.mean(err ** 2)))
                nonzero = actual_concat != 0
                mape = (
                    float(np.mean(np.abs(err[nonzero] / actual_concat[nonzero])) * 100)
                    if nonzero.any() else None
                )

                results.append(ForecastMetrics(
                    method=method, cell_id=str(cell), column=col,
                    mae=round(mae, 4), rmse=round(rmse, 4),
                    mape=round(mape, 2) if mape is not None else None,
                    n_origins=len(errors),
                ))

    return results


# ── Anomaly lead-time evaluation ─────────────────────────────────────────

def evaluate_anomaly_lead_time(
    parsed: Dict[str, Any],
    ground_truth_events: List[Dict[str, Any]],
    methods: Tuple[str, ...] = DEFAULT_METHODS,
    horizon_h: int = 4,
    check_step_h: float = 0.5,
) -> List[LeadTimeMetrics]:
    """
    For each ground-truth event window, walk backward from its start_h in
    `check_step_h` steps and ask: at what point does the forecaster first
    predict an anomalous severity for this cell/column within horizon_h?
    That gap is the lead time. If no origin before start_h predicts it,
    it's a miss (detected=False). Also counts false alarms: origins with
    no nearby ground-truth window where the method still predicts High/
    Critical severity.
    """
    ts_col = parsed.get("timestamp_col", "")
    cell_col = parsed.get("cell_col", "")
    if not ts_col:
        return []

    df_all = pd.DataFrame(parsed["df_records"])
    df_all[ts_col] = pd.to_datetime(df_all[ts_col], errors="coerce")
    df_all = df_all.dropna(subset=[ts_col])
    t0 = df_all[ts_col].min()
    freq_s = _infer_freq_seconds(df_all, ts_col, cell_col)
    if not freq_s:
        return []
    horizon_periods = max(1, int(horizon_h * 3600 / freq_s))

    results: List[LeadTimeMetrics] = []

    for event in ground_truth_events:
        cell_id, column = event["cell_id"], event["column"]
        start_h = event["start_h"]
        sub = _series_for(parsed, cell_id, column)
        if sub is None or len(sub) < 24:
            continue

        w, c, direction = _get_thresholds(column, parsed)

        for method in methods:
            detected, lead_time_h, false_alarms = False, None, 0

            check_h = start_h
            while check_h - check_step_h >= 0 and not detected:
                check_h -= check_step_h
                origin_ts = t0 + pd.Timedelta(hours=check_h)
                train = sub[sub[ts_col] <= origin_ts]
                if len(train) < 24:
                    continue

                forecast = _point_forecast(method, train, ts_col, column, horizon_periods, freq_s)
                if forecast is None:
                    continue
                forecast_val = float(np.mean(forecast))
                sev = _sev_from_forecast(forecast_val, w, c, column, direction)
                if sev in ("High", "Critical"):
                    detected = True
                    lead_time_h = round(start_h - check_h, 2)

            # False-alarm scan: origins well before the event where a
            # High/Critical forecast still fires (not explained by any
            # ground-truth window for this cell/column).
            other_windows = [
                e for e in ground_truth_events
                if e["cell_id"] == cell_id and e["column"] == column
            ]
            clean_checks_h = [
                h for h in np.arange(0.5, max(start_h - horizon_h, 0.5), check_step_h * 2)
                if not any(w_["start_h"] - horizon_h <= h <= w_["end_h"] for w_ in other_windows)
            ]
            for h in clean_checks_h[:6]:  # cap cost
                origin_ts = t0 + pd.Timedelta(hours=h)
                train = sub[sub[ts_col] <= origin_ts]
                if len(train) < 24:
                    continue
                forecast = _point_forecast(method, train, ts_col, column, horizon_periods, freq_s)
                if forecast is None:
                    continue
                if _sev_from_forecast(float(np.mean(forecast)), w, c, column, direction) in ("High", "Critical"):
                    false_alarms += 1

            results.append(LeadTimeMetrics(
                method=method, injected_event=event["kind"], cell_id=cell_id,
                column=column, detected=detected, lead_time_h=lead_time_h,
                false_alarms=false_alarms,
            ))

    return results


# ── Combined report ──────────────────────────────────────────────────────

def run_benchmark_report(
    parsed: Dict[str, Any],
    ground_truth_events: Optional[List[Dict[str, Any]]] = None,
    methods: Tuple[str, ...] = DEFAULT_METHODS,
    horizon_h: int = 4,
) -> Dict[str, Any]:
    """One-call entry point: backtest accuracy + lead-time evaluation,
    flattened into a summary table suitable for the dashboard/report."""
    accuracy = rolling_origin_backtest(parsed, methods=methods, horizon_h=horizon_h)
    lead_time = (
        evaluate_anomaly_lead_time(parsed, ground_truth_events, methods=methods, horizon_h=horizon_h)
        if ground_truth_events else []
    )

    by_method: Dict[str, Dict[str, float]] = {}
    for m in accuracy:
        agg = by_method.setdefault(m.method, {"mae_sum": 0.0, "rmse_sum": 0.0, "n": 0})
        agg["mae_sum"] += m.mae
        agg["rmse_sum"] += m.rmse
        agg["n"] += 1
    summary_table = [
        {
            "method": method,
            "avg_mae": round(agg["mae_sum"] / agg["n"], 4),
            "avg_rmse": round(agg["rmse_sum"] / agg["n"], 4),
            "n_series": agg["n"],
            "lead_time_detected": sum(
                1 for lt in lead_time if lt.method == method and lt.detected
            ),
            "lead_time_total": sum(1 for lt in lead_time if lt.method == method),
        }
        for method, agg in by_method.items() if agg["n"] > 0
    ]

    return {
        "forecast_accuracy": [asdict(m) for m in accuracy],
        "lead_time": [asdict(m) for m in lead_time],
        "summary_table": summary_table,
    }
