# app/sheets.py
from __future__ import annotations
import os, json
from typing import Optional, List, Dict, Any
from datetime import datetime
import pytz  # Библиотека для работы с часовыми поясами

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ... (код для аутентификации остается без изменений) ...

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
    raise RuntimeError("Google Sheets creds not provided.")

def _get_client() -> gspread.Client:
    global _client
    if _client is None:
        _client = gspread.authorize(_build_credentials())
    return _client

def _get_spreadsheet() -> gspread.Spreadsheet:
    global _spreadsheet
    if _spreadsheet is None:
        if not _SPREADSHEET_ID:
            raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID is not set.")
        _spreadsheet = _get_client().open_by_key(_SPREADSHEET_ID)
    return _spreadsheet

def get_worksheet(sheet_name: str) -> pd.DataFrame:
    ws = _get_spreadsheet().worksheet(sheet_name)
    records = ws.get_all_records(numeric_value_strategy=gspread.utils.NumericValueStrategy.FLOAT)
    return pd.DataFrame(records)

def append_row(sheet_name: str, row: List[Any]) -> None:
    ws = _get_spreadsheet().worksheet(sheet_name)
    ws.append_row(row, value_input_option="USER_ENTERED")

def upsert_dict_row(sheet_name: str, row_dict: Dict[str, Any]) -> None:
    ws = _get_spreadsheet().worksheet(sheet_name)
    header = ws.row_values(1)
    values = [row_dict.get(col, "") for col in header]
    ws.append_row(values, value_input_option="USER_ENTERED")

# НОВАЯ ФУНКЦИЯ для сохранения пользователя
def append_user(profile: Dict, tg_id: int) -> bool:
    """
    Сохраняет данные пользователя в лист 'users' в Google Sheets.
    """
    try:
        # Устанавливаем часовой пояс для корректной даты
        tz = pytz.timezone('Asia/Almaty')
        created_at = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

        user_data = {
            "tg_id": tg_id,
            "fio": profile.get("name"),
            "company name": profile.get("company"),
            "industry": profile.get("industry"),
            "position": profile.get("position"),
            "phone": profile.get("phone"),
            "created_at": created_at,
        }
        # Используем вашу функцию upsert_dict_row для добавления
        upsert_dict_row(sheet_name="users", row_dict=user_data)
        return True
    except Exception as e:
        # В реальном проекте здесь лучше логировать ошибку
        print(f"Error appending user to Google Sheets: {e}")
        return False

def append_user(profile: Dict, tg_id: int) -> bool:
    """
    Сохраняет данные пользователя в лист 'users' в Google Sheets.
    """
    try:
        # Устанавливаем часовой пояс для корректной даты (Алматы)
        tz = pytz.timezone('Asia/Almaty')
        created_at = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

        user_data = {
            "tg_id": tg_id,
            "fio": profile.get("name"),
            "company name": profile.get("company"), # Убедитесь, что название столбца в таблице именно такое
            "industry": profile.get("industry"),
            "position": profile.get("position"),
            "phone": profile.get("phone"),
            "created_at": created_at,
        }
        # Используем существующую функцию для добавления строки
        worksheet = _get_spreadsheet().worksheet("users") # Укажите точное имя листа
        header = worksheet.row_values(1)
        values = [user_data.get(col, "") for col in header]
        worksheet.append_row(values, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        print(f"Error appending user to Google Sheets: {e}") # Логирование ошибки
        return False