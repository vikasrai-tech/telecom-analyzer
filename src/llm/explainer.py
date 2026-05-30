"""
LLM Explainer — RAG + Ollama with rule-based fallback.

Flow:
  1. Build query from anomaly details
  2. Retrieve top-5 relevant 3GPP spec chunks (FAISS)
  3. Call Ollama (phi3:mini) with RAG-augmented prompt
  4. If Ollama unavailable → rule-based explanation using retrieved chunks
  5. Return structured: {hypothesis, severity, citations, investigation_hints}
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Ollama model preference list ─────────────────────────────────────
_PREFERRED_MODELS = ["phi3:mini", "phi3", "phi3:3.8b", "llama3.2:1b",
                     "llama3.2:3b", "mistral:7b-instruct", "gemma2:2b"]

_ollama_model: Optional[str] = None   # cached after first successful call


def _detect_ollama_model() -> Optional[str]:
    """Return first available model from preference list, or None."""
    global _ollama_model
    if _ollama_model:
        return _ollama_model
    try:
        import ollama
        available = {m.model.split(":")[0] for m in ollama.list().models}
        for preferred in _PREFERRED_MODELS:
            base = preferred.split(":")[0]
            if base in available:
                _ollama_model = preferred
                logger.info(f"Ollama model selected: {preferred}")
                return preferred
        logger.info(f"No preferred model found. Available: {available}")
    except Exception as e:
        logger.warning(f"Ollama not reachable: {e}")
    return None


def _build_query(anomaly: Dict[str, Any]) -> str:
    """Build a natural-language query for RAG retrieval."""
    parts = [
        anomaly.get("type", ""),
        anomaly.get("procedure", ""),
        anomaly.get("layer", ""),
        anomaly.get("evidence", ""),
    ]
    causes = anomaly.get("failure_causes", {})
    if causes:
        top = max(causes, key=causes.get)
        parts.append(f"cause: {top}")
    return " ".join(p for p in parts if p)


def _build_prompt(anomaly: Dict[str, Any], chunks: List[Dict]) -> str:
    """Build the RAG-augmented prompt for the LLM."""
    cause_str = ""
    causes = anomaly.get("failure_causes", {})
    if causes:
        sorted_causes = sorted(causes.items(), key=lambda x: x[1], reverse=True)
        cause_str = ", ".join(f"{c}({n})" for c, n in sorted_causes[:4])

    spec_context = "\n\n".join(
        f"[{c['spec']} §{c['section']} — {c['topic']}]\n{c['text']}"
        for c in chunks[:5]
    )

    return f"""You are a 5G network expert. Analyze this telecom anomaly and explain it clearly.

ANOMALY:
- Type: {anomaly.get('type', '?')}
- Severity: {anomaly.get('severity', '?')}
- Layer: {anomaly.get('layer', '?')}
- Procedure: {anomaly.get('procedure', '?')}
- Evidence: {anomaly.get('evidence', '?')}
- Failure causes: {cause_str or 'none recorded'}
- Detector: {anomaly.get('detector', '?')}

RELEVANT 3GPP SPECIFICATIONS:
{spec_context}

