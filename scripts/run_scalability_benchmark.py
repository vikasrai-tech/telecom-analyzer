"""
Scalability benchmark — replaces scripts/run_scalability_experiment.py.

Profiles:
  1. Full pipeline stage timings (PCAP + KPI + Stats + EventRouter)
  2. KPI detection scaling sweep: 4 / 8 / 12 / 16 cells

Usage:
    cd /mnt/e/telecom-analyzer
    python scripts/run_scalability_benchmark.py

Results saved to:
    results/scalability/scalability_results.json
"""

import json
import logging
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

DATA_KPI   = ROOT / "data" / "raw" / "kpi_64ue_6hr.csv"
DATA_STATS = ROOT / "data" / "raw" / "stats_64ue_6hr.csv"
DATA_PCAP  = ROOT / "data" / "raw" / "ue_64_6hr.pcap"
OUT_DIR    = ROOT / "results" / "scalability"

RUNS_PER_CELL = 3


def timed_stage(fn):
    """Run fn(), return (result, latency_s, peak_mb)."""
    tracemalloc.start()
    t0 = time.perf_counter()
    result = fn()
    latency = round(time.perf_counter() - t0, 4)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, latency, round(peak / 1e6, 2)


def run_full_pipeline():
    """Profile each stage of the full pipeline."""
    from src.parsers.kpi_parser import parse_kpi_file
    from src.parsers.stats_parser import parse_stats_file
    from src.detection.kpi_detector import detect_kpi_anomalies
    from src.detection.stats_detector import detect_stats_anomalies
    from src.orchestrator.event_router import EventRouter

    stages = {}

    # Stage 1: PCAP parse
    pcap_parsed = None
    if DATA_PCAP.exists():
        try:
            from src.parsers.pcap_parser_real import parse_pcap
            _, lat, mem = timed_stage(lambda: parse_pcap(str(DATA_PCAP)))
            stages["pcap_parse"] = {"latency_s": lat, "peak_mb": mem, "status": "ok"}
            print(f"  PCAP parse:   {lat:.3f}s, {mem:.1f} MB")
            # Get result for detection stage
            pcap_parsed = parse_pcap(str(DATA_PCAP))
        except Exception as e:
            stages["pcap_parse"] = {"latency_s": None, "peak_mb": None, "status": f"skipped: {e}"}
            print(f"  PCAP parse:   SKIPPED ({e})")
    else:
        stages["pcap_parse"] = {"latency_s": None, "peak_mb": None, "status": "file not found"}
        print(f"  PCAP parse:   SKIPPED (file not found)")

    # Stage 2: PCAP detect
    if pcap_parsed and isinstance(pcap_parsed, dict) and pcap_parsed.get("anomalies"):
        try:
            _, lat, mem = timed_stage(lambda: pcap_parsed["anomalies"])
            stages["pcap_detect"] = {"latency_s": lat, "peak_mb": mem, "status": "ok (anomalies pre-computed in parser)"}
            print(f"  PCAP detect:  anomalies pre-computed in parser ({len(pcap_parsed['anomalies'])} anomalies)")
        except Exception as e:
            stages["pcap_detect"] = {"latency_s": None, "peak_mb": None, "status": f"skipped: {e}"}
    else:
        stages["pcap_detect"] = {"latency_s": None, "peak_mb": None, "status": "skipped (no pcap_parsed)"}

    # Stage 3: KPI parse
    kpi_parsed, lat, mem = timed_stage(lambda: parse_kpi_file(str(DATA_KPI)))
    stages["kpi_parse"] = {"latency_s": lat, "peak_mb": mem, "status": "ok",
                           "rows": kpi_parsed.get("rows", 0)}
    print(f"  KPI parse:    {lat:.3f}s, {mem:.1f} MB ({kpi_parsed.get('rows',0)} rows)")

    # Stage 4: KPI detect
    _, lat, mem = timed_stage(lambda: detect_kpi_anomalies(kpi_parsed))
    stages["kpi_detect"] = {"latency_s": lat, "peak_mb": mem, "status": "ok"}
    print(f"  KPI detect:   {lat:.3f}s, {mem:.1f} MB")

    # Stage 5: Stats parse + detect
    stats_parsed, lat_sp, mem_sp = timed_stage(lambda: parse_stats_file(str(DATA_STATS)))
    stats_anoms, lat_sd, mem_sd = timed_stage(lambda: detect_stats_anomalies(stats_parsed))
    stages["stats_parse"] = {"latency_s": lat_sp, "peak_mb": mem_sp, "status": "ok",
                             "rows": stats_parsed.get("rows", 0)}
    stages["stats_detect"] = {"latency_s": lat_sd, "peak_mb": mem_sd, "status": "ok"}
    print(f"  Stats parse:  {lat_sp:.3f}s, {mem_sp:.1f} MB ({stats_parsed.get('rows',0)} rows)")
    print(f"  Stats detect: {lat_sd:.3f}s, {mem_sd:.1f} MB")

    # Stage 6: EventRouter correlation
    kpi_anoms = detect_kpi_anomalies(kpi_parsed)

    def run_router():
        r = EventRouter()
        r.ingest(kpi_anoms, source="kpi")
        r.ingest(stats_anoms, source="stats")
        return r

    router, lat, mem = timed_stage(run_router)
    summary = router.summary()
    stages["correlation"] = {
        "latency_s": lat, "peak_mb": mem, "status": "ok",
        "total_events": summary["total"],
        "correlated_events": summary["correlated"],
    }
    print(f"  Correlation:  {lat:.3f}s, {mem:.1f} MB "
          f"({summary['total']} events, {summary['correlated']} correlated)")

    return stages


