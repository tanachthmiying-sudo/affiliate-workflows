"""
Workflow 7: LS Status Updater — Team B
────────────────────────────────────────────────────────────────
Objective:
  - Read TikTok Affiliate Creator List Excel export (period summary)
  - Pull all records from Feishu Base "AFS Central Team Testing"
    → table "Creators LS Schedule-Team B"
  - Match on: Creator username  +  export period overlaps Feishu schedule range
  - If creator has Affiliate LIVE GMV > 0 AND ≥1 Affiliate LIVE stream  →  Status = "Success"
  - Optionally write actual LIVE GMV back to the "LS GMV" column

Auth: uses lark-cli (device-flow OAuth) — no FEISHU_APP_ID/SECRET needed.
      Run `lark-cli auth login --domain base` once per device to set up.

Usage:
  # Auto-detect date from filename:
  python src/workflows/07_ls_status_updater.py -f Creator_List_20260610-20260616_*.xlsx

  # Dry run (shows matches, no Feishu writes):
  python src/workflows/07_ls_status_updater.py -f data.xlsx --dry-run

  # Inspect Excel columns and exit:
  python src/workflows/07_ls_status_updater.py -f data.xlsx --inspect

  # Via run_workflow.py:
  python run_workflow.py --workflow 7 --input-file data.xlsx --dry-run
"""

import sys
import os
import json
import re
import subprocess
import argparse
from datetime import datetime, date
from typing import Optional, Dict, List, Any, Tuple
from collections import defaultdict


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

BASE_TOKEN  = "PPGNbRBT9aLSvisUghcccQSinxg"   # AFS Central Team Testing
TABLE_NAME  = "Creators LS Schedule-Team B"

LS_CREATOR_ALIASES = [
    "creator username", "creator id", "creator_id",
    "anchor id", "anchor_id", "unique_id", "uniqueid",
    "tiktok id", "tiktok_id", "user id", "user_id",
    "handle", "username", "account id",
    "sellers id", "seller id", "affiliate id",
]
LS_GMV_ALIASES = [
    "affiliate live gmv", "affiliate live_gmv",
    "live gmv", "live_gmv", "ls gmv", "ls_gmv",
    "gmv", "total gmv", "estimated gmv", "gmv (thb)",
]
LS_STREAMS_ALIASES = [
    "affiliate live streams", "affiliate live_streams",
    "live streams", "live_streams",
    "ls sessions", "live sessions", "stream count", "live count",
]


# ─────────────────────────────────────────────────────────────
# lark-cli helpers
# ─────────────────────────────────────────────────────────────

