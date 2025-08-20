# app/keyboards.py
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from typing import List, Optional, Set

# НОВАЯ ФУНКЦИЯ
def join_kb() -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопкой 'Join' для начала регистрации.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Join", callback_data="join")]]
    )

def paginated_multiselect_kb(
    items: List[str],
    callback_prefix: str,
    selected_items: Optional[Set[str]] = None,
    page: int = 0,
    items_per_page: int = 20,
    show_skip: bool = False,
    always_show_done: bool = True,
) -> InlineKeyboardMarkup:
    if selected_items is None:
        selected_items = set()

    start = page * items_per_page
    end = start + items_per_page
    paginated = items[start:end]
    total_pages = (len(items) + items_per_page - 1) // items_per_page

    rows = []
    for it in paginated:
        txt = f"✅ {it}" if it in selected_items else f"☑️ {it}"
        rows.append([InlineKeyboardButton(text=txt, callback_data=f"{callback_prefix}:pick:{it}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{callback_prefix}:page:{page-1}"))
    if end < len(items):
        nav.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"{callback_prefix}:page:{page+1}"))
    if nav:
        rows.append(nav)

    actions = []
    if show_skip:
        actions.append(InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"{callback_prefix}:skip"))
    if always_show_done or selected_items:
        actions.append(InlineKeyboardButton(text="✅ Готово", callback_data=f"{callback_prefix}:done"))
    if actions:
        rows.append(actions)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def phone_request_kb() -> ReplyKeyboardMarkup:
    """Клавиатура для запроса номера телефона."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Нажмите, чтобы поделиться номером",
    )


def remove_kb() -> ReplyKeyboardRemove:
    """Удаляет клавиатуру."""
    return ReplyKeyboardRemove()