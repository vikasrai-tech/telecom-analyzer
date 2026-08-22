"""
Unified Telecom Analyzer — Dashboard
=====================================
Presentation layer only. Business logic lives in src/parsers/, src/detection/, src/llm/.

CURRENT STATE:
  ✅ PCAP parser      — real (NAS / NGAP / RRC / F1AP / E1AP / XnAP)
  ✅ Detection engine — real (6 detectors: IF · Statistical · OC-SVM · LOF · EE · LSTM-AE)
  ✅ KPI parser       — real (Excel/CSV gNB KPI exports)
  ✅ KPI detection    — real (Threshold + Peer Comparison + Trend)
  ✅ LLM explainer   — real (RAG: FAISS + MiniLM + Ollama phi3:mini / rule-based fallback)
"""

import streamlit as st
import pandas as pd
import tempfile
import os
from datetime import datetime
from pathlib import Path
from typing import Dict
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.parsers.pcap_parser_real import parse_pcap as parse_pcap_real
from src.parsers.kpi_parser import parse_kpi_file
from src.parsers.stats_parser import parse_stats_file, get_meta as stats_get_meta
from src.detection.detector import detect_anomalies_by_detector, merge_detector_results
from src.detection.kpi_detector import (
    detect_kpi_anomalies, detect_kpi_anomalies_by_detector, kpi_summary_table
)
from src.detection.stats_detector import (
    detect_stats_anomalies, detect_stats_anomalies_by_detector
)
from src.orchestrator.event_router import EventRouter, _correlation_key
from src.detection.predictor import run_prediction
from src.feedback.store import save_feedback, load_feedback, feedback_stats
from src.llm.explainer import explain_anomaly, ollama_status
from src.agent.react_agent import run_root_cause_agent
from src.agent.tools import get_predictions_for_cell

st.set_page_config(
    page_title="Unified Telecom Analyzer",
    page_icon="📡",
    layout="wide",
)

def render_time_filter(r: dict, key_suffix: str = "") -> dict:
    """
    Render a time-range filter widget and return a filtered copy of the parsed data dict.
    Works for both KPI and Stats data. Supports quick presets + custom date/time pickers.
    """
    ts_col = r.get("timestamp_col", "")
    if not ts_col:
        return r

    df = pd.DataFrame(r["df_records"])
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col])
    if df.empty:
        return r

    ts_min = df[ts_col].min()
    ts_max = df[ts_col].max()
    duration_h = (ts_max - ts_min).total_seconds() / 3600

    with st.expander("🕐 Time Range Filter", expanded=True):
        st.caption(
            f"Dataset: **{ts_min.strftime('%Y-%m-%d %H:%M')}** → "
            f"**{ts_max.strftime('%Y-%m-%d %H:%M')}**  "
            f"(total {duration_h:.1f}h,  {len(df):,} rows)"
        )

        # Quick presets — only show those shorter than actual data span
        presets = ["All data"]
        for label, hours in [("Last 1h", 1), ("Last 2h", 2), ("Last 4h", 4),
                              ("Last 8h", 8), ("Last 12h", 12), ("Last 24h", 24)]:
            if duration_h >= hours:
                presets.append(label)
        presets.append("Custom range")

        quick = st.radio(
            "Quick select",
            presets,
            horizontal=True,
            key=f"tf_quick{key_suffix}",
        )

        ts_start, ts_end = ts_min, ts_max

        if quick.startswith("Last"):
            hours = float(quick.split()[1].rstrip("h"))
            ts_start = ts_max - pd.Timedelta(hours=hours)

        elif quick == "Custom range":
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                s_date = st.date_input("Start date", value=ts_min.date(),
                                       min_value=ts_min.date(), max_value=ts_max.date(),
                                       key=f"tf_sd{key_suffix}")
            with c2:
                s_time = st.time_input("Start time", value=ts_min.time(),
                                       step=300, key=f"tf_st{key_suffix}")
            with c3:
                e_date = st.date_input("End date", value=ts_max.date(),
                                       min_value=ts_min.date(), max_value=ts_max.date(),
                                       key=f"tf_ed{key_suffix}")
            with c4:
                e_time = st.time_input("End time", value=ts_max.time(),
                                       step=300, key=f"tf_et{key_suffix}")
            ts_start = pd.Timestamp.combine(s_date, s_time)
            ts_end   = pd.Timestamp.combine(e_date, e_time)
            if ts_start > ts_end:
                st.warning("⚠️ Start is after end — swapping.")
                ts_start, ts_end = ts_end, ts_start

        # Apply filter
        mask    = (df[ts_col] >= ts_start) & (df[ts_col] <= ts_end)
        df_f    = df[mask].copy()
        n_total = len(df)
        n_f     = len(df_f)
        win_h   = max((ts_end - ts_start).total_seconds() / 3600, 0)

        fi1, fi2, fi3, fi4 = st.columns(4)
        fi1.metric("Total rows",     f"{n_total:,}")
        fi2.metric("Filtered rows",  f"{n_f:,}",
                   delta=f"{n_f - n_total:,}" if n_f != n_total else None)
        fi3.metric("Coverage",       f"{n_f / n_total * 100:.1f}%")
        fi4.metric("Window",         f"{win_h:.1f} h")

        if n_f == 0:
            st.warning("⚠️ No data in selected range — reverting to full dataset.")
            return r

    # Build filtered copy
    r_f = dict(r)
    r_f["df_records"] = df_f.to_dict("records")
    r_f["rows"]       = n_f
    r_f["time_range"] = [
        str(df_f[ts_col].min()),
        str(df_f[ts_col].max()),
    ]
    cell_col = r.get("cell_col", "")
    gnb_col  = r.get("gnb_col", "")
    if cell_col and cell_col in df_f.columns:
        r_f["cells"] = sorted(df_f[cell_col].dropna().unique().tolist())
    if gnb_col and gnb_col in df_f.columns:
        r_f["gnbs"] = sorted(df_f[gnb_col].dropna().unique().tolist())

    # Recompute per-column summary for Stats data
    if "summary" in r and r["summary"]:
        new_summary = {}
        for col in r["summary"]:
            if col in df_f.columns:
                s = df_f[col].dropna()
                if len(s) > 0:
                    new_summary[col] = {
                        "mean": float(s.mean()),
                        "std":  float(s.std()),
                        "min":  float(s.min()),
                        "max":  float(s.max()),
                        "p10":  float(s.quantile(0.10)),
                        "p90":  float(s.quantile(0.90)),
                    }
        r_f["summary"] = new_summary

    return r_f


def render_kpi_dashboard_charts(r: dict) -> None:
    """Auto-generate trend + cell-comparison charts for the KPI dashboard."""
    import plotly.express as px
    from src.parsers.kpi_defs import get_meta as kpi_get_meta

    kpi_cols = r["kpi_columns"]
    ts_col   = r["timestamp_col"]
    cell_col = r["cell_col"]
    if not kpi_cols or not ts_col:
        return

    PRIORITY = [
        "DL_Throughput_Mbps", "UL_Throughput_Mbps",
        "PRB_Utilization_DL_%", "PRB_Utilization_UL_%",
        "RRC_Success_Rate_%", "Handover_Success_Rate_%",
        "CQI", "SINR_dB",
        "Cell_Availability_%", "Packet_Loss_%",
    ]
    LINE_COLORS = {
        "DL_Throughput_Mbps":      "#1f77b4",
        "UL_Throughput_Mbps":      "#17becf",
        "PRB_Utilization_DL_%":    "#d62728",
        "PRB_Utilization_UL_%":    "#ff7f0e",
        "RRC_Success_Rate_%":      "#2ca02c",
        "Handover_Success_Rate_%": "#9467bd",
        "CQI":                     "#8c564b",
        "SINR_dB":                 "#e377c2",
        "Cell_Availability_%":     "#bcbd22",
        "Packet_Loss_%":           "#e31a1c",
    }
    display = [k for k in PRIORITY if k in kpi_cols] or kpi_cols
    display  = display[:8]

    df = pd.DataFrame(r["df_records"])
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")

    # ── Trend charts — 2 per row ─────────────────────────────────────────────
    st.subheader("📊 Dashboard — Key KPI Trends")
    st.caption("Fleet-average over time  ·  🟠 dashed = Warning  ·  🔴 dashed = Critical")

    for i in range(0, len(display), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            if i + j >= len(display):
                break
            kpi   = display[i + j]
            kmeta = kpi_get_meta(kpi)
            color = LINE_COLORS.get(kpi, "#1f4e79")

            df_agg = (df.groupby(ts_col)[kpi].mean()
                        .reset_index().rename(columns={kpi: "value"})
                        .dropna(subset=["value"]))
            if df_agg.empty:
                continue

            fig = px.line(
                df_agg, x=ts_col, y="value",
                title=kpi,
                labels={"value": kmeta.get("unit", ""), ts_col: ""},
                color_discrete_sequence=[color],
            )
            fig.update_traces(line=dict(width=2.5),
                              fill="tozeroy",
                              fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.08)")
            if kmeta.get("warning") is not None:
                fig.add_hline(y=kmeta["warning"], line_dash="dash", line_color="orange",
                              annotation_text=f"Warn {kmeta['warning']}", annotation_font_size=9,
                              annotation_position="bottom right")
            if kmeta.get("critical") is not None:
                fig.add_hline(y=kmeta["critical"], line_dash="dash", line_color="red",
                              annotation_text=f"Crit {kmeta['critical']}", annotation_font_size=9,
                              annotation_position="top right")
            fig.update_layout(
                height=260, margin=dict(l=44, r=16, t=38, b=22),
                plot_bgcolor="#f8f9fa", paper_bgcolor="white",
                font=dict(size=11), showlegend=False,
                xaxis=dict(showgrid=False, zeroline=False),
                yaxis=dict(gridcolor="#e5e5e5"),
                title_font_size=13,
            )
            col.plotly_chart(fig, use_container_width=True)

    # ── Cell comparison ──────────────────────────────────────────────────────
    if cell_col:
        st.subheader("🏙️ Cell Comparison")
        bar_kpi = st.selectbox("Select KPI for comparison", display, key="dash_kpi_bar")
        kmeta   = kpi_get_meta(bar_kpi)
        better_high = kmeta.get("better_high", True)

        df_bar = (df.groupby(cell_col)[bar_kpi].mean().reset_index()
                    .rename(columns={bar_kpi: "mean_val"})
                    .sort_values("mean_val", ascending=not better_high))

        b1, b2 = st.columns([2, 3])
        with b1:
            fig_bar = px.bar(
                df_bar, x="mean_val", y=cell_col, orientation="h",
                title=f"{bar_kpi} — avg per cell",
                labels={"mean_val": kmeta.get("unit", ""), cell_col: "Cell"},
                color="mean_val",
                color_continuous_scale="RdYlGn" if better_high else "RdYlGn_r",
            )
            if kmeta.get("warning"):
                fig_bar.add_vline(x=kmeta["warning"], line_dash="dash", line_color="orange")
            if kmeta.get("critical"):
                fig_bar.add_vline(x=kmeta["critical"], line_dash="dash", line_color="red")
            fig_bar.update_layout(height=max(280, len(df_bar) * 28 + 80),
                                  margin=dict(l=10, r=20, t=38, b=24),
                                  plot_bgcolor="#f8f9fa", coloraxis_showscale=False)
            st.plotly_chart(fig_bar, use_container_width=True)

        with b2:
            top_cells  = df_bar[cell_col].tolist()[:6]
            df_multi   = df[df[cell_col].isin(top_cells)][[ts_col, cell_col, bar_kpi]]
            fleet_avg  = df.groupby(ts_col)[bar_kpi].mean().reset_index()
            fleet_avg[cell_col] = "⬛ Fleet Avg"
            df_combined = pd.concat([df_multi, fleet_avg[[ts_col, cell_col, bar_kpi]]])

            fig_multi = px.line(
                df_combined, x=ts_col, y=bar_kpi, color=cell_col,
                title=f"{bar_kpi} — per-cell trend",
                labels={bar_kpi: kmeta.get("unit", ""), ts_col: ""},
            )
            if kmeta.get("warning"):
                fig_multi.add_hline(y=kmeta["warning"], line_dash="dash",
                                    line_color="orange", annotation_text="Warn",
                                    annotation_font_size=9)
            if kmeta.get("critical"):
                fig_multi.add_hline(y=kmeta["critical"], line_dash="dash",
                                    line_color="red", annotation_text="Crit",
                                    annotation_font_size=9)
            fig_multi.update_layout(
                height=max(280, len(df_bar) * 28 + 80),
                margin=dict(l=44, r=20, t=38, b=24),
                plot_bgcolor="#f8f9fa",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1, font=dict(size=10)),
            )
            st.plotly_chart(fig_multi, use_container_width=True)