Based on the anomaly and the 3GPP specifications, respond ONLY with a valid JSON object in this exact format:
{{
  "hypothesis": "One paragraph explaining the most likely root cause in plain English.",
  "citations": [
    {{"spec": "TS XX.XXX", "section": "X.X.X", "quote": "Short relevant quote or description."}}
  ],
  "investigation_hints": [
    "First thing to check.",
    "Second thing to check.",
    "Third thing to check."
  ]
}}"""


def _call_ollama(prompt: str, model: str) -> Optional[Dict]:
    """Call Ollama and parse JSON response."""
    try:
        import ollama
        logger.info(f"Calling Ollama ({model})...")
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2, "num_predict": 600},
        )
        raw = response.message.content.strip()

        # Extract JSON block if wrapped in markdown code fences
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            raw = match.group(1)
        else:
            # Find the first { ... } block
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]

        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"Ollama response not valid JSON: {e}")
    except Exception as e:
        logger.warning(f"Ollama call failed: {e}")
    return None


def _rule_based_explanation(
    anomaly: Dict[str, Any],
    chunks: List[Dict],
) -> Dict[str, Any]:
    """
    Structured explanation built from retrieved spec chunks.
    Used when Ollama is unavailable or returns bad JSON.
    Still far better than the old stub — uses real 3GPP content.
    """
    proc      = anomaly.get("procedure", "this procedure")
    layer     = anomaly.get("layer", "")
    severity  = anomaly.get("severity", "Medium")
    evidence  = anomaly.get("evidence", "")
    causes    = anomaly.get("failure_causes", {})

    # Pick most relevant chunk as the primary spec reference
    primary   = chunks[0] if chunks else {}

    # Build hypothesis from evidence + top cause
    top_cause = max(causes, key=causes.get) if causes else ""
    cause_ctx = {
        "congestion":                     "AMF or network overload (5GMM cause #22). Back-off T3502 applies.",
        "timeout":                        "No response received within timer window — likely N2/F1/E1 link latency or NF unavailability.",
        "auth-failure":                   "Authentication failed — check AUSF/UDM reachability and UE SIM/SUPI profile.",
        "semantically-incorrect-message": "Message encoding error — check 3GPP spec version compatibility between NFs.",
        "radio-connection-with-ue-lost":  "Radio Link Failure (RLF) — check coverage, DRX, and handover thresholds.",
        "radio-resources-not-available":  "Cell capacity exhausted — check PRB utilisation and scheduler configuration.",
        "procedure-cancelled":            "Resource unavailable at target NF — check gNB-DU/CU-UP capacity and health.",
        "user-inactivity":                "UE moved to idle — normal behaviour, verify inactivity timer config if excessive.",
        "ue-context-release":             "Context released prematurely — check bearer lifecycle and UPF session anchor.",
    }.get(top_cause, f"Investigate the {top_cause or 'reported'} failure cause at the {layer} layer.")

    hypothesis = (
        f"The {proc} anomaly (severity={severity}) shows {evidence}. "
        f"The dominant failure pattern is: {cause_ctx} "
        f"Based on {primary.get('spec', 'the 3GPP spec')}, "
        f"{primary.get('text', '')[:200].rstrip('.')}. "
        f"This warrants {'immediate' if severity in ('High','Critical') else 'scheduled'} investigation."
    )

    # Build citations from retrieved chunks
    citations = [
        {
            "spec":    c.get("spec", ""),
            "section": c.get("section", ""),
            "quote":   c.get("text", "")[:150].rstrip(".") + ".",
        }
        for c in chunks[:3]
        if c.get("spec")
    ]

    # Build investigation hints from top cause + layer
    layer_hints = {
        "NAS":  ["Check AMF process health and CPU/memory utilisation.",
                 "Inspect NAS trace on the affected UE SUPI.",
                 "Verify AUSF/UDM reachability from AMF."],
        "NGAP": ["Check N2 SCTP association status between gNB and AMF.",
                 "Review AMF capacity — active UE context count vs limit.",
                 "Compare with baseline success rate from last 7 days."],
        "RRC":  ["Check DL RSRP and SINR for affected cells.",
                 "Review gNB RRC log for reject causes and waiting times.",
                 "Verify cell load — PRB utilisation at time of failures."],
        "F1AP": ["Verify F1 SCTP link between gNB-DU and gNB-CU-CP.",
                 "Check gNB-DU hardware alarms and resource counters.",
                 "Review DU software version for known F1AP bugs."],
        "E1AP": ["Check E1 SCTP link between gNB-CU-CP and gNB-CU-UP.",
                 "Inspect gNB-CU-UP memory usage and GTP tunnel table.",
                 "Verify CU-UP software stability — check restart counters."],
        "XnAP": ["Verify Xn SCTP association between the two gNBs.",
                 "Check target gNB capacity — PRB and context count.",
                 "Review A3 offset and TTT parameters for handover triggers."],
    }.get(layer, ["Enable detailed tracing on the affected network function.",
                  "Collect protocol logs covering the failure window.",
                  "Compare with healthy cells in the same cluster."])

    cause_hints = {
        "congestion": "Check AMF/SMF/UPF CPU and memory — scale out if > 80% sustained.",
        "timeout":    "Capture N2/F1/E1 SCTP traffic — look for retransmissions or connection resets.",
        "auth-failure": "Verify HSS/AUSF responds within 2s — check AUSF latency KPI.",
        "radio-resources-not-available": "Review PRB utilisation trend — add capacity or activate load-balancing.",
        "procedure-cancelled": "Check gNB-DU/CU-UP process restart logs for crash indicators.",
    }.get(top_cause, "Analyse failure cause distribution for patterns.")

    hints = layer_hints[:2] + [cause_hints, "Compare anomalous cell/procedure with healthy peer group."]

    return {
        "hypothesis":          hypothesis,
        "severity":            severity,
        "citations":           citations,
        "investigation_hints": hints,
        "source":              "rule-based (Ollama not available)",
    }


# ── Public API ────────────────────────────────────────────────────────

def explain_anomaly(anomaly: Dict[str, Any], top_k: int = 5) -> Dict[str, Any]:
    """
    Main entry point.
    Returns {hypothesis, severity, citations, investigation_hints, source}.
    """
    from src.rag.retriever import retrieve

    query  = _build_query(anomaly)
    chunks = retrieve(query, top_k=top_k)
    logger.info(f"Retrieved {len(chunks)} spec chunks for query: {query[:80]}")

    # Try Ollama first
    model = _detect_ollama_model()
    if model:
        prompt = _build_prompt(anomaly, chunks)
        result = _call_ollama(prompt, model)
        if result:
            result.setdefault("severity", anomaly.get("severity", "?"))
            result["source"] = f"Ollama ({model}) + RAG"
            # Ensure citations include spec/section if model returned minimal info
            if not result.get("citations") and chunks:
                result["citations"] = [
                    {"spec": c["spec"], "section": c["section"],
                     "quote": c["text"][:120] + "..."}
                    for c in chunks[:2]
                ]
            return result

    # Fallback: rule-based with retrieved spec chunks
    logger.info("Ollama unavailable — using rule-based explanation with RAG context")
    return _rule_based_explanation(anomaly, chunks)


def explain_anomaly_stub(anomaly: Dict[str, Any]) -> Dict[str, Any]:
    """
    Backward-compatible wrapper — now calls the real explainer.
    Old stub behaviour is gone.
    """
    return explain_anomaly(anomaly)


def ollama_status() -> Dict[str, Any]:
    """Return Ollama availability info for the dashboard status panel."""
    model = _detect_ollama_model()
    if model:
        return {"available": True, "model": model, "mode": "LLM + RAG"}
    try:
        import ollama
        models = ollama.list().models
        if models:
            names = [m.model for m in models]
            return {"available": False, "mode": "rule-based",
                    "message": f"Ollama running but no preferred model. Pull one of: "
                               f"{', '.join(_PREFERRED_MODELS[:3])}",
                    "available_models": names}
        return {"available": False, "mode": "rule-based",
                "message": f"Ollama running but no models pulled. Run: ollama pull phi3:mini"}
    except Exception:
        return {"available": False, "mode": "rule-based",
                "message": "Ollama not running. Install from ollama.com or run: ollama serve"}
