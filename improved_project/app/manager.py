# app/manager.py
from __future__ import annotations
import asyncio
import logging
from typing import Dict, Optional, Tuple

from aiogram.fsm.context import FSMContext

from . import sheets
from .ai_logic import route_user_message_registration, generate_assistant_response_registration

log = logging.getLogger(__name__)

Profile = Dict[str, Optional[str]]
REG_FIELDS = ("name", "company", "industry", "position", "phone")


async def _current_step(state: FSMContext) -> Optional[str]:
    """Определяет текущий шаг регистрации, проверяя данные в FSM."""
    user_data = await state.get_data()
    for field in REG_FIELDS:
        if field not in user_data:
            return field
    return None


async def handle_event(
        user_id: int,
        state_obj: FSMContext,
        user_text: Optional[str] = None,
        contact_phone: Optional[str] = None
) -> Tuple[str, bool, Optional[str]]:
    step = await _current_step(state_obj)
    user_question = None

    if contact_phone:
        await state_obj.update_data(phone=contact_phone)
        step = await _current_step(state_obj)


    elif user_text and step:
        # Попробуем ИИ-роутер для автозаполнения слотов и выявления вопросов
        try:
            routed = await route_user_message_registration(user_text=user_text, current_step=step)
        except Exception:
            routed = None

        if routed and isinstance(routed, dict):
            slots = routed.get("slots") or {}
            updates = {k: v for k, v in slots.items() if k in REG_FIELDS and v}
            if updates:
                await state_obj.update_data(**updates)
            user_question = routed.get("user_question") or None
        else:
            # Фолбэк: прежняя логика для телефона
            is_text_for_phone_step = (step == "phone")
            if is_text_for_phone_step:
                import re
                digits = re.sub(r"\D+", "", user_text)
                if digits:
                    await state_obj.update_data(phone=digits)
                    user_question = None
                else:
                    user_question = user_text
            else:
                user_question = user_text

        step = await _current_step(state_obj)

    user_data = await state_obj.get_data()

    if not step:
        log.debug("Все поля регистрации заполнены. Проверяем сохранение в Google Sheets.")
        if not user_data.get("saved_to_sheet"):
            await state_obj.bot.send_message(user_id, "Спасибо за регистрацию! ✨ Одну минуту, сохраняю ваш профиль...")

            # --- ДИАГНОСТИЧЕСКОЕ ЛОГИРОВАНИЕ ---
            log.info(f"Попытка записи в Google Sheets для tg_id={user_id}. Данные: {user_data}")
            ok = False # Изначально считаем, что запись не удалась
            try:
                # Запускаем синхронную функцию в отдельном потоке
                ok = await asyncio.to_thread(sheets.append_user, user_data, tg_id=user_id)
            except Exception as e:
                log.critical(f"Критическая ошибка ПРИ ВЫЗОВЕ asyncio.to_thread для sheets.append_user: {e}", exc_info=True)


            if ok:
                log.info(f"ЗАПИСЬ УСПЕШНА для tg_id={user_id}.")
                await state_obj.update_data(saved_to_sheet=True)
                # Важно: возвращаем пустую строку, чтобы бот ничего не писал после "сохраняю ваш профиль"
                return "", False, "start_selection"
            else:
                # Если ok == False, значит, была ошибка внутри sheets.append_user
                log.error(f"ЗАПИСЬ НЕ УДАЛАСЬ для tg_id={user_id}. Функция sheets.append_user вернула False.")
                return "К сожалению, произошла ошибка при сохранении вашего профиля. Пожалуйста, попробуйте связаться с менеджером.", False, None
        else:
            # Пользователь уже сохранен, просто переходим дальше
            log.info(f"Пользователь tg_id={user_id} уже был сохранен. Переход к выбору.")
            return "", False, "start_selection"

    assistant_text = await generate_assistant_response_registration(
        state=user_data,
        next_step=step,
        user_question=user_question,
        last_assistant_question=user_data.get("last_question")
    )

    await state_obj.update_data(last_question=assistant_text)
    ask_phone = (step == "phone")

    return assistant_text, ask_phone, None