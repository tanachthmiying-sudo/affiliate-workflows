"""
Workflow 1: Recheck Creators Posted Video Status & Track Content Performance
─────────────────────────────────────────────────────────────────────────────
Objective:
  - Verify posting completeness for all contracted creators
  - Surface high-performing videos for Boost Ads consideration
  - Flag underperforming or missing posts
  - Write results back to AFS Base (Feishu Bitable)

Inputs:  TikTok Seller CSV export or BI JSON  +  AFS Base
Outputs: AFS Base table update  +  Feishu Bot summary card
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feishu_client import FeishuClient
from tiktok_parser import (
    load_latest_video_csv,
    get_sample_videos,
    classify_video_potential,
    safe_int,
    safe_float,
)
from config_loader import load_config
from datetime import datetime


def run(dry_run: bool = False, data_dir: str = "data/samples"):
    cfg = load_config()
    client = FeishuClient()

    print("\n[WF1] ▶ Video Status Tracker — starting")

    # ── 1. Load video data ──────────────────────────────────────────────
    try:
        videos = load_latest_video_csv(data_dir)
        print(f"[WF1] Loaded {len(videos)} videos from CSV")
    except FileNotFoundError:
        print("[WF1] No CSV found — using sample data")
        videos = get_sample_videos()

    # ── 2. Analyse each video ───────────────────────────────────────────
    posted = [v for v in videos if str(v.get("status", "")).lower() == "posted"]
    pending = [v for v in videos if str(v.get("status", "")).lower() == "pending"]
    not_posted = [v for v in videos if str(v.get("status", "")).lower() in ("not posted", "missing", "")]

    for v in videos:
        v["potential"] = classify_video_potential(v)

    high_potential = [v for v in posted if v["potential"] == "🔥 High"]
    boost_candidates = [v for v in high_potential if not v.get("is_boosted")]

    total_gmv = sum(safe_float(v.get("gmv", 0)) or 0 for v in posted)
    total_views = sum(safe_int(v.get("views", 0)) or 0 for v in posted)

    print(f"[WF1] Posted: {len(posted)} | Pending: {len(pending)} | Not Posted: {len(not_posted)}")
    print(f"[WF1] High potential: {len(high_potential)} | Boost candidates: {len(boost_candidates)}")
    print(f"[WF1] Total GMV: {total_gmv:,.0f} THB | Total Views: {total_views:,}")

    # ── 3. Write to AFS Base (Feishu Bitable) ──────────────────────────
    app_token = cfg.get("afs_base_token")
    table_id = cfg.get("video_table_id")

    if app_token and table_id and not dry_run:
        updates = []
        for v in videos:
            record_id = v.get("feishu_record_id")  # pre-populated from earlier sync
            fields = {
                "Video ID": v.get("video_id", ""),
                "Status": v.get("status", ""),
                "Views": safe_int(v.get("views")) or 0,
                "GMV (THB)": safe_float(v.get("gmv")) or 0,
                "Orders": safe_int(v.get("orders")) or 0,
                "Growth Potential": v["potential"],
                "Boost Recommended": "Yes" if v in boost_candidates else "No",
                "Last Updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            if record_id:
                updates.append({"record_id": record_id, "fields": fields})
            else:
                client.upsert_record(app_token, table_id, fields)

        if updates:
            client.batch_update_records(app_token, table_id, updates)
            print(f"[WF1] Updated {len(updates)} records in AFS Base")
    else:
        print("[WF1] DRY RUN or no Base config — skipping Feishu write")

    # ── 4. Send Feishu Bot summary ──────────────────────────────────────
    summary = [
        f"Total videos tracked: **{len(videos)}**",
        f"✅ Posted: {len(posted)}  |  ⏳ Pending: {len(pending)}  |  ❌ Not Posted: {len(not_posted)}",
        f"Total GMV from posted videos: **{total_gmv:,.0f} THB**",
        f"Total views: **{total_views:,}**",
    ]
    highlights = [
        f"🔥 {v.get('video_id', 'N/A')} — {safe_float(v.get('gmv',0)):,.0f} THB, {safe_int(v.get('views',0)):,} views"
        for v in boost_candidates[:5]
    ]

    if not dry_run:
        client.send_workflow_summary(
            workflow_name="Video Status Tracker",
            status="warning" if not_posted else "success",
            summary_lines=summary,
            highlight_items=highlights if highlights else ["No boost candidates this cycle"],
        )

    result = {
        "total": len(videos),
        "posted": len(posted),
        "pending": len(pending),
        "not_posted": len(not_posted),
        "high_potential_count": len(high_potential),
        "boost_candidates": boost_candidates[:10],
        "total_gmv": total_gmv,
        "total_views": total_views,
    }
    print("[WF1] ✓ Complete")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WF1: Video Status Tracker")
    parser.add_argument("--dry-run", action="store_true", help="Skip Feishu writes")
    parser.add_argument("--data-dir", default="data/samples")
    args = parser.parse_args()
    run(dry_run=args.dry_run, data_dir=args.data_dir)