def render_stats_dashboard_charts(r: dict) -> None:
    """Auto-generate trend + cell-comparison charts for the DU/CU Stats dashboard."""
    import plotly.express as px
    from src.parsers.stats_parser import get_meta as s_get_meta

    l1l2_cols = r["l1l2_columns"]
    ts_col    = r["timestamp_col"]
    cell_col  = r["cell_col"]
    if not l1l2_cols or not ts_col:
        return

    PRIORITY = [
        "dl_throughput_mbps", "ul_throughput_mbps",
        "dl_bler",            "ul_bler",
        "dl_prb_util",        "ul_prb_util",
        "pusch_snr_db",       "dl_mcs",
        "dl_harq_nack_rate",  "nof_ue",
    ]
    LINE_COLORS = {
        "dl_throughput_mbps":  "#1f77b4",
        "ul_throughput_mbps":  "#17becf",
        "dl_bler":             "#d62728",
        "ul_bler":             "#ff7f0e",
        "dl_prb_util":         "#9467bd",
        "ul_prb_util":         "#8c564b",
        "pusch_snr_db":        "#2ca02c",
        "dl_mcs":              "#e377c2",
        "dl_harq_nack_rate":   "#e31a1c",
        "nof_ue":              "#bcbd22",
    }
    LABELS = {
        "dl_throughput_mbps":  "DL Throughput",
        "ul_throughput_mbps":  "UL Throughput",
        "dl_bler":             "DL BLER",
        "ul_bler":             "UL BLER",
        "dl_prb_util":         "DL PRB Utilization",
        "ul_prb_util":         "UL PRB Utilization",
        "pusch_snr_db":        "PUSCH SNR",
        "dl_mcs":              "DL MCS",
        "dl_harq_nack_rate":   "DL HARQ NACK Rate",
        "nof_ue":              "Active UEs",
    }

    display = [k for k in PRIORITY if k in l1l2_cols] or l1l2_cols
    display  = display[:8]

    df = pd.DataFrame(r["df_records"])
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")

    fmt = r.get("format", "").upper()
    st.subheader(f"📊 Dashboard — L1/L2 Metric Trends  [{fmt}]")
    st.caption("All-cell average over time  ·  🟠 dashed = Warning  ·  🔴 dashed = Critical")

    for i in range(0, len(display), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            if i + j >= len(display):
                break
            metric  = display[i + j]
            smeta   = s_get_meta(metric)
            color   = LINE_COLORS.get(metric, "#1f4e79")
            label   = LABELS.get(metric, metric)

            df_agg = (df.groupby(ts_col)[metric].mean()
                        .reset_index().rename(columns={metric: "value"})
                        .dropna(subset=["value"]))
            if df_agg.empty:
                continue

            fig = px.line(
                df_agg, x=ts_col, y="value",
                title=label,
                labels={"value": smeta.get("unit", ""), ts_col: ""},
                color_discrete_sequence=[color],
            )
            fig.update_traces(line=dict(width=2.5),
                              fill="tozeroy",
                              fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.09)")
            if smeta.get("warning") is not None:
                fig.add_hline(y=smeta["warning"], line_dash="dash", line_color="orange",
                              annotation_text=f"Warn {smeta['warning']}", annotation_font_size=9,
                              annotation_position="bottom right")
            if smeta.get("critical") is not None:
                fig.add_hline(y=smeta["critical"], line_dash="dash", line_color="red",
                              annotation_text=f"Crit {smeta['critical']}", annotation_font_size=9,
                              annotation_position="top right")
            fig.update_layout(
                height=260, margin=dict(l=44, r=16, t=38, b=22),
                plot_bgcolor="#f8f9fa", paper_bgcolor="white",
                font=dict(size=11), showlegend=False,
                xaxis=dict(showgrid=False, zeroline=False),
                yaxis=dict(gridcolor="#e5e5e5"),
                title_font_size=13,
            )
            col.plotly_chart(fig, use_container_width=True)

    # ── Cell comparison ──────────────────────────────────────────────────────
    if cell_col:
        st.subheader("🏙️ Cell (PCI) Comparison")
        bar_metric = st.selectbox("Select metric for comparison", display, key="dash_stats_bar")
        smeta      = s_get_meta(bar_metric)

        df_bar = (df.groupby(cell_col)[bar_metric].mean().reset_index()
                    .rename(columns={bar_metric: "mean_val"})
                    .sort_values("mean_val", ascending=False))

        b1, b2 = st.columns([2, 3])
        with b1:
            worse_high = any(k in bar_metric for k in ("bler", "nack", "prb", "congestion"))
            cscale = "RdYlGn_r" if worse_high else "RdYlGn"
            fig_bar = px.bar(
                df_bar, x="mean_val", y=cell_col, orientation="h",
                title=f"{LABELS.get(bar_metric, bar_metric)} — avg per PCI",
                labels={"mean_val": smeta.get("unit", ""), cell_col: "PCI"},
                color="mean_val", color_continuous_scale=cscale,
            )
            if smeta.get("warning"):
                fig_bar.add_vline(x=smeta["warning"], line_dash="dash", line_color="orange")
            if smeta.get("critical"):
                fig_bar.add_vline(x=smeta["critical"], line_dash="dash", line_color="red")
            fig_bar.update_layout(height=max(280, len(df_bar) * 32 + 80),
                                  margin=dict(l=10, r=20, t=38, b=24),
                                  plot_bgcolor="#f8f9fa", coloraxis_showscale=False)
            st.plotly_chart(fig_bar, use_container_width=True)

        with b2:
            top_cells   = df_bar[cell_col].tolist()
            df_multi    = df[df[cell_col].isin(top_cells)][[ts_col, cell_col, bar_metric]]
            fleet_avg   = df.groupby(ts_col)[bar_metric].mean().reset_index()
            fleet_avg[cell_col] = "⬛ All-Cell Avg"
            df_combined = pd.concat([df_multi, fleet_avg[[ts_col, cell_col, bar_metric]]])

            fig_multi = px.line(
                df_combined, x=ts_col, y=bar_metric, color=cell_col,
                title=f"{LABELS.get(bar_metric, bar_metric)} — per PCI trend",
                labels={bar_metric: smeta.get("unit", ""), ts_col: ""},
            )
            if smeta.get("warning"):
                fig_multi.add_hline(y=smeta["warning"], line_dash="dash",
                                    line_color="orange", annotation_text="Warn",
                                    annotation_font_size=9)
            if smeta.get("critical"):
                fig_multi.add_hline(y=smeta["critical"], line_dash="dash",
                                    line_color="red", annotation_text="Crit",
                                    annotation_font_size=9)
            fig_multi.update_layout(
                height=max(280, len(df_bar) * 32 + 80),
                margin=dict(l=44, r=20, t=38, b=24),
                plot_bgcolor="#f8f9fa",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1, font=dict(size=10)),
            )
            st.plotly_chart(fig_multi, use_container_width=True)


