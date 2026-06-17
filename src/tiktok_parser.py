"""
TikTok Seller Data Parser
Ingests data from:
  1. Manual CSV exports from TikTok Seller / Affiliate Center
  2. BI system JSON exports
  3. Direct Feishu Base read (AFS base as source)
"""

import os
import csv
import json
import glob
from typing import List, Dict, Optional, Any
from datetime import datetime


# ─────────────────────────────────────────────────────
# Column name normalization map
# Maps TikTok Seller export headers → internal keys
# ─────────────────────────────────────────────────────

CREATOR_COLUMN_MAP = {
    # Creator identity
    "creator_id": "creator_id",
    "unique_id": "creator_id",
    "tiktok_id": "creator_id",
    "creator name": "creator_name",
    "creator_name": "creator_name",
    "nickname": "creator_name",

    # Followers
    "followers": "followers",
    "follower_count": "followers",
    "fans count": "followers",

    # GMV
    "gmv": "gmv",
    "total gmv": "gmv",
    "estimated gmv": "gmv",
    "gmv (thb)": "gmv",

    # Video metrics
    "video_count": "video_count",
    "videos posted": "video_count",
    "total videos": "video_count",

    # Live stream
    "live_count": "live_count",
    "live sessions": "live_count",

    # Performance
    "conversion_rate": "conversion_rate",
    "cvr": "conversion_rate",
    "avg views": "avg_views",
    "average video views": "avg_views",

    # Status
    "status": "status",
    "cooperation status": "status",
    "collab_status": "status",

    # Tier
    "creator_tier": "tier",
    "tier": "tier",
    "creator tier": "tier",
}

VIDEO_COLUMN_MAP = {
    "video_id": "video_id",
    "video id": "video_id",
    "tiktok video id": "video_id",
    "creator_id": "creator_id",
    "creator id": "creator_id",
    "video title": "video_title",
    "title": "video_title",
    "posted_date": "posted_date",
    "post date": "posted_date",
    "post_time": "posted_date",
    "views": "views",
    "video views": "views",
    "play count": "views",
    "likes": "likes",
    "like count": "likes",
    "comments": "comments",
    "comment count": "comments",
    "shares": "shares",
    "share count": "shares",
    "gmv": "gmv",
    "video gmv": "gmv",
    "orders": "orders",
    "order count": "orders",
    "status": "status",
    "video_status": "status",
    "posting_status": "status",
    "is_boosted": "is_boosted",
    "boosted": "is_boosted",
    "campaign_id": "campaign_id",
    "campaign id": "campaign_id",
    "ls_campaign": "campaign_id",
}


def _normalize_row(row: Dict[str, Any], column_map: Dict[str, str]) -> Dict[str, Any]:
    """Apply column normalization to a CSV row."""
    normalized = {}
    for raw_key, value in row.items():
        clean_key = raw_key.strip().lower()
        mapped = column_map.get(clean_key)
        if mapped:
            normalized[mapped] = value
    return normalized


def load_csv(filepath: str, column_map: Dict[str, str]) -> List[Dict]:
    """Load and normalize a TikTok CSV export."""
    rows = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            normalized = _normalize_row(dict(row), column_map)
            if normalized:
                rows.append(normalized)
    print(f"[Parser] Loaded {len(rows)} rows from {os.path.basename(filepath)}")
    return rows


