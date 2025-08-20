# app/routers/influencers.py
from __future__ import annotations
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from typing import Set, List, Optional
import re

from ..states import SelectionBasicStates, SelectionDecisionStates
from ..keyboards import paginated_multiselect_kb
from ..influencers import list_cities, list_topics
from ..formatting import ensure_min_words

router = Router(name="influencer_selection")

CITIES_LIMIT = 25
TOPICS_LIMIT = 10

# ===== helpers =====

def _infer_gender_from_text(text: str) -> Optional[str]:
    t = text.lower()
    if any(w in t for w in ["жен", "девушка", "она"]):
        return "ж"
    if any(w in t for w in ["муж", "парень", "он"]):
        return "м"
    return None

def _age_is_ambiguous(text: str) -> bool:
    # «24» — неясно: ровно/до/от/диапазон
    return bool(re.fullmatch(r"\d{1,2}", text.strip()))

def _ask_age_clarify(msg: Message):
    kb = paginated_multiselect_kb(
        items=["Ровно", "До", "От", "Диапазон 20–24"],
        callback_prefix="ageclar",
        items_per_page=20,
        always_show_done=False,
    )
    return msg.answer(
        ensure_min_words("Вы указали «24». Уточните: ровно 24, до 24, от 24, или диапазон 20–24?"),
        reply_markup=kb
    )

# ===== entrypoint =====

async def start_selection(message: Message, state: FSMContext):
    # города (обязательный мультивыбор)
    await state.set_state(SelectionBasicStates.cities)
    cities = list_cities(limit=CITIES_LIMIT)
    await state.update_data(sel_cities=set(), cities_page=0)
    await message.answer(
        ensure_min_words("Супер! Начнём с городов. Можно выбрать несколько — галочка появится рядом."),
        reply_markup=paginated_multiselect_kb(
            cities, "city", selected_items=set(), page=0, items_per_page=10, show_skip=False, always_show_done=True
        ),
    )

# ===== cities =====

