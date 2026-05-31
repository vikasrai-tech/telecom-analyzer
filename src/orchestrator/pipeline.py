"""
Unified Telecom Analyzer — Pipeline Orchestrator

Provides run_pcap_pipeline() and run_kpi_pipeline() as the single
entry point for both the dashboard and the REST API.

CLI usage:
  python -m src.orchestrator.pipeline --input data/raw/test_5g_full.pcap
  python -m src.orchestrator.pipeline --input data/raw/5G_Network_KPI_Sample.xlsx --kpi
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def run_pcap_pipeline(
    file_path: str,
    explain_top_n: int = 4,
    skip_llm: bool = False,
) -> Dict[str, Any]:
    """
    Parse PCAP → detect anomalies → LLM explain top anomalies.

    Returns
    -------
    {
      "parsed":       dict from pcap_parser_real.parse_pcap(),
      "anomalies":    merged list from all 6 detectors,
      "by_detector":  {detector_name: [anomaly, ...]},
      "explanations": [{anomaly, explanation}, ...],
      "duration_s":   float,
    }
    """
    t0 = time.perf_counter()

    from src.parsers.pcap_parser_real import parse_pcap
    from src.detection.detector import detect_anomalies_by_detector, merge_detector_results
    from src.llm.explainer import explain_anomaly

    logger.info(f"[pipeline] Parsing PCAP: {file_path}")
    parsed = parse_pcap(file_path)

    logger.info("[pipeline] Running 6 PCAP detectors...")
    by_detector = detect_anomalies_by_detector(parsed)
    anomalies   = merge_detector_results(by_detector)

    explanations: List[Dict[str, Any]] = []
    if not skip_llm:
        top = [a for a in anomalies if a["severity"] in ("High", "Medium")][:explain_top_n]
        if not top:
            top = anomalies[:2]
        for a in top:
            logger.info(f"[pipeline] Explaining: {a['type']} ({a['severity']})")
            exp = explain_anomaly(a)
            explanations.append({"anomaly": a, "explanation": exp})

    duration = round(time.perf_counter() - t0, 2)
    logger.info(f"[pipeline] PCAP pipeline done in {duration}s — {len(anomalies)} anomalies")

    return {
        "pipeline":     "pcap",
        "input_file":   str(file_path),
        "parsed":       parsed,
        "anomalies":    anomalies,
        "by_detector":  by_detector,
        "explanations": explanations,
        "duration_s":   duration,
    }


def run_kpi_pipeline(
    file_path: str,
    explain_top_n: int = 4,
    skip_llm: bool = False,
) -> Dict[str, Any]:
    """
    Parse KPI file → detect anomalies → LLM explain top anomalies.

    Returns
    -------
    {
      "parsed":        dict from kpi_parser.parse_kpi_file(),
      "anomalies":     merged list from all 6 KPI detectors,
      "by_detector":   {detector_name: [anomaly, ...]},
      "summary_table": list from kpi_summary_table(),
      "explanations":  [{anomaly, explanation}, ...],
      "duration_s":    float,
    }
    """
    t0 = time.perf_counter()

    from src.parsers.kpi_parser import parse_kpi_file
    from src.detection.kpi_detector import (
        detect_kpi_anomalies_by_detector,
        detect_kpi_anomalies,
        kpi_summary_table,
    )
    from src.llm.explainer import explain_anomaly

    logger.info(f"[pipeline] Parsing KPI file: {file_path}")
    parsed = parse_kpi_file(file_path)

    logger.info("[pipeline] Running 6 KPI detectors...")
    by_detector = detect_kpi_anomalies_by_detector(parsed)
    anomalies   = sorted(
        [a for anoms in by_detector.values() for a in anoms],
        key=lambda a: ({"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(a["severity"], 0),
                       a.get("score", 0)),
        reverse=True,
    )
    summary = kpi_summary_table(parsed)

    explanations: List[Dict[str, Any]] = []
    if not skip_llm:
        top = [a for a in anomalies if a["severity"] in ("Critical", "High")][:explain_top_n]
        if not top:
            top = anomalies[:2]
        for a in top:
            # Adapt KPI anomaly to the PCAP anomaly schema expected by the explainer
            adapted = {
                "type":     a.get("label", a.get("kpi", "KPI anomaly")),
                "severity": a["severity"],
                "layer":    "KPI",
                "procedure": a.get("category", ""),
                "evidence": a.get("evidence", ""),
                "failure_causes": {},
                "detector": a.get("detector", ""),
            }
            logger.info(f"[pipeline] Explaining KPI: {adapted['type']} ({adapted['severity']})")
            exp = explain_anomaly(adapted)
            explanations.append({"anomaly": a, "explanation": exp})

    duration = round(time.perf_counter() - t0, 2)
    logger.info(f"[pipeline] KPI pipeline done in {duration}s — {len(anomalies)} anomalies")

    return {
        "pipeline":      "kpi",
        "input_file":    str(file_path),
        "parsed":        parsed,
        "anomalies":     anomalies,
        "by_detector":   by_detector,
        "summary_table": summary,
        "explanations":  explanations,
        "duration_s":    duration,
    }


def run_stats_pipeline(
    file_path: str,
    explain_top_n: int = 4,
    skip_llm: bool = False,
) -> Dict[str, Any]:
    """
    Parse DU/CU stats file → detect L1/L2 anomalies → LLM explain top anomalies.

    Returns
    -------
    {
      "parsed":       dict from stats_parser.parse_stats_file(),
      "anomalies":    merged list from all 6 stats detectors,
      "by_detector":  {detector_name: [anomaly, ...]},
      "explanations": [{anomaly, explanation}, ...],
      "duration_s":   float,
    }
    """
    t0 = time.perf_counter()

    from src.parsers.stats_parser import parse_stats_file
    from src.detection.stats_detector import (
        detect_stats_anomalies_by_detector,
        detect_stats_anomalies,
    )
    from src.llm.explainer import explain_anomaly

    logger.info(f"[pipeline] Parsing stats file: {file_path}")
    parsed = parse_stats_file(file_path)

    logger.info("[pipeline] Running 6 stats detectors...")
    by_detector = detect_stats_anomalies_by_detector(parsed)
    anomalies   = detect_stats_anomalies(parsed)

    explanations: List[Dict[str, Any]] = []
    if not skip_llm:
        top = [a for a in anomalies if a["severity"] in ("Critical", "High")][:explain_top_n]
        if not top:
            top = anomalies[:2]
        for a in top:
            adapted = {
                "type":           a.get("label", "L1/L2 anomaly"),
                "severity":       a["severity"],
                "layer":          "KPI",
                "procedure":      a.get("category", ""),
                "evidence":       a.get("evidence", ""),
                "failure_causes": {},
                "detector":       a.get("detector", ""),
            }
            exp = explain_anomaly(adapted)
            explanations.append({"anomaly": a, "explanation": exp})

    duration = round(time.perf_counter() - t0, 2)
    logger.info(f"[pipeline] Stats pipeline done in {duration}s — {len(anomalies)} anomalies")

    return {
        "pipeline":     "stats",
        "input_file":   str(file_path),
        "parsed":       parsed,
        "anomalies":    anomalies,
        "by_detector":  by_detector,
        "explanations": explanations,
        "duration_s":   duration,
    }


def run_pipeline(
    file_path: str,
    kpi: bool = False,
    stats: bool = False,
    explain_top_n: int = 4,
    skip_llm: bool = False,
) -> Dict[str, Any]:
    """Auto-detect or force pipeline type."""
    suffix = Path(file_path).suffix.lower()
    if kpi or suffix in (".xlsx", ".xls"):
        return run_kpi_pipeline(file_path, explain_top_n=explain_top_n, skip_llm=skip_llm)
    if stats:
        return run_stats_pipeline(file_path, explain_top_n=explain_top_n, skip_llm=skip_llm)
    if suffix in (".csv", ".parquet"):
        # Ambiguous — try stats first (srsRAN/OAI/NIST), fall back to KPI
        try:
            return run_stats_pipeline(file_path, explain_top_n=explain_top_n, skip_llm=skip_llm)
        except Exception:
            return run_kpi_pipeline(file_path, explain_top_n=explain_top_n, skip_llm=skip_llm)
    return run_pcap_pipeline(file_path, explain_top_n=explain_top_n, skip_llm=skip_llm)


# ── CLI ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    parser = argparse.ArgumentParser(description="Telecom Analyzer — CLI pipeline runner")
    parser.add_argument("--input",  required=True, help="Path to PCAP or KPI file")
    parser.add_argument("--kpi",    action="store_true", help="Force KPI mode")
    parser.add_argument("--output", default=None, help="Write JSON report to this path")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM explanations")
    args = parser.parse_args()

    result = run_pipeline(args.input, kpi=args.kpi, skip_llm=args.no_llm)

    # Print summary to stdout
    print(f"\n{'='*60}")
    print(f"Pipeline : {result['pipeline'].upper()}")
    print(f"Input    : {result['input_file']}")
    print(f"Duration : {result['duration_s']}s")
    print(f"Anomalies: {len(result['anomalies'])}")
    sev_counts = {}
    for a in result["anomalies"]:
        sev_counts[a["severity"]] = sev_counts.get(a["severity"], 0) + 1
    for sev, n in sorted(sev_counts.items()):
        print(f"  {sev:10s}: {n}")
    print(f"Explained: {len(result['explanations'])}")
    print(f"{'='*60}\n")

    if args.output:
        # Remove non-serialisable pandas objects from parsed
        out = {k: v for k, v in result.items() if k != "parsed"}
        out["parsed_summary"] = {
            k: v for k, v in result["parsed"].items()
            if k not in ("df_records",)
        }
        with open(args.output, "w") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"Report written to: {args.output}")
