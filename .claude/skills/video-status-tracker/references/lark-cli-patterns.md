# lark-cli patterns for Feishu Base (Bitable)

These are the exact command shapes that worked when this skill was built and
verified against a real base. Deviating from them is what causes the
silent-failure modes noted inline.

## 0. Auth

This skill assumes `lark-cli` is already installed and authenticated with at
least the `base` domain scope (covers table/field/record read+write). Check:

```bash
lark-cli auth status
```

If `base:table:read`, `base:field:create`, `base:record:read` are missing:

```bash
lark-cli auth login --domain base --no-wait --json
```

Returns `device_code` and `verification_url`. Generate a QR code
(`lark-cli auth qrcode "<url>" --output ./qr.png` — relative path only),
show the user the QR + URL, end the turn, wait for them to confirm they've
authorized, then:

```bash
lark-cli auth login --device-code "<device_code>"
```

Don't reuse a stale device_code across turns — get a fresh one each time.

## 1. Finding the base and table

Resolve the table_id by name every run — don't hardcode it:

```bash
lark-cli base +table-list --base-token "<APP_TOKEN>" --format pretty
```

Match `"Creator's Pool"` by name and extract its `id`.

There's no reliable Drive-search-by-name without an extra `search:docs:read`
scope most setups won't have. Always ask the user to paste the Feishu Base
URL (`https://xxx.feishu.cn/base/<APP_TOKEN>?table=...`) to extract the
app_token — don't try to look it up.

## 2. Listing fields (check before creating — idempotency)

```bash
lark-cli base +field-list --base-token "<APP_TOKEN>" --table-id "<TABLE_ID>"
```

Parse the JSON, build a set of existing field names, and only call
`+field-create` for ones that are missing.

## 3. Creating fields

```bash
lark-cli base +field-create --base-token "<APP_TOKEN>" --table-id "<TABLE_ID>" \
  --json '{"name":"Video Status","type":"select","multiple":false,"options":[{"name":"Posted"},{"name":"Pending"},{"name":"Not Posted"}]}'
```

Field type reference for this workflow:

| Field | `type` | notes |
|---|---|---|
| Video Status | `select` | options: Posted / Pending / Not Posted |
| Video ID | `text` | |
| Video Title | `text` | |
| Post Date | `datetime` | |
| Views, Likes, Comments, Shares, Orders | `number` | |
| GMV (THB) | `number` | |
| Growth Potential | `select` | options: 🔥 High / ⚡ Medium / ⬇ Low |
| Boost Recommended | `checkbox` | |
| AFS Conversion Rate | `text` | |
| Last Updated | `datetime` | |

**Known limitation:** the Bitable API has no "insert after field X" option.
`+field-create` always appends at the end. Tell the user if they ask about
column placement — don't try to work around it.

## 4. Reading records with filter + pagination

`--format json` is required for parseable output (`--format pretty` only
works on some subcommands like `+table-list`, not `+record-list`).

```bash
lark-cli base +record-list --base-token "<APP_TOKEN>" --table-id "<TABLE_ID>" \
  --filter-json '{"logic":"and","conditions":[["Brand","intersects",["Bostanten Women'"'"'s Bag"]]]}' \
  --offset 0 --limit 200 --format json
```

- `--limit` maxes at 200. Loop `--offset` (0, 200, 400...) until
  `data.has_more` is `false`.
- Use `intersects` for select/multi-select filters; `==` for exact matches.
- Do date-range filtering client-side in Python after fetching — it's more
  reliable than crafting date comparison expressions in `--filter-json`.
- Datetime fields come back as strings like `"2026-06-09 00:00:00"` — parse
  with `datetime.strptime(s, "%Y-%m-%d %H:%M:%S")`.

## 5. Writing per-record updates (the part that trips people up)

`lark-cli base +record-batch-update` applies **one uniform patch to every
record_id in the list** — useless when each row needs different values.

Use the raw API passthrough for per-record heterogeneous writes:

```bash
lark-cli api POST "/open-apis/bitable/v1/apps/<APP_TOKEN>/tables/<TABLE_ID>/records/batch_update" \
  --data @./batch_update.json
```

`batch_update.json` must be a relative path from the current working
directory (see §6). Shape:

```json
{
  "records": [
    {"record_id": "recXXX", "fields": {"Video Status": "Posted", "Views": 524}},
    {"record_id": "recYYY", "fields": {"Video Status": "Not Posted"}}
  ]
}
```

Max 200 records per call — chunk if needed.

**Datetime fields in the raw API must be epoch milliseconds (integer), not
date strings.** The CLI's convenience shorthand `"2026-03-24 10:00:00"` only
works through CLI-level helpers (like `+record-upsert`), not the raw JSON
body. Sending a string here causes `DatetimeFieldConvFail`. Convert:

```python
int(datetime_obj.timestamp() * 1000)
```

After the call, verify `response["code"] == 0` and that
`len(response["data"]["records"])` matches what you sent.

## 6. CLI sandbox path rules

- `--data @file` and `--output` reject absolute paths. Always `cd` into the
  project directory first and use relative paths (`./batch_update.json`).
  Clean up temp files afterward (`rm -f ./batch_update.json`).
- `--format` values differ per subcommand — `+table-list` accepts `pretty`;
  `+record-list` only accepts `json` or `markdown`. Run
  `lark-cli base <command> --help` when unsure.
