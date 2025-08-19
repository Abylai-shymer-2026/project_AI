# app/routers/common.py
from __future__ import annotations

import random
from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery

from ..config import settings
from ..token_store import tokens
from ..keyboards import join_kb, phone_request_kb, remove_kb
from ..formatting import sanitize_html
from ..manager import handle_event
from ..routers.influencers import start_selection  # запуск этапа подбора блогеров

router = Router(name="common")

GREETING = (
    "👋🏻Вас приветствует медиа маркетинговое агентство Nonna Marketing!\n\n"
    "Бот поможет Вам найти подходящих инфлюенсеров для вашей задачи.\n\n"
    "📋Для дальнейшей работы пожалуйста пройдите регистрацию."
)


async def _strict_mode_guard(message: Message) -> bool:
    """Возвращает True, если доступ запрещён в STRICT режиме (и уже отправлено предупреждение)."""
    if settings.START_MODE.lower() == "strict" and not tokens.is_authorized(message.from_user.id):
        text = (
            "🔒 Доступ по персональной ссылке. Пожалуйста, используйте URL, который вам отправил менеджер (@A_bylaikhan)."
        )
        await message.answer(text)
        return True
    return False


@router.message(CommandStart(deep_link=True))
async def start_with_payload(message: Message, command: CommandObject) -> None:
    user_id = message.from_user.id
    payload = (command.args or "").strip()
    token = payload.replace("invite_", "").strip()

    if settings.START_MODE.lower() == "strict":
        if tokens.consume(token, user_id):
            await message.answer(GREETING, reply_markup=join_kb())
            return
        await message.answer(
            "🔒 Доступ по персональной ссылке. Пожалуйста, используйте URL, который вам отправил менеджер (@A_bylaikhan)."
        )
        return

    # dev режим — просто даём доступ
    tokens.grant_for_dev(user_id)
    await message.answer(GREETING, reply_markup=join_kb())


@router.message(CommandStart())
async def start_plain(message: Message) -> None:
    user_id = message.from_user.id
    if settings.START_MODE.lower() == "strict":
        await message.answer(
            "🔒 Доступ по персональной ссылке. Пожалуйста, используйте URL, который вам отправил менеджер (@A_bylaikhan)."
        )
        return
    tokens.grant_for_dev(user_id)
    await message.answer(GREETING, reply_markup=join_kb())


@router.callback_query(F.data == "join")
async def on_join(cb: CallbackQuery) -> None:
    user_id = cb.from_user.id
    if settings.START_MODE.lower() == "strict" and not tokens.is_authorized(user_id):
        await cb.answer("Требуется персональная ссылка. Обратитесь к менеджеру.", show_alert=True)
        return

    # llm-менеджер теперь возвращает три значения
    text, ask_phone, next_action = await handle_event(user_id=user_id, system_event="joined")
    text = sanitize_html(text or "").strip()
    if not text:
        text = random.choice([
            "Здравствуйте! Рады познакомиться.",
            "Привет! Очень рады вас видеть.",
            "Рады знакомству!",
        ])

    # ВАЖНО: edit_text поддерживает только InlineKeyboardMarkup/None.
    await cb.message.edit_text(text)

    # Если нужен запрос телефона — отправляем ОТДЕЛЬНЫМ сообщением с ReplyKeyboardMarkup.
    if ask_phone:
        await cb.message.answer(
            "Можно отправить номер контакта одной кнопкой.",
            reply_markup=phone_request_kb()
        )

    # Если регистрация завершена и нужно начать подбор — запускаем.
    if next_action == "start_selection":
        await start_selection(cb.message)

    await cb.answer()


@router.message(F.contact)
async def on_contact(message: Message) -> None:
    # Строгий режим — проверка доступа
    if settings.START_MODE.lower() == "strict" and not tokens.is_authorized(message.from_user.id):
        await message.answer(
            "🔒 Доступ по персональной ссылке. Пожалуйста, используйте URL, который вам отправил менеджер (@A_bylaikhan)."
        )
        return

    # Передаём телефон в менеджер
    phone = message.contact.phone_number
    text, ask_phone, next_action = await handle_event(
        user_id=message.from_user.id,
        phone=phone,
        system_event="contact",
    )
    text = sanitize_html(text or "").strip()
    if not text:
        text = random.choice([
            "Спасибо! Продолжим.",
            "Благодарю, двигаемся дальше.",
            "Отлично, идём дальше.",
        ])

    # После контакта — убираем клавиатуру
    await message.answer(text, reply_markup=remove_kb())

    # Если регистрация завершена — старт подбора
    if next_action == "start_selection":
        await start_selection(message)


@router.message(F.text)
async def any_text(message: Message) -> None:
    # Строгий режим — проверка доступа
    if settings.START_MODE.lower() == "strict" and not tokens.is_authorized(message.from_user.id):
        await message.answer(
            "🔒 Доступ по персональной ссылке. Пожалуйста, используйте URL, который вам отправил менеджер (@A_bylaikhan)."
        )
        return

    # Передаём текст в менеджер
    text, ask_phone, next_action = await handle_event(
        user_id=message.from_user.id,
        user_text=message.text,
        system_event="message",
    )
    text = sanitize_html(text or "").strip()
    if not text:
        text = random.choice([
            "Продолжим.",
            "Давайте продолжим.",
            "Хорошо, идём дальше.",
        ])

    if ask_phone:
        # Только ReplyKeyboard здесь
        await message.answer(text, reply_markup=phone_request_kb())
    else:
        await message.answer(text)

    # Если регистрация завершена — старт подбора
    if next_action == "start_selection":
        await start_selection(message)