@router.callback_query(SelectionBasicStates.cities, F.data.startswith("city:"))
async def on_city(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: Set[str] = set(data.get("sel_cities") or [])
    page = int(data.get("cities_page") or 0)
    cities = list_cities(limit=CITIES_LIMIT)

    _, action, value = cb.data.split(":", 2)
    if action == "pick":
        if value in selected:
            selected.remove(value)
        else:
            selected.add(value)
        await state.update_data(sel_cities=selected)
    elif action == "page":
        page = max(0, int(value))
        await state.update_data(cities_page=page)
    elif action == "done":
        if not selected:
            await cb.answer("Нужно выбрать хотя бы один город", show_alert=True)
        else:
            # Переходим к тематикам
            await state.set_state(SelectionBasicStates.topics)
            await state.update_data(sel_topics=set(), topics_page=0)
            topics = list_topics(limit=TOPICS_LIMIT)
            await cb.message.edit_text(
                ensure_min_words("Отличный выбор городов! Теперь тематики — тоже можно несколько."),
                reply_markup=paginated_multiselect_kb(
                    topics, "topic", selected_items=set(), page=0, items_per_page=10, show_skip=False, always_show_done=True
                ),
            )
            await cb.answer()
            return
    # re-render
    await cb.message.edit_reply_markup(
        reply_markup=paginated_multiselect_kb(
            cities, "city", selected_items=selected, page=page, items_per_page=10, show_skip=False, always_show_done=True
        )
    )
    await cb.answer()

# ===== topics =====

@router.callback_query(SelectionBasicStates.topics, F.data.startswith("topic:"))
async def on_topic(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: Set[str] = set(data.get("sel_topics") or [])
    page = int(data.get("topics_page") or 0)
    topics = list_topics(limit=TOPICS_LIMIT)

    _, action, value = cb.data.split(":", 2)
    if action == "pick":
        if value in selected:
            selected.remove(value)
        else:
            selected.add(value)
        await state.update_data(sel_topics=selected)
    elif action == "page":
        page = max(0, int(value))
        await state.update_data(topics_page=page)
    elif action == "done":
        if not selected:
            await cb.answer("Нужно выбрать хотя бы одну тематику", show_alert=True)
        else:
            # Переходим к возрасту (optional)
            await state.set_state(SelectionBasicStates.age)
            await cb.message.edit_text(
                ensure_min_words("Какой возраст блогеров предпочтителен? Можно написать диапазон (например, 20-24) или оставить пустым."),
                reply_markup=None
            )
            await cb.answer()
            return

    await cb.message.edit_reply_markup(
        reply_markup=paginated_multiselect_kb(
            topics, "topic", selected_items=selected, page=page, items_per_page=10, show_skip=False, always_show_done=True
        )
    )
    await cb.answer()

# ===== age (optional, с уточнением «24») =====

@router.message(SelectionBasicStates.age, F.text)
async def on_age_text(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    if not text:
        await state.update_data(age_text=None)
    else:
        if _age_is_ambiguous(text):
            await state.update_data(pending_age=text)
            await _ask_age_clarify(msg)
            return
        await state.update_data(age_text=text)

    # Переходим к языку
    await state.set_state(SelectionBasicStates.language)
    kb = paginated_multiselect_kb(
        items=["Казахский", "Русский", "Двуязычный", "Пропустить"],
        callback_prefix="lang",
        items_per_page=4,
        always_show_done=False
    )
    await msg.answer(ensure_min_words("Какой язык контента желателен? Выберите один вариант или «Пропустить»."), reply_markup=kb)

@router.callback_query(F.data.startswith("ageclar:"))
async def on_age_clarify(cb: CallbackQuery, state: FSMContext):
    choice = cb.data.split(":", 2)[2]
    base = (await state.get_data()).get("pending_age") or "24"
    mapping = {
        "Ровно": base,
        "До": f"<= {base}",
        "От": f">= {base}",
        "Диапазон 20–24": "20-24",
    }
    await state.update_data(age_text=mapping.get(choice, base), pending_age=None)
    await cb.message.edit_reply_markup(None)
    # дальше спросим язык
    await state.set_state(SelectionBasicStates.language)
    kb = paginated_multiselect_kb(
        items=["Казахский", "Русский", "Двуязычный", "Пропустить"],
        callback_prefix="lang",
        items_per_page=4,
        always_show_done=False
    )
    await cb.message.answer(ensure_min_words("Понял возраст. Теперь язык контента?"), reply_markup=kb)
    await cb.answer()

# ===== language (buttons) =====

@router.callback_query(SelectionBasicStates.language, F.data.startswith("lang:"))
async def on_language(cb: CallbackQuery, state: FSMContext):
    choice = cb.data.split(":", 2)[2]
    language = None if choice == "Пропустить" else choice
    await state.update_data(language=language)

    # Пол попытаемся определить из текста пользователя дальше, но сейчас спрашивать не будем.
    await state.update_data(gender=None)
    # Переходим к решению: Advanced / Показать результат
    await state.set_state(SelectionDecisionStates.decide)
    kb = paginated_multiselect_kb(
        items=["Advanced", "Показать результат"],
        callback_prefix="decide",
        items_per_page=2,
        always_show_done=False
    )
    await cb.message.edit_text(
        ensure_min_words("Хочешь добавить точные фильтры (семейное положение, подписчики, форматы, бюджет) или сразу показать результат?"),
        reply_markup=kb
    )
    await cb.answer()

# ===== decision =====

@router.callback_query(SelectionDecisionStates.decide, F.data.startswith("decide:"))
async def on_decide(cb: CallbackQuery, state: FSMContext):
    action = cb.data.split(":", 2)[2]
    if action == "Advanced":
        # дальше подключим расширенные фильтры на следующем шаге
        await cb.message.edit_text("Окей, включаю расширенные фильтры…")
        # TODO: set_state(...) для advanced
    else:
        # Здесь пока просто завершим базовый этап — на следующем шаге подключим оплату и выдачу.
        await cb.message.edit_text("Принято. На следующем шаге подключу оплату и покажу результаты.")
    await cb.answer()
