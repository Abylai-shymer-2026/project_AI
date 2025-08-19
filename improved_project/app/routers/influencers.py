# app/routers/influencers.py
from __future__ import annotations
import io
from typing import Dict, Optional, List
import pandas as pd  # ИСПРАВЛЕНО: Добавлен импорт pandas
from aiogram import Router, F
from aiogram.enums import ChatAction
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from .. import llm
# Эти функции должны быть адаптированы для работы с байтами в памяти
# Например, export_excel_to_bytes(df) -> bytes
from ..influencers import (
    list_cities, query_influencers, paginate, export_excel, export_pdf
)

router = Router(name="influencers")

# ВАЖНОЕ ПРИМЕЧАНИЕ:
# Хранение состояния в глобальном словаре _state - рискованно.
# Если бот перезапустится, все пользователи потеряют свой прогресс подбора.
# Рекомендуется переделать этот механизм на машину состояний (FSM) из aiogram.
# Это более сложная задача, которую можно выполнить следующим шагом.
_state: Dict[int, Dict] = {}


def _get_state(uid: int) -> Dict:
    return _state.setdefault(uid, {
        "filters": {
            "cities": None, "topics": None, "age_range": None,
            "followers_range": None, "language": None,
        },
        "pending_step": "cities", "page": 1,
        "last_list_len": 0, "selection_started": False,
    })


# ... (остальные функции-хелперы без изменений: city_buttons, language_buttons, etc.) ...
def city_buttons() -> InlineKeyboardMarkup:
    cities = list_cities()[:48]
    rows = [];
    row = []
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
        rows[0].append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page:{page - 1}"))
    if page < pages:
        rows[0].append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"page:{page + 1}"))
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
    # ДОБАВЛЯЕМ "TYPING..."
    await message.bot.send_chat_action(message.from_user.id, action=ChatAction.TYPING)

    st = _get_state(message.from_user.id)
    st["pending_step"] = "cities"
    st["selection_started"] = True

    # Генерируем текст через LLM для большей вариативности
    resp = await llm.postreg_responder_reply(state=st, user_question=None)
    kb = _buttons_for(st["pending_step"]) if resp.get("ask_buttons") != "none" else None

    await message.answer(resp["assistant_text"], reply_markup=kb)


@router.callback_query(F.data.startswith("city:"))
async def on_city(cb: CallbackQuery):
    # ДОБАВЛЯЕМ "TYPING..."
    await cb.message.bot.send_chat_action(cb.from_user.id, action=ChatAction.TYPING)

    st = _get_state(cb.from_user.id)
    val = cb.data.split(":", 1)[1]
    if val != "done":
        route = await llm.postreg_router_decide(
            filters=st["filters"], user_text=val, user_event="button",
            pending_step=st["pending_step"], cities_from_db=list_cities(),
        )
        updates = route.get("updates") or {}
        for k, v in updates.items(): st["filters"][k] = v
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
    # ДОБАВЛЯЕМ "TYPING..."
    await cb.message.bot.send_chat_action(cb.from_user.id, action=ChatAction.TYPING)

    st = _get_state(cb.from_user.id)
    code = cb.data.split(":", 1)[1]
    val = None if code == "skip" else code

    route = await llm.postreg_router_decide(
        filters=st["filters"], user_text=(val or "Пропустить"), user_event="button",
        pending_step=st["pending_step"], cities_from_db=list_cities(),
    )
    for k, v in (route.get("updates") or {}).items(): st["filters"][k] = v
    st["pending_step"] = route.get("next_step") or st["pending_step"]

    if st["pending_step"] == "done":
        await cb.message.edit_text("Отлично, все фильтры заполнены! Сейчас я подготовлю для вас список.")
        await show_results(cb.message, st)
        await cb.answer()
        return

    resp = await llm.postreg_responder_reply(state=st, user_question=None)
    kb = _buttons_for(st["pending_step"]) if resp.get("ask_buttons") != "none" else None
    await cb.message.edit_text(resp["assistant_text"], reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("page:"))
