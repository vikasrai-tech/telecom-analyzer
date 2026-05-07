"""
Unified Telecom Analyzer — Dashboard
=====================================

ARCHITECTURE:
    This is the presentation layer only.
    Business logic lives in src/parsers/, src/detection/, src/llm/
    Dashboard just: receives input → calls services → displays output

WHY STREAMLIT:
    Rapid prototyping for data science dashboards.
    No HTML/CSS/JS needed — pure Python.
    Built-in widgets: file_uploader, metrics, dataframe, expander.
    Alternative was Flask + React — overkill for Phase I.
    Streamlit can be replaced later without touching parser/detection code.

CURRENT STATE (Phase I):
    ✅ PCAP parser — REAL (pcap_parser_real.py)
    🔶 Detection engine — stub (will be real in Week 6-8)
    🔶 LLM explainer — stub (will be real in Week 11-14)

WHY STUBS STILL EXIST:
    Incremental development — one real component at a time.
    Detection and LLM stubs let us demo the full pipeline
    even before those components are implemented.
"""

import streamlit as st
import pandas as pd
import tempfile
import os
from pathlib import Path
import sys

# WHY sys.path:
#   Streamlit runs app.py from its own working directory.
#   Without this, 'from src.parsers...' would fail with ModuleNotFoundError.
#   We add project root to Python's search path explicitly.
sys.path.append(str(Path(__file__).resolve().parents[2]))

# ── Import real parser (NOT stub anymore) ─────────────────────────
from src.parsers.pcap_parser_real import parse_pcap as parse_pcap_real

# ── Import stubs (still used for detection + LLM) ─────────────────
from src.detection.detector import detect_anomalies_stub
from src.llm.explainer import explain_anomaly_stub

# ── Page config ───────────────────────────────────────────────────
# WHY WIDE LAYOUT:
#   Procedure counter table has multiple columns.
#   Wide layout uses full browser width — more readable.
st.set_page_config(
    page_title="Unified Telecom Analyzer",
    page_icon="📡",
    layout="wide",
)

# ── Header ────────────────────────────────────────────────────────
st.title("📡 Unified Telecom Analyzer")
st.caption(
    "Phase I · Real PCAP parser active · "
    "Detection and LLM: stubs (coming Week 6-14)"
)

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.header("Upload Data")

    data_type = st.radio(
        "Data type",
        ["PCAP", "DU/CU Stats", "KPI Time-series"],
    )

    # File extensions per data type
    # WHY DICT LOOKUP:
    #   Cleaner than if/elif chain.
    #   Easy to add new types — one line in dict.
    ext_map = {
        "PCAP": ["pcap", "pcapng"],
        "DU/CU Stats": ["csv"],
        "KPI Time-series": ["csv", "parquet"],
    }

    uploaded = st.file_uploader(
        f"Upload {data_type} file",
        type=ext_map[data_type],
    )

    st.divider()

    # Parser info
    st.subheader("Parser Status")
    if data_type == "PCAP":
        st.success("✅ Real parser active")
        st.caption("Using pcap_parser_real.py")
    else:
        st.warning("🔶 Stub parser (coming soon)")

    st.divider()
    show_raw = st.checkbox("Show raw parser output", value=False)

# ── Main panel ────────────────────────────────────────────────────
if uploaded is None:
    st.info("👈 Upload a file in the sidebar to begin.")

    # Show what's real vs stub
    col1, col2, col3 = st.columns(3)
    with col1:
        st.success("**PCAP Parser**\n\nReal ✅\n\nNAS procedure tracking\nSuccess/failure rates\nCause code extraction")
    with col2:
        st.warning("**Detection Engine**\n\nStub 🔶\n\nIsolation Forest coming\nLSTM Autoencoder coming\n(Week 6-8)")
    with col3:
        st.warning("**LLM Explainer**\n\nStub 🔶\n\nPhi-3 Mini RAG coming\n3GPP spec retrieval coming\n(Week 11-14)")
    st.stop()

# ── File received ─────────────────────────────────────────────────
st.success(f"✅ Received: `{uploaded.name}` ({uploaded.size:,} bytes)")

