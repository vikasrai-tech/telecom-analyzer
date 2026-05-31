"""
Prediction Layer — Phase II (Tier 3)

Two forecasting methods:
  1. Prophet  — seasonal decomposition, handles daily/weekly cycles,
                best for KPI time-series with clear trends
  2. LSTM     — sequence model, captures nonlinear dependencies,
                best for irregular L1/L2 counter behaviour

Both return predicted anomalies in the same schema as the detection
layer, tagged state="predicted" with lead_time_h set.

Input:  parsed output from kpi_parser or stats_parser
        (requires timestamp_col + numeric columns)
Output: list of predicted anomaly dicts (state="predicted")
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Forecast horizon
DEFAULT_HORIZON_H = 4       # predict 4 hours ahead
DEFAULT_MIN_ROWS  = 24      # need at least 24 data points to forecast


# ── Helpers ───────────────────────────────────────────────────────────

def _get_thresholds(col: str, parsed: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """Return (warning, critical) for a column from either parser's metadata."""
    # Try stats metadata
    try:
        from src.parsers.stats_parser import get_meta as stats_meta
        m = stats_meta(col)
        if m["warning"] is not None:
            return m["warning"], m["critical"]
    except Exception:
        pass
    # Try KPI metadata
    try:
        from src.parsers.kpi_defs import get_meta as kpi_meta
        m = kpi_meta(col)
        if m.get("warning") is not None:
            return m["warning"], m["critical"]
    except Exception:
        pass
    return None, None


def _sev_from_forecast(val: float, warning: Optional[float],
                       critical: Optional[float], col: str) -> str:
    if warning is None:
        return "Low"
    worse_high = any(k in col for k in ("bler", "prb", "nack"))
    if worse_high:
        if critical is not None and val >= critical:
            return "Critical"
        if val >= warning:
            return "High"
    else:
        if critical is not None and val <= critical:
            return "Critical"
        if val <= warning:
            return "High"
    return "Low"


def _make_predicted(col, cell, forecast_val, horizon_h, sev, evidence, method) -> Dict:
    return {
        "label":          col,
        "category":       col,
        "cell_id":        str(cell),
        "gnb_id":         str(cell),
        "value":          round(float(forecast_val), 3),
        "unit":           "",
        "severity":       sev,
        "evidence":       evidence,
        "recommendation": f"Predicted {sev.lower()} anomaly in {col} within {horizon_h}h. "
                          f"Take proactive action now before threshold breach.",
        "detector":       f"Prediction ({method})",
        "score":          round(abs(forecast_val), 3),
        "state":          "predicted",
        "lead_time_h":    horizon_h,
        "source":         "prediction",
    }


# ── Prophet forecaster ────────────────────────────────────────────────

def forecast_prophet(
    parsed: Dict[str, Any],
    horizon_h: int = DEFAULT_HORIZON_H,
    min_rows:  int = DEFAULT_MIN_ROWS,
) -> List[Dict[str, Any]]:
    """
    Use Facebook Prophet to forecast KPI/Stats time series.
    Returns predicted anomalies with state='predicted'.
    """
    try:
        from prophet import Prophet
    except ImportError:
        logger.warning("[predictor] Prophet not installed — skipping")
        return []

    ts_col   = parsed.get("timestamp_col", "")
    cell_col = parsed.get("cell_col", "")
    cols     = parsed.get("l1l2_columns") or parsed.get("kpi_columns") or []

    if not ts_col or not cols:
        return []

    df = pd.DataFrame(parsed["df_records"])
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col])

    # Infer frequency for forecast horizon
    if len(df[ts_col].dropna()) < 2:
        return []
    freq_s = (df[ts_col].sort_values().diff().median().total_seconds())
    horizon_periods = max(1, int(horizon_h * 3600 / freq_s))

    predicted = []
    groups = df.groupby(cell_col) if cell_col else [("ALL", df)]

    for cell, grp in groups:
        for col in cols:
            sub = grp[[ts_col, col]].dropna().rename(
                columns={ts_col: "ds", col: "y"}
            ).sort_values("ds")
            if len(sub) < min_rows:
                continue

            try:
                m = Prophet(
                    interval_width=0.95,
                    daily_seasonality=False,
                    weekly_seasonality=False,
                    yearly_seasonality=False,
                    changepoint_prior_scale=0.1,
                )
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    m.fit(sub)

                future  = m.make_future_dataframe(periods=horizon_periods, freq=f"{int(freq_s)}s")
                fc      = m.predict(future)
                horizon_rows = fc.tail(horizon_periods)
                forecast_val = horizon_rows["yhat"].mean()
                forecast_hi  = horizon_rows["yhat_upper"].mean()

            except Exception as e:
                logger.debug(f"[prophet] {col}@{cell}: {e}")
                continue

            w, c = _get_thresholds(col, parsed)
            sev  = _sev_from_forecast(forecast_val, w, c, col)
            if sev == "Low":
                sev_hi = _sev_from_forecast(forecast_hi, w, c, col)
                if sev_hi == "Low":
                    continue
                sev = "Medium"  # upper bound will breach

            predicted.append(_make_predicted(
                col, cell, forecast_val, horizon_h, sev,
                evidence=(f"Prophet forecast: {col} will reach "
                          f"{forecast_val:.2f} (upper CI={forecast_hi:.2f}) "
                          f"in {horizon_h}h. Current mean={sub['y'].tail(5).mean():.2f}"),
                method="Prophet",
            ))
            logger.info(f"[prophet] {col}@{cell} forecast={forecast_val:.2f} sev={sev}")

    return predicted


# ── LSTM forecaster ───────────────────────────────────────────────────

