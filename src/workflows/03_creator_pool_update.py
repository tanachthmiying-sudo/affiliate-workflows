"""
Workflow 3: Creators Pool Data Update
───────────────────────────────────────
Objective:
  - Pull latest creator performance metrics from TikTok Seller
  - Refresh creator pool table in AFS Base with up-to-date data
  - Auto-recalculate creator tiers based on current GMV / follower data
  - Flag status changes (new Active, newly Inactive)

Inputs:  TikTok Seller CSV / BI system
Outputs: AFS Base creator pool table (bulk update)  +  Feishu Bot summary
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feishu_client import FeishuClient
from tiktok_parser import (
    load_latest_creator_csv,
    get_sample_creators,
    classify_creator_tier,
    safe_int,
    safe_float,
)
from config_loader import load_config
from datetime import datetime


def run(dry_run: bool = False, data_dir: str = "data/samples"):
    cfg = load_config()
    client = FeishuClient()

    print("\n[WF3] ▶ Creator Pool Update — starting")

    # ── 1. Load fresh creator data from TikTok export ───────────────────
    try:
        creators = load_latest_creator_csv(data_dir)
        print(f"[WF3] Loaded {len(creators)} creators from CSV")
    except FileNotFoundError:
        print("[WF3] No CSV found — using sample data")
        creators = get_sample_creators()

    # ── 2. Enrich: recalculate tiers ────────────────────────────────────
    tier_counts: dict = {}
    for c in creators:
        followers = safe_int(c.get("followers", 0)) or 0
        gmv = safe_float(c.get("gmv", 0)) or 0.0
        new_tier = classify_creator_tier(followers, gmv)
        c["computed_tier"] = new_tier
        tier_counts[new_tier] = tier_counts.get(new_tier, 0) + 1

    active = [c for c in creators if str(c.get("status", "")).lower() == "active"]
    pending = [c for c in creators if str(c.get("status", "")).lower() == "pending"]
    inactive = [c for c in creators if str(c.get("status", "")).lower() in ("inactive", "churned")]

    print(f"[WF3] Active: {len(active)} | Pending: {len(pending)} | Inactive: {len(inactive)}")
    print(f"[WF3] Tier distribution: {tier_counts}")

    # ── 3. Sync to AFS Base ─────────────────────────────────────────────
    app_token = cfg.get("afs_base_token")
    table_id = cfg.get("creator_pool_table_id")

    synced = 0
    if app_token and table_id and not dry_run:
        for c in creators:
            fields = {
                "Creator ID": c.get("creator_id", ""),
                "Creator Name": c.get("creator_name", ""),
                "Followers": safe_int(c.get("followers")) or 0,
                "GMV (THB)": safe_float(c.get("gmv")) or 0.0,
                "Video Count": safe_int(c.get("video_count")) or 0,
                "Live Count": safe_int(c.get("live_count")) or 0,
                "Status": c.get("status", ""),
                "Creator Tier": c["computed_tier"],
                "Last Updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            existing = client.find_record_by_field(
                app_token, table_id, "Creator ID", c.get("creator_id", "")
            )
            rid = existing.get("record_id") if existing else None
            client.upsert_record(app_token, table_id, fields, record_id=rid)
            synced += 1

        print(f"[WF3] Synced {synced} creators to AFS Base")
    else:
        print("[WF3] DRY RUN or no Base config — skipping write")

    # ── 4. Feishu Bot summary ────────────────────────────────────────────
    tier_summary = " | ".join(f"{k}: {v}" for k, v in sorted(tier_counts.items()))
    summary_lines = [
        f"Total creators in pool: **{len(creators)}**",
        f"✅ Active: {len(active)}  |  ⏳ Pending: {len(pending)}  |  ⚠️ Inactive: {len(inactive)}",
        f"Tier breakdown: {tier_summary}",
        f"Records synced to AFS Base: {synced if not dry_run else 'DRY RUN'}",
    ]

    top_gmv = sorted(active, key=lambda x: safe_float(x.get("gmv", 0)) or 0, reverse=True)[:5]
    highlights = [
        f"#{i+1} {c.get('creator_name','?')} ({c['computed_tier']}) — {safe_float(c.get('gmv',0)):,.0f} THB GMV"
        for i, c in enumerate(top_gmv)
    ]

    if not dry_run:
        client.send_workflow_summary(
            workflow_name="Creator Pool Update",
            status="success",
            summary_lines=summary_lines,
            highlight_items=highlights,
        )

    print("[WF3] ✓ Complete")
    return {
        "total_creators": len(creators),
        "active": len(active),
        "pending": len(pending),
        "tier_counts": tier_counts,
        "synced": synced,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WF3: Creator Pool Update")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data-dir", default="data/samples")
    args = parser.parse_args()
    run(dry_run=args.dry_run, data_dir=args.data_dir)
