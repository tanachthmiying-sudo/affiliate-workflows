"""
Feishu / Lark API Client
Handles: Auth, Bitable (Base) read/write, Bot messaging
"""

import os
import json
import time
import requests
from typing import Optional, Dict, List, Any
from datetime import datetime


class FeishuClient:
    """
    Feishu/Lark API wrapper for affiliate workflows.
    Covers: Tenant auth, Bitable (Base) CRUD, Bot messages.
    """

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        bot_webhook: Optional[str] = None,
    ):
        self.app_id = app_id or os.getenv("FEISHU_APP_ID")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET")
        self.bot_webhook = bot_webhook or os.getenv("FEISHU_BOT_WEBHOOK")
        self._token: Optional[str] = None
        self._token_expires_at: float = 0

        # Credentials are validated lazily on first API call (allows --dry-run without creds)

    # ─────────────────────────────────────────────
    # Authentication
    # ─────────────────────────────────────────────

    def _refresh_token(self) -> str:
        """Fetch a new tenant_access_token if expired."""
        if not self.app_id or not self.app_secret:
            raise ValueError(
                "Missing Feishu credentials. Set FEISHU_APP_ID and FEISHU_APP_SECRET "
                "environment variables or pass them directly."
            )
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        resp = requests.post(
            f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"Feishu auth failed: {data.get('msg')}")

        self._token = data["tenant_access_token"]
        self._token_expires_at = time.time() + data.get("expire", 7200)
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._refresh_token()}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        resp = requests.get(
            f"{self.BASE_URL}{path}",
            headers=self._headers(),
            params=params or {},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu API error [{path}]: {data.get('msg')}")
        return data.get("data", {})

    def _post(self, path: str, body: Dict) -> Dict:
        resp = requests.post(
            f"{self.BASE_URL}{path}",
            headers=self._headers(),
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu API error [{path}]: {data.get('msg')}")
        return data.get("data", {})

    def _patch(self, path: str, body: Dict) -> Dict:
        resp = requests.patch(
            f"{self.BASE_URL}{path}",
            headers=self._headers(),
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu API error [{path}]: {data.get('msg')}")
        return data.get("data", {})

    # ─────────────────────────────────────────────
    # Bitable (Base) — Tables
    # ─────────────────────────────────────────────

    def list_tables(self, app_token: str) -> List[Dict]:
        """List all tables in a Bitable app."""
        data = self._get(f"/bitable/v1/apps/{app_token}/tables")
        return data.get("items", [])

    def get_table_fields(self, app_token: str, table_id: str) -> List[Dict]:
        """Get all field definitions for a table."""
        data = self._get(f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields")
        return data.get("items", [])

    # ─────────────────────────────────────────────
    # Bitable — Records
    # ─────────────────────────────────────────────

    def get_records(
        self,
        app_token: str,
        table_id: str,
        filter_str: Optional[str] = None,
        page_size: int = 100,
        field_names: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Fetch all records from a Bitable table (auto-paginates).
        filter_str: Feishu filter formula, e.g. 'AND(CurrentValue.[Status]="Active")'
        """
        records = []
        page_token = None

        while True:
            params: Dict[str, Any] = {"page_size": page_size}
            if filter_str:
                params["filter"] = filter_str
            if field_names:
                params["field_names"] = json.dumps(field_names)
            if page_token:
                params["page_token"] = page_token

            data = self._get(
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                params=params,
            )
            records.extend(data.get("items", []))

            if not data.get("has_more"):
                break
            page_token = data.get("page_token")

        return records

    def upsert_record(
        self,
        app_token: str,
        table_id: str,
        fields: Dict[str, Any],
        record_id: Optional[str] = None,
    ) -> Dict:
        """Create a new record or update an existing one."""
        if record_id:
            return self._patch(
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
                {"fields": fields},
            )
        return self._post(
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            {"fields": fields},
        )

    def batch_create_records(
        self, app_token: str, table_id: str, records: List[Dict[str, Any]]
    ) -> Dict:
        """Batch create up to 500 records at once."""
        return self._post(
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
            {"records": [{"fields": r} for r in records]},
        )

    def batch_update_records(
        self, app_token: str, table_id: str, updates: List[Dict]
    ) -> Dict:
        """
        Batch update records.
        updates: list of {"record_id": "...", "fields": {...}}
        """
        return self._post(
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update",
            {"records": updates},
        )

    def find_record_by_field(
        self,
        app_token: str,
        table_id: str,
        field_name: str,
        field_value: str,
    ) -> Optional[Dict]:
        """Find first record matching a field value."""
        records = self.get_records(
            app_token,
            table_id,
            filter_str=f'CurrentValue.[{field_name}]="{field_value}"',
        )
        return records[0] if records else None

    # ─────────────────────────────────────────────
    # Bot Messaging
    # ─────────────────────────────────────────────

    def send_bot_message(
        self,
        text: Optional[str] = None,
        card: Optional[Dict] = None,
        webhook: Optional[str] = None,
    ) -> bool:
        """
        Send a message via Feishu custom bot webhook.
        Supports plain text or interactive card.
        """
        url = webhook or self.bot_webhook
        if not url:
            print("[Feishu Bot] No webhook configured — skipping notification.")
            return False

        if card:
            payload = {"msg_type": "interactive", "card": card}
        else:
            payload = {"msg_type": "text", "content": {"text": text or ""}}

        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200

    def send_workflow_summary(
        self,
        workflow_name: str,
        status: str,
        summary_lines: List[str],
        highlight_items: Optional[List[str]] = None,
        webhook: Optional[str] = None,
    ) -> bool:
        """
        Send a structured workflow result card to Feishu bot.
        status: "success" | "warning" | "error"
        """
        color_map = {"success": "green", "warning": "yellow", "error": "red"}
        color = color_map.get(status, "blue")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        elements = [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(f"- {s}" for s in summary_lines)},
            }
        ]

        if highlight_items:
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**⚡ Highlights:**\n" + "\n".join(f"• {h}" for h in highlight_items),
                    },
                }
            )

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"[{workflow_name}] Run Complete"},
                "template": color,
            },
            "elements": elements
            + [
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": f"Ran at {now} by Claude Code"}],
                }
            ],
        }

        return self.send_bot_message(card=card, webhook=webhook)
