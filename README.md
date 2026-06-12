# Unified Telecom Analyzer

Multi-modal anomaly detection and explanation framework for 5G networks.
Processes **PCAP traces** (NAS, NGAP, RRC, F1AP, E1AP, XnAP), **DU/CU
statistics** (srsRAN / OAI / NIST / Parquet), and **KPI time-series**
(Excel/CSV gNB exports) through a unified pipeline — runs an 18-detector
anomaly ensemble, correlates events across sources, forecasts future
anomalies, and explains root causes with a RAG pipeline grounded in 3GPP
specifications.

**M.Tech Project — Phase I**
**Programme:** M.Tech Data Science (PES Bangalore with Great Learning)

---

## Quick Start (Windows + WSL2 + 16 GB RAM)

If you are starting fresh, follow `docs/SETUP.md` step by step.

```bash
make demo     # simple dashboard for a quick demo  -> http://localhost:8501
make dev      # full technical dashboard           -> http://localhost:8501
make api      # FastAPI REST server                -> http://localhost:8000/docs
```

---

## What it does

### 1. Parsing — 3GPP protocol stack + KPI/stats exports
- **PCAP** (`src/parsers/pcap_parser_real.py` + per-protocol modules):
  decodes **NAS** (TS 24.501), **NGAP** (TS 38.413), **RRC** (TS 38.331),
  **F1AP** (TS 38.473), **E1AP** (TS 38.463), **XnAP** (TS 38.423).
  Uses `pyshark` for real captures, with a raw-discriminator fallback for
  synthetic test PCAPs.
- **DU/CU Stats** (`src/parsers/stats_parser.py`): srsRAN, OAI, NIST, and
  Parquet counter exports — L1/L2 metrics (BLER, HARQ, SNR, PRB).
- **KPI** (`src/parsers/kpi_parser.py` + `kpi_defs.py`): gNB/EMS Excel or
  CSV exports, normalised against a 3GPP KPI catalogue (thresholds,
  direction, units, aliases).

### 2. Detection — 18-detector ensemble
| Domain | Detectors (`src/detection/`) |
|---|---|
| **PCAP** (`detectors.py`) | Isolation Forest · One-Class SVM · LOF · Elliptic Envelope · Statistical (threshold + cascade) · LSTM Autoencoder |
| **KPI** (`kpi_detector.py`) | Threshold Violation · Peer Comparison (z-score) · Trend (linear regression) · IQR (Tukey fence) · CUSUM · Bollinger Bands |
| **Stats/L1-L2** (`stats_detector.py`) | Same 6-method ensemble applied to srsRAN/OAI/NIST counters |

Each detector returns severity (Critical/High/Medium/Low), rationale, and
a method-comparison matrix so results can be cross-checked.

### 3. Event Routing & Correlation
`src/orchestrator/event_router.py` tags events by source (pcap / kpi /
stats), ingests them into a unified event log, and correlates anomalies
across sources (e.g. a PCAP handover failure + a KPI handover-success-rate
dip on the same cell/time window).

### 4. Prediction Layer
`src/detection/predictor.py` — forecasts anomalies **4 hours ahead** using:
- **Prophet** — seasonal/trend decomposition for KPI time-series
- **LSTM** — sequence model for irregular L1/L2 counter behaviour

Predicted anomalies are tagged `state="predicted"` with a `lead_time_h`,
using the same schema as live detections.

### 5. RAG + LLM Explanations
`src/rag/` (FAISS + MiniLM embeddings over 38 3GPP spec chunks) retrieves
relevant spec text for each anomaly; `src/llm/explainer.py` sends it to a
local **Ollama (phi3:mini)** model for a grounded explanation, with a
rule-based fallback if Ollama isn't running.

### 6. MLOps Feedback Loop
- **Feedback store** (`src/feedback/store.py`): engineer "this was a real
  issue / false positive" feedback → `data/feedback/feedback_log.jsonl`
- **Nightly retrainer** (`src/detection/retrainer.py`,
  `scripts/nightly_retrain.py`, `make retrain`): adjusts per-detector
  contamination/threshold based on observed false-positive rate →
  `data/models/retrain_config.json`, picked up automatically on the next run.

### 7. Interfaces
- **Streamlit dashboard** (`src/dashboard/app.py` / `app_simple.py`):
  upload PCAP/KPI/Stats → procedure tabs, failure-cause breakdown, IE
  inspector, anomaly + rationale views, prediction panel, feedback widget.
- **FastAPI REST API** (`src/api/main.py`):
  - `GET  /health` — health check + Ollama status
  - `POST /analyze/pcap` — upload PCAP → full analysis
  - `POST /analyze/kpi` — upload KPI (xlsx/csv) → full analysis
  - `GET  /analyze/{job_id}` — retrieve a cached result
  - Interactive docs at `/docs`
- **CLI orchestrator** (`src/orchestrator/pipeline.py`):
  ```bash
  python -m src.orchestrator.pipeline --input data/raw/ue_attach_10.pcap --no-llm
  python -m src.orchestrator.pipeline --input data/raw/kpi_10hr_sample.csv --kpi --no-llm
  python -m src.orchestrator.pipeline --input data/raw/stats_sample.csv --stats --no-llm
  ```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Streamlit Dashboard          │  FastAPI REST API  │  CLI         │
