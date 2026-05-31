"""
Unified Telecom Analyzer — Event Router (Tier 3)

Responsibilities:
  1. Normalise anomalies from all 3 sources (PCAP / Stats / KPI) into a
     single EventRecord schema.
  2. Tag each event:
       source      — "pcap" | "stats" | "kpi"
       state       — "current" (anomaly now) | "predicted" (Phase II)
       lead_time_h — 0.0 for current; N hours ahead for predicted
  3. Cross-source correlation — same cell flagged by ≥ 2 sources in the
     same time window → higher confidence, merged CorrelatedEvent.
  4. Priority queue — events sorted by (severity, score, source_count).
  5. Event log — append-only list for the feedback loop (Tier 5).

Usage:
    from src.orchestrator.event_router import EventRouter

    router = EventRouter()
    router.ingest(pcap_anomalies,  source="pcap",  parsed_pcap)
    router.ingest(stats_anomalies, source="stats", parsed_stats)
    router.ingest(kpi_anomalies,   source="kpi",   parsed_kpi)

    events   = router.get_events()          # all events, sorted by priority
    corr     = router.get_correlated()      # cross-source confirmed events
    summary  = router.summary()             # counts by severity / source
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Severity ordering ─────────────────────────────────────────────────
SEV_RANK = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

# ── EventRecord schema ────────────────────────────────────────────────
# All fields are plain Python types (JSON-serialisable).

def _new_event(
    source: str,
    anomaly: Dict[str, Any],
    state: str = "current",
    lead_time_h: float = 0.0,
) -> Dict[str, Any]:
    """
    Build a normalised EventRecord from any anomaly dict.

    Handles the different field names used by the three detectors:
      PCAP:  type, procedure, layer, failure_causes, score
      Stats: label, category, cell_id, value, unit
      KPI:   label, category, cell_id, value, unit
    """
    # ── Common fields ─────────────────────────────────────────────────
    severity  = anomaly.get("severity", "Low")
    detector  = anomaly.get("detector", "unknown")
    evidence  = anomaly.get("evidence", "")
    score     = float(anomaly.get("score", 0.0))

    # ── Source-specific field extraction ─────────────────────────────
    if source == "pcap":
        category  = anomaly.get("type",      anomaly.get("label", ""))
        cell_id   = anomaly.get("cell_id",   "—")
        metric    = anomaly.get("procedure", "")
        layer     = anomaly.get("layer",     "")
        unit      = ""
        value     = None
    else:
        category  = anomaly.get("label",     anomaly.get("type", ""))
        cell_id   = str(anomaly.get("cell_id", "—"))
        metric    = anomaly.get("category",  "")
        layer     = source.upper()
        unit      = anomaly.get("unit", "")
        value     = anomaly.get("value")

    return {
        "event_id":               str(uuid.uuid4())[:12],
        "created_at":             datetime.now(timezone.utc).isoformat(),
        "source":                 source,            # pcap | stats | kpi
        "state":                  state,             # current | predicted
        "lead_time_h":            lead_time_h,       # 0 = now; N = N hrs ahead
        "severity":               severity,
        "category":               category,
        "cell_id":                cell_id,
        "metric":                 metric,
        "layer":                  layer,
        "value":                  value,
        "unit":                   unit,
        "evidence":               evidence,
        "detector":               detector,
        "score":                  score,
        # Correlation fields — filled in by the router
        "correlated_sources":     [],
        "correlation_confidence": 0.0,
        "raw_anomaly":            anomaly,
    }


def _correlation_key(event: Dict[str, Any]) -> str:
    """
    Correlation key = cell_id.
    Any two sources flagging the same cell are cross-source correlated.
    For PCAP events without a cell_id, also try procedure-level grouping.
    """
    cell = event["cell_id"]
    if cell and cell != "—":
        return cell

    # PCAP events often lack cell_id — group by broad procedure category
    cat = event["category"].lower()
    if any(k in cat for k in ("rrc",)):
        return "proc::rrc"
    if any(k in cat for k in ("nas", "registration", "auth", "pdu")):
        return "proc::nas"
    if any(k in cat for k in ("ngap", "context", "handover")):
        return "proc::ngap"
    return f"proc::{cat[:20]}"


# ── EventRouter ───────────────────────────────────────────────────────

class EventRouter:
    """
    Central event bus for the Unified Telecom Analyzer.

    Typical flow:
        router = EventRouter()
        router.ingest(pcap_anomalies,  source="pcap")
        router.ingest(stats_anomalies, source="stats")
        router.ingest(kpi_anomalies,   source="kpi")

        events      = router.get_events()
        correlated  = router.get_correlated()
    """

    def __init__(self, correlation_window_h: float = 1.0):
        self._events: List[Dict[str, Any]] = []
        self._correlation_window_h = correlation_window_h

    # ── Ingest ────────────────────────────────────────────────────────

    def ingest(
        self,
        anomalies: List[Dict[str, Any]],
        source: str,
        state: str = "current",
        lead_time_h: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Convert a list of raw anomalies into EventRecords and add to the log.
        Returns the new EventRecords added.
        """
        new_events = []
        for a in anomalies:
            ev = _new_event(source, a, state=state, lead_time_h=lead_time_h)
            self._events.append(ev)
            new_events.append(ev)
        logger.info(f"[router] Ingested {len(new_events)} events from source='{source}'")
        self._run_correlation()
        return new_events

    def ingest_predicted(
        self,
        anomalies: List[Dict[str, Any]],
        source: str,
        lead_time_h: float,
    ) -> List[Dict[str, Any]]:
        """Phase II entry point — predicted anomalies with lead time."""
        return self.ingest(anomalies, source=source,
                           state="predicted", lead_time_h=lead_time_h)

    # ── Correlation ───────────────────────────────────────────────────

    def _run_correlation(self) -> None:
        """
        Group events by (cell, category-bucket).
        If ≥ 2 different sources flag the same bucket:
          • Mark correlated_sources on all matching events
          • Compute confidence = num_sources / 3
        """
        from collections import defaultdict
        bucket_map: Dict[str, List[Dict]] = defaultdict(list)
        for ev in self._events:
            k = _correlation_key(ev)
            bucket_map[k].append(ev)

        for events_in_bucket in bucket_map.values():
            sources = list({ev["source"] for ev in events_in_bucket})
            if len(sources) < 2:
                # Reset if previously correlated (e.g., after re-ingest)
                for ev in events_in_bucket:
                    ev["correlated_sources"]     = []
                    ev["correlation_confidence"] = 0.0
                continue
            confidence = round(len(sources) / 3.0, 2)
            for ev in events_in_bucket:
                ev["correlated_sources"]     = [s for s in sources if s != ev["source"]]
                ev["correlation_confidence"] = confidence

    # ── Queries ───────────────────────────────────────────────────────

    def get_events(
        self,
        source: Optional[str] = None,
        state:  Optional[str] = None,
        min_severity: str = "Low",
    ) -> List[Dict[str, Any]]:
        """
        Return events sorted by priority (severity DESC, score DESC).
        Optional filters: source, state, min_severity.
        """
        min_rank = SEV_RANK.get(min_severity, 1)
        events = [
            ev for ev in self._events
            if SEV_RANK.get(ev["severity"], 0) >= min_rank
            and (source is None or ev["source"] == source)
            and (state  is None or ev["state"]  == state)
        ]
        return sorted(
            events,
            key=lambda e: (
                SEV_RANK.get(e["severity"], 0),
                len(e["correlated_sources"]),   # correlated events rank higher
                e["score"],
            ),
            reverse=True,
        )

    def get_correlated(self, min_sources: int = 2) -> List[Dict[str, Any]]:
        """Return only cross-source correlated events (≥ min_sources)."""
        return [
            ev for ev in self._events
            if len(ev["correlated_sources"]) >= min_sources - 1
        ]

    def get_by_cell(self, cell_id: str) -> List[Dict[str, Any]]:
        """All events for a specific cell, sorted by priority."""
        return sorted(
            [ev for ev in self._events if ev["cell_id"] == cell_id],
            key=lambda e: SEV_RANK.get(e["severity"], 0),
            reverse=True,
        )

    def summary(self) -> Dict[str, Any]:
        """High-level counts for the dashboard header."""
        total       = len(self._events)
        correlated  = len(self.get_correlated())
        predicted   = sum(1 for e in self._events if e["state"] == "predicted")
        current     = total - predicted

        by_sev = {s: 0 for s in ("Critical", "High", "Medium", "Low")}
        by_src = {"pcap": 0, "stats": 0, "kpi": 0}
        for ev in self._events:
            by_sev[ev["severity"]] = by_sev.get(ev["severity"], 0) + 1
            by_src[ev["source"]]   = by_src.get(ev["source"],   0) + 1

        top_cells: Dict[str, int] = {}
        for ev in self._events:
            top_cells[ev["cell_id"]] = top_cells.get(ev["cell_id"], 0) + 1
        top_cells = dict(sorted(top_cells.items(), key=lambda x: x[1], reverse=True)[:5])

        return {
            "total":          total,
            "current":        current,
            "predicted":      predicted,
            "correlated":     correlated,
            "by_severity":    by_sev,
            "by_source":      by_src,
            "top_cells":      top_cells,
        }

    def clear(self) -> None:
        self._events = []


# ── Module-level convenience ──────────────────────────────────────────

def route_events(
    pcap_anomalies:  Optional[List[Dict]] = None,
    stats_anomalies: Optional[List[Dict]] = None,
    kpi_anomalies:   Optional[List[Dict]] = None,
) -> EventRouter:
    """
    One-shot helper: build a router, ingest all three sources, return it.

    Example:
        router = route_events(
            pcap_anomalies=pcap_result["anomalies"],
            kpi_anomalies=kpi_result["anomalies"],
        )
        events = router.get_events()
    """
    router = EventRouter()
    if pcap_anomalies:
        router.ingest(pcap_anomalies,  source="pcap")
    if stats_anomalies:
        router.ingest(stats_anomalies, source="stats")
    if kpi_anomalies:
        router.ingest(kpi_anomalies,   source="kpi")
    return router
