"""
KPI Parser — loads Excel / CSV exports from gNB/EMS systems.

Supports:
  • Excel (.xlsx, .xls)
  • CSV  (.csv)

Output schema:
  {
    "source":      filename,
    "rows":        int,
    "cells":       list of unique Cell_IDs,
    "gnbs":        list of unique gNB_IDs,
    "time_range":  [start_str, end_str],
    "kpi_columns": list of canonical KPI keys found in the file,
    "df_json":     JSON-serialised DataFrame (orient="records"),
    "summary":     {kpi_key: {min, max, mean, std, p10, p90}},
    "parser_version": "kpi_v1",
  }
"""

import logging
from pathlib import Path
from typing import Dict, Any, List

import pandas as pd

from .kpi_defs import resolve_column, get_meta, KPI_CATALOG

logger = logging.getLogger(__name__)

# Columns that identify a row — not KPI measurements
ID_COLUMNS = {"timestamp", "cell_id", "gnb_id", "date", "time",
              "siteid", "site_id", "node_id", "nodeid", "enodebid",
              "gnbid", "cellid", "period", "granularityperiod"}


def _load_raw(filepath: str) -> pd.DataFrame:
    """Load Excel, CSV, or Parquet into a DataFrame."""
    path = Path(filepath)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(filepath, engine="openpyxl")
    elif suffix == ".csv":
        df = pd.read_csv(filepath)
    elif suffix == ".parquet":
        df = pd.read_parquet(filepath)
    else:
        raise ValueError(f"Unsupported format: {suffix}. Use .xlsx, .csv, or .parquet")
    return df


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename DataFrame columns to canonical KPI keys where possible.
    Non-KPI columns (Timestamp, Cell_ID, gNB_ID) are kept as-is
    but lowercased for consistent access.
    """
    rename_map = {}
    for col in df.columns:
        canon = resolve_column(col)
        if canon != col:
            rename_map[col] = canon
    if rename_map:
        df = df.rename(columns=rename_map)
        logger.info(f"Renamed {len(rename_map)} columns to canonical names")
    return df


def _detect_id_columns(df: pd.DataFrame) -> List[str]:
    """Identify which columns are identifiers (not KPI values)."""
    return [c for c in df.columns if c.lower().replace(" ", "_") in ID_COLUMNS
            or c.lower() in ID_COLUMNS]


def _find_timestamp_col(df: pd.DataFrame) -> str:
    """Find the timestamp/date column."""
    for col in df.columns:
        if col.lower() in ("timestamp", "date", "time", "datetime",
                           "period", "granularityperiod"):
            return col
    return ""


def _find_cell_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        if col.lower() in ("cell_id", "cellid", "cell", "eutrancell",
                           "nrcell", "nrcellid"):
            return col
    return ""


def _find_gnb_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        if col.lower() in ("gnb_id", "gnbid", "gnb", "nodeb",
                           "enodeb_id", "site_id", "siteid"):
            return col
    return ""


def parse_kpi_file(filepath: str) -> Dict[str, Any]:
    """
    Main entry point. Returns structured KPI output dict.
    """
    logger.info(f"Loading KPI file: {filepath}")
    df_raw = _load_raw(filepath)
    logger.info(f"Loaded {len(df_raw)} rows × {len(df_raw.columns)} cols")

    df = _normalise_columns(df_raw)

    # Identify structural columns
    ts_col   = _find_timestamp_col(df)
    cell_col = _find_cell_col(df)
    gnb_col  = _find_gnb_col(df)

    # Parse timestamp if found
    if ts_col and ts_col in df.columns:
        df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")

    # Identify KPI columns (all numeric columns that are not ID columns)
    id_cols = {c for c in [ts_col, cell_col, gnb_col] if c}
    kpi_cols = [
        c for c in df.columns
        if c not in id_cols
        and c.lower() not in ID_COLUMNS
        and pd.api.types.is_numeric_dtype(df[c])
    ]

    logger.info(f"KPI columns found: {kpi_cols}")

    # Summary stats per KPI column
    summary = {}
    for col in kpi_cols:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        meta = get_meta(col)
        summary[col] = {
            "label":     meta.get("label", col),
            "category":  meta.get("category", "Other"),
            "unit":      meta.get("unit", ""),
            "direction": meta.get("direction", "higher_better"),
            "target":    meta.get("target"),
            "warning":   meta.get("warning"),
            "critical":  meta.get("critical"),
            "min":   round(float(s.min()),  4),
            "max":   round(float(s.max()),  4),
            "mean":  round(float(s.mean()), 4),
            "std":   round(float(s.std()),  4),
            "p10":   round(float(s.quantile(0.10)), 4),
            "p90":   round(float(s.quantile(0.90)), 4),
        }

    # Cell and gNB lists
    cells = sorted(df[cell_col].dropna().unique().tolist()) if cell_col else []
    gnbs  = sorted(df[gnb_col].dropna().unique().tolist())  if gnb_col  else []

    # Time range
    if ts_col and ts_col in df.columns:
        valid_ts = df[ts_col].dropna()
        time_range = [
            str(valid_ts.min()) if len(valid_ts) else "?",
            str(valid_ts.max()) if len(valid_ts) else "?",
        ]
    else:
        time_range = ["?", "?"]

    # Serialise DataFrame to JSON-compatible list
    # Convert Timestamp to string for JSON serialisation
    df_out = df.copy()
    if ts_col and ts_col in df_out.columns:
        df_out[ts_col] = df_out[ts_col].astype(str)

    return {
        "source":         Path(filepath).name,
        "rows":           len(df),
        "cells":          cells,
        "gnbs":           gnbs,
        "time_range":     time_range,
        "kpi_columns":    kpi_cols,
        "timestamp_col":  ts_col,
        "cell_col":       cell_col,
        "gnb_col":        gnb_col,
        "df_records":     df_out.to_dict(orient="records"),
        "summary":        summary,
        "parser_version": "kpi_v1",
    }
