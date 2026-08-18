"""
Prediction Layer — Phase II

Three forecasting methods:
  1. Prophet       — off-the-shelf library baseline (seasonal/trend
                     decomposition), kept as a control for the benchmark
                     comparison rather than a built contribution.
  2. Holt-Winters  — explicitly-configured exponential smoothing
                     (additive damped trend, optional seasonality) via
                     statsmodels — a genuinely hand-configured baseline.
  3. LSTM          — hand-rolled PyTorch sequence model with a direct
                     multi-horizon output head (single forward pass over
                     the whole horizon, no autoregressive error
                     compounding) and a time-ordered train/val split.

All three return predicted anomalies in the same schema as the detection
layer, tagged state="predicted" with lead_time_h set. See
src/detection/forecast_eval.py for the backtesting/lead-time evaluation
harness that quantitatively compares them.

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

def _get_thresholds(col: str, parsed: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Return (warning, critical, direction) for a column from either parser's
    metadata. direction is "higher_better" / "lower_better" when known."""
    # Try stats metadata
    try:
        from src.parsers.stats_parser import get_meta as stats_meta
        m = stats_meta(col)
        if m["warning"] is not None:
            return m["warning"], m["critical"], m.get("direction")
    except Exception:
        pass
    # Try KPI metadata
    try:
        from src.parsers.kpi_defs import get_meta as kpi_meta
        m = kpi_meta(col)
        if m.get("warning") is not None:
            return m["warning"], m["critical"], m.get("direction")
    except Exception:
        pass
    return None, None, None


def _sev_from_forecast(val: float, warning: Optional[float],
                       critical: Optional[float], col: str,
                       direction: Optional[str] = None) -> str:
    if warning is None:
        return "Low"
    if direction is not None:
        worse_high = direction == "lower_better"
    else:
        worse_high = any(k in col.lower() for k in ("bler", "prb", "nack", "latency", "loss", "drop"))
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


def _infer_freq_seconds(df: pd.DataFrame, ts_col: str, cell_col: str = "") -> Optional[float]:
    """Median sampling interval in seconds, computed per-cell when a cell
    column is available. Rows for different cells sharing the same minute
    (the normal case for multi-cell KPI/stats exports) make the naive
    "sort the whole dataframe by timestamp and diff" median collapse to
    zero — that used to silently divide-by-zero downstream on any
    multi-cell dataset, only masked because the unit tests only ever used
    single-cell fixtures."""
    if cell_col and cell_col in df.columns:
        diffs = []
        for _, grp in df.groupby(cell_col):
            d = grp[ts_col].sort_values().diff().dropna()
            if len(d):
                diffs.append(d.median().total_seconds())
        return float(np.median(diffs)) if diffs else None

    d = df[ts_col].sort_values().diff().dropna()
    return float(d.median().total_seconds()) if len(d) else None


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