└───────────────────┬──────────────────┬──────────────┬────────────┘
                     │                  │              │
┌────────────────────▼──────────────────▼──────────────▼────────────┐
│              Orchestrator  (src/orchestrator/pipeline.py)         │
│        run_pcap_pipeline · run_kpi_pipeline · run_stats_pipeline  │
└──────┬──────────────────┬──────────────────┬──────────────────────┘
       │                  │                  │
┌──────▼──────┐   ┌───────▼───────┐   ┌──────▼────────┐
│ PCAP Parser │   │  Stats Parser │   │  KPI Parser   │
│ NAS·NGAP·RRC│   │ srsRAN/OAI/   │   │ Excel/CSV +   │
│ F1AP·E1AP·  │   │ NIST/Parquet  │   │ KPI catalogue │
│ XnAP        │   │               │   │               │
└──────┬──────┘   └───────┬───────┘   └──────┬────────┘
       │                  │                  │
┌──────▼──────────────────▼──────────────────▼────────────────────┐
│        Detection Ensemble (18 detectors, src/detection/)         │
│  IF · OC-SVM · LOF · Elliptic Env · Statistical · LSTM-AE  (x3)   │
└──────────────────────┬──────────────────────┬────────────────────┘
                        │                      │
              ┌─────────▼─────────┐  ┌─────────▼──────────┐
              │   Event Router    │  │  Prediction Layer  │
              │  (cross-source    │  │  Prophet + LSTM     │
              │   correlation)    │  │  4h-ahead forecast  │
              └─────────┬─────────┘  └─────────┬──────────┘
                        │                      │
              ┌─────────▼──────────────────────▼──────────┐
              │  RAG (FAISS over 3GPP specs) → Ollama LLM  │
              │  explanation, with rule-based fallback     │
              └─────────────────┬───────────────────────────┘
                                 │
              ┌──────────────────▼───────────────────────┐
              │  Feedback Store → Nightly Retrainer        │
              │  (adjusts detector params from FP rate)   │
              └────────────────────────────────────────────┘
```

---

## Repository Layout

```
telecom-analyzer/
├── src/
│   ├── parsers/          # PCAP (NAS/NGAP/RRC/F1AP/E1AP/XnAP), stats, KPI
│   ├── detection/         # 18-detector ensemble + predictor + retrainer
│   ├── rag/                # FAISS knowledge base + retriever + embedder
│   ├── llm/                # Ollama (phi3:mini) explainer + fallback
│   ├── feedback/           # engineer feedback store (JSONL)
│   ├── orchestrator/       # pipeline (PCAP/KPI/Stats) + event router
│   ├── api/                # FastAPI REST API
│   └── dashboard/          # Streamlit apps (full + simple)
├── tests/                  # 56 tests — walking skeleton, real pipeline,
│                           #   event router, feedback/prediction, retrainer
├── scripts/
│   ├── generate_ue_attach_pcap.py    # 10 UE attach scenario PCAP
│   ├── generate_handover_pcap.py     # 20 UE handover (XnAP+NGAP) PCAP
│   ├── generate_kpi_timeseries.py    # 10-hour KPI sample (throughput/HO)
│   ├── generate_test_stats.py        # synthetic srsRAN/OAI/NIST stats
│   ├── generate_*_ppt.py             # reviewer slide decks
│   └── nightly_retrain.py            # `make retrain` entrypoint
├── data/
│   ├── raw/              # generated/downloaded test data (gitignored)
│   ├── feedback/         # feedback_log.jsonl
│   └── models/           # retrain_config.json, trained artifacts
├── docs/                  # SETUP.md, WEEK_1_GUIDE.md
└── Makefile               # demo / dev / api / test / retrain / lint / format
```

---

## Generating test data

```bash
# 10 UE full attach flow (RRC->F1AP->NAS->NGAP->...->RRC Reconfig), 4 failure scenarios
python scripts/generate_ue_attach_pcap.py

# 20 UE handover (10 Xn-based via XnAP, 10 N2-based via NGAP), 4 failures
python scripts/generate_handover_pcap.py

# 10-hour, 1-min granularity KPI sample across 10 cells / 3 gNBs,
# with injected congestion/outage/drift anomalies
python scripts/generate_kpi_timeseries.py

# synthetic srsRAN / OAI / NIST DU/CU stats CSVs
python scripts/generate_test_stats.py
```

All outputs land under `data/raw/` (gitignored).

---

## Running tests

```bash
make test       # fast smoke tests (walking skeleton)
make test-all   # full suite — 56 tests, requires generated test data
```

---

## Phase I Milestones

| Week  | Milestone                | Status |
|-------|--------------------------|--------|
| 1     | Setup + walking skeleton | ✅     |
| 2-4   | PCAP parser + procedures | ✅     |
| 5-7   | DU/CU + KPI parsers      | ✅     |
| 8-10  | Detection engine         | ✅     |
| 11-14 | RAG + LLM integration    | ✅     |
| 15-17 | Dashboard + feedback     | ✅     |
| 18-21 | MLOps pipeline           | ✅     |
| 22-24 | Final demo + paper draft | ✅     |

## License

Academic project. See LICENSE file.
