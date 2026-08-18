"""
Scenario-level / cell-level detection metrics.

IMPORTANT — scope of evaluation:
  - N=3 injected fault scenarios (congestion/outage/drift) in a controlled
    synthetic dataset.
  - Evaluation is at CELL level: a detection method "detects" a fault if it
    flags the fault cell (PCI_3, PCI_12, or PCI_8) as anomalous.
  - True Negatives = normal cells correctly not flagged.
  - This is NOT event-level precision/recall; individual anomaly rows are not
    compared against per-row ground truth timestamps.
  - N=3 is explicitly a dataset limitation that must be stated in any
    publication using these numbers.
"""

from typing import Any, Dict, Set


def compute_scenario_metrics(
    detected_cells: Set[str],
    fault_cells: Set[str],
    all_cells: Set[str],
) -> Dict[str, Any]:
    """
    Compute scenario-level (cell-level) detection metrics.

    Parameters
    ----------
    detected_cells : set
        Cells the detection method flagged as anomalous.
    fault_cells : set
        Ground-truth fault cells ({"PCI_3", "PCI_12", "PCI_8"}).
    all_cells : set
        All 16 cells in the dataset.

    Returns
    -------
    dict with TP, FP, FN, TN, precision, recall, f1, and a documentation note.

    Note: "scenario-level / cell-level detection (N=3 injected fault scenarios)"
    """
    normal_cells = all_cells - fault_cells

    tp = len(detected_cells & fault_cells)
    fp = len(detected_cells - fault_cells)
    fn = len(fault_cells - detected_cells)
    tn = len(normal_cells - detected_cells)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0 else 0.0
    )

    return {
        "TP":        tp,
        "FP":        fp,
        "FN":        fn,
        "TN":        tn,
        "precision": round(precision, 4),
        "recall":    round(recall, 4),
        "f1":        round(f1, 4),
        "detected_fault_cells":  sorted(detected_cells & fault_cells),
        "missed_fault_cells":    sorted(fault_cells - detected_cells),
        "false_positive_cells":  sorted(detected_cells - fault_cells),
        "evaluation_note": (
            "Scenario-level / cell-level detection. N=3 injected fault scenarios "
            "(congestion PCI_3, outage PCI_12, drift PCI_8) in a 16-cell synthetic "
            "dataset. This is a dataset limitation — recall/precision should not be "
            "extrapolated to real-world deployments without additional validation."
        ),
    }