def _prophet_point_forecast(
    sub: pd.DataFrame, horizon_periods: int, freq_s: float,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Fit Prophet on a `ds`/`y` dataframe and return (yhat, yhat_upper) arrays
    of length `horizon_periods`, or None on failure. Raw point-forecast helper
    shared by `forecast_prophet()` (severity-filtered) and
    `forecast_eval.py`'s backtest harness (unfiltered regression metrics)."""
    try:
        from prophet import Prophet
    except ImportError:
        return None
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

        future = m.make_future_dataframe(periods=horizon_periods, freq=f"{int(freq_s)}s")
        fc     = m.predict(future)
        horizon_rows = fc.tail(horizon_periods)
        return horizon_rows["yhat"].values, horizon_rows["yhat_upper"].values
    except Exception:
        return None


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
        from prophet import Prophet  # noqa: F401 (import-guard only)
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

    # Infer sampling frequency (per-cell — see _infer_freq_seconds docstring)
    freq_s = _infer_freq_seconds(df, ts_col, cell_col)
    if not freq_s:
        return []
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

            fc = _prophet_point_forecast(sub, horizon_periods, freq_s)
            if fc is None:
                logger.debug(f"[prophet] {col}@{cell}: forecast failed")
                continue
            yhat, yhat_upper = fc
            forecast_val = float(np.mean(yhat))
            forecast_hi  = float(np.mean(yhat_upper))

            w, c, direction = _get_thresholds(col, parsed)
            sev  = _sev_from_forecast(forecast_val, w, c, col, direction)
            if sev == "Low":
                sev_hi = _sev_from_forecast(forecast_hi, w, c, col, direction)
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


# ── Holt-Winters forecaster ────────────────────────────────────────────

def _holt_winters_point_forecast(
    series: np.ndarray, horizon_periods: int, seasonal_periods: Optional[int] = None,
) -> Optional[np.ndarray]:
    """Fit Holt-Winters on a raw series and return a horizon-length forecast
    array, or None on failure/unavailability. Raw point-forecast helper shared
    by `forecast_holt_winters()` (severity-filtered) and `forecast_eval.py`'s
    backtest harness (unfiltered regression metrics)."""
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
    except ImportError:
        return None

    use_seasonal = (
        seasonal_periods is not None and len(series) >= 2 * seasonal_periods
    )
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ExponentialSmoothing(
                series,
                trend="add",
                damped_trend=True,
                seasonal="add" if use_seasonal else None,
                seasonal_periods=seasonal_periods if use_seasonal else None,
                initialization_method="estimated",
            )
            fit = model.fit(optimized=True)
            return np.asarray(fit.forecast(horizon_periods))
    except Exception:
        return None


def forecast_holt_winters(
    parsed: Dict[str, Any],
    horizon_h: int = DEFAULT_HORIZON_H,
    min_rows:  int = DEFAULT_MIN_ROWS,
    seasonal_periods: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Use Holt-Winters (additive trend, damped, optional additive seasonality)
    to forecast KPI/Stats time series. Unlike Prophet, the trend/seasonality
    configuration here is explicitly chosen rather than auto-fit by a
    higher-level library, so this is the "genuinely configured" baseline.
    Returns predicted anomalies with state='predicted'.
    """
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing  # noqa: F401
    except ImportError:
        logger.warning("[predictor] statsmodels not installed — skipping Holt-Winters")
        return []

    ts_col   = parsed.get("timestamp_col", "")
    cell_col = parsed.get("cell_col", "")
    cols     = parsed.get("l1l2_columns") or parsed.get("kpi_columns") or []

    if not ts_col or not cols:
        return []

    df = pd.DataFrame(parsed["df_records"])
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col])

    freq_s = _infer_freq_seconds(df, ts_col, cell_col)
    if not freq_s:
        return []
    horizon_periods = max(1, int(horizon_h * 3600 / freq_s))

    predicted = []
    groups = df.groupby(cell_col) if cell_col else [("ALL", df)]

    for cell, grp in groups:
        for col in cols:
            sub = grp[[ts_col, col]].dropna().sort_values(ts_col)
            if len(sub) < min_rows:
                continue

            series   = sub[col].values.astype(float)
            forecast = _holt_winters_point_forecast(series, horizon_periods, seasonal_periods)
            if forecast is None:
                logger.debug(f"[holt_winters] {col}@{cell}: forecast failed")
                continue

            forecast_val = float(np.mean(forecast))
            forecast_max = float(np.max(forecast))

            w, c, direction = _get_thresholds(col, parsed)
            sev  = _sev_from_forecast(forecast_val, w, c, col, direction)
            if sev == "Low":
                sev_max = _sev_from_forecast(forecast_max, w, c, col, direction)
                if sev_max == "Low":
                    continue
                sev = "Medium"

            predicted.append(_make_predicted(
                col, cell, forecast_val, horizon_h, sev,
                evidence=(f"Holt-Winters forecast: {col} predicted "
                          f"{forecast_val:.2f} (peak={forecast_max:.2f}) "
                          f"in {horizon_h}h. Last 5 values mean={series[-5:].mean():.2f}"),
                method="Holt-Winters",
            ))
            logger.info(f"[holt_winters] {col}@{cell} forecast={forecast_val:.2f} sev={sev}")

    return predicted


# ── LSTM forecaster ───────────────────────────────────────────────────

class _LSTMForecaster:
    """LSTM forecaster with a direct multi-horizon output head — predicts the
    whole horizon in a single forward pass instead of feeding predictions back
    in as input (which compounds error over a multi-hour horizon). Trains with
    a time-ordered train/val split and early stopping on validation MAE."""

    def __init__(self, lookback: int = 12, hidden: int = 32, epochs: int = 60,
                 val_frac: float = 0.2, patience: int = 8):
        self.lookback = lookback
        self.hidden   = hidden
        self.epochs   = epochs
        self.val_frac = val_frac
        self.patience = patience
        self.val_mae: Optional[float] = None
        self._net  = None
        self._mu   = 0.0
        self._sig  = 1.0

    def _windows(self, z: np.ndarray, horizon: int) -> Tuple[np.ndarray, np.ndarray]:
        X, y = [], []
        for i in range(len(z) - self.lookback - horizon + 1):
            X.append(z[i:i + self.lookback])
            y.append(z[i + self.lookback: i + self.lookback + horizon])
        return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)

    def fit(self, series: np.ndarray, horizon: int) -> "_LSTMForecaster":
        import torch
        import torch.nn as nn

        mu, sig = series.mean(), (series.std() or 1.0)
        self._mu, self._sig = mu, sig
        z = (series - mu) / sig

        X, y = self._windows(z, horizon)
        self._net, self.val_mae = None, None
        if len(X) < 5:
            return self

        n_val = min(max(1, int(len(X) * self.val_frac)), len(X) - 1)
        X_train, y_train = X[:-n_val], y[:-n_val]
        X_val,   y_val   = X[-n_val:], y[-n_val:]

        class Net(nn.Module):
            def __init__(self, hidden, horizon):
                super().__init__()
                self.lstm   = nn.LSTM(1, hidden, batch_first=True)
                self.linear = nn.Linear(hidden, horizon)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.linear(out[:, -1, :])

        net     = Net(self.hidden, horizon)
        opt     = torch.optim.Adam(net.parameters(), lr=1e-2)
        loss_fn = nn.MSELoss()

        X_train_t = torch.tensor(X_train).unsqueeze(-1)
        y_train_t = torch.tensor(y_train)
        X_val_t   = torch.tensor(X_val).unsqueeze(-1)
        y_val_t   = torch.tensor(y_val)

        best_val, best_state, stall = float("inf"), None, 0

        for _ in range(self.epochs):
            net.train()
            opt.zero_grad()
            loss = loss_fn(net(X_train_t), y_train_t)
            loss.backward()
            opt.step()

            net.eval()
            with torch.no_grad():
                val_mae = torch.mean(torch.abs(net(X_val_t) - y_val_t)).item()

            if val_mae < best_val - 1e-5:
                best_val, stall = val_mae, 0
                best_state = {k: v.clone() for k, v in net.state_dict().items()}
            else:
                stall += 1
                if stall >= self.patience:
                    break

        if best_state is not None:
            net.load_state_dict(best_state)
        net.eval()

        self._net    = net
        self.val_mae = best_val * sig  # de-normalize to original units
        return self

    @property
    def is_fitted(self) -> bool:
        """True once fit() has trained a net (False if there wasn't enough
        data to build >=5 training windows for the requested horizon)."""
        return self._net is not None

    def predict(self, series: np.ndarray, horizon: int) -> np.ndarray:
        """Direct multi-horizon forecast via a single forward pass."""
        import torch

        if not self.is_fitted:
            return np.full(horizon, series[-1])

        window = (series[-self.lookback:] - self._mu) / self._sig
        x_in = torch.tensor(window, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
        with torch.no_grad():
            out = self._net(x_in).squeeze(0).numpy()
        return out * self._sig + self._mu

    def fit_predict(self, series: np.ndarray, horizon: int) -> np.ndarray:
        """Fit then predict in one call."""
        self.fit(series, horizon)
        return self.predict(series, horizon)


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

    freq_s = _infer_freq_seconds(df, ts_col, cell_col)
    if not freq_s:
        return []
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
                forecaster.fit(series, horizon_periods)
                if not forecaster.is_fitted:
                    logger.debug(
                        f"[lstm] {col}@{cell}: not enough rows for horizon="
                        f"{horizon_periods} periods — skipping (no fabricated flat forecast)"
                    )
                    continue
                forecasts    = forecaster.predict(series, horizon_periods)
                forecast_val = float(forecasts.mean())
                forecast_max = float(forecasts.max())
            except Exception as e:
                logger.debug(f"[lstm] {col}@{cell}: {e}")
                continue

            w, c, direction = _get_thresholds(col, parsed)
            sev  = _sev_from_forecast(forecast_val, w, c, col, direction)
            if sev == "Low":
                sev_max = _sev_from_forecast(forecast_max, w, c, col, direction)
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
        methods = ["prophet", "holt_winters", "lstm"]

    results: Dict[str, List] = {}

    if "prophet" in methods:
        logger.info("[predictor] Running Prophet forecast (off-the-shelf baseline)...")
        results["prophet"] = forecast_prophet(parsed, horizon_h=horizon_h)

    if "holt_winters" in methods:
        logger.info("[predictor] Running Holt-Winters forecast...")
        results["holt_winters"] = forecast_holt_winters(parsed, horizon_h=horizon_h)

    if "lstm" in methods:
        logger.info("[predictor] Running LSTM forecast...")
        results["lstm"] = forecast_lstm(parsed, horizon_h=horizon_h)

    total = sum(len(v) for v in results.values())
    logger.info(f"[predictor] Done — {total} predicted anomalies across {len(results)} methods")
    return results
