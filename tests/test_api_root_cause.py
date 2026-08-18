"""Tests for POST /agent/root-cause (src/api/main.py).

Combines previously-analyzed jobs (by job_id) into one shared EventRouter
and runs the root-cause agent — this is the API-side counterpart to the
dashboard's Root Cause Agent tab. Populates the in-memory job store
directly rather than going through file upload, to keep this test fast
and deterministic.
"""

from fastapi.testclient import TestClient

from src.api.main import app, _results

client = TestClient(app)

KPI_ANOM = {
    "label": "dl_bler", "category": "l1_quality", "cell_id": "PCI_3",
    "severity": "Critical", "value": 22.0, "unit": "%",
    "evidence": "BLER=22%", "score": 6.0, "detector": "Threshold",
}
STATS_ANOM = {
    "label": "Handover_Success_Rate_%", "category": "mobility", "cell_id": "PCI_3",
    "severity": "High", "value": 60.0, "unit": "%",
    "evidence": "HO success rate dropped to 60%", "score": 5.0, "detector": "Threshold",
}


def _seed_job(job_id: str, pipeline: str, anomalies, predictions=None):
    _results[job_id] = {
        "pipeline": pipeline,
        "anomalies": anomalies,
        "predictions": predictions or {},
    }


def test_root_cause_endpoint_combines_jobs_and_correlates():
    _seed_job("job-kpi-1",   "kpi",   [KPI_ANOM])
    _seed_job("job-stats-1", "stats", [STATS_ANOM])

    resp = client.post("/agent/root-cause", json={"job_ids": ["job-kpi-1", "job-stats-1"]})
    assert resp.status_code == 200
    data = resp.json()

    assert data["summary"]["total"] == 2
    assert len(data["correlated_events"]) == 2
    assert len(data["root_causes"]) == 1
    rc = data["root_causes"][0]
    assert rc["cell_id"] == "PCI_3"
    assert len(rc["causal_chain"]) == 2


def test_root_cause_endpoint_unknown_job_404():
    resp = client.post("/agent/root-cause", json={"job_ids": ["does-not-exist"]})
    assert resp.status_code == 404


def test_root_cause_endpoint_single_job_no_correlation():
    _seed_job("job-kpi-only", "kpi", [KPI_ANOM])
    resp = client.post("/agent/root-cause", json={"job_ids": ["job-kpi-only"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["root_causes"] == []
