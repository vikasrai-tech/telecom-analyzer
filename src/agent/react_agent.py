"""Bounded ReAct-style root-cause agent.

Uses Ollama (reusing the same model-detection convention as
src/llm/explainer.py) when available, with a guardrail: any step whose
output can't be parsed as an Action or a Final Answer falls through to a
fixed deterministic tool-call order for the remaining steps, and a failed
Final Answer falls back to rule_based_root_cause(). This keeps a live demo
robust against a small local model (phi3:mini) occasionally not following
the expected format, while still doing genuine multi-step tool-assisted
reasoning rather than a single bigger prompt.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.llm.explainer import _detect_ollama_model
from src.orchestrator.event_router import EventRouter, _correlation_key
from src.agent import tools
from src.agent.rule_based import rule_based_root_cause
from src.agent.schemas import CausalHop, RootCauseResult

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 4

_TOOL_MENU = """You have these tools available:
  get_event_details(event_id)
  get_related_events(event_id)
  query_3gpp_spec(query)
  get_predictions_for_cell(cell_id)

At each step, respond with EXACTLY ONE of:
Action: tool_name(args)
Final Answer: {"root_cause": "...", "causal_chain": [{"event_id": "...", "role": "trigger|symptom|contributing_factor", "explanation": "..."}], "confidence": 0.0-1.0, "citations": [{"spec": "...", "section": "...", "quote": "..."}], "recommended_action": "..."}"""

_ACTION_RE = re.compile(r"Action:\s*(\w+)\((.*?)\)", re.DOTALL)
_FINAL_RE  = re.compile(r"Final Answer:\s*(\{.*\})", re.DOTALL)

# Deterministic fallback tool order used when a step's model output can't be parsed.
_FALLBACK_ORDER = ["get_event_details", "get_related_events", "query_3gpp_spec", "get_predictions_for_cell"]


def _dispatch_tool(name: str, arg: str, router: EventRouter) -> Any:
    arg = arg.strip().strip('"').strip("'")
    try:
        if name == "get_event_details":
            return tools.get_event_details(arg, router)
        if name == "get_related_events":
            return tools.get_related_events(arg, router)
        if name == "query_3gpp_spec":
            return tools.query_3gpp_spec(arg)
        if name == "get_predictions_for_cell":
            return tools.get_predictions_for_cell(arg, router)
    except Exception as e:
        logger.debug(f"[react_agent] tool {name}({arg}) failed: {e}")
    return None


def _build_prompt(
    correlated_group: List[Dict[str, Any]],
    predictions: List[Dict[str, Any]],
    scratchpad: str,
) -> str:
    events_desc = "\n".join(
        f"- event_id={e['event_id']} cell={e['cell_id']} source={e['source']} "
        f"layer={e['layer']} severity={e['severity']} category={e['category']} "
        f"evidence={e['evidence']}"
        for e in correlated_group
    )
    preds_desc = "\n".join(
        f"- {p.get('label', '?')} on {p.get('cell_id', '?')} predicted in "
        f"{p.get('lead_time_h', '?')}h (severity={p.get('severity', '?')})"
        for p in predictions
    ) or "(none)"

    return f"""You are a 5G network root-cause analysis agent. A group of anomalies was
flagged as correlated (same cell / bucket) across multiple detection sources.
Determine the causal chain: which event TRIGGERED the others, which are SYMPTOMS,
and which are CONTRIBUTING_FACTORs. Use the tools to gather more context before
answering, then give a Final Answer.

CORRELATED EVENTS:
{events_desc}

RELATED PREDICTIONS (forecast, not yet happened):
{preds_desc}

{_TOOL_MENU}

SCRATCHPAD SO FAR:
{scratchpad or "(nothing yet)"}

