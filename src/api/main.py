"""
Unified Telecom Analyzer — FastAPI REST API

Endpoints:
  GET  /health                   → health check + Ollama status
  POST /analyze/pcap             → upload PCAP, returns full analysis
  POST /analyze/kpi              → upload KPI (xlsx/csv), returns full analysis
                                    (run_prediction=true adds Phase II forecasts)
  POST /analyze/stats            → upload DU/CU stats (csv/parquet), returns full analysis
                                    (run_prediction=true adds Phase II forecasts)
  GET  /analyze/{job_id}         → retrieve a previous result (in-memory cache)
  POST /agent/root-cause         → combine previously analyzed job_ids into one
                                    shared EventRouter and run the LLM root-cause
                                    agent over cross-source correlated events

Run:
  uvicorn src.api.main:app --reload --port 8000
"""

import numpy as np
import asyncio
import logging
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import nest_asyncio
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

nest_asyncio.apply()

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

# Mount Vue 3 Web Frontend static assets
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", tags=["UI"], include_in_schema=False)
async def serve_vue_ui():
    """Serve the modern Vue 3 Web UI dashboard."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"status": "API active", "docs": "/docs"})

# In-memory job store (production: replace with Redis / DB)
_results: Dict[str, Any] = {}


def _make_json_serializable(obj: Any) -> Any:
    """Recursively convert numpy types, datetimes, and custom objects to JSON-serialisable Python primitives."""
    if isinstance(obj, dict):
        return {str(k): _make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [_make_json_serializable(v) for v in obj]
    elif isinstance(obj, (np.floating, float)):
        return float(obj)
    elif isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return [_make_json_serializable(v) for v in obj.tolist()]
    elif hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def _strip_dataframe(result: Dict[str, Any]) -> Dict[str, Any]:
    """Remove non-JSON-serialisable 'df_records' from parsed output and sanitize numpy types."""
    out = dict(result)
    if "parsed" in out and isinstance(out["parsed"], dict):
        p = dict(out["parsed"])
        p.pop("df_records", None)
        out["parsed"] = p
    return _make_json_serializable(out)


def _build_kpi_trend(parsed: Dict[str, Any], max_points: int = 60) -> List[Dict[str, Any]]:
    """Aggregate per-row KPI/stats records into a compact time-series (mean
    DL throughput + DL PRB utilization across cells, per timestamp) for the
    dashboard trend chart. Returns [] when the source has no usable
    timestamp/throughput/PRB columns (e.g. a PCAP upload)."""
    records = parsed.get("df_records")
    ts_col = parsed.get("timestamp_col")
    if not records or not ts_col:
        return []

    columns = records[0].keys()

    def _find_col(candidates: List[str]) -> Optional[str]:
        for cand in candidates:
            for c in columns:
                if c.lower() == cand:
                    return c
        for cand in candidates:
            for c in columns:
                if cand in c.lower():
                    return c
        return None

    dl_col = _find_col(["dl_throughput_mbps", "throughput"])
    prb_col = _find_col(["dl_prb_util", "prb_utilization_dl_%", "prb_util"])
    if not dl_col and not prb_col:
        return []

    buckets: Dict[str, Dict[str, list]] = {}
    for row in records:
        ts = row.get(ts_col)
        if ts is None:
            continue
        b = buckets.setdefault(str(ts), {"dl": [], "prb": []})
        for col, key in ((dl_col, "dl"), (prb_col, "prb")):
            if not col:
                continue
            val = row.get(col)
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            if v == v:  # skip NaN
                b[key].append(v)

    points = [
        {
            "timestamp": ts_key,
            "dl_throughput_mbps": round(sum(b["dl"]) / len(b["dl"]), 2) if b["dl"] else None,
            "prb_utilization_pct": round(sum(b["prb"]) / len(b["prb"]), 2) if b["prb"] else None,
        }
        for ts_key, b in sorted(buckets.items())
    ]

    if len(points) > max_points:
        step = len(points) / max_points
        points = [points[int(i * step)] for i in range(max_points)]

    return points


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
        result = await asyncio.to_thread(
            run_pcap_pipeline, tmp_path, explain_top_n=explain_top_n, skip_llm=skip_llm
        )
    except Exception as e:
        logger.exception("PCAP pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)

    result["source_filename"] = file.filename

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
    run_prediction: bool = False,
    prediction_horizon_h: int = 4,
):
    """
    Upload a KPI time-series file and receive full analysis:
    - Parsed KPI table (cells × time × KPIs)
    - 6-method KPI anomaly ensemble
    - LLM explanations for top anomalies
    - Optional Phase II forecasting (Prophet / Holt-Winters / LSTM) when
      run_prediction=true
    """
    suffix = Path(file.filename or "upload.xlsx").suffix.lower()
    if suffix not in (".xlsx", ".xls", ".csv"):
        raise HTTPException(status_code=400, detail="File must be .xlsx, .xls, or .csv")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        from src.orchestrator.pipeline import run_kpi_pipeline
        result = await asyncio.to_thread(
            run_kpi_pipeline,
            tmp_path, explain_top_n=explain_top_n, skip_llm=skip_llm,
            run_prediction=run_prediction, prediction_horizon_h=prediction_horizon_h,
        )
    except Exception as e:
        logger.exception("KPI pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)

    if isinstance(result.get("parsed"), dict):
        result["parsed"]["kpi_trend"] = _build_kpi_trend(result["parsed"])
    result["source_filename"] = file.filename

    job_id = str(uuid.uuid4())[:8]
    _results[job_id] = result

    out = _strip_dataframe(result)
    out["job_id"] = job_id
    return JSONResponse(content=out, status_code=200)


@app.post("/analyze/stats", tags=["Analysis"])
async def analyze_stats(
    file: UploadFile = File(..., description="DU/CU stats file (csv, parquet)"),
    explain_top_n: int = 4,
    skip_llm: bool = False,
    run_prediction: bool = False,
    prediction_horizon_h: int = 4,
):
    """
    Upload a DU/CU stats export (srsRAN / OAI / NIST / Parquet) and receive
    full analysis:
    - Parsed L1/L2 counter table
    - 6-method stats anomaly ensemble
    - LLM explanations for top anomalies
    - Optional Phase II forecasting when run_prediction=true
    """
    suffix = Path(file.filename or "upload.csv").suffix.lower()
    if suffix not in (".csv", ".parquet"):
        raise HTTPException(status_code=400, detail="File must be .csv or .parquet")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        from src.orchestrator.pipeline import run_stats_pipeline
        result = await asyncio.to_thread(
            run_stats_pipeline,
            tmp_path, explain_top_n=explain_top_n, skip_llm=skip_llm,
            run_prediction=run_prediction, prediction_horizon_h=prediction_horizon_h,
        )
    except Exception as e:
        logger.exception("Stats pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)

    if isinstance(result.get("parsed"), dict):
        result["parsed"]["kpi_trend"] = _build_kpi_trend(result["parsed"])
    result["source_filename"] = file.filename

    job_id = str(uuid.uuid4())[:8]
    _results[job_id] = result

    out = _strip_dataframe(result)
    out["job_id"] = job_id
    return JSONResponse(content=out, status_code=200)


@app.post("/agent/root-cause", tags=["Agent"])
async def analyze_root_cause_endpoint(
    job_ids: List[str] = Body(..., embed=True),
    min_sources: int = 2,
):
    """
    Combine previously analyzed jobs (by job_id, from /analyze/pcap,
    /analyze/kpi, /analyze/stats) into one shared EventRouter and run the
    LLM root-cause agent over cross-source correlated event groups.

    Each pipeline call today only ever sees its own single-source events,
    so correlation across e.g. a PCAP job and a KPI job requires combining
    their already-computed results here, rather than in the pipeline
    itself. Falls back to a deterministic rule-based explanation per group
    when Ollama isn't running.
    """
    from src.orchestrator.event_router import EventRouter
    from src.agent.react_agent import analyze_root_cause

    router = EventRouter()
    for jid in job_ids:
        if jid not in _results:
            raise HTTPException(status_code=404, detail=f"Job '{jid}' not found")
        result = _results[jid]
        router.ingest(result["anomalies"], source=result["pipeline"])

        predictions = result.get("predictions", {}) or {}
        all_predicted = [a for anoms in predictions.values() for a in anoms]
        if all_predicted:
            router.ingest_predicted(all_predicted, source=result["pipeline"], lead_time_h=4)

    # analyze_root_cause makes blocking ollama.chat() calls — offload to a
    # thread so it doesn't stall the event loop for other concurrent requests.
    root_causes = await asyncio.to_thread(analyze_root_cause, router, min_sources=min_sources)
    return _make_json_serializable({
        "root_causes": root_causes,
        "correlated_events": router.get_correlated(min_sources=min_sources),
        "summary": router.summary(),
    })


@app.get("/analyze/{job_id}", tags=["Analysis"])
async def get_result(job_id: str):
    """Retrieve a previously computed analysis result by job ID."""
    if job_id not in _results:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return JSONResponse(content=_strip_dataframe(_results[job_id]))


def _numeric_kpi_columns(parsed: Dict[str, Any]) -> List[str]:
    """All uploaded-file columns usable as a chartable KPI metric — i.e.
    every column except the identifying ones (timestamp/cell/gNB) and any
    that never hold a numeric value in this file."""
    records = parsed.get("df_records")
    if not records:
        return []
    id_cols = {c for c in (parsed.get("timestamp_col"), parsed.get("cell_col"), parsed.get("gnb_col")) if c}
    candidates = parsed.get("kpi_columns") or parsed.get("l1l2_columns")
    if not candidates:
        candidates = [c for c in records[0].keys() if c not in id_cols]

    numeric = []
    for col in candidates:
        if col in id_cols:
            continue
        for row in records:
            val = row.get(col)
            if val is None:
                continue
            try:
                float(val)
                numeric.append(col)
            except (TypeError, ValueError):
                pass
            break
    return numeric


@app.get("/analyze/{job_id}/kpi-filters", tags=["Analysis"])
async def get_kpi_filters(job_id: str):
    """gNBs, cells and chartable metrics available in this job's uploaded
    file — populates the KPI Explorer's three filter pickers. `gnbs` is []
    for sources that don't track a gNB column (e.g. DU/CU stats exports)."""
    if job_id not in _results:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    parsed = _results[job_id].get("parsed", {})
    return {
        "gnbs": parsed.get("gnbs", []),
        "cells": parsed.get("cells", []),
        "metrics": _numeric_kpi_columns(parsed),
    }


