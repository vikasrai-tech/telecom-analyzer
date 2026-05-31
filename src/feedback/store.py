"""
Engineer Feedback Store — Tier 5

Appends engineer verdicts on anomalies to a JSONL log.
Used for:
  - Model quality tracking (false positive / false negative rate)
  - Nightly retraining data (Phase II)
  - Dashboard feedback history

Schema per record:
  {
    "feedback_id":   str (uuid),
    "timestamp":     ISO str,
    "session_id":    str,
    "event_id":      str,          # from EventRecord
    "source":        pcap|stats|kpi,
    "anomaly_type":  str,
    "severity":      str,
    "detector":      str,
    "cell_id":       str,
    "verdict":       "correct" | "false_positive" | "uncertain",
    "comment":       str,          # optional engineer note
    "evidence":      str,
  }
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_STORE = Path("data/feedback/feedback_log.jsonl")


def _ensure_store(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()


def save_feedback(
    event_id:     str,
    source:       str,
    anomaly_type: str,
    severity:     str,
    detector:     str,
    cell_id:      str,
    evidence:     str,
    verdict:      str,                    # correct | false_positive | uncertain
    comment:      str = "",
    session_id:   str = "",
    store_path:   Path = DEFAULT_STORE,
) -> Dict[str, Any]:
    """Append one feedback record. Returns the saved record."""
    _ensure_store(store_path)
    record = {
        "feedback_id":  str(uuid.uuid4())[:12],
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "session_id":   session_id,
        "event_id":     event_id,
        "source":       source,
        "anomaly_type": anomaly_type,
        "severity":     severity,
        "detector":     detector,
        "cell_id":      cell_id,
        "verdict":      verdict,
        "comment":      comment,
        "evidence":     evidence[:200],
    }
    with open(store_path, "a") as f:
        f.write(json.dumps(record) + "\n")
    logger.info(f"[feedback] saved: {verdict} on {anomaly_type} ({event_id})")
    return record


def load_feedback(
    store_path: Path = DEFAULT_STORE,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Load all feedback records, newest first."""
    _ensure_store(store_path)
    records = []
    with open(store_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    records.reverse()  # newest first
    return records[:limit] if limit else records


def feedback_stats(store_path: Path = DEFAULT_STORE) -> Dict[str, Any]:
    """Aggregate statistics over all feedback — used for retraining decision."""
    records = load_feedback(store_path)
    if not records:
        return {
            "total": 0, "correct": 0, "false_positive": 0,
            "uncertain": 0, "precision": None,
            "by_detector": {}, "by_source": {},
        }

    verdicts = [r["verdict"] for r in records]
    correct   = verdicts.count("correct")
    fp        = verdicts.count("false_positive")
    uncertain = verdicts.count("uncertain")
    precision = round(correct / (correct + fp), 3) if (correct + fp) > 0 else None

    by_det: Dict[str, Dict[str, int]] = {}
    by_src: Dict[str, Dict[str, int]] = {}
    for r in records:
        d = r["detector"]
        s = r["source"]
        v = r["verdict"]
        by_det.setdefault(d, {"correct": 0, "false_positive": 0, "uncertain": 0})
        by_src.setdefault(s, {"correct": 0, "false_positive": 0, "uncertain": 0})
        by_det[d][v] = by_det[d].get(v, 0) + 1
        by_src[s][v] = by_src[s].get(v, 0) + 1

    return {
        "total":        len(records),
        "correct":      correct,
        "false_positive": fp,
        "uncertain":    uncertain,
        "precision":    precision,
        "by_detector":  by_det,
        "by_source":    by_src,
    }
