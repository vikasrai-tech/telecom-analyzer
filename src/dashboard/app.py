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
from src.orchestrator.event_router import EventRouter
from src.detection.predictor import run_prediction
from src.feedback.store import save_feedback, load_feedback, feedback_stats
from src.llm.explainer import explain_anomaly, ollama_status

st.set_page_config(
    page_title="Unified Telecom Analyzer",
    page_icon="📡",
    layout="wide",
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


def render_prediction_panel(parsed: Dict, source: str) -> None:
    """Run prediction layer and show predicted anomalies."""
    st.divider()
    st.subheader("🔮 Prediction Layer — Forecast Ahead (Phase II)")
    st.caption("LSTM + Prophet: predicts anomalies up to 4h in advance · tagged state=predicted")

    with st.expander("📖 Why LSTM + Prophet? (reviewer rationale)", expanded=False):
        st.markdown("""
| Method | Type | Why |
|--------|------|-----|
| **Prophet** | Bayesian structural time-series | Handles seasonality, trends, and missing data. Produces confidence intervals. Best for KPIs with daily/weekly patterns (PRB load, throughput). |
| **LSTM** | Deep learning / sequence | Captures nonlinear dependencies between metrics. Better than Prophet when there's no clear seasonality — L1/L2 counters like HARQ NACK rate or BLER show abrupt non-seasonal shifts. |

**Complementary:** Prophet catches slow degradation early; LSTM catches sudden pattern breaks.
**Lead time:** Default 4h — gives NOC engineers time to act before threshold breach.
        """)

    horizon_h = st.slider("Forecast horizon (hours)", 1, 12, 4, key=f"horizon_{source}")

    with st.spinner(f"Running LSTM + Prophet forecast ({horizon_h}h ahead)..."):
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

    p1, p2, p3 = st.columns(3)
    p1.metric("Predicted anomalies", len(all_predicted))
    p2.metric("🔮 Prophet", len(pred_by_method.get("prophet", [])))
    p3.metric("🧠 LSTM",    len(pred_by_method.get("lstm", [])))

    SEV_ICON = {"Critical": "🚨", "High": "🔴", "Medium": "🟡", "Low": "🟢"}
    router = EventRouter()
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

# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Upload Data")
    data_type = st.radio("Data type", ["PCAP", "DU/CU Stats", "KPI Time-series"])
    ext_map = {
        "PCAP":             ["pcap", "pcapng"],
        "DU/CU Stats":      ["csv", "parquet"],
        "KPI Time-series":  ["csv", "xlsx", "xls", "parquet"],
    }
    uploaded = st.file_uploader(f"Upload {data_type} file",
                               type=ext_map.get(data_type, ["pcap"]))
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
                st.markdown("**Engineer Feedback**")
                render_feedback_button(
                    event_id=a.get("label","") + "_" + a.get("cell_id",""),
                    source="kpi", anomaly_type=a.get("label",""),
                    severity=a["severity"], detector=a.get("detector",""),
                    cell_id=a.get("cell_id",""), evidence=a.get("evidence",""),
                )

    # ── Prediction Layer ──────────────────────────────────────────────
    render_prediction_panel(parsed_kpi, source="kpi")

    # ── Event Router ─────────────────────────────────────────────────
    kpi_router = EventRouter()
    kpi_router.ingest(kpi_anomalies, source="kpi")
    render_event_log(kpi_router)

    st.stop()  # KPI path ends here

# ══════════════════════════════════════════════════════════════════════
# STATS DASHBOARD (DU/CU Stats path — srsRAN / OAI / NIST)
# ══════════════════════════════════════════════════════════════════════
if is_stats and parsed_stats:
    import plotly.express as px

    r = parsed_stats
    st.subheader("📡 DU/CU Stats Overview")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Rows",          r["rows"])
    m2.metric("Cells",         len(r["cells"]))
    m3.metric("L1/L2 Metrics", len(r["l1l2_columns"]))
    m4.metric("Format",        r["format"].upper())
    m5.metric("Time Range",
              f"{str(r['time_range'][0])[:16]} → {str(r['time_range'][1])[:16]}"
              if r["time_range"][0] else "—")

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
            meta = stats_get_meta(sel_metric)
            fig  = px.line(df_line, x=ts_col, y="value", title=title,
                           labels={"value": f"{sel_metric} ({meta['unit']})", ts_col: "Time"})
            if meta.get("warning") is not None:
                fig.add_hline(y=meta["warning"],  line_dash="dot",
                              line_color="orange", annotation_text="Warning")
            if meta.get("critical") is not None:
                fig.add_hline(y=meta["critical"], line_dash="dot",
                              line_color="red",   annotation_text="Critical")
            st.plotly_chart(fig, use_container_width=True)

    # ── Per-Cell Heatmap ──────────────────────────────────────────────
    st.subheader("🗺️ Per-Cell Metric Breakdown")
    if l1l2_cols and cell_col:
        df_all  = pd.DataFrame(r["df_records"])
        df_cell = df_all.groupby(cell_col)[l1l2_cols].mean().round(3).reset_index()
        st.dataframe(df_cell, use_container_width=True, height=300)

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
        SEV_ICON = {"Critical": "🚨", "High": "🔴", "Medium": "🟡", "Low": "🟢"}
        for a in shown[:20]:
            icon = SEV_ICON.get(a["severity"], "⚪")
            with st.expander(
                f"{icon} [{a['severity']}] {a['label']} | {a['cell_id']} | {a['detector']}",
                expanded=(a["severity"] in ("Critical", "High")),
            ):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Evidence**")
                    st.info(a["evidence"])
                    st.markdown(
                        f"Value: **{a['value']} {a['unit']}** &nbsp;|&nbsp; "
                        f"Warning: {a['warning']} &nbsp;|&nbsp; Critical: {a['critical']}"
                    )
                with c2:
                    st.markdown("**Recommendation**")
                    st.success(a["recommendation"])
                st.markdown("**Engineer Feedback**")
                render_feedback_button(
                    event_id=a.get("label","") + "_" + a.get("cell_id",""),
                    source="stats", anomaly_type=a.get("label",""),
                    severity=a["severity"], detector=a.get("detector",""),
                    cell_id=a.get("cell_id",""), evidence=a.get("evidence",""),
                )

    # ── Prediction Layer ──────────────────────────────────────────────
    render_prediction_panel(parsed_stats, source="stats")

    # ── Event Router ─────────────────────────────────────────────────
    stats_router = EventRouter()
    stats_router.ingest(stats_anomalies, source="stats")
    render_event_log(stats_router)

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
            st.markdown("**Engineer Feedback**")
            render_feedback_button(
                event_id=a.get("type","") + "_" + a.get("procedure",""),
                source="pcap", anomaly_type=a.get("type",""),
                severity=a["severity"], detector=a.get("detector",""),
                cell_id=a.get("cell_id","—"), evidence=a.get("evidence",""),
            )

    # ── LLM explanation — RAG + Ollama ───────────────────────────────
    st.subheader("🤖 LLM Explanation — RAG over 3GPP Specs")

    # Ollama status badge
    status = ollama_status()
    if status["available"]:
        st.success(f"✅ {status['mode']} — model: `{status['model']}`")
    else:
        st.info(
            f"ℹ️ Running in **{status['mode']}** mode — "
            f"{status.get('message', 'Ollama not available')}  \n"
            "To enable LLM: `ollama pull phi3:mini` then restart the dashboard."
        )

    top_anomalies = [a for a in anomalies if a["severity"] in ("High", "Medium")][:4]
    if not top_anomalies:
        top_anomalies = anomalies[:2]

    SEV_ICON = {"High": "🔴", "Medium": "🟡", "Low": "🟢", "Critical": "🚨"}

    for a in top_anomalies:
        icon   = SEV_ICON.get(a["severity"], "⚪")
        header = f"{icon} [{a['severity']}] {a['type']}"
        with st.expander(header, expanded=(a["severity"] == "High")):
            with st.spinner("Retrieving 3GPP specs + generating explanation..."):
                exp = explain_anomaly(a)

            src = exp.get("source", "")
            if "Ollama" in src:
                st.caption(f"🤖 Generated by {src}")
            else:
                st.caption(f"📚 {src}")

            st.markdown("**Hypothesis**")
            st.info(exp.get("hypothesis", "—"))

            citations = exp.get("citations", [])
            if citations:
                st.markdown("**3GPP Citations**")
                for cite in citations:
                    spec    = cite.get("spec", "")
                    section = cite.get("section", "")
                    quote   = cite.get("quote", "")
                    st.markdown(f"- `{spec} §{section}` — {quote}")

            hints = exp.get("investigation_hints", [])
            if hints:
                st.markdown("**Investigation Checklist**")
                for hint in hints:
                    st.markdown(f"- {hint}")

# ── Event Router — PCAP path ──────────────────────────────────────────
if parsed is not None and anomalies:
    pcap_router = EventRouter()
    pcap_router.ingest(anomalies, source="pcap")
    render_event_log(pcap_router)
