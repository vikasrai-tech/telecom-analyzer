"""
Walking skeleton dashboard for the Unified Telecom Analyzer.

This is intentionally minimal — every component is a stub that returns
fake data. The point is to wire up the *flow* end-to-end so that we can
replace one stub at a time with real implementations.

Run with: streamlit run src/dashboard/app.py
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Add src to path so we can import siblings
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.parsers.pcap_parser import parse_pcap_stub
from src.detection.detector import detect_anomalies_stub
from src.llm.explainer import explain_anomaly_stub


# ---- Page config ----
st.set_page_config(
    page_title="Unified Telecom Analyzer",
    page_icon="📡",
    layout="wide",
)

# ---- Header ----
st.title("📡 Unified Telecom Analyzer")
st.caption(
    "Walking skeleton — Phase I, Week 1. "
    "All components are stubs returning sample data."
)

# ---- Sidebar ----
with st.sidebar:
    st.header("Upload Data")
    data_type = st.radio(
        "Data type",
        ["PCAP", "DU/CU Stats", "KPI Time-series"],
        help="Choose which kind of data you are uploading.",
    )

    file_ext = {"PCAP": ["pcap", "pcapng"], "DU/CU Stats": ["csv"], "KPI Time-series": ["csv", "parquet"]}
    uploaded = st.file_uploader(
        f"Upload {data_type} file",
        type=file_ext[data_type],
    )

    st.divider()
    st.header("Settings")
    detector_choice = st.selectbox(
        "Detection algorithm",
        ["Isolation Forest (stub)", "LSTM Autoencoder (stub)"],
    )
    show_raw = st.checkbox("Show raw parsed data", value=False)

# ---- Main panel ----
if uploaded is None:
    st.info("👈 Upload a file in the sidebar to begin.")
    st.markdown(
        """
        ### What this dashboard does

        1. **Parses** the uploaded data (PCAP / stats / KPI) into a structured form.
        2. **Aggregates** procedure-level counters (for PCAP) — RRC Setup, NGAP,
           NAS Registration, PDU Session pass/fail rates.
        3. **Detects** anomalies using ML models trained on labelled telecom data.
        4. **Explains** detected anomalies using a local small LLM (Phi-3 Mini)
           with retrieval over 3GPP specifications.
        5. **Captures feedback** from engineers to improve future detections.

        > This is the walking skeleton. Each step currently returns demo data.
        """
    )
    st.stop()

# ---- File received: run the pipeline ----
st.success(f"Received `{uploaded.name}` ({uploaded.size:,} bytes)")

with st.spinner("Step 1 of 3: Parsing data..."):
    parsed = parse_pcap_stub(uploaded.name)

st.subheader("📊 Parsed Summary")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total events", parsed["total_events"])
col2.metric("RRC Setup attempts", parsed["procedures"]["RRC_Setup"]["attempts"])
col3.metric("Success rate", f'{parsed["procedures"]["RRC_Setup"]["success_rate"]:.1f}%')
col4.metric("Failure causes", len(parsed["procedures"]["RRC_Setup"]["failure_causes"]))

if show_raw:
    with st.expander("Raw parsed data"):
        st.json(parsed)

# ---- Detection ----
with st.spinner("Step 2 of 3: Running anomaly detection..."):
    anomalies = detect_anomalies_stub(parsed, detector=detector_choice)

st.subheader("⚠️ Detected Anomalies")
if not anomalies:
    st.success("No anomalies detected in the uploaded data.")
else:
    df = pd.DataFrame(anomalies)
    st.dataframe(df, use_container_width=True)

# ---- Explanation for first anomaly ----
if anomalies:
    st.subheader("🤖 LLM Explanation")
    selected = st.selectbox(
        "Choose anomaly to explain",
        options=range(len(anomalies)),
        format_func=lambda i: f"#{i+1}: {anomalies[i]['type']}",
    )

    with st.spinner("Step 3 of 3: Generating explanation..."):
        explanation = explain_anomaly_stub(anomalies[selected])

    st.markdown(f"**Hypothesis:** {explanation['hypothesis']}")
    st.markdown(f"**Severity:** `{explanation['severity']}`")

    with st.expander("Cited 3GPP clauses"):
        for c in explanation["citations"]:
            st.markdown(f"- **{c['spec']}** §{c['section']}: {c['quote']}")

    with st.expander("Suggested investigation steps"):
        for step in explanation["investigation_hints"]:
            st.markdown(f"- {step}")

    # ---- Feedback ----
    st.divider()
    st.subheader("📝 Engineer Feedback")
    fb_col1, fb_col2 = st.columns([1, 4])
    with fb_col1:
        fb = st.radio("Was this useful?", ["👍 Yes", "👎 No", "🤔 Partial"], horizontal=False)
    with fb_col2:
        notes = st.text_area("Notes (optional)", placeholder="What was right or wrong about this?")
    if st.button("Submit feedback"):
        st.success("Feedback recorded (stub — will be wired to MLOps loop in Phase 5).")

# ---- Footer ----
st.divider()
st.caption(
    "M.Tech Project · Phase I Walking Skeleton · "
    "Replace stubs with real implementations week by week."
)
