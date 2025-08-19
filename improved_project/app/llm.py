# app/llm.py
from __future__ import annotations
import asyncio
import json
import os
import random
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


def _get_prompt_from_path(default_path_env: str, fallback_text: str) -> str:
    path = getattr(settings, default_path_env, None)
    if not path:
        # sensible defaults
        if default_path_env == "ROUTER_PROMPT_PATH":
            path = "app/prompts/router_system_prompt.txt"
        elif default_path_env == "RESPONDER_REG_PROMPT_PATH":
            path = "app/prompts/responder_registration_prompt.txt"
        else:
            path = ""
    content = _read_file_cached(path) if path else ""
    return (content.strip() or fallback_text.strip())


# ===================== Chat wrapper (handles gpt-5/o*) =====================

async def _chat(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: float = 0.6,
    max_tokens: int = 700,
    response_format: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Universal Chat Completions call:
    - Regular models → pass temperature & max_tokens
    - gpt-5*/o* → don't pass temperature; limit via extra_body.max_completion_tokens
    - If response_format provided (e.g., {"type":"json_object"}), forward it.
    - Never return empty string: returns "[no-content]" if needed.
    """
    client = _client()
    if client is None:
        return "⚙️ ИИ не настроен: добавьте OPENAI_API_KEY в .env (и перезапустите бота)."

    mdl = (model or getattr(settings, "RESPONDER_MODEL", "gpt-4o-mini")).strip()

    def _sync_create():
        base_kwargs: Dict[str, Any] = dict(
            model=mdl,
            messages=messages,
            top_p=1.0,
        )
        if response_format:
            base_kwargs["response_format"] = response_format

        if _needs_reasoning_params(mdl):
            base_kwargs["extra_body"] = {"max_completion_tokens": max_tokens}
        else:
            base_kwargs["temperature"] = temperature
            base_kwargs["max_tokens"] = max_tokens

        try:
            return client.chat.completions.create(**base_kwargs)
        except Exception as e:
            msg = str(e)
            # Retry guidance for reasoning families / params mismatch:
            if "max_tokens" in msg and "max_completion_tokens" in msg:
                base_kwargs.pop("max_tokens", None)
                eb = base_kwargs.get("extra_body") or {}
                eb["max_completion_tokens"] = max_tokens
                base_kwargs["extra_body"] = eb
                base_kwargs.pop("temperature", None)
                return client.chat.completions.create(**base_kwargs)
            if "Unsupported value: 'temperature'" in msg:
                base_kwargs.pop("temperature", None)
                return client.chat.completions.create(**base_kwargs)
            raise

    resp = await asyncio.to_thread(_sync_create)
    text = (resp.choices[0].message.content or "").strip()
    return text or "[no-content]"


# ===================== System prompts (fallbacks) =====================

_ROUTER_FALLBACK = """
You are the Router. Your role is not to answer user questions directly, but to decide what should happen next in the conversation and route the input to the correct system.

Your responsibilities:
1. **Registration Flow Tracking**
   - You must track which registration step the user is on (slots: name, company, industry, position, phone).
   - If the user gives a valid answer for the current slot, mark it as filled and advance to the next step.
   - If the user gives an irrelevant or empty answer, instruct the ManagerLLM to re-ask that specific question.
   - If the user already answered a slot, do NOT re-ask; move forward.

2. **Question Handling**
   - If the user asks a question (instead of answering), route it to ResponderLLM.
   - After ResponderLLM answers, continue registration from the exact next pending step.
   - Do not lose previously collected answers. The flow must resume smoothly.

3. **Context Awareness**
   - Normalize user answers where possible. Example:
     - "cafe", "fast food", "restaurant chain" → interpret as "restaurant business".
   - Do not be strict with wording. If an answer is interpretable as valid, accept it.
   - Only reject if the input is nonsense, irrelevant (e.g., “banana”, “lol”), or empty.

4. **State Management**
   - Maintain a memory of the last 30 messages per user, stored for 7 days, then cleared.
   - Ensure continuity across turns. The user must feel the assistant remembers their context.

5. **Routing Rules**
   - ManagerLLM = guides through registration steps, organizes slots, keeps structure.
   - ResponderLLM = answers any free-form user questions during or after registration.
   - Router = decides which LLM should handle the input.

6. **Tone and Behavior**
   - You are invisible to the user; you never speak directly.
   - You only produce routing decisions and slot updates.
   - Your outputs must be structured and machine-readable (JSON format).

---

### Output format (always JSON):
```json
{
  "action": "route",
  "target": "ManagerLLM",
  "reason": "User provided company name, valid slot value"
}

"""

_RESPONDER_REG_FALLBACK = """
You are Aray, a professional marketing manager assistant with a warm, human personality. You are not a bot, but a person who speaks naturally, shows empathy, and keeps conversations engaging. Your task is to guide users through a registration process step by step (name, company name, industry/field, position, contact number).

Rules:
- Be polite and friendly.
- Keep the conversation engaging and interesting.
- Always respond in 35–40 words in Russian. Do not shorten or lengthen beyond this range.
- Accept any reasonable input as a valid answer. If the user says "café", "food", or "fast food chain", normalize it into "restaurant business" or "public catering" and save in the industry slot.
- Do not repeat a question if the answer can be interpreted as valid. Only ask again if the answer is empty, meaningless, or irrelevant.
- If the user asks a question instead of answering, route it to the ResponderLLM. After ResponderLLM gives the answer, continue registration from the exact next step without restarting.
- Never loop on the same question. If a slot is already filled, move forward logically.
- Use a warm, friendly, and human-like tone. For example, include light empathy and natural small touches ("I see, that makes sense", "That’s interesting").
- Remember: Your role is to smoothly complete registration, not to sound robotic or restricted.
- About the company: Nonna Marketing provides a full range of marketing and PR services. We work with bloggers on both commercial and barter basis. If the user asks about services, respond with this context.
- If the user asks something outside your knowledge, politely say: "Please ask the manager @A_bylaikhan for details."

Вход (строгий JSON):
{

Выход (строгий JSON):
{
  "assistant_text": "строка; закончить одним вопросом",
  "ask_phone_button": false|true
}
Только JSON. Никаких пояснений.
"""


# ===================== Router (always-on) =====================

async def router_decide(
    *,
    state: Dict[str, Optional[str]],
    stage: str,                         # "registration" | "postreg"
    user_text: str,
    system_event: str = "message",
    model: Optional[str] = None,
    max_tokens: int = 500,
) -> Dict[str, Any]:
    """
    Всегда первый шаг. Понимает, что пришло (вопрос/данные/оба), какие слоты извлечь,
    нужно ли двигаться дальше и не завершилась ли регистрация.
    """
    sys_prompt = _get_prompt_from_path(
        "ROUTER_PROMPT_PATH",
        _ROUTER_FALLBACK,
    )

    payload = {
        "state": {
            "name": state.get("name"),
            "company": state.get("company"),
            "industry": state.get("industry"),
            "position": state.get("position"),
            "phone": state.get("phone"),
        },
        "stage": stage,
        "user_text": (user_text or "").strip(),
        "system_event": system_event or "message",
    }

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]

    raw = await _chat(
        messages,
        model=model or getattr(settings, "ROUTER_MODEL", getattr(settings, "RESPONDER_MODEL", "gpt-4o-mini")),
        temperature=0.2,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )

    try:
        data = json.loads(raw)
    except Exception:
        data = {
            "intent": "chitchat",
            "slots": {"name": None, "company": None, "industry": None, "position": None, "phone": None},
            "advance": False,
            "next_step": "company",
            "stage_target": stage,
            "user_question": None,
        }

    # normalize
    data.setdefault("intent", "chitchat")
    data.setdefault("slots", {})
    data.setdefault("advance", False)
    data.setdefault("next_step", "company")
    data.setdefault("stage_target", stage)
    data.setdefault("user_question", None)

    slots = {}
    for k in ("name", "company", "industry", "position", "phone"):
        v = data["slots"].get(k, None)
        slots[k] = (str(v).strip() if isinstance(v, str) and v.strip() else None)
    data["slots"] = slots

    if data["next_step"] not in {"name","company","industry","position","phone","done"}:
        data["next_step"] = "company"
    if data["stage_target"] not in {"registration","postreg"}:
        data["stage_target"] = stage

    return data


# ===================== Responder (stage-aware; now registration only) =====================

async def responder_reply(
    *,
    stage: str,                          # "registration" | "postreg"
    state: Dict[str, Optional[str]],
    next_step: str,                      # from router
    user_question: Optional[str],        # from router
    last_assistant_question: str = "",
    first_turn: bool = False,
    model_reg: Optional[str] = None,
    model_post: Optional[str] = None,
    max_tokens: int = 600,
) -> Dict[str, Any]:
    """
    Формирует человекоподобный ответ пользователю.
    Пока реализован режим регистрации (stage='registration').
    Для postreg оставлен fallback.
    """
    if stage == "registration":
        sys_prompt = _get_prompt_from_path(
            "RESPONDER_REG_PROMPT_PATH",
            _RESPONDER_REG_FALLBACK,
        )
        payload = {
            "state": {
                "name": state.get("name"),
                "company": state.get("company"),
                "industry": state.get("industry"),
                "position": state.get("position"),
                "phone": state.get("phone"),
            },
            "next_step": next_step,
            "user_question": user_question,
            "last_assistant_question": (last_assistant_question or "").strip(),
            "first_turn": bool(first_turn),
            "length_hints": {"general": "30-40", "answer": "20-25"},
        }
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        raw = await _chat(
            messages,
            model=model_reg or getattr(settings, "RESPONDER_MODEL_REG", getattr(settings, "RESPONDER_MODEL", "gpt-4o-mini")),
            temperature=0.4,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            data = json.loads(raw)
        except Exception:
            data = {
                "assistant_text": random.choice([
                    "Давайте продолжим. Поделитесь, пожалуйста, как называется ваш бизнес и чем он занимается?",
                    "Расскажите, как называется ваш бизнес и в какой сфере он работает?",
                    "Чтобы двигаться дальше, подскажите название и направление вашего бизнеса.",
                ]),
                "ask_phone_button": False,
            }
        data.setdefault("assistant_text", "")
        data.setdefault("ask_phone_button", False)
        if not str(data["assistant_text"]).strip():
            data["assistant_text"] = random.choice([
                "Продолжим. Как называется ваш бизнес и чем вы занимаетесь?",
                "Давайте продолжим — расскажите, как называется ваша компания и что вы делаете?",
                "Чтобы помочь, подскажите название и сферу деятельности вашего бизнеса.",
            ])
        # ask_phone_button — только если шаг phone
        if next_step != "phone":
            data["ask_phone_button"] = False
        return data


# --------- POST-REG: influencer selection (LLM-driven) ---------

_POSTREG_ROUTER_FB = "Produce STRICT JSON with keys: intent, updates, next_step."
_POSTREG_RESP_FB = "Produce STRICT JSON with keys: assistant_text, ask_buttons."

def _get_postreg_router_prompt() -> str:
    path = getattr(settings, "ROUTER_POSTREG_PROMPT_PATH", "app/prompts/router_postreg_prompt.txt")
    return (_read_file_cached(path) or _POSTREG_ROUTER_FB).strip()

def _get_postreg_responder_prompt() -> str:
    path = getattr(settings, "RESPONDER_POSTREG_PROMPT_PATH", "app/prompts/responder_postreg_prompt.txt")
    return (_read_file_cached(path) or _POSTREG_RESP_FB).strip()


async def postreg_router_decide(
    *,
    filters: dict,
    user_text: str,
    user_event: str,              # "message" | "button"
    pending_step: str,            # "cities|topics|age_range|followers_range|language|done"
    cities_from_db: list[str],
    model: str | None = None,
    max_tokens: int = 500,
) -> dict:
    sys_prompt = _get_postreg_router_prompt()
    payload = {
        "filters": filters,
        "user_text": (user_text or "").strip(),
        "user_event": user_event,
        "pending_step": pending_step,
        "cities_from_db": cities_from_db,
    }
    msgs = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    raw = await _chat(
        msgs,
        model=model or getattr(settings, "ROUTER_MODEL", getattr(settings, "RESPONDER_MODEL", "gpt-4o-mini")),
        temperature=0.2,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    try:
        data = json.loads(raw)
    except Exception:
        data = {"intent": "other", "updates": {}, "next_step": pending_step}
    data.setdefault("intent", "other")
    data.setdefault("updates", {})
    data.setdefault("next_step", pending_step)
    return data


async def postreg_responder_reply(
    *,
    state: dict,                   # {"filters": {...}, "pending_step": "..."}
    user_question: str | None,     # если router увидел вопрос
    model: str | None = None,
    max_tokens: int = 520,
) -> dict:
    sys_prompt = _get_postreg_responder_prompt()
    payload = {
        "filters": state.get("filters") or {},
        "pending_step": state.get("pending_step") or "cities",
        "user_question": user_question,
        "last_assistant_question": "",
        "first_turn": False,
    }
    msgs = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    raw = await _chat(
        msgs,
        model=model or getattr(settings, "RESPONDER_MODEL", "gpt-4o-mini"),
        temperature=0.4,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    try:
        data = json.loads(raw)
    except Exception:
        data = {"assistant_text": "Продолжим отбор. Для начала выберите города.", "ask_buttons": "cities"}
    data.setdefault("assistant_text", "Продолжим отбор. Для начала выберите города.")
    data.setdefault("ask_buttons", "none")
    return data
