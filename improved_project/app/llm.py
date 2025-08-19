# app/routers/influencers.py
from __future__ import annotations
import io
import pandas as pd
from typing import Dict
from aiogram import Router, F
from aiogram.enums import ChatAction
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, BufferedInputFile)

from ..influencers import (
    list_cities, query_influencers, paginate, list_topics
)

router = Router(name="influencers")

# --- Управление состоянием подбора ---
# Храним фильтры и текущий шаг для каждого пользователя в словаре.
# Примечание: Эти данные будут сброшены при перезапуске бота.
# Для постоянного хранения потребуется более сложное решение (например, Redis).
_user_states: Dict[int, Dict] = {}


def get_user_state(user_id: int) -> Dict:
    """Получает или создает состояние для пользователя."""
    default_state = {
        "filters": {
            "cities": None, "topics": None, "age_range": None,
            "gender": None, "language": None, "followers_range": None,
            "price_range": None, "service": None,
        },
        "current_step": "city",  # Начинаем с города
        "page": 1
    }
    return _user_states.setdefault(user_id, default_state)


def get_next_step(state: Dict) -> str:
    """Определяет следующий шаг сценария на основе заполненных фильтров."""
    filters = state["filters"]
    if filters["cities"] is None: return "city"
    if filters["topics"] is None: return "topic"
    if filters["age_range"] is None: return "age"
    if filters["gender"] is None: return "gender"
    if filters["language"] is None: return "language"

    # После базовых фильтров предлагаем выбор
    if state.get("advanced_choice_made") is None:
        return "advanced_or_results"

    # Если выбрали продвинутый поиск
    if state.get("advanced_mode") is True:
        if filters["followers_range"] is None: return "followers"
        if filters["price_range"] is None: return "budget"
        if filters["service"] is None: return "service"

    return "done"  # Все шаги пройдены


# --- Клавиатуры ---
def city_buttons() -> InlineKeyboardMarkup:
    cities = list_cities()[:12]
    buttons = [InlineKeyboardButton(text=c, callback_data=f"select:{c}") for c in cities]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 3] for i in range(0, len(buttons), 3)])


def topic_buttons() -> InlineKeyboardMarkup:
    topics = list_topics()[:8]
    buttons = [InlineKeyboardButton(text=t, callback_data=f"select:{t}") for t in topics]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)])


def gender_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мужской 👨", callback_data="select:Мужской"),
         InlineKeyboardButton(text="Женский 👩", callback_data="select:Женский")],
        [InlineKeyboardButton(text="Пропустить ➡️", callback_data="select:пропустить")]
    ])


def language_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Казахский", callback_data="select:Казахский"),
         InlineKeyboardButton(text="Русский", callback_data="select:Русский")],
        [InlineKeyboardButton(text="Двуязычный", callback_data="select:Двуязычный"),
         InlineKeyboardButton(text="Пропустить ➡️", callback_data="select:пропустить")]
    ])


def advanced_or_results_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Получить результат", callback_data="select:get_results")],
        [InlineKeyboardButton(text="🔍 Продвинутый поиск", callback_data="select:advanced_search")]
    ])


def get_keyboard_for_step(step: str) -> InlineKeyboardMarkup | None:
    """Возвращает нужную клавиатуру для текущего шага."""
    if step == "city": return city_buttons()
    if step == "topic": return topic_buttons()
    if step == "gender": return gender_buttons()
    if step == "language": return language_buttons()
    if step == "advanced_or_results": return advanced_or_results_keyboard()
    return None


def results_keyboard(page: int, max_pages: int) -> InlineKeyboardMarkup:
    # ... (код этой функции не меняется, как в прошлый раз) ...
    pass


# --- Главный цикл обработки ---
async def process_selection_step(message: Message, user_input: str | None = None, event: str = "message"):
    """
    Основная функция, которая управляет диалогом подбора.
    Вызывается при каждом сообщении или нажатии кнопки от пользователя.
    """
    await message.bot.send_chat_action(message.from_user.id, action=ChatAction.TYPING)
    user_id = message.from_user.id
    state = get_user_state(user_id)

    # 1. Роутер: анализируем ответ пользователя и обновляем фильтры
    current_step_before = get_next_step(state)

    # Особая логика для выбора "результат/продвинутый"
    if current_step_before == "advanced_or_results" and user_input in ["get_results", "advanced_search"]:
        state["advanced_choice_made"] = True
        if user_input == "advanced_search":
            state["advanced_mode"] = True
        else:
            state["advanced_mode"] = False
    else:
        # Отправляем текст пользователя в LLM для извлечения фильтров
        route = await llm.postreg_router_decide(
            filters=state["filters"],
            user_text=user_input or "",
            user_event=event,
            pending_step=current_step_before,
            cities_from_db=list_cities(),
        )
        # Применяем обновления
        for key, value in (route.get("updates") or {}).items():
            if value:
                state["filters"][key] = value

    # 2. Определяем следующий шаг
    current_step_after = get_next_step(state)
    state["current_step"] = current_step_after

    # 3. Респондер: генерируем ответ ИИ
    if current_step_after == "done":
        await message.answer("Отлично, все критерии заданы! Готовлю для вас список... 🕵️‍♀️")
        await show_results(message, state)
        return

    # Просим LLM сгенерировать следующий вопрос
    response_data = await llm.postreg_responder_reply(
        state={"filters": state["filters"], "pending_step": current_step_after},
        user_question=None  # Предполагаем, что пользователь отвечает на вопросы, а не задает свои
    )

    text_to_send = response_data.get("assistant_text") or "Что-то пошло не так, давайте попробуем снова."
    keyboard = get_keyboard_for_step(current_step_after)

    await message.answer(text_to_send, reply_markup=keyboard)


