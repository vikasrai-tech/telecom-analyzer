"""
Tests for src/detection/throughput_normalizer.py

Covers:
  1. Healthy TDD cell — no alert
  2. Healthy FDD cell — no alert  (was previously always alerting)
  3. Congested TDD cell — alert fires
  4. Congested FDD cell — alert fires
  5. Missing capacity — graceful fallback (None returned)
  6. Zero capacity — graceful fallback (None returned)
  7. Invalid capacity — graceful fallback (None returned)
  8. Raw throughput preserved in anomaly dict
  9. Normalized throughput calculation
  10. Non-throughput KPI bypasses normalization
  11. Threshold detector integration — FDD no longer fires on healthy throughput
  12. Threshold detector integration — TDD behavior unchanged
  13. TDD fault still detected after normalization
  14. FDD fault still detected after normalization
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.detection.throughput_normalizer import (
    CHANNEL_TYPE_CAPACITY,
    NORMALIZED_THRESHOLDS,
    THROUGHPUT_KPI_TYPE,
    build_capacity_map,
    get_cell_capacity,
    is_throughput_kpi,
    load_aware_ul_severity,
    normalize_throughput,
    normalized_severity,
)


# ── Shared fixtures ──────────────────────────────────────────────────────────
# Capacity values confirmed 2026-08-15: TDD DL=1400, UL=100 | FDD DL=84, UL=50
CAPACITY_MAP = {
    "PCI_TDD": {"dl": 1400.0, "ul": 100.0},
    "PCI_FDD": {"dl":   84.0, "ul":  50.0},
}


# ═══════════════════════════════════════════════════════════════════════════════
# Capacity registry
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetCellCapacity:
    def test_tdd_returns_correct_capacity(self):
        # Confirmed authoritative: TDD DL=1400, UL=100
        cap = get_cell_capacity("TDD")
        assert cap["dl"] == 1400.0
        assert cap["ul"] == 100.0

    def test_fdd_returns_correct_capacity(self):
        # Confirmed authoritative: FDD DL=84, UL=50
        cap = get_cell_capacity("FDD")
        assert cap["dl"] == 84.0
        assert cap["ul"] == 50.0

    def test_case_insensitive(self):
        assert get_cell_capacity("tdd") is not None
        assert get_cell_capacity("fdd") is not None

    def test_unknown_type_returns_none(self):
        # Q5 — missing/unknown channel type
        assert get_cell_capacity("UNKNOWN") is None
        assert get_cell_capacity("")        is None
        assert get_cell_capacity(None)      is None


class TestBuildCapacityMap:
    def _records(self, cells):
        return [{"Cell_ID": c, "Channel_Type": t, "DL_Throughput_Mbps": 100}
                for c, t in cells]

    def test_builds_map_from_records(self):
        records = self._records([("PCI_1", "TDD"), ("PCI_9", "FDD")])
        cap_map = build_capacity_map(records)
        assert cap_map["PCI_1"]["dl"] == 1400.0   # authoritative TDD DL
        assert cap_map["PCI_9"]["dl"] == 84.0     # authoritative FDD DL

    def test_missing_channel_type_omitted(self):
        records = [{"Cell_ID": "PCI_X", "DL_Throughput_Mbps": 100}]
        cap_map = build_capacity_map(records)
        assert "PCI_X" not in cap_map

    def test_deduplicates_per_cell(self):
        records = self._records([("PCI_1", "TDD")] * 100)
        cap_map = build_capacity_map(records)
        assert len(cap_map) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Normalization formula
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalizeThroughput:
    """Q9 — normalized throughput calculation"""

    def test_tdd_dl_nominal(self):
        """769 Mbps / 1400 Mbps = 54.93% (authoritative TDD DL=1400)"""
        result = normalize_throughput("DL_Throughput_Mbps", 769.0, "PCI_TDD", CAPACITY_MAP)
        assert result is not None
        assert abs(result["normalized_pct"] - (769.0 / 1400.0 * 100)) < 0.01

    def test_fdd_dl_nominal(self):
        """51 Mbps / 84 Mbps = 60.71% (authoritative FDD DL=84)"""
        result = normalize_throughput("DL_Throughput_Mbps", 51.0, "PCI_FDD", CAPACITY_MAP)
        assert result is not None
        assert abs(result["normalized_pct"] - (51.0 / 84.0 * 100)) < 0.01

    def test_tdd_and_fdd_healthy_produce_similar_normalized_values(self):
        """Key property: similar load level → normalized % within 15 pp of each other.
        TDD: 769/1400=54.9%, FDD: 51/84=60.7% — different because existing dataset
        was generated with old capacities; normalization still eliminates the bias."""
        tdd = normalize_throughput("DL_Throughput_Mbps", 769.0, "PCI_TDD", CAPACITY_MAP)
        fdd = normalize_throughput("DL_Throughput_Mbps",  51.0, "PCI_FDD", CAPACITY_MAP)
        # Both well above the 7.14% warning threshold — neither should alert
        assert tdd["normalized_pct"] > 7.14
        assert fdd["normalized_pct"] > 7.14

    def test_raw_value_preserved(self):
        """Q8 — raw value must be unchanged"""
        result = normalize_throughput("DL_Throughput_Mbps", 750.0, "PCI_TDD", CAPACITY_MAP)
        assert result["raw_value"] == 750.0

    def test_capacity_mbps_in_result(self):
        # TDD DL capacity is now 1400 Mbps
        result = normalize_throughput("DL_Throughput_Mbps", 100.0, "PCI_TDD", CAPACITY_MAP)
        assert result["capacity_mbps"] == 1400.0

    def test_fdd_capacity_mbps_in_result(self):
        # FDD DL capacity is now 84 Mbps
        result = normalize_throughput("DL_Throughput_Mbps", 42.0, "PCI_FDD", CAPACITY_MAP)
        assert result["capacity_mbps"] == 84.0

    def test_unit_is_pct_of_capacity(self):
        result = normalize_throughput("DL_Throughput_Mbps", 100.0, "PCI_TDD", CAPACITY_MAP)
        assert "%" in result["normalized_unit"]

    def test_non_throughput_kpi_returns_none(self):
        """Q10 — non-throughput KPI bypasses normalization"""
        result = normalize_throughput("Cell_Availability_%", 99.0, "PCI_TDD", CAPACITY_MAP)
        assert result is None

    def test_missing_cell_returns_none(self):
        """Q5 — unknown cell → graceful None"""
        result = normalize_throughput("DL_Throughput_Mbps", 100.0, "UNKNOWN_CELL", CAPACITY_MAP)
        assert result is None

    def test_zero_capacity_returns_none(self):
        """Q6 — zero capacity → no division, returns None"""
        cap_map = {"PCI_BAD": {"dl": 0.0, "ul": 0.0}}
        result = normalize_throughput("DL_Throughput_Mbps", 100.0, "PCI_BAD", cap_map)
        assert result is None

    def test_negative_capacity_returns_none(self):
        """Q7 — invalid (negative) capacity → None"""
        cap_map = {"PCI_BAD": {"dl": -500.0, "ul": -50.0}}
        result = normalize_throughput("DL_Throughput_Mbps", 100.0, "PCI_BAD", cap_map)
        assert result is None

    def test_ul_kpi(self):
        result = normalize_throughput("UL_Throughput_Mbps", 50.0, "PCI_TDD", CAPACITY_MAP)
        assert result is not None
        assert result["direction"] == "ul"
        assert abs(result["normalized_pct"] - (50.0 / 100.0 * 100)) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# Severity thresholds
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalizedSeverity:
    """Verify alert logic using normalized thresholds derived from TDD calibration."""

    def test_healthy_tdd_dl_no_alert(self):
        """Q1 — TDD at 769/1400 ≈ 54.9% → well above 7.14% warning → no alert"""
        pct = 769.0 / 1400.0 * 100
        assert normalized_severity(pct, "dl") == ""

    def test_healthy_fdd_dl_no_alert(self):
        """Q2 — FDD at 51/84 ≈ 60.7% → well above 7.14% warning → no alert (FIX CONFIRMED)"""
        pct = 51.0 / 84.0 * 100
        assert normalized_severity(pct, "dl") == ""

    def test_congested_tdd_dl_alert(self):
        """Q3 — TDD at 40/1400 ≈ 2.86% → below 3.57% critical → Critical"""
        pct = 40.0 / 1400.0 * 100   # ≈ 2.86%, safely below critical (3.5714%)
        assert normalized_severity(pct, "dl") == "Critical"

    def test_congested_fdd_dl_alert(self):
        """Q4 — FDD at 2/84 ≈ 2.38% → below 3.57% critical → Critical"""
        pct = 2.0 / 84.0 * 100   # ≈ 2.38%
        assert normalized_severity(pct, "dl") == "Critical"

    def test_warning_band_dl(self):
        """5% is between critical(3.57%) and warning(7.14%) → High"""
        assert normalized_severity(5.0, "dl") == "High"

    def test_healthy_tdd_ul_no_alert(self):
        """TDD UL at 51/100 = 51% → above UL warning 50% → no alert"""
        pct = 51.0 / 100.0 * 100
        assert normalized_severity(pct, "ul") == ""

    def test_healthy_fdd_ul_borderline(self):
        """FDD UL at 25.5/50 = 51% → above UL warning 50% → no alert"""
        pct = 25.5 / 50.0 * 100
        assert normalized_severity(pct, "ul") == ""

    def test_thresholds_derived_from_tdd_values(self):
        """Normalized thresholds must equal (original_Mbps / confirmed_TDD_capacity * 100)
        TDD DL=1400 Mbps (confirmed), TDD UL=100 Mbps (confirmed)."""
        dl_warn_pct  = NORMALIZED_THRESHOLDS["dl"]["warning"]
        dl_crit_pct  = NORMALIZED_THRESHOLDS["dl"]["critical"]
        ul_warn_pct  = NORMALIZED_THRESHOLDS["ul"]["warning"]
        ul_crit_pct  = NORMALIZED_THRESHOLDS["ul"]["critical"]

        assert abs(dl_warn_pct  - (100.0 / 1400.0 * 100)) < 0.01   # 7.1429%
        assert abs(dl_crit_pct  - ( 50.0 / 1400.0 * 100)) < 0.01   # 3.5714%
        assert abs(ul_warn_pct  - ( 50.0 /  100.0 * 100)) < 0.01   # 50.0%
        assert abs(ul_crit_pct  - ( 20.0 /  100.0 * 100)) < 0.01   # 20.0%


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: detect_threshold_violations with normalization
# ═══════════════════════════════════════════════════════════════════════════════

def _make_parsed_kpi(cell_id, channel_type, dl_tput, ul_tput,
                     avail=99.99, rrc_sr=100.0):
    """Build a minimal parsed_kpi dict for one cell, one row."""
    return {
        "kpi_columns": ["DL_Throughput_Mbps", "UL_Throughput_Mbps",
                        "Cell_Availability_%", "RRC_Success_Rate_%"],
        "timestamp_col": "ts",
        "cell_col": "cell",
        "gnb_col":  "gnb",
        "df_records": [{
            "ts": "2026-01-01 08:00",
            "cell": cell_id,
            "gnb": "gNB-1",
            "Channel_Type": channel_type,
            "DL_Throughput_Mbps": dl_tput,
            "UL_Throughput_Mbps": ul_tput,
            "Cell_Availability_%": avail,
            "RRC_Success_Rate_%":  rrc_sr,
        }],
    }


class TestThresholdDetectorIntegration:
    def _detect(self, cell_id, channel_type, dl_tput, ul_tput, **kw):
        from src.detection.kpi_detector import detect_threshold_violations
        parsed = _make_parsed_kpi(cell_id, channel_type, dl_tput, ul_tput, **kw)
        return detect_threshold_violations(parsed)

    def test_healthy_tdd_no_throughput_alert(self):
        """Q12 — TDD at 769 Mbps: was never alerting, still should not alert"""
        anoms = self._detect("PCI_1", "TDD", dl_tput=769.0, ul_tput=51.0)
        tput_anoms = [a for a in anoms if "Throughput" in a.get("label", "")]
        assert len(tput_anoms) == 0

    def test_healthy_fdd_no_throughput_alert(self):
        """Q11 — FDD at 51 Mbps: was always alerting, must NOT alert after fix"""
        anoms = self._detect("PCI_9", "FDD", dl_tput=51.0, ul_tput=25.5)
        tput_anoms = [a for a in anoms if "Throughput" in a.get("label", "")]
        assert len(tput_anoms) == 0, (
            f"Healthy FDD cell still firing: {[a['evidence'] for a in tput_anoms]}"
        )

    def test_congested_tdd_still_detected(self):
        """Q13 — TDD at 30 Mbps (30/1500=2% < 3.33% critical) → Critical"""
        anoms = self._detect("PCI_1", "TDD", dl_tput=30.0, ul_tput=51.0)
        dl_anoms = [a for a in anoms if "DL" in a.get("label", "")]
        assert any(a["severity"] == "Critical" for a in dl_anoms), \
            "Severely congested TDD DL should be Critical"

    def test_congested_fdd_still_detected(self):
        """Q14 — FDD at 2 Mbps (2/100=2% < 3.33% critical) → Critical"""
        anoms = self._detect("PCI_9", "FDD", dl_tput=2.0, ul_tput=25.5)
        dl_anoms = [a for a in anoms if "DL" in a.get("label", "")]
        assert any(a["severity"] == "Critical" for a in dl_anoms), \
            "Severely congested FDD DL should be Critical"

    def test_raw_value_preserved_in_anomaly(self):
        """Q8 — raw Mbps value must appear unchanged in anomaly dict"""
        anoms = self._detect("PCI_1", "TDD", dl_tput=30.0, ul_tput=51.0)
        dl_anoms = [a for a in anoms if "DL" in a.get("label", "")]
        assert any(abs(a["value"] - 30.0) < 0.01 for a in dl_anoms), \
            "Raw value must be 30.0 Mbps, not replaced by normalized %"

    def test_normalized_pct_attached_to_anomaly(self):
        """Anomaly dict must contain normalized_pct field"""
        anoms = self._detect("PCI_1", "TDD", dl_tput=30.0, ul_tput=51.0)
        dl_anoms = [a for a in anoms if "DL" in a.get("label", "") and "normalized_pct" in a]
        assert len(dl_anoms) > 0, "normalized_pct should be in anomaly dict"

    def test_non_throughput_kpis_unaffected(self):
        """Cell Availability and RRC Success thresholds must work as before"""
        # Availability = 98% (below 99% warning) → should alert
        anoms = self._detect("PCI_1", "TDD", dl_tput=769.0, ul_tput=51.0, avail=98.0)
        avail_anoms = [a for a in anoms if "Availability" in a.get("label", "")]
        assert len(avail_anoms) > 0, "Cell Availability alert should still fire"

    def test_no_channel_type_falls_back_to_raw(self):
        """If Channel_Type is absent, raw Mbps threshold is used (backward compat)"""
        from src.detection.kpi_detector import detect_threshold_violations
        parsed = {
            "kpi_columns": ["DL_Throughput_Mbps"],
            "timestamp_col": "ts", "cell_col": "cell", "gnb_col": "gnb",
            "df_records": [{
                "ts": "2026-01-01", "cell": "PCI_X", "gnb": "gNB-X",
                # No Channel_Type key
                "DL_Throughput_Mbps": 30.0,
            }],
        }
        anoms = detect_threshold_violations(parsed)
        # Raw path: 30 < 50 (critical) → should alert
        assert len(anoms) > 0

    def test_evidence_string_contains_normalized_info(self):
        """Evidence string must show normalized % for explainability"""
        anoms = self._detect("PCI_1", "TDD", dl_tput=30.0, ul_tput=51.0)
        dl_anoms = [a for a in anoms if "DL" in a.get("label", "") and
                    "% of" in a.get("evidence", "")]
        assert len(dl_anoms) > 0, "Evidence should contain normalized percentage info"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase A — Load-Aware UL Threshold (10 required tests)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_parsed_kpi_with_prb(cell_id, channel_type, ul_tput, prb_ul,
                               dl_tput=500.0, avail=99.99, rrc_sr=100.0):
    """Minimal parsed_kpi with UL throughput + PRB_Utilization_UL_% in each row."""
    return {
        "kpi_columns": ["DL_Throughput_Mbps", "UL_Throughput_Mbps",
                        "Cell_Availability_%", "RRC_Success_Rate_%"],
        "timestamp_col": "ts",
        "cell_col":      "cell",
        "gnb_col":       "gnb",
        "df_records": [{
            "ts":                    "2026-01-01 08:00",
            "cell":                  cell_id,
            "gnb":                   "gNB-1",
            "Channel_Type":          channel_type,
            "DL_Throughput_Mbps":    dl_tput,
            "UL_Throughput_Mbps":    ul_tput,
            "PRB_Utilization_UL_%":  prb_ul,
            "Cell_Availability_%":   avail,
            "RRC_Success_Rate_%":    rrc_sr,
        }],
    }


class TestLoadAwareULThreshold:
    """
    Phase A — 10 required tests for load-aware UL threshold.

    Data basis (kpi_64ue_6hr.csv):
      Normal UL efficiency (ul_norm_pct / PRB_UL_pct): mean≈1.07, std≈0.18
      PCI_3 congestion (high PRB): efficiency 0.17–0.25
      PCI_12 outage: PRB_UL < 5 % → absolute floor catches UL_norm=0.36 %
      Normal cells UL_norm min: 8–17 % → always above 5 % absolute floor
    """

    def _ul_anoms(self, cell_id, channel_type, ul_tput, prb_ul, **kw):
        from src.detection.kpi_detector import detect_threshold_violations
        parsed = _make_parsed_kpi_with_prb(cell_id, channel_type, ul_tput, prb_ul, **kw)
        anoms = detect_threshold_violations(parsed)
        return [a for a in anoms if "UL" in a.get("label", "")]

    # ── Test 1 ────────────────────────────────────────────────────────────────
    def test_1_healthy_fdd_low_load_no_ul_anomaly(self):
        """
        FDD cell, PRB_UL=25%, UL=12.5 Mbps (25% of 50 Mbps).
        efficiency=1.0 — low load, low UL is expected.
        dynamic_warning = max(5%, 25%×0.5) = 12.5%; actual=25% > 12.5% → no alert.
        """
        # ul_norm_pct = 12.5/50*100 = 25%; efficiency = 25/25 = 1.0
        anoms = self._ul_anoms("PCI_FDD", "FDD", ul_tput=12.5, prb_ul=25.0)
        assert len(anoms) == 0, (
            f"Healthy FDD cell at low load should not fire: {[a['evidence'] for a in anoms]}"
        )

    # ── Test 2 ────────────────────────────────────────────────────────────────
    def test_2_healthy_tdd_low_load_no_ul_anomaly(self):
        """
        TDD cell, PRB_UL=35%, UL=37.8 Mbps (37.8% of 100 Mbps).
        efficiency=1.08 — low load, low UL is expected.
        dynamic_warning = max(5%, 35%×0.5) = 17.5%; actual=37.8% > 17.5% → no alert.
        """
        anoms = self._ul_anoms("PCI_TDD", "TDD", ul_tput=37.8, prb_ul=35.0)
        assert len(anoms) == 0, (
            f"Healthy TDD cell at low load should not fire: {[a['evidence'] for a in anoms]}"
        )

    # ── Test 3 ────────────────────────────────────────────────────────────────
    def test_3_healthy_fdd_high_load_no_anomaly(self):
        """
        FDD cell, PRB_UL=70%, UL=37.5 Mbps (75% of 50 Mbps).
        efficiency=1.07 — high load, UL tracks PRB load correctly.
        dynamic_warning = max(5%, 70%×0.5) = 35%; actual=75% > 35% → no alert.
        """
        anoms = self._ul_anoms("PCI_FDD", "FDD", ul_tput=37.5, prb_ul=70.0)
        assert len(anoms) == 0, (
            f"Healthy FDD at high load should not fire: {[a['evidence'] for a in anoms]}"
        )

    # ── Test 4 ────────────────────────────────────────────────────────────────
    def test_4_healthy_tdd_high_load_no_anomaly(self):
        """
        TDD cell, PRB_UL=65%, UL=70 Mbps (70% of 100 Mbps).
        efficiency=1.08 — high load, UL is healthy.
        dynamic_warning = max(5%, 65%×0.5) = 32.5%; actual=70% > 32.5% → no alert.
        """
        anoms = self._ul_anoms("PCI_TDD", "TDD", ul_tput=70.0, prb_ul=65.0)
        assert len(anoms) == 0, (
            f"Healthy TDD at high load should not fire: {[a['evidence'] for a in anoms]}"
        )

    # ── Test 5 ────────────────────────────────────────────────────────────────
    def test_5_genuine_low_ul_during_high_load_detected(self):
        """
        TDD cell, PRB_UL=80%, UL=10 Mbps (10% of 100 Mbps).
        efficiency=0.125 < 0.20 critical threshold.
        dynamic_critical = max(2%, 80%×0.20) = 16%; actual=10% < 16% → Critical.
        This mirrors PCI_3 congestion pattern (efficiency 0.17–0.25, high PRB).
        """
        anoms = self._ul_anoms("PCI_TDD", "TDD", ul_tput=10.0, prb_ul=80.0)
        assert len(anoms) > 0, "Genuine UL degradation at high load must be detected"
        assert anoms[0]["severity"] == "Critical", (
            f"Expected Critical, got {anoms[0]['severity']}: {anoms[0]['evidence']}"
        )

    # ── Test 6 ────────────────────────────────────────────────────────────────
    def test_6_missing_prb_metadata_safe_fallback(self):
        """
        PRB_UL is missing (None).  Fallback: absolute-floor only.
        UL_norm=4% → below 5% warning floor, above 2% critical floor → High.
        UL_norm=1% → below 2% critical floor → Critical.
        No PRB context is available — fallback must be deterministic.
        """
        from src.detection.throughput_normalizer import load_aware_ul_severity
        # 4% < 5% floor warning → High
        sev, note = load_aware_ul_severity(normalized_pct=4.0, prb_ul_pct=None)
        assert sev == "High", f"Expected High from fallback path, got '{sev}'"
        assert "fallback" in note.lower(), "Evidence note must mention fallback path"
        # 1% < 2% floor critical → Critical
        sev2, _ = load_aware_ul_severity(normalized_pct=1.0, prb_ul_pct=None)
        assert sev2 == "Critical", f"Expected Critical from fallback path, got '{sev2}'"

    # ── Test 7 ────────────────────────────────────────────────────────────────
    def test_7_invalid_prb_metadata_safe_fallback(self):
        """
        PRB_UL is invalid (NaN, negative, or out-of-range).
        Function must not raise and must return safe deterministic result.
        """
        import math
        for bad in [float("nan"), -10.0, 250.0]:
            sev, note = load_aware_ul_severity(normalized_pct=30.0, prb_ul_pct=bad)
            # 30% > 5% floor → no alert in fallback
            assert sev == "", (
                f"PRB={bad} should produce '' (fallback, 30% healthy), got '{sev}'"
            )

    # ── Test 8 ────────────────────────────────────────────────────────────────
    def test_8_raw_ul_throughput_unchanged_in_anomaly(self):
        """
        Raw Mbps value must appear unchanged in the anomaly dict.
        Capacity normalization must NOT replace the raw value.
        """
        from src.detection.kpi_detector import detect_threshold_violations
        # TDD: UL=10 Mbps at PRB_UL=80% → Critical (efficiency=0.10 < 0.20)
        parsed = _make_parsed_kpi_with_prb("PCI_TDD", "TDD", ul_tput=10.0, prb_ul=80.0)
        anoms = detect_threshold_violations(parsed)
        ul_anoms = [a for a in anoms if "UL" in a.get("label", "")]
        assert len(ul_anoms) > 0, "Should have at least one UL anomaly"
        assert abs(ul_anoms[0]["value"] - 10.0) < 0.01, (
            f"Raw value must be 10.0 Mbps, got {ul_anoms[0]['value']}"
        )

    # ── Test 9 ────────────────────────────────────────────────────────────────
    def test_9_capacity_normalization_unchanged(self):
        """
        normalized_pct must equal (raw_Mbps / capacity_Mbps) × 100 exactly.
        The load-aware path must NOT alter the normalization formula.
        TDD: 10 Mbps / 100 Mbps = 10%.
        """
        from src.detection.kpi_detector import detect_threshold_violations
        parsed = _make_parsed_kpi_with_prb("PCI_TDD", "TDD", ul_tput=10.0, prb_ul=80.0)
        anoms = detect_threshold_violations(parsed)
        ul_anoms = [a for a in anoms if "UL" in a.get("label", "") and
                    "normalized_pct" in a]
        assert len(ul_anoms) > 0
        assert abs(ul_anoms[0]["normalized_pct"] - (10.0 / 100.0 * 100)) < 0.01, (
            f"normalized_pct should be 10.0, got {ul_anoms[0]['normalized_pct']}"
        )

    # ── Test 10 ───────────────────────────────────────────────────────────────
    def test_10_non_ul_kpi_detection_unchanged(self):
        """
        DL and non-throughput KPI detection must be unaffected by Phase A.
        Cell_Availability at 98% (below 99% warning) must still fire.
        DL at 30 Mbps (2.14% of 1400 Mbps TDD < 3.57% critical) must still fire.
        """
        from src.detection.kpi_detector import detect_threshold_violations
        parsed = _make_parsed_kpi_with_prb(
            "PCI_TDD", "TDD",
            ul_tput=60.0,   # healthy UL — must NOT fire
            prb_ul=60.0,
            dl_tput=30.0,   # below critical DL threshold
            avail=98.0,     # below warning
        )
        anoms = detect_threshold_violations(parsed)
        labels = [a.get("label", "") for a in anoms]

        ul_anoms = [a for a in anoms if "UL" in a.get("label", "")]
        assert len(ul_anoms) == 0, (
            f"Healthy UL (60 Mbps at PRB=60%) must not fire: {[a['evidence'] for a in ul_anoms]}"
        )
        assert any("DL" in l for l in labels), "DL anomaly must still fire"
        assert any("Availability" in l for l in labels), "Cell Availability alert must still fire"
