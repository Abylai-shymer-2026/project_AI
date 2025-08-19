# app/routers/common.py
from __future__ import annotations

from aiogram import Router, F
from aiogram.enums import ChatAction
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery

from ..config import settings
from ..token_store import tokens
from ..keyboards import join_kb, phone_request_kb, remove_kb
from ..formatting import sanitize_html
from ..manager import handle_event
from ..routers.influencers import start_selection  # запуск этапа подбора блогеров

router = Router(name="common")

# УБРАЛИ КОНСТАНТУ GREETING

@router.message(CommandStart(deep_link=True))
async def start_with_payload(message: Message, command: CommandObject) -> None:
    user_id = message.from_user.id
    payload = (command.args or "").strip()
    token = payload.replace("invite_", "").strip()

    if settings.START_MODE.lower() == "strict":
        if tokens.consume(token, user_id):
            # Сразу отправляем на регистрацию
            await message.answer("Для начала работы, пожалуйста, пройдите короткую регистрацию.", reply_markup=join_kb())
            return
        await message.answer(
            "🔒 Доступ по персональной ссылке. Пожалуйста, используйте URL, который вам отправил менеджер (@A_bylaikhan)."
        )
        return

    # dev режим — просто даём доступ
    tokens.grant_for_dev(user_id)
    await message.answer("Для начала работы, пожалуйста, пройдите короткую регистрацию.", reply_markup=join_kb())


@router.message(CommandStart())
async def start_plain(message: Message) -> None:
    user_id = message.from_user.id
    if settings.START_MODE.lower() == "strict":
        await message.answer(
            "🔒 Доступ по персональной ссылке. Пожалуйста, используйте URL, который вам отправил менеджер (@A_bylaikhan)."
        )
        return
    tokens.grant_for_dev(user_id)
    await message.answer("Для начала работы, пожалуйста, пройдите короткую регистрацию.", reply_markup=join_kb())


@router.callback_query(F.data == "join")
async def on_join(cb: CallbackQuery) -> None:
    user_id = cb.from_user.id
    if settings.START_MODE.lower() == "strict" and not tokens.is_authorized(user_id):
        await cb.answer("Требуется персональная ссылка. Обратитесь к менеджеру.", show_alert=True)
        return

    # ДОБАВЛЯЕМ "TYPING..."
    await cb.message.bot.send_chat_action(cb.from_user.id, action=ChatAction.TYPING)

    # llm-менеджер теперь сгенерирует уникальное приветствие
    text, ask_phone, next_action = await handle_event(user_id=user_id, system_event="joined")
    text = sanitize_html(text or "").strip() or "Здравствуйте! Давайте начнем. Как я могу к вам обращаться?"

    # Убираем старую кнопку "Join" и отправляем первое сообщение от ИИ
    await cb.message.edit_text(text)

    if ask_phone:
        await cb.message.answer(
            "Можно отправить номер контакта одной кнопкой.",
            reply_markup=phone_request_kb()
        )

    if next_action == "start_selection":
        await start_selection(cb.message)

    await cb.answer()


@router.message(F.contact)
async def on_contact(message: Message) -> None:
    if settings.START_MODE.lower() == "strict" and not tokens.is_authorized(message.from_user.id):
        await message.answer(
            "🔒 Доступ по персональной ссылке. Пожалуйста, используйте URL, который вам отправил менеджер (@A_bylaikhan)."
        )
        return

    # ДОБАВЛЯЕМ "TYPING..."
    await message.bot.send_chat_action(message.from_user.id, action=ChatAction.TYPING)

    phone = message.contact.phone_number
    text, ask_phone, next_action = await handle_event(
        user_id=message.from_user.id,
        phone=phone,
        system_event="contact",
    )
    text = sanitize_html(text or "").strip() or "Спасибо! Продолжим."

    await message.answer(text, reply_markup=remove_kb())

    if next_action == "start_selection":
        await start_selection(message)


@router.message(F.text)
async def any_text(message: Message) -> None:
    if settings.START_MODE.lower() == "strict" and not tokens.is_authorized(message.from_user.id):
        await message.answer(
            "🔒 Доступ по персональной ссылке. Пожалуйста, используйте URL, который вам отправил менеджер (@A_bylaikhan)."
        )
        return

    # ДОБАВЛЯЕМ "TYPING..."
    await message.bot.send_chat_action(message.from_user.id, action=ChatAction.TYPING)

    text, ask_phone, next_action = await handle_event(
        user_id=message.from_user.id,
        user_text=message.text,
        system_event="message",
    )
    text = sanitize_html(text or "").strip() or "Продолжим."

    reply_markup = phone_request_kb() if ask_phone else None
    await message.answer(text, reply_markup=reply_markup)

    if next_action == "start_selection":
        await start_selection(message)