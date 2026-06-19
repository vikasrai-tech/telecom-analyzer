"""
Shared topology/config for the 64-UE / 6-hour dataset (PCAP + KPI + Stats).

16 cells across 4 gNBs (4 cells each), 64 UEs (4 per cell):
  PCI_1  .. PCI_8   (gNB-1, gNB-2)  -> TDD  cells, DL capacity 1500 Mbps, UL 100 Mbps
  PCI_9  .. PCI_16  (gNB-3, gNB-4)  -> FDD  cells, DL capacity  100 Mbps, UL  50 Mbps

KPI and Stats generators both use this 6-hour window (08:00-14:00) and the
same 3 injected-anomaly windows so the two datasets can be cross-correlated
on (cell_id, time).
"""

from datetime import datetime

START      = datetime(2026, 6, 13, 8, 0, 0)   # 08:00
N_MINUTES  = 360                              # 6 hours @ 1-minute granularity

CELLS = [
    ("PCI_1",  "gNB-1", "TDD"), ("PCI_2",  "gNB-1", "TDD"),
    ("PCI_3",  "gNB-1", "TDD"), ("PCI_4",  "gNB-1", "TDD"),
    ("PCI_5",  "gNB-2", "TDD"), ("PCI_6",  "gNB-2", "TDD"),
    ("PCI_7",  "gNB-2", "TDD"), ("PCI_8",  "gNB-2", "TDD"),
    ("PCI_9",  "gNB-3", "FDD"), ("PCI_10", "gNB-3", "FDD"),
    ("PCI_11", "gNB-3", "FDD"), ("PCI_12", "gNB-3", "FDD"),
    ("PCI_13", "gNB-4", "FDD"), ("PCI_14", "gNB-4", "FDD"),
    ("PCI_15", "gNB-4", "FDD"), ("PCI_16", "gNB-4", "FDD"),
]

# Per-cell peak (busy-hour) channel capacity, Mbps
CAPACITY = {
    "TDD": {"dl": 1500.0, "ul": 100.0},
    "FDD": {"dl":  100.0, "ul":  50.0},
}

UE_PER_CELL = 4   # 16 cells x 4 = 64 UEs

# ── Shared anomaly windows (minute offsets from START) ──────────────────
# Congestion on a TDD cell: throughput/PRB/HO/RRC all degrade
ANOM_CONGESTION = {"cell": "PCI_3",  "start": 90,  "end": 150}   # 09:30-10:30

# Hardware/backhaul outage on an FDD cell: hard step-change collapse
ANOM_OUTAGE     = {"cell": "PCI_12", "start": 240, "end": 260}   # 12:00-12:20

# Slow drift on a TDD cell: HO success / latency degrade gradually
ANOM_DRIFT      = {"cell": "PCI_8",  "start": 300, "end": 360}   # 13:00-14:00


def diurnal_factor(minute: int) -> float:
    """Busy-period curve over the 6-hour window, peaking around 11:00 (mid-window)."""
    import numpy as np
    hour = 8 + minute / 60.0
    return 0.30 + 0.70 * np.sin(np.pi * (hour - 8) / 6.0) ** 1.3
