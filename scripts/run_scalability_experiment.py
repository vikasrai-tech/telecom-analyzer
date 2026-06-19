"""
Scalability experiment: time KPI detection on 4 / 8 / 12 / 16 cells.
Writes results to docs/figures/scalability_results.json.
"""

import time, json, tracemalloc, sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from src.parsers.kpi_parser import parse_kpi_file
from src.detection.kpi_detector import detect_kpi_anomalies_by_detector

DATA = Path("data/raw/kpi_64ue_6hr.csv")
OUT  = Path("docs/figures/scalability_results.json")
RUNS_PER_CELL_COUNT = 3


def time_pipeline(df_subset):
    """Parse + detect; return (latency_s, peak_mb)."""
    # Write subset to temp CSV then parse it
    tmp = Path("data/raw/_tmp_subset.csv")
    df_subset.to_csv(tmp, index=False)

    tracemalloc.start()
    t0 = time.perf_counter()

    parsed = parse_kpi_file(str(tmp))
    _ = detect_kpi_anomalies_by_detector(parsed)

    latency = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    tmp.unlink(missing_ok=True)
    return latency, peak / 1e6   # seconds, MB


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATA)
    all_cells = sorted(df["Cell_ID"].unique())

    results = {}
    for n_cells in [4, 8, 12, 16]:
        cells = all_cells[:n_cells]
        subset = df[df["Cell_ID"].isin(cells)]
        n_rows = len(subset)
        run_times, run_mems = [], []
        for run in range(RUNS_PER_CELL_COUNT):
            lat, mem = time_pipeline(subset)
            run_times.append(round(lat, 2))
            run_mems.append(round(mem, 1))
            print(f"  cells={n_cells}, run={run+1}: {lat:.2f}s, {mem:.1f} MB")

        results[n_cells] = {
            "n_rows":        n_rows,
            "latency_mean":  round(sum(run_times) / len(run_times), 2),
            "latency_runs":  run_times,
            "memory_mean_mb": round(sum(run_mems) / len(run_mems), 1),
            "memory_runs":   run_mems,
        }

    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {OUT}")
    for n, v in results.items():
        print(f"  {n:2d} cells | {v['latency_mean']:.2f}s | {v['memory_mean_mb']:.1f} MB")


if __name__ == "__main__":
    main()
