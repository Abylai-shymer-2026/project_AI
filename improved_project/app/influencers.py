# app/influencers.py
from __future__ import annotations
import re
import math
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd
from .sheets import get_worksheet  # ваш helper


COLS = ["name","username","profile_url","city","topics","language","followers","reach_stories",
        "reach_reels","reach_post","er","price","updated_at","gender","age","marital_status","children_count"]

def _load_df() -> pd.DataFrame:
    ws = get_worksheet("influencers")
    if isinstance(ws, pd.DataFrame):
        df = ws
    else:
        import gspread_dataframe
        df = gspread_dataframe.get_as_dataframe(ws, evaluate_formulas=True, header=0)
    df = df.rename(columns={c: c.strip() for c in df.columns})
    for c in COLS:
        if c not in df.columns:
            df[c] = None
    for c in ["followers","age","reach_stories","reach_reels","reach_post","price"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["city","topics","language","username","name","profile_url","gender","marital_status"]:
        if c in df.columns:
            df[c] = df[c].astype(str).fillna("").str.strip()
    return df

def list_cities() -> List[str]:
    df = _load_df()
    cities = sorted(set([c for c in df["city"].dropna().astype(str).str.strip() if c]))
    return cities

def _topics_match(row_topics: str, want_topics: List[str]) -> bool:
    if not want_topics:
        return True
    if not row_topics:
        return False
    row_set = set([t.strip().lower() for t in re.split(r"[;,/]| и ", row_topics) if t.strip()])
    want_set = set([t.strip().lower() for t in want_topics if t.strip()])
    return bool(row_set & want_set)

def query_influencers(
    *,
    cities: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    age_range: Optional[Dict[str, Optional[int]]] = None,
    followers_range: Optional[Dict[str, Optional[int]]] = None,
    language: Optional[str] = None,
) -> pd.DataFrame:
    df = _load_df()
    if cities:
        low = set([c.lower() for c in cities])
        df = df[df["city"].str.lower().isin(low)]
    if topics:
        df = df[df["topics"].apply(lambda x: _topics_match(x, topics))]
    if age_range:
        a_min = age_range.get("min"); a_max = age_range.get("max")
        if a_min is not None: df = df[df["age"] >= a_min]
        if a_max is not None: df = df[df["age"] <= a_max]
    if followers_range:
        f_min = followers_range.get("min"); f_max = followers_range.get("max")
        if f_min is not None: df = df[df["followers"] >= f_min]
        if f_max is not None: df = df[df["followers"] <= f_max]
    if language:
        df = df[df["language"].str.lower() == language.strip().lower()]
    return df

def paginate(df: pd.DataFrame, page: int, page_size: int = 5) -> Tuple[pd.DataFrame, int]:
    total = len(df)
    pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, pages))
    start = (page - 1) * page_size
    end = start + page_size
    return df.iloc[start:end], pages

def export_excel(df: pd.DataFrame, path: str) -> str:
    out = df[["name","username","profile_url","city","topics","language","followers","er","price","updated_at"]].copy()
    out.to_excel(path, index=False)
    return path

def export_pdf(df: pd.DataFrame, path: str) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    x, y = 40, height - 40
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Influencer Shortlist"); y -= 20
    c.setFont("Helvetica", 10)
    for _, row in df.iterrows():
        lines = [
            f"{row.get('name','')} (@{row.get('username','')}) — {row.get('city','')} • {row.get('language','')}",
            f"Topics: {row.get('topics','')}",
            f"Followers: {int(row['followers']) if pd.notnull(row.get('followers')) else '-'} | ER: {row.get('er','-')} | Price: {row.get('price','-')}",
            f"Profile: {row.get('profile_url','')}",
        ]
        for ln in lines:
            if y < 60:
                c.showPage(); y = height - 40; c.setFont("Helvetica", 10)
            c.drawString(x, y, ln[:110]); y -= 14
        y -= 6
    c.save()
    return path