def _lark(args: List[str]) -> dict:
    """Run a lark-cli command and return parsed JSON. Raises on non-zero exit."""
    cmd = ["lark-cli"] + args + ["--format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"lark-cli returned non-JSON:\n{result.stdout}\n{result.stderr}")
    if not data.get("ok", True):   # some commands use "ok", raw API uses "code"
        err = data.get("error") or data
        raise RuntimeError(f"lark-cli error: {err}")
    return data


def _resolve_table_id(base_token: str, table_name: str) -> str:
    """Find a table's ID by name — avoids hardcoding IDs that change across bases."""
    data = _lark(["base", "+table-list", "--base-token", base_token])
    for t in data["data"]["tables"]:
        if t["name"].strip() == table_name.strip():
            return t["id"]
    available = [t["name"] for t in data["data"]["tables"]]
    raise ValueError(f"Table '{table_name}' not found. Available: {available}")


def _fetch_all_records(base_token: str, table_id: str) -> List[Dict]:
    """Paginate through all records, returning list of {record_id, fields} dicts."""
    records = []
    offset = 0
    limit = 200
    while True:
        data = _lark([
            "base", "+record-list",
            "--base-token", base_token,
            "--table-id", table_id,
            "--offset", str(offset),
            "--limit", str(limit),
        ])
        d = data["data"]
        field_names = d["fields"]
        for rid, row in zip(d["record_id_list"], d["data"]):
            records.append({
                "record_id": rid,
                "fields": dict(zip(field_names, row)),
            })
        print(f"[WF7]   Fetched {len(records)} records so far…", end="\r")
        if not d.get("has_more"):
            break
        offset += limit
    print()
    return records


def _batch_update(base_token: str, table_id: str, updates: List[Dict], dry_run: bool):
    """Write per-record field updates via the raw Bitable batch_update endpoint."""
    if dry_run:
        print(f"[WF7] DRY RUN — {len(updates)} records would be updated (no changes made)")
        return

    # Write payload to a temp file (lark-cli requires relative path)
    payload_path = "wf7_batch_update.json"
    with open(payload_path, "w", encoding="utf-8") as f:
        json.dump({"records": updates}, f, ensure_ascii=False)

    try:
        result = subprocess.run(
            [
                "lark-cli", "api", "POST",
                f"/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/batch_update",
                "--data", f"@./{payload_path}",
            ],
            capture_output=True, text=True,
        )
        resp = json.loads(result.stdout)
        if resp.get("code", -1) != 0:
            raise RuntimeError(f"batch_update failed: {resp}")
        written = len(resp.get("data", {}).get("records", []))
        print(f"[WF7] ✓ Wrote {written} records to Feishu")
    finally:
        if os.path.exists(payload_path):
            os.remove(payload_path)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _find_col(columns: List[str], aliases: List[str]) -> Optional[str]:
    col_lower = {c.strip().lower(): c for c in columns}
    for alias in aliases:
        if alias.lower() in col_lower:
            return col_lower[alias.lower()]
    return None


def _safe_float(val: Any) -> float:
    try:
        return float(str(val).replace(",", "").replace("฿", "").replace("--", "0").strip())
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val: Any) -> int:
    try:
        return int(float(str(val).replace(",", "").replace("--", "0").strip()))
    except (ValueError, TypeError):
        return 0


def _parse_date_str(val: Any) -> Optional[date]:
    """Parse lark-cli date strings: '2026-05-25 00:00:00' or '2026-05-25'."""
    if val is None:
        return None
    s = str(val).strip()
    # Try full datetime first, then date-only (slice to known lengths)
    for s_slice, fmt in [
        (s[:19], "%Y-%m-%d %H:%M:%S"),
        (s[:10], "%Y-%m-%d"),
    ]:
        try:
            return datetime.strptime(s_slice, fmt).date()
        except ValueError:
            continue
    return None


def _extract_select(val: Any) -> Optional[str]:
    """Feishu select fields come back as a list ['Option'] or None."""
    if isinstance(val, list):
        return val[0].strip() if val else None
    if isinstance(val, str):
        return val.strip() or None
    return None


def _parse_period_from_filename(filepath: str) -> Tuple[Optional[date], Optional[date]]:
    basename = os.path.basename(filepath)
    m = re.search(r"(\d{8})-(\d{8})", basename)
    if m:
        try:
            return (
                datetime.strptime(m.group(1), "%Y%m%d").date(),
                datetime.strptime(m.group(2), "%Y%m%d").date(),
            )
        except ValueError:
            pass
    return None, None


def periods_overlap(
    export_from: date, export_to: date,
    sched_from: Optional[date], sched_to: Optional[date],
) -> bool:
    if sched_from is None or sched_to is None:
        return False
    return export_from <= sched_to and export_to >= sched_from


# ─────────────────────────────────────────────────────────────
# Excel loader
# ─────────────────────────────────────────────────────────────