# --- Обработчики Aiogram ---

async def start_selection(message: Message):
    """Запускает новый сеанс подбора."""
    _user_states.pop(message.from_user.id, None)  # Сбрасываем старое состояние
    await process_selection_step(message, user_input=None, event="start")


@router.message(F.text)
async def on_text_message(message: Message):
    """Ловит все текстовые ответы пользователя на этапе подбора."""
    if not _user_states.get(message.from_user.id):  # Защита от случайных сообщений
        return
    await process_selection_step(message, user_input=message.text)


@router.callback_query(F.data.startswith("select:"))
async def on_button_click(cb: CallbackQuery):
    """Ловит все нажатия на инлайн-кнопки."""
    if not _user_states.get(cb.from_user.id):
        return

    user_choice = cb.data.split(":", 1)[1]
    # Редактируем сообщение, чтобы убрать кнопки и показать выбор
    await cb.message.edit_text(f"Ваш выбор: {user_choice}")
    await process_selection_step(cb.message, user_input=user_choice, event="button")
    await cb.answer()


async def show_results(message: Message, state: FSMContext, edit: bool = False):
    await message.bot.send_chat_action(message.from_user.id, action=ChatAction.TYPING)
    data = await state.get_data()
    filters = data.get("filters", {})
    page = data.get("page", 1)

    # Здесь должна быть ваша логика запроса к Google Sheets
    df = query_influencers(**filters)
    if df.empty:
        await message.answer(
            "К сожалению, по вашим фильтрам никого не найдено. 😕\nПопробуйте запустить новый подбор с другими критериями.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔄 Новый подбор", callback_data="new_search")]]))
        return

    chunk, max_pages = paginate(df, page, 5)

    text_lines = []
    for _, r in chunk.iterrows():
        followers = f'{int(r["followers"]):,}'.replace(',', ' ') if pd.notnull(r["followers"]) else "-"
        text_lines.append(
            f"👤 <b>{r.get('name', '')}</b> (@{r.get('username', '')}) - {r.get('city', '')}\n"
            f"<b>Темы:</b> {r.get('topics', '')}\n"
            f"<b>Подписчики:</b> {followers} | <b>Язык:</b> {r.get('language', '-')}"
        )

    text = "Вот кто нашёлся по вашим критериям:\n\n" + "\n\n".join(
        text_lines) + f"\n\n<i>Страница {page} из {max_pages}</i>"

    if edit:
        await message.edit_text(text, reply_markup=results_keyboard(page, max_pages))
    else:
        await message.answer(text, reply_markup=results_keyboard(page, max_pages))

    await state.set_state(InfluencerSearch.showing_results)


@router.callback_query(InfluencerSearch.showing_results, F.data.startswith("page:"))
async def on_page_switch(cb: CallbackQuery, state: FSMContext):
    page = int(cb.data.split(":")[1])
    await state.update_data(page=page)
    await show_results(cb.message, state, edit=True)


@router.callback_query(F.data == "new_search")
async def on_new_search(cb: CallbackQuery, state: FSMContext):
    # Запускаем сценарий заново, передавая message из callback'а
    await start_selection(cb.message, state)


# --- Экспорт (можно вынести в отдельный файл) ---
@router.callback_query(InfluencerSearch.showing_results, F.data.startswith("export:"))
async def on_export(cb: CallbackQuery, state: FSMContext):
    # ... (логика экспорта остается такой же, как в предыдущем ответе) ...
    await cb.answer("Готовлю файл...")

# --- Важно! Регистрируем хендлеры в dp ---
# В вашем основном файле bot.py убедитесь, что вы передаете state_storage в Dispatcher
# dp = Dispatcher(storage=MemoryStorage()) # или RedisStorage
# dp.include_router(influencers.router)