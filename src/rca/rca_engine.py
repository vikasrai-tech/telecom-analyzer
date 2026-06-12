"""
RCA Engine — Root Cause Analysis for 5G Anomalies

Algorithm:
  1. Group anomalies by cell_id + 30-second time bucket
  2. Within each group, order anomalies by protocol stack depth (lowest layer first)
  3. Apply causal rules: if a lower-layer anomaly can explain higher-layer anomalies,
     form a causal chain and emit an RCAResult
  4. Unmatched anomalies get a single-event RCAResult with lower confidence

Input:  List of anomaly dicts (any mix of PCAP, KPI, stats sources)
Output: List[RCAResult] — one per identified root cause

RCAResult fields:
  root_cause_anomaly  — the anomaly identified as the root cause
  causal_chain        — ordered list [root → ... → effect]
  affected_anomalies  — all anomalies this root cause explains
  rule_name           — which causal rule fired (or "single_event")
  confidence          — float [0, 1]
  cell_id             — affected cell (or "unknown")
  layer_path          — human-readable layer chain string
  evidence_summary    — one-paragraph explanation
  recommendation      — engineer action
  spec_ref            — 3GPP spec reference
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .causal_graph import (
    CAUSAL_RULES,
    CausalRule,
    find_rules_for_root,
    layer_label,
    layer_rank,
    match_rule,
)

logger = logging.getLogger(__name__)

# Group anomalies within this many seconds into the same time bucket
TIME_BUCKET_SECONDS = 30

# Minimum anomalies for a causal group to be considered multi-cause
MIN_GROUP_SIZE_FOR_CAUSAL = 2


# ── Result model ──────────────────────────────────────────────────────

@dataclass
class RCAResult:
    root_cause_anomaly: Dict[str, Any]
    causal_chain: List[Dict[str, Any]]
    affected_anomalies: List[Dict[str, Any]]
    rule_name: str
    confidence: float
    cell_id: str
    layer_path: str
    evidence_summary: str
    recommendation: str
    spec_ref: str
    severity: str = "Medium"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "root_cause_type":  self.root_cause_anomaly.get("type", "Unknown"),
            "root_cause_layer": self.root_cause_anomaly.get("layer")
                                or self.root_cause_anomaly.get("source", "?"),
            "rule_name":        self.rule_name,
            "confidence":       round(self.confidence, 3),
            "severity":         self.severity,
            "cell_id":          self.cell_id,
            "layer_path":       self.layer_path,
            "affected_count":   len(self.affected_anomalies),
            "causal_chain":     [a.get("type", "?") for a in self.causal_chain],
            "evidence_summary": self.evidence_summary,
            "recommendation":   self.recommendation,
            "spec_ref":         self.spec_ref,
        }


# ── Helpers ───────────────────────────────────────────────────────────

def _cell_id(anomaly: dict) -> str:
    return str(anomaly.get("cell_id") or anomaly.get("cell") or "unknown")


def _time_bucket(anomaly: dict) -> str:
    """Coerce timestamp to a 30-second bucket string for grouping."""
    ts = anomaly.get("timestamp", "")
    if not ts or ts in ("trend", "N/A", ""):
        return "no_ts"
    try:
        # handles ISO strings: 2024-01-15T12:34:56 or 2024-01-15 12:34:56.789
        ts_clean = str(ts).replace("T", " ").split(".")[0]
        parts = ts_clean.split(":")
        if len(parts) >= 3:
            h, m, s = parts[0], parts[1], int(parts[2])
            bucket = (s // TIME_BUCKET_SECONDS) * TIME_BUCKET_SECONDS
            return f"{h}:{m}:{bucket:02d}"
    except Exception:
        pass
    return str(ts)[:16]  # minute-level bucket as fallback


def _group_anomalies(anomalies: List[dict]) -> Dict[str, List[dict]]:
    """Group anomalies by (cell_id, time_bucket)."""
    groups: Dict[str, List[dict]] = defaultdict(list)
    for a in anomalies:
        key = f"{_cell_id(a)}|{_time_bucket(a)}"
        groups[key].append(a)
    return groups


def _severity_from_chain(anomalies: List[dict]) -> str:
    ranks = {"Critical": 3, "High": 2, "Medium": 1, "Low": 0, "Clean": -1}
    top = max((ranks.get(a.get("severity", "Low"), 0) for a in anomalies), default=0)
    return {3: "Critical", 2: "High", 1: "Medium", 0: "Low"}.get(top, "Medium")


def _layer_path_str(chain: List[dict]) -> str:
    """'NAS → NGAP → KPI' style string from causal chain."""
    labels = []
    seen = set()
    for a in chain:
        lbl = layer_label(a)
        if lbl not in seen:
            seen.add(lbl)
            labels.append(lbl)
    return " → ".join(labels) if labels else "?"


def _build_evidence_summary(root: dict, rule: CausalRule, effects: List[dict]) -> str:
    root_type = root.get("type", "anomaly")
    root_ev   = root.get("evidence", "")
    effect_types = [e.get("type", "effect") for e in effects[:3]]
    lines = [
        f"Root cause identified at {layer_label(root)}: {root_type}.",
    ]
    if root_ev:
        lines.append(f"Evidence: {root_ev}")
    if effect_types:
        lines.append(
            f"This caused {len(effects)} downstream anomaly(ies): "
            + ", ".join(effect_types)
            + (f" (+{len(effects)-3} more)" if len(effects) > 3 else "")
            + "."
        )
    lines.append(f"Causal rule: {rule.description} [{rule.spec_ref}].")
    return " ".join(lines)


def _single_event_summary(anomaly: dict) -> str:
    return (
        f"Isolated anomaly at {layer_label(anomaly)}: {anomaly.get('type', 'Unknown')}. "
        f"Evidence: {anomaly.get('evidence', 'N/A')}. "
        "No correlated anomalies found in the same time window; "
        "this may be a standalone event or the only observable symptom."
    )


# ── Core analysis ─────────────────────────────────────────────────────

def _analyze_group(group: List[dict]) -> List[RCAResult]:
    """Apply causal rules to a co-located group of anomalies."""
    results: List[RCAResult] = []
    # Sort by layer rank ascending: lower layer = potential root cause
    sorted_group = sorted(group, key=lambda a: (layer_rank(a), a.get("score", 0)))
    assigned: set = set()  # indices already explained by a rule

    for root_idx, root in enumerate(sorted_group):
        if root_idx in assigned:
            continue
        matched_rules = find_rules_for_root(root)
        if not matched_rules:
            continue

        best_rule, base_conf = matched_rules[0]

        # Find effects: higher-layer anomalies this rule can propagate to
        effects = [
            a for i, a in enumerate(sorted_group)
            if i != root_idx
            and i not in assigned
            and (
                (a.get("layer") or a.get("source")) in best_rule.effect_layers
                or layer_rank(a) > layer_rank(root)
            )
        ]

        if not effects and len(group) < MIN_GROUP_SIZE_FOR_CAUSAL:
            continue

        # Confidence boost for corroborating evidence
        confidence = base_conf
        if len(effects) >= 3:
            confidence = min(confidence + 0.05, 0.98)
        if len(effects) >= 5:
            confidence = min(confidence + 0.03, 0.98)

        causal_chain = [root] + effects
        cell = _cell_id(root)
        explained_indices = {root_idx} | {
            sorted_group.index(e) for e in effects
        }
        assigned |= explained_indices

        results.append(RCAResult(
            root_cause_anomaly=root,
            causal_chain=causal_chain,
            affected_anomalies=effects,
            rule_name=best_rule.name,
            confidence=confidence,
            cell_id=cell,
            layer_path=_layer_path_str(causal_chain),
            evidence_summary=_build_evidence_summary(root, best_rule, effects),
            recommendation=best_rule.recommendation,
            spec_ref=best_rule.spec_ref,
            severity=_severity_from_chain(causal_chain),
        ))

    # Unassigned anomalies → single-event RCAResult
    for idx, anomaly in enumerate(sorted_group):
        if idx in assigned:
            continue
        # Try to find at least a matching rule for recommendation
        matched = find_rules_for_root(anomaly)
        rule = matched[0][0] if matched else CAUSAL_RULES[0]
        results.append(RCAResult(
            root_cause_anomaly=anomaly,
            causal_chain=[anomaly],
            affected_anomalies=[],
            rule_name="single_event",
            confidence=matched[0][1] * 0.6 if matched else 0.40,
            cell_id=_cell_id(anomaly),
            layer_path=layer_label(anomaly),
            evidence_summary=_single_event_summary(anomaly),
            recommendation=rule.recommendation if matched else "Investigate the anomaly manually.",
            spec_ref=rule.spec_ref if matched else "N/A",
            severity=anomaly.get("severity", "Medium"),
        ))

    return results


# ── Public API ────────────────────────────────────────────────────────

def analyze(anomalies: List[Dict[str, Any]]) -> List[RCAResult]:
    """
    Perform root cause analysis on a list of anomaly dicts.

    Args:
        anomalies: mixed list from PCAP detectors, KPI detectors, stats detectors.

    Returns:
        List[RCAResult] sorted by confidence descending.
    """
    if not anomalies:
        return []

    groups = _group_anomalies(anomalies)
    results: List[RCAResult] = []

    for group_key, group in groups.items():
        logger.debug(f"RCA group '{group_key}': {len(group)} anomalies")
        group_results = _analyze_group(group)
        results.extend(group_results)

    # Deduplicate: if the same root_cause_anomaly appears in multiple groups
    # (due to fallback timestamp bucketing), keep the highest-confidence one
    seen: Dict[str, RCAResult] = {}
    for r in results:
        key = r.root_cause_anomaly.get("type", "") + r.cell_id
        if key not in seen or r.confidence > seen[key].confidence:
            seen[key] = r

    final = sorted(seen.values(), key=lambda r: r.confidence, reverse=True)
    logger.info(f"RCA: {len(anomalies)} anomalies → {len(final)} root cause(s)")
    return final


def analyze_to_dict(anomalies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convenience wrapper — returns plain dicts instead of RCAResult objects."""
    return [r.as_dict() for r in analyze(anomalies)]
