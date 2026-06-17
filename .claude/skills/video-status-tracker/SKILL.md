---
name: video-status-tracker
description: >
  Run the Migo Thailand Affiliate Video Status Tracker workflow. Use this
  skill whenever the user wants to check creator posting status, update
  Creator's Pool with video performance data from a TikTok Seller export,
  compute Growth Potential / Boost Recommended, or produce the AFS
  conversion-rate report for a given timeframe and brand. Trigger on phrases
  like "run WF1", "video status tracker", "check who posted", "update
  Creator's Pool", "AFS conversion rate", "boost candidates", "which
  creators haven't posted", or whenever a TikTok Seller export file (.xlsx
  or .csv) is attached alongside a date range or "this period" mention.
---

# Video Status Tracker

This skill automates the end-to-end workflow for tracking whether contracted
creators have posted videos, scoring their performance, and writing the
results back to Feishu Base ("Creator's Pool" table).

**Bundled resources:**
- `scripts/match_and_score.py` — TikTok export parser, creator matching,
  Growth Potential classifier, AFS conversion-rate calculator. Run inline
  via a `python3 -` heredoc or as `python3 scripts/match_and_score.py`.
  Read it before writing any Python snippet — it already has the logic you
  need; don't reinvent it.
- `references/lark-cli-patterns.md` — exact lark-cli command shapes,
  known gotchas (datetime format, batch_update path restriction, pagination).
  Read this before touching any Feishu write operation.

---

## Step 0 — Collect inputs

Before doing anything, confirm these three things with the user if they
haven't already provided them:

1. **TikTok export file** — path to the `.xlsx` or `.csv` downloaded from
   TikTok Seller Center → Affiliate → Video Performance. If they dragged a
   file into the message, the path is already there.
2. **Timeframe** — start and end dates (inclusive). The file's name often
   encodes the range (e.g. `Video_List_20260601-20260615_...xlsx`), but
   **verify against actual `Video post date` values in the file** — dates
   in the filename vs. the data can be off by a year (Buddhist calendar
   vs. Gregorian). If you find a mismatch, flag it to the user and confirm
   which dates to use before proceeding.
3. **Brand filter** (optional) — e.g. "Bostanten Women's Bag". If the user
   specifies one, use it as a `intersects` filter on the `Brand`
   (multi-select) field when fetching Creator's Pool rows. If omitted,
   fetch all brands.

Also ask for (or extract from a pasted URL):

4. **Feishu Base app_token** — the `<APP_TOKEN>` segment from the Base URL
   (`https://xxx.feishu.cn/base/<APP_TOKEN>?...`). Don't try to search Drive
   by name; it requires an extra OAuth scope most users won't have. Always
   ask the user to paste the URL.

---

## Step 1 — Detect TikTok export columns

Read `scripts/match_and_score.py` and use its `detect_columns()` function to
auto-map canonical metric names to actual column names in this export.

Run a quick inline Python snippet to print the detected mapping:

```python
import sys, json
sys.path.insert(0, ".claude/skills/video-status-tracker/scripts")
from match_and_score import detect_columns
import openpyxl
ws = openpyxl.load_workbook("<path>", data_only=True).active
header = next(ws.iter_rows(values_only=True))
mapping, missing = detect_columns(header)
print(json.dumps({"mapping": mapping, "missing": missing}, indent=2, ensure_ascii=False))
```

If any of these canonical fields are **missing** from the export, **ask the
user** how to handle each one before continuing — don't silently default:

- `views` — commonly mapped to "Shoppable video impressions" (TikTok's proxy
  for video reach). Ask to confirm if the label differs.
- `shares` — TikTok Seller exports frequently omit this. If missing, set to
  0 and tell the user.
- `gmv` — watch for two GMV columns ("GMV" vs "Affiliate shoppable video
  GMV"). They use different attribution windows and give different numbers.
  Ask which one the user wants; the choice affects Growth Potential math.
- `creator` / `creator_id` — must match Feishu's "Creators ID" field (the
  TikTok username). If the export uses a different column name/format, check
  with the user before guessing.

---

## Step 2 — Check lark-cli auth

