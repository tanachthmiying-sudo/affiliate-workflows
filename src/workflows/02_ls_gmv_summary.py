"""
Workflow 2: LS Creators GMV Summary for Each Campaign
──────────────────────────────────────────────────────
Objective:
  - Verify LS (Live Streaming) completeness per campaign schedule
  - Calculate GMV per creator per campaign
  - Flag creators who have not completed their LS obligations
  - Write campaign-level summary to AFS Base

Inputs:  TikTok Seller CSV / BI system  +  AFS Base (LS schedule table)
Outputs: AFS Base campaign summary table  +  Feishu Bot summary card
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feishu_client import FeishuClient
from tiktok_parser import safe_float, safe_int, get_sample_videos
from config_loader import load_config
from datetime import datetime
from collections import defaultdict


SAMPLE_LS_SCHEDULE = [
    {"creator_id": "C001", "campaign_id": "CAMP_JUN", "required_ls": 2, "completed_ls": 2, "gmv": 8500.0},
    {"creator_id": "C002", "campaign_id": "CAMP_JUN", "required_ls": 1, "completed_ls": 0, "gmv": 0.0},
    {"creator_id": "C004", "campaign_id": "CAMP_JUN", "required_ls": 3, "completed_ls": 3, "gmv": 24000.0},
    {"creator_id": "C005", "campaign_id": "CAMP_JUN", "required_ls": 2, "completed_ls": 1, "gmv": 45000.0},
    {"creator_id": "C001", "campaign_id": "CAMP_MAY", "required_ls": 2, "completed_ls": 2, "gmv": 7200.0},
    {"creator_id": "C003", "campaign_id": "CAMP_MAY", "required_ls": 1, "completed_ls": 1, "gmv": 1100.0},
]


def run(dry_run: bool = False, data_dir: str = "data/samples"):
    cfg = load_config()
    client = FeishuClient()

    print("\n[WF2] ▶ LS GMV Campaign Summary — starting")

    # ── 1. Load LS schedule from AFS Base or sample ─────────────────────
    app_token = cfg.get("afs_base_token")
    ls_table_id = cfg.get("ls_schedule_table_id")
    campaign_table_id = cfg.get("campaign_summary_table_id")

    if app_token and ls_table_id:
        raw = client.get_records(app_token, ls_table_id)
        ls_data = [r.get("fields", {}) for r in raw]
        print(f"[WF2] Loaded {len(ls_data)} LS records from AFS Base")
    else:
        ls_data = SAMPLE_LS_SCHEDULE
        print("[WF2] Using sample LS schedule data")

    # ── 2. Aggregate by campaign ─────────────────────────────────────────
    campaigns: dict = defaultdict(lambda: {
        "total_creators": 0, "completed": 0, "incomplete": 0,
        "total_required_ls": 0, "total_completed_ls": 0, "total_gmv": 0.0,
        "incomplete_creators": [],
    })

    for row in ls_data:
        cid = row.get("campaign_id", "UNKNOWN")
        required = safe_int(row.get("required_ls", 0)) or 0
        completed = safe_int(row.get("completed_ls", 0)) or 0
        gmv = safe_float(row.get("gmv", 0)) or 0.0

        campaigns[cid]["total_creators"] += 1
        campaigns[cid]["total_required_ls"] += required
        campaigns[cid]["total_completed_ls"] += completed
        campaigns[cid]["total_gmv"] += gmv

        if completed >= required:
            campaigns[cid]["completed"] += 1
        else:
            campaigns[cid]["incomplete"] += 1
            campaigns[cid]["incomplete_creators"].append(
                f"{row.get('creator_id', '?')} ({completed}/{required})"
            )

    print(f"[WF2] Campaigns found: {list(campaigns.keys())}")

    # ── 3. Write campaign summaries to AFS Base ──────────────────────────
    if app_token and campaign_table_id and not dry_run:
        for campaign_id, stats in campaigns.items():
            completion_rate = (
                stats["total_completed_ls"] / stats["total_required_ls"] * 100
                if stats["total_required_ls"] > 0 else 0
            )
            fields = {
                "Campaign ID": campaign_id,
                "Total Creators": stats["total_creators"],
                "LS Completed": stats["completed"],
                "LS Incomplete": stats["incomplete"],
                "Total GMV (THB)": round(stats["total_gmv"], 2),
                "LS Completion Rate (%)": round(completion_rate, 1),
                "Incomplete Creators": ", ".join(stats["incomplete_creators"]),
                "Last Updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            existing = client.find_record_by_field(
                app_token, campaign_table_id, "Campaign ID", campaign_id
            )
            rid = existing.get("record_id") if existing else None
            client.upsert_record(app_token, campaign_table_id, fields, record_id=rid)
            print(f"[WF2] Upserted campaign: {campaign_id}")

    # ── 4. Build summary for bot message ────────────────────────────────
    total_gmv_all = sum(c["total_gmv"] for c in campaigns.values())
    all_incomplete = []
    for cid, stats in campaigns.items():
        all_incomplete.extend([f"[{cid}] {x}" for x in stats["incomplete_creators"]])

    summary_lines = []
    for cid, stats in campaigns.items():
        rate = (stats["total_completed_ls"] / stats["total_required_ls"] * 100
                if stats["total_required_ls"] > 0 else 0)
        summary_lines.append(
            f"**{cid}** — GMV: {stats['total_gmv']:,.0f} THB | "
            f"Completion: {rate:.0f}% ({stats['completed']}/{stats['total_creators']} creators)"
        )

    if not dry_run:
        client.send_workflow_summary(
            workflow_name="LS GMV Campaign Summary",
            status="warning" if all_incomplete else "success",
            summary_lines=summary_lines + [f"📦 Total GMV all campaigns: **{total_gmv_all:,.0f} THB**"],
            highlight_items=all_incomplete[:5] if all_incomplete else ["All creators completed LS ✅"],
        )

    print("[WF2] ✓ Complete")
    return {
        "campaigns": dict(campaigns),
        "total_gmv": total_gmv_all,
        "incomplete_creators": all_incomplete,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WF2: LS GMV Campaign Summary")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data-dir", default="data/samples")
    args = parser.parse_args()
    run(dry_run=args.dry_run, data_dir=args.data_dir)
