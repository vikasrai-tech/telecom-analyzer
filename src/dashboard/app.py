"""
Unified Telecom Analyzer — Dashboard
=====================================
Presentation layer only. Business logic lives in src/parsers/, src/detection/, src/llm/.

CURRENT STATE:
  ✅ PCAP parser      — real (NAS / NGAP / RRC / F1AP / E1AP / XnAP)
  ✅ Detection engine — real (6 detectors: IF · Statistical · OC-SVM · LOF · EE · LSTM-AE)
  ✅ KPI parser       — real (Excel/CSV gNB KPI exports)
  ✅ KPI detection    — real (Threshold + Peer Comparison + Trend)
  🔶 LLM explainer   — stub (Phi-3 Mini RAG coming Week 11-14)
"""

import streamlit as st
import pandas as pd
import tempfile
import os
from pathlib import Path
from typing import Dict
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.parsers.pcap_parser_real import parse_pcap as parse_pcap_real
from src.parsers.kpi_parser import parse_kpi_file
from src.detection.detector import detect_anomalies_by_detector, merge_detector_results
from src.detection.kpi_detector import (
    detect_kpi_anomalies, detect_kpi_anomalies_by_detector, kpi_summary_table
)
from src.llm.explainer import explain_anomaly_stub

st.set_page_config(
    page_title="Unified Telecom Analyzer",
    page_icon="📡",
    layout="wide",
)

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
    "Detection and LLM: stubs (coming Week 6-14)"
)

# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Upload Data")
    data_type = st.radio("Data type", ["PCAP", "DU/CU Stats", "KPI Time-series"])
    ext_map = {
        "PCAP": ["pcap", "pcapng"],
        "DU/CU Stats / KPI": ["csv", "xlsx", "xls"],
    }
    uploaded = st.file_uploader(f"Upload {data_type} file",
                               type=ext_map.get(data_type, ["pcap"]))
    st.divider()

    st.subheader("Parser Status")
    if data_type == "DU/CU Stats / KPI":
        st.success("✅ KPI parser active")
        st.markdown("""
        **Accepts:** Excel (.xlsx) or CSV

        **KPI categories:**
        - Availability · Accessibility
        - Retainability · Mobility
        - Capacity (PRB) · Throughput
        - Radio Quality (CQI/SINR/BLER)
        - Latency · RACH · Scheduling

        **Sample file:**
        `data/raw/5G_Network_KPI_Sample.xlsx`
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
    else:
        st.warning("🔶 Stub parser (coming soon)")

    st.divider()
    show_raw = st.checkbox("Show raw parser output", value=False)

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
        st.warning("**LLM Explainer**\n\nStub 🔶\n\nPhi-3 Mini RAG coming\n3GPP spec retrieval coming\n(Week 11-14)")
    st.stop()

# ── Parse ─────────────────────────────────────────────────────────────
st.success(f"✅ Received: `{uploaded.name}` ({uploaded.size:,} bytes)")

suffix = uploaded.name.split('.')[-1].lower()
is_kpi = data_type == "DU/CU Stats / KPI"

with st.spinner("🔍 Parsing file..."):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name

        if is_kpi:
            parsed_kpi = parse_kpi_file(tmp_path)
            parsed = None
        else:
            parsed = parse_pcap_real(tmp_path)
            parsed_kpi = None

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
    st.subheader("📊 KPI Overview")

    r = parsed_kpi
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Rows",           r["rows"])
    m2.metric("Unique Cells",   len(r["cells"]))
    m3.metric("Unique gNBs",    len(r["gnbs"]))
    m4.metric("KPI Columns",    len(r["kpi_columns"]))
    m5.metric("Time Range",     f"{r['time_range'][0][:16]} → {r['time_range'][1][:16]}")

    # ── KPI Summary Table ─────────────────────────────────────────────
    st.subheader("🚦 KPI Health Summary")
    st.caption("🟢 OK  🟡 Warning  🔴 Critical  (based on mean value vs thresholds)")

    summary_rows = kpi_summary_table(parsed_kpi)
    if summary_rows:
        df_summary = pd.DataFrame(summary_rows)
        st.dataframe(df_summary, use_container_width=True, height=420)

    # ── KPI Trend Charts ──────────────────────────────────────────────
    st.subheader("📈 KPI Trend Explorer")
    kpi_cols = r["kpi_columns"]
    ts_col   = r["timestamp_col"]
    cell_col = r["cell_col"]

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
            meta = get_meta(sel_kpi)
            fig  = px.line(df_line, x=ts_col, y="value", title=title,
                           labels={"value": f"{sel_kpi} ({meta.get('unit','')})",
                                   ts_col: "Time"})
            # Add warning / critical lines
            if meta.get("warning") is not None:
                fig.add_hline(y=meta["warning"],  line_dash="dot",
                              line_color="orange", annotation_text="Warning")
            if meta.get("critical") is not None:
                fig.add_hline(y=meta["critical"], line_dash="dot",
                              line_color="red",    annotation_text="Critical")
            st.plotly_chart(fig, use_container_width=True)

    # ── Per-Cell KPI Heatmap ──────────────────────────────────────────
    st.subheader("🗺️ Per-Cell KPI Breakdown")
    if kpi_cols and cell_col:
        df_all = pd.DataFrame(r["df_records"])
        gnb_col = r.get("gnb_col", "")
        group_cols = [cell_col] + ([gnb_col] if gnb_col else [])
        df_cell = df_all.groupby(group_cols)[kpi_cols].mean().round(2).reset_index()
        df_cell = df_cell.sort_values(kpi_cols[0])
        st.dataframe(df_cell, use_container_width=True, height=350)

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
        kpi_by_detector = detect_kpi_anomalies_by_detector(parsed_kpi)
        kpi_anomalies   = sorted(
            [a for anoms in kpi_by_detector.values() for a in anoms],
            key=lambda a: ({"Critical":4,"High":3,"Medium":2,"Low":1}.get(a["severity"],0),
                           a.get("score", 0)),
            reverse=True,
        )

    if not kpi_anomalies:
        st.success("✅ No KPI anomalies detected.")
    else:
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
            st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True, height=320)

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

        # Expandable detail cards for top anomalies
        st.subheader("🔎 Top Anomaly Details")
        SEV_ICON = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}
        for a in kpi_anomalies[:15]:
            icon   = SEV_ICON.get(a["severity"], "⚪")
            header = (f"{icon} [{a['severity']}] {a['label']} | "
                      f"{a['cell_id']} | {a['detector']}")
            with st.expander(header, expanded=(a["severity"] == "Critical")):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Evidence**")
                    st.info(a["evidence"])
                    st.markdown(
                        f"Value: **{a['value']} {a['unit']}** &nbsp;|&nbsp; "
                        f"Warning: {a['warning']} &nbsp;|&nbsp; "
                        f"Critical: {a['critical']}"
                    )
                with c2:
                    st.markdown("**Recommendation**")
                    st.success(a["recommendation"])

    st.stop()  # KPI path ends here — skip PCAP sections below

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

    for a in shown:
        icon  = SEV_COLOR.get(a["severity"], "⚪")
        badge = " ✅ confirmed" if a.get("confirmed_by", 1) > 1 else ""
        header = (
            f"{icon} [{a['severity']}] {a['type']}  "
            f"| score={a['score']:.3f} | {a['detector']}{badge}"
        )
        with st.expander(header, expanded=(a["severity"] == "High")):
            c1, c2 = st.columns(2)

            with c1:
                st.markdown("**Evidence**")
                st.info(a["evidence"])

                if a.get("failure_causes"):
                    st.markdown("**Failure causes**")
                    causes_df = pd.DataFrame([
                        {"Cause": k, "Count": v}
                        for k, v in sorted(a["failure_causes"].items(),
                                           key=lambda x: x[1], reverse=True)
                    ])
                    st.dataframe(causes_df, use_container_width=True)

            with c2:
                st.markdown("**Recommendation**")
                st.success(a["recommendation"])
                st.markdown(
                    f"**Layer:** `{a.get('layer','?')}` &nbsp; "
                    f"**Procedure:** `{a.get('procedure','?')}`"
                )
                if a.get("confirmed_by", 1) > 1:
                    st.markdown(
                        f"**Confirmed by {a['confirmed_by']} detectors** — "
                        "high confidence finding."
                    )

    # ── LLM explanation stub ──────────────────────────────────────────
    st.subheader("🤖 LLM Explanation")
    st.warning("🔶 Phi-3 Mini + RAG over 3GPP specs coming in Week 11-14.")
    top = [a for a in anomalies if a["severity"] in ("High", "Medium")][:3]
    for a in top:
        with st.expander(f"[{a['severity']}] {a['type']}"):
            exp = explain_anomaly_stub(a)
            st.markdown(f"**Hypothesis:** {exp['hypothesis']}")
            if exp.get("citations"):
                st.markdown("**3GPP Citations:**")
                for cite in exp["citations"]:
                    st.markdown(f"- `{cite['spec']} §{cite['section']}`: {cite['quote']}")
            if exp.get("investigation_hints"):
                st.markdown("**Investigation hints:**")
                for hint in exp["investigation_hints"]:
                    st.markdown(f"- {hint}")