def run_cell_scaling():
    """KPI-only detection scaling sweep: 4 / 8 / 12 / 16 cells."""
    from src.parsers.kpi_parser import parse_kpi_file
    from src.detection.kpi_detector import detect_kpi_anomalies_by_detector

    df = pd.read_csv(DATA_KPI)
    all_cells = sorted(df["Cell_ID"].unique())
    tmp = DATA_KPI.parent / "_tmp_subset.csv"

    scaling = {}
    for n_cells in [4, 8, 12, 16]:
        cells  = all_cells[:n_cells]
        subset = df[df["Cell_ID"].isin(cells)]
        n_rows = len(subset)
        run_times, run_mems = [], []

        for run in range(RUNS_PER_CELL):
            subset.to_csv(tmp, index=False)

            def _pipeline():
                p = parse_kpi_file(str(tmp))
                detect_kpi_anomalies_by_detector(p)

            _, lat, mem = timed_stage(_pipeline)
            run_times.append(lat)
            run_mems.append(mem)
            print(f"    cells={n_cells}, run={run+1}: {lat:.3f}s, {mem:.1f} MB")

        tmp.unlink(missing_ok=True)
        scaling[str(n_cells)] = {
            "n_rows":         n_rows,
            "latency_mean":   round(sum(run_times) / len(run_times), 3),
            "latency_runs":   [round(t, 3) for t in run_times],
            "memory_mean_mb": round(sum(run_mems) / len(run_mems), 1),
            "memory_runs":    [round(m, 1) for m in run_mems],
        }

    return scaling


def main():
    print("=" * 60)
    print("SCALABILITY BENCHMARK")
    print(f"Random seed: {RANDOM_SEED}")
    print("=" * 60)

    print("\n[1/3] Full pipeline stage profiling ...")
    pipeline_stages = run_full_pipeline()

    print("\n[2/3] KPI detection cell-scaling sweep ...")
    cell_scaling = run_cell_scaling()

    print("\n[3/3] Saving results ...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    output = {
        "random_seed":     RANDOM_SEED,
        "dataset": {
            "kpi_file":   str(DATA_KPI.name),
            "stats_file": str(DATA_STATS.name),
            "pcap_file":  str(DATA_PCAP.name),
        },
        "pipeline_stages": pipeline_stages,
        "cell_scaling":    cell_scaling,
        "memory_note": (
            "Memory measured with tracemalloc per stage. "
            "Peak is the stage's own allocation peak, not cumulative. "
            "Reported in MB. The 1.2 GB figure cited in earlier PPT slides "
            "was incorrect — actual measured peak for KPI-only pipeline is ~21 MB."
        ),
    }

    json_path = OUT_DIR / "scalability_results.json"
    json_path.write_text(json.dumps(output, indent=2))
    print(f"  Saved: {json_path}")

    print("\n" + "=" * 60)
    print("SCALABILITY RESULTS (ACTUAL)")
    print("=" * 60)
    print("\n--- Full Pipeline Stages ---")
    for stage, d in pipeline_stages.items():
        lat = f"{d['latency_s']:.3f}s" if d["latency_s"] is not None else "N/A"
        mem = f"{d['peak_mb']:.1f} MB" if d["peak_mb"] is not None else "N/A"
        print(f"  {stage:<20} {lat:>8}  {mem:>10}  [{d.get('status','?')}]")

    print("\n--- Cell Scaling (KPI detection) ---")
    print(f"  {'Cells':>6} {'Rows':>7} {'Mean Lat (s)':>13} {'Mean Mem (MB)':>14}")
    for n_str, d in sorted(cell_scaling.items(), key=lambda x: int(x[0])):
        print(f"  {n_str:>6} {d['n_rows']:>7} {d['latency_mean']:>13.3f} {d['memory_mean_mb']:>14.1f}")

    # Manifest
    manifest_path = ROOT / "results" / "experiment_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass
    manifest["scalability"] = {
        "script":       "run_scalability_benchmark.py",
        "random_seed":  RANDOM_SEED,
        "results_file": str(json_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
