# Migo Affiliate Specialist — Claude Code Workflows

This project connects Claude Code to Feishu Base (Bitable) to automate
the 6 core workflows of the Affiliate Specialist role.

All workflows push results to **AFS Base** (Feishu Bitable) and send
summaries via **Feishu Bot webhook**.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials
cp config.yaml.template config.yaml
# Edit config.yaml with your Feishu App ID, App Secret, Base tokens

# 3. Test without writing to Feishu (dry run)
python run_workflow.py --workflow all --dry-run

# 4. Run a single workflow
python run_workflow.py --workflow 1
```

---

## Slash Commands

Use these in Claude Code CLI by typing `/run-workflow` or via the commands below.

### `/wf1` — Video Status Tracker
**Recheck creators' posted video status and track content performance**

```bash
python src/workflows/01_video_status_tracker.py [--dry-run] [--data-dir data/samples]
```
- Checks posting completeness for all contracted creators
- Identifies high-GMV videos for Boost Ads
- Updates AFS Base: video status table
- Bot: posts summary with boost candidates

### `/wf2` — LS GMV Campaign Summary
**LS Creators GMV summary for each campaign**

```bash
python src/workflows/02_ls_gmv_summary.py [--dry-run]
```
- Calculates GMV per creator per campaign
- Flags creators who missed LS obligations
- Updates AFS Base: campaign summary table
- Bot: highlights incomplete creators

### `/wf3` — Creator Pool Update
**Creators pool data update**

```bash
python src/workflows/03_creator_pool_update.py [--dry-run] [--data-dir data/samples]
```
- Syncs latest creator metrics from TikTok export/BI
- Auto-recalculates creator tiers (Mega/Macro/Mid/Micro/Nano)
- Updates AFS Base: creator pool table
- Bot: tier breakdown summary

### `/wf4` — Sample Approve Filter
**Filter sample approve list in seller backend**

```bash
python src/workflows/04_sample_approve_filter.py [--dry-run]
```
- Applies qualification criteria to raw TikTok creator leads
- Filters out existing pool members and blacklisted creators
- Writes qualified leads to AFS Base: leads table
- Bot: reports qualified lead count

### `/wf5` — Video & LS Trend Analysis
**Video and LS output trend over time**

```bash
python src/workflows/05_video_ls_trend_analysis.py [--dry-run] [--output-dir reports]
```
- Detects week-over-week trends in video and LS output
- Flags declining channels for focus
- Generates HTML trend chart in reports/
- Bot: channel health alert with recommendations

### `/wf6` — Creator Tier Analysis
**Creator GMV contribution by tiers & tier distribution**

```bash
python src/workflows/06_creator_tier_analysis.py [--dry-run] [--output-dir reports]
```
- Calculates GMV % by tier and creator count distribution
- Detects over-reliance / concentration risk
- Generates HTML report in reports/
- Bot: tier breakdown + strategic recommendations

---

## Run All Workflows

```bash
# Run all 6 workflows in sequence
python run_workflow.py --workflow all

# Run all in dry-run mode (no Feishu writes)
python run_workflow.py --workflow all --dry-run
```

---

## Data Sources

| Source | How to use |
|---|---|
| TikTok Seller CSV | Download from Affiliate Center → save to `data/samples/` |
| BI System JSON | Export from company BI → save to `data/samples/` |
| AFS Base (Feishu) | Set `afs_base_token` in config.yaml |

**CSV naming convention:**
- Creator data: `data/samples/*creator*.csv`
- Video data: `data/samples/*video*.csv`

---

## Feishu Base Tables Required

| Table | config.yaml key | Used in |
|---|---|---|
| Creator Pool | `creator_pool_table_id` | WF3, WF4, WF6 |
| Video Status | `video_table_id` | WF1 |
| LS Schedule | `ls_schedule_table_id` | WF2 |
| Campaign Summary | `campaign_summary_table_id` | WF2 |
| Leads (to contact) | `leads_table_id` | WF4 |
| Trend Data | `trend_table_id` | WF5 |
| Insights | `insight_table_id` | WF5, WF6 |

---

## Environment Variables (alternative to config.yaml)

```bash
export FEISHU_APP_ID="cli_xxxxxxxxxxxx"
export FEISHU_APP_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export FEISHU_BOT_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"
```

---

## Claude Code Hooks (auto-run on schedule)

See `.claude/settings.json` for hook configuration.

Example: auto-run WF1 + WF3 every morning at 9am.

---

## Qualification Criteria (WF4)

Adjust thresholds in `config.yaml`:

```yaml
lead_min_followers: 10000       # minimum follower count
lead_min_gmv_30d: 500           # minimum GMV last 30 days (THB)
lead_min_engagement_rate: 2.0   # minimum engagement rate %
```
