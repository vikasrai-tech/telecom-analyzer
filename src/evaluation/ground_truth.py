"""
Ground truth for the 64-UE / 6-hour dataset.

Loaded from scripts/_ue64_config.py which is the authoritative source for
injected fault scenarios (PCI_3 congestion, PCI_12 outage, PCI_8 drift).

N=3 injected faults — this is explicitly a limitation of the dataset and must
be stated when reporting recall/precision numbers.
"""

from typing import Any, Dict, List, Set

# ── Fault scenarios (match _ue64_config.py exactly) ─────────────────────────
# Times converted from minute offsets to hour offsets for readability.
# start_minute=90 → start_hour=1.5 (relative to 08:00)

FAULT_SCENARIOS: List[Dict[str, Any]] = [
    {
        "scenario_id":      "congestion",
        "fault_type":       "congestion",
        "cell_id":          "PCI_3",
        "start_minute":     90,
        "end_minute":       150,
        "start_hour":       1.5,
        "end_hour":         2.5,
        "affected_domains": ["kpi", "stats"],
        "description": (
            "DL congestion on TDD cell PCI_3 (gNB-1). "
            "PRB utilisation exceeds 90%, throughput/HO/RRC degrade."
        ),
    },
    {
        "scenario_id":      "outage",
        "fault_type":       "outage",
        "cell_id":          "PCI_12",
        "start_minute":     240,
        "end_minute":       260,
        "start_hour":       4.0,
        "end_hour":         4.33,
        "affected_domains": ["kpi", "stats", "pcap"],
        "description": (
            "Hardware/backhaul outage on FDD cell PCI_12 (gNB-3). "
            "Hard step-change collapse in Cell_Availability, RACH, and NGAP procedures."
        ),
    },
    {
        "scenario_id":      "drift",
        "fault_type":       "drift",
        "cell_id":          "PCI_8",
        "start_minute":     300,
        "end_minute":       360,
        "start_hour":       5.0,
        "end_hour":         6.0,
        "affected_domains": ["kpi", "stats"],
        "description": (
            "Slow drift on TDD cell PCI_8 (gNB-2). "
            "Handover success rate and latency degrade gradually."
        ),
    },
]

# All 16 cells in the dataset
ALL_CELLS: Set[str] = {
    "PCI_1", "PCI_2", "PCI_3", "PCI_4",
    "PCI_5", "PCI_6", "PCI_7", "PCI_8",
    "PCI_9", "PCI_10", "PCI_11", "PCI_12",
    "PCI_13", "PCI_14", "PCI_15", "PCI_16",
}

FAULT_CELLS: Set[str] = {"PCI_3", "PCI_12", "PCI_8"}

# Normal (non-fault) cells
NORMAL_CELLS: Set[str] = ALL_CELLS - FAULT_CELLS


# ── Accessor helpers ──────────────────────────────────────────────────────────

def get_fault_cells() -> Set[str]:
    """Return the set of cells that have injected faults."""
    return FAULT_CELLS.copy()


def get_fault_cell_for_scenario(scenario_id: str) -> str:
    """Return the cell_id for a given scenario_id, or '' if not found."""
    for s in FAULT_SCENARIOS:
        if s["scenario_id"] == scenario_id:
            return s["cell_id"]
    return ""


def get_scenario(scenario_id: str) -> Dict[str, Any]:
    """Return full scenario dict or empty dict if not found."""
    for s in FAULT_SCENARIOS:
        if s["scenario_id"] == scenario_id:
            return s
    return {}
