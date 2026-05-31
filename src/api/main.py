"""
Unified Telecom Analyzer — FastAPI REST API

Endpoints:
  GET  /health                   → health check + Ollama status
  POST /analyze/pcap             → upload PCAP, returns full analysis
  POST /analyze/kpi              → upload KPI (xlsx/csv), returns full analysis
  GET  /analyze/{job_id}         → retrieve a previous result (in-memory cache)

Run:
  uvicorn src.api.main:app --reload --port 8000
"""

import logging
import tempfile
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Unified Telecom Analyzer API",
    version="1.0.0",
    description="5G network anomaly detection and LLM-powered explanation over PCAP and KPI files.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store (production: replace with Redis / DB)
_results: Dict[str, Any] = {}


def _strip_dataframe(result: Dict[str, Any]) -> Dict[str, Any]:
    """Remove non-JSON-serialisable 'df_records' from parsed output."""
    out = dict(result)
    if "parsed" in out and isinstance(out["parsed"], dict):
        p = dict(out["parsed"])
        p.pop("df_records", None)
        out["parsed"] = p
    return out


@app.get("/health", tags=["System"])
async def health():
    """Health check + Ollama availability status."""
    from src.llm.explainer import ollama_status
    status = ollama_status()
    return {
        "status": "ok",
        "llm": status,
        "api_version": "1.0.0",
    }


@app.post("/analyze/pcap", tags=["Analysis"])
async def analyze_pcap(
    file: UploadFile = File(..., description="PCAP or PCAPNG file"),
    explain_top_n: int = 4,
    skip_llm: bool = False,
):
    """
    Upload a PCAP file and receive full analysis:
    - Parsed 5G procedures (NAS / NGAP / RRC / F1AP / E1AP / XnAP)
    - 6-detector anomaly ensemble
    - LLM explanations for top anomalies
    """
    suffix = Path(file.filename or "upload.pcap").suffix.lower()
    if suffix not in (".pcap", ".pcapng"):
        raise HTTPException(status_code=400, detail="File must be .pcap or .pcapng")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        from src.orchestrator.pipeline import run_pcap_pipeline
        result = run_pcap_pipeline(tmp_path, explain_top_n=explain_top_n, skip_llm=skip_llm)
    except Exception as e:
        logger.exception("PCAP pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)

    job_id = str(uuid.uuid4())[:8]
    _results[job_id] = result

    out = _strip_dataframe(result)
    out["job_id"] = job_id
    return JSONResponse(content=out, status_code=200)


@app.post("/analyze/kpi", tags=["Analysis"])
async def analyze_kpi(
    file: UploadFile = File(..., description="KPI file (xlsx, xls, csv)"),
    explain_top_n: int = 4,
    skip_llm: bool = False,
):
    """
    Upload a KPI time-series file and receive full analysis:
    - Parsed KPI table (cells × time × KPIs)
    - 6-method KPI anomaly ensemble
    - LLM explanations for top anomalies
    """
    suffix = Path(file.filename or "upload.xlsx").suffix.lower()
    if suffix not in (".xlsx", ".xls", ".csv"):
        raise HTTPException(status_code=400, detail="File must be .xlsx, .xls, or .csv")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        from src.orchestrator.pipeline import run_kpi_pipeline
        result = run_kpi_pipeline(tmp_path, explain_top_n=explain_top_n, skip_llm=skip_llm)
    except Exception as e:
        logger.exception("KPI pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)

    job_id = str(uuid.uuid4())[:8]
    _results[job_id] = result

    out = _strip_dataframe(result)
    out["job_id"] = job_id
    return JSONResponse(content=out, status_code=200)


@app.get("/analyze/{job_id}", tags=["Analysis"])
async def get_result(job_id: str):
    """Retrieve a previously computed analysis result by job ID."""
    if job_id not in _results:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return JSONResponse(content=_strip_dataframe(_results[job_id]))
