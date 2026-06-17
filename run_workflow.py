#!/usr/bin/env python3
"""
Migo Affiliate Workflows — Master Runner
Usage:
  python run_workflow.py --workflow all [--dry-run]
  python run_workflow.py --workflow 1 [--dry-run]
  python run_workflow.py --workflow 1,3,5 [--dry-run]
"""

import sys
import os
import argparse
import time

# Ensure src/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


WORKFLOWS = {
    "1": {
        "name": "Video Status Tracker",
        "module": "workflows.01_video_status_tracker",
        "file": "src/workflows/01_video_status_tracker.py",
    },
    "2": {
        "name": "LS GMV Campaign Summary",
        "module": "workflows.02_ls_gmv_summary",
        "file": "src/workflows/02_ls_gmv_summary.py",
    },
    "3": {
        "name": "Creator Pool Update",
        "module": "workflows.03_creator_pool_update",
        "file": "src/workflows/03_creator_pool_update.py",
    },
    "4": {
        "name": "Sample Approve Filter",
        "module": "workflows.04_sample_approve_filter",
        "file": "src/workflows/04_sample_approve_filter.py",
    },
    "5": {
        "name": "Video & LS Trend Analysis",
        "module": "workflows.05_video_ls_trend_analysis",
        "file": "src/workflows/05_video_ls_trend_analysis.py",
    },
    "6": {
        "name": "Creator Tier Analysis",
        "module": "workflows.06_creator_tier_analysis",
        "file": "src/workflows/06_creator_tier_analysis.py",
    },
}


def import_and_run(wf_num: str, dry_run: bool, data_dir: str, output_dir: str):
    """Dynamically import and execute a workflow module."""
    wf = WORKFLOWS[wf_num]
    print(f"\n{'='*60}")
    print(f"  WF{wf_num}: {wf['name']}")
    print(f"{'='*60}")

    # Import by file path to avoid module name conflict with leading digits
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"wf_{wf_num}",
        os.path.join(os.path.dirname(__file__), wf["file"]),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    kwargs = {"dry_run": dry_run}
    if wf_num in ("1", "3", "4"):
        kwargs["data_dir"] = data_dir
    if wf_num in ("5", "6"):
        kwargs["output_dir"] = output_dir

    start = time.time()
    result = mod.run(**kwargs)
    elapsed = time.time() - start
    print(f"\n  ✓ WF{wf_num} completed in {elapsed:.1f}s")
    return result


def main():
    parser = argparse.ArgumentParser(description="Migo Affiliate Workflow Runner")
    parser.add_argument(
        "--workflow",
        default="all",
        help='Workflow(s) to run: "all", "1", "2,3", etc.',
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip all Feishu writes")
    parser.add_argument("--data-dir", default="data/samples", help="Directory with TikTok CSV exports")
    parser.add_argument("--output-dir", default="reports", help="Directory for generated reports")
    args = parser.parse_args()

    if args.workflow == "all":
        to_run = list(WORKFLOWS.keys())
    else:
        to_run = [w.strip() for w in args.workflow.split(",")]

    invalid = [w for w in to_run if w not in WORKFLOWS]
    if invalid:
        print(f"Unknown workflow(s): {invalid}. Valid: {list(WORKFLOWS.keys())} or 'all'")
        sys.exit(1)

    print(f"\n{'#'*60}")
    print(f"  Migo Affiliate Workflows")
    print(f"  Running: {to_run}  |  Dry run: {args.dry_run}")
    print(f"{'#'*60}")

    results = {}
    errors = {}

    for wf_num in to_run:
        try:
            results[wf_num] = import_and_run(
                wf_num, args.dry_run, args.data_dir, args.output_dir
            )
        except Exception as e:
            print(f"\n[ERROR] WF{wf_num} failed: {e}")
            errors[wf_num] = str(e)

    # Final summary
    print(f"\n{'='*60}")
    print(f"  Run Summary")
    print(f"{'='*60}")
    for wf_num in to_run:
        if wf_num in errors:
            print(f"  WF{wf_num} {WORKFLOWS[wf_num]['name']}: ❌ FAILED — {errors[wf_num]}")
        else:
            print(f"  WF{wf_num} {WORKFLOWS[wf_num]['name']}: ✅ OK")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