What is your next step?"""


def _validate_and_format(result: Dict[str, Any], model: str) -> Dict[str, Any]:
    """Validate the model's Final Answer against RootCauseResult's shape;
    raises if malformed so the caller falls back to the rule-based path."""
    if not result.get("root_cause") or not result.get("causal_chain"):
        raise ValueError("Final Answer missing required fields")

    chain = [
        CausalHop(
            event_id=h.get("event_id", ""),
            role=h.get("role", "symptom"),
            explanation=h.get("explanation", ""),
        )
        for h in result["causal_chain"]
    ]
    return RootCauseResult(
        root_cause=result["root_cause"],
        causal_chain=chain,
        confidence=float(result.get("confidence", 0.5)),
        citations=result.get("citations", []),
        recommended_action=result.get("recommended_action", ""),
        source=f"Ollama ({model}) + ReAct",
    ).as_dict()


def run_root_cause_agent(
    correlated_group: List[Dict[str, Any]],
    router: EventRouter,
    predictions: Optional[List[Dict[str, Any]]] = None,
    max_iterations: int = MAX_ITERATIONS,
) -> Dict[str, Any]:
    """
    Investigate one correlated event group. Runs a bounded ReAct loop
    against Ollama when available; falls back to rule_based_root_cause()
    when Ollama isn't running, or whenever the model's output can't be
    parsed at any step (guardrail — never hard-fails on a small-model
    hiccup).
    """
    predictions = predictions or []
    model = _detect_ollama_model()
    if not model:
        return rule_based_root_cause(correlated_group, predictions)

    scratchpad = ""
    for step in range(max_iterations):
        prompt = _build_prompt(correlated_group, predictions, scratchpad)
        try:
            import ollama
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2, "num_predict": 500},
            )
            raw = response.message.content.strip()
        except Exception as e:
            logger.warning(f"[react_agent] Ollama call failed at step {step}: {e}")
            break

        final_match = _FINAL_RE.search(raw)
        if final_match:
            try:
                parsed = json.loads(final_match.group(1))
                return _validate_and_format(parsed, model)
            except Exception as e:
                logger.debug(f"[react_agent] Final answer invalid: {e}")
                break  # fall through to rule-based below

        action_match = _ACTION_RE.search(raw)
        if action_match:
            tool_name, arg = action_match.group(1), action_match.group(2)
            observation = _dispatch_tool(tool_name, arg, router)
            scratchpad += f"\nStep {step + 1}: Action: {tool_name}({arg})\nObservation: {observation}\n"
            continue

        # Guardrail: couldn't parse an Action or Final Answer this step —
        # use a fixed deterministic tool order instead of aborting.
        fallback_tool = _FALLBACK_ORDER[step % len(_FALLBACK_ORDER)]
        first = correlated_group[0] if correlated_group else {}
        arg = {
            "get_event_details":       first.get("event_id", ""),
            "get_related_events":      first.get("event_id", ""),
            "query_3gpp_spec":         first.get("category", ""),
            "get_predictions_for_cell": first.get("cell_id", ""),
        }[fallback_tool]
        observation = _dispatch_tool(fallback_tool, arg, router)
        scratchpad += (
            f"\nStep {step + 1}: (unparsed model output — used deterministic fallback) "
            f"Action: {fallback_tool}({arg})\nObservation: {observation}\n"
        )

    logger.info("[react_agent] No valid Final Answer within max_iterations — falling back to rule-based")
    return rule_based_root_cause(correlated_group, predictions)


def analyze_root_cause(router: EventRouter, min_sources: int = 2) -> List[Dict[str, Any]]:
    """
    Public entry point. Groups correlated events using EventRouter's own
    correlation key (cell, or procedure bucket for PCAP events without a
    cell_id), runs the agent per group, and returns RootCauseResult dicts.
    """
    correlated = router.get_correlated(min_sources=min_sources)
    if not correlated:
        return []

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for ev in correlated:
        key = _correlation_key(ev)
        groups.setdefault(key, []).append(ev)

    results = []
    for group in groups.values():
        cell_id = group[0]["cell_id"]
        predictions = tools.get_predictions_for_cell(cell_id, router) if cell_id != "—" else []
        results.append(run_root_cause_agent(group, router, predictions=predictions))
    return results
