"""
Tests for src/evaluation/ module.

Covers:
  - ground_truth.py: FAULT_SCENARIOS has 3 items; accessors work
  - detection_metrics.py: compute_scenario_metrics with known inputs
  - correlation_metrics.py: output structure
"""

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── ground_truth.py tests ─────────────────────────────────────────────────────

class TestGroundTruth:
    def test_fault_scenarios_count(self):
        from src.evaluation.ground_truth import FAULT_SCENARIOS
        assert len(FAULT_SCENARIOS) == 3

    def test_fault_scenarios_ids(self):
        from src.evaluation.ground_truth import FAULT_SCENARIOS
        ids = {s["scenario_id"] for s in FAULT_SCENARIOS}
        assert ids == {"congestion", "outage", "drift"}

    def test_fault_cells_match_scenarios(self):
        from src.evaluation.ground_truth import FAULT_SCENARIOS, FAULT_CELLS
        scenario_cells = {s["cell_id"] for s in FAULT_SCENARIOS}
        assert scenario_cells == FAULT_CELLS

    def test_all_cells_count(self):
        from src.evaluation.ground_truth import ALL_CELLS
        assert len(ALL_CELLS) == 16

    def test_normal_cells(self):
        from src.evaluation.ground_truth import NORMAL_CELLS, ALL_CELLS, FAULT_CELLS
        assert len(NORMAL_CELLS) == 13
        assert NORMAL_CELLS == ALL_CELLS - FAULT_CELLS
        assert NORMAL_CELLS.isdisjoint(FAULT_CELLS)

    def test_get_fault_cells(self):
        from src.evaluation.ground_truth import get_fault_cells, FAULT_CELLS
        assert get_fault_cells() == FAULT_CELLS

    def test_get_fault_cell_for_scenario(self):
        from src.evaluation.ground_truth import get_fault_cell_for_scenario
        assert get_fault_cell_for_scenario("congestion") == "PCI_3"
        assert get_fault_cell_for_scenario("outage")     == "PCI_12"
        assert get_fault_cell_for_scenario("drift")      == "PCI_8"
        assert get_fault_cell_for_scenario("nonexistent") == ""

    def test_scenario_minute_ranges(self):
        from src.evaluation.ground_truth import FAULT_SCENARIOS
        for s in FAULT_SCENARIOS:
            assert s["start_minute"] < s["end_minute"]
            assert s["start_minute"] >= 0
            assert s["end_minute"] <= 360  # 6-hour window

    def test_affected_domains(self):
        from src.evaluation.ground_truth import FAULT_SCENARIOS, get_scenario
        outage = get_scenario("outage")
        assert "pcap" in outage["affected_domains"]
        congestion = get_scenario("congestion")
        assert "kpi" in congestion["affected_domains"]


# ── detection_metrics.py tests ────────────────────────────────────────────────

class TestDetectionMetrics:
    """Tests for compute_scenario_metrics with known inputs."""

    def _metrics(self, detected, fault, all_c):
        from src.evaluation.detection_metrics import compute_scenario_metrics
        return compute_scenario_metrics(
            detected_cells=set(detected),
            fault_cells=set(fault),
            all_cells=set(all_c),
        )

    def test_perfect_detection(self):
        """All 3 faults detected, no false positives."""
        all_c = {f"C{i}" for i in range(6)}
        fault = {"C0", "C1", "C2"}
        m = self._metrics(fault, fault, all_c)
        assert m["TP"] == 3
        assert m["FP"] == 0
        assert m["FN"] == 0
        assert m["TN"] == 3
        assert m["precision"] == 1.0
        assert m["recall"]    == 1.0
        assert m["f1"]        == 1.0

    def test_no_detection(self):
        """Nothing detected."""
        all_c = {f"C{i}" for i in range(6)}
        fault = {"C0", "C1", "C2"}
        m = self._metrics(set(), fault, all_c)
        assert m["TP"] == 0
        assert m["FN"] == 3
        assert m["TN"] == 3
        assert m["recall"]    == 0.0
        assert m["precision"] == 0.0
        assert m["f1"]        == 0.0

    def test_partial_detection(self):
        """2 of 3 faults detected, 1 false positive."""
        all_c = {f"C{i}" for i in range(6)}
        fault = {"C0", "C1", "C2"}
        detected = {"C0", "C1", "C5"}  # 2 TP, 1 FP, 1 FN
        m = self._metrics(detected, fault, all_c)
        assert m["TP"] == 2
        assert m["FP"] == 1
        assert m["FN"] == 1
        assert m["TN"] == 2
        assert abs(m["precision"] - 2/3) < 0.001
        assert abs(m["recall"]    - 2/3) < 0.001

    def test_f1_zero_denominator(self):
        """TP=0 and FP=0: precision undefined, F1 = 0."""
        all_c = {"C0", "C1", "C2", "C3"}
        fault = {"C0", "C1"}
        m = self._metrics(set(), fault, all_c)
        assert m["f1"] == 0.0

    def test_output_structure(self):
        """Result dict has all required keys."""
        from src.evaluation.detection_metrics import compute_scenario_metrics
        m = compute_scenario_metrics({"A"}, {"A", "B"}, {"A", "B", "C", "D"})
        required = {"TP", "FP", "FN", "TN", "precision", "recall", "f1",
                    "detected_fault_cells", "missed_fault_cells",
                    "false_positive_cells", "evaluation_note"}
        assert required.issubset(m.keys())

    def test_evaluation_note_mentions_limitation(self):
        from src.evaluation.detection_metrics import compute_scenario_metrics
        m = compute_scenario_metrics(set(), {"A"}, {"A", "B"})
        note = m["evaluation_note"].lower()
        assert "n=3" in note or "limitation" in note

    def test_real_ground_truth_cells(self):
        """Sanity check with actual fault/all_cells from ground_truth.py."""
        from src.evaluation.ground_truth import FAULT_CELLS, ALL_CELLS
        m = self._metrics(FAULT_CELLS, FAULT_CELLS, ALL_CELLS)
        assert m["TP"] == 3
        assert m["TN"] == 13
        assert m["f1"] == 1.0