def load_bi_json(filepath: str) -> List[Dict]:
    """Load BI system JSON export (array of records)."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    # Some BI exports wrap in {"data": [...]}
    return data.get("data", data.get("rows", []))


def load_latest_creator_csv(data_dir: str = "data/samples") -> List[Dict]:
    """Auto-find the most recent creator CSV in the data directory."""
    pattern = os.path.join(data_dir, "*creator*")
    files = sorted(glob.glob(pattern, recursive=False))
    if not files:
        raise FileNotFoundError(f"No creator CSV found in {data_dir}")
    latest = files[-1]
    return load_csv(latest, CREATOR_COLUMN_MAP)


def load_latest_video_csv(data_dir: str = "data/samples") -> List[Dict]:
    """Auto-find the most recent video CSV in the data directory."""
    pattern = os.path.join(data_dir, "*video*")
    files = sorted(glob.glob(pattern, recursive=False))
    if not files:
        raise FileNotFoundError(f"No video CSV found in {data_dir}")
    latest = files[-1]
    return load_csv(latest, VIDEO_COLUMN_MAP)


def safe_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def safe_int(value: Any) -> Optional[int]:
    f = safe_float(value)
    return int(f) if f is not None else None


def classify_video_potential(row: Dict) -> str:
    """
    Classify a video as High / Medium / Low growth potential
    based on engagement and GMV signals.
    """
    views = safe_int(row.get("views", 0)) or 0
    gmv = safe_float(row.get("gmv", 0)) or 0
    orders = safe_int(row.get("orders", 0)) or 0

    score = 0
    if views > 50000:
        score += 2
    elif views > 10000:
        score += 1

    if gmv > 5000:
        score += 3
    elif gmv > 1000:
        score += 2
    elif gmv > 100:
        score += 1

    if orders > 50:
        score += 2
    elif orders > 10:
        score += 1

    if score >= 5:
        return "🔥 High"
    elif score >= 2:
        return "⚡ Medium"
    return "⬇ Low"


def classify_creator_tier(followers: int, gmv: float) -> str:
    """Segment creators into standard affiliate tiers."""
    if followers >= 1_000_000 or gmv >= 100_000:
        return "Mega"
    elif followers >= 100_000 or gmv >= 10_000:
        return "Macro"
    elif followers >= 10_000 or gmv >= 1_000:
        return "Mid"
    elif followers >= 1_000:
        return "Micro"
    return "Nano"


def get_sample_creators() -> List[Dict]:
    """Return sample creator data for testing when no CSV is available."""
    return [
        {"creator_id": "C001", "creator_name": "Creator A", "followers": 125000, "gmv": 12500.0, "video_count": 8, "status": "Active", "tier": "Macro"},
        {"creator_id": "C002", "creator_name": "Creator B", "followers": 45000,  "gmv": 3200.0,  "video_count": 5, "status": "Active", "tier": "Mid"},
        {"creator_id": "C003", "creator_name": "Creator C", "followers": 8500,   "gmv": 450.0,   "video_count": 2, "status": "Pending", "tier": "Micro"},
        {"creator_id": "C004", "creator_name": "Creator D", "followers": 310000, "gmv": 28000.0, "video_count": 12, "status": "Active", "tier": "Macro"},
        {"creator_id": "C005", "creator_name": "Creator E", "followers": 2100000,"gmv": 185000.0,"video_count": 20, "status": "Active", "tier": "Mega"},
    ]


def get_sample_videos() -> List[Dict]:
    """Return sample video data for testing when no CSV is available."""
    return [
        {"video_id": "V001", "creator_id": "C001", "views": 85000,  "gmv": 2100.0, "orders": 42,  "status": "Posted",   "campaign_id": "CAMP_JUN"},
        {"video_id": "V002", "creator_id": "C001", "views": 12000,  "gmv": 320.0,  "orders": 8,   "status": "Posted",   "campaign_id": "CAMP_JUN"},
        {"video_id": "V003", "creator_id": "C002", "views": 5000,   "gmv": 80.0,   "orders": 2,   "status": "Pending",  "campaign_id": "CAMP_JUN"},
        {"video_id": "V004", "creator_id": "C004", "views": 230000, "gmv": 18000.0,"orders": 360, "status": "Posted",   "campaign_id": "CAMP_JUN"},
        {"video_id": "V005", "creator_id": "C005", "views": 1500000,"gmv": 92000.0,"orders": 1840,"status": "Posted",   "campaign_id": "CAMP_MAY"},
        {"video_id": "V006", "creator_id": "C003", "views": 900,    "gmv": 0.0,    "orders": 0,   "status": "Not Posted","campaign_id": "CAMP_JUN"},
    ]
