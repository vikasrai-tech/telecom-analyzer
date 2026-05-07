"""
PCAP parser — currently a stub.

In Week 2-3 this will be replaced with a real implementation using
pyshark/tshark that:
  1. Parses NGAP, NAS, RRC messages
  2. Correlates request/response by transaction ID
  3. Computes per-procedure success and failure counts with cause codes

For now it returns plausible dummy data so the UI can be exercised.
"""

from typing import Dict, Any


def parse_pcap_stub(filename: str) -> Dict[str, Any]:
    """Return fake but realistic PCAP analysis output."""
    return {
        "filename": filename,
        "total_events": 14_287,
        "duration_seconds": 14_400,  # 4 hours
        "procedures": {
            "RRC_Setup": {
                "attempts": 1248,
                "success": 1225,
                "failure": 23,
                "success_rate": 98.16,
                "failure_causes": {
                    "rrc-Reject": 18,
                    "timer-T300-Expired": 5,
                },
            },
            "NGAP_InitialContextSetup": {
                "attempts": 1225,
                "success": 1219,
                "failure": 6,
                "success_rate": 99.51,
                "failure_causes": {
                    "user-Inactivity": 4,
                    "radio-Connection-With-UE-Lost": 2,
                },
            },
            "NAS_Registration": {
                "attempts": 1107,
                "success": 1098,
                "failure": 9,
                "success_rate": 99.19,
                "failure_causes": {
                    "auth-Failure": 6,
                    "security-Mode-Reject": 3,
                },
            },
            "PDU_Session_Establishment": {
                "attempts": 1098,
                "success": 1085,
                "failure": 13,
                "success_rate": 98.82,
                "failure_causes": {
                    "insufficient-Resources": 9,
                    "ue-Authentication-Failed": 4,
                },
            },
        },
    }