@app.get("/analyze/{job_id}/kpi-series", tags=["Analysis"])
async def get_kpi_series(
    job_id: str,
    metrics: str,
    cells: Optional[str] = None,
    gnbs: Optional[str] = None,
    max_points: int = 80,
):
    """Per-cell time-series for one or more KPI columns, optionally
    restricted to a subset of gNBs/cells, downsampled for charting.
    `metrics`/`cells`/`gnbs` are comma-separated; omitting cells/gnbs means
    "all". Reads from the in-memory unstripped result (df_records never
    leaves the server in the main /analyze/* response, only via this
    endpoint). Returns {"series": {metric: {cell: [{timestamp, value}, ...]}}}."""
    if job_id not in _results:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    parsed = _results[job_id].get("parsed", {})
    records = parsed.get("df_records")
    ts_col = parsed.get("timestamp_col")
    cell_col = parsed.get("cell_col")
    gnb_col = parsed.get("gnb_col")
    if not records or not ts_col:
        raise HTTPException(status_code=400, detail="This job has no time-series data to chart.")

    metric_list = [m for m in metrics.split(",") if m]
    if not metric_list:
        raise HTTPException(status_code=400, detail="At least one metric is required.")
    cell_filter = set(cells.split(",")) if cells else None
    gnb_filter = set(gnbs.split(",")) if gnbs else None

    result: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for metric in metric_list:
        if metric not in records[0]:
            continue
        buckets: Dict[str, Dict[str, list]] = {}
        for row in records:
            if gnb_filter is not None and gnb_col and str(row.get(gnb_col)) not in gnb_filter:
                continue
            cell = str(row.get(cell_col)) if cell_col else "ALL"
            if cell_filter is not None and cell not in cell_filter:
                continue
            ts = row.get(ts_col)
            val = row.get(metric)
            if ts is None or val is None:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            if v != v:  # NaN
                continue
            buckets.setdefault(cell, {}).setdefault(str(ts), []).append(v)

        series: Dict[str, List[Dict[str, Any]]] = {}
        for cell, ts_map in buckets.items():
            points = [
                {"timestamp": ts_key, "value": round(sum(vals) / len(vals), 4)}
                for ts_key, vals in sorted(ts_map.items())
            ]
            if len(points) > max_points:
                step = len(points) / max_points
                points = [points[int(i * step)] for i in range(max_points)]
            series[cell] = points
        result[metric] = series

    return _make_json_serializable({"series": result})


