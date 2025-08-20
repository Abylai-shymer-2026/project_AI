# app/influencers.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import re, io, math
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe

from .sheets import get_client, get_spreadsheet
from .config import settings


def _read_influencers_worksheet() -> pd.DataFrame:
    # ... (код этой функции не меняется)
    client = get_client()
    sh = get_spreadsheet(client)
    try:
        ws = sh.worksheet("influencers")
    except gspread.WorksheetNotFound:
        header = [
            "name", "username", "profile_url", "city", "topics", "language", "followers",
            "reach_stories", "reach_reels", "reach_post", "price", "updated_at",
            "gender", "age", "marital_status", "children_count"
        ]
        ws = sh.add_worksheet(title="influencers", rows=1000, cols=len(header))
        ws.append_row(header)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0, dtype=str)
    df = df.dropna(how="all")
    for col in ("followers", "reach_stories", "reach_reels", "reach_post", "price", "age", "children_count"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.replace("\u202f", "").str.replace(" ", "")
    for col in ("followers", "reach_stories", "reach_reels", "reach_post", "price", "children_count"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("city", "topics", "language", "gender", "marital_status"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
    return df


def list_cities(limit: int = 24) -> List[str]:
    # ... (код этой функции не меняется)
    df = _read_influencers_worksheet()
    if "city" not in df.columns: return []
    vals = (df["city"].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist())
    return sorted(set(vals), key=str.lower)[:limit]


def list_topics(limit: int = 24) -> List[str]:
    # ... (код этой функции не меняется)
    df = _read_influencers_worksheet()
    if "topics" not in df.columns: return []
    all_topics: List[str] = []
    for raw in df["topics"].dropna().astype(str).tolist():
        parts = re.split(r"[;,/|]+|\s*,\s*", raw)
        all_topics.extend([p.strip() for p in parts if p.strip()])
    return sorted(set(all_topics), key=str.lower)[:limit]


def parse_age_range(s: str) -> Optional[Tuple[Optional[int], Optional[int]]]:
    # ... (код этой функции не меняется)
    if not s: return None
    t = s.strip().lower().replace("лет", "").replace("г.", "").replace("г", "").replace(" ", "")
    t = t.replace("до", "<=").replace("от", ">=").replace("—", "-").replace("..", "-")
    m = re.match(r"^(\d{1,2})\+$", t)
    if m: return (int(m.group(1)), None)
    m = re.match(r"^<=?(\d{1,2})$", t)
    if m: return (None, int(m.group(1)))
    m = re.match(r"^>=?(\d{1,2})$", t)
    if m: return (int(m.group(1)), None)
    m = re.match(r"^(\d{1,2})-(\d{1,2})$", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    m = re.match(r"^(\d{1,2})$", t)
    if m:
        x = int(m.group(1));
        return (x, x)
    return None


def _topics_contains(cell: str, req_topics: List[str]) -> bool:
    """Проверяет, содержит ли ячейка хотя бы одну из требуемых тем."""
    if not cell or not req_topics: return False
    # Приводим все к нижнему регистру один раз для эффективности
    cell_topics = {p.strip().lower() for p in re.split(r"[;,/|]+|\s*,\s*", str(cell)) if p.strip()}
    req_topics_set = {t.strip().lower() for t in req_topics}
    # Возвращаем True, если есть хотя бы одно пересечение
    return not cell_topics.isdisjoint(req_topics_set)


def query_influencers(
        *, city: Optional[List[str]] = None, topic: Optional[List[str]] = None,
        age_range: Optional[Tuple[Optional[int], Optional[int]]] = None,
        gender: Optional[str] = None, language: Optional[str] = None,
        marital_status: Optional[str] = None,  # <-- НОВЫЙ ПАРАМЕТР
        has_children: Optional[bool] = None,  # <-- НОВЫЙ ПАРАМЕТР
        children_count: Optional[str] = None,  # <-- НОВЫЙ ПАРАМЕТР
        followers_min: Optional[int] = None, followers_max: Optional[int] = None,
        budget_max: Optional[int] = None, services: Optional[List[str]] = None,
        limit: Optional[int] = None
) -> pd.DataFrame:
    df = _read_influencers_worksheet()
    if df.empty:
        return df

    mask = pd.Series([True] * len(df))

    if city:
        city_lower = [c.strip().lower() for c in city]
        mask &= df.get("city", "").astype(str).str.strip().str.lower().isin(city_lower)

    if topic:
        mask &= df.get("topics", "").apply(lambda s: _topics_contains(s, topic))

    if language:
        mask &= df.get("language", "").astype(str).str.lower().str.contains(language.strip().lower())

    if gender:
        g = gender.strip().lower()
        mask &= df.get("gender", "").astype(str).str.lower().str.startswith(g[:1])

    # --- НОВАЯ ЛОГИКА ФИЛЬТРАЦИИ ---
    if marital_status:
        # Ищем совпадения в колонке 'marital_status'
        # married -> женат, замужем
        # single -> не женат, не замужем
        # divorced -> разведен, разведена
        status_map = {
            "married": ["женат", "замужем"],
            "single": ["не женат", "не замужем"],
            "divorced": ["разведен", "разведена"]
        }
        if marital_status in status_map:
            mask &= df.get("marital_status", "").astype(str).str.strip().str.lower().isin(status_map[marital_status])

    if has_children is not None:
        # Фильтруем по наличию детей. 'children_count' > 0 означает, что дети есть.
        # pd.to_numeric преобразует не-числа в NaN, которые мы заменяем на 0.
        children_col = pd.to_numeric(df.get("children_count", "0"), errors='coerce').fillna(0)
        if has_children:
            mask &= (children_col > 0)
        else:
            mask &= (children_col == 0)

    if children_count:
        children_col = pd.to_numeric(df.get("children_count", "0"), errors='coerce').fillna(0)
        if children_count == "more":
            mask &= (children_col > 4)
        elif children_count.isdigit():
            mask &= (children_col == int(children_count))
    # --- КОНЕЦ НОВОЙ ЛОГИКИ ---

    if age_range:
        # ... (логика фильтрации по возрасту без изменений) ...
        lo, hi = age_range
        col = df.get("age")
        if col is not None:
            def ok(cell: str) -> bool:
                cell = str(cell or "").strip()
                if not cell: return False
                if cell.isdigit():
                    age = int(cell)
                    if lo is not None and age < lo: return False
                    if hi is not None and age > hi: return False
                    return True
                rng = parse_age_range(cell)
                if rng is None: return False
                a, b = rng
                if lo is not None and a is not None and b is not None and b < lo: return False
                if hi is not None and a is not None and a > hi: return False
                return True

            mask &= col.apply(ok)

    if followers_min is not None: mask &= df.get("followers").fillna(-1) >= followers_min
    if followers_max is not None: mask &= df.get("followers").fillna(10 ** 12) <= followers_max
    if budget_max is not None and "price" in df.columns:
        mask &= df["price"].fillna(10 ** 12) <= budget_max

    res = df.loc[mask].copy()
    if "updated_at" in res.columns:
        res["__ts"] = pd.to_datetime(res["updated_at"], errors="coerce")
        res = res.sort_values(["__ts", "followers"], ascending=[False, False]).drop(columns=["__ts"])
    elif "followers" in res.columns:
        res = res.sort_values("followers", ascending=False)

    return res.head(limit) if limit else res


def paginate(df: pd.DataFrame, page: int, per_page: int = 5):
    # ... (код этой и других функций ниже не меняется)
    import math
    total = max(1, int(math.ceil(len(df) / float(per_page))))
    page = max(1, min(page, total))
    s, e = (page - 1) * per_page, (page - 1) * per_page + per_page
    return df.iloc[s:e].copy(), total


def export_excel(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Influencers")
    return output.getvalue()


def export_pdf(df: pd.DataFrame) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 20 * mm
    c.setFont("Helvetica-Bold", 14);
    c.drawString(20 * mm, y, "Influencers");
    y -= 10 * mm
    c.setFont("Helvetica", 10)
    cols = ["name", "username", "city", "topics", "language", "followers", "price"]
    rows = df[[c for c in cols if c in df.columns]].fillna("").astype(str).values.tolist()
    for row in rows:
        line = " | ".join(row)
        for w in simpleSplit(line, "Helvetica", 10, width - 40 * mm):
            if y < 20 * mm: c.showPage(); y = height - 20 * mm; c.setFont("Helvetica", 10)
            c.drawString(20 * mm, y, w);
            y -= 6 * mm
        y -= 4 * mm
    c.save()
    return buffer.getvalue()