# ── Parse ─────────────────────────────────────────────────────────
# WHY TEMPFILE:
#   Streamlit gives us BytesIO (in-memory file object).
#   pyshark needs a real file PATH on disk.
#   tempfile.NamedTemporaryFile creates a real disk file temporarily.
#
# WHY delete=False then manual cleanup:
#   On Windows/WSL, NamedTemporaryFile with delete=True cannot be
#   read by tshark while Python has it open (file locking issue).
#   Solution: create with delete=False, manually delete after parsing.
#
# WHY suffix='.pcap':
#   tshark identifies file format by extension.
#   Without .pcap extension, tshark may misidentify format.

with st.spinner("🔍 Parsing PCAP — extracting 5G procedures..."):
    tmp_path = None
    try:
        # Save uploaded file to disk
        with tempfile.NamedTemporaryFile(
            suffix=f".{uploaded.name.split('.')[-1]}",
            delete=False
        ) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name

        # Call real parser
        if data_type == "PCAP":
            parsed = parse_pcap_real(tmp_path)
        else:
            # Stub for non-PCAP types (Phase I)
            from src.parsers.pcap_parser import parse_pcap_stub
            parsed = parse_pcap_stub(uploaded.name)

    except Exception as e:
        st.error(f"❌ Parser error: {e}")
        st.info("Make sure the file is a valid PCAP/PCAPng capture.")
        st.stop()
    finally:
        # WHY FINALLY:
        #   Temp file must be deleted even if exception occurs.
        #   Without this — temp files accumulate on disk.
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

# ── Summary metrics ───────────────────────────────────────────────
st.subheader("📊 Parsed Summary")

# Top-level metrics
col1, col2, col3 = st.columns(3)
col1.metric(
    "Total signalling events",
    f"{parsed.get('total_events', 0):,}"
)
col2.metric(
    "Packets processed",
    f"{parsed.get('total_packets_processed', 0):,}"
)
col3.metric(
    "Parser version",
    parsed.get('parser_version', 'stub')
)

# ── Procedure counters ────────────────────────────────────────────
st.subheader("📋 Procedure-Level Counters")

# WHY THIS SECTION IS THE CORE VALUE:
#   This is what NOC engineers do manually today — open Wireshark,
#   count requests vs responses, compute success rate.
#   We automate it. This is the primary engineering contribution.

procedures = parsed.get('procedures', {})

if not procedures:
    st.warning("No 5G procedures found in this capture.")
    st.info(
        "For PCAP files: make sure capture contains NAS/NGAP/RRC traffic. "
        "Try the test file: data/raw/test_nas_registration.pcap"
    )
else:
    # Build procedure summary table
    # WHY LIST OF DICTS → DATAFRAME:
    #   Streamlit renders DataFrames as interactive tables.
    #   List of dicts is the cleanest way to build DataFrame rows.
    rows = []
    for proc_name, stats in procedures.items():
        rows.append({
            "Procedure": proc_name,
            "Attempts": stats["attempts"],
            "Success": stats["success"],
            "Failure": stats["failure"],
            "Success Rate %": f"{stats['success_rate']:.1f}%",
            "Top Failure Cause": (
                max(stats["failure_causes"],
                    key=stats["failure_causes"].get)
                if stats["failure_causes"] else "—"
            ),
        })

    df_procs = pd.DataFrame(rows)
    st.dataframe(df_procs, use_container_width=True)

    # Failure cause breakdown per procedure
    st.subheader("🔍 Failure Cause Breakdown")
    for proc_name, stats in procedures.items():
        if stats["failure_causes"]:
            with st.expander(f"{proc_name} — failure causes"):
                causes_df = pd.DataFrame([
                    {"Cause": cause, "Count": count}
                    for cause, count in sorted(
                        stats["failure_causes"].items(),
                        key=lambda x: x[1],
                        reverse=True
                    )
                ])
                st.dataframe(causes_df, use_container_width=True)
        else:
            with st.expander(f"{proc_name} — no failures"):
                st.success("All procedures completed successfully.")

# ── Raw output ────────────────────────────────────────────────────
if show_raw:
    with st.expander("Raw parser output (JSON)"):
        st.json(parsed)

# ── Detection (stub) ──────────────────────────────────────────────
st.divider()
st.subheader("⚠️ Anomaly Detection")
st.warning(
    "🔶 Detection engine is a stub — Isolation Forest + LSTM Autoencoder "
    "will be implemented in Week 6-8."
)

with st.spinner("Running anomaly detection (stub)..."):
    anomalies = detect_anomalies_stub(parsed, detector="Isolation Forest (stub)")

if anomalies:
    df_anomalies = pd.DataFrame(anomalies)