# Unified Telecom Analyzer

Multi-modal anomaly detection and explanation framework for 5G networks.
Processes PCAP traces, DU/CU statistics, and KPI time-series through a
unified pipeline with retrieval-augmented LLM explanations grounded in
3GPP specifications.

**M.Tech Project — Phase I**
**Programme:** M.Tech Data Science (PES Bangalore with Great Learning)

---

## Quick Start (Windows + WSL2 + 16 GB RAM)

If you are starting fresh, follow `docs/SETUP.md` step by step.
After setup, the entire stack runs with:

```bash
make dev      # starts Streamlit dashboard at http://localhost:8501
```

---

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│  Streamlit Dashboard  (upload + view + feedback)          │
└──────────────────────┬────────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────────┐
│  Orchestrator  (routes events, builds context)            │
└──────┬─────────────────┬──────────────────┬───────────────┘
       │                 │                  │
┌──────▼──────┐  ┌──────▼──────┐  ┌────────▼────────┐
│ PCAP Parser │  │ Stats Parser│  │  KPI Parser     │
│  + Tracker  │  │             │  │                 │
└──────┬──────┘  └──────┬──────┘  └────────┬────────┘
       │                 │                  │
┌──────▼─────────────────▼──────────────────▼───────────────┐
│  Detection Engine  (Isolation Forest + LSTM Autoencoder)  │
└──────────────────────┬────────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────────┐
│  RAG  (FAISS over 3GPP specs)  →  LLM (Phi-3 Mini local)  │
└───────────────────────────────────────────────────────────┘
```

## Repository Layout

```
telecom-analyzer/
├── src/
│   ├── parsers/         # PCAP, DU/CU stats, KPI parsers
│   ├── detection/       # Isolation Forest, LSTM autoencoder
│   ├── rag/             # FAISS + retrievers
│   ├── llm/             # Phi-3 client, prompt templates
│   ├── orchestrator/    # event routing, context assembly
│   └── dashboard/       # Streamlit app entry point
├── tests/               # pytest unit tests
├── data/
│   ├── raw/             # downloaded datasets (gitignored)
│   ├── processed/       # cleaned outputs (gitignored)
│   └── specs/           # 3GPP TS files (gitignored, see SETUP)
├── models/              # trained model artifacts (DVC tracked)
├── notebooks/           # exploratory Jupyter notebooks
├── scripts/             # one-off scripts (data download, etc.)
├── docs/                # SETUP.md, ARCHITECTURE.md, etc.
└── .github/workflows/   # CI pipeline
```

## Phase I Milestones

| Week  | Milestone                | Status |
|-------|--------------------------|--------|
| 1     | Setup + walking skeleton | ⏳     |
| 2-4   | PCAP parser + procedures | ⏳     |
| 5-7   | DU/CU + KPI parsers      | ⏳     |
| 8-10  | Detection engine         | ⏳     |
| 11-14 | RAG + LLM integration    | ⏳     |
| 15-17 | Dashboard + feedback     | ⏳     |
| 18-21 | MLOps pipeline           | ⏳     |
| 22-24 | Final demo + paper draft | ⏳     |

## License

Academic project. See LICENSE file.
