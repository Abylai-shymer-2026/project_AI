#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nonna Marketing Bot — STEP 1 DIAGNOSTICS
Goal: verify environment, .env, Google Sheets connectivity, and required worksheet schemas.
This script is **read-only** for Sheets (it does not append/update rows).

USAGE (Windows, PowerShell):
  python nonna_diag.py

If .env isn't auto-loaded by your shell, the script will try to read it from the current directory.
"""

from __future__ import annotations

import os
import sys
import json
import traceback
from pathlib import Path

RESULT_OK = "✅ OK"
RESULT_FAIL = "❌ FAIL"
RESULT_WARN = "⚠️ WARN"

EXPECTED_SHEETS = {
    "users": [
        "user_id", "tg_username", "full_name", "phone",
        "company_name", "industry", "position", "created_at"
    ],
    "influencers": [
        "name","username","profile_url","city","topics","language",
        "followers","reach_stories","reach_reels","reach_post","er",
        "price","updated_at","gender","age","marital_status","children_count"
    ],
    "payments": [
        "user_id", "tg_username", "amount", "currency", "method",
        "status", "payload", "paid_at"
    ],
    "selections": [
        "user_id", "tg_username", "selected_usernames", "export_format",
        "export_url", "selected_at"
    ]
}

def load_env_from_file(env_path: Path) -> None:
    """Minimal .env reader. Lines `KEY=VALUE`. Quotes are optional. Ignores comments and blanks."""
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v
    except Exception:
        print(f"{RESULT_WARN} Couldn't parse .env at {env_path} (continuing).")

def check_python() -> None:
    print("• Python:", sys.version.replace("\n", " "))

def check_packages() -> dict:
    out = {}
    def check_one(name):
        try:
            mod = __import__(name)
            ver = getattr(mod, "__version__", "unknown")
            print(f"• {name}: {ver}")
            out[name] = ver
        except Exception as e:
            print(f"{RESULT_FAIL} import {name}: {e}")
            out[name] = None
    print("Checking packages…")
    for pkg in ["aiogram", "gspread", "pandas", "google.oauth2", "gspread_dataframe"]:
        check_one(pkg.split(".")[0])
    return out

def get_creds(scopes):
    """
    Auth priority:
      1) GOOGLE_SHEETS_CREDENTIALS_JSON
      2) GOOGLE_SHEETS_CREDENTIALS_FILE (absolute or relative path)
    """
    from google.oauth2.service_account import Credentials

    json_str = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "").strip()
    file_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "").strip()

    if json_str:
        try:
            info = json.loads(json_str)
            return Credentials.from_service_account_info(info, scopes=scopes), "json"
        except Exception as e:
            raise RuntimeError(f"Bad GOOGLE_SHEETS_CREDENTIALS_JSON: {e}")

    if file_path:
        p = Path(file_path)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Service account file not found: {p}")
        return Credentials.from_service_account_file(str(p), scopes=scopes), "file"

    raise RuntimeError("Provide GOOGLE_SHEETS_CREDENTIALS_JSON or GOOGLE_SHEETS_CREDENTIALS_FILE")

def check_sheets() -> None:
    print("\nGoogle Sheets connectivity…")
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id:
        print(f"{RESULT_FAIL} GOOGLE_SHEET_ID is empty")
        return

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds, mode = get_creds(scopes)
        import gspread
        from gspread_dataframe import get_as_dataframe

        client = gspread.authorize(creds)
        sh = client.open_by_key(sheet_id)
        print(f"{RESULT_OK} Opened spreadsheet: {sh.title} (auth via {mode})")

        # Verify worksheets + headers
        existing_titles = [ws.title for ws in sh.worksheets()]
        for tab, expected in EXPECTED_SHEETS.items():
            if tab not in existing_titles:
                print(f"{RESULT_FAIL} Missing worksheet '{tab}'")
                continue
            ws = sh.worksheet(tab)
            header = ws.row_values(1)
            missing = [c for c in expected if c not in header]
            if missing:
                print(f"{RESULT_FAIL} Sheet '{tab}': missing columns: {missing}")
            else:
                print(f"{RESULT_OK} Sheet '{tab}' header OK ({len(header)} cols)")

        # Quick read check for influencers
        if "influencers" in existing_titles:
            ws = sh.worksheet("influencers")
            df = get_as_dataframe(ws, evaluate_formulas=True, header=0, nrows=5)
            n_non_empty = int(df.dropna(how="all").shape[0])
            print(f"{RESULT_OK} influencers: can read top rows (non-empty rows ~ {n_non_empty})")

    except Exception as e:
        print(f"{RESULT_FAIL} Sheets error: {e}")
        print(traceback.format_exc())

def main():
    print("=== Nonna Marketing Bot — STEP 1 DIAGNOSTICS ===\n")
    # Try to load .env from the current directory (non-fatal if missing)
    load_env_from_file(Path.cwd() / ".env")

    # Show essential env keys presence
    essential = ["BOT_TOKEN", "OPENAI_API_KEY", "GOOGLE_SHEET_ID",
                 "GOOGLE_SHEETS_CREDENTIALS_JSON", "GOOGLE_SHEETS_CREDENTIALS_FILE",
                 "START_MODE"]
    print("Env presence check:")
    for k in essential:
        val = os.getenv(k)
        if k in ("GOOGLE_SHEETS_CREDENTIALS_JSON",):
            status = RESULT_OK if (val and len(val) > 40) else RESULT_WARN
        elif k in ("GOOGLE_SHEETS_CREDENTIALS_FILE",):
            status = RESULT_OK if (val and len(val) > 3) else RESULT_WARN
        else:
            status = RESULT_OK if val else RESULT_FAIL
        shown = (val[:6] + "…") if val else "EMPTY"
        print(f"• {k}: {shown}  {status}")

    print("")
    check_python()
    pkgs = check_packages()

    # Version hints
    if pkgs.get("aiogram"):
        try:
            import aiogram
            ver = aiogram.__version__
            major = int(ver.split(".")[0])
            if major < 3:
                print(f"{RESULT_FAIL} aiogram must be v3.x, found {ver}")
        except Exception:
            pass

    check_sheets()
    print("\n=== DONE ===")

if __name__ == "__main__":
    main()
