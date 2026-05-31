"""
DU/CU Stats Parser — L1/L2 counters from srsRAN, OAI, NIST formats.

Supports:
  • srsRAN gNB stats CSV  (pci, dl_nof_ok/nok, dl_prb, dl_mcs, pusch_snr_db …)
  • OAI gNB stats CSV     (DL_MCS1, PRB_DL, dlsch_errors, SNR …)
  • NIST / generic CSV    (RSRP_dBm, DL_BLER_pct, PRB_Utilization_pct …)
  • Parquet               (any of the above saved as .parquet)

Output schema (canonical, same shape as kpi_parser output):
  {
    "source":        filename,
    "format":        "srsran" | "oai" | "nist" | "generic",
    "rows":          int,
    "cells":         [cell_id, ...],
    "time_range":    [start_str, end_str],
    "l1l2_columns":  [canonical_col, ...],   # e.g. dl_bler, dl_mcs, ul_prb_util
    "timestamp_col": str,
    "cell_col":      str,
    "df_records":    list-of-dicts,          # for dashboard / detection
    "summary":       {col: {min,max,mean,std,p10,p90}},
    "parser_version": "stats_v1",
  }
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Canonical column definitions ─────────────────────────────────────
# (canonical_name, unit, description)
L1L2_META: Dict[str, Dict] = {
    "dl_prb_util":      {"unit": "%",    "desc": "DL PRB Utilisation",       "warning": 80,  "critical": 90},
    "ul_prb_util":      {"unit": "%",    "desc": "UL PRB Utilisation",       "warning": 80,  "critical": 90},
    "dl_bler":          {"unit": "%",    "desc": "DL Block Error Rate",       "warning": 10,  "critical": 20},
    "ul_bler":          {"unit": "%",    "desc": "UL Block Error Rate",       "warning": 10,  "critical": 20},
    "dl_mcs":           {"unit": "idx",  "desc": "DL Modulation Coding Scheme", "warning": 6, "critical": 4},
    "ul_mcs":           {"unit": "idx",  "desc": "UL Modulation Coding Scheme", "warning": 6, "critical": 4},
    "dl_harq_nack_rate":{"unit": "%",    "desc": "DL HARQ NACK Rate",         "warning": 15,  "critical": 25},
    "ul_harq_nack_rate":{"unit": "%",    "desc": "UL HARQ NACK Rate",         "warning": 15,  "critical": 25},
    "dl_throughput_mbps":{"unit": "Mbps","desc": "DL Throughput",             "warning": None,"critical": None},
    "ul_throughput_mbps":{"unit": "Mbps","desc": "UL Throughput",             "warning": None,"critical": None},
    "pusch_snr_db":     {"unit": "dB",   "desc": "UL PUSCH SINR",             "warning": 5,   "critical": 0},
    "pucch_snr_db":     {"unit": "dB",   "desc": "UL PUCCH SINR",             "warning": 5,   "critical": 0},
    "snr_db":           {"unit": "dB",   "desc": "SNR",                       "warning": 5,   "critical": 0},
    "rsrp_dbm":         {"unit": "dBm",  "desc": "Reference Signal Received Power","warning":-105,"critical":-115},
    "rsrq_db":          {"unit": "dB",   "desc": "Reference Signal Received Quality","warning":-14,"critical":-18},
    "nof_ue":           {"unit": "count","desc": "Active UE Count",            "warning": None,"critical": None},
    "dl_harq_nack":     {"unit": "count","desc": "DL HARQ NACK count (raw)",   "warning": None,"critical": None},
    "ul_harq_nack":     {"unit": "count","desc": "UL HARQ NACK count (raw)",   "warning": None,"critical": None},
}

# ── Format fingerprints ───────────────────────────────────────────────
_SRSRAN_KEYS  = {"dl_nof_ok", "dl_nof_nok", "ul_nof_ok", "ul_nof_nok",
                 "pusch_snr_db", "dl_brate", "ul_brate", "pci"}
_OAI_KEYS     = {"dlsch_total", "dlsch_errors", "dl_mcs1", "prb_dl", "snr"}
_NIST_KEYS    = {"rsrp_dbm", "dl_bler_pct", "prb_utilization_pct", "harq_nack_dl"}


def _detect_format(cols: List[str]) -> str:
    lower = {c.lower() for c in cols}
    if _SRSRAN_KEYS & lower:
        return "srsran"
    if _OAI_KEYS & lower:
        return "oai"
    if _NIST_KEYS & lower:
        return "nist"
    return "generic"


def _find_col(df: pd.DataFrame, candidates: List[str]) -> str:
    """Return first matching column (case-insensitive), or ''."""
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return ""


def _normalize_srsran(df: pd.DataFrame) -> Tuple[pd.DataFrame, str, str]:
    """Map srsRAN columns → canonical names. Returns (df, ts_col, cell_col)."""
    ts_col   = _find_col(df, ["timestamp", "time", "t"])
    cell_col = _find_col(df, ["pci", "cell_id", "cell"])

    rename: Dict[str, str] = {}

    # PRB utilisation: srsRAN gives absolute PRB count (out of 106 for 20MHz NR)
    # We convert to % if values look like counts (<= 110), else treat as %
    dl_prb = _find_col(df, ["dl_prb"])
    ul_prb = _find_col(df, ["ul_prb"])
    if dl_prb:
        if df[dl_prb].max() <= 110:
            df["dl_prb_util"] = (df[dl_prb] / 106 * 100).round(1)
        else:
            rename[dl_prb] = "dl_prb_util"
    if ul_prb:
        if df[ul_prb].max() <= 110:
            df["ul_prb_util"] = (df[ul_prb] / 106 * 100).round(1)
        else:
            rename[ul_prb] = "ul_prb_util"

    # BLER from HARQ ok/nok counts
    dl_ok  = _find_col(df, ["dl_nof_ok"])
    dl_nok = _find_col(df, ["dl_nof_nok"])
    ul_ok  = _find_col(df, ["ul_nof_ok"])
    ul_nok = _find_col(df, ["ul_nof_nok"])
    if dl_ok and dl_nok:
        total = df[dl_ok] + df[dl_nok]
        df["dl_bler"]          = (df[dl_nok] / total.replace(0, np.nan) * 100).round(2)
        df["dl_harq_nack_rate"]= df["dl_bler"]
    if ul_ok and ul_nok:
        total = df[ul_ok] + df[ul_nok]
        df["ul_bler"]          = (df[ul_nok] / total.replace(0, np.nan) * 100).round(2)
        df["ul_harq_nack_rate"]= df["ul_bler"]

    # MCS
    for src, dst in [("dl_mcs", "dl_mcs"), ("ul_mcs", "ul_mcs")]:
        col = _find_col(df, [src])
        if col and col != dst:
            rename[col] = dst

    # Throughput — srsRAN dl_brate/ul_brate in bps → Mbps
    dl_brate = _find_col(df, ["dl_brate"])
    ul_brate = _find_col(df, ["ul_brate"])
    if dl_brate:
        df["dl_throughput_mbps"] = (df[dl_brate] / 1e6).round(2)
    if ul_brate:
        df["ul_throughput_mbps"] = (df[ul_brate] / 1e6).round(2)

    # SNR
    for src, dst in [("pusch_snr_db", "pusch_snr_db"), ("pucch_snr_db", "pucch_snr_db")]:
        col = _find_col(df, [src])
        if col:
            rename[col] = dst

    # nof_ue
    nue = _find_col(df, ["nof_ue"])
    if nue:
        rename[nue] = "nof_ue"

    if rename:
        df = df.rename(columns=rename)
    return df, ts_col, cell_col


def _normalize_oai(df: pd.DataFrame) -> Tuple[pd.DataFrame, str, str]:
    ts_col   = _find_col(df, ["timestamp", "time"])
    cell_col = _find_col(df, ["cell_id", "cell", "ue_id", "imsi"])

    rename: Dict[str, str] = {}

    # BLER — OAI may provide directly or as errors/total
    dl_bler = _find_col(df, ["DL_BLER", "dl_bler"])
    ul_bler = _find_col(df, ["UL_BLER", "ul_bler"])
    if dl_bler:
        rename[dl_bler] = "dl_bler"
    elif _find_col(df, ["dlsch_errors"]) and _find_col(df, ["dlsch_total"]):
        e = _find_col(df, ["dlsch_errors"])
        t = _find_col(df, ["dlsch_total"])
        df["dl_bler"] = (df[e] / df[t].replace(0, np.nan) * 100).round(2)
        df["dl_harq_nack_rate"] = df["dl_bler"]
    if ul_bler:
        rename[ul_bler] = "ul_bler"
    elif _find_col(df, ["ulsch_errors"]) and _find_col(df, ["ulsch_total"]):
        e = _find_col(df, ["ulsch_errors"])
        t = _find_col(df, ["ulsch_total"])
        df["ul_bler"] = (df[e] / df[t].replace(0, np.nan) * 100).round(2)
        df["ul_harq_nack_rate"] = df["ul_bler"]

    # PRB
    for src, dst in [("PRB_DL", "dl_prb_util"), ("PRB_UL", "ul_prb_util")]:
        col = _find_col(df, [src])
        if col:
            rename[col] = dst

    # MCS
    for src, dst in [("DL_MCS1", "dl_mcs"), ("UL_MCS1", "ul_mcs"),
                     ("dl_mcs1", "dl_mcs"), ("ul_mcs1", "ul_mcs")]:
        col = _find_col(df, [src])
        if col and dst not in df.columns:
            rename[col] = dst

    # SNR
    snr = _find_col(df, ["SNR", "snr"])
    if snr:
        rename[snr] = "snr_db"

    # Throughput
    for src, dst in [("DL_bitrate", "dl_throughput_mbps"), ("UL_bitrate", "ul_throughput_mbps")]:
        col = _find_col(df, [src])
        if col:
            df[dst] = (df[col] / 1e6).round(2)

    if rename:
        df = df.rename(columns=rename)
    return df, ts_col, cell_col


def _normalize_nist(df: pd.DataFrame) -> Tuple[pd.DataFrame, str, str]:
    ts_col   = _find_col(df, ["Time", "timestamp", "time"])
    cell_col = _find_col(df, ["Cell", "cell_id", "cell", "IMSI"])

    rename: Dict[str, str] = {}

    mappings = [
        (["RSRP_dBm", "rsrp_dbm", "RSRP"],                 "rsrp_dbm"),
        (["RSRQ_dB",  "rsrq_db",  "RSRQ"],                 "rsrq_db"),
        (["SNR_dB",   "snr_db",   "SNR"],                   "snr_db"),
        (["DL_BLER_pct", "DL_BLER", "dl_bler"],             "dl_bler"),
        (["UL_BLER_pct", "UL_BLER", "ul_bler"],             "ul_bler"),
        (["PRB_Utilization_pct", "PRB_util", "prb_util"],   "dl_prb_util"),
        (["DL_MCS", "dl_mcs"],                              "dl_mcs"),
        (["UL_MCS", "ul_mcs"],                              "ul_mcs"),
        (["DL_Throughput_Mbps", "dl_throughput"],           "dl_throughput_mbps"),
        (["UL_Throughput_Mbps", "ul_throughput"],           "ul_throughput_mbps"),
        (["HARQ_NACK_DL", "harq_nack_dl"],                  "dl_harq_nack"),
        (["HARQ_NACK_UL", "harq_nack_ul"],                  "ul_harq_nack"),
    ]
    for candidates, canonical in mappings:
        col = _find_col(df, candidates)
        if col and col != canonical:
            rename[col] = canonical

    # Derive HARQ NACK rate if raw counts available
    if "dl_harq_nack" in df.columns or "dl_harq_nack" in rename.values():
        pass  # keep as raw count; detector will handle

    if rename:
        df = df.rename(columns=rename)
    return df, ts_col, cell_col


def _normalize_generic(df: pd.DataFrame) -> Tuple[pd.DataFrame, str, str]:
    ts_col   = _find_col(df, ["timestamp", "time", "Time", "date"])
    cell_col = _find_col(df, ["cell_id", "cell", "pci", "enb_id", "gnb_id"])
    # Best-effort: return as-is; detection will skip unknown columns
    return df, ts_col, cell_col


def _summary(df: pd.DataFrame, cols: List[str]) -> Dict[str, Any]:
    out = {}
    for col in cols:
        if col not in df.columns:
            continue
        s = df[col].dropna()
        if s.empty:
            continue
        out[col] = {
            "min":  round(float(s.min()),  3),
            "max":  round(float(s.max()),  3),
            "mean": round(float(s.mean()), 3),
            "std":  round(float(s.std()),  3),
            "p10":  round(float(s.quantile(0.10)), 3),
            "p90":  round(float(s.quantile(0.90)), 3),
        }
    return out


# ── Public API ────────────────────────────────────────────────────────

def parse_stats_file(filepath: str) -> Dict[str, Any]:
    """
    Parse a DU/CU stats file (CSV or Parquet) and return normalised output.
    Auto-detects srsRAN / OAI / NIST / generic format.
    """
    path   = Path(filepath)
    suffix = path.suffix.lower()

    if suffix == ".parquet":
        df = pd.read_parquet(filepath)
    elif suffix == ".csv":
        df = pd.read_csv(filepath)
    else:
        raise ValueError(f"Unsupported format: {suffix}. Use .csv or .parquet")

    logger.info(f"Loaded stats file: {path.name}  ({len(df)} rows × {len(df.columns)} cols)")

    fmt = _detect_format(list(df.columns))
    logger.info(f"Detected format: {fmt}")

    if fmt == "srsran":
        df, ts_col, cell_col = _normalize_srsran(df)
    elif fmt == "oai":
        df, ts_col, cell_col = _normalize_oai(df)
    elif fmt == "nist":
        df, ts_col, cell_col = _normalize_nist(df)
    else:
        df, ts_col, cell_col = _normalize_generic(df)

    # Identify which canonical L1/L2 columns are present
    l1l2_cols = [c for c in L1L2_META if c in df.columns]

    # Parse timestamps
    if ts_col and ts_col in df.columns:
        df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
        valid_ts = df[ts_col].dropna()
        time_range = (
            [str(valid_ts.min()), str(valid_ts.max())]
            if not valid_ts.empty else ["", ""]
        )
    else:
        time_range = ["", ""]

    cells = sorted(df[cell_col].dropna().unique().tolist()) if cell_col else []

    return {
        "source":         path.name,
        "format":         fmt,
        "rows":           len(df),
        "cells":          [str(c) for c in cells],
        "time_range":     time_range,
        "l1l2_columns":   l1l2_cols,
        "timestamp_col":  ts_col,
        "cell_col":       cell_col,
        "df_records":     df.to_dict(orient="records"),
        "summary":        _summary(df, l1l2_cols),
        "parser_version": "stats_v1",
    }


def get_meta(col: str) -> Dict[str, Any]:
    """Return metadata (unit, desc, warning, critical) for a canonical L1/L2 column."""
    return L1L2_META.get(col, {"unit": "", "desc": col, "warning": None, "critical": None})