def render_anomaly_distribution_charts(anomalies: list, source: str) -> None:
    """Pie + bar charts showing anomaly breakdown by severity and detector."""
    if not anomalies:
        return
    import plotly.express as px

    st.subheader("📊 Anomaly Distribution")
    df_a = pd.DataFrame([{
        "Severity": a["severity"],
        "Detector": a.get("detector", "—"),
        "Cell":     a.get("cell_id", a.get("label", "—")),
    } for a in anomalies])

    SEV_COLORS = {"Critical": "#c0392b", "High": "#e67e22",
                  "Medium": "#f1c40f", "Low": "#27ae60"}

    ch1, ch2, ch3 = st.columns(3)
    with ch1:
        sev_counts = df_a["Severity"].value_counts().reset_index()
        sev_counts.columns = ["Severity", "Count"]
        fig_pie = px.pie(sev_counts, values="Count", names="Severity",
                         title="By Severity",
                         color="Severity",
                         color_discrete_map=SEV_COLORS,
                         hole=0.4)
        fig_pie.update_layout(height=280, margin=dict(l=0, r=0, t=36, b=0),
                              showlegend=True, legend=dict(font=dict(size=10)))
        fig_pie.update_traces(textfont_size=11)
        st.plotly_chart(fig_pie, use_container_width=True)

    with ch2:
        det_counts = df_a["Detector"].value_counts().reset_index()
        det_counts.columns = ["Detector", "Count"]
        fig_det = px.bar(det_counts, x="Count", y="Detector", orientation="h",
                         title="By Detector",
                         color="Count", color_continuous_scale="Blues")
        fig_det.update_layout(height=280, margin=dict(l=10, r=20, t=36, b=0),
                              plot_bgcolor="#f8f9fa", coloraxis_showscale=False,
                              yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(fig_det, use_container_width=True)

    with ch3:
        cell_counts = df_a["Cell"].value_counts().head(10).reset_index()
        cell_counts.columns = ["Cell", "Anomalies"]
        fig_cell = px.bar(cell_counts, x="Anomalies", y="Cell", orientation="h",
                          title="Top Affected Cells",
                          color="Anomalies", color_continuous_scale="Reds")
        fig_cell.update_layout(height=280, margin=dict(l=10, r=20, t=36, b=0),
                               plot_bgcolor="#f8f9fa", coloraxis_showscale=False,
                               yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(fig_cell, use_container_width=True)


def render_export_panel(
    sections,
    meta: dict,
    filename_prefix: str = "report",
    figures: list = None,
    anomaly_cards: list = None,
) -> None:
    """Render CSV / Excel / PDF / HTML download buttons for the current analysis."""
    from src.reports.report_generator import (
        generate_csv, generate_xlsx, generate_pdf, generate_html,
    )

    st.divider()
    st.subheader("📥 Export Report")
    st.caption(
        "**HTML** mirrors the full dashboard (charts + tables + anomaly cards).  "
        "**CSV / Excel** are flat data tables for further analysis.  "
        "**PDF** is a printable summary."
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        html_bytes = generate_html(sections, meta, figures=figures, anomaly_cards=anomaly_cards)
        st.download_button(
            label="🌐 Full Report (HTML)",
            data=html_bytes,
            file_name=f"{filename_prefix}_{timestamp}.html",
            mime="text/html",
            use_container_width=True,
            key=f"dl_html_{filename_prefix}",
            help="Full dashboard: charts, tables, anomaly cards. Open in browser → Print → Save as PDF",
        )

    with col2:
        csv_bytes = generate_csv(sections, meta)
        st.download_button(
            label="📄 CSV",
            data=csv_bytes,
            file_name=f"{filename_prefix}_{timestamp}.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"dl_csv_{filename_prefix}",
        )

    with col3:
        xlsx_bytes = generate_xlsx(sections, meta)
        st.download_button(
            label="📊 Excel (.xlsx)",
            data=xlsx_bytes,
            file_name=f"{filename_prefix}_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"dl_xlsx_{filename_prefix}",
        )

    with col4:
        with st.spinner("Building PDF…"):
            pdf_bytes = generate_pdf(sections, meta)
        st.download_button(
            label="📑 PDF",
            data=pdf_bytes,
            file_name=f"{filename_prefix}_{timestamp}.pdf",
            mime="application/pdf",
            use_container_width=True,
            key=f"dl_pdf_{filename_prefix}",
        )


def render_event_log(router: "EventRouter") -> None:
    """Render the Event Router log + cross-source correlation panel."""
    st.divider()
    st.subheader("🔀 Event Router — Unified Event Log")
    summary = router.summary()

    # Summary metrics
    e1, e2, e3, e4, e5 = st.columns(5)
    e1.metric("Total Events",     summary["total"])
    e2.metric("🔴 Critical+High", summary["by_severity"].get("Critical", 0) +
                                   summary["by_severity"].get("High", 0))
    e3.metric("🔁 Correlated",    summary["correlated"])
    e4.metric("📡 Current",       summary["current"])
    e5.metric("🔮 Predicted",     summary["predicted"])

    src_cols = st.columns(3)
    for col, src in zip(src_cols, ["pcap", "stats", "kpi"]):
        col.metric(f"Source: {src.upper()}", summary["by_source"].get(src, 0))

    # Top cells
    if summary["top_cells"]:
        st.markdown("**Top cells by event count:**  " +
                    "  ·  ".join(f"`{c}` ({n})" for c, n in summary["top_cells"].items()))

    # Correlated events highlight
    correlated = router.get_correlated()
    if correlated:
        st.subheader("🔗 Cross-Source Correlated Events")
        st.caption("Same cell flagged by ≥ 2 data sources — highest confidence findings")
        for ev in correlated[:10]:
            conf_pct = int(ev["correlation_confidence"] * 100)
            sev_icon = {"Critical": "🚨", "High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(ev["severity"], "⚪")
            sources  = [ev["source"]] + ev["correlated_sources"]
            with st.expander(
                f"{sev_icon} [{ev['severity']}] {ev['category']} | Cell: {ev['cell_id']} "
                f"| Sources: {' + '.join(s.upper() for s in sources)} | Confidence: {conf_pct}%",
                expanded=(ev["severity"] in ("Critical", "High")),
            ):
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**Source:** `{ev['source'].upper()}`")
                c2.markdown(f"**Corroborated by:** `{', '.join(ev['correlated_sources']).upper()}`")
                c3.markdown(f"**Confidence:** `{conf_pct}%`")
                st.info(ev["evidence"])
                st.markdown(f"**State:** `{ev['state']}`  |  "
                            f"**Lead time:** `{ev['lead_time_h']}h`  |  "
                            f"**Detector:** `{ev['detector']}`")

    # Full event table
    with st.expander("📋 Full Event Log (all sources)", expanded=False):
        events = router.get_events()
        if events:
            df_ev = pd.DataFrame([{
                "Severity":    e["severity"],
                "Source":      e["source"].upper(),
                "State":       e["state"],
                "Category":    e["category"],
                "Cell":        e["cell_id"],
                "Metric/Proc": e["metric"],
                "Detector":    e["detector"],
                "Correlated":  "✅" if e["correlated_sources"] else "—",
                "Confidence":  f"{int(e['correlation_confidence']*100)}%"
                               if e["correlated_sources"] else "—",
                "Score":       round(e["score"], 3),
            } for e in events])
            st.dataframe(df_ev, use_container_width=True, height=400)
        else:
            st.success("No events in log.")


def render_feedback_button(event_id: str, source: str, anomaly_type: str,
                           severity: str, detector: str, cell_id: str,
                           evidence: str) -> None:
    """Render 👍 / 👎 / ❓ feedback buttons for one anomaly card."""
    key_base = f"fb_{event_id}"
    c1, c2, c3, c4 = st.columns([1, 1, 1, 4])
    with c1:
        if st.button("👍 Correct", key=f"{key_base}_ok"):
            save_feedback(event_id, source, anomaly_type, severity,
                          detector, cell_id, evidence, verdict="correct",
                          session_id=st.session_state.get("session_id", ""))
            st.success("Feedback saved!")
    with c2:
        if st.button("👎 False +ve", key=f"{key_base}_fp"):
            save_feedback(event_id, source, anomaly_type, severity,
                          detector, cell_id, evidence, verdict="false_positive",
                          session_id=st.session_state.get("session_id", ""))
            st.warning("Marked as false positive.")
    with c3:
        if st.button("❓ Uncertain", key=f"{key_base}_unk"):
            save_feedback(event_id, source, anomaly_type, severity,
                          detector, cell_id, evidence, verdict="uncertain",
                          session_id=st.session_state.get("session_id", ""))
            st.info("Marked uncertain.")


def render_prediction_panel(parsed: Dict, source: str, router: "EventRouter") -> None:
    """Run prediction layer and show predicted anomalies. Predicted events
    are routed into the shared session router (not a throwaway one) so
    they're visible to the Root Cause Agent tab across the session."""
    st.divider()
    st.subheader("🔮 Prediction Layer — Forecast Ahead (Phase II)")
    st.caption("Prophet + Holt-Winters + LSTM: predicts anomalies up to 4h in advance · tagged state=predicted")

    with st.expander("📖 Why Prophet + Holt-Winters + LSTM? (reviewer rationale)", expanded=False):
        st.markdown("""
| Method | Type | Why |
|--------|------|-----|
| **Prophet** | Bayesian structural time-series | Handles seasonality, trends, and missing data. Produces confidence intervals. Best for KPIs with daily/weekly patterns (PRB load, throughput). |
| **Holt-Winters** | Exponential smoothing | Hand-configured (damped trend, optional seasonality) baseline — cheap, interpretable, good sanity check against Prophet. |
| **LSTM** | Deep learning / sequence | Captures nonlinear dependencies between metrics. Better than Prophet when there's no clear seasonality — L1/L2 counters like HARQ NACK rate or BLER show abrupt non-seasonal shifts. |
| **TimesFM** | Foundation model (Google, 200M params) | Zero-shot forecaster pretrained on 100B+ real-world time-series. No fine-tuning needed — works directly on raw CSV exports. Reviewer-recommended for production-grade telecom forecasting. |

**Complementary:** Prophet/Holt-Winters catch slow degradation early; LSTM catches sudden pattern breaks; TimesFM generalises across all patterns zero-shot.
**Lead time:** Default 4h — gives NOC engineers time to act before threshold breach.
        """)

    horizon_h = st.slider("Forecast horizon (hours)", 1, 12, 4, key=f"horizon_{source}")

    with st.spinner(f"Running forecast ({horizon_h}h ahead) — Prophet · Holt-Winters · LSTM · TimesFM ..."):
        try:
            pred_by_method = run_prediction(parsed, horizon_h=horizon_h)
        except Exception as e:
            st.error(f"Prediction failed: {e}")
            return

    all_predicted = [
        {**a, "method": method}
        for method, anoms in pred_by_method.items()
        for a in anoms
    ]

    if not all_predicted:
        st.success(f"✅ No predicted anomalies in the next {horizon_h}h.")
        return

    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("Predicted anomalies", len(all_predicted))
    p2.metric("🔮 Prophet",       len(pred_by_method.get("prophet", [])))
    p3.metric("📈 Holt-Winters",  len(pred_by_method.get("holt_winters", [])))
    p4.metric("🧠 LSTM",          len(pred_by_method.get("lstm", [])))
    p5.metric("⚡ TimesFM",       len(pred_by_method.get("timesfm", [])))

    SEV_ICON = {"Critical": "🚨", "High": "🔴", "Medium": "🟡", "Low": "🟢"}
    for method, anoms in pred_by_method.items():
        router.ingest_predicted(anoms, source=source, lead_time_h=horizon_h)

    for a in sorted(all_predicted,
                    key=lambda x: {"Critical":4,"High":3,"Medium":2,"Low":1}.get(x["severity"],0),
                    reverse=True)[:15]:
        icon = SEV_ICON.get(a["severity"], "⚪")
        with st.expander(
            f"{icon} [PREDICTED {a['severity']}] {a['label']} | {a['cell_id']} "
            f"| {a['method'].upper()} | lead={horizon_h}h",
            expanded=(a["severity"] in ("Critical", "High")),
        ):
            st.info(a["evidence"])
            st.success(a["recommendation"])
            st.markdown(f"**State:** `predicted`  |  **Lead time:** `{horizon_h}h`  |  "
                        f"**Method:** `{a['method']}`")


def render_root_cause_panel(router: "EventRouter") -> None:
    """Root Cause Agent (Phase II) — reasons over cross-source correlated
    events (accumulated in the shared session router across uploads) to
    explain WHY an anomaly happened, not just what it is. Works with or
    without Ollama running (rule-based fallback is always available)."""
    st.header("🕵️ Root Cause Agent (Phase II)")
    st.caption(
        "Reasons over cross-source correlated anomalies (+ predictions) to explain "
        "causal chains. Upload PCAP, KPI, and/or Stats files in the sidebar — all "
        "three uploaders are always there, upload as many as you like — correlation "
        "needs at least 2 sources flagging the same cell."
    )

    summary = router.summary()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total events", summary["total"])
    c2.metric("Correlated",   summary["correlated"])
    c3.metric("Predicted",    summary["predicted"])
    c4.metric("Sources seen", sum(1 for v in summary["by_source"].values() if v > 0))

    correlated = router.get_correlated(min_sources=2)
    if not correlated:
        st.info(
            "No cross-source correlated events yet. Upload at least two different "
            "file types flagging the same cell in this session (e.g. KPI + Stats, "
            "or PCAP + KPI), then come back here."
        )
        return

    groups: Dict[str, list] = {}
    for ev in correlated:
        groups.setdefault(_correlation_key(ev), []).append(ev)

    ROLE_ICON = {"trigger": "🎯", "symptom": "🔻", "contributing_factor": "🔗"}

    for key, group in groups.items():
        cell_id = group[0]["cell_id"]
        sources = sorted({e["source"] for e in group})
        with st.expander(
            f"📍 Cell {cell_id} — {len(group)} correlated events across {', '.join(sources)}",
            expanded=True,
        ):
            if st.button("🔎 Investigate root cause", key=f"rca_btn_{key}"):
                preds = get_predictions_for_cell(cell_id, router) if cell_id != "—" else []
                with st.spinner("Running root-cause agent..."):
                    st.session_state[f"rca_result_{key}"] = run_root_cause_agent(
                        group, router, predictions=preds,
                    )

            result = st.session_state.get(f"rca_result_{key}")
            if result:
                st.success(f"**Source:** {result['source']}  |  **Confidence:** {result['confidence']:.0%}")
                st.markdown(f"**Root cause:** {result['root_cause']}")
                st.markdown("**Causal chain:**")
                for hop in result["causal_chain"]:
                    icon = ROLE_ICON.get(hop["role"], "•")
                    st.markdown(f"{icon} **{hop['role'].replace('_', ' ').title()}** — {hop['explanation']}")
                if result["citations"]:
                    st.markdown("**3GPP citations:**")
                    for c in result["citations"]:
                        st.caption(f"[{c['spec']} §{c['section']}] {c['quote']}")
                st.info(f"**Recommended action:** {result['recommended_action']}")


def render_simple_mode(router: "EventRouter") -> None:
    """Simple Mode — one uploader, auto-detects file type by extension
    (.pcap/.pcapng -> PCAP, .xlsx/.xls -> KPI, .csv/.parquet -> tries Stats'
    strict format auto-detection first, falls back to KPI), and shows one
    consolidated results screen. No manual View-switching, no per-detector
    jargon. Reuses the exact same parse/detect/ingest functions as Detailed
    mode and writes into the same shared_router, so switching to Detailed
    mode mid-session sees everything Simple mode already ingested."""
    st.caption(
        "🎯 **Simple mode** — drop your files below, get one summary. "
        "Switch to 🔧 Detailed mode in the sidebar for full per-protocol "
        "drill-down and reviewer rationale."
    )

    files = st.file_uploader(
        "Upload PCAP / KPI / Stats files — any mix, any number",
        type=["pcap", "pcapng", "csv", "xlsx", "xls", "parquet"],
        accept_multiple_files=True,
        key="simple_upload",
    )

    if "_simple_processed" not in st.session_state:
        st.session_state["_simple_processed"] = {}
    processed = st.session_state["_simple_processed"]

    for f in files or []:
        fp = f"{f.name}:{f.size}"
        if fp in processed:
            continue
        suffix = f.name.split(".")[-1].lower()
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=False) as tmp:
                tmp.write(f.getvalue())
                tmp_path = tmp.name

            if suffix in ("pcap", "pcapng"):
                kind, source = "PCAP", "pcap"
                parsed = parse_pcap_real(tmp_path)
                anomalies = merge_detector_results(detect_anomalies_by_detector(parsed))
            elif suffix in ("xlsx", "xls"):
                kind, source = "KPI", "kpi"
                parsed = parse_kpi_file(tmp_path)
                anomalies = detect_kpi_anomalies(parsed)
            else:  # csv / parquet — ambiguous. parse_stats_file never
                # raises (it falls back to a "generic" format for anything
                # it doesn't recognize), so a plain try/except can't tell a
                # real Stats file from a KPI file — it would silently
                # misdetect every KPI CSV as an empty-result Stats file.
                # Sniff the header against Stats' own srsRAN/OAI/NIST column
                # fingerprints first; only trust "generic" if a KPI parse of
                # the same header doesn't find any known KPI columns either.
                from src.parsers.stats_parser import _detect_format as _stats_detect_format
                if suffix == "parquet":
                    _header_cols = pd.read_parquet(tmp_path).columns.tolist()
                else:
                    _header_cols = pd.read_csv(tmp_path, nrows=0).columns.tolist()

                if _stats_detect_format(_header_cols) != "generic":
                    kind, source = "DU/CU Stats", "stats"
                    parsed = parse_stats_file(tmp_path)
                    anomalies = detect_stats_anomalies(parsed)
                else:
                    parsed_kpi_probe = parse_kpi_file(tmp_path)
                    if parsed_kpi_probe["kpi_columns"]:
                        kind, source = "KPI", "kpi"
                        parsed = parsed_kpi_probe
                        anomalies = detect_kpi_anomalies(parsed)
                    else:
                        kind, source = "DU/CU Stats", "stats"
                        parsed = parse_stats_file(tmp_path)
                        anomalies = detect_stats_anomalies(parsed)

            router.ingest(anomalies, source=source)
            processed[fp] = {"name": f.name, "kind": kind, "count": len(anomalies), "ok": True}
        except Exception as e:
            processed[fp] = {"name": f.name, "kind": "?", "count": 0, "ok": False, "error": str(e)}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    if processed:
        for rec in processed.values():
            if rec["ok"]:
                st.success(f"✅ `{rec['name']}` — detected as **{rec['kind']}**, {rec['count']} anomalies found")
            else:
                st.error(f"❌ `{rec['name']}` — couldn't parse: {rec['error']}")

    summary = router.summary()
    if summary["total"] == 0:
        st.info("👈 Upload at least one file to get started.")
        return

    st.divider()
    st.subheader("📊 Summary")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total events", summary["total"])
    m2.metric("🚨 Critical",  summary["by_severity"]["Critical"])
    m3.metric("🔴 High",      summary["by_severity"]["High"])
    m4.metric("Correlated",   summary["correlated"])
    m5.metric("Sources",      sum(1 for v in summary["by_source"].values() if v > 0))

    sev_df = pd.DataFrame({
        "Count": [summary["by_severity"][s] for s in ("Critical", "High", "Medium", "Low")],
    }, index=["Critical", "High", "Medium", "Low"])
    st.bar_chart(sev_df, height=200)

    st.divider()
    st.subheader("⚠️ Top Issues")
    SEV_ICON = {"Critical": "🚨", "High": "🔴", "Medium": "🟡", "Low": "🟢"}
    top_events = router.get_events(min_severity="Medium")[:10]
    if not top_events:
        st.success("No Medium+ severity issues found.")
    for ev in top_events:
        icon = SEV_ICON.get(ev["severity"], "⚪")
        cell = f" · cell {ev['cell_id']}" if ev["cell_id"] != "—" else ""
        with st.expander(f"{icon} [{ev['severity']}] {ev['category']}{cell} — source: {ev['source'].upper()}"):
            st.markdown(f"**Evidence:** {ev['evidence']}")
            rec = (ev.get("raw_anomaly") or {}).get("recommendation")
            if rec:
                st.markdown(f"**Recommendation:** {rec}")

    correlated = router.get_correlated(min_sources=2)
    if correlated:
        st.divider()
        st.subheader("🕵️ Root Cause")
        st.caption("Cross-source correlated anomalies, auto-analyzed below.")
        _rc_fp = len(correlated)
        if st.session_state.get("_simple_rc_fp") != _rc_fp:
            from src.agent.react_agent import analyze_root_cause
            with st.spinner("Running root-cause agent..."):
                st.session_state["_simple_rc_result"] = analyze_root_cause(router)
            st.session_state["_simple_rc_fp"] = _rc_fp
        for rc in st.session_state.get("_simple_rc_result", []):
            with st.expander(f"📍 Cell {rc['cell_id']} — {rc['root_cause'][:90]}", expanded=True):
                st.markdown(f"**Root cause:** {rc['root_cause']}")
                st.info(f"**Recommended action:** {rc['recommended_action']}")
    else:
        st.caption(
            "💡 Upload a second file type flagging the same cell to unlock "
            "root-cause analysis (e.g. KPI + Stats)."
        )


def render_feedback_history() -> None:
    """Show feedback history + retraining trigger panel."""
    records = load_feedback(limit=100)
    stats   = feedback_stats()

    st.subheader("📋 Feedback History")
    if stats["total"] == 0:
        st.info("No feedback submitted yet. Use 👍/👎/❓ on anomaly cards.")
        return

    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Total",        stats["total"])
    f2.metric("✅ Correct",   stats["correct"])
    f3.metric("❌ False +ve", stats["false_positive"])
    f4.metric("❓ Uncertain", stats["uncertain"])
    if stats["precision"] is not None:
        st.progress(stats["precision"],
                    text=f"Overall Precision: {stats['precision']*100:.1f}%")

    if records:
        df_fb = pd.DataFrame([{
            "Time":     r["timestamp"][:16],
            "Verdict":  r["verdict"],
            "Type":     r["anomaly_type"],
            "Severity": r["severity"],
            "Source":   r["source"],
            "Detector": r["detector"],
            "Cell":     r["cell_id"],
        } for r in records[:50]])
        st.dataframe(df_fb, use_container_width=True, height=250)

    # Per-detector precision
    if stats["by_detector"]:
        st.markdown("**Precision by detector:**")
        det_rows = []
        for det, counts in stats["by_detector"].items():
            total = counts["correct"] + counts["false_positive"]
            prec  = round(counts["correct"] / total, 2) if total > 0 else None
            det_rows.append({"Detector": det, "Correct": counts["correct"],
                              "False +ve": counts["false_positive"],
                              "Precision": prec})
        st.dataframe(pd.DataFrame(det_rows), use_container_width=True)

    # ── Retraining trigger ────────────────────────────────────────────
    st.divider()
    st.markdown("**🔄 Nightly Retraining**")
    st.caption("Adjusts detector parameters based on feedback. "
               "Runs automatically at 2am via cron (`make retrain`).")

    col_btn, col_dry = st.columns(2)
    with col_btn:
        if st.button("🔄 Retrain Now", key="retrain_btn",
                     disabled=(stats["total"] < 5)):
            from src.detection.retrainer import run_retraining
            with st.spinner("Running retraining..."):
                report = run_retraining()
            if report["status"] == "ok":
                n_changed = sum(1 for a in report["adjustments"].values() if a["changed"])
                st.success(f"✅ Retraining complete — {n_changed} detector(s) adjusted")
                for det, adj in report["adjustments"].items():
                    if adj["changed"]:
                        st.markdown(f"- `{det}`: fp={adj['fp_rate']*100:.0f}%  "
                                    f"`{adj['before']}` → `{adj['after']}`")
            else:
                st.warning(report.get("reason", "Retraining skipped"))
        if stats["total"] < 5:
            st.caption("Need ≥ 5 feedback records to retrain.")

    with col_dry:
        if st.button("🔍 Dry Run", key="retrain_dry"):
            from src.detection.retrainer import run_retraining
            with st.spinner("Simulating retraining..."):
                report = run_retraining(dry_run=True)
            if report["status"] == "ok":
                st.info("Dry-run result (config NOT written):")
                for det, adj in report["adjustments"].items():
                    arrow = "→" if adj["changed"] else "·"
                    st.markdown(f"- `{det}` {arrow} `{adj['after']}`")
            else:
                st.warning(report.get("reason", "—"))


def make_proc_table(proc_dict):
    rows = []
    for proc_name, stats in proc_dict.items():
        rows.append({
            "Procedure":         proc_name,
            "Attempts":          stats["attempts"],
            "Success":           stats["success"],
            "Failure":           stats["failure"],
            "Success Rate %":    f"{stats['success_rate']:.1f}%",
            "Top Failure Cause": (
                max(stats["failure_causes"], key=stats["failure_causes"].get)
                if stats["failure_causes"] else "—"
            ),
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()

st.title("📡 Unified Telecom Analyzer")
st.caption(
    "Full 3GPP stack active: NAS · NGAP · RRC · F1AP · E1AP · XnAP  |  "
    "6-detector ensemble · RAG + Ollama LLM · REST API"
)

# ── Session init ──────────────────────────────────────────────────────
import uuid as _uuid
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(_uuid.uuid4())[:8]
if "shared_router" not in st.session_state:
    # One router persisted across Streamlit reruns for the whole browser
    # session — previously each tab built its own router, so cross-source
    # correlation (e.g. a PCAP handover failure + a KPI handover-rate dip
    # on the same cell) never actually surfaced anywhere in the dashboard.
    st.session_state["shared_router"] = EventRouter()
shared_router: EventRouter = st.session_state["shared_router"]

# ── Mode toggle ───────────────────────────────────────────────────────
with st.sidebar:
    ui_mode = st.radio(
        "Mode",
        ["🎯 Simple", "🔧 Detailed (Reviewer)"],
        index=0,
        key="ui_mode",
        help="Simple: one uploader, one summary screen. Detailed: full "
             "per-protocol drill-down, detector rationale, method comparisons.",
    )
    st.divider()

if ui_mode == "🎯 Simple":
    render_simple_mode(shared_router)
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Upload Data")
    st.caption(
        "Upload any or all — no need to switch anything between files. "
        "Correlation & the Root Cause Agent need 2+ sources flagging the same cell."
    )
    pcap_uploaded  = st.file_uploader("📡 PCAP file",       type=["pcap", "pcapng"],
                                       key="up_pcap")
    kpi_uploaded   = st.file_uploader("📊 KPI file",         type=["csv", "xlsx", "xls", "parquet"],
                                       key="up_kpi")
    stats_uploaded = st.file_uploader("📶 DU/CU Stats file", type=["csv", "parquet"],
                                       key="up_stats")
    st.divider()

    _uploads_by_type = {
        "PCAP":            pcap_uploaded,
        "DU/CU Stats":     stats_uploaded,
        "KPI Time-series": kpi_uploaded,
    }
    _view_options = ["PCAP", "DU/CU Stats", "KPI Time-series", "Root Cause Agent (Phase II)"]
    _n_sources = sum(f is not None for f in _uploads_by_type.values())
    _default_view = (
        "Root Cause Agent (Phase II)" if _n_sources >= 2 else
        next((t for t, f in _uploads_by_type.items() if f is not None), "PCAP")
    )
    data_type = st.radio(
        "View",
        _view_options,
        index=_view_options.index(_default_view),
    )
    ext_map = {
        "PCAP":             ["pcap", "pcapng"],
        "DU/CU Stats":      ["csv", "parquet"],
        "KPI Time-series":  ["csv", "xlsx", "xls", "parquet"],
    }
    uploaded = _uploads_by_type.get(data_type)
    st.divider()

    st.subheader("Parser Status")
    if data_type == "KPI Time-series":
        st.success("✅ KPI parser active")
        st.markdown("""
        **Accepts:** Excel (.xlsx), CSV, Parquet

        **KPI categories:**
        - Availability · Accessibility
        - Retainability · Mobility
        - Capacity (PRB) · Throughput
        - Radio Quality (CQI/SINR/BLER)
        - Latency · RACH · Scheduling

        **Sample file:**
        `data/raw/5G_Network_KPI_Sample.xlsx`
        """)
    elif data_type == "DU/CU Stats":
        st.success("✅ Stats parser active")
        st.markdown("""
        **Accepts:** CSV, Parquet

        **Formats auto-detected:**
        - ✅ srsRAN (pci, dl_nof_ok/nok, dl_mcs, pusch_snr_db …)
        - ✅ OAI (DL_MCS1, PRB_DL, dlsch_errors, SNR …)
        - ✅ NIST (RSRP_dBm, DL_BLER_pct, PRB_Utilization_pct …)

        **L1/L2 metrics:** PRB · BLER · MCS · HARQ · SNR · RSRP

        **Sample files:**
        `data/raw/srsran_stats.csv`
        `data/raw/oai_stats.csv`
        `data/raw/nist_stats.csv`
        """)
    elif data_type == "PCAP":
        st.success("✅ Real parser active")
        st.markdown("""
        **Layers (all active):**
        - ✅ NAS — TS 24.501
        - ✅ NGAP — TS 38.413
        - ✅ RRC — TS 38.331
        - ✅ F1AP — TS 38.473
        - ✅ E1AP — TS 38.463
        - ✅ XnAP — TS 38.423

        **Test file:**
        `data/raw/test_5g_full.pcap`
        *(run `scripts/generate_test_pcap.py`)*
        """)

    st.divider()
    show_raw = st.checkbox("Show raw parser output", value=False)
    st.divider()
    with st.expander("📋 Feedback History", expanded=False):
        render_feedback_history()

# ── Background ingest: whichever source isn't the active View still gets
#    parsed + detected + ingested into shared_router here, so uploading
#    e.g. PCAP + KPI + Stats all at once populates cross-source correlation
#    immediately, without needing to click through each View. The active
#    View's own file is parsed+ingested by its section below as usual —
#    skipped here to avoid ingesting it twice. Guarded by a name+size
#    fingerprint so a plain widget rerun (e.g. clicking a chart) doesn't
#    re-ingest and duplicate events on every interaction.
_BG_DETECTORS = {
    "PCAP":            ("pcap",  parse_pcap_real,  lambda p: merge_detector_results(detect_anomalies_by_detector(p))),
    "KPI Time-series": ("kpi",   parse_kpi_file,   detect_kpi_anomalies),
    "DU/CU Stats":     ("stats", parse_stats_file, detect_stats_anomalies),
}
for _bg_type, _bg_file in _uploads_by_type.items():
    if _bg_type == data_type or _bg_file is None:
        continue
    _bg_fp = f"{_bg_file.name}:{_bg_file.size}"
    if st.session_state.get(f"_bg_fp_{_bg_type}") == _bg_fp:
        continue
    _bg_source, _bg_parse_fn, _bg_detect_fn = _BG_DETECTORS[_bg_type]
    _bg_tmp_path = None
    try:
        _bg_suffix = _bg_file.name.split(".")[-1].lower()
        with tempfile.NamedTemporaryFile(suffix=f".{_bg_suffix}", delete=False) as _bg_tmp:
            _bg_tmp.write(_bg_file.getvalue())
            _bg_tmp_path = _bg_tmp.name
        _bg_parsed    = _bg_parse_fn(_bg_tmp_path)
        _bg_anomalies = _bg_detect_fn(_bg_parsed)
        shared_router.ingest(_bg_anomalies, source=_bg_source)
        st.session_state[f"_bg_fp_{_bg_type}"] = _bg_fp
    except Exception as _bg_e:
        st.sidebar.caption(f"⚠️ Background parse of {_bg_type} file failed: {_bg_e}")
    finally:
        if _bg_tmp_path and os.path.exists(_bg_tmp_path):
            os.unlink(_bg_tmp_path)

# ── Root Cause Agent mode (no file upload needed — reads the session's
#    shared router, populated by whatever PCAP/KPI/Stats files were
#    uploaded, in this same browser session, in any View) ────────────────
if data_type == "Root Cause Agent (Phase II)":
    render_root_cause_panel(shared_router)
    st.stop()

# ── No file yet ───────────────────────────────────────────────────────
if uploaded is None:
    st.info("👈 Upload a file in the sidebar to begin.")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.success("**NAS** ✅ TS 24.501\n\nRegistration · Auth\nSecurity Mode\nPDU Session\nDeregistration")
    with col2:
        st.success("**NGAP** ✅ TS 38.413\n\nInitialContextSetup\nPDUSession Setup/Release\nUEContextRelease\nHandover · Paging")
    with col3:
        st.success("**RRC** ✅ TS 38.331\n\nSetup · Reestablishment\nReconfiguration · Release\nSecurity Mode\nUE Capability · Measurement")
    col4, col5, col6 = st.columns(3)
    with col4:
        st.success("**F1AP** ✅ TS 38.473\n\nF1 Setup\nUE Context Setup/Release\nDL/UL RRC Transfer\nInitial UL RRC")
    with col5:
        st.success("**E1AP** ✅ TS 38.463\n\ngNB-CU-UP Setup\nBearer Context Setup\nBearer Modification/Release\nData Notification")
    with col6:
        st.success("**XnAP** ✅ TS 38.423\n\nXn Setup\nHandover Request\nUE Context Release\nSN Addition (MR-DC)")
    st.divider()
    col_det, col_llm = st.columns(2)
    with col_det:
        st.success("**Detection Engine** ✅\n\nIsolation Forest\nStatistical (Threshold+Cascade)\nOne-Class SVM\nLOF\nElliptic Envelope\nLSTM Autoencoder")
    with col_llm:
        st.success("**LLM Explainer** ✅\n\nRAG over 3GPP specs\nFAISS + MiniLM embeddings\nOllama (phi3:mini)\nRule-based fallback")
    st.stop()

# ── Parse ─────────────────────────────────────────────────────────────
st.success(f"✅ Received: `{uploaded.name}` ({uploaded.size:,} bytes)")

suffix = uploaded.name.split('.')[-1].lower()
is_kpi   = data_type == "KPI Time-series"
is_stats = data_type == "DU/CU Stats"

with st.spinner("🔍 Parsing file..."):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name

        if is_kpi:
            parsed_kpi   = parse_kpi_file(tmp_path)
            parsed_stats = None
            parsed       = None
        elif is_stats:
            parsed_stats = parse_stats_file(tmp_path)
            parsed_kpi   = None
            parsed       = None
        else:
            parsed       = parse_pcap_real(tmp_path)
            parsed_kpi   = None
            parsed_stats = None

    except Exception as e:
        st.error(f"❌ Parser error: {e}")
        st.stop()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

# ══════════════════════════════════════════════════════════════════════
# KPI DASHBOARD (Excel / CSV path)
# ══════════════════════════════════════════════════════════════════════
if is_kpi and parsed_kpi:
    r = render_time_filter(parsed_kpi, key_suffix="_kpi")

    # ── gNB Filter ────────────────────────────────────────────────────
    _kpi_data = parsed_kpi  # may be narrowed below
    _gnb_col  = r.get("gnb_col", "")
    if r.get("gnbs"):
        st.subheader("🏢 Filter by gNB")
        _g1, _g2 = st.columns([3, 1])
        with _g1:
            _sel_gnbs = st.multiselect(
                "Select gNB(s) — all selected = no filter",
                options=r["gnbs"],
                default=r["gnbs"],
                key="kpi_gnb_filter",
                placeholder="Choose one or more gNBs…",
            )
        with _g2:
            st.metric("Selected gNBs", f"{len(_sel_gnbs)} / {len(r['gnbs'])}")

        if not _sel_gnbs:
            st.warning("⚠️ No gNB selected — showing full dataset.")
        elif set(_sel_gnbs) != set(r["gnbs"]) and _gnb_col:
            _df_gnb = pd.DataFrame(r["df_records"])
            if _gnb_col in _df_gnb.columns:
                _df_gnb = _df_gnb[_df_gnb[_gnb_col].isin(_sel_gnbs)]
                _r_gnb = dict(r)
                _r_gnb["df_records"] = _df_gnb.to_dict("records")
                _r_gnb["rows"]       = len(_df_gnb)
                _r_gnb["gnbs"]       = _sel_gnbs
                _cc = r.get("cell_col", "")
                if _cc and _cc in _df_gnb.columns:
                    _r_gnb["cells"] = sorted(_df_gnb[_cc].dropna().unique().tolist())
                r = _r_gnb
                _kpi_data = dict(parsed_kpi)
                _kpi_data["df_records"] = _df_gnb.to_dict("records")

    st.subheader("📊 KPI Overview")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Rows",           r["rows"])
    m2.metric("Unique Cells",   len(r["cells"]))
    m3.metric("Unique gNBs",    len(r["gnbs"]))
    m4.metric("KPI Columns",    len(r["kpi_columns"]))
    m5.metric("Time Range",     f"{r['time_range'][0][:16]} → {r['time_range'][1][:16]}")

    render_kpi_dashboard_charts(r)

    # ── KPI Summary Table ─────────────────────────────────────────────
    st.subheader("🚦 KPI Health Summary")
    st.caption("🟢 OK  🟡 Warning  🔴 Critical  (based on mean value vs thresholds)")

    summary_rows = kpi_summary_table(_kpi_data)
    if summary_rows:
        df_summary = pd.DataFrame(summary_rows)
        st.dataframe(df_summary, use_container_width=True, height=420)

    # ── KPI Trend Charts ──────────────────────────────────────────────
    st.subheader("📈 KPI Trend Explorer")
    kpi_cols = r["kpi_columns"]
    ts_col   = r["timestamp_col"]
    cell_col = r["cell_col"]

    _kpi_trend_fig = None
    _kpi_df_cell   = pd.DataFrame()

    if kpi_cols and ts_col:
        import plotly.express as px

        col_sel, cell_sel = st.columns(2)
        with col_sel:
            sel_kpi = st.selectbox("Select KPI", kpi_cols)
        with cell_sel:
            cell_options = ["All cells (fleet avg)"] + r["cells"]
            sel_cell = st.selectbox("Select Cell", cell_options)

        df_plot = pd.DataFrame(r["df_records"])
        df_plot[ts_col] = pd.to_datetime(df_plot[ts_col], errors="coerce")

        if sel_cell == "All cells (fleet avg)":
            df_line = (df_plot.groupby(ts_col)[sel_kpi]
                       .mean().reset_index().rename(columns={sel_kpi: "value"}))
            title = f"{sel_kpi} — Fleet Average over Time"
        else:
            df_line = (df_plot[df_plot[cell_col] == sel_cell][[ts_col, sel_kpi]]
                       .rename(columns={sel_kpi: "value"}))
            title = f"{sel_kpi} — {sel_cell}"

        if not df_line.empty:
            from src.parsers.kpi_defs import get_meta
            kpi_meta = get_meta(sel_kpi)
            fig  = px.line(df_line, x=ts_col, y="value", title=title,
                           labels={"value": f"{sel_kpi} ({kpi_meta.get('unit','')})",
                                   ts_col: "Time"})
            # Add warning / critical lines
            if kpi_meta.get("warning") is not None:
                fig.add_hline(y=kpi_meta["warning"],  line_dash="dot",
                              line_color="orange", annotation_text="Warning")
            if kpi_meta.get("critical") is not None:
                fig.add_hline(y=kpi_meta["critical"], line_dash="dot",
                              line_color="red",    annotation_text="Critical")
            st.plotly_chart(fig, use_container_width=True)
            _kpi_trend_fig = fig  # capture for HTML export

    # ── Per-Cell KPI Heatmap ──────────────────────────────────────────
    st.subheader("🗺️ Per-Cell KPI Breakdown")
    if kpi_cols and cell_col:
        df_all = pd.DataFrame(r["df_records"])
        gnb_col = r.get("gnb_col", "")
        group_cols = [cell_col] + ([gnb_col] if gnb_col else [])
        df_cell = df_all.groupby(group_cols)[kpi_cols].mean().round(2).reset_index()
        df_cell = df_cell.sort_values(kpi_cols[0])
        st.dataframe(df_cell, use_container_width=True, height=350)
        _kpi_df_cell = df_cell  # capture for HTML export

    # ── KPI Anomaly Detection ─────────────────────────────────────────
    st.divider()
    st.subheader("⚠️ KPI Anomaly Detection — 6-Method Ensemble")
    st.caption("Threshold · Peer Comparison · Trend · IQR · CUSUM · Bollinger Bands")

    with st.expander("📖 Why these 6 KPI detection methods? (reviewer rationale)", expanded=False):
        st.markdown("""
| # | Method | Type | Why we use it |
|---|--------|------|---------------|
| 1 | **Threshold Violation** | Rule-based | Encodes operator SLA limits directly from 3GPP / ITU-T. Instant, interpretable, zero false positives for known thresholds. Every other method is calibrated against this baseline. |
| 2 | **Peer Comparison (Z-score)** | Statistical / cross-cell | A KPI value might be within threshold but still 3σ worse than all peer cells. Catches underperforming cells the operator hasn't set explicit limits for. |
| 3 | **Trend (Linear Regression)** | Statistical / temporal | Detects monotonic long-term degradation before it hits threshold. Slope > 0.5 unit/hr = actionable even if current value is still "green". |
| 4 | **IQR (Tukey Fence)** | Robust statistics | No distribution assumption. Z-score is sensitive to outliers (outlier inflates σ, masking itself). IQR is robust — PRB utilization is right-skewed, CQI during interference is left-skewed. |
| 5 | **CUSUM** | Sequential / change-point | Accumulates small consistent deviations invisible to per-point detectors. Standard NOC method for early warning: catches RRC SR quietly dropping 99.5% → 98.2% over 10 intervals before any threshold fires. |
| 6 | **Bollinger Bands** | Rolling envelope / burst | Catches sudden short-term spikes that trend analysis misses. PRB momentary burst to 95% in a normally 40%-loaded cell; CQI crash during interference. Window=5 gives local context. |

**Complementary coverage:**
- Threshold + IQR → point-in-time violations
- Peer Comparison → cross-cell relative anomalies
- Trend + CUSUM → time-evolving degradation
- Bollinger Bands → sudden bursts
        """)

    with st.spinner("Running 6 KPI detectors..."):
        kpi_by_detector = detect_kpi_anomalies_by_detector(_kpi_data)
        kpi_anomalies   = sorted(
            [a for anoms in kpi_by_detector.values() for a in anoms],
            key=lambda a: ({"Critical":4,"High":3,"Medium":2,"Low":1}.get(a["severity"],0),
                           a.get("score", 0)),
            reverse=True,
        )

    if not kpi_anomalies:
        st.success("✅ No KPI anomalies detected.")
    else:
        render_anomaly_distribution_charts(kpi_anomalies, "KPI")
        crit_n = sum(1 for a in kpi_anomalies if a["severity"] == "Critical")
        high_n = sum(1 for a in kpi_anomalies if a["severity"] == "High")
        med_n  = sum(1 for a in kpi_anomalies if a["severity"] == "Medium")
        low_n  = sum(1 for a in kpi_anomalies if a["severity"] == "Low")

        ka1, ka2, ka3, ka4 = st.columns(4)
        ka1.metric("🔴 Critical", crit_n)
        ka2.metric("🟠 High",     high_n)
        ka3.metric("🟡 Medium",   med_n)
        ka4.metric("🟢 Low",      low_n)

        # ── KPI method comparison matrix ──────────────────────────────
        st.subheader("🔬 KPI Method Comparison Matrix")
        st.caption("Which detector flagged which KPI + Cell  |  🔴 Critical · 🟠 High · 🟡 Medium · 🟢 Low · ✅ OK")

        KPI_DET_COLS = ["Threshold", "Peer Comparison", "Trend", "IQR", "CUSUM", "Bollinger Bands"]
        KPI_SEV_BADGE = {"Critical": "🔴 Crit", "High": "🟠 High", "Medium": "🟡 Med", "Low": "🟢 Low"}

        kpi_matrix_key: Dict[str, Dict[str, str]] = {}
        for det_name, anoms in kpi_by_detector.items():
            for a in anoms:
                row_key = f"{a['label']} | {a['cell_id']}"
                if row_key not in kpi_matrix_key:
                    kpi_matrix_key[row_key] = {}
                existing = kpi_matrix_key[row_key].get(det_name, "")
                SEV_R = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
                if SEV_R.get(a["severity"], 0) > SEV_R.get(existing, 0):
                    kpi_matrix_key[row_key][det_name] = a["severity"]

        _kpi_matrix_df = pd.DataFrame()
        if kpi_matrix_key:
            matrix_rows = []
            for row_key, det_sevs in list(kpi_matrix_key.items())[:60]:
                row = {"KPI | Cell": row_key}
                agreement = sum(1 for v in det_sevs.values() if v)
                for det in KPI_DET_COLS:
                    sev = det_sevs.get(det, "")
                    row[det[:10]] = KPI_SEV_BADGE.get(sev, "✅") if sev else "✅"
                row["Confirmed by"] = f"{agreement}/{len(KPI_DET_COLS)}"
                matrix_rows.append(row)
            _kpi_matrix_df = pd.DataFrame(matrix_rows)
            st.dataframe(_kpi_matrix_df, use_container_width=True, height=320)

        # Anomaly table
        anom_df = pd.DataFrame([{
            "Severity":    a["severity"],
            "KPI":         a["label"],
            "Category":    a["category"],
            "Cell":        a["cell_id"],
            "gNB":         a["gnb_id"],
            "Value":       a["value"],
            "Unit":        a["unit"],
            "Warning":     a["warning"],
            "Critical":    a["critical"],
            "Detector":    a["detector"],
            "Evidence":    a["evidence"][:80],
        } for a in kpi_anomalies])

        sev_filter = st.selectbox("Filter severity",
                                  ["All", "Critical", "High", "Medium", "Low"],
                                  key="kpi_sev")
        shown_df = anom_df if sev_filter == "All" else anom_df[anom_df["Severity"] == sev_filter]
        st.dataframe(shown_df, use_container_width=True, height=400)

        # ── Inline Issue Analysis ─────────────────────────────────────────
        st.subheader("🔬 Issue Analysis")
        _kpi_shown = ([a for a in kpi_anomalies if a["severity"] == sev_filter]
                      if sev_filter != "All" else kpi_anomalies)[:20]
        if _kpi_shown:
            _kpi_labels = [
                f"#{i+1}  [{a['severity']}]  {a['label']}  |  {a['cell_id']}  |  {a['detector']}"
                for i, a in enumerate(_kpi_shown)
            ]
            _kpi_sel = st.selectbox(
                "Select issue to view analysis →",
                range(len(_kpi_labels)),
                format_func=lambda i: _kpi_labels[i],
                key="kpi_issue_sel",
            )
            _ka = _kpi_shown[_kpi_sel]
            _SEV_ICON = {"Critical": "🚨", "High": "🔴", "Medium": "🟡", "Low": "🟢"}
            _kicon = _SEV_ICON.get(_ka["severity"], "⚪")

            st.markdown(f"#### {_kicon} {_ka['label']}  |  Cell: `{_ka['cell_id']}`")
            _kac1, _kac2 = st.columns(2)
            with _kac1:
                st.markdown("**Issue**")
                st.info(_ka["evidence"])
                st.markdown(
                    f"Value: **{_ka['value']} {_ka['unit']}** &nbsp;|&nbsp; "
                    f"Warning: {_ka['warning']} &nbsp;|&nbsp; Critical: {_ka['critical']}"
                )
            with _kac2:
                st.markdown("**Recommendation**")
                st.success(_ka["recommendation"])

            st.markdown("**🤖 LLM Analysis — RAG over 3GPP Specs**")
            _kpi_exp_key = f"llm_kpi_{_ka.get('label','')}_{_ka.get('cell_id','')}"
            if _kpi_exp_key not in st.session_state:
                with st.spinner("Retrieving 3GPP specs + generating analysis..."):
                    st.session_state[_kpi_exp_key] = explain_anomaly(_ka)
            _kexp = st.session_state[_kpi_exp_key]
            _ksrc = _kexp.get("source", "")
            st.caption(f"🤖 {_ksrc}" if "Ollama" in _ksrc else f"📚 {_ksrc}")
            st.info(_kexp.get("hypothesis", "—"))
            if _kexp.get("citations"):
                st.markdown("**3GPP Citations**")
                for _cite in _kexp["citations"]:
                    st.markdown(f"- `{_cite.get('spec','')} §{_cite.get('section','')}` — {_cite.get('quote','')}")
            if _kexp.get("investigation_hints"):
                st.markdown("**Investigation Checklist**")
                for _hint in _kexp["investigation_hints"]:
                    st.markdown(f"- {_hint}")

            st.markdown("**Engineer Feedback**")
            render_feedback_button(
                event_id=_ka.get("label","") + "_" + _ka.get("cell_id",""),
                source="kpi", anomaly_type=_ka.get("label",""),
                severity=_ka["severity"], detector=_ka.get("detector",""),
                cell_id=_ka.get("cell_id",""), evidence=_ka.get("evidence",""),
            )

    # ── Export Report ─────────────────────────────────────────────────
    _kpi_export_sections = []
    if summary_rows:
        _kpi_export_sections.append({
            "title": "KPI Health Summary",
            "df": pd.DataFrame(summary_rows),
        })
    if not _kpi_df_cell.empty:
        _kpi_export_sections.append({
            "title": "Per-Cell KPI Breakdown",
            "df": _kpi_df_cell,
        })
    if not _kpi_matrix_df.empty:
        _kpi_export_sections.append({
            "title": "KPI Method Comparison Matrix",
            "df": _kpi_matrix_df,
            "notes": "🔴 Crit = Critical · 🟠 High · 🟡 Med · 🟢 Low · ✅ Not flagged",
        })
    _kpi_anom_df = pd.DataFrame([{
        "Severity": a["severity"], "KPI": a["label"],
        "Category": a["category"], "Cell": a["cell_id"],
        "gNB": a["gnb_id"], "Value": a["value"], "Unit": a["unit"],
        "Warning": a["warning"], "Critical": a["critical"],
        "Detector": a["detector"], "Evidence": a["evidence"],
        "Recommendation": a["recommendation"],
    } for a in kpi_anomalies]) if kpi_anomalies else pd.DataFrame()
    if not _kpi_anom_df.empty:
        _kpi_export_sections.append({
            "title": "KPI Anomalies",
            "df": _kpi_anom_df,
            "notes": f"{len(kpi_anomalies)} anomalies detected",
        })

    _kpi_meta = {
        "Source File":  uploaded.name,
        "Data Type":    "KPI Time-series",
        "Rows":         r["rows"],
        "Unique Cells": len(r["cells"]),
        "Unique gNBs":  len(r["gnbs"]),
        "KPI Columns":  len(r["kpi_columns"]),
        "Time Range":   f"{r['time_range'][0][:16]} → {r['time_range'][1][:16]}",
        "Anomalies":    len(kpi_anomalies),
    }
    _kpi_figures = (
        [{"title": f"KPI Trend: {_kpi_trend_fig.layout.title.text}", "fig": _kpi_trend_fig}]
        if _kpi_trend_fig is not None else []
    )
    _kpi_anomaly_cards = [
        {
            "severity":       a["severity"],
            "title":          f"{a['label']} | {a['cell_id']} | {a['detector']}",
            "evidence":       a["evidence"],
            "recommendation": a["recommendation"],
            "value":          a["value"],
            "unit":           a["unit"],
            "warning":        a["warning"],
            "critical":       a["critical"],
        }
        for a in kpi_anomalies[:20]
    ]
    render_export_panel(
        _kpi_export_sections, _kpi_meta, "kpi_report",
        figures=_kpi_figures, anomaly_cards=_kpi_anomaly_cards,
    )

    # ── Event Router ─────────────────────────────────────────────────
    shared_router.ingest(kpi_anomalies, source="kpi")

    # ── Prediction Layer ──────────────────────────────────────────────
    render_prediction_panel(_kpi_data, source="kpi", router=shared_router)

    render_event_log(shared_router)

    st.stop()  # KPI path ends here

# ══════════════════════════════════════════════════════════════════════
# STATS DASHBOARD (DU/CU Stats path — srsRAN / OAI / NIST)
# ══════════════════════════════════════════════════════════════════════
if is_stats and parsed_stats:
    import plotly.express as px

    r = render_time_filter(parsed_stats, key_suffix="_stats")
    st.subheader("📡 DU/CU Stats Overview")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Rows",          r["rows"])
    m2.metric("Cells",         len(r["cells"]))
    m3.metric("L1/L2 Metrics", len(r["l1l2_columns"]))
    m4.metric("Format",        r["format"].upper())
    m5.metric("Time Range",
              f"{str(r['time_range'][0])[:16]} → {str(r['time_range'][1])[:16]}"
              if r["time_range"][0] else "—")

    render_stats_dashboard_charts(r)

    # ── L1/L2 Summary Table ───────────────────────────────────────────
    st.subheader("🚦 L1/L2 Metric Health Summary")
    st.caption("🟢 OK  🟡 Warning  🔴 Critical  (based on mean value vs 3GPP thresholds)")

    if r["summary"]:
        summary_rows = []
        for col, stats in r["summary"].items():
            meta = stats_get_meta(col)
            mean_val = stats["mean"]
            w = meta.get("warning")
            c_thresh = meta.get("critical")

            # Determine status
            status = "🟢 OK"
            worse_high = any(k in col for k in ("bler", "prb", "nack"))
            if w is not None:
                if worse_high:
                    if c_thresh and mean_val >= c_thresh:
                        status = "🔴 Critical"
                    elif mean_val >= w:
                        status = "🟡 Warning"
                else:
                    if c_thresh and mean_val <= c_thresh:
                        status = "🔴 Critical"
                    elif mean_val <= w:
                        status = "🟡 Warning"

            summary_rows.append({
                "Status":   status,
                "Metric":   col,
                "Desc":     meta["desc"],
                "Unit":     meta["unit"],
                "Mean":     round(mean_val, 2),
                "Min":      round(stats["min"], 2),
                "Max":      round(stats["max"], 2),
                "P10":      round(stats["p10"], 2),
                "P90":      round(stats["p90"], 2),
                "Warning":  w,
                "Critical": c_thresh,
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, height=400)

    # ── Trend Explorer ────────────────────────────────────────────────
    st.subheader("📈 L1/L2 Metric Trend Explorer")
    l1l2_cols = r["l1l2_columns"]
    ts_col    = r["timestamp_col"]
    cell_col  = r["cell_col"]

    _stats_trend_fig = None
    _stats_df_cell   = pd.DataFrame()

    if l1l2_cols and ts_col:
        col_sel, cell_sel = st.columns(2)
        with col_sel:
            sel_metric = st.selectbox("Select Metric", l1l2_cols, key="stats_metric")
        with cell_sel:
            cell_opts = ["All cells (avg)"] + r["cells"]
            sel_cell  = st.selectbox("Select Cell", cell_opts, key="stats_cell")

        df_plot = pd.DataFrame(r["df_records"])
        df_plot[ts_col] = pd.to_datetime(df_plot[ts_col], errors="coerce")

        if sel_cell == "All cells (avg)":
            df_line = (df_plot.groupby(ts_col)[sel_metric]
                       .mean().reset_index().rename(columns={sel_metric: "value"}))
            title = f"{sel_metric} — All Cells Average"
        else:
            df_line = (df_plot[df_plot[cell_col] == sel_cell][[ts_col, sel_metric]]
                       .rename(columns={sel_metric: "value"}))
            title = f"{sel_metric} — {sel_cell}"

        if not df_line.empty:
            stat_meta = stats_get_meta(sel_metric)
            fig  = px.line(df_line, x=ts_col, y="value", title=title,
                           labels={"value": f"{sel_metric} ({stat_meta['unit']})", ts_col: "Time"})
            if stat_meta.get("warning") is not None:
                fig.add_hline(y=stat_meta["warning"],  line_dash="dot",
                              line_color="orange", annotation_text="Warning")
            if stat_meta.get("critical") is not None:
                fig.add_hline(y=stat_meta["critical"], line_dash="dot",
                              line_color="red",   annotation_text="Critical")
            st.plotly_chart(fig, use_container_width=True)
            _stats_trend_fig = fig  # capture for HTML export

    # ── Per-Cell Heatmap ──────────────────────────────────────────────
    st.subheader("🗺️ Per-Cell Metric Breakdown")
    if l1l2_cols and cell_col:
        df_all  = pd.DataFrame(r["df_records"])
        df_cell = df_all.groupby(cell_col)[l1l2_cols].mean().round(3).reset_index()
        st.dataframe(df_cell, use_container_width=True, height=300)
        _stats_df_cell = df_cell  # capture for HTML export

    # ── Stats Anomaly Detection ───────────────────────────────────────
    st.divider()
    st.subheader("⚠️ L1/L2 Anomaly Detection — 6-Method Ensemble")
    st.caption("Threshold · Peer Comparison · Trend · IQR · CUSUM · Bollinger Bands")

    with st.expander("📖 Why these 6 methods? (reviewer rationale)", expanded=False):
        st.markdown("""
| # | Method | Type | Why for L1/L2 stats |
|---|--------|------|---------------------|
| 1 | **Threshold** | Rule-based | 3GPP/vendor limits for BLER (<10%), PRB (<80%), SNR (>5 dB). Instant, interpretable. |
| 2 | **Peer Comparison** | Z-score / cross-cell | A cell with BLER=8% is "OK" vs threshold but suspect if all peers are at 2%. |
| 3 | **Trend** | Linear regression | Gradual MCS degradation or rising HARQ NACK rate — early warning before threshold fires. |
| 4 | **IQR** | Robust / distribution-free | L1 counters are often skewed (HARQ NACK counts). IQR handles non-Gaussian distributions. |
| 5 | **CUSUM** | Sequential / change-point | Catches persistent drift in SNR or PRB utilisation that per-point methods miss. |
| 6 | **Bollinger Bands** | Rolling envelope | Detects transient interference spikes in SINR/RSRP that last only a few intervals. |
        """)

    with st.spinner("Running 6 L1/L2 detectors..."):
        stats_by_det  = detect_stats_anomalies_by_detector(parsed_stats)
        stats_anomalies = detect_stats_anomalies(parsed_stats)

    if not stats_anomalies:
        st.success("✅ No L1/L2 anomalies detected.")
    else:
        render_anomaly_distribution_charts(stats_anomalies, "Stats")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🔴 Critical", sum(1 for a in stats_anomalies if a["severity"] == "Critical"))
        c2.metric("🟠 High",     sum(1 for a in stats_anomalies if a["severity"] == "High"))
        c3.metric("🟡 Medium",   sum(1 for a in stats_anomalies if a["severity"] == "Medium"))
        c4.metric("🟢 Low",      sum(1 for a in stats_anomalies if a["severity"] == "Low"))

        # Method comparison matrix
        st.subheader("🔬 Method Comparison Matrix")
        DET_COLS  = ["Threshold", "Peer Comparison", "Trend", "IQR", "CUSUM", "Bollinger Bands"]
        SEV_BADGE = {"Critical": "🔴 Crit", "High": "🟠 High", "Medium": "🟡 Med", "Low": "🟢 Low"}
        SEV_R     = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

        matrix: Dict[str, Dict[str, str]] = {}
        for det_name, anoms in stats_by_det.items():
            for a in anoms:
                key = f"{a['label']} | {a['cell_id']}"
                matrix.setdefault(key, {})
                if SEV_R.get(a["severity"], 0) > SEV_R.get(matrix[key].get(det_name, ""), 0):
                    matrix[key][det_name] = a["severity"]

        if matrix:
            rows = []
            for key, det_sevs in list(matrix.items())[:60]:
                row = {"Metric | Cell": key}
                for det in DET_COLS:
                    sev = det_sevs.get(det, "")
                    row[det[:10]] = SEV_BADGE.get(sev, "✅") if sev else "✅"
                row["Confirmed by"] = f"{sum(1 for v in det_sevs.values() if v)}/{len(DET_COLS)}"
                rows.append(row)
            st.dataframe(pd.DataFrame(rows), use_container_width=True, height=300)

        # Anomaly table
        sev_filter = st.selectbox("Filter severity",
                                  ["All", "Critical", "High", "Medium", "Low"],
                                  key="stats_sev")
        shown = stats_anomalies if sev_filter == "All" else [
            a for a in stats_anomalies if a["severity"] == sev_filter
        ]
        _stats_anom_flat = pd.DataFrame([{
            "Severity": a["severity"],
            "Metric":   a["label"],
            "Cell":     a["cell_id"],
            "Value":    a["value"],
            "Unit":     a["unit"],
            "Warning":  a["warning"],
            "Critical": a["critical"],
            "Detector": a["detector"],
            "Evidence": a["evidence"][:80],
        } for a in shown])
        st.dataframe(_stats_anom_flat, use_container_width=True, height=350)

        # ── Inline Issue Analysis ─────────────────────────────────────────
        st.subheader("🔬 Issue Analysis")
        _stats_shown = shown[:20]
        if _stats_shown:
            _stats_labels = [
                f"#{i+1}  [{a['severity']}]  {a['label']}  |  {a['cell_id']}  |  {a['detector']}"
                for i, a in enumerate(_stats_shown)
            ]
            _stats_sel = st.selectbox(
                "Select issue to view analysis →",
                range(len(_stats_labels)),
                format_func=lambda i: _stats_labels[i],
                key="stats_issue_sel",
            )
            _sa = _stats_shown[_stats_sel]
            _SEV_ICON = {"Critical": "🚨", "High": "🔴", "Medium": "🟡", "Low": "🟢"}
            _sicon = _SEV_ICON.get(_sa["severity"], "⚪")

            st.markdown(f"#### {_sicon} {_sa['label']}  |  Cell: `{_sa['cell_id']}`")
            _sc1, _sc2 = st.columns(2)
            with _sc1:
                st.markdown("**Issue**")
                st.info(_sa["evidence"])
                st.markdown(
                    f"Value: **{_sa['value']} {_sa['unit']}** &nbsp;|&nbsp; "
                    f"Warning: {_sa['warning']} &nbsp;|&nbsp; Critical: {_sa['critical']}"
                )
            with _sc2:
                st.markdown("**Recommendation**")
                st.success(_sa["recommendation"])

            st.markdown("**🤖 LLM Analysis — RAG over 3GPP Specs**")
            _stats_exp_key = f"llm_stats_{_sa.get('label','')}_{_sa.get('cell_id','')}"
            if _stats_exp_key not in st.session_state:
                with st.spinner("Retrieving 3GPP specs + generating analysis..."):
                    st.session_state[_stats_exp_key] = explain_anomaly(_sa)
            _sexp = st.session_state[_stats_exp_key]
            _ssrc = _sexp.get("source", "")
            st.caption(f"🤖 {_ssrc}" if "Ollama" in _ssrc else f"📚 {_ssrc}")
            st.info(_sexp.get("hypothesis", "—"))
            if _sexp.get("citations"):
                st.markdown("**3GPP Citations**")
                for _cite in _sexp["citations"]:
                    st.markdown(f"- `{_cite.get('spec','')} §{_cite.get('section','')}` — {_cite.get('quote','')}")
            if _sexp.get("investigation_hints"):
                st.markdown("**Investigation Checklist**")
                for _hint in _sexp["investigation_hints"]:
                    st.markdown(f"- {_hint}")

            st.markdown("**Engineer Feedback**")
            render_feedback_button(
                event_id=_sa.get("label","") + "_" + _sa.get("cell_id",""),
                source="stats", anomaly_type=_sa.get("label",""),
                severity=_sa["severity"], detector=_sa.get("detector",""),
                cell_id=_sa.get("cell_id",""), evidence=_sa.get("evidence",""),
            )

    # ── Export Report ─────────────────────────────────────────────────
    _stats_export_sections = []
    if r.get("summary") and summary_rows:
        _stats_export_sections.append({
            "title": "L1-L2 Metric Health Summary",
            "df": pd.DataFrame(summary_rows),
        })
    if not _stats_df_cell.empty:
        _stats_export_sections.append({
            "title": "Per-Cell Metric Breakdown",
            "df": _stats_df_cell,
        })
    _stats_anom_df = pd.DataFrame([{
        "Severity": a["severity"], "Metric": a["label"],
        "Cell": a["cell_id"], "Value": a["value"], "Unit": a["unit"],
        "Warning": a["warning"], "Critical": a["critical"],
        "Detector": a["detector"], "Evidence": a["evidence"],
        "Recommendation": a["recommendation"],
    } for a in stats_anomalies]) if stats_anomalies else pd.DataFrame()
    if not _stats_anom_df.empty:
        _stats_export_sections.append({
            "title": "L1-L2 Anomalies",
            "df": _stats_anom_df,
            "notes": f"{len(stats_anomalies)} anomalies detected",
        })
    _stats_meta = {
        "Source File":   uploaded.name,
        "Data Type":     "DU/CU Stats",
        "Format":        r["format"].upper(),
        "Rows":          r["rows"],
        "Cells":         len(r["cells"]),
        "L1/L2 Metrics": len(r["l1l2_columns"]),
        "Anomalies":     len(stats_anomalies),
    }
    _stats_figures = (
        [{"title": f"Metric Trend: {_stats_trend_fig.layout.title.text}", "fig": _stats_trend_fig}]
        if _stats_trend_fig is not None else []
    )
    _stats_anomaly_cards = [
        {
            "severity":       a["severity"],
            "title":          f"{a['label']} | {a['cell_id']} | {a['detector']}",
            "evidence":       a["evidence"],
            "recommendation": a["recommendation"],
            "value":          a["value"],
            "unit":           a["unit"],
            "warning":        a["warning"],
            "critical":       a["critical"],
        }
        for a in stats_anomalies[:20]
    ]
    render_export_panel(
        _stats_export_sections, _stats_meta, "stats_report",
        figures=_stats_figures, anomaly_cards=_stats_anomaly_cards,
    )

    # ── Event Router ─────────────────────────────────────────────────
    shared_router.ingest(stats_anomalies, source="stats")

    # ── Prediction Layer ──────────────────────────────────────────────
    render_prediction_panel(parsed_stats, source="stats", router=shared_router)

    render_event_log(shared_router)

    st.stop()  # Stats path ends here

# ── Summary metrics ───────────────────────────────────────────────────
st.subheader("📊 Parsed Summary")

procedures = parsed.get('procedures', {})
message_log = parsed.get('message_log', [])
layer_counts = parsed.get('layer_event_counts', {})

# Group by layer
ALL_LAYERS = ["NAS", "NGAP", "RRC", "F1AP", "E1AP", "XnAP"]
by_layer = {l: {} for l in ALL_LAYERS}
for proc_name, stats in procedures.items():
    layer = stats.get('layer', 'NAS')
    if layer in by_layer:
        by_layer[layer][proc_name] = stats

col1, col2, col3 = st.columns(3)
col1.metric("Total signalling events", f"{parsed.get('total_events', 0):,}")
col2.metric("Procedures tracked",      len(procedures))
col3.metric("Parser version",          parsed.get('parser_version', '?'))

col4, col5, col6, col7, col8, col9 = st.columns(6)
for col, lyr in zip([col4, col5, col6, col7, col8, col9], ALL_LAYERS):
    col.metric(f"{lyr} procs", len(by_layer[lyr]))

# ── Per-layer procedure tables ────────────────────────────────────────
st.subheader("📋 Procedure-Level Counters")

if not procedures:
    st.warning("No 5G procedures found in this capture.")
    st.info(
        "For test data: run `python scripts/generate_test_pcap.py` "
        "then upload `data/raw/test_5g_full.pcap`"
    )
else:
    LAYER_TABS = [
        ("All Layers",          "all"),
        ("NAS — TS 24.501",     "NAS"),
        ("NGAP — TS 38.413",    "NGAP"),
        ("RRC — TS 38.331",     "RRC"),
        ("F1AP — TS 38.473",    "F1AP"),
        ("E1AP — TS 38.463",    "E1AP"),
        ("XnAP — TS 38.423",    "XnAP"),
    ]
    LAYER_CAPTIONS = {
        "NAS":  "5G Mobility + Session Management (TS 24.501)",
        "NGAP": "N2 interface: gNB-CU ↔ AMF (TS 38.413)",
        "RRC":  "Uu interface: UE ↔ gNB (TS 38.331)",
        "F1AP": "F1 interface: gNB-DU ↔ gNB-CU-CP (TS 38.473)",
        "E1AP": "E1 interface: gNB-CU-CP ↔ gNB-CU-UP (TS 38.463)",
        "XnAP": "Xn interface: gNB ↔ gNB, MR-DC (TS 38.423)",
    }

    tabs = st.tabs([t for t, _ in LAYER_TABS])

    with tabs[0]:
        st.dataframe(make_proc_table(procedures), use_container_width=True)

    for i, (_, layer_key) in enumerate(LAYER_TABS[1:], start=1):
        with tabs[i]:
            if by_layer[layer_key]:
                st.caption(LAYER_CAPTIONS[layer_key])
                st.dataframe(make_proc_table(by_layer[layer_key]), use_container_width=True)
            else:
                st.info(f"No {layer_key} procedures found in this capture.")

    # ── Failure cause breakdown ───────────────────────────────────────
    st.subheader("🔍 Failure Cause Breakdown")
    any_failures = any(s["failure_causes"] for s in procedures.values())
    if not any_failures:
        st.success("No failures found in this capture.")
    else:
        for proc_name, stats in procedures.items():
            layer = stats.get('layer', 'NAS')
            if stats["failure_causes"]:
                with st.expander(f"[{layer}] {proc_name} — failure causes"):
                    causes_df = pd.DataFrame([
                        {"Cause": cause, "Count": count}
                        for cause, count in sorted(
                            stats["failure_causes"].items(), key=lambda x: x[1], reverse=True
                        )
                    ])
                    st.dataframe(causes_df, use_container_width=True)

    # ── Message log with IE viewer ────────────────────────────────────
    if message_log:
        st.subheader("📨 Message Log & IE Inspector")
        st.caption(
            "Every decoded message with its Information Elements. "
            "Expand a row to see extracted IEs vs. spec-defined IEs."
        )
        layer_filter = st.selectbox(
            "Filter by layer", ["All"] + ALL_LAYERS, key="msg_log_filter"
        )
        filtered_log = [
            e for e in message_log
            if layer_filter == "All" or e["layer"] == layer_filter
        ]
        st.caption(f"Showing {len(filtered_log)} of {len(message_log)} events")

        for evt in filtered_log[:200]:   # cap at 200 rows for performance
            role_icon = {"request": "→", "response": "✓", "failure": "✗",
                         "timeout": "⏱"}.get(evt["role"], "•")
            label = (
                f"[{evt['layer']}] {evt['procedure']}  "
                f"{role_icon}  UE={evt['ue_id']}  "
                f"IEs: {evt['observed_ie_count']}/{evt['expected_ie_count']}"
            )
            with st.expander(label, expanded=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Observed IEs** (extracted from capture)")
                    if evt["ies"]:
                        ie_df = pd.DataFrame([
                            {"IE Name": k, "Value": v}
                            for k, v in evt["ies"].items()
                        ])
                        st.dataframe(ie_df, use_container_width=True)
                    else:
                        st.info("No IEs extracted (synthetic PCAP or pyshark dissection unavailable)")
                with c2:
                    st.markdown("**Missing Mandatory IEs** (per 3GPP spec)")
                    if evt["mandatory_missing"]:
                        for ie_name in evt["mandatory_missing"]:
                            st.warning(f"• {ie_name}")
                    else:
                        st.success("All mandatory IEs present (or message uses synthetic payload)")

# ── Raw output ────────────────────────────────────────────────────────
if show_raw:
    with st.expander("Raw parser output (JSON)"):
        st.json(parsed)

# ── Detection — real ──────────────────────────────────────────────────
st.divider()
st.subheader("⚠️ Anomaly Detection — 6-Detector Ensemble")

# ── Detector rationale ────────────────────────────────────────────────
with st.expander("📖 Why these 6 detectors? (reviewer rationale)", expanded=False):
    st.markdown("""
| # | Detector | Type | Why we use it |
|---|----------|------|---------------|
| 1 | **Isolation Forest** | Unsupervised / tree-based | No label data needed — anomalies are rare in telecom (most procedures succeed). Trees isolate anomalies in fewer splits. O(n log n), scales to thousands of procedures. No distribution assumption. |
| 2 | **Statistical (Threshold + Cascade)** | Rule-based / domain knowledge | Encodes 3GPP SLA thresholds directly. 100% interpretable. Catches known patterns: timeout concentration, cascading NAS→NGAP→RRC failures. Baseline every ML method is measured against. |
| 3 | **One-Class SVM** | Kernel / geometric boundary | Learns a non-linear boundary around normal data in kernel space. Complements IF: where IF uses tree depth, SVM uses geometric margin. Better when the normal cluster is compact and non-Gaussian. |
| 4 | **LOF (Local Outlier Factor)** | Density / local comparison | Compares each procedure to its k-nearest neighbors. IF and SVM are *global* — LOF catches *local* outliers: a procedure with 85% SR in a cluster where all peers are >99%. |
| 5 | **Elliptic Envelope** | Statistical / Mahalanobis | Fastest interpretable baseline. Fits a multivariate Gaussian; flags points with high Mahalanobis distance. When the normal cluster is elliptical (stable networks), this is the most reliable detector. Sanity-checks the ML methods. |
| 6 | **LSTM Autoencoder** | Deep learning / sequential | 5G signaling is sequential: Registration→Auth→Security→PDU Session. Tabular methods treat each procedure independently. The LSTM learns *normal sequences*; unusual orderings or gaps produce high reconstruction error. Only method that catches procedure-order violations. |

**Multi-detector agreement** — when ≥ 2 detectors flag the same procedure, confidence is higher.
IF alone may have false positives from contamination tuning; SVM alone can over-reject at boundaries.
The ensemble cross-validates each finding.
    """)

SEV_COLOR = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}

with st.spinner("Running 6 detectors: Isolation Forest · Statistical · OC-SVM · LOF · Elliptic Envelope · LSTM Autoencoder..."):
    by_detector = detect_anomalies_by_detector(parsed)
    anomalies   = merge_detector_results(by_detector)

if not anomalies:
    st.success("✅ No anomalies detected across all three detectors.")
else:
    # ── Summary metrics ───────────────────────────────────────────────
    high   = sum(1 for a in anomalies if a["severity"] == "High")
    medium = sum(1 for a in anomalies if a["severity"] == "Medium")
    low    = sum(1 for a in anomalies if a["severity"] == "Low")
    confirmed = sum(1 for a in anomalies if a.get("confirmed_by", 1) > 1)

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("🔴 High severity",   high)
    mc2.metric("🟡 Medium severity", medium)
    mc3.metric("🟢 Low severity",    low)
    mc4.metric("🔁 Multi-detector confirmed", confirmed)

    # ── Method comparison matrix ──────────────────────────────────────
    st.subheader("🔬 Method Comparison Matrix")
    st.caption(
        "Which detector flagged which procedure. "
        "🔴 High · 🟡 Medium · 🟢 Low · ✅ Not flagged"
    )

    DETECTOR_COLS = [
        "Isolation Forest", "Statistical", "One-Class SVM",
        "LOF", "Elliptic Envelope", "LSTM Autoencoder",
    ]
    SEV_BADGE = {"High": "🔴 High", "Medium": "🟡 Med", "Low": "🟢 Low"}

    # Build {procedure → {detector → severity}}
    proc_det_map: Dict[str, Dict[str, str]] = {}
    all_procs = set(a["procedure"] for anoms in by_detector.values() for a in anoms)
    for proc in sorted(all_procs):
        proc_det_map[proc] = {}
        for det_name in DETECTOR_COLS:
            for a in by_detector.get(det_name, []):
                if a["procedure"] == proc:
                    proc_det_map[proc][det_name] = a["severity"]
                    break

    if proc_det_map:
        matrix_rows = []
        for proc, det_sevs in proc_det_map.items():
            row = {"Procedure": proc}
            agreement = sum(1 for v in det_sevs.values() if v)
            for det in DETECTOR_COLS:
                sev = det_sevs.get(det, "")
                row[det[:12]] = SEV_BADGE.get(sev, "✅") if sev else "✅"
            row["Agreement"] = f"{agreement}/{len(DETECTOR_COLS)} detectors"
            matrix_rows.append(row)

        st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True, height=350)
    else:
        st.success("No procedures flagged by any detector.")

    # ── Anomaly table ─────────────────────────────────────────────────
    sev_filter = st.selectbox(
        "Filter by severity", ["All", "High", "Medium", "Low"], key="sev_filter"
    )
    shown = [a for a in anomalies if sev_filter == "All" or a["severity"] == sev_filter]
    _pcap_flat = pd.DataFrame([{
        "Severity":  a["severity"],
        "Layer":     a.get("layer", "—"),
        "Procedure": a.get("procedure", "—"),
        "Type":      a["type"],
        "Score":     round(a["score"], 3),
        "Detector":  a["detector"],
        "Confirmed": f"✅ {a['confirmed_by']} detectors" if a.get("confirmed_by", 1) > 1 else "—",
        "Evidence":  a["evidence"][:80],
    } for a in shown])
    st.dataframe(_pcap_flat, use_container_width=True, height=350)

    # ── Export Report ─────────────────────────────────────────────────
    _pcap_proc_df = make_proc_table(procedures)
    _pcap_anom_df = pd.DataFrame([{
        "Severity":     a["severity"],
        "Layer":        a.get("layer", "—"),
        "Procedure":    a.get("procedure", "—"),
        "Type":         a["type"],
        "Score":        round(a["score"], 3),
        "Detector":     a["detector"],
        "Cell":         a.get("cell_id", "—"),
        "Evidence":     a["evidence"],
        "Recommendation": a["recommendation"],
    } for a in anomalies]) if anomalies else pd.DataFrame()

    _pcap_export_sections = []
    if not _pcap_proc_df.empty:
        _pcap_export_sections.append({"title": "Procedure Counters", "df": _pcap_proc_df})
    if not _pcap_anom_df.empty:
        _pcap_export_sections.append({
            "title": "Anomaly Detection Results",
            "df": _pcap_anom_df,
            "notes": f"{len(anomalies)} anomalies detected",
        })
    _pcap_meta = {
        "Source File":        uploaded.name,
        "Data Type":          "PCAP (5G Signalling)",
        "Total Events":       parsed.get("total_events", 0),
        "Procedures Tracked": len(procedures),
        "Anomalies":          len(anomalies),
        "Parser Version":     parsed.get("parser_version", "—"),
    }
    _pcap_anomaly_cards = [
        {
            "severity":       a["severity"],
            "title":          f"{a.get('type','?')} | {a.get('procedure','?')} | {a['detector']}",
            "evidence":       a["evidence"],
            "recommendation": a["recommendation"],
            "value":          round(a["score"], 3),
            "unit":           "score",
            "warning":        "—",
            "critical":       "—",
        }
        for a in anomalies[:20]
    ]
    render_export_panel(
        _pcap_export_sections, _pcap_meta, "pcap_report",
        anomaly_cards=_pcap_anomaly_cards,
    )

    # ── Inline Issue Analysis ─────────────────────────────────────────
    st.subheader("🔬 Issue Analysis — RAG over 3GPP Specs")
    _pcap_status = ollama_status()
    if _pcap_status["available"]:
        st.success(f"✅ {_pcap_status['mode']} — model: `{_pcap_status['model']}`")
    else:
        st.info(
            f"ℹ️ Running in **{_pcap_status['mode']}** mode — "
            f"{_pcap_status.get('message', 'Ollama not available')}  \n"
            "To enable LLM: `ollama pull phi3:mini` then restart the dashboard."
        )

    _pcap_shown = shown[:20]
    if _pcap_shown:
        _pcap_labels = [
            f"#{i+1}  [{a['severity']}]  {a['type']}  |  "
            f"{a.get('procedure','?')}  |  {a['detector']}"
            for i, a in enumerate(_pcap_shown)
        ]
        _pcap_sel = st.selectbox(
            "Select issue to view analysis →",
            range(len(_pcap_labels)),
            format_func=lambda i: _pcap_labels[i],
            key="pcap_issue_sel",
        )
        _pa = _pcap_shown[_pcap_sel]
        _SEV_ICON = {"High": "🔴", "Medium": "🟡", "Low": "🟢", "Critical": "🚨"}
        _picon = _SEV_ICON.get(_pa["severity"], "⚪")

        st.markdown(
            f"#### {_picon} {_pa['type']}  |  "
            f"[{_pa.get('layer','?')}] `{_pa.get('procedure','?')}`"
        )
        _pc1, _pc2 = st.columns(2)
        with _pc1:
            st.markdown("**Issue**")
            st.info(_pa["evidence"])
            if _pa.get("failure_causes"):
                st.markdown("**Failure Causes**")
                _causes_df = pd.DataFrame([
                    {"Cause": k, "Count": v}
                    for k, v in sorted(_pa["failure_causes"].items(),
                                       key=lambda x: x[1], reverse=True)
                ])
                st.dataframe(_causes_df, use_container_width=True)
        with _pc2:
            st.markdown("**Recommendation**")
            st.success(_pa["recommendation"])
            st.markdown(
                f"**Layer:** `{_pa.get('layer','?')}` &nbsp; "
                f"**Procedure:** `{_pa.get('procedure','?')}` &nbsp; "
                f"**Score:** `{_pa['score']:.3f}`"
            )
            if _pa.get("confirmed_by", 1) > 1:
                st.markdown(
                    f"**Confirmed by {_pa['confirmed_by']} detectors** — high confidence."
                )

        st.markdown("**🤖 LLM Analysis**")
        _pcap_exp_key = f"llm_pcap_{_pa.get('type','')}_{_pa.get('procedure','')}"
        if _pcap_exp_key not in st.session_state:
            with st.spinner("Retrieving 3GPP specs + generating analysis..."):
                st.session_state[_pcap_exp_key] = explain_anomaly(_pa)
        _pexp = st.session_state[_pcap_exp_key]
        _psrc = _pexp.get("source", "")
        st.caption(f"🤖 {_psrc}" if "Ollama" in _psrc else f"📚 {_psrc}")
        st.info(_pexp.get("hypothesis", "—"))
        if _pexp.get("citations"):
            st.markdown("**3GPP Citations**")
            for _cite in _pexp["citations"]:
                st.markdown(f"- `{_cite.get('spec','')} §{_cite.get('section','')}` — {_cite.get('quote','')}")
        if _pexp.get("investigation_hints"):
            st.markdown("**Investigation Checklist**")
            for _hint in _pexp["investigation_hints"]:
                st.markdown(f"- {_hint}")

        st.markdown("**Engineer Feedback**")
        render_feedback_button(
            event_id=_pa.get("type","") + "_" + _pa.get("procedure",""),
            source="pcap", anomaly_type=_pa.get("type",""),
            severity=_pa["severity"], detector=_pa.get("detector",""),
            cell_id=_pa.get("cell_id","—"), evidence=_pa.get("evidence",""),
        )

# ── Event Router — PCAP path ──────────────────────────────────────────
if parsed is not None and anomalies:
    shared_router.ingest(anomalies, source="pcap")
    render_event_log(shared_router)
