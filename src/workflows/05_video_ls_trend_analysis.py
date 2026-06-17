"""
Workflow 5: Video and LS Output Trend Over Time
─────────────────────────────────────────────────
Objective:
  - Visualize weekly/monthly trend of video post volume vs. LS session volume
  - Identify which channel (video or LS) needs more focus
  - Detect momentum drops before they impact GMV
  - Output: trend chart image + AFS Base trend table + Feishu Bot insight

Inputs:  AFS Base (historical video + LS records)
Outputs: Trend analysis PNG / HTML chart  +  AFS Base trend table  +  Bot alert
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feishu_client import FeishuClient
from tiktok_parser import safe_int, safe_float
from config_loader import load_config
from datetime import datetime, timedelta
from collections import defaultdict


SAMPLE_TREND_DATA = [
    {"week": "2026-W18", "video_posts": 28, "ls_sessions": 14, "total_gmv": 85000},
    {"week": "2026-W19", "video_posts": 32, "ls_sessions": 16, "total_gmv": 102000},
    {"week": "2026-W20", "video_posts": 25, "ls_sessions": 18, "total_gmv": 95000},
    {"week": "2026-W21", "video_posts": 18, "ls_sessions": 12, "total_gmv": 74000},
    {"week": "2026-W22", "video_posts": 22, "ls_sessions": 15, "total_gmv": 88000},
    {"week": "2026-W23", "video_posts": 30, "ls_sessions": 20, "total_gmv": 115000},
]


def _detect_trend(values: list) -> str:
    """Simple linear trend detection: up / down / flat."""
    if len(values) < 2:
        return "flat"
    first_half = sum(values[: len(values) // 2]) / (len(values) // 2)
    second_half = sum(values[len(values) // 2 :]) / (len(values) - len(values) // 2)
    pct_change = (second_half - first_half) / first_half * 100 if first_half else 0
    if pct_change > 5:
        return f"📈 up {pct_change:.0f}%"
    elif pct_change < -5:
        return f"📉 down {abs(pct_change):.0f}%"
    return "➡ flat"


def _generate_trend_chart(trend_data: list, output_path: str) -> bool:
    """Generate HTML trend chart (no matplotlib dependency)."""
    try:
        weeks = [d["week"] for d in trend_data]
        videos = [d["video_posts"] for d in trend_data]
        ls_vals = [d["ls_sessions"] for d in trend_data]
        gmv_vals = [int(d["total_gmv"]) for d in trend_data]

        max_count = max(max(videos), max(ls_vals), 1)
        max_gmv = max(gmv_vals, default=1)

        def bar_width(v, max_v): return int(v / max_v * 300)

        rows = ""
        for i, w in enumerate(weeks):
            rows += f"""
            <tr>
              <td style="padding:4px 8px;font-size:12px;color:#888">{w}</td>
              <td><div style="background:#4F81FF;height:16px;width:{bar_width(videos[i],max_count)}px;border-radius:3px"></div>
                  <span style="font-size:11px;color:#4F81FF;margin-left:4px">{videos[i]}</span></td>
              <td><div style="background:#FF6B6B;height:16px;width:{bar_width(ls_vals[i],max_count)}px;border-radius:3px"></div>
                  <span style="font-size:11px;color:#FF6B6B;margin-left:4px">{ls_vals[i]}</span></td>
              <td style="font-size:12px;color:#2E7D32;padding-left:8px">฿{gmv_vals[i]:,}</td>
            </tr>"""

        html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<title>Video & LS Trend</title>
<style>
  body{{font-family:sans-serif;padding:24px;background:#F9FAFB}}
  h2{{color:#333;margin-bottom:4px}}
  p{{color:#666;font-size:13px}}
  table{{border-collapse:collapse;width:100%;margin-top:16px}}
  th{{text-align:left;padding:8px;background:#F0F4FF;font-size:12px;color:#444}}
  tr:hover{{background:#F7F7F7}}
  .legend{{display:flex;gap:20px;margin:12px 0;font-size:13px}}
  .dot{{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:4px}}
</style></head><body>
<h2>📊 Video & LS Output Trend</h2>
<p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")} | Source: AFS Base</p>
<div class="legend">
  <span><span class="dot" style="background:#4F81FF"></span>Video Posts</span>
  <span><span class="dot" style="background:#FF6B6B"></span>LS Sessions</span>
  <span><span class="dot" style="background:#2E7D32"></span>GMV (THB)</span>
</div>
<table>
  <tr><th>Week</th><th>Video Posts</th><th>LS Sessions</th><th>Total GMV</th></tr>
  {rows}
</table>
</body></html>"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[WF5] Chart saved: {output_path}")
        return True
    except Exception as e:
        print(f"[WF5] Chart generation failed: {e}")
        return False


def run(dry_run: bool = False, data_dir: str = "data/samples", output_dir: str = "reports"):
    cfg = load_config()
    client = FeishuClient()

    print("\n[WF5] ▶ Video & LS Trend Analysis — starting")

    # ── 1. Load historical trend data from AFS Base ──────────────────────
    app_token = cfg.get("afs_base_token")
    trend_table_id = cfg.get("trend_table_id")

    if app_token and trend_table_id:
        records = client.get_records(app_token, trend_table_id)
        trend_data = sorted(
            [r.get("fields", {}) for r in records],
            key=lambda x: x.get("week", ""),
        )
        print(f"[WF5] Loaded {len(trend_data)} trend records from AFS Base")
    else:
        trend_data = SAMPLE_TREND_DATA
        print("[WF5] Using sample trend data")

    if len(trend_data) < 2:
        print("[WF5] Not enough data for trend analysis — need at least 2 periods")
        return {}

    # ── 2. Compute trend signals ─────────────────────────────────────────
    video_trend = _detect_trend([safe_int(d.get("video_posts", 0)) or 0 for d in trend_data])
    ls_trend = _detect_trend([safe_int(d.get("ls_sessions", 0)) or 0 for d in trend_data])
    gmv_trend = _detect_trend([safe_float(d.get("total_gmv", 0)) or 0 for d in trend_data])

    latest = trend_data[-1]
    prev = trend_data[-2]

    video_wow = (
        ((safe_int(latest.get("video_posts", 0)) or 0) - (safe_int(prev.get("video_posts", 0)) or 0))
        / max(safe_int(prev.get("video_posts", 1)) or 1, 1) * 100
    )
    ls_wow = (
        ((safe_int(latest.get("ls_sessions", 0)) or 0) - (safe_int(prev.get("ls_sessions", 0)) or 0))
        / max(safe_int(prev.get("ls_sessions", 1)) or 1, 1) * 100
    )

    # Determine focus area recommendation
    focus_recommendation = []
    if "down" in video_trend:
        focus_recommendation.append("⚠️ Video output declining — increase posting cadence")
    if "down" in ls_trend:
        focus_recommendation.append("⚠️ LS sessions declining — schedule more live streams")
    if not focus_recommendation:
        focus_recommendation.append("✅ Both channels on positive trajectory")

    print(f"[WF5] Video trend: {video_trend} | LS trend: {ls_trend} | GMV trend: {gmv_trend}")

    # ── 3. Generate HTML chart ────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)
    chart_path = os.path.join(output_dir, f"trend_{datetime.now().strftime('%Y%m%d')}.html")
    _generate_trend_chart(trend_data, chart_path)

    # ── 4. Write insight record to AFS Base ──────────────────────────────
    if app_token and trend_table_id and not dry_run:
        insight_table_id = cfg.get("insight_table_id", trend_table_id)
        client.upsert_record(
            app_token,
            insight_table_id,
            {
                "Report Date": datetime.now().strftime("%Y-%m-%d"),
                "Video Trend": video_trend,
                "LS Trend": ls_trend,
                "GMV Trend": gmv_trend,
                "WoW Video Change (%)": round(video_wow, 1),
                "WoW LS Change (%)": round(ls_wow, 1),
                "Focus Recommendation": " | ".join(focus_recommendation),
            },
        )

    # ── 5. Feishu Bot insight alert ───────────────────────────────────────
    summary_lines = [
        f"Video output trend: **{video_trend}** (WoW: {video_wow:+.0f}%)",
        f"LS sessions trend: **{ls_trend}** (WoW: {ls_wow:+.0f}%)",
        f"GMV trend: **{gmv_trend}**",
        f"Latest week: {latest.get('week','?')} — {safe_int(latest.get('video_posts',0))} videos, {safe_int(latest.get('ls_sessions',0))} LS, ฿{safe_float(latest.get('total_gmv',0)):,.0f}",
    ]

    if not dry_run:
        status = "warning" if any("down" in t for t in [video_trend, ls_trend]) else "success"
        client.send_workflow_summary(
            workflow_name="Video & LS Trend Analysis",
            status=status,
            summary_lines=summary_lines,
            highlight_items=focus_recommendation,
        )

    print("[WF5] ✓ Complete")
    return {
        "video_trend": video_trend,
        "ls_trend": ls_trend,
        "gmv_trend": gmv_trend,
        "chart_path": chart_path,
        "focus_recommendations": focus_recommendation,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WF5: Video & LS Trend Analysis")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data-dir", default="data/samples")
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()
    run(dry_run=args.dry_run, data_dir=args.data_dir, output_dir=args.output_dir)
