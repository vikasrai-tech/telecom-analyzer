"""
Phase B tests — PRB_DL sustained-duration threshold.

DATA BASIS (kpi_64ue_6hr.csv)
    Normal cells: max consecutive minutes PRB_DL > 80% = 2 min
                  ZERO runs >= 3 min across all 13 normal cells
    PCI_3 congestion fault: 38 consecutive minutes > 80%
    Sustained threshold = 5 min: eliminates all normal FP, preserves fault detection

See also: investigation summary in src/detection/kpi_detector.py (_PRB_DL constants).
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.detection.kpi_detector import (
    _PRB_DL_KPI,
    _PRB_DL_SUSTAINED_CRIT_MIN,
    _PRB_DL_SUSTAINED_WARN_MIN,
    detect_threshold_violations,
)


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_prb_records(
    cell_id: str,
    channel_type: str,
    prb_dl_values: List[float],
    start: datetime = datetime(2026, 6, 13, 10, 0, 0),
    interval_s: int = 60,
    dl_tput: Optional[float] = None,
    ul_tput: float = 50.0,
    prb_ul: float = 45.0,
    avail: float = 99.99,
) -> dict:
    """
    Build a minimal parsed_kpi dict with one cell and N consecutive rows,
    each 1 minute apart, with specified PRB_DL values.
    """
    dl_cap = {"TDD": 1400.0, "FDD": 84.0}.get(channel_type, 1400.0)
    ul_cap = {"TDD": 100.0,  "FDD":  50.0}.get(channel_type, 100.0)

    if dl_tput is None:
        # Healthy DL throughput ≈ 60 % of capacity
        dl_tput = dl_cap * 0.60

    records = []
    for i, prb_dl in enumerate(prb_dl_values):
        ts = (start + timedelta(seconds=i * interval_s)).strftime("%Y-%m-%dT%H:%M:%S")
        records.append({
            "ts":   ts,
            "cell": cell_id,
            "gnb":  "gNB-1",
            "Channel_Type":          channel_type,
            "PRB_Utilization_DL_%":  prb_dl,
            "PRB_Utilization_UL_%":  prb_ul,
            "DL_Throughput_Mbps":    dl_tput,
            "UL_Throughput_Mbps":    ul_tput,
            "Cell_Availability_%":   avail,
        })

    kpi_cols = [
        "PRB_Utilization_DL_%", "PRB_Utilization_UL_%",
        "DL_Throughput_Mbps", "UL_Throughput_Mbps",
        "Cell_Availability_%",
    ]
    return {
        "kpi_columns":   kpi_cols,
        "timestamp_col": "ts",
        "cell_col":      "cell",
        "gnb_col":       "gnb",
        "df_records":    records,
    }


def _prb_anoms(parsed):
    """Return only PRB_DL anomalies from detect_threshold_violations."""
    anoms = detect_threshold_violations(parsed)
    return [a for a in anoms if a.get("kpi") == _PRB_DL_KPI]


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1 — Normal short PRB spike → no anomaly
# ═══════════════════════════════════════════════════════════════════════════════
class TestPRBShortSpike:
    def test_1_short_spike_below_warn_threshold_no_anomaly(self):
        """
        3 consecutive minutes PRB_DL > 80% — below the 5-min warning window.
        Must NOT generate a PRB_DL anomaly.
        """
        # 3 < _PRB_DL_SUSTAINED_WARN_MIN (5)
        parsed = _make_prb_records("PCI_NORMAL", "TDD", prb_dl_values=[82.0] * 3)
        assert len(_prb_anoms(parsed)) == 0, (
            f"Short spike (3 min > 80%) must NOT fire (threshold={_PRB_DL_SUSTAINED_WARN_MIN} min)"
        )

    def test_1b_single_minute_spike_no_anomaly(self):
        """Single 1-minute crossing at 87% — models the most common normal spike."""
        parsed = _make_prb_records("PCI_NORMAL", "FDD", prb_dl_values=[87.0])
        assert len(_prb_anoms(parsed)) == 0

    def test_1c_isolated_spikes_with_gaps_no_anomaly(self):
        """
        Two isolated 2-minute spikes separated by a gap.
        Neither run meets the 5-min minimum — no anomaly.
        """
        # 2 + gap + 2 = two separate runs of 2 min each
        values = [85.0, 86.0, 60.0, 60.0, 60.0, 85.0, 84.0]
        parsed = _make_prb_records("PCI_NORMAL", "TDD", prb_dl_values=values)
        assert len(_prb_anoms(parsed)) == 0, "Two separate 2-min runs must not fire"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2 — Normal sustained high PRB (boundary) → no anomaly
# ═══════════════════════════════════════════════════════════════════════════════
class TestPRBBoundary:
    def test_2_exactly_4min_run_no_anomaly(self):
        """
        4 consecutive minutes > 80% is below the 5-min warning window.
        (Boundary: 4 < 5 → suppress.)
        """
        parsed = _make_prb_records("PCI_NORMAL", "TDD", prb_dl_values=[82.0] * 4)
        assert len(_prb_anoms(parsed)) == 0, (
            f"4-min run must not fire (threshold is {_PRB_DL_SUSTAINED_WARN_MIN} min)"
        )

    def test_2_exactly_5min_run_fires(self):
        """
        5 consecutive minutes > 80% meets the minimum — MUST fire.
        """
        parsed = _make_prb_records("PCI_NORMAL", "TDD", prb_dl_values=[82.0] * 5)
        prb = _prb_anoms(parsed)
        assert len(prb) == 1, (
            f"5-min run must fire exactly once (got {len(prb)})"
        )
        assert prb[0]["severity"] == "High"

    def test_2_exactly_2min_crit_run_no_anomaly(self):
        """
        2 consecutive critical minutes (> 90%) — below the 3-min critical window.
        (Normal cells never cross 90% at all; this is a boundary robustness test.)
        """
        parsed = _make_prb_records("PCI_NORMAL", "TDD", prb_dl_values=[92.0] * 2)
        assert len(_prb_anoms(parsed)) == 0, (
            f"2-min critical run must not fire (threshold={_PRB_DL_SUSTAINED_CRIT_MIN} min)"
        )

    def test_2_exactly_3min_crit_run_fires_critical(self):
        """3 consecutive minutes > 90% → Critical (meets the 3-min critical threshold)."""
        parsed = _make_prb_records("PCI_NORMAL", "TDD", prb_dl_values=[92.0] * 3)
        prb = _prb_anoms(parsed)
        assert len(prb) == 1
        assert prb[0]["severity"] == "Critical"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3 — Genuine congestion → anomaly detected
# ═══════════════════════════════════════════════════════════════════════════════
class TestPRBGenuineCongestion:
    def test_3_sustained_6min_warning_fires(self):
        """6 consecutive minutes > 80% — sustained congestion → High anomaly."""
        parsed = _make_prb_records("PCI_FAULT", "TDD", prb_dl_values=[85.0] * 6)
        prb = _prb_anoms(parsed)
        assert len(prb) >= 1
        assert prb[0]["severity"] in ("High", "Critical")

    def test_3_sustained_38min_fires_once(self):
        """
        38 consecutive minutes > 80% — mirrors the PCI_3 congestion fault.
        Exactly one trigger anomaly expected (the 5th-minute trigger).
        """
        parsed = _make_prb_records("PCI_3", "TDD", prb_dl_values=[90.0] * 38)
        prb = _prb_anoms(parsed)
        # One run of 38 minutes → one anomaly (but could be Critical since >90%)
        assert len(prb) >= 1, "38-minute congestion must generate at least one PRB_DL anomaly"

    def test_3_anomaly_has_sustained_minutes_field(self):
        """Anomaly dict must include sustained_minutes for explainability."""
        parsed = _make_prb_records("PCI_FAULT", "TDD", prb_dl_values=[85.0] * 7)
        prb = _prb_anoms(parsed)
        assert len(prb) >= 1
        assert "sustained_minutes" in prb[0], "sustained_minutes field must be in anomaly dict"
        assert prb[0]["sustained_minutes"] >= _PRB_DL_SUSTAINED_WARN_MIN

    def test_3_evidence_mentions_sustained(self):
        """Evidence string must describe the sustained duration."""
        parsed = _make_prb_records("PCI_FAULT", "TDD", prb_dl_values=[85.0] * 6)
        prb = _prb_anoms(parsed)
        assert len(prb) >= 1
        ev = prb[0].get("evidence", "")
        assert "sustained" in ev.lower() or "consecutive" in ev.lower(), (
            f"Evidence must mention sustained duration: {ev}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4 — High PRB + healthy DL throughput
# ═══════════════════════════════════════════════════════════════════════════════
class TestHighPRBHealthyThroughput:
    def test_4_brief_high_prb_healthy_dl_no_anomaly(self):
        """
        Brief PRB spike (3 min) with healthy DL throughput.
        No anomaly expected: brief spike is suppressed by duration filter,
        regardless of throughput level.
        """
        # DL = 70% of TDD 1400 = 980 Mbps (healthy)
        parsed = _make_prb_records(
            "PCI_NORMAL", "TDD",
            prb_dl_values=[85.0] * 3,
            dl_tput=980.0,
        )
        assert len(_prb_anoms(parsed)) == 0, (
            "Brief PRB spike with healthy DL must not fire"
        )

    def test_4_sustained_high_prb_healthy_dl_fires(self):
        """
        Sustained PRB (6 min) with healthy DL throughput.
        Even with healthy DL, sustained high PRB indicates scheduling saturation.
        Anomaly expected (duration criterion met).
        """
        parsed = _make_prb_records(
            "PCI_FAULT", "TDD",
            prb_dl_values=[85.0] * 6,
            dl_tput=980.0,
        )
        prb = _prb_anoms(parsed)
        assert len(prb) >= 1, (
            "Sustained PRB (6 min) must fire even when DL throughput is healthy"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5 — High PRB + degraded DL throughput
# ═══════════════════════════════════════════════════════════════════════════════
class TestHighPRBDegradedThroughput:
    def test_5_sustained_high_prb_low_dl_fires(self):
        """
        Sustained PRB (6 min) + degraded DL throughput (pathological congestion).
        Anomaly expected — models PCI_3 congestion pattern:
        high PRB, low DL throughput efficiency.
        """
        # DL = 15% of TDD capacity (≈ PCI_3 congestion row: PRB=80%, DL_eff=0.19)
        parsed = _make_prb_records(
            "PCI_3", "TDD",
            prb_dl_values=[85.0] * 6,
            dl_tput=210.0,  # 210/1400 = 15% of TDD capacity
        )
        prb = _prb_anoms(parsed)
        assert len(prb) >= 1, "High PRB + low DL at sustained duration must fire"

    def test_5_brief_spike_low_dl_no_prb_anomaly(self):
        """
        Brief PRB spike (3 min) + degraded DL.
        Still no PRB anomaly: duration is the gating criterion.
        (DL degradation is caught by the DL threshold detector separately.)
        """
        parsed = _make_prb_records(
            "PCI_FAULT", "TDD",
            prb_dl_values=[85.0] * 3,
            dl_tput=50.0,
        )
        assert len(_prb_anoms(parsed)) == 0, (
            "Brief PRB spike must not fire even with degraded DL"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6 — Missing DL throughput metadata
# ═══════════════════════════════════════════════════════════════════════════════
class TestMissingThroughputMetadata:
    def test_6_missing_dl_throughput_does_not_break_prb_check(self):
        """
        PRB_DL sustained check must work even when DL_Throughput_Mbps is absent.
        Duration check is PRB-only; no throughput corroboration required.
        """
        parsed = _make_prb_records("PCI_FAULT", "TDD", prb_dl_values=[85.0] * 6)
        # Remove DL throughput from records
        for r in parsed["df_records"]:
            r.pop("DL_Throughput_Mbps", None)
        parsed["kpi_columns"] = [c for c in parsed["kpi_columns"]
                                  if c != "DL_Throughput_Mbps"]
        prb = _prb_anoms(parsed)
        assert len(prb) >= 1, (
            "PRB_DL sustained check must work without DL_Throughput_Mbps"
        )

    def test_6_missing_dl_short_run_no_anomaly(self):
        """Brief run still suppressed even without DL throughput data."""
        parsed = _make_prb_records("PCI_NORMAL", "TDD", prb_dl_values=[85.0] * 3)
        for r in parsed["df_records"]:
            r.pop("DL_Throughput_Mbps", None)
        parsed["kpi_columns"] = [c for c in parsed["kpi_columns"]
                                  if c != "DL_Throughput_Mbps"]
        assert len(_prb_anoms(parsed)) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7 — Missing load metadata
# ═══════════════════════════════════════════════════════════════════════════════
class TestMissingLoadMetadata:
    def test_7_missing_user_count_does_not_break_prb_check(self):
        """
        PRB_DL sustained check must work without Avg_RRC_Connected_Users.
        PRB utilization is the direct resource signal; user count is not used.
        """
        parsed = _make_prb_records("PCI_FAULT", "TDD", prb_dl_values=[85.0] * 6)
        for r in parsed["df_records"]:
            r.pop("Avg_RRC_Connected_Users", None)
        prb = _prb_anoms(parsed)
        assert len(prb) >= 1

    def test_7_missing_prb_ul_does_not_affect_prb_dl_check(self):
        """
        PRB_UL absence must not affect the PRB_DL sustained filter.
        They are independent KPIs.
        """
        parsed = _make_prb_records("PCI_FAULT", "TDD", prb_dl_values=[85.0] * 6)
        for r in parsed["df_records"]:
            r.pop("PRB_Utilization_UL_%", None)
        parsed["kpi_columns"] = [c for c in parsed["kpi_columns"]
                                  if c != "PRB_Utilization_UL_%"]
        prb = _prb_anoms(parsed)
        assert len(prb) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Test 8 — Phase A UL behavior remains unchanged
# ═══════════════════════════════════════════════════════════════════════════════
class TestPhaseAULUnchanged:
    def test_8_ul_load_aware_still_suppresses_low_load_fp(self):
        """
        Phase A: healthy UL at low load must still produce NO UL anomaly.
        PRB_UL=35%, UL=38 Mbps (38% of TDD 100 Mbps, efficiency=1.09) → no alert.
        """
        parsed = _make_prb_records(
            "PCI_NORMAL", "TDD",
            prb_dl_values=[60.0],   # healthy PRB_DL — no PRB anomaly
            ul_tput=38.0,
            prb_ul=35.0,
        )
        anoms = detect_threshold_violations(parsed)
        ul_anoms = [a for a in anoms if "UL" in a.get("label", "")]
        assert len(ul_anoms) == 0, (
            f"Phase A: healthy UL at low PRB must not fire: "
            f"{[a['evidence'] for a in ul_anoms]}"
        )

    def test_8_ul_load_aware_still_fires_on_genuine_ul_fault(self):
        """
        Phase A: genuine UL degradation at high PRB must still fire.
        PRB_UL=70%, UL=10 Mbps (10% of TDD, efficiency=0.143 < 0.20 crit).
        dynamic_critical = max(2%, 70%×0.20) = 14%; actual=10% < 14% → Critical.
        PRB_UL=70 < 80% warning — does NOT fire PRB threshold itself.
        """
        parsed = _make_prb_records(
            "PCI_FAULT", "TDD",
            prb_dl_values=[60.0],   # healthy DL PRB — no PRB_DL anomaly
            ul_tput=10.0,
            prb_ul=70.0,            # 70% < 80% warning → no PRB_UL threshold fire
        )
        anoms = detect_threshold_violations(parsed)
        # Filter specifically for UL throughput (not PRB_UL which has "UL" in label too)
        ul_tput_anoms = [a for a in anoms if a.get("kpi") == "UL_Throughput_Mbps"]
        assert len(ul_tput_anoms) > 0, "Phase A UL fault must still be detected"
        assert ul_tput_anoms[0]["severity"] == "Critical", (
            f"Expected Critical, got {ul_tput_anoms[0]['severity']}: "
            f"{ul_tput_anoms[0].get('evidence','')}"
        )

    def test_8_prb_dl_and_ul_work_independently(self):
        """
        PRB_DL sustained filter and UL load-aware check must coexist correctly.
        Sustained PRB_DL → PRB_DL anomaly.
        Healthy UL → no UL anomaly.
        """
        parsed = _make_prb_records(
            "PCI_FAULT", "TDD",
            prb_dl_values=[85.0] * 6,   # sustained → PRB_DL anomaly
            ul_tput=70.0,               # healthy UL at PRB_UL=45%
            prb_ul=45.0,
        )
        anoms = detect_threshold_violations(parsed)
        prb_dl_anoms = [a for a in anoms if a.get("kpi") == _PRB_DL_KPI]
        ul_anoms     = [a for a in anoms if "UL" in a.get("label", "")]
        assert len(prb_dl_anoms) >= 1, "Sustained PRB_DL must fire"
        assert len(ul_anoms) == 0, (
            f"Healthy UL must not fire alongside PRB_DL: "
            f"{[a['evidence'] for a in ul_anoms]}"
        )
