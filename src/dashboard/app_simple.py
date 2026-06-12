"""
Unified Telecom Analyzer — Simple Dashboard
Clean, easy-to-read view for demo and reviewer presentation.
"""

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

st.set_page_config(
    page_title="5G Network Anomaly Detector",
    page_icon="📡",
    layout="wide",
)

# ── CSS for clean cards ───────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #1a2a3a; border-radius: 10px;
    padding: 20px; text-align: center; margin: 4px;
}
.metric-num  { font-size: 2.4rem; font-weight: 700; }
.metric-lbl  { font-size: 0.9rem; color: #aaa; margin-top: 4px; }
.sev-critical { color: #ff4d4d; }
.sev-high     { color: #ff9400; }
.sev-medium   { color: #ffd700; }
.sev-low      { color: #2dc653; }
.sev-clean    { color: #2dc653; }
div[data-testid="stDataFrame"] { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────
SEV_ICON  = {"Critical": "🔴", "High": "🟠", "Medium": "🟡",
             "Low": "🟢", "Clean": "✅"}
SEV_ORDER = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "Clean": 0}

def sev_icon(s):
    return SEV_ICON.get(s, "⚪")

def run_pipeline(uploaded_file):
    suffix = Path(uploaded_file.name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(uploaded_file.read())
        tmp = f.name
    try:
        from src.orchestrator.pipeline import run_pipeline as _run
        result = _run(tmp, skip_llm=True)
        return result
    finally:
        os.unlink(tmp)

def plain_type(t: str) -> str:
    """Convert technical anomaly type to plain English."""
    t = t.replace(" anomaly", "").replace("_", " ")
    replacements = {
        "NAS Registration":        "Registration Failure",
        "NAS Authentication":      "Authentication Failure",
        "NAS PDUSession":          "Data Session Failure",
        "NAS SecurityMode":        "Security Setup Failure",
        "NGAP InitialContextSetup":"Initial Context Failure",
        "NGAP PDUSessionResource": "PDU Session Failure",
        "RRC Setup":               "Radio Connection Failure",
        "RRC Reestablishment":     "Radio Link Failure",
        "RRC Reconfiguration":     "Reconfiguration Anomaly",
        "F1AP UEContextSetup":     "UE Context Failure (DU-CU)",
        "E1AP BearerContext":      "Bearer Setup Failure",
        "XnAP HandoverRequest":    "Handover Failure",
        "Cascading failure":       "Cascading Failure",
        "Anomalous message sequence": "Sequence Order Violation",
    }
    for k, v in replacements.items():
        if k.lower() in t.lower():
            return v
    return t.title()

def plain_layer(layer: str) -> str:
    labels = {
        "NAS":  "Core (NAS)", "NGAP": "Core (NGAP)", "RRC":  "Radio (RRC)",
        "F1AP": "DU-CU (F1)", "E1AP": "DU-CU (E1)",  "XnAP": "Inter-gNB (Xn)",
        "KPI":  "KPI",        "kpi":  "KPI",          "stats":"L1/L2 Stats",
    }
    return labels.get(layer, layer or "—")

def fix_action(anomaly: dict) -> str:
    """Return one-line engineer action from anomaly evidence."""
    ev  = anomaly.get("evidence", "")
    rec = anomaly.get("recommendation", "")
    t   = anomaly.get("type", "")
    if rec:
        return rec.split(".")[0].strip()
    if "radio-connection" in ev or "rlf" in ev.lower():
        return "Check UE RF signal — possible coverage hole"
    if "congestion" in ev.lower() or "cause 22" in ev.lower() or "#22" in ev:
        return "Check AMF load — possible network congestion"
    if "timeout" in ev.lower():
        return "Check network timer configuration"
    if "auth" in t.lower():
        return "Check UE subscription and AUSF/UDM"
    if "handover" in t.lower() or "ho" in t.lower():
        return "Check HO parameters and neighbor cell coverage"
    if "bearer" in t.lower() or "pdu" in t.lower():
        return "Check UPF/SMF connectivity"
    if "bler" in ev.lower() or "snr" in ev.lower():
        return "Check antenna configuration and interference"
    if "prb" in ev.lower():
        return "Check PRB utilisation — possible capacity issue"
    return "Investigate and escalate to NOC"


# ── Header ────────────────────────────────────────────────────────────
st.title("📡 5G Network Anomaly Detector")
st.caption("Upload PCAP · KPI · Stats file — auto-detects format and finds anomalies")

# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📂 Upload File")
    uploaded = st.file_uploader(
        "Drop your file here",
        type=["pcap", "pcapng", "csv", "xlsx", "xls", "parquet"],
        help="PCAP trace · srsRAN/OAI/NIST stats CSV · KPI Excel"
    )
    st.divider()
    st.markdown("**Supported formats**")
    st.markdown("- 📦 PCAP trace (`.pcap`)\n- 📊 KPI Excel (`.xlsx`)\n- 📈 Stats CSV (`.csv`)\n- 🗃️ Parquet (`.parquet`)")
    st.divider()
    st.markdown("**Detection methods**")
    st.markdown("""
- Isolation Forest
- Statistical Rules
- One-Class SVM
- LOF
- Elliptic Envelope
- LSTM Autoencoder
    """)

# ── Landing page ──────────────────────────────────────────────────────
if uploaded is None:
    st.info("👈 Upload a file from the sidebar to start anomaly detection.")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.success("**PCAP Trace**\nDetects failures in NAS, NGAP, RRC, F1AP, E1AP, XnAP procedures")
    with c2:
        st.success("**KPI Time-Series**\nDetects degradation in 50 KPIs — throughput, BLER, PRB, handover")
    with c3:
        st.success("**DU/CU Stats**\nDetects L1/L2 anomalies in srsRAN, OAI, NIST format")
    st.stop()

# ── Run pipeline ──────────────────────────────────────────────────────
with st.spinner(f"🔍 Analysing `{uploaded.name}` ..."):
    try:
        result = run_pipeline(uploaded)
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

anomalies = result.get("anomalies", [])
pipeline  = result.get("pipeline", "pcap")
parsed    = result.get("parsed", {})

# ── Summary cards ─────────────────────────────────────────────────────
counts = {}
for a in anomalies:
    s = a.get("severity", "Low")
    counts[s] = counts.get(s, 0) + 1

total    = len(anomalies)
critical = counts.get("Critical", 0)
high     = counts.get("High", 0)
medium   = counts.get("Medium", 0)
low      = counts.get("Low", 0)

st.success(f"✅ File processed: `{uploaded.name}`  |  Pipeline: **{pipeline.upper()}**  |  Duration: **{result.get('duration_s', 0)}s**")
st.divider()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Anomalies", total)
col2.metric("🔴 Critical", critical)
col3.metric("🟠 High",     high)
col4.metric("🟡 Medium",   medium)
col5.metric("🟢 Low",      low)

if total == 0:
    st.success("## ✅ No anomalies detected — network looks healthy!")
    st.stop()

st.divider()

# ── Two column layout ─────────────────────────────────────────────────
left, right = st.columns([3, 2])

# ── LEFT: Anomaly table ───────────────────────────────────────────────
with left:
    st.subheader("🚨 Detected Anomalies")

    # Sort by severity
    sorted_anomalies = sorted(
        anomalies,
        key=lambda a: SEV_ORDER.get(a.get("severity", "Low"), 0),
        reverse=True
    )

    rows = []
    for a in sorted_anomalies:
        sev   = a.get("severity", "Low")
        layer = a.get("layer") or a.get("source") or "?"
        rows.append({
            "Sev":    f"{sev_icon(sev)} {sev}",
            "Issue":  plain_type(a.get("type", "")),
            "Where":  plain_layer(layer),
            "Cell":   str(a.get("cell_id") or "—"),
            "Action": fix_action(a),
        })

    df_table = pd.DataFrame(rows)
    st.dataframe(
        df_table,
        use_container_width=True,
        height=min(50 + len(rows) * 35, 500),
        hide_index=True,
    )

# ── RIGHT: Charts ─────────────────────────────────────────────────────
with right:
    st.subheader("📊 Summary")

    # Severity breakdown bar chart
    sev_df = pd.DataFrame([
        {"Severity": s, "Count": c}
        for s, c in sorted(counts.items(), key=lambda x: SEV_ORDER.get(x[0], 0), reverse=True)
    ])
    st.bar_chart(sev_df.set_index("Severity"), color="#00b4d8", height=200)

    # Protocol / source breakdown
    st.markdown("**By Protocol / Source**")
    layer_counts = {}
    for a in anomalies:
        lyr = plain_layer(a.get("layer") or a.get("source") or "Unknown")
        layer_counts[lyr] = layer_counts.get(lyr, 0) + 1

    lyr_df = pd.DataFrame([
        {"Layer": k, "Count": v}
        for k, v in sorted(layer_counts.items(), key=lambda x: x[1], reverse=True)
    ])
    st.dataframe(lyr_df, use_container_width=True, hide_index=True, height=200)

st.divider()

# ── Top findings detail ───────────────────────────────────────────────
st.subheader("🔎 Top Findings")

top = [a for a in sorted_anomalies if a.get("severity") in ("Critical", "High")][:5]
if not top:
    top = sorted_anomalies[:5]

for i, a in enumerate(top):
    sev    = a.get("severity", "Low")
    issue  = plain_type(a.get("type", ""))
    where  = plain_layer(a.get("layer") or a.get("source") or "?")
    action = fix_action(a)
    ev     = a.get("evidence", "—")
    cell   = a.get("cell_id") or "—"

    with st.expander(f"{sev_icon(sev)} [{sev}]  {issue}  —  {where}", expanded=(i == 0)):
        c1, c2 = st.columns(2)
        c1.markdown(f"**Cell / Source:** `{cell}`")
        c2.markdown(f"**Detected by:** `{a.get('detector', '—')}`")

        st.markdown("**What happened:**")
        st.info(ev)

        st.markdown("**What to do:**")
        st.success(action)

# ── PCAP extra: procedure health ─────────────────────────────────────
if pipeline == "pcap":
    st.divider()
    st.subheader("📋 Procedure Health")

    procs = parsed.get("procedures", {})
    if procs:
        proc_rows = []
        for name, stats in procs.items():
            sr = stats.get("success_rate", 100)
            status = "✅ OK" if sr >= 98 else ("🟡 Warning" if sr >= 90 else "🔴 Issue")
            proc_rows.append({
                "Protocol":     name.replace("_", " "),
                "Attempts":     stats.get("attempts", 0),
                "Failures":     stats.get("failure", 0),
                "Success Rate": f"{sr:.1f}%",
                "Status":       status,
            })
        proc_rows.sort(key=lambda r: r["Success Rate"])
        st.dataframe(pd.DataFrame(proc_rows), use_container_width=True, hide_index=True)

# ── KPI extra: health summary ─────────────────────────────────────────
if pipeline == "kpi":
    st.divider()
    st.subheader("📋 KPI Health Summary")

    from src.detection.kpi_detector import kpi_summary_table
    summary = kpi_summary_table(parsed)
    if summary:
        sum_rows = []
        for row in summary[:20]:
            status_map = {"🟢 OK": "✅ OK", "🟡 Warning": "🟡 Warning",
                          "🔴 Critical": "🔴 Critical"}
            sum_rows.append({
                "KPI":      row.get("label", row.get("kpi", "")),
                "Category": row.get("category", ""),
                "Value":    row.get("display_value", "—"),
                "Status":   row.get("status", "—"),
            })
        st.dataframe(pd.DataFrame(sum_rows), use_container_width=True,
                     hide_index=True, height=350)

# ── Stats extra: metric overview ─────────────────────────────────────
if pipeline == "stats":
    st.divider()
    st.subheader("📋 L1/L2 Metric Overview")

    summary = parsed.get("summary", {})
    if summary:
        from src.parsers.stats_parser import get_meta
        stat_rows = []
        for col, s in summary.items():
            if col in ("hour_of_day", "day_of_week"):
                continue
            meta = get_meta(col)
            warn = meta.get("warning")
            crit = meta.get("critical")
            mean_val = s.get("mean", 0)
            if crit is not None and warn is not None:
                if (meta.get("desc","").lower() in ("lower_better","") and
                        col in ("dl_bler","ul_bler","dl_prb_util","ul_prb_util",
                                "dl_harq_nack_rate","ul_harq_nack_rate","congestion_score")):
                    status = "🔴 Critical" if mean_val >= crit else ("🟡 Warning" if mean_val >= warn else "✅ OK")
                else:
                    status = "🔴 Critical" if mean_val <= crit else ("🟡 Warning" if mean_val <= warn else "✅ OK")
            else:
                status = "—"
            stat_rows.append({
                "Metric":  meta.get("desc", col),
                "Mean":    round(mean_val, 2),
                "Min":     round(s.get("min", 0), 2),
                "Max":     round(s.get("max", 0), 2),
                "Unit":    meta.get("unit", ""),
                "Status":  status,
            })
        st.dataframe(pd.DataFrame(stat_rows), use_container_width=True,
                     hide_index=True, height=350)

st.divider()
st.caption("5G Anomaly Detector · M.Tech Data Science · PES Bangalore — Great Learning")
