"""
Anomaly detector — currently a stub.

Week 6-8 will replace this with:
  - Isolation Forest on tabular features (per procedure success rates)
  - LSTM Autoencoder on time-windowed counter sequences
"""

from typing import List, Dict, Any


def detect_anomalies_stub(parsed: Dict[str, Any], detector: str) -> List[Dict[str, Any]]:
    """Return a small list of fake anomalies for UI demo."""
    return [
        {
            "type": "PDU_Session_Establishment failure spike",
            "severity": "Medium",
            "score": 0.82,
            "detector": detector,
            "evidence": "13 failures observed; baseline expects ≤ 4 over 4 hours",
        },
        {
            "type": "NAS_Registration auth-Failure cluster",
            "severity": "Low",
            "score": 0.61,
            "detector": detector,
            "evidence": "6 auth-Failure events in a 30-minute window",
        },
    ]
