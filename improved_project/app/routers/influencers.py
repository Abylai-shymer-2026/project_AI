# app/routers/influencers.py
from __future__ import annotations
from typing import Dict, Optional, List
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from .. import llm
from ..influencers import (
    list_cities, query_influencers, paginate, export_excel, export_pdf
)

router = Router(name="influencers")

_state: Dict[int, Dict] = {}

def _get_state(uid: int) -> Dict:
    return _state.setdefault(uid, {
        "filters": {
            "cities": None,
            "topics": None,
            "age_range": None,
            "followers_range": None,
            "language": None,
        },
        "pending_step": "cities",
        "page": 1,
        "last_list_len": 0,
        "selection_started": False,
    })

def city_buttons() -> InlineKeyboardMarkup:
    cities = list_cities()[:48]
    rows = []; row = []
    for i, c in enumerate(cities, 1):
        row.append(InlineKeyboardButton(text=c, callback_data=f"city:{c}"))
        if i % 3 == 0: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(text="Готово ✅", callback_data="city:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def language_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Казахский", callback_data="lang:Казахский"),
         InlineKeyboardButton(text="Русский", callback_data="lang:Русский"),
         InlineKeyboardButton(text="Двуязычный", callback_data="lang:Двуязычный")],
        [InlineKeyboardButton(text="Пропустить", callback_data="lang:skip")]
    ])

def paging_keyboard(page: int, pages: int) -> InlineKeyboardMarkup:
    rows = [[]]
    if page > 1:
        rows[0].append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page:{page-1}"))
    if page < pages:
        rows[0].append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"page:{page+1}"))
    rows.append([
        InlineKeyboardButton(text="Экспорт PDF", callback_data="export:pdf"),
        InlineKeyboardButton(text="Экспорт Excel", callback_data="export:xlsx"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _buttons_for(step: str) -> InlineKeyboardMarkup | None:
    if step == "cities": return city_buttons()
    if step == "language": return language_buttons()
    return None

async def start_selection(message: Message):
    st = _get_state(message.from_user.id)
    st["pending_step"] = "cities"
    st["selection_started"] = True
    await message.answer(
        "Спасибо за регистрацию! Перейдём к подбору инфлюенсеров под ваши предпочтения. "
        "Для начала выберите города. Можно нажимать кнопки ниже или написать текстом.",
        reply_markup=city_buttons()
    )

@router.callback_query(F.data.startswith("city:"))
async def on_city(cb: CallbackQuery):
    st = _get_state(cb.from_user.id)
    val = cb.data.split(":",1)[1]
    if val != "done":
        route = await llm.postreg_router_decide(
            filters=st["filters"],
            user_text=val,
            user_event="button",
            pending_step=st["pending_step"],
            cities_from_db=list_cities(),
        )
        updates = route.get("updates") or {}
        for k, v in updates.items():
            st["filters"][k] = v
        st["pending_step"] = route.get("next_step") or st["pending_step"]
        await cb.answer(f"Добавлено: {val}")
        return

    if not st["filters"]["cities"]:
        await cb.answer("Выберите хотя бы один город", show_alert=True)
        return

    st["pending_step"] = "topics"
    resp = await llm.postreg_responder_reply(state=st, user_question=None)
    kb = _buttons_for(st["pending_step"]) if resp.get("ask_buttons") != "none" else None
    await cb.message.edit_text(resp["assistant_text"], reply_markup=kb)

@router.callback_query(F.data.startswith("lang:"))
async def on_lang(cb: CallbackQuery):
    st = _get_state(cb.from_user.id)
    code = cb.data.split(":",1)[1]
    val = None if code == "skip" else code

    route = await llm.postreg_router_decide(
        filters=st["filters"],
        user_text=(val or "Пропустить"),
        user_event="button",
        pending_step=st["pending_step"],
        cities_from_db=list_cities(),
    )
    for k, v in (route.get("updates") or {}).items():
        st["filters"][k] = v
    st["pending_step"] = route.get("next_step") or st["pending_step"]

    if st["pending_step"] == "done":
        await show_results(cb.message, st)
        await cb.answer()
        return

    resp = await llm.postreg_responder_reply(state=st, user_question=None)
    kb = _buttons_for(st["pending_step"]) if resp.get("ask_buttons") != "none" else None
    await cb.message.edit_text(resp["assistant_text"], reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("page:"))
async def on_page(cb: CallbackQuery):
    st = _get_state(cb.from_user.id)
    try:
        st["page"] = int(cb.data.split(":",1)[1])
    except:
        pass
    await show_results(cb.message, st, edit=True)

@router.callback_query(F.data.startswith("export:"))
async def on_export(cb: CallbackQuery):
    st = _get_state(cb.from_user.id)
    df = query_influencers(**st["filters"])
    if df.empty:
        await cb.answer("Пока нет результатов", show_alert=True); return
    if cb.data.endswith("pdf"):
        path = f"influencers_{cb.from_user.id}.pdf"
        export_pdf(df, path)
        await cb.message.answer_document(document=(path, "influencers.pdf"))
    else:
        path = f"influencers_{cb.from_user.id}.xlsx"
        export_excel(df, path)
        await cb.message.answer_document(document=(path, "influencers.xlsx"))
    await cb.answer()

async def show_results(message: Message, st: Dict, edit: bool=False):
    df = query_influencers(**st["filters"])
    page = st.get("page", 1)
    chunk, pages = paginate(df, page, 5)
    st["last_list_len"] = len(df)

    if chunk.empty:
        text = "По выбранным фильтрам пока ничего не нашли. Попробуйте расширить диапазоны или убрать часть условий."
        if edit: await message.edit_text(text)
        else:    await message.answer(text)
        return

    lines = []
    for _, r in chunk.iterrows():
        followers = int(r["followers"]) if pd.notnull(r["followers"]) else "-"
        lines.append(
            f"• {r.get('name','')} (@{r.get('username','')}) — {r.get('city','')} • {r.get('language','')}\n"
            f"  Темы: {r.get('topics','')}\n"
            f"  Подписчики: {followers} | ER: {r.get('er','-')} | Цена: {r.get('price','-')}\n"
            f"  Профиль: {r.get('profile_url','')}"
        )
    text = "Подходящие инфлюенсеры:\n\n" + "\n\n".join(lines) + f"\n\nСтр. {page}/{pages}"
    kb = paging_keyboard(page, pages)
    if edit:
        await message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    else:
        await message.answer(text, reply_markup=kb, disable_web_page_preview=True)

@router.message()
async def on_message(message: Message):
    st = _get_state(message.from_user.id)
    txt = (message.text or "").strip()

    route = await llm.postreg_router_decide(
        filters=st["filters"],
        user_text=txt,
        user_event="message",
        pending_step=st["pending_step"],
        cities_from_db=list_cities(),
    )
    for k, v in (route.get("updates") or {}).items():
        st["filters"][k] = v
    st["pending_step"] = route.get("next_step") or st["pending_step"]

    user_q = txt if route.get("intent") in {"question","both"} else None
    resp = await llm.postreg_responder_reply(state=st, user_question=user_q)

    if st["pending_step"] == "done":
        await message.answer(resp["assistant_text"])
        await show_results(message, st)
        return

    kb = _buttons_for(st["pending_step"]) if resp.get("ask_buttons") != "none" else None
    await message.answer(resp["assistant_text"], reply_markup=kb)
