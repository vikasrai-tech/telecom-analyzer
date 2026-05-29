"""
Feature Engineering — converts parsed PCAP output into ML feature vectors.

Two feature spaces:
  1. Procedure-level  — one row per procedure (for Isolation Forest)
  2. Sequence-level   — sliding windows over message_log (for LSTM Autoencoder)
"""

from typing import Dict, Any, List, Tuple
import numpy as np

# ── Layer / role integer encodings ────────────────────────────────────
LAYER_IDS  = {"NAS": 0, "NGAP": 1, "RRC": 2, "F1AP": 3, "E1AP": 4, "XnAP": 5}
ROLE_IDS   = {
    "request": 0, "command": 0,            # initiating
    "response": 1, "accept": 1,
    "complete": 1, "result": 1,            # success
    "reject": 2, "failure": 2,             # failure
    "timeout": 3,                          # timeout
}

# ── Procedure-level feature names (Isolation Forest input) ────────────
PROC_FEATURE_NAMES = [
    "success_rate",          # 0-100
    "failure_rate",          # 0-100
    "attempt_share",         # this proc's attempts / all attempts
    "failure_count",         # raw failure count
    "cause_diversity",       # distinct cause codes / max(failure, 1)
    "top_cause_concentration",# most common cause / max(failure, 1)
    "timeout_ratio",         # timeout failures / max(failure, 1)
    "has_any_failure",       # 0 or 1
]

# ── Sequence feature names (LSTM input) ───────────────────────────────
SEQ_FEATURE_NAMES = [
    "layer_id",              # 0-5 (normalized to 0-1)
    "proc_id",               # procedure vocab ID (normalized to 0-1)
    "role_id",               # 0-3 (normalized to 0-1)
    "time_delta",            # seconds since previous event (capped + normalized)
]

WINDOW_SIZE = 10             # LSTM sliding window


def extract_procedure_features(parsed: Dict[str, Any]) -> Tuple[List[str], np.ndarray]:
    """
    Build feature matrix X where each row = one procedure.
    Returns (proc_names, X) where X.shape = (n_procs, n_features).
    """
    procedures = parsed.get("procedures", {})
    if not procedures:
        return [], np.empty((0, len(PROC_FEATURE_NAMES)))

    total_attempts = max(sum(s["attempts"] for s in procedures.values()), 1)

    proc_names, rows = [], []
    for name, stats in procedures.items():
        fail      = stats["failure"]
        causes    = stats.get("failure_causes", {})
        timeout_n = causes.get("timeout", 0)
        top_cause = max(causes.values()) if causes else 0

        rows.append([
            stats["success_rate"],
            100.0 - stats["success_rate"],
            stats["attempts"] / total_attempts,
            float(fail),
            len(causes) / max(fail, 1),
            top_cause / max(fail, 1),
            timeout_n / max(fail, 1),
            float(fail > 0),
        ])
        proc_names.append(name)

    return proc_names, np.array(rows, dtype=np.float32)


def extract_sequence_features(
    parsed: Dict[str, Any], window: int = WINDOW_SIZE
) -> Tuple[np.ndarray, List[Dict], Dict[str, int]]:
    """
    Build sliding-window sequence tensor from message_log.
    Returns:
      windows      — shape (n_windows, window, n_seq_features)
      window_meta  — list of dicts with context per window
      proc_vocab   — mapping of procedure name → integer ID
    """
    log = parsed.get("message_log", [])
    if len(log) < window + 1:
        return np.empty((0, window, len(SEQ_FEATURE_NAMES))), [], {}

    # Build procedure vocabulary
    proc_vocab: Dict[str, int] = {}
    for entry in log:
        p = entry.get("procedure", "unknown")
        if p not in proc_vocab:
            proc_vocab[p] = len(proc_vocab)
    n_procs = max(len(proc_vocab), 1)

    # Encode each event
    events = []
    prev_ts = log[0]["timestamp"]
    for entry in log:
        layer_id = LAYER_IDS.get(entry.get("layer", "NAS"), 0)
        proc_id  = proc_vocab.get(entry.get("procedure", ""), 0)
        role_id  = ROLE_IDS.get(entry.get("role", "request"), 0)
        dt       = min(entry["timestamp"] - prev_ts, 60.0)   # cap at 60s
        prev_ts  = entry["timestamp"]
        events.append([
            layer_id / 5.0,
            proc_id  / n_procs,
            role_id  / 3.0,
            dt       / 60.0,
        ])

    events = np.array(events, dtype=np.float32)

    # Slide window
    windows, meta = [], []
    for i in range(len(events) - window):
        windows.append(events[i : i + window])
        meta.append({
            "start_idx": i,
            "end_idx":   i + window,
            "layer":     log[i + window - 1].get("layer", "?"),
            "procedure": log[i + window - 1].get("procedure", "?"),
            "role":      log[i + window - 1].get("role", "?"),
            "ue_id":     log[i + window - 1].get("ue_id", "?"),
            "timestamp": log[i + window - 1].get("timestamp", 0),
        })

    return np.array(windows, dtype=np.float32), meta, proc_vocab