async def on_page(cb: CallbackQuery):
    await cb.message.bot.send_chat_action(cb.from_user.id, action=ChatAction.TYPING)
    st = _get_state(cb.from_user.id)
    try:
        st["page"] = int(cb.data.split(":", 1)[1])
    except:
        pass
    await show_results(cb.message, st, edit=True)
    await cb.answer()


@router.callback_query(F.data.startswith("export:"))
async def on_export(cb: CallbackQuery):
    await cb.answer("Готовлю файл, это может занять несколько секунд...")
    await cb.message.bot.send_chat_action(cb.from_user.id, action=ChatAction.UPLOAD_DOCUMENT)

    st = _get_state(cb.from_user.id)
    df = query_influencers(**st["filters"])
    if df.empty:
        await cb.message.answer("Нет данных для экспорта. Попробуйте изменить фильтры.")
        return

    # ИЗМЕНЕНО: Отправка файлов из памяти, а не с диска
    # ПРИМЕЧАНИЕ: Ваши функции `export_pdf` и `export_excel` должны быть
    # изменены, чтобы возвращать байты (bytes) вместо сохранения на диск.
    # Например: `def export_pdf_to_bytes(df) -> bytes:`
    if cb.data.endswith("pdf"):
        # file_bytes = export_pdf_to_bytes(df) # <-- Ваша измененная функция
        # document = BufferedInputFile(file_bytes, filename="influencers.pdf")
        # await cb.message.answer_document(document=document)
        await cb.message.answer("Функция экспорта в PDF в разработке.")  # Временная заглушка
    else:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Influencers')
        output.seek(0)
        document = BufferedInputFile(output.read(), filename="influencers.xlsx")
        await cb.message.answer_document(document=document)


async def show_results(message: Message, st: Dict, edit: bool = False):
    await message.bot.send_chat_action(message.from_user.id, action=ChatAction.TYPING)

    df = query_influencers(**st["filters"])
    page = st.get("page", 1)
    chunk, pages = paginate(df, page, 5)
    st["last_list_len"] = len(df)

    if chunk.empty:
        text = "По вашим фильтрам никого не нашли. 😕 Попробуйте выбрать другие города или темы."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    lines = []
    for _, r in chunk.iterrows():
        followers = f'{int(r["followers"]):,}'.replace(',', ' ') if pd.notnull(r["followers"]) else "-"
        lines.append(
            f"👤 <b>{r.get('name', '')}</b> (@{r.get('username', '')}) - {r.get('city', '')}\n"
            f"<b>Темы:</b> {r.get('topics', '')}\n"
            f"<b>Подписчики:</b> {followers} | <b>ER:</b> {r.get('er', '-')}\n"
            f"<a href='{r.get('profile_url', '')}'>Ссылка на профиль</a>"
        )
    text = "Вот кто нашёлся по вашим критериям:\n\n" + "\n\n".join(lines) + f"\n\n<i>Страница {page} из {pages}</i>"
    kb = paging_keyboard(page, pages)
    if edit:
        await message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    else:
        await message.answer(text, reply_markup=kb, disable_web_page_preview=True)


@router.message()
async def on_message(message: Message):
    # ДОБАВЛЯЕМ "TYPING..."
    await message.bot.send_chat_action(message.from_user.id, action=ChatAction.TYPING)

    st = _get_state(message.from_user.id)
    if not st.get("selection_started"):
        await message.answer("Пожалуйста, сначала завершите регистрацию.")
        return

    txt = (message.text or "").strip()
    route = await llm.postreg_router_decide(
        filters=st["filters"], user_text=txt, user_event="message",
        pending_step=st["pending_step"], cities_from_db=list_cities(),
    )
    for k, v in (route.get("updates") or {}).items(): st["filters"][k] = v
    st["pending_step"] = route.get("next_step") or st["pending_step"]

    user_q = txt if route.get("intent") in {"question", "both"} else None
    resp = await llm.postreg_responder_reply(state=st, user_question=user_q)

    if st["pending_step"] == "done":
        await message.answer(resp["assistant_text"])
        await show_results(message, st)
        return

    kb = _buttons_for(st["pending_step"]) if resp.get("ask_buttons") != "none" else None
    await message.answer(resp["assistant_text"], reply_markup=kb)