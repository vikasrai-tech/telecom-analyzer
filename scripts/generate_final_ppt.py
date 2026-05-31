"""
Generate final project overview PPT — Unified Telecom Analyzer
Covers: Architecture, all components, test results, reviewer Q&A
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pathlib import Path

DARK_BG   = RGBColor(0x0D, 0x1B, 0x2A)
ACCENT    = RGBColor(0x00, 0xB4, 0xD8)
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
GREEN     = RGBColor(0x2D, 0xC6, 0x53)
ORANGE    = RGBColor(0xFF, 0x94, 0x00)
RED       = RGBColor(0xFF, 0x4D, 0x4D)
GREY      = RGBColor(0xAA, 0xAA, 0xAA)
LIGHT_BG  = RGBColor(0x14, 0x2B, 0x40)


def set_bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_title_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    # Title
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(9), Inches(1.2))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = "Unified Telecom Analyzer"
    run.font.size = Pt(40)
    run.font.bold = True
    run.font.color.rgb = ACCENT

    # Subtitle
    tb2 = slide.shapes.add_textbox(Inches(0.5), Inches(2.5), Inches(9), Inches(0.6))
    p2 = tb2.text_frame.paragraphs[0]
    p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run()
    r2.text = "End-to-End 5G Network Anomaly Detection & LLM Explanation"
    r2.font.size = Pt(20)
    r2.font.color.rgb = WHITE

    # Status chips
    tb3 = slide.shapes.add_textbox(Inches(0.5), Inches(3.3), Inches(9), Inches(0.5))
    p3 = tb3.text_frame.paragraphs[0]
    p3.alignment = PP_ALIGN.CENTER
    r3 = p3.add_run()
    r3.text = "✅ 6 Protocols  ✅ 6 PCAP Detectors  ✅ 6 KPI Detectors  ✅ RAG + LLM  ✅ REST API  ✅ 20 Tests"
    r3.font.size = Pt(14)
    r3.font.color.rgb = GREEN

    # Tech stack
    tb4 = slide.shapes.add_textbox(Inches(0.5), Inches(4.2), Inches(9), Inches(1.0))
    tf4 = tb4.text_frame
    tf4.word_wrap = True
    p4 = tf4.paragraphs[0]
    p4.alignment = PP_ALIGN.CENTER
    r4 = p4.add_run()
    r4.text = "Python · pyshark · scikit-learn · PyTorch · FAISS · Ollama · Streamlit · FastAPI"
    r4.font.size = Pt(13)
    r4.font.color.rgb = GREY


def add_architecture_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    tb = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(9.4), Inches(0.5))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = "🏗️  System Architecture"
    r.font.size = Pt(26)
    r.font.bold = True
    r.font.color.rgb = ACCENT

    layers = [
        ("INPUT LAYER",
         ["PCAP (pyshark/scapy)", "KPI Excel / CSV"],
         ACCENT, 0.8),
        ("PARSING LAYER  — TS 24.501 / 38.413 / 38.331 / 38.473 / 38.463 / 38.423",
         ["NAS", "NGAP", "RRC", "F1AP", "E1AP", "XnAP"],
         GREEN, 1.65),
        ("DETECTION LAYER  (PCAP: 6 detectors | KPI: 6 methods)",
         ["Isolation Forest", "Statistical", "OC-SVM", "LOF", "Elliptic Env.", "LSTM-AE",
          "Threshold", "Peer Comparison", "Trend", "IQR", "CUSUM", "Bollinger"],
         ORANGE, 2.7),
        ("RAG + LLM LAYER  — 3GPP spec chunks + Ollama (phi3:mini)",
         ["FAISS index", "MiniLM embeddings", "Rule-based fallback"],
         RGBColor(0xA0, 0x60, 0xFF), 3.75),
        ("OUTPUT LAYER",
         ["Streamlit Dashboard", "FastAPI REST API", "CLI Pipeline Runner"],
         RGBColor(0xFF, 0x4D, 0x9F), 4.65),
    ]

    for label, items, color, top in layers:
        tb_l = slide.shapes.add_textbox(Inches(0.3), Inches(top), Inches(2.2), Inches(0.35))
        p_l  = tb_l.text_frame.paragraphs[0]
        r_l  = p_l.add_run()
        r_l.text = label
        r_l.font.size = Pt(9)
        r_l.font.bold = True
        r_l.font.color.rgb = color

        tb_i = slide.shapes.add_textbox(Inches(0.3), Inches(top + 0.3), Inches(9.2), Inches(0.45))
        tf_i = tb_i.text_frame
        p_i  = tf_i.paragraphs[0]
        p_i.alignment = PP_ALIGN.LEFT
        r_i  = p_i.add_run()
        r_i.text = "  ·  ".join(items)
        r_i.font.size = Pt(11)
        r_i.font.color.rgb = WHITE


def add_protocol_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    tb = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(9.4), Inches(0.5))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = "📡  Parsed 3GPP Protocols"
    r.font.size = Pt(26)
    r.font.bold = True
    r.font.color.rgb = ACCENT

    protocols = [
        ("NAS — TS 24.501",   "Registration · Auth · Security Mode · PDU Session · Deregistration",
         "AMF ↔ UE  (N1)"),
        ("NGAP — TS 38.413",  "InitialContextSetup · PDUSession Setup/Release · UEContextRelease · Handover · Paging",
         "gNB-CU ↔ AMF  (N2)"),
        ("RRC — TS 38.331",   "Setup · Reestablishment · Reconfiguration · Release · UE Capability · Measurement",
         "UE ↔ gNB  (Uu)"),
        ("F1AP — TS 38.473",  "F1 Setup · UE Context Setup/Release · DL/UL RRC Transfer · Initial UL RRC",
         "gNB-DU ↔ gNB-CU-CP  (F1)"),
        ("E1AP — TS 38.463",  "CU-UP Setup · Bearer Context Setup/Modify/Release · Data Notification",
         "gNB-CU-CP ↔ gNB-CU-UP  (E1)"),
        ("XnAP — TS 38.423",  "Xn Setup · Handover Request · UE Context Release · SN Addition (MR-DC)",
         "gNB ↔ gNB  (Xn)"),
    ]

    for i, (proto, procs, iface) in enumerate(protocols):
        top = 0.9 + i * 0.75
        tb_p = slide.shapes.add_textbox(Inches(0.3), Inches(top), Inches(2.5), Inches(0.3))
        p_p  = tb_p.text_frame.paragraphs[0]
        r_p  = p_p.add_run()
        r_p.text = proto
        r_p.font.size = Pt(13)
        r_p.font.bold = True
        r_p.font.color.rgb = GREEN

        tb_d = slide.shapes.add_textbox(Inches(2.9), Inches(top), Inches(5.0), Inches(0.3))
        p_d  = tb_d.text_frame.paragraphs[0]
        r_d  = p_d.add_run()
        r_d.text = procs
        r_d.font.size = Pt(10)
        r_d.font.color.rgb = WHITE

        tb_i = slide.shapes.add_textbox(Inches(8.0), Inches(top), Inches(1.8), Inches(0.3))
        p_i  = tb_i.text_frame.paragraphs[0]
        p_i.alignment = PP_ALIGN.RIGHT
        r_i  = p_i.add_run()
        r_i.text = iface
        r_i.font.size = Pt(9)
        r_i.font.color.rgb = GREY


def add_pcap_detection_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    tb = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(9.4), Inches(0.5))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = "⚠️  PCAP Anomaly Detection — 6-Detector Ensemble"
    r.font.size = Pt(22)
    r.font.bold = True
    r.font.color.rgb = ACCENT

    detectors = [
        ("1", "Isolation Forest",    "Unsupervised / tree",
         "Anomalies isolate in fewer tree splits. No distribution assumption. O(n log n). Handles 5G's >99% normal rate."),
        ("2", "Statistical (Threshold+Cascade)", "Rule-based",
         "Encodes 3GPP SLA directly. 100% interpretable. Catches congestion chains, timeout storms."),
        ("3", "One-Class SVM",       "Kernel / boundary",
         "Non-linear normal region in kernel space. Complements IF where normal cluster is compact."),
        ("4", "LOF",                 "Density / local",
         "Local Outlier Factor — catches cells 3σ below peer cluster even if globally OK."),
        ("5", "Elliptic Envelope",   "Mahalanobis / Gaussian",
         "Fastest interpretable baseline. Sanity-checks the ML methods."),
        ("6", "LSTM Autoencoder",    "Deep learning / sequence",
         "Only method that catches procedure-ORDER violations (e.g., PDU before Auth)."),
    ]

    for i, (num, name, dtype, why) in enumerate(detectors):
        top = 0.85 + i * 0.65
        for x, w, text, color, sz, bold in [
            (0.3, 0.25, num,   ACCENT, 14, True),
            (0.6, 2.2,  name,  WHITE,  12, True),
            (2.9, 1.5,  dtype, ORANGE, 10, False),
            (4.5, 5.2,  why,   GREY,   10, False),
        ]:
            tb_x = slide.shapes.add_textbox(Inches(x), Inches(top), Inches(w), Inches(0.45))
            p_x  = tb_x.text_frame.paragraphs[0]
            r_x  = p_x.add_run()
            r_x.text = text
            r_x.font.size = Pt(sz)
            r_x.font.bold = bold
            r_x.font.color.rgb = color


def add_kpi_detection_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    tb = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(9.4), Inches(0.5))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = "📊  KPI Anomaly Detection — 6-Method Ensemble"
    r.font.size = Pt(22)
    r.font.bold = True
    r.font.color.rgb = ACCENT

    methods = [
        ("1", "Threshold Violation",    "Rule-based / point",
         "Per-row check vs warning/critical. Encodes 3GPP/ITU-T SLA. Zero false positives for known limits."),
        ("2", "Peer Comparison",        "Statistical / cross-cell",
         "Z-score vs fleet. Catches underperforming cells within threshold but 3σ below peers."),
        ("3", "Trend (LinReg)",         "Statistical / temporal",
         "Slope > 0.5 unit/hr = actionable even if still 'green'. Early warning for degradation."),
        ("4", "IQR (Tukey Fence)",      "Robust / distribution-free",
         "No Gaussian assumption. Works on skewed KPIs (PRB right-skewed, CQI during interference left-skewed)."),
        ("5", "CUSUM",                  "Sequential / change-point",
         "Accumulates small deviations. Catches RRC SR 99.5%→98.2% drift before any threshold fires."),
        ("6", "Bollinger Bands",        "Rolling envelope / burst",
         "Catches sudden spikes invisible to trend methods. Window=5 gives local context."),
    ]

    for i, (num, name, dtype, why) in enumerate(methods):
        top = 0.85 + i * 0.65
        for x, w, text, color, sz, bold in [
            (0.3, 0.25, num,   ACCENT, 14, True),
            (0.6, 2.2,  name,  WHITE,  12, True),
            (2.9, 1.8,  dtype, ORANGE, 10, False),
            (4.8, 4.9,  why,   GREY,   10, False),
        ]:
            tb_x = slide.shapes.add_textbox(Inches(x), Inches(top), Inches(w), Inches(0.45))
            p_x  = tb_x.text_frame.paragraphs[0]
            r_x  = p_x.add_run()
            r_x.text = text
            r_x.font.size = Pt(sz)
            r_x.font.bold = bold
            r_x.font.color.rgb = color


def add_llm_rag_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    tb = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(9.4), Inches(0.5))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = "🤖  LLM Explainer — RAG over 3GPP Specifications"
    r.font.size = Pt(22)
    r.font.bold = True
    r.font.color.rgb = ACCENT

    flow = [
        ("1  Anomaly", "procedure + severity + failure_causes + evidence",
         "Input to pipeline"),
        ("2  Query Build", "natural-language query from anomaly fields",
         "_build_query()"),
        ("3  Retrieve", "FAISS cosine search → top-5 3GPP spec chunks",
         "all-MiniLM-L6-v2 embeddings (80 MB)"),
        ("4  Prompt", "anomaly + spec context → structured JSON prompt",
         "_build_prompt()"),
        ("5  LLM Call", "Ollama (phi3:mini / llama3.2 / mistral fallback chain)",
         "temperature=0.2, num_predict=600"),
        ("6  Fallback", "rule-based explanation from retrieved chunks",
         "if Ollama unavailable — still uses real 3GPP content"),
        ("7  Output", "hypothesis · citations · investigation_hints · source",
         "Displayed in dashboard + returned by API"),
    ]

    for i, (step, desc, note) in enumerate(flow):
        top = 0.85 + i * 0.6
        for x, w, text, color, sz, bold in [
            (0.3, 1.3,  step, ACCENT, 12, True),
            (1.7, 4.8,  desc, WHITE,  11, False),
            (6.6, 3.1,  note, GREY,   9,  False),
        ]:
            tb_x = slide.shapes.add_textbox(Inches(x), Inches(top), Inches(w), Inches(0.42))
            p_x  = tb_x.text_frame.paragraphs[0]
            r_x  = p_x.add_run()
            r_x.text = text
            r_x.font.size = Pt(sz)
            r_x.font.bold = bold
            r_x.font.color.rgb = color

    kb_note = "Knowledge base: 38 curated 3GPP spec chunks (TS 24.501 · 38.413 · 38.331 · 38.473 · 38.463 · 38.423 · 38.913)"
    tb_kb = slide.shapes.add_textbox(Inches(0.3), Inches(5.1), Inches(9.2), Inches(0.3))
    p_kb  = tb_kb.text_frame.paragraphs[0]
    r_kb  = p_kb.add_run()
    r_kb.text = kb_note
    r_kb.font.size = Pt(10)
    r_kb.font.color.rgb = ORANGE


def add_api_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    tb = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(9.4), Inches(0.5))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = "🌐  Output Interfaces — Dashboard · REST API · CLI"
    r.font.size = Pt(22)
    r.font.bold = True
    r.font.color.rgb = ACCENT

    interfaces = [
        ("Streamlit Dashboard", "make dev  →  http://localhost:8501",
         ["Upload PCAP or KPI file", "6 protocol tabs + failure cause breakdown + IE inspector",
          "6-detector method comparison matrix", "LLM explanation with 3GPP citations"]),
        ("FastAPI REST API", "make api  →  http://localhost:8000",
         ["POST /analyze/pcap  — upload PCAP, returns JSON",
          "POST /analyze/kpi   — upload KPI file, returns JSON",
          "GET  /analyze/{job_id}  — retrieve cached result",
          "GET  /health  — Ollama status + version"]),
        ("CLI Pipeline Runner", "python -m src.orchestrator.pipeline --input file.pcap",
         ["Auto-detects PCAP vs KPI from file extension",
          "--no-llm flag skips LLM (fast mode)",
          "--output report.json writes JSON report",
          "Used in CI tests + batch processing"]),
    ]

    top = 0.85
    for name, cmd, bullets in interfaces:
        tb_n = slide.shapes.add_textbox(Inches(0.3), Inches(top), Inches(9.2), Inches(0.35))
        p_n  = tb_n.text_frame.paragraphs[0]
        r_n  = p_n.add_run()
        r_n.text = f"▶  {name}  —  {cmd}"
        r_n.font.size = Pt(13)
        r_n.font.bold = True
        r_n.font.color.rgb = GREEN

        for j, b in enumerate(bullets):
            tb_b = slide.shapes.add_textbox(Inches(0.7), Inches(top + 0.35 + j * 0.28),
                                            Inches(8.8), Inches(0.28))
            p_b  = tb_b.text_frame.paragraphs[0]
            r_b  = p_b.add_run()
            r_b.text = f"• {b}"
            r_b.font.size = Pt(11)
            r_b.font.color.rgb = WHITE

        top += 0.35 + len(bullets) * 0.28 + 0.3


def add_test_results_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    tb = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(9.4), Inches(0.5))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = "✅  Test Results — 20 Tests, All Passing"
    r.font.size = Pt(26)
    r.font.bold = True
    r.font.color.rgb = ACCENT

    suites = [
        ("test_walking_skeleton.py  (4 tests)",
         ["parse_pcap_stub returns correct keys",
          "detect_anomalies_stub returns anomaly list",
          "explain_anomaly_stub returns citations",
          "Full stub pipeline runs end-to-end"],
         GREEN),
        ("test_real_pipeline.py  (16 tests)",
         ["Real PCAP parser — keys, procedures, schema",
          "Real PCAP detectors — 6 detectors return correct dict",
          "Real KPI parser — keys, KPI columns",
          "Real KPI detectors — schema validated",
          "RAG retriever — chunks, relevance ordering",
          "LLM explainer — rule-based output schema",
          "Orchestrator run_pcap_pipeline() end-to-end",
          "Orchestrator run_kpi_pipeline() end-to-end",
          "run_pipeline() auto-detects file type"],
         GREEN),
    ]

    top = 0.9
    for title, tests, color in suites:
        tb_t = slide.shapes.add_textbox(Inches(0.3), Inches(top), Inches(9.2), Inches(0.35))
        p_t  = tb_t.text_frame.paragraphs[0]
        r_t  = p_t.add_run()
        r_t.text = title
        r_t.font.size = Pt(14)
        r_t.font.bold = True
        r_t.font.color.rgb = ACCENT

        for j, test in enumerate(tests):
            tb_x = slide.shapes.add_textbox(Inches(0.5), Inches(top + 0.4 + j * 0.3),
                                            Inches(8.8), Inches(0.3))
            p_x  = tb_x.text_frame.paragraphs[0]
            r_x  = p_x.add_run()
            r_x.text = f"✅  {test}"
            r_x.font.size = Pt(11)
            r_x.font.color.rgb = color

        top += 0.4 + len(tests) * 0.3 + 0.3


def add_reviewer_qa_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    tb = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(9.4), Inches(0.5))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = "🎯  Reviewer Q&A — Anticipated Questions"
    r.font.size = Pt(22)
    r.font.bold = True
    r.font.color.rgb = ACCENT

    qa = [
        ("Why 6 detectors instead of 1?",
         "No single method catches all anomaly types. IF+SVM are global; LOF is local. "
         "Threshold is deterministic; ML adapts. LSTM catches sequences. Multi-detector "
         "agreement = higher confidence. See Method Comparison Matrix in the dashboard."),
        ("Why Ollama (local LLM) not OpenAI?",
         "Telecom data is sensitive — operator configurations, failure rates, cell IDs "
         "cannot leave the premises. Local Ollama keeps all data on-site. "
         "Rule-based fallback ensures the system works even without GPU/model."),
        ("Why FAISS for RAG, not a vector DB?",
         "Corpus is small (38 spec chunks). FAISS is in-process, zero infra, "
         "sub-millisecond retrieval. A vector DB (Pinecone, Weaviate) adds operational "
         "complexity with no benefit at this scale."),
        ("Why pyshark over scapy for PCAP?",
         "Pyshark wraps Wireshark's tshark — provides full 3GPP ASN.1 dissection of "
         "NAS/NGAP/RRC out of the box. Scapy has no 5G-NR dissectors; we'd need to "
         "implement ASN.1 decoding from scratch. See PCAP_Parsing_Methods.pptx."),
    ]

    top = 0.85
    for q, a in qa:
        tb_q = slide.shapes.add_textbox(Inches(0.3), Inches(top), Inches(9.2), Inches(0.3))
        p_q  = tb_q.text_frame.paragraphs[0]
        r_q  = p_q.add_run()
        r_q.text = f"Q: {q}"
        r_q.font.size = Pt(12)
        r_q.font.bold = True
        r_q.font.color.rgb = ORANGE

        tb_a = slide.shapes.add_textbox(Inches(0.5), Inches(top + 0.3), Inches(9.0), Inches(0.5))
        tf_a = tb_a.text_frame
        tf_a.word_wrap = True
        p_a  = tf_a.paragraphs[0]
        r_a  = p_a.add_run()
        r_a.text = f"A: {a}"
        r_a.font.size = Pt(10)
        r_a.font.color.rgb = WHITE

        top += 1.0


def add_summary_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    tb = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(9), Inches(0.6))
    p = tb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = "Project Complete ✅"
    r.font.size = Pt(36)
    r.font.bold = True
    r.font.color.rgb = GREEN

    items = [
        "6 × 3GPP protocols parsed (NAS · NGAP · RRC · F1AP · E1AP · XnAP)",
        "6 × PCAP anomaly detectors + 6 × KPI anomaly detectors",
        "RAG pipeline: 38 spec chunks · FAISS · MiniLM · Ollama (phi3:mini)",
        "Streamlit dashboard with method comparison matrices",
        "FastAPI REST API (POST /analyze/pcap, POST /analyze/kpi)",
        "CLI orchestrator pipeline runner",
        "20 tests passing — stub + real integration",
        "4 reviewer PPTs (PCAP methods, KPI methods, this deck)",
    ]

    for i, item in enumerate(items):
        top = 1.9 + i * 0.42
        tb_i = slide.shapes.add_textbox(Inches(1.0), Inches(top), Inches(8.2), Inches(0.4))
        p_i  = tb_i.text_frame.paragraphs[0]
        r_i  = p_i.add_run()
        r_i.text = f"✅  {item}"
        r_i.font.size = Pt(14)
        r_i.font.color.rgb = WHITE


def main():
    prs = Presentation()
    prs.slide_width  = Inches(10)
    prs.slide_height = Inches(5.63)

    add_title_slide(prs)
    add_architecture_slide(prs)
    add_protocol_slide(prs)
    add_pcap_detection_slide(prs)
    add_kpi_detection_slide(prs)
    add_llm_rag_slide(prs)
    add_api_slide(prs)
    add_test_results_slide(prs)
    add_reviewer_qa_slide(prs)
    add_summary_slide(prs)

    out = Path("docs/Project_Overview_Final.pptx")
    out.parent.mkdir(exist_ok=True)
    prs.save(str(out))
    print(f"Saved: {out}  ({prs.slides.__len__()} slides)")


if __name__ == "__main__":
    main()
