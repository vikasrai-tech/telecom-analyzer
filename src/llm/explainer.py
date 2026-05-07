"""
LLM explainer — currently a stub.

Week 11-14 will replace this with:
  - Real RAG over 3GPP specs (FAISS + bge-small-en-v1.5)
  - Local Phi-3 Mini call via Ollama
  - Structured JSON output with hypothesis, citations, hints

For now we just return a plausible-looking explanation so the UI works.
"""

from typing import Dict, Any


def explain_anomaly_stub(anomaly: Dict[str, Any]) -> Dict[str, Any]:
    """Return a fake structured explanation."""
    return {
        "hypothesis": (
            f"The detected pattern '{anomaly['type']}' is consistent with "
            "intermittent core-network resource exhaustion or transient "
            "authentication-server unavailability during the observation window."
        ),
        "severity": anomaly["severity"],
        "citations": [
            {
                "spec": "TS 24.501",
                "section": "5.5.1.2",
                "quote": "5GMM cause #22 (Congestion) is sent when the network "
                         "rejects the registration due to congestion.",
            },
            {
                "spec": "TS 38.413",
                "section": "9.3.1.2",
                "quote": "Cause IE values for InitialContextSetup failures.",
            },
        ],
        "investigation_hints": [
            "Check AMF resource utilisation and recent change-management entries.",
            "Verify if related cells in the same TAC show similar failure patterns.",
            "Compare with baseline success rates from the previous 7 days.",
        ],
    }