```bash
lark-cli auth status
```

If `base:table:read`, `base:field:create`, `base:record:read`,
`base:record:create` are missing, start the device-flow login (see
`references/lark-cli-patterns.md` §0). Show the user the QR code + URL,
end the turn, and wait for them to confirm before continuing.

---

## Step 3 — Resolve table_id, ensure fields exist

```bash
lark-cli base +table-list --base-token "<APP_TOKEN>" --format pretty
```

Find `"Creator's Pool"` and record its `id` (e.g. `tblXXXXXXXX`).

Then list existing fields:

```bash
lark-cli base +field-list --base-token "<APP_TOKEN>" --table-id "<TABLE_ID>"
```

Create any of the 14 required fields that are missing (see
`references/lark-cli-patterns.md` §3 for the `+field-create` syntax and
type map). Check by name — skip creation if the field already exists to
keep this step idempotent. Tell the user which fields were created and note
that new fields append at the end of the table (Bitable has no API for
inserting at a specific position).

---

## Step 4 — Fetch and filter Creator's Pool rows

Paginate through all records, applying the Brand filter if specified:

```bash
lark-cli base +record-list --base-token "<APP_TOKEN>" --table-id "<TABLE_ID>" \
  --filter-json '{"logic":"and","conditions":[["Brand","intersects",["<BRAND>"]]]}' \
  --offset 0 --limit 200 --format json
```

Loop on `--offset` until `data.has_more` is `false`. See
`references/lark-cli-patterns.md` §4 for pagination details.

