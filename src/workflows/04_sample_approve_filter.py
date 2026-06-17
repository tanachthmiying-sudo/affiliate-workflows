"""
Workflow 4: Filter Sample Approve List in Seller Backend
──────────────────────────────────────────────────────────
Objective:
  - Apply company qualification criteria to raw creator data from TikTok backend
  - Surface "possible leads" — creators worth reaching out to
  - Write qualified lead list to AFS Base

Inputs:  TikTok Seller > Creator Data Tools  +  Feishu Base (thresholds config)
Outputs: AFS Base "Leads to Contact" table  +  Feishu Bot with lead count

Qualification criteria (configurable via config.yaml):
  - Min followers threshold
  - Min GMV (last 30 days)
  - Min engagement rate
  - Not already in active creator pool
  - Status not "blacklisted"
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feishu_client import FeishuClient
from tiktok_parser import safe_int, safe_float, classify_creator_tier
from config_loader import load_config
from datetime import datetime


SAMPLE_RAW_CANDIDATES = [
    {"creator_id": "N001", "creator_name": "NewCreator A", "followers": 55000, "gmv_30d": 3200.0, "engagement_rate": 4.2, "blacklisted": False},
    {"creator_id": "N002", "creator_name": "NewCreator B", "followers": 8000,  "gmv_30d": 200.0,  "engagement_rate": 2.1, "blacklisted": False},
    {"creator_id": "N003", "creator_name": "NewCreator C", "followers": 120000,"gmv_30d": 15000.0,"engagement_rate": 5.8, "blacklisted": False},
    {"creator_id": "N004", "creator_name": "NewCreator D", "followers": 500,   "gmv_30d": 0.0,    "engagement_rate": 1.0, "blacklisted": False},
    {"creator_id": "N005", "creator_name": "NewCreator E", "followers": 30000, "gmv_30d": 1200.0, "engagement_rate": 6.5, "blacklisted": True},
    {"creator_id": "C001", "creator_name": "Creator A",   "followers": 125000, "gmv_30d": 12500.0,"engagement_rate": 3.1, "blacklisted": False},  # already in pool
]


def _passes_criteria(creator: dict, criteria: dict, existing_ids: set) -> tuple[bool, list]:
    """
    Return (passes: bool, fail_reasons: list).
    """
    reasons = []
    followers = safe_int(creator.get("followers", 0)) or 0
    gmv_30d = safe_float(creator.get("gmv_30d", 0)) or 0.0
    eng_rate = safe_float(creator.get("engagement_rate", 0)) or 0.0
    cid = creator.get("creator_id", "")

    if creator.get("blacklisted"):
        reasons.append("Blacklisted")
    if followers < criteria.get("min_followers", 10000):
        reasons.append(f"Followers {followers} < {criteria.get('min_followers',10000)}")
    if gmv_30d < criteria.get("min_gmv_30d", 500):
        reasons.append(f"GMV {gmv_30d} < {criteria.get('min_gmv_30d',500)}")
    if eng_rate < criteria.get("min_engagement_rate", 2.0):
        reasons.append(f"Eng. rate {eng_rate} < {criteria.get('min_engagement_rate',2.0)}")
    if cid in existing_ids:
        reasons.append("Already in active pool")

    return (len(reasons) == 0, reasons)


def run(dry_run: bool = False, data_dir: str = "data/samples"):
    cfg = load_config()
    client = FeishuClient()

    print("\n[WF4] ▶ Sample Approve Filter — starting")

    # ── Qualification criteria (from config or defaults) ─────────────────
    criteria = {
        "min_followers": cfg.get("lead_min_followers", 10000),
        "min_gmv_30d": cfg.get("lead_min_gmv_30d", 500),
        "min_engagement_rate": cfg.get("lead_min_engagement_rate", 2.0),
    }
    print(f"[WF4] Criteria: {criteria}")

    # ── 1. Load existing creator IDs (to avoid duplicates) ───────────────
    app_token = cfg.get("afs_base_token")
    pool_table_id = cfg.get("creator_pool_table_id")
    existing_ids = set()

    if app_token and pool_table_id:
        records = client.get_records(app_token, pool_table_id, field_names=["Creator ID"])
        for r in records:
            cid = r.get("fields", {}).get("Creator ID")
            if cid:
                existing_ids.add(cid)
        print(f"[WF4] {len(existing_ids)} existing creators loaded from pool")

    # ── 2. Load candidate list ────────────────────────────────────────────
    # In production: load from TikTok Seller > Creator Data Tools export
    candidates = SAMPLE_RAW_CANDIDATES
    print(f"[WF4] Evaluating {len(candidates)} candidates")

    # ── 3. Filter ────────────────────────────────────────────────────────
    qualified = []
    rejected = []

    for c in candidates:
        passes, reasons = _passes_criteria(c, criteria, existing_ids)
        if passes:
            c["tier"] = classify_creator_tier(
                safe_int(c.get("followers", 0)) or 0,
                safe_float(c.get("gmv_30d", 0)) or 0.0,
            )
            qualified.append(c)
        else:
            rejected.append({"creator": c, "reasons": reasons})

    print(f"[WF4] Qualified: {len(qualified)} | Rejected: {len(rejected)}")

    # ── 4. Write qualified leads to AFS Base ─────────────────────────────
    leads_table_id = cfg.get("leads_table_id")
    synced = 0

    if app_token and leads_table_id and not dry_run:
        for c in qualified:
            fields = {
                "Creator ID": c.get("creator_id", ""),
                "Creator Name": c.get("creator_name", ""),
                "Followers": safe_int(c.get("followers")) or 0,
                "GMV 30D (THB)": safe_float(c.get("gmv_30d")) or 0.0,
                "Engagement Rate (%)": safe_float(c.get("engagement_rate")) or 0.0,
                "Suggested Tier": c.get("tier", ""),
                "Lead Status": "New Lead",
                "Date Added": datetime.now().strftime("%Y-%m-%d"),
            }
            client.upsert_record(app_token, leads_table_id, fields)
            synced += 1

        print(f"[WF4] Wrote {synced} leads to AFS Base")

    # ── 5. Feishu Bot notification ────────────────────────────────────────
    summary_lines = [
        f"Candidates evaluated: **{len(candidates)}**",
        f"✅ Qualified leads: **{len(qualified)}**",
        f"❌ Rejected: {len(rejected)}",
        f"Top rejection reason: {rejected[0]['reasons'][0] if rejected else 'N/A'}",
    ]
    highlights = [
        f"{c.get('creator_name','?')} ({c.get('tier','?')}) — "
        f"{safe_int(c.get('followers',0)):,} followers, "
        f"{safe_float(c.get('gmv_30d',0)):,.0f} THB GMV"
        for c in qualified[:5]
    ]

    if not dry_run:
        client.send_workflow_summary(
            workflow_name="Sample Approve Filter",
            status="success" if qualified else "warning",
            summary_lines=summary_lines,
            highlight_items=highlights or ["No qualified leads found"],
        )

    print("[WF4] ✓ Complete")
    return {
        "total_candidates": len(candidates),
        "qualified": qualified,
        "rejected_count": len(rejected),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WF4: Sample Approve Filter")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data-dir", default="data/samples")
    args = parser.parse_args()
    run(dry_run=args.dry_run, data_dir=args.data_dir)
