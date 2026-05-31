"""
Nightly Retraining Script
Run via cron or `make retrain`.

Usage:
  python scripts/nightly_retrain.py
  python scripts/nightly_retrain.py --dry-run
  python scripts/nightly_retrain.py --store data/feedback/feedback_log.jsonl
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Nightly detector retraining")
    parser.add_argument("--store",   default=None,
                        help="Path to feedback JSONL store")
    parser.add_argument("--config",  default="data/models/retrain_config.json",
                        help="Output config path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute adjustments but don't write config")
    args = parser.parse_args()

    from src.detection.retrainer import run_retraining

    store  = Path(args.store)  if args.store  else None
    config = Path(args.config)

    logger.info("=" * 60)
    logger.info("Nightly Retraining — Unified Telecom Analyzer")
    logger.info("=" * 60)

    report = run_retraining(
        store_path=store,
        config_path=config,
        dry_run=args.dry_run,
    )

    print(f"\nStatus:      {report['status']}")
    print(f"Feedback:    {report['total_feedback']} records")
    if report.get("overall_precision") is not None:
        print(f"Precision:   {report['overall_precision']*100:.1f}%")

    if report["status"] == "skipped":
        print(f"Reason:      {report.get('reason','')}")
        return

    print(f"\nAdjustments ({len(report['adjustments'])}):")
    for det, adj in report["adjustments"].items():
        changed = "✓ changed" if adj["changed"] else "— unchanged"
        print(f"  {det:25s}  fp={adj['fp_rate']*100:.0f}%  "
              f"{adj['before']} → {adj['after']}  {changed}")

    if report["skipped"]:
        print(f"\nSkipped (< 2 rated): {', '.join(report['skipped'])}")

    if not args.dry_run:
        print(f"\nConfig written: {config}")
    else:
        print("\n[dry-run] Config NOT written.")


if __name__ == "__main__":
    main()
