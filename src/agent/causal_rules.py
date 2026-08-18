"""
Protocol-Stack Event Ranking Engine — 5G Causal Rules

Ported and adapted from a prior Phase II attempt (git commit 6851f89,
src/rca/causal_graph.py) that was built and then reverted the same day to
keep the repo at a clean "Phase I complete" state — not because the
causal-rule content was wrong. Adapted here to operate on EventRouter's
normalized EventRecord fields (`layer`, `category`, `metric`, `source`)
instead of the old raw per-detector anomaly dict fields (`type`, `kpi`,
`procedure`); real 3GPP citations for each rule now come from a live RAG
retrieval in rule_based.py rather than the old code's hardcoded
`spec_ref` string (kept below only as a fallback reference).

Layer ordering (lowest = root, highest = symptom):
  0  PHY/L1       — physical radio (BLER, SNR, RSRP)
  1  MAC/RLC/PDCP — L2 scheduling (HARQ, PDCP drops) / generic stats
  2  RRC           — radio connection (Setup, Reconfig, Release)
  3  F1AP          — DU<->CU control plane
  4  E1AP          — CU-CP<->CU-UP bearer control
  5  XNAP          — inter-gNB handover
  6  NGAP          — gNB<->AMF (N2 interface)
  7  NAS           — UE<->AMF (5GMM/5GSM)
  8  KPI           — aggregate network KPIs
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# ── Layer registry ────────────────────────────────────────────────────

LAYER_RANK: Dict[str, int] = {
    "PHY":   0,
    "L1":    0,
    "MAC":   1,
    "RLC":   1,
    "PDCP":  1,
    "L2":    1,
    "STATS": 1,   # stats source default when no PHY-ish keyword matches
    "RRC":   2,
    "F1AP":  3,
    "E1AP":  4,
    "XNAP":  5,
    "NGAP":  6,
    "NAS":   7,
    "KPI":   8,
    "?":     5,   # unknown -> mid-stack
}

LAYER_LABELS: Dict[str, str] = {
    "PHY":   "Physical Layer (RF)",
    "L1":    "Physical Layer (RF)",
    "MAC":   "MAC/RLC/PDCP (L2)",
    "RLC":   "MAC/RLC/PDCP (L2)",
    "PDCP":  "MAC/RLC/PDCP (L2)",
    "L2":    "MAC/RLC/PDCP (L2)",
    "STATS": "DU/CU Statistics (L2)",
    "RRC":   "RRC (TS 38.331)",
    "F1AP":  "F1AP (TS 38.473)",
    "E1AP":  "E1AP (TS 38.463)",
    "XNAP":  "XnAP (TS 38.423)",
    "NGAP":  "NGAP (TS 38.413)",
    "NAS":   "NAS (TS 24.501)",
    "KPI":   "KPI (aggregate)",
}

_PHY_KEYWORDS = ("bler", "snr", "rsrp", "rsrq", "pusch", "pucch", "cqi")
_MAC_KEYWORDS = ("harq", "pdcp", "rlc", "prb", "sched", "buffer", "retrans")


def layer_rank(event: Dict[str, Any]) -> int:
    """Return the protocol-stack rank of an EventRecord (lower = deeper)."""
    layer = str(event.get("layer") or event.get("source") or "?").upper()
    if layer in ("STATS", "KPI"):
        text = f"{event.get('category', '')} {event.get('metric', '')}".lower()
        if any(k in text for k in _PHY_KEYWORDS):
            return LAYER_RANK["PHY"]
        if layer == "KPI" and not any(k in text for k in _MAC_KEYWORDS):
            return LAYER_RANK["KPI"]
        return LAYER_RANK["MAC"]
    return LAYER_RANK.get(layer, 5)


def layer_label(event: Dict[str, Any]) -> str:
    layer = str(event.get("layer") or event.get("source") or "?").upper()
    return LAYER_LABELS.get(layer, layer)


# ── Causal rule definitions ───────────────────────────────────────────

@dataclass
class CausalRule:
    name: str
    description: str
    root_layer: str          # layer of the root cause (key into LAYER_RANK)
    effect_layers: List[str] # layers this cause can propagate to
    keywords: List[str]      # matched against category/evidence/metric text
    confidence: float        # base confidence [0, 1]
    spec_ref: str            # 3GPP spec reference (fallback if RAG retrieval is empty)
    recommendation: str


CAUSAL_RULES: List[CausalRule] = [
    CausalRule(
        name="L1_radio_degradation",
        description="RF/physical layer degradation causing RRC failures and cascading up.",
        root_layer="PHY",
        effect_layers=["RRC", "NGAP", "NAS", "KPI"],
        keywords=["bler", "snr", "rsrp", "rsrq", "cqi", "radio", "rf", "signal"],
        confidence=0.88,
        spec_ref="TS 38.331 §5.3.1",
        recommendation=(
            "Check UE RF conditions: RSRP < -110 dBm or SINR < 0 dB indicates coverage hole. "
            "Review antenna tilt, TX power, and inter-cell interference (ICIC). "
            "Consider adding a relay or small cell."
        ),
    ),
    CausalRule(
        name="L2_scheduling_issue",
        description="MAC/HARQ/PDCP layer errors causing throughput degradation and KPI drops.",
        root_layer="MAC",
        effect_layers=["RRC", "KPI"],
        keywords=["harq", "pdcp", "rlc", "scheduling", "sched", "buffer", "retransmission", "drop"],
        confidence=0.82,
        spec_ref="TS 38.321 §5.4",
        recommendation=(
            "Check HARQ retransmission rate (>10% indicates poor link quality). "
            "Review DL/UL scheduling algorithm and PRB utilisation. "
            "Inspect PDCP discard timer and buffer status reports."
        ),
    ),
    CausalRule(
        name="RRC_setup_failure",
        description="RRC connection setup failures causing NGAP and NAS procedure failures.",
        root_layer="RRC",
        effect_layers=["NGAP", "NAS", "KPI"],
        keywords=["rrc", "setup", "reconfig", "release", "connection"],
        confidence=0.80,
        spec_ref="TS 38.331 §5.3.3",
        recommendation=(
            "Check RRC Setup Failure cause IE. Common causes: "
            "radio link failure (check BLER), resource unavailability (check PRB usage), "
            "or security failure (check RRC integrity keys). "
            "Review gNB RRC timer T300/T301 configuration."
        ),
    ),
    CausalRule(
        name="F1AP_context_failure",
        description="F1AP DU<->CU-CP context setup failure causing NGAP failures.",
        root_layer="F1AP",
        effect_layers=["NGAP", "NAS"],
        keywords=["f1ap", "ue context", "f1", "du", "cu"],
        confidence=0.78,
        spec_ref="TS 38.473 §8.3",
        recommendation=(
            "Check F1AP UE Context Setup Failure cause. "
            "Verify F1 interface connectivity (SCTP association). "
            "Inspect DU cell capacity and resource availability. "
            "Check gNB-DU software version compatibility with gNB-CU."
        ),
    ),
    CausalRule(
        name="NGAP_overload",
        description="AMF overload or N2 interface congestion causing NAS registration rejections.",
        root_layer="NGAP",
        effect_layers=["NAS", "KPI"],
        keywords=["overload", "congestion", "amf", "ngap", "n2", "cause 22", "#22", "overload start"],
        confidence=0.90,
        spec_ref="TS 38.413 §8.7 / TS 24.501 §5GMM cause #22",
        recommendation=(
            "AMF is overloaded. Immediate actions: "
            "1. Check AMF CPU/memory utilisation. "
            "2. Enable AMF load balancing across instances. "
            "3. Review NGAP OVERLOAD_START restriction level. "
            "4. UEs will back off using T3502 (12 min) — monitor re-registration rate."
        ),
    ),
    CausalRule(
        name="authentication_failure",
        description="NAS authentication or security mode failures.",
        root_layer="NAS",
        effect_layers=["KPI"],
        keywords=["auth", "security mode", "authentication", "5gmm cause #20", "mac failure"],
        confidence=0.85,
        spec_ref="TS 24.501 §5.4.1 / §5.4.2",
        recommendation=(
            "Authentication failures indicate SIM/USIM or AMF key issues. "
            "Check: UE subscription in UDM/AUSF, NAS security algorithms, "
            "and AMF key generation. Replay attacks produce MAC failure (#20)."
        ),
    ),
    CausalRule(
        name="handover_failure",
        description="XnAP/inter-gNB handover failure causing RRC release and NAS re-registration.",
        root_layer="XNAP",
        effect_layers=["RRC", "NGAP", "NAS"],
        keywords=["handover", "xnap", "xn", "ho failure", "mobility", "a3 event"],
        confidence=0.80,
        spec_ref="TS 38.423 §8.3 / TS 38.331 §5.4.2",
        recommendation=(
            "Handover failure detected. Check: "
            "A3 event offset and TTT (too aggressive -> ping-pong, too conservative -> RLF). "
            "Xn interface SCTP connectivity. "
            "Target cell admission control configuration."
        ),
    ),
    CausalRule(
        name="bearer_setup_failure",
        description="E1AP CU-CP<->CU-UP bearer or PDU session setup failure.",
        root_layer="E1AP",
        effect_layers=["NGAP", "NAS", "KPI"],
        keywords=["e1ap", "bearer", "pdu session", "cu-up", "cu-cp", "drb"],
        confidence=0.78,
        spec_ref="TS 38.463 §8.3",
        recommendation=(
            "E1AP bearer setup failed. Check: "
            "CU-UP resource availability (GTP tunnel quota). "
            "E1 interface SCTP association. "
            "QoS parameter mismatch between CU-CP and CU-UP."
        ),
    ),
]


# ── Rule matching ─────────────────────────────────────────────────────

def match_rule(event: Dict[str, Any], rule: CausalRule) -> bool:
    """Check if an EventRecord matches a causal rule's root-cause pattern."""
    # failure_causes is the detector's structured {cause_name: count} map —
    # always populated, unlike `evidence` which only names the dominant
    # cause once its concentration passes the detector's own display
    # threshold. Include every cause name here so keyword matching isn't
    # at the mercy of that threshold.
    failure_causes = (event.get("raw_anomaly") or {}).get("failure_causes") or {}
    text = " ".join(str(x) for x in (
        event.get("category", ""),
        event.get("evidence", ""),
        event.get("metric", ""),
        event.get("layer", ""),
        event.get("source", ""),
        " ".join(failure_causes.keys()),
    )).lower()
    layer = str(event.get("layer") or event.get("source") or "?").upper()
    layer_matches = (
        layer == rule.root_layer
        or layer_rank(event) == LAYER_RANK.get(rule.root_layer, -1)
    )
    keyword_matches = any(kw in text for kw in rule.keywords)
    return layer_matches or keyword_matches


def find_rules_for_root(event: Dict[str, Any]) -> List[Tuple[CausalRule, float]]:
    """Return (rule, confidence) pairs where this event is a plausible root cause,
    sorted by confidence descending."""
    results = [(rule, rule.confidence) for rule in CAUSAL_RULES if match_rule(event, rule)]
    results.sort(key=lambda x: x[1], reverse=True)
    return results
