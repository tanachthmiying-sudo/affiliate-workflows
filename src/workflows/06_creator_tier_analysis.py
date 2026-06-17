"""
Workflow 6: Creator GMV Contribution by Tiers & Tier Distribution
───────────────────────────────────────────────────────────────────
Objective:
  - Analyse what % of total GMV comes from each creator tier (Mega/Macro/Mid/Micro/Nano)
  - Show tier distribution (how many creators per tier)
  - Identify over-reliance on single tier (concentration risk)
  - Recommend tier mix strategy

Inputs:  AFS Base (creator pool with GMV data)
Outputs: HTML analysis report  +  AFS Base insight record  +  Feishu Bot card
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feishu_client import FeishuClient
from tiktok_parser import get_sample_creators, safe_float, safe_int, classify_creator_tier
from config_loader import load_config
from datetime import datetime


TIER_ORDER = ["Mega", "Macro", "Mid", "Micro", "Nano"]

# Target healthy mix (benchmark)
HEALTHY_MIX = {"Mega": 30, "Macro": 35, "Mid": 20, "Micro": 10, "Nano": 5}


def run(dry_run: bool = False, data_dir: str = "data/samples", output_dir: str = "reports"):
    cfg = load_config()
    client = FeishuClient()

    print("\n[WF6] ▶ Creator Tier Analysis — starting")

    # ── 1. Load creator pool from AFS Base ──────────────────────────────
    app_token = cfg.get("afs_base_token")
    pool_table_id = cfg.get("creator_pool_table_id")

    if app_token and pool_table_id:
        records = client.get_records(app_token, pool_table_id)
        creators = [r.get("fields", {}) for r in records]
        print(f"[WF6] Loaded {len(creators)} creators from AFS Base")
    else:
        creators = get_sample_creators()
        print("[WF6] Using sample creator data")

    # ── 2. Compute tier GMV + distribution ──────────────────────────────
    tier_gmv: dict = {t: 0.0 for t in TIER_ORDER}
    tier_count: dict = {t: 0 for t in TIER_ORDER}

    for c in creators:
        gmv = safe_float(c.get("GMV (THB)", c.get("gmv", 0))) or 0.0
        followers = safe_int(c.get("Followers", c.get("followers", 0))) or 0

        # Use stored tier or recompute
        tier = c.get("Creator Tier", c.get("tier", c.get("computed_tier")))
        if not tier:
            tier = classify_creator_tier(followers, gmv)

        if tier not in tier_gmv:
            tier = "Nano"

        tier_gmv[tier] += gmv
        tier_count[tier] += 1

    total_gmv = sum(tier_gmv.values())
    total_creators = sum(tier_count.values())

    # GMV % contribution by tier
    tier_gmv_pct = {
        t: (tier_gmv[t] / total_gmv * 100 if total_gmv > 0 else 0)
        for t in TIER_ORDER
    }

    # Distribution %
    tier_dist_pct = {
        t: (tier_count[t] / total_creators * 100 if total_creators > 0 else 0)
        for t in TIER_ORDER
    }

    print(f"\n[WF6] GMV Contribution:")
    for t in TIER_ORDER:
        print(f"  {t:8s}: {tier_count[t]:3d} creators | GMV ฿{tier_gmv[t]:>12,.0f} ({tier_gmv_pct[t]:.1f}%)")

    # ── 3. Detect concentration risk ────────────────────────────────────
    risks = []
    recommendations = []
    dominant_tier = max(tier_gmv_pct, key=tier_gmv_pct.get)

    if tier_gmv_pct[dominant_tier] > 60:
        risks.append(f"⚠️ Over-reliance on {dominant_tier} tier ({tier_gmv_pct[dominant_tier]:.0f}% of GMV)")
        recommendations.append(f"Diversify: grow {[t for t in TIER_ORDER if t != dominant_tier][0]} and Mid tiers")

    for tier in TIER_ORDER:
        diff = tier_gmv_pct[tier] - HEALTHY_MIX.get(tier, 0)
        if diff < -10:
            recommendations.append(f"Grow {tier} tier — currently {tier_gmv_pct[tier]:.0f}% vs target {HEALTHY_MIX[tier]}%")

    if not risks:
        risks.append("✅ Healthy tier distribution — no concentration risk detected")

    # ── 4. Generate HTML report ──────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, f"tier_analysis_{datetime.now().strftime('%Y%m%d')}.html")

    bars_gmv = ""
    bars_count = ""
    max_pct = max(tier_gmv_pct.values(), default=1)
    COLORS = {"Mega": "#6C3483", "Macro": "#1A5276", "Mid": "#1E8449", "Micro": "#D68910", "Nano": "#CB4335"}

    for t in TIER_ORDER:
        c = COLORS.get(t, "#999")
        w_gmv = int(tier_gmv_pct[t] / max(max_pct, 1) * 280)
        w_cnt = int(tier_dist_pct[t] / 100 * 280)
        bars_gmv += f'<tr><td style="padding:5px 8px;font-weight:600;color:{c}">{t}</td><td><div style="background:{c};height:20px;width:{w_gmv}px;border-radius:3px;min-width:4px"></div></td><td style="padding-left:8px;font-size:13px">฿{tier_gmv[t]:,.0f} <span style="color:#999">({tier_gmv_pct[t]:.1f}%)</span></td></tr>'
        bars_count += f'<tr><td style="padding:5px 8px;font-weight:600;color:{c}">{t}</td><td><div style="background:{c};height:20px;width:{w_cnt}px;border-radius:3px;min-width:4px"></div></td><td style="padding-left:8px;font-size:13px">{tier_count[t]} creators <span style="color:#999">({tier_dist_pct[t]:.1f}%)</span></td></tr>'

    rec_html = "".join(f'<li style="margin:4px 0">{r}</li>' for r in recommendations or ["Strategy looks balanced."])
    risk_html = "".join(f'<li style="margin:4px 0">{r}</li>' for r in risks)

    report_html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8"><title>Creator Tier Analysis</title>
<style>
  body{{font-family:sans-serif;padding:24px;background:#F9FAFB;color:#222}}
  h2{{color:#333}} h3{{color:#555;border-bottom:1px solid #EEE;padding-bottom:4px}}
  table{{border-collapse:collapse;width:100%;margin-bottom:24px}}
  .box{{background:#FFF;border-radius:8px;padding:16px;margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
  ul{{margin:8px 0 0 16px;color:#444;font-size:13px}}
</style></head><body>
<h2>🏆 Creator Tier Analysis Report</h2>
<p style="color:#888;font-size:13px">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")} | Total Creators: {total_creators} | Total GMV: ฿{total_gmv:,.0f}</p>

<div class="box">
  <h3>GMV Contribution by Tier</h3>
  <table>{bars_gmv}</table>
</div>

<div class="box">
  <h3>Creator Count Distribution</h3>
  <table>{bars_count}</table>
</div>

<div class="box">
  <h3>⚠️ Concentration Risk</h3>
  <ul>{risk_html}</ul>
</div>

<div class="box">
  <h3>📋 Strategic Recommendations</h3>
  <ul>{rec_html}</ul>
</div>
</body></html>"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_html)
    print(f"[WF6] Report saved: {report_path}")

    # ── 5. Write insight to AFS Base ─────────────────────────────────────
    insight_table_id = cfg.get("insight_table_id")
    if app_token and insight_table_id and not dry_run:
        client.upsert_record(
            app_token,
            insight_table_id,
            {
                "Report Date": datetime.now().strftime("%Y-%m-%d"),
                "Dominant Tier": dominant_tier,
                "Dominant GMV %": round(tier_gmv_pct[dominant_tier], 1),
                "Mega GMV %": round(tier_gmv_pct["Mega"], 1),
                "Macro GMV %": round(tier_gmv_pct["Macro"], 1),
                "Mid GMV %": round(tier_gmv_pct["Mid"], 1),
                "Total GMV (THB)": round(total_gmv, 2),
                "Risk Flag": risks[0],
            },
        )

    # ── 6. Feishu Bot notification ────────────────────────────────────────
    summary_lines = [
        f"Total creators: **{total_creators}** | Total GMV: **฿{total_gmv:,.0f}**",
    ] + [
        f"{t}: {tier_count[t]} creators ({tier_dist_pct[t]:.0f}%) → ฿{tier_gmv[t]:,.0f} GMV ({tier_gmv_pct[t]:.0f}%)"
        for t in TIER_ORDER if tier_count[t] > 0
    ]

    if not dry_run:
        client.send_workflow_summary(
            workflow_name="Creator Tier Analysis",
            status="warning" if any("⚠️" in r for r in risks) else "success",
            summary_lines=summary_lines,
            highlight_items=risks + recommendations,
        )

    print("[WF6] ✓ Complete")
    return {
        "tier_gmv": tier_gmv,
        "tier_count": tier_count,
        "tier_gmv_pct": tier_gmv_pct,
        "total_gmv": total_gmv,
        "risks": risks,
        "recommendations": recommendations,
        "report_path": report_path,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WF6: Creator Tier Analysis")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data-dir", default="data/samples")
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()
    run(dry_run=args.dry_run, data_dir=args.data_dir, output_dir=args.output_dir)
