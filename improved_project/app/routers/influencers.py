# app/routers/influencers.py
from __future__ import annotations
import io
from typing import Dict
import pandas as pd
from aiogram import Router, F
from aiogram.enums import ChatAction
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, BufferedInputFile)

from .. import llm
# Убедитесь, что в вашем файле app/influencers.py есть эти функции
from ..influencers import (
    list_cities, query_influencers, paginate, list_topics,
    export_excel, export_pdf
)

router = Router(name="influencers")

# --- Управление состоянием подбора в памяти ---
_user_states: Dict[int, Dict] = {}


def get_user_state(user_id: int) -> Dict:
    """Получает или создает состояние для пользователя."""
    if user_id not in _user_states:
        _user_states[user_id] = {
            "filters": {},
            "page": 1,
            "advanced_choice_made": False,
            "advanced_mode": False
        }
    return _user_states[user_id]


def get_next_step(state: Dict) -> str:
    """Определяет следующий шаг сценария на основе заполненных фильтров."""
    filters = state["filters"]
    # Используем .get() для безопасного доступа
    if not filters.get("cities"): return "city"
    if not filters.get("topics"): return "topic"
    if not filters.get("age_range"): return "age"
    if not filters.get("gender"): return "gender"
    if not filters.get("language"): return "language"
    if not state.get("advanced_choice_made"): return "advanced_or_results"
    if state.get("advanced_mode"):
        if not filters.get("followers_range"): return "followers"
        if not filters.get("price_range"): return "budget"  # 'budget' соответствует 'price_range'
        if not filters.get("service"): return "service"
    return "done"


# --- Клавиатуры ---

def city_buttons() -> InlineKeyboardMarkup:
    cities = list_cities()[:12]
    buttons = [InlineKeyboardButton(text=c, callback_data=f"select:{c}") for c in cities]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 3] for i in range(0, len(buttons), 3)])


def topic_buttons() -> InlineKeyboardMarkup:
    # Убедитесь, что функция list_topics() существует в app/influencers.py
    topics = list_topics()[:8]
    buttons = [InlineKeyboardButton(text=t, callback_data=f"select:{t}") for t in topics]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)])


def gender_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мужской 👨", callback_data="select:Мужской"),
         InlineKeyboardButton(text="Женский 👩", callback_data="select:Женский")],
        [InlineKeyboardButton(text="Пропустить ➡️", callback_data="select:пропустить")]])


def language_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Казахский", callback_data="select:Казахский"),
         InlineKeyboardButton(text="Русский", callback_data="select:Русский")],
        [InlineKeyboardButton(text="Двуязычный", callback_data="select:Двуязычный"),
         InlineKeyboardButton(text="Пропустить ➡️", callback_data="select:пропустить")]])


def advanced_or_results_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Получить результат", callback_data="select:get_results")],
        [InlineKeyboardButton(text="🔍 Продвинутый поиск", callback_data="select:advanced_search")]])


