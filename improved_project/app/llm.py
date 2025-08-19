# app/llm.py
from __future__ import annotations
import asyncio
import json
import os
from typing import Dict, List, Optional, Tuple, Any

from openai import OpenAI
from .config import settings

# ===================== OpenAI client =====================

def _client() -> Optional[OpenAI]:
    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        return None
    return OpenAI(api_key=api_key)

def _needs_reasoning_params(model_name: str) -> bool:
    m = (model_name or "").lower()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


# ===================== File prompt cache =====================

_PROMPT_CACHE: Dict[str, Tuple[float, str]] = {}  # path -> (mtime, content)

def _read_file_cached(path: str) -> str:
    try:
        st = os.stat(path)
        mtime = st.st_mtime
        cached = _PROMPT_CACHE.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        _PROMPT_CACHE[path] = (mtime, content)
        return content
    except Exception:
        return ""


def _get_prompt_from_path(default_path_env: str) -> str:
    path = getattr(settings, default_path_env, "")
    return (_read_file_cached(path) if path else "").strip()


# ===================== Chat wrapper =====================

async def _chat(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: float = 0.6,
    max_tokens: int = 700,
    response_format: Optional[Dict[str, Any]] = None,
) -> str:
    client = _client()
    if client is None:
        return json.dumps({"assistant_text": "⚙️ ИИ не настроен: добавьте OPENAI_API_KEY в .env."})

    mdl = (model or getattr(settings, "RESPONDER_MODEL", "gpt-4o-mini")).strip()
    base_kwargs: Dict[str, Any] = dict(model=mdl, messages=messages, top_p=1.0)
    if response_format:
        base_kwargs["response_format"] = response_format

    if _needs_reasoning_params(mdl):
        base_kwargs["extra_body"] = {"max_completion_tokens": max_tokens}
    else:
        base_kwargs["temperature"] = temperature
        base_kwargs["max_tokens"] = max_tokens

    try:
        resp = await asyncio.to_thread(lambda: client.chat.completions.create(**base_kwargs))
        text = (resp.choices[0].message.content or "").strip()
        return text or "[no-content]"
    except Exception as e:
        print(f"ERROR: OpenAI API call failed: {e}")
        return json.dumps({"assistant_text": "Произошла ошибка при обращении к ИИ. Пожалуйста, попробуйте еще раз позже."})

# ===================== Registration: Router + Responder =====================

async def router_decide(**kwargs) -> Dict[str, Any]:
    sys_prompt = _get_prompt_from_path("ROUTER_PROMPT_PATH")
    payload = {
        "state": kwargs.get("state"), "stage": kwargs.get("stage"),
        "user_text": kwargs.get("user_text", ""), "system_event": kwargs.get("system_event", "message"),
    }
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    raw = await _chat(messages, model=settings.REG_MODEL, temperature=0.2, max_tokens=settings.REG_MAX_TOKENS, response_format={"type": "json_object"})
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"slots": {}, "user_question": kwargs.get("user_text"), "stage_target": "registration"}

async def responder_reply(**kwargs) -> Dict[str, Any]:
    sys_prompt = _get_prompt_from_path("RESPONDER_REG_PROMPT_PATH")
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": json.dumps(kwargs, ensure_ascii=False)}]
    raw = await _chat(messages, model=settings.RESPONDER_MODEL, temperature=0.4, max_tokens=600, response_format={"type": "json_object"})
    try:
        data = json.loads(raw)
        data.setdefault("ask_phone_button", False)
        return data
    except json.JSONDecodeError:
        return {"assistant_text": "Продолжим. Как вас зовут?", "ask_phone_button": False}


# ===================== Post-Registration: Router + Responder =====================

async def postreg_router_decide(**kwargs) -> dict:
    sys_prompt = _get_prompt_from_path("ROUTER_POSTREG_PROMPT_PATH")
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": json.dumps(kwargs, ensure_ascii=False)}]
    raw = await _chat(messages, model=settings.RESPONDER_MODEL, temperature=0.2, max_tokens=500, response_format={"type": "json_object"})
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"intent": "other", "updates": {}, "next_step": kwargs.get("pending_step")}

async def postreg_responder_reply(**kwargs) -> dict:
    sys_prompt = _get_prompt_from_path("RESPONDER_POSTREG_PROMPT_PATH")
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": json.dumps(kwargs, ensure_ascii=False)}]
    raw = await _chat(messages, model=settings.RESPONDER_MODEL, temperature=0.4, max_tokens=520, response_format={"type": "json_object"})
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"assistant_text": "Давайте продолжим подбор. С какого города начнем?"}