def load_tiktok_creator_list(filepath: str, inspect: bool = False) -> List[Dict]:
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip3 install pandas openpyxl")

    df = pd.read_excel(filepath, dtype=str, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    if inspect:
        print("\n[WF7 INSPECT] Columns in Excel:")
        for i, col in enumerate(df.columns):
            sample = df.iloc[0][col] if len(df) > 0 else ""
            print(f"  [{i:>2}] '{col}'  →  sample: {repr(sample)}")
        print(f"\n[WF7 INSPECT] Total rows: {len(df)}")
        return []

    col_creator = _find_col(df.columns.tolist(), LS_CREATOR_ALIASES)
    col_gmv     = _find_col(df.columns.tolist(), LS_GMV_ALIASES)
    col_streams = _find_col(df.columns.tolist(), LS_STREAMS_ALIASES)

    missing = []
    if not col_creator: missing.append("Creator username")
    if not col_gmv:     missing.append("Affiliate LIVE GMV")
    if not col_streams: missing.append("Affiliate LIVE streams")
    if missing:
        print(f"[WF7] ❌ Could not detect columns: {missing}")
        print("[WF7]    Run with --inspect to see all column names.")
        raise ValueError("Column detection failed.")

    print(f"[WF7] Columns → creator='{col_creator}'  gmv='{col_gmv}'  streams='{col_streams}'")

    import pandas as pd
    records = []
    for _, row in df.iterrows():
        raw = row.get(col_creator, "")
        if pd.isna(raw) or str(raw).strip() == "":
            continue
        records.append({
            "creator_id":   str(raw).strip().lower().lstrip("@"),
            "live_gmv":     _safe_float(row.get(col_gmv, 0)),
            "live_streams": _safe_int(row.get(col_streams, 0)),
        })

    print(f"[WF7] Loaded {len(records)} creator rows from Excel")
    return records


# ─────────────────────────────────────────────────────────────
# Main workflow
# ─────────────────────────────────────────────────────────────

def run(
    dry_run: bool = False,
    input_file: str = "",
    inspect: bool = False,
    update_gmv: bool = True,
    period_start: str = "",
    period_end: str = "",
    **kwargs,
):
    print("\n[WF7] ▶ LS Status Updater (Team B) — starting")
    print(f"[WF7] Auth: lark-cli user session (no app credentials needed)")

    # ── 1. Validate input file ────────────────────────────────
    if not input_file:
        print("[WF7] ❌ No input file. Use --input-file / -f")
        sys.exit(1)
    if not os.path.exists(input_file):
        print(f"[WF7] ❌ File not found: {input_file}")
        sys.exit(1)

    # ── 2. Detect export period ───────────────────────────────
    if period_start and period_end:
        try:
            export_from = datetime.strptime(period_start, "%Y-%m-%d").date()
            export_to   = datetime.strptime(period_end,   "%Y-%m-%d").date()
        except ValueError:
            print("[WF7] ❌ Dates must be YYYY-MM-DD")
            sys.exit(1)
    else:
        export_from, export_to = _parse_period_from_filename(input_file)
        if not export_from:
            print("[WF7] ❌ Could not detect date range from filename.")
            print("       Expected pattern: Creator_List_YYYYMMDD-YYYYMMDD_*.xlsx")
            print("       Or use: --period-start YYYY-MM-DD --period-end YYYY-MM-DD")
            sys.exit(1)

    print(f"[WF7] Export period: {export_from}  →  {export_to}")

    # ── 3. Load Excel ─────────────────────────────────────────
    creator_rows = load_tiktok_creator_list(input_file, inspect=inspect)
    if inspect:
        print("[WF7] Inspect mode — exiting without changes.")
        return {}
    if not creator_rows:
        print("[WF7] ⚠ No creator rows loaded.")
        return {}

    creator_index = {r["creator_id"]: r for r in creator_rows if r.get("creator_id")}
    with_gmv = sum(1 for r in creator_rows if r["live_gmv"] > 0)
    with_ls  = sum(1 for r in creator_rows if r["live_streams"] > 0)
    print(f"[WF7] Creators with LIVE GMV > 0 : {with_gmv}")
    print(f"[WF7] Creators with LIVE streams  : {with_ls}")

    # ── 4. Resolve Feishu table ───────────────────────────────
    print(f"\n[WF7] Resolving table '{TABLE_NAME}' via lark-cli…")
    table_id = _resolve_table_id(BASE_TOKEN, TABLE_NAME)
    print(f"[WF7] Table ID: {table_id}")

    # ── 5. Fetch schedule records ─────────────────────────────
    print(f"[WF7] Fetching schedule records…")
    raw_records = _fetch_all_records(BASE_TOKEN, table_id)
    print(f"[WF7] Fetched {len(raw_records)} schedule records")
    if not raw_records:
        print("[WF7] ⚠ No records found. Check base token and table name.")
        return {}

    # ── 6. Detect Feishu field names ──────────────────────────
    # Use full field-list (not sample record keys) so empty columns are included
    field_list_data = _lark(["base", "+field-list",
                              "--base-token", BASE_TOKEN,
                              "--table-id", table_id])
    all_field_names = [f["name"] for f in field_list_data["data"]["fields"]]
    print(f"[WF7] Feishu fields: {all_field_names}")

    def _find_feishu_field(candidates):
        fl = {k.strip().lower(): k for k in all_field_names}
        for c in candidates:
            if c.strip().lower() in fl:
                return fl[c.strip().lower()]
        return None

    f_creator = _find_feishu_field(["creators id", "creator id", "creator_id", "tiktok id"])
    f_from    = _find_feishu_field(["(from) ls date", "from ls date", "ls start date", "start date"])
    f_to      = _find_feishu_field(["(to)ls date", "(to) ls date", "to ls date", "ls end date", "end date"])
    f_status  = _find_feishu_field(["status"])
    f_ls_gmv      = _find_feishu_field(["ls gmv", "ls_gmv", "gmv"])
    f_ls_streams  = _find_feishu_field(["affiliate live streams", "live streams", "ls streams"])

    missing_fields = []
    if not f_creator: missing_fields.append("Creators ID")
    if not f_from:    missing_fields.append("(From) LS Date")
    if not f_to:      missing_fields.append("(To)LS Date")
    if not f_status:  missing_fields.append("Status")
    if missing_fields:
        print(f"[WF7] ❌ Required fields not found: {missing_fields}")
        print(f"[WF7]    Available: {list(sample_fields.keys())}")
        sys.exit(1)

    print(f"[WF7] Fields → creator='{f_creator}'  from='{f_from}'  to='{f_to}'  status='{f_status}'")
    if f_ls_gmv and update_gmv:
        print(f"[WF7] Will also update GMV field: '{f_ls_gmv}'")
    if f_ls_streams:
        print(f"[WF7] Will also update streams field: '{f_ls_streams}'")

    # ── 7. Match and build updates ────────────────────────────
    updates      = []
    matched      = []
    no_tiktok    = []
    no_gmv       = []
    skipped_date = []
    out_of_range = []

    for rec in raw_records:
        fields    = rec["fields"]
        record_id = rec["record_id"]

        raw_creator = fields.get(f_creator)
        creator_id  = str(raw_creator).strip().lower().lstrip("@") if raw_creator else ""
        if not creator_id:
            continue

        sched_from = _parse_date_str(fields.get(f_from))
        sched_to   = _parse_date_str(fields.get(f_to))
        if sched_from is None or sched_to is None:
            skipped_date.append(creator_id)
            continue

        if not periods_overlap(export_from, export_to, sched_from, sched_to):
            out_of_range.append({
                "creator_id": creator_id,
                "sched": f"{sched_from} → {sched_to}",
            })
            continue

        tt_row = creator_index.get(creator_id)
        if tt_row is None:
            no_tiktok.append({"creator_id": creator_id, "sched": f"{sched_from} → {sched_to}"})
            continue

        live_gmv     = tt_row["live_gmv"]
        live_streams = tt_row["live_streams"]

        if live_gmv <= 0:
            no_gmv.append({"creator_id": creator_id, "streams": live_streams})
            continue

        # ✅ Match — build update
        update_fields: Dict[str, Any] = {f_status: "Success"}
        if update_gmv and f_ls_gmv:
            update_fields[f_ls_gmv] = live_gmv
        if f_ls_streams:
            update_fields[f_ls_streams] = live_streams

        updates.append({"record_id": record_id, "fields": update_fields})
        matched.append({
            "creator_id":   creator_id,
            "live_gmv":     live_gmv,
            "live_streams": live_streams,
            "sched_from":   str(sched_from),
            "sched_to":     str(sched_to),
            "was_status":   _extract_select(fields.get(f_status)),
        })

    # ── 8. Summary report ─────────────────────────────────────
    total_sched = len(matched) + len(no_tiktok) + len(no_gmv) + len(skipped_date)

    print(f"\n[WF7] ── Match Summary {'─'*38}")
    print(f"  ✅ Will mark Success (GMV > 0, period overlap) : {len(matched)}")
    print(f"  🔴 Not in TikTok export                        : {len(no_tiktok)}")
    print(f"  🟡 In export but LIVE GMV = 0                  : {len(no_gmv)}")
    print(f"  ⬛ Schedule outside export period              : {len(out_of_range)}")
    print(f"  ⚠  Missing schedule dates                      : {len(skipped_date)}")

    if matched:
        print(f"\n[WF7] ── Will mark SUCCESS {'─'*36}")
        for m in matched:
            prev = f"  (was: {m['was_status']})" if m['was_status'] and m['was_status'] != 'Success' else ""
            print(f"  {m['creator_id']:35s}  ฿{m['live_gmv']:>10,.0f}  {m['live_streams']} streams  [{m['sched_from']} → {m['sched_to']}]{prev}")

    if no_gmv:
        print(f"\n[WF7] ── LIVE GMV = 0 (will NOT mark Success) {'─'*18}")
        for n in no_gmv[:15]:
            print(f"  {n['creator_id']:35s}  streams: {n['streams']}")
        if len(no_gmv) > 15:
            print(f"  … and {len(no_gmv) - 15} more")

    if no_tiktok:
        print(f"\n[WF7] ── Not found in TikTok export {'─'*28}")
        for n in no_tiktok[:10]:
            print(f"  {n['creator_id']:35s}  scheduled: {n['sched']}")
        if len(no_tiktok) > 10:
            print(f"  … and {len(no_tiktok) - 10} more")

    if skipped_date:
        print(f"\n[WF7] ── Missing schedule dates (skipped) {'─'*22}")
        for c in skipped_date[:10]:
            print(f"  {c}")

    # ── 9. Write to Feishu (or dry-run) ──────────────────────
    if not updates:
        print("\n[WF7] Nothing to update.")
    else:
        CHUNK = 200
        if dry_run:
            print(f"\n[WF7] DRY RUN — {len(updates)} records would be updated (no changes made)")
        else:
            print(f"\n[WF7] Writing {len(updates)} updates to Feishu…")
            for i in range(0, len(updates), CHUNK):
                chunk = updates[i: i + CHUNK]
                _batch_update(BASE_TOKEN, table_id, chunk, dry_run=False)
                print(f"[WF7]   Batch {i // CHUNK + 1}: {len(chunk)} records ✓")
            print("[WF7] ✓ All done")

    print(f"\n[WF7] ✓ Complete")
    return {
        "matched":      len(matched),
        "no_gmv":       len(no_gmv),
        "no_tiktok":    len(no_tiktok),
        "out_of_range": len(out_of_range),
        "skipped_date": len(skipped_date),
    }


# ─────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WF7: LS Status Updater — Team B")
    parser.add_argument("--input-file", "-f", required=True,
                        help="TikTok Creator List Excel (.xlsx). Date range auto-detected from filename.")
    parser.add_argument("--period-start", default="", help="Override start date (YYYY-MM-DD)")
    parser.add_argument("--period-end",   default="", help="Override end date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only — no Feishu writes")
    parser.add_argument("--inspect", action="store_true", help="Print Excel column names and exit")
    parser.add_argument("--no-gmv-update", action="store_true", help="Skip writing GMV back to LS GMV column")
    args = parser.parse_args()

    result = run(
        dry_run=args.dry_run,
        input_file=args.input_file,
        inspect=args.inspect,
        update_gmv=not args.no_gmv_update,
        period_start=args.period_start,
        period_end=args.period_end,
    )
    if result:
        print(f"\n[WF7] Result: {result}")
