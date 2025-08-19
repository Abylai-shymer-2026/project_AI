from __future__ import annotations
import os, json
from typing import Optional, List, Dict, Any

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# Ожидаемые переменные окружения:
# GOOGLE_SHEETS_SPREADSHEET_ID=...  (ID таблицы)
# GOOGLE_SERVICE_ACCOUNT_FILE=app/creds/service_account.json  (либо)
# GOOGLE_SERVICE_ACCOUNT_JSON={...}  (JSON строкой)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")

_client: Optional[gspread.Client] = None
_spreadsheet: Optional[gspread.Spreadsheet] = None

def _build_credentials() -> Credentials:
    sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        info = json.loads(sa_json)
        return Credentials.from_service_account_info(info, scopes=_SCOPES)
    if sa_file:
        return Credentials.from_service_account_file(sa_file, scopes=_SCOPES)
    raise RuntimeError("Google Sheets creds not provided. Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON.")

def _get_client() -> gspread.Client:
    global _client
    if _client is None:
        creds = _build_credentials()
        _client = gspread.authorize(creds)
    return _client

def _get_spreadsheet() -> gspread.Spreadsheet:
    global _spreadsheet
    if _spreadsheet is None:
        if not _SPREADSHEET_ID:
            raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID is not set.")
        _spreadsheet = _get_client().open_by_key(_SPREADSHEET_ID)
    return _spreadsheet

def get_worksheet(sheet_name: str):
    """
    Возвращает либо gspread.Worksheet, либо pandas.DataFrame.
    Для совместимости с текущим app/influencers.py можно вернуть DataFrame сразу.
    """
    ws = _get_spreadsheet().worksheet(sheet_name)
    records = ws.get_all_records(numeric_value_strategy=gspread.utils.NumericValueStrategy.FLOAT)
    df = pd.DataFrame(records)
    return df  # influencers.py умеет работать и с DataFrame

# Доп. хелперы (можно использовать для регистрации пользователей):
def append_row(sheet_name: str, row: List[Any]) -> None:
    ws = _get_spreadsheet().worksheet(sheet_name)
    ws.append_row(row, value_input_option="USER_ENTERED")

def upsert_dict_row(sheet_name: str, row_dict: Dict[str, Any]) -> None:
    """
    Быстрый способ добавить запись, учитывая имена колонок в шапке.
    """
    ws = _get_spreadsheet().worksheet(sheet_name)
    header = ws.row_values(1)
    values = [row_dict.get(col, "") for col in header]
    ws.append_row(values, value_input_option="USER_ENTERED")