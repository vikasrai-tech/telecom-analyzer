"""
Anomaly Detector — currently a stub.
Week 6-8: Isolation Forest + LSTM Autoencoder
"""
from typing import List, Dict, Any


def detect_anomalies_stub(
    parsed: Dict[str, Any],
    detector: str = "Isolation Forest (stub)"
) -> List[Dict[str, Any]]:
    procedures = parsed.get("procedures", {})
    anomalies = []
    for proc_name, stats in procedures.items():
        if stats.get("failure", 0) > 0:
            anomalies.append({
                "type": f"{proc_name} failure spike",
                "severity": "Medium" if stats["failure"] > 1 else "Low",
                "score": round(stats["failure"] / max(stats["attempts"], 1), 2),
                "detector": detector,
                "evidence": (
                    f"{stats['failure']} failures; "
                    f"success rate {stats['success_rate']}%"
                ),
            })
    return anomalies