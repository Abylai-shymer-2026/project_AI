#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nonna_setup_sheets.py — one-time initializer for the Nonna Marketing bot Google Sheet.

It creates (or fixes) the following worksheets with the expected headers:
  - users
  - influencers
  - payments
  - selections

The script is **idempotent**: run it safely multiple times; it will only add what's missing.
It reads .env from the current folder (like nonna_diag.py).

Usage:
  python nonna_setup_sheets.py
"""
from __future__ import annotations

import os
import json
from pathlib import Path

EXPECTED = {
    "users": [
        "user_id", "tg_username", "full_name", "phone",
        "company_name", "industry", "position", "created_at",
    ],
    "influencers": [
        "name","username","profile_url","city","topics","language",
        "followers","reach_stories","reach_reels","reach_post","er",
        "price","updated_at","gender","age","marital_status","children_count",
    ],
    "payments": [
        "user_id", "tg_username", "amount", "currency", "method",
        "status", "payload", "paid_at",
    ],
    "selections": [
        "user_id", "tg_username", "selected_usernames", "export_format",
        "export_url", "selected_at",
    ],
}

def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def get_creds(scopes):
    from google.oauth2.service_account import Credentials
    js = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "").strip()
    fp = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "").strip()
    if js:
        info = json.loads(js)
        return Credentials.from_service_account_info(info, scopes=scopes), "json"
    if fp:
        p = Path(fp)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        info = json.loads(p.read_text(encoding="utf-8"))
        return Credentials.from_service_account_file(str(p), scopes=scopes), "file"
    raise RuntimeError("Provide GOOGLE_SHEETS_CREDENTIALS_JSON or GOOGLE_SHEETS_CREDENTIALS_FILE")

def ensure_tab(sh, title: str, header: list[str]):
    try:
        ws = sh.worksheet(title)
        existing = ws.row_values(1)
        if not existing:
            ws.update('1:1', [header])
            print(f"• {title}: header created ({len(header)} cols)")
        else:
            changed = False
            new_header = list(existing)
            for c in header:
                if c not in new_header:
                    new_header.append(c)
                    changed = True
            if changed:
                ws.resize(rows=ws.row_count, cols=max(ws.col_count, len(new_header)))
                ws.update('1:1', [new_header])
                print(f"• {title}: header extended to {len(new_header)} cols")
            else:
                print(f"• {title}: header OK ({len(existing)} cols)")
        return ws
    except Exception:
        ws = sh.add_worksheet(title=title, rows=1000, cols=max(10, len(header)))
        ws.update([header], range_name=f"{title}!1:1")
        print(f"• {title}: worksheet created with header")
        return ws

def main():
    print("=== Nonna Marketing Bot — SHEET INITIALIZER ===")
    load_env(Path.cwd() / ".env")

    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id or " " in sheet_id:
        raise SystemExit("Set a valid GOOGLE_SHEET_ID in .env (no spaces).")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds, mode = get_creds(scopes)

    import gspread
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    print(f"Opened spreadsheet: {sh.title} (auth via {mode})")

    for tab, header in EXPECTED.items():
        ensure_tab(sh, tab, header)

    print("All required worksheets are present with correct headers.")
    print("You can now run: python nonna_diag.py")

if __name__ == "__main__":
    main()