def _build_report_sections(job_result: Dict[str, Any]) -> "tuple[List[Dict[str, Any]], Dict[str, Any]]":
    """Turn a stored /analyze/* result into (sections, meta) for
    report_generator — one row per anomaly / prediction, plus a summary
    header. Mirrors the tables the Streamlit dashboard already exports."""
    import pandas as pd

    anomalies = job_result.get("anomalies", []) or []
    predictions = job_result.get("predictions", {}) or {}
    predicted = [a for anoms in predictions.values() for a in anoms]

    sections: List[Dict[str, Any]] = []
    if anomalies:
        anom_df = pd.DataFrame([{
            "Severity": a.get("severity", ""),
            "Type": a.get("type") or a.get("label") or a.get("category", ""),
            "Cell": a.get("cell_id", "—"),
            "Layer": a.get("layer", ""),
            "Detector": a.get("detector", ""),
            "Evidence": a.get("evidence", ""),
            "Recommendation": a.get("recommendation", ""),
        } for a in anomalies])
        sections.append({
            "title": "Detected Anomalies", "df": anom_df,
            "notes": f"{len(anomalies)} anomalies detected",
        })

    if predicted:
        pred_df = pd.DataFrame([{
            "Lead Time (h)": a.get("lead_time_h", ""),
            "Metric": a.get("label") or a.get("category", ""),
            "Cell": a.get("cell_id", "—"),
            "Severity": a.get("severity", ""),
            "Detector": a.get("detector", ""),
            "Evidence": a.get("evidence", ""),
            "Recommendation": a.get("recommendation", ""),
        } for a in predicted])
        sections.append({
            "title": "Predicted Anomalies (Phase II Forecast)", "df": pred_df,
            "notes": f"{len(predicted)} anomalies forecast ahead of time",
        })

    sev_counts: Dict[str, int] = {}
    for a in anomalies:
        sev = a.get("severity", "Low")
        sev_counts[sev] = sev_counts.get(sev, 0) + 1

    meta = {
        "Source File": job_result.get("source_filename", "—"),
        "Pipeline": str(job_result.get("pipeline", "—")).upper(),
        "Total Anomalies": len(anomalies),
        "Critical": sev_counts.get("Critical", 0),
        "High": sev_counts.get("High", 0),
        "Medium": sev_counts.get("Medium", 0),
        "Low": sev_counts.get("Low", 0),
        "Predicted Anomalies (4h)": len(predicted),
    }
    return sections, meta