class _LSTMForecaster:
    """Lightweight LSTM — trains quickly on short series (< 1s per cell/metric)."""

    def __init__(self, lookback: int = 12, hidden: int = 32, epochs: int = 30):
        self.lookback = lookback
        self.hidden   = hidden
        self.epochs   = epochs

    def _prepare(self, series: np.ndarray) -> Tuple[np.ndarray, float, float]:
        mu  = series.mean()
        sig = series.std() or 1.0
        z   = (series - mu) / sig
        X, y = [], []
        for i in range(len(z) - self.lookback):
            X.append(z[i:i + self.lookback])
            y.append(z[i + self.lookback])
        return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32), mu, sig

    def fit_predict(self, series: np.ndarray, horizon: int) -> np.ndarray:
        """Returns horizon-step ahead forecasts in original scale."""
        import torch
        import torch.nn as nn

        X, y_train, mu, sig = self._prepare(series)
        if len(X) < 5:
            return np.full(horizon, series[-1])

        X_t = torch.tensor(X).unsqueeze(-1)          # (N, T, 1)
        y_t = torch.tensor(y_train).unsqueeze(-1)     # (N, 1)

        model = nn.Sequential(
            nn.LSTM(1, self.hidden, batch_first=True),
        )

        class Net(nn.Module):
            def __init__(self, hidden):
                super().__init__()
                self.lstm   = nn.LSTM(1, hidden, batch_first=True)
                self.linear = nn.Linear(hidden, 1)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.linear(out[:, -1, :])

        net  = Net(self.hidden)
        opt  = torch.optim.Adam(net.parameters(), lr=1e-2)
        loss_fn = nn.MSELoss()

        net.train()
        for _ in range(self.epochs):
            opt.zero_grad()
            pred = net(X_t)
            loss = loss_fn(pred, y_t)
            loss.backward()
            opt.step()

        # Autoregressive forecast
        net.eval()
        window = list((series[-self.lookback:] - mu) / sig)
        preds  = []
        with torch.no_grad():
            for _ in range(horizon):
                x_in = torch.tensor(
                    np.array(window[-self.lookback:], dtype=np.float32)
                ).unsqueeze(0).unsqueeze(-1)
                nxt = net(x_in).item()
                preds.append(nxt)
                window.append(nxt)

        return np.array(preds) * sig + mu


def forecast_lstm(
    parsed: Dict[str, Any],
    horizon_h: int = DEFAULT_HORIZON_H,
    min_rows:  int = DEFAULT_MIN_ROWS,
) -> List[Dict[str, Any]]:
    """
    Use a lightweight LSTM to forecast KPI/Stats time series.
    Returns predicted anomalies with state='predicted'.
    """
    try:
        import torch  # noqa
    except ImportError:
        logger.warning("[predictor] PyTorch not installed — skipping LSTM")
        return []

    ts_col   = parsed.get("timestamp_col", "")
    cell_col = parsed.get("cell_col", "")
    cols     = parsed.get("l1l2_columns") or parsed.get("kpi_columns") or []

    if not ts_col or not cols:
        return []

    df = pd.DataFrame(parsed["df_records"])
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col])

    if len(df) < 2:
        return []
    freq_s = (df[ts_col].sort_values().diff().median().total_seconds())
    horizon_periods = max(1, int(horizon_h * 3600 / freq_s))

    forecaster = _LSTMForecaster()
    predicted  = []
    groups = df.groupby(cell_col) if cell_col else [("ALL", df)]

    for cell, grp in groups:
        for col in cols:
            series = grp.sort_values(ts_col)[col].dropna().values
            if len(series) < min_rows:
                continue

            try:
                forecasts    = forecaster.fit_predict(series, horizon_periods)
                forecast_val = float(forecasts.mean())
                forecast_max = float(forecasts.max())
            except Exception as e:
                logger.debug(f"[lstm] {col}@{cell}: {e}")
                continue

            w, c = _get_thresholds(col, parsed)
            sev  = _sev_from_forecast(forecast_val, w, c, col)
            if sev == "Low":
                sev_max = _sev_from_forecast(forecast_max, w, c, col)
                if sev_max == "Low":
                    continue
                sev = "Medium"

            predicted.append(_make_predicted(
                col, cell, forecast_val, horizon_h, sev,
                evidence=(f"LSTM forecast: {col} predicted "
                          f"{forecast_val:.2f} (peak={forecast_max:.2f}) "
                          f"in {horizon_h}h. Last 5 values mean={series[-5:].mean():.2f}"),
                method="LSTM",
            ))
            logger.info(f"[lstm] {col}@{cell} forecast={forecast_val:.2f} sev={sev}")

    return predicted


# ── Public API ────────────────────────────────────────────────────────

def run_prediction(
    parsed: Dict[str, Any],
    horizon_h: int = DEFAULT_HORIZON_H,
    methods: Optional[List[str]] = None,
) -> Dict[str, List[Dict]]:
    """
    Run prediction layer. Returns {method: [predicted_anomaly, ...]}.

    methods: None = run all; ["prophet"] or ["lstm"] to select.
    """
    if methods is None:
        methods = ["prophet", "lstm"]

    results: Dict[str, List] = {}

    if "prophet" in methods:
        logger.info("[predictor] Running Prophet forecast...")
        results["prophet"] = forecast_prophet(parsed, horizon_h=horizon_h)

    if "lstm" in methods:
        logger.info("[predictor] Running LSTM forecast...")
        results["lstm"] = forecast_lstm(parsed, horizon_h=horizon_h)

    total = sum(len(v) for v in results.values())
    logger.info(f"[predictor] Done — {total} predicted anomalies across {len(results)} methods")
    return results
