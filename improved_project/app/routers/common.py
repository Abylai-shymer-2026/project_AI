# app/routers/common.py
from __future__ import annotations

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from ..config import settings
from ..token_store import tokens
from ..keyboards import remove_kb, phone_request_kb
from ..formatting import sanitize_html, ensure_min_words
from ..manager import handle_event

# Создаём реальный Router здесь, без самоссылочного импорта
router = Router(name="common")


async def _start_selection_lazy(message: Message, state: FSMContext):
    # Ленивый импорт, чтобы исключить любые циклы импорта между routers/*.py
    from .influencers import start_selection
    await start_selection(message, state)


@router.message(F.text)
async def on_user_text(message: Message, state: FSMContext):
    # strict: работаем только с авторизованными по URL
    if settings.START_MODE.lower() == "strict" and not tokens.is_authorized(message.from_user.id):
        return

    # Сохраняем технические данные пользователя в FSM для записи в Sheets
    try:
        await state.update_data(tg_username=(message.from_user.username or ""))
    except Exception:
        pass

    text, ask_phone, next_action = await handle_event(
        user_id=message.from_user.id,
        user_text=(message.text or "").strip(),
        state_obj=state,
    )

    if text:
        if ask_phone:
            await message.answer(ensure_min_words(sanitize_html(text)), reply_markup=phone_request_kb())
        else:
            await message.answer(ensure_min_words(sanitize_html(text)))

    if next_action == "start_selection":
        await _start_selection_lazy(message, state)


@router.message(F.contact)
async def on_contact(message: Message, state: FSMContext):
    if settings.START_MODE.lower() == "strict" and not tokens.is_authorized(message.from_user.id):
        return

    phone = message.contact.phone_number if message.contact else None
    if not phone:
        await message.answer("Не удалось прочитать номер. Можете отправить его текстом?")
        return

    try:
        await state.update_data(tg_username=(message.from_user.username or ""))
    except Exception:
        pass

    text, ask_phone, next_action = await handle_event(
        user_id=message.from_user.id,
        user_text=None,
        contact_phone=phone,
        state_obj=state,
    )

    if text:
        await message.answer(ensure_min_words(sanitize_html(text)), reply_markup=remove_kb())

    if next_action == "start_selection":
        await _start_selection_lazy(message, state)