def results_keyboard(page: int, max_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page:{page - 1}"))
    if page < max_pages:
        nav.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"page:{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([
        InlineKeyboardButton(text="📄 Экспорт PDF", callback_data="export:pdf"),
        InlineKeyboardButton(text="📊 Экспорт Excel", callback_data="export:xlsx"),
    ])
    buttons.append([InlineKeyboardButton(text="🔄 Новый подбор", callback_data="new_search")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Главный цикл обработки ---

async def process_selection_step(message: Message, user_input: str | None, event: str):
    state = get_user_state(message.from_user.id)
    step_before = get_next_step(state)

    # Обновляем состояние на основе ввода пользователя
    if step_before == "advanced_or_results" and user_input in ["get_results", "advanced_search"]:
        state["advanced_choice_made"] = True
        state["advanced_mode"] = (user_input == "advanced_search")
    elif user_input:
        # Пропускаемые шаги
        if user_input.lower() in ["пропустить", "любой", "skip"] and step_before in ["age", "gender", "language",
                                                                                     "followers", "budget", "service"]:
            state["filters"][
                step_before + "_range" if "age" in step_before or "follower" in step_before else step_before] = "skipped"
        else:
            route = await llm.postreg_router_decide(
                filters=state["filters"], user_text=user_input, user_event=event,
                pending_step=step_before, cities_from_db=list_cities())
            for key, value in (route.get("updates") or {}).items():
                if value: state["filters"][key] = value

    step_after = get_next_step(state)

    # Генерируем ответ ИИ
    if step_after == "done":
        await message.answer("Отлично, все критерии заданы! Готовлю для вас список... 🕵️‍♀️")
        await show_results(message, state)
        return

    resp = await llm.postreg_responder_reply(
        state={"filters": state["filters"], "pending_step": step_after}, user_question=None)

    kb_map = {
        "city": city_buttons(), "topic": topic_buttons(), "gender": gender_buttons(),
        "language": language_buttons(), "advanced_or_results": advanced_or_results_keyboard()
    }
    await message.answer(resp.get("assistant_text", "Продолжим..."), reply_markup=kb_map.get(step_after))


# --- Обработчики Aiogram ---

async def start_selection(message: Message):
    _user_states.pop(message.from_user.id, None)
    await process_selection_step(message, user_input=None, event="start")


@router.message(F.text)
async def on_text_message(message: Message):
    if message.from_user.id in _user_states:
        await process_selection_step(message, user_input=message.text, event="message")


@router.callback_query(F.data.startswith("select:"))
async def on_button_click(cb: CallbackQuery):
    if cb.from_user.id in _user_states:
        user_choice = cb.data.split(":", 1)[1]
        await cb.message.edit_text(f"<i>Ваш выбор: {user_choice}</i>")
        await process_selection_step(cb.message, user_input=user_choice, event="button")
    await cb.answer()


@router.callback_query(F.data == "new_search")
async def on_new_search(cb: CallbackQuery):
    await cb.message.delete()
    await start_selection(cb.message)
    await cb.answer()


async def show_results(message: Message, state: Dict, edit: bool = False):
    filters_to_query = {k: v for k, v in state.get("filters", {}).items() if v != "skipped"}
    df = query_influencers(**filters_to_query)

    if df.empty:
        await message.answer("К сожалению, по вашим фильтрам никого не найдено. 😕", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔄 Новый подбор", callback_data="new_search")]]))
        return

    page = state.get("page", 1)
    chunk, max_pages = paginate(df, page, 5)

    lines = []
    for _, r in chunk.iterrows():
        followers = f'{int(r["followers"]):,}'.replace(',', ' ') if pd.notnull(r.get("followers")) else "-"
        lines.append(
            f"👤 <b>{r.get('name', '')}</b> (@{r.get('username', '')}) - {r.get('city', '')}\n"
            f"<b>Темы:</b> {r.get('topics', '')}\n"
            f"<b>Подписчики:</b> {followers} | <b>Язык:</b> {r.get('language', '-')}"
        )

    text = "Вот кто нашёлся по вашим критериям:\n\n" + "\n\n".join(lines) + f"\n\n<i>Страница {page} из {max_pages}</i>"

    if edit:
        await message.edit_text(text, reply_markup=results_keyboard(page, max_pages))
    else:
        await message.answer(text, reply_markup=results_keyboard(page, max_pages))


@router.callback_query(F.data.startswith("page:"))
async def on_page_switch(cb: CallbackQuery):
    state = get_user_state(cb.from_user.id)
    state["page"] = int(cb.data.split(":")[1])
    await show_results(cb.message, state, edit=True)
    await cb.answer()


@router.callback_query(F.data.startswith("export:"))
async def on_export(cb: CallbackQuery):
    await cb.answer("Готовлю файл...")
    state = get_user_state(cb.from_user.id)
    filters_to_query = {k: v for k, v in state.get("filters", {}).items() if v != "skipped"}
    df = query_influencers(**filters_to_query)

    if df.empty:
        await cb.message.answer("Нет данных для экспорта.")
        return

    if cb.data.endswith("pdf"):
        # Логика для PDF
        pdf_bytes = io.BytesIO()
        # Тут должна быть ваша реализация export_pdf, пишущая в BytesIO
        # export_pdf(df, pdf_bytes)
        # pdf_bytes.seek(0)
        # await cb.message.answer_document(BufferedInputFile(pdf_bytes, "influencers.pdf"))
        await cb.message.answer("Экспорт в PDF пока в разработке.")

    else:  # Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Influencers')
        output.seek(0)
        await cb.message.answer_document(BufferedInputFile(output, "influencers.xlsx"))