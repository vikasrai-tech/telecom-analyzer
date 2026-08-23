"""Data schemas for the LLM root-cause agent (Phase II)."""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class CausalHop:
    event_id: str
    role: str   # "trigger" | "symptom" | "contributing_factor"
    explanation: str

    def as_dict(self) -> Dict[str, Any]:
        return {"event_id": self.event_id, "role": self.role, "explanation": self.explanation}


@dataclass
class RootCauseResult:
    root_cause: str
    causal_chain: List[CausalHop]
    confidence: float
    citations: List[Dict[str, str]]   # [{spec, section, quote}]
    recommended_action: str
    source: str   # "Ollama (<model>) + ReAct" | "rule-based (Ollama unavailable)"
    cell_id: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "root_cause": self.root_cause,
            "causal_chain": [h.as_dict() for h in self.causal_chain],
            "confidence": round(self.confidence, 3),
            "citations": self.citations,
            "recommended_action": self.recommended_action,
            "source": self.source,
            "cell_id": self.cell_id,
        }
