# app/ai_logic.py
from __future__ import annotations
import json
import logging
from typing import Any, Dict, Optional

from openai import AsyncOpenAI
from .config import settings
from .formatting import ensure_min_words, sanitize_html

log = logging.getLogger(__name__)

# Используем единый асинхронный клиент OpenAI
client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    timeout=settings.OPENAI_TIMEOUT,
)


def _read_prompt(file_path: str) -> str:
    """Читает текст системного промпта из файла."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        log.error(f"Файл промпта не найден: {file_path}")
        return ""
    except Exception as e:
        log.error(f"Ошибка при чтении файла промпта {file_path}: {e}")
        return ""


# --- Логика для ЭТАПА 1: РЕГИСТРАЦИЯ ---

async def route_user_message_registration(user_text: str, current_step: str) -> Optional[Dict[str, Any]]:
    """
    ИИ-Router для этапа регистрации.
    Анализирует текст пользователя и извлекает данные.
    """
    system_prompt = _read_prompt("app/prompts/router_system_prompt.txt")
    if not system_prompt:
        return None

    user_prompt = f"Current registration step: '{current_step}'. User message: '{user_text}'"

    try:
        log.debug("AI-Router (Регистрация): Отправка запроса...")
        response = await client.chat.completions.create(
            model=settings.REG_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        log.debug(f"AI-Router (Регистрация) | Результат: {result}")
        return result
    except Exception as e:
        log.error(f"AI-Router (Регистрация) | Ошибка: {e}")
        return None


async def generate_assistant_response_registration(state: Dict[str, Any], next_step: str,
                                                   user_question: Optional[str] = None,
                                                   last_assistant_question: Optional[str] = None) -> str:
    """
    ИИ-Responder (Арай) для этапа регистрации.
    Генерирует ответ пользователю.
    """
    system_prompt = _read_prompt("app/prompts/responder_registration_prompt.txt")
    if not system_prompt:
        return "Произошла внутренняя ошибка. Пожалуйста, попробуйте позже."

    input_data = {
        "state": state,
        "next_step": next_step,
        "user_question": user_question,
        "last_assistant_question": last_assistant_question,
        "first_turn": all(value is None for key, value in state.items() if key in REG_FIELDS)
    }

    try:
        log.debug(f"AI-Responder (Регистрация): Отправка запроса для шага '{next_step}'...")
        response = await client.chat.completions.create(
            model=settings.RESPONDER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        result_json = json.loads(response.choices[0].message.content)
        log.debug(f"AI-Responder (Регистрация) | Результат: {result_json}")
        return result_json.get("assistant_text", "Я не совсем поняла, можете повторить?")
    except Exception as e:
        log.error(f"AI-Responder (Регистрация) | Ошибка: {e}")
        return "Извините, у меня возникли технические неполадки. Давайте попробуем чуть позже."


# --- Логика для ЭТАПА 2: ПОДБОР ИНФЛЮЕНСЕРОВ ---

async def generate_text(intent: str, context: Optional[Dict[str, Any]] = None, fallback: Optional[str] = None) -> str:
    """
    Универсальная функция для генерации текста Арай на этапе подбора инфлюенсеров.
    """
    system_prompt = _read_prompt("app/prompts/responder_postreg_prompt.txt")
    if not system_prompt:
        return fallback or "Произошла ошибка, попробуйте позже."

    input_data = {
        "pending_step": intent,
        "user_filters": context or {},
    }

    try:
        log.debug(f"AI-Generator (Подбор): Отправка запроса для интента '{intent}'...")
        response = await client.chat.completions.create(
            model=settings.RESPONDER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        result_json = json.loads(response.choices[0].message.content)
        text = result_json.get("assistant_text")
        log.debug(f"AI-Generator (Подбор) | Результат: {text}")
        if not text:
            raise ValueError("Ответ ИИ не содержит текста")
        return sanitize_html(text)

    except Exception as e:
        log.error(f"AI-Generator (Подбор) | Ошибка: {e}")
        return fallback or "Извините, возникла небольшая проблема. Давайте продолжим."


REG_FIELDS = ("name", "company", "industry", "position", "phone")