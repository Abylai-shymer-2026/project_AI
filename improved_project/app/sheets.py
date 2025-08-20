# app/sheets.py
from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import gspread
import pytz
from gspread.exceptions import APIError, WorksheetNotFound, SpreadsheetNotFound
from gspread import Spreadsheet
from google.oauth2.service_account import Credentials

from .config import settings

_LOG = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client: Optional[gspread.Client] = None


def _get_credentials() -> Credentials:
    _LOG.debug("Попытка создания учетных данных Google...")
    sa_json = settings.GOOGLE_SHEETS_CREDENTIALS_JSON

    # ИСПОЛЬЗУЕМ НОВУЮ ПЕРЕМЕННУЮ С АБСОЛЮТНЫМ ПУТЕМ
    sa_file_path = settings.CREDENTIALS_FILE_ABSPATH

    if sa_json:
        try:
            # ... (логика для JSON остается без изменений)
            if sa_json.startswith("'") and sa_json.endswith("'"):
                sa_json = sa_json[1:-1]
            info = json.loads(sa_json)
            creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
            _LOG.info("Учетные данные Google успешно созданы из JSON для: %s", info.get("client_email"))
            return creds
        except Exception as e:
            _LOG.error("Ошибка при создании учетных данных из JSON: %s. Пробуем файл...", e)

    if sa_file_path and sa_file_path.exists():
        try:
            creds = Credentials.from_service_account_file(str(sa_file_path), scopes=_SCOPES)
            _LOG.info("Учетные данные Google успешно созданы из файла: %s", sa_file_path)
            return creds
        except Exception as e:
            _LOG.error("Ошибка при создании учетных данных из файла %s: %s", sa_file_path, e)
    elif sa_file_path:
        # Логируем ошибку, если файл по абсолютному пути не найден
        _LOG.critical(f"Файл с учетными данными НЕ НАЙДЕН по абсолютному пути: {sa_file_path}")

    raise RuntimeError(
        "Не удалось создать учетные данные Google. Проверьте GOOGLE_SHEETS_CREDENTIALS_JSON или GOOGLE_SHEETS_CREDENTIALS_FILE в .env")


def get_client() -> gspread.Client:
    # ... (эта функция без изменений)
    global _client
    if _client is None:
        _LOG.debug("Клиент gspread не инициализирован. Авторизуемся...")
        creds = _get_credentials()
        _client = gspread.authorize(creds)
        _LOG.info("Клиент gspread успешно авторизован.")
    return _client


def get_spreadsheet(client: gspread.Client) -> Spreadsheet:
    # ... (эта функция без изменений)
    try:
        sh = client.open_by_key(settings.GOOGLE_SHEET_ID)
        _LOG.info("Таблица '%s' успешно открыта.", sh.title)
        return sh
    except SpreadsheetNotFound:
        _LOG.critical(
            f"ТАБЛИЦА С ID '{settings.GOOGLE_SHEET_ID}' НЕ НАЙДЕНА! Проверьте ID и права доступа у сервисного аккаунта.")
        raise
    except APIError as e:
        _LOG.error("Ошибка API при открытии таблицы: %s", e)
        raise


def append_user(profile: Dict[str, Optional[str]], tg_id: int) -> bool:
    # ... (эта функция без изменений)
    try:
        _LOG.info(f"Начинаю синхронную запись пользователя {tg_id} в Google Sheets...")
        client = get_client()
        sh = get_spreadsheet(client)

        try:
            ws = sh.worksheet("users")
        except WorksheetNotFound:
            _LOG.warning("Лист 'users' не найден, создаю новый.")
            # Выравниваем заголовки с диагностикой/инициализатором
            header = [
                "user_id", "tg_username", "full_name", "phone",
                "company_name", "industry", "position", "created_at"
            ]
            ws = sh.add_worksheet(title="users", rows=1000, cols=len(header))
            ws.append_row(header)

        tz = pytz.timezone("Asia/Almaty")
        created_at = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        # Пытаемся определить текущего пользователя из профиля (если доступно)
        tg_username = (profile.get("tg_username") or "").strip()
        full_name = (profile.get("name") or "").strip()
        company_name = (profile.get("company") or "").strip()
        industry = (profile.get("industry") or "").strip()
        position = (profile.get("position") or "").strip()
        phone = (profile.get("phone") or "").strip()

        row = [
            str(tg_id), tg_username, full_name, phone,
            company_name, industry, position, created_at,
        ]

        ws.append_row(row, value_input_option="USER_ENTERED")
        _LOG.info("Пользователь %s успешно записан в таблицу 'users'.", tg_id)
        return True

    except Exception as e:
        _LOG.exception("!!! КРИТИЧЕСКАЯ ОШИБКА при записи в Google Sheets: %s", e)
        return False


def _ensure_worksheet(sh: Spreadsheet, title: str, header: List[str]):
    try:
        ws = sh.worksheet(title)
    except WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=max(10, len(header)))
        ws.append_row(header)
        return ws
    # extend header if needed
    existing = ws.row_values(1)
    need_extend = False
    new_header = list(existing)
    for c in header:
        if c not in new_header:
            new_header.append(c)
            need_extend = True
    if need_extend:
        ws.resize(rows=ws.row_count, cols=max(ws.col_count, len(new_header)))
        ws.update('1:1', [new_header])
    return ws


def append_payment(user_id: int, tg_username: str | None, amount: int, currency: str, method: str, status: str, payload: str | None = None) -> bool:
    try:
        _LOG.info("Запись платежа в 'payments' для %s", user_id)
        client = get_client()
        sh = get_spreadsheet(client)
        header = ["user_id", "tg_username", "amount", "currency", "method", "status", "payload", "paid_at"]
        ws = _ensure_worksheet(sh, "payments", header)
        tz = pytz.timezone("Asia/Almaty")
        paid_at = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        row = [str(user_id), (tg_username or ""), amount, currency, method, status, (payload or ""), paid_at]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception:
        _LOG.exception("Ошибка записи платежа")
        return False


def append_selection(user_id: int, tg_username: str | None, selected_usernames: List[str], export_format: str | None = None, export_url: str | None = None) -> bool:
    try:
        _LOG.info("Запись выбора в 'selections' для %s (%d шт.)", user_id, len(selected_usernames))
        client = get_client()
        sh = get_spreadsheet(client)
        header = ["user_id", "tg_username", "selected_usernames", "export_format", "export_url", "selected_at"]
        ws = _ensure_worksheet(sh, "selections", header)
        tz = pytz.timezone("Asia/Almaty")
        ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        row = [str(user_id), (tg_username or ""), ", ".join(["@" + u.lstrip("@") for u in selected_usernames]), (export_format or ""), (export_url or ""), ts]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception:
        _LOG.exception("Ошибка записи выбора блогеров")
        return False