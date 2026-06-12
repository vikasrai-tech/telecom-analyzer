"""
KPI Definitions — 5G NR Network KPI catalogue.

Covers the KPIs present in the Excel sample plus the full list from
the operator's requirement. Each entry defines:
  category   — Accessibility / Retainability / Mobility / Capacity /
                Radio Quality / Throughput / Scheduling / RACH
  unit       — %, Mbps, GB, dB, index, ms, count
  direction  — "higher_better" or "lower_better"
  target     — operator SLA / green threshold
  warning    — amber threshold (investigation needed)
  critical   — red threshold (immediate action)
  aliases    — alternate column names found in vendor exports
"""

from typing import Dict, Any

KPI_CATALOG: Dict[str, Dict[str, Any]] = {

    # ── Availability ──────────────────────────────────────────────────
    "Cell_Availability_%": {
        "label":     "Cell Availability",
        "category":  "Availability",
        "unit":      "%",
        "direction": "higher_better",
        "target":    99.5, "warning": 99.0, "critical": 95.0,
        "aliases":   ["Cell Availability", "CellAvailability", "cell_avail"],
    },

    # ── Accessibility ─────────────────────────────────────────────────
    "RRC_Connection_Attempts": {
        "label":     "RRC Connection Attempts",
        "category":  "Accessibility",
        "unit":      "count",
        "direction": "higher_better",
        "target":    None, "warning": None, "critical": None,
        "aliases":   ["RRC Connection Attempts", "RRCConnEstab_Att",
                      "rrc_conn_attempts", "RRC Attempts"],
    },
    "RRC_Connection_Rejects": {
        "label":     "RRC Connection Rejects",
        "category":  "Accessibility",
        "unit":      "count",
        "direction": "lower_better",
        "target":    0, "warning": 5, "critical": 20,
        "aliases":   ["RRC Connection Rejects", "RRCConnEstab_Rej",
                      "rrc_conn_rejects", "RRC Rejects"],
    },
    "RRC_Reestablishment_Attempts": {
        "label":     "RRC Reestablishment Attempts",
        "category":  "Accessibility",
        "unit":      "count",
        "direction": "lower_better",
        "target":    0, "warning": 10, "critical": 50,
        "aliases":   ["RRC Reestablishment Attempts", "RRCReestab_Att",
                      "rrc_reestab_attempts"],
    },
    "Avg_RRC_Connected_Users": {
        "label":     "Avg RRC Connected Users",
        "category":  "Accessibility",
        "unit":      "count",
        "direction": "higher_better",
        "target":    None, "warning": None, "critical": None,
        "aliases":   ["Avg RRC Connected Users", "AvgRRCConnectedUsers",
                      "avg_rrc_users"],
    },
    "Peak_RRC_Connected_Users": {
        "label":     "Peak RRC Connected Users",
        "category":  "Accessibility",
        "unit":      "count",
        "direction": "higher_better",
        "target":    None, "warning": None, "critical": None,
        "aliases":   ["Peak RRC Connected Users", "PeakRRCConnectedUsers",
                      "peak_rrc_users"],
    },
    "RRC_Success_Rate_%": {
        "label":     "RRC Connection Setup Success Rate",
        "category":  "Accessibility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    99.0, "warning": 98.0, "critical": 95.0,
        "aliases":   ["RRC Connection Setup Success Rate",
                      "RRC Setup Success Rate", "RRC_ConnEstab_SR"],
    },
    "Registration_Success_Rate_%": {
        "label":     "Registration Success Rate",
        "category":  "Accessibility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    99.0, "warning": 98.0, "critical": 95.0,
        "aliases":   ["UE-Associated logical NG-connection Success Rate",
                      "NAS Registration Success Rate"],
    },
    "PDU_Session_Success_Rate_%": {
        "label":     "Session Setup Success Rate",
        "category":  "Accessibility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    99.0, "warning": 98.0, "critical": 95.0,
        "aliases":   ["Session Setup Success Rate", "PDU Session Success Rate",
                      "Session success rate EJ_New"],
    },
    "UE_Context_ICS_Success_Rate_%": {
        "label":     "UE Context ICS Success Rate",
        "category":  "Accessibility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    99.0, "warning": 98.0, "critical": 95.0,
        "aliases":   ["UE Context ICS Success Rate"],
    },

    # ── Retainability ─────────────────────────────────────────────────
    "Packet_Loss_%": {
        "label":     "Packet Loss Rate",
        "category":  "Retainability",
        "unit":      "%",
        "direction": "lower_better",
        "target":    0.1, "warning": 0.5, "critical": 1.0,
        "aliases":   ["DRB Drop Rate", "DRB Drop Rate 5QI9 %",
                      "Packet_Loss", "packet_loss_rate"],
    },
    "RRC_Drop_Rate_%": {
        "label":     "RRC Drop Rate",
        "category":  "Retainability",
        "unit":      "%",
        "direction": "lower_better",
        "target":    0.1, "warning": 0.5, "critical": 1.0,
        "aliases":   ["RRC Drop Rate", "RRCDropRate"],
    },
    "DRB_Success_Rate_%": {
        "label":     "DRB Success Rate",
        "category":  "Retainability",
        "unit":      "%",
        "direction": "higher_better",
        "target":    99.0, "warning": 98.0, "critical": 95.0,
        "aliases":   ["DRB Success Rate", "Overall_DRB Success Rate",
                      "Overall DRB Success Rate"],
    },
    "DRB_Attempts": {
        "label":     "DRB Attempts",
        "category":  "Retainability",
        "unit":      "count",
        "direction": "higher_better",
        "target":    None, "warning": None, "critical": None,
        "aliases":   ["DRB Attempts", "DRB_Att", "drb_attempts"],
    },
    "DRB_Drop_Rate_5QI9_%": {
        "label":     "DRB Drop Rate 5QI9 %",
        "category":  "Retainability",
        "unit":      "%",
        "direction": "lower_better",
        "target":    0.1, "warning": 0.5, "critical": 1.0,
        "aliases":   ["DRB Drop Rate 5QI9 %", "DRB_DropRate_5QI9",
                      "drb_drop_rate_5qi9"],
    },

    # ── Mobility ──────────────────────────────────────────────────────
    "Handover_Success_Rate_%": {
        "label":     "Overall 5G Handover Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    95.0, "warning": 93.0, "critical": 90.0,
        "aliases":   ["Overall 5G Handover Success Rate",
                      "Overall 5G Intra_Inter HO Success Rate",
                      "5G_HandIN Success Rate %"],
    },
    "Xn_HO_Prep_Success_Rate_%": {
        "label":     "Xn Handover Preparation Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    95.0, "warning": 93.0, "critical": 90.0,
        "aliases":   ["Xn Handover Preparation Success Rate",
                      "Xn Handover Preparation Success"],
    },
    "Xn_HO_Exec_Success_Rate_%": {
        "label":     "Xn Handover Execution Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    95.0, "warning": 93.0, "critical": 90.0,
        "aliases":   ["Xn Handover Execution Success Rate"],
    },
    "NG_HO_Prep_Success_Rate_%": {
        "label":     "Ng Handover Preparation Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    90.0, "warning": 88.0, "critical": 85.0,
        "aliases":   ["Ng Handover Preparation Success Rate",
                      "Overall Ng Handover Success Rate"],
    },
    "NG_HO_Exec_Success_Rate_%": {
        "label":     "Ng Handover Execution Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    90.0, "warning": 88.0, "critical": 85.0,
        "aliases":   ["Ng Handover Execution Success Rate"],
    },
    "Intra_HO_Success_Rate_%": {
        "label":     "Overall 5G Intra HO Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    95.0, "warning": 93.0, "critical": 90.0,
        "aliases":   ["Overall 5G Intra HO Success Rate",
                      "Intra HO Prep Success Rate", "Intra HandIN Success Rate",
                      "Intra HO Exec Success Rate"],
    },
    "EPS_Fallback_Success_Rate_%": {
        "label":     "EPS Fallback Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    90.0, "warning": 88.0, "critical": 85.0,
        "aliases":   ["EPS Fallback Success Rate"],
    },
    "5G_to_4G_HO_Success_Rate_%": {
        "label":     "5G to 4G HO Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    90.0, "warning": 88.0, "critical": 85.0,
        "aliases":   ["5G to 4G HO Success Rate"],
    },
    "4G_to_5G_HO_Success_Rate_%": {
        "label":     "4G to 5G HO Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    90.0, "warning": 88.0, "critical": 85.0,
        "aliases":   ["4G to 5G HO Success Rate", "4G_to_5G_HO_SR"],
    },
    "Overall_5G_HO_Success_Rate_%": {
        "label":     "Overall 5G HO Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    95.0, "warning": 93.0, "critical": 90.0,
        "aliases":   ["Overall 5G HO Success Rate", "Overall_5G_HO_SR"],
    },
    "Xn_HO_IN_Success_Rate_%": {
        "label":     "Xn HO-IN Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    95.0, "warning": 93.0, "critical": 90.0,
        "aliases":   ["Xn HO-IN Success Rate", "Xn_HandIN Success Rate %",
                      "xn_ho_in_sr"],
    },
    "NG_HO_IN_Success_Rate_%": {
        "label":     "NG HO-IN Success Rate",
        "category":  "Mobility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    90.0, "warning": 88.0, "critical": 85.0,
        "aliases":   ["NG HO-IN Success Rate", "NG_HandIN Success Rate",
                      "ng_ho_in_sr"],
    },
    "EPS_Fallback_Attempts": {
        "label":     "EPS Fallback Attempts",
        "category":  "Mobility",
        "unit":      "count",
        "direction": "lower_better",
        "target":    0, "warning": 5, "critical": 20,
        "aliases":   ["EPS Fallback Attempts", "EPSFallback_Att",
                      "eps_fallback_attempts"],
    },
    "UE_Associated_NG_Conn_SR_%": {
        "label":     "UE-Associated NG-connection Success Rate",
        "category":  "Accessibility",
        "unit":      "%",
        "direction": "higher_better",
        "target":    99.0, "warning": 98.0, "critical": 95.0,
        "aliases":   ["UE-Associated logical NG-connection Success Rate",
                      "UE_Assoc_NG_SR", "ue_ng_conn_sr"],
    },

    # ── Capacity ──────────────────────────────────────────────────────
    "PRB_Utilization_DL_%": {
        "label":     "DL PRB Utilization",
        "category":  "Capacity",
        "unit":      "%",
        "direction": "lower_better",
        "target":    75.0, "warning": 80.0, "critical": 90.0,
        "aliases":   ["DL PRB Utilization", "PRB_DL", "DL_PRB_Usage"],
    },
    "PRB_Utilization_UL_%": {
        "label":     "UL PRB Utilization",
        "category":  "Capacity",
        "unit":      "%",
        "direction": "lower_better",
        "target":    75.0, "warning": 80.0, "critical": 90.0,
        "aliases":   ["UL PRB Utilization", "PRB_UL", "UL_PRB_Usage"],
    },

    # ── Throughput ────────────────────────────────────────────────────
    "DL_Throughput_Mbps": {
        "label":     "User Throughput DL (Mbps)",
        "category":  "Throughput",
        "unit":      "Mbps",
        "direction": "higher_better",
        "target":    500.0, "warning": 100.0, "critical": 50.0,
        "aliases":   ["User Throughput_DL (Mbps)", "User Throughput DL (Mbps)",
                      "DL_Throughput", "dl_tput_mbps"],
    },
    "UL_Throughput_Mbps": {
        "label":     "User Throughput UL (Mbps)",
        "category":  "Throughput",
        "unit":      "Mbps",
        "direction": "higher_better",
        "target":    100.0, "warning": 50.0, "critical": 20.0,
        "aliases":   ["User Throughput_UL (Mbps)", "User Throughput UL (Mbps)",
                      "UL_Throughput", "ul_tput_mbps"],
    },
    "Cell_MAC_DL_Throughput_Mbps": {
        "label":     "Cell Effective MAC DL Throughput (Mbps)",
        "category":  "Throughput",
        "unit":      "Mbps",
        "direction": "higher_better",
        "target":    500.0, "warning": 100.0, "critical": 50.0,
        "aliases":   ["Cell Effective MAC DL Throughput(Mbps)",
                      "Cell Effective Mac DL Throughput(Mbps)",
                      "cell_mac_dl_tput"],
    },
    "Cell_MAC_UL_Throughput_Mbps": {
        "label":     "Cell Effective MAC UL Throughput (Mbps)",
        "category":  "Throughput",
        "unit":      "Mbps",
        "direction": "higher_better",
        "target":    100.0, "warning": 50.0, "critical": 20.0,
        "aliases":   ["Cell Effective MAC UL Throughput(Mbps)",
                      "Cell Effective Mac UL Throughput(Mbps)",
                      "cell_mac_ul_tput"],
    },
    "Total_Traffic_GB": {
        "label":     "Total Traffic (GB)",
        "category":  "Throughput",
        "unit":      "GB",
        "direction": "higher_better",
        "target":    None, "warning": None, "critical": None,
        "aliases":   ["Total Traffic (GB)", "total_traffic_gb",
                      "TotalTraffic_GB"],
    },

    # ── Radio Quality ─────────────────────────────────────────────────
    "CQI": {
        "label":     "Average DL CQI",
        "category":  "Radio Quality",
        "unit":      "index (0-15)",
        "direction": "higher_better",
        "target":    10.0, "warning": 8.0, "critical": 5.0,
        "aliases":   ["Average DL CQI", "avg_cqi", "DL_CQI"],
    },
    "SINR_dB": {
        "label":     "PUSCH SINR",
        "category":  "Radio Quality",
        "unit":      "dB",
        "direction": "higher_better",
        "target":    15.0, "warning": 5.0, "critical": 0.0,
        "aliases":   ["Pusch Sinr", "PUSCH SINR", "SINR", "sinr_db"],
    },
    "Initial_DL_BLER_%": {
        "label":     "Initial DL BLER",
        "category":  "Radio Quality",
        "unit":      "%",
        "direction": "lower_better",
        "target":    5.0, "warning": 10.0, "critical": 20.0,
        "aliases":   ["Initial DL BLER"],
    },
    "Initial_UL_BLER_%": {
        "label":     "Initial UL BLER",
        "category":  "Radio Quality",
        "unit":      "%",
        "direction": "lower_better",
        "target":    5.0, "warning": 10.0, "critical": 20.0,
        "aliases":   ["Initial UL BLER"],
    },
    "Avg_Residual_BLER_DL_%": {
        "label":     "Average Residual BLER-DL",
        "category":  "Radio Quality",
        "unit":      "%",
        "direction": "lower_better",
        "target":    1.0, "warning": 3.0, "critical": 10.0,
        "aliases":   ["Average Residual BLER-DL", "Avg_Residual_BLER_DL",
                      "residual_bler_dl"],
    },
    "Avg_Residual_BLER_UL_%": {
        "label":     "Average Residual BLER-UL",
        "category":  "Radio Quality",
        "unit":      "%",
        "direction": "lower_better",
        "target":    1.0, "warning": 3.0, "critical": 10.0,
        "aliases":   ["Average Residual BLER-UL", "Avg_Residual_BLER_UL",
                      "residual_bler_ul"],
    },
    "Avg_DL_MCS": {
        "label":     "Average DL MCS",
        "category":  "Radio Quality",
        "unit":      "index (0-28)",
        "direction": "higher_better",
        "target":    20.0, "warning": 10.0, "critical": 6.0,
        "aliases":   ["Average DL MCS", "avg_dl_mcs", "DL_MCS",
                      "Average DL MCS Index"],
    },
    "Avg_UL_MCS": {
        "label":     "Average UL MCS",
        "category":  "Radio Quality",
        "unit":      "index (0-28)",
        "direction": "higher_better",
        "target":    18.0, "warning": 8.0, "critical": 4.0,
        "aliases":   ["Average UL MCS", "avg_ul_mcs", "UL_MCS",
                      "Average UL MCS Index"],
    },
    "Avg_DL_Rank": {
        "label":     "Average DL Rank",
        "category":  "Radio Quality",
        "unit":      "index (1-4)",
        "direction": "higher_better",
        "target":    2.0, "warning": 1.5, "critical": 1.0,
        "aliases":   ["Average DL Rank", "avg_dl_rank", "DL_Rank",
                      "Avg DL Rank Indicator"],
    },
    "Avg_UL_RSSI_dBm": {
        "label":     "Average UL RSSI",
        "category":  "Radio Quality",
        "unit":      "dBm",
        "direction": "lower_better",
        "target":    -110.0, "warning": -100.0, "critical": -90.0,
        "aliases":   ["Average UL RSSI", "Avg_RSSI_UL"],
    },

    # ── Latency ───────────────────────────────────────────────────────
    "Latency_ms": {
        "label":     "Latency",
        "category":  "Quality",
        "unit":      "ms",
        "direction": "lower_better",
        "target":    10.0, "warning": 30.0, "critical": 50.0,
        "aliases":   ["Latency", "latency_ms", "avg_latency"],
    },

    # ── RACH ──────────────────────────────────────────────────────────
    "RACH_Success_Rate_%": {
        "label":     "RACH Success Rate",
        "category":  "RACH",
        "unit":      "%",
        "direction": "higher_better",
        "target":    99.0, "warning": 98.0, "critical": 95.0,
        "aliases":   ["RACH Success Rate", "RACH Success Rate Dedicated",
                      "RACH Success Rate Non Dedicated"],
    },

    # ── Scheduling ────────────────────────────────────────────────────
    "DL_CCE_Success_Rate_%": {
        "label":     "MAC AVG DL CCE Success Rate",
        "category":  "Scheduling",
        "unit":      "%",
        "direction": "higher_better",
        "target":    95.0, "warning": 90.0, "critical": 85.0,
        "aliases":   ["MAC_AVG_dlCCEsuccessRateAgg_data"],
    },
    "UL_CCE_Success_Rate_%": {
        "label":     "MAC AVG UL CCE Success Rate",
        "category":  "Scheduling",
        "unit":      "%",
        "direction": "higher_better",
        "target":    95.0, "warning": 90.0, "critical": 85.0,
        "aliases":   ["MAC_AVG_ulCCEsuccessRateAgg_data"],
    },
}

# ── Build reverse alias lookup: alias → canonical column name ─────────
ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canon, meta in KPI_CATALOG.items():
    ALIAS_TO_CANONICAL[canon.lower()] = canon
    for alias in meta.get("aliases", []):
        ALIAS_TO_CANONICAL[alias.lower()] = canon


def resolve_column(raw_name: str) -> str:
    """Map any column name variant to its canonical KPI key, or return raw_name."""
    return ALIAS_TO_CANONICAL.get(raw_name.lower(), raw_name)


def get_meta(canonical: str) -> Dict[str, Any]:
    """Return KPI metadata dict or a safe default."""
    return KPI_CATALOG.get(canonical, {
        "label":     canonical,
        "category":  "Other",
        "unit":      "",
        "direction": "higher_better",
        "target":    None, "warning": None, "critical": None,
    })


# Category ordering for display
CATEGORY_ORDER = [
    "Availability", "Accessibility", "Retainability",
    "Mobility", "Capacity", "Throughput",
    "Radio Quality", "Quality", "RACH", "Scheduling", "Other",
]