_REPORT_FORMATS = {
    "csv": ("text/csv", "csv"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
    "pdf": ("application/pdf", "pdf"),
    "html": ("text/html", "html"),
}


@app.get("/analyze/{job_id}/export", tags=["Analysis"])
async def export_report(job_id: str, format: str = "pdf"):
    """Download this job's anomaly report as csv | xlsx | docx | pdf | html."""
    if job_id not in _results:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    if format not in _REPORT_FORMATS:
        raise HTTPException(status_code=400, detail=f"format must be one of {list(_REPORT_FORMATS)}")

    from src.reports.report_generator import (
        generate_csv, generate_docx, generate_html, generate_pdf, generate_xlsx,
    )
    generators = {
        "csv": generate_csv, "xlsx": generate_xlsx, "docx": generate_docx,
        "pdf": generate_pdf, "html": generate_html,
    }

    sections, meta = _build_report_sections(_results[job_id])
    try:
        content = await asyncio.to_thread(generators[format], sections, meta)
    except Exception as e:
        logger.exception("Report export failed")
        raise HTTPException(status_code=500, detail=str(e))

    mime, ext = _REPORT_FORMATS[format]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{meta.get('Pipeline', 'report').lower()}_report_{job_id}_{timestamp}.{ext}"
    return Response(
        content=content, media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/feedback", tags=["Feedback"])
async def submit_feedback(
    event_id: str = Body(..., embed=True),
    source: str = Body("pcap", embed=True),
    anomaly_type: str = Body(..., embed=True),
    severity: str = Body("High", embed=True),
    detector: str = Body("Ensemble", embed=True),
    cell_id: str = Body("gNB-1", embed=True),
    evidence: str = Body("", embed=True),
    verdict: str = Body(..., embed=True),
    comment: str = Body("", embed=True),
):
    """Submit engineer feedback (correct | false_positive | uncertain) to log."""
    from src.feedback.store import save_feedback
    record = save_feedback(
        event_id=event_id,
        source=source,
        anomaly_type=anomaly_type,
        severity=severity,
        detector=detector,
        cell_id=cell_id,
        evidence=evidence,
        verdict=verdict,
        comment=comment,
    )
    return {"status": "saved", "record": record}