Then filter client-side (Python) to rows where `"Date of contact"` falls
within the timeframe. Extract per row:
- `record_id` (from `record_id_list`)
- `Creators ID` (the TikTok username — this is the match key)
- `AFS` (multi-select staff field — take the **first** value as the owner;
  if multiple, note this in the summary but don't double-count)
- `Date of contact`

If a row has no `Creators ID` value, treat it as "Not Posted" and include
it in the not-posted list with a note "(no Creator ID)".

---

## Step 5 — Load TikTok export, match, classify

Use `match_and_score.py`'s `load_tiktok_export()` and `match_pool_to_videos()`:

```python
import sys
sys.path.insert(0, ".claude/skills/video-status-tracker/scripts")
from match_and_score import load_tiktok_export, detect_columns, match_pool_to_videos, compute_afs_conversion_rates
from datetime import datetime
import openpyxl, json

# detect columns
ws = openpyxl.load_workbook("<path>", data_only=True).active
header = next(ws.iter_rows(values_only=True))
mapping, _ = detect_columns(header)

start = datetime(<YYYY>, <M>, <D>)
end   = datetime(<YYYY>, <M>, <D>, 23, 59, 59)

videos = load_tiktok_export("<path>", mapping)
matched, not_posted = match_pool_to_videos(pool_rows, videos, start, end)
afs_rates, afs_stats = compute_afs_conversion_rates(pool_rows, matched)
```

`pool_rows` is the list you built in Step 4 (each dict needs `record_id`,
`creator_id_raw`, `afs_owner`, `date_of_contact`).

For creators with multiple videos in the window, `match_pool_to_videos`
automatically picks the highest-GMV one — don't override this manually.

---

## Step 6 — Build batch update payload and write to Feishu

Construct a JSON body with one entry per Creator's Pool row in the timeframe:

**Matched (Posted):**
```python
{
  "record_id": m["record_id"],
  "fields": {
    "Video Status": "Posted",
    "Video ID":     m["video"]["video_id"],
    "Video Title":  m["video"]["title"],
    "Post Date":    int(m["video"]["post_date"].timestamp() * 1000),  # epoch ms!
    "Views":        m["video"]["views"] or 0,
    "Likes":        m["video"]["likes"] or 0,
    "Comments":     m["video"]["comments"] or 0,
    "Shares":       m["video"]["shares"] or 0,
    "Orders":       m["video"]["orders"] or 0,
    "GMV (THB)":    m["video"]["gmv"] or 0.0,
    "Growth Potential":    m["potential"],
    "Boost Recommended":   m["boost"],        # true/false checkbox
    "AFS Conversion Rate": afs_rates[m["afs_owner"]],
    "Last Updated":        int(datetime.now().timestamp() * 1000),
  }
}
```

**Not Posted:**
```python
{
  "record_id": p["record_id"],
  "fields": {
    "Video Status":        "Not Posted",
    "AFS Conversion Rate": afs_rates.get(p["afs_owner"], ""),
    "Last Updated":        int(datetime.now().timestamp() * 1000),
  }
}
```

Write the payload to `./batch_update.json` (relative path — required by
lark-cli sandbox, see `references/lark-cli-patterns.md` §6), then call:

```bash
cd /Users/tanachpacharapha/Desktop/Migo/affiliate-workflows  # or the actual project root
lark-cli api POST "/open-apis/bitable/v1/apps/<APP_TOKEN>/tables/<TABLE_ID>/records/batch_update" \
  --data @./batch_update.json
```

Verify `response["code"] == 0` and that the returned record count matches
what you sent. Then clean up: `rm -f ./batch_update.json`.

If there are more than 200 rows, split into chunks of 200 and call the
endpoint once per chunk.

---

## Step 7 — Print summary

Print this exact format (no substitutions — use the real computed values):

```
📅 TIMEFRAME: YYYY-MM-DD → YYYY-MM-DD

📋 POSTING COMPLETENESS
   ✅ Posted:       X (X%)
   ❌ Not Posted:   X (X%)

   Not Posted:
   - <creator_id> | <afs_owner>
   ...

📊 VIDEO PERFORMANCE
   🔥 High potential:   X
   ⚡ Medium potential: X
   ⬇  Low potential:   X
   Total GMV: ฿X,XXX

🚀 TOP 5 BOOST CANDIDATES
   (none — no 🔥 High videos this period)
   — or —
   1. <creator_id> | <video_title_truncated_50_chars> | <views> views | ฿<gmv>
   ...

🎯 AFS CONVERSION RATE
   <AFS Name>         | Contacted: X | Posted: X | X/X (XX%)
   ...

✅ Total records updated in Creator's Pool: X
```

For the Boost Candidates section: rank by GMV descending, break ties by
views. If no rows hit 🔥 High, say so explicitly rather than listing ⬇ Low
rows as "candidates" — that's misleading for the team's Boost Ads decisions.

---

## Growth Potential thresholds (reference)

| Label | Condition |
|---|---|
| 🔥 High | views > 50,000 **OR** GMV > 5,000 **OR** orders > 50 |
| ⚡ Medium | views > 10,000 **OR** GMV > 1,000 **OR** orders > 10 |
| ⬇ Low | everything else |

`Boost Recommended` = `true` only when Growth Potential is 🔥 High.
All thresholds are in `scripts/match_and_score.py` (`classify_growth_potential`).
Update that function if the team changes the thresholds — don't hardcode
them in the skill instructions and in the script separately.

---

## Known limitations / notes for the user

- **New columns append at end.** Bitable's API has no field-positioning
  option. If the user asked for columns placed immediately after "Date of
  Contact", tell them it's not possible via API and they'd need to drag them
  manually in the Feishu UI.
- **Shares not available in TikTok Seller exports** (as of mid-2026). The
  column is created and set to 0. If a future export adds it, `detect_columns`
  will pick it up automatically via the "shares" alias.
- **Multiple videos per creator.** Only the highest-GMV video per creator
  per timeframe is written back — the "best performance" for that period.
  Other videos aren't lost; they just don't drive the status row. If the
  user wants all videos tracked separately, that needs a different table
  schema (one row per video, not one row per creator).
- **Multi-AFS rows.** When a Creator's Pool row lists more than one AFS
  owner, the first value is treated as primary for conversion-rate grouping.
  The creator counts toward that one owner's Contacted/Posted totals, not
  all owners'.
- **Legacy script.** `src/workflows/01_video_status_tracker.py` is a simpler
  older version that uses `config.yaml` credentials and writes to a generic
  "video status" table — not Creator's Pool. Don't delete it; it may be used
  by other team members or `run_workflow.py --workflow 1`.