# ── correlation_metrics.py tests ──────────────────────────────────────────────

class TestCorrelationMetrics:
    """Tests for compute_correlation_assignment_rate output structure."""

    def _make_router(self, kpi_anoms, stats_anoms):
        from src.orchestrator.event_router import EventRouter
        r = EventRouter()
        r.ingest(kpi_anoms, source="kpi")
        r.ingest(stats_anoms, source="stats")
        return r

    def _mock_anomaly(self, cell_id="PCI_1", severity="High"):
        return {
            "cell_id":    cell_id,
            "severity":   severity,
            "label":      "Test KPI",
            "category":   "Test",
            "value":      10.0,
            "unit":       "%",
            "evidence":   "test evidence",
            "detector":   "Threshold",
            "score":      1.0,
        }

    def test_output_has_required_keys(self):
        from src.evaluation.correlation_metrics import compute_correlation_assignment_rate
        router = self._make_router([], [])
        result = compute_correlation_assignment_rate(router)
        required = {"metric_name", "note", "total_events", "clustered_events",
                    "single_source_events", "assignment_rate_pct", "by_source"}
        assert required.issubset(result.keys())

    def test_empty_router(self):
        from src.evaluation.correlation_metrics import compute_correlation_assignment_rate
        router = self._make_router([], [])
        result = compute_correlation_assignment_rate(router)
        assert result["total_events"] == 0
        assert result["assignment_rate_pct"] == 0.0

    def test_metric_name_is_not_accuracy(self):
        from src.evaluation.correlation_metrics import compute_correlation_assignment_rate
        router = self._make_router([], [])
        result = compute_correlation_assignment_rate(router)
        assert "accuracy" not in result["metric_name"].lower()
        assert "assignment" in result["metric_name"].lower()

    def test_note_mentions_not_precision_recall(self):
        from src.evaluation.correlation_metrics import compute_correlation_assignment_rate
        router = self._make_router([], [])
        result = compute_correlation_assignment_rate(router)
        note = result["note"].lower()
        assert "not" in note
        assert ("precision" in note or "recall" in note)

    def test_cross_source_events_counted(self):
        """Events from both KPI and Stats on same cell should be correlated."""
        from src.evaluation.correlation_metrics import compute_correlation_assignment_rate
        kpi_anoms   = [self._mock_anomaly("PCI_3")]
        stats_anoms = [self._mock_anomaly("PCI_3")]
        router = self._make_router(kpi_anoms, stats_anoms)
        result = compute_correlation_assignment_rate(router)
        # Both events share PCI_3 across two sources — both should be clustered
        assert result["total_events"] == 2
        assert result["clustered_events"] == 2
        assert result["assignment_rate_pct"] == 100.0

    def test_single_source_not_clustered(self):
        """Events from only one source on different cells — no cross-source correlation."""
        from src.evaluation.correlation_metrics import compute_correlation_assignment_rate
        kpi_anoms = [self._mock_anomaly("PCI_1"), self._mock_anomaly("PCI_2")]
        router = self._make_router(kpi_anoms, [])
        result = compute_correlation_assignment_rate(router)
        assert result["total_events"] == 2
        assert result["clustered_events"] == 0
        assert result["assignment_rate_pct"] == 0.0
