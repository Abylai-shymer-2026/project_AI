# app/manager.py
from __future__ import annotations
import time
from typing import Dict, Optional, Tuple, List
from . import llm, sheets
import inspect

Profile = Dict[str, Optional[str]]

_profiles: Dict[int, Profile] = {}
_history: Dict[int, List[Dict[str, str]]] = {}  # [{role, content, ts}]
MEM_LIMIT = 30
MEM_TTL = 7 * 24 * 3600  # 7 дней


def _get_stage(profile: Profile) -> str:
    """registration | postreg"""
    need = [k for k in ("name", "company", "industry", "position", "phone") if not profile.get(k)]
    return "registration" if need else "postreg"


def _current_step(profile: Profile) -> Optional[str]:
    if not profile.get("name"):
        return "name"
    if not profile.get("company"):
        return "company"
    if not profile.get("industry"):
        return "industry"
    if not profile.get("position"):
        return "position"
    if not profile.get("phone"):
        return "phone"
    return None


def get_profile(user_id: int) -> Profile:
    return _profiles.setdefault(
        user_id,
        {
            "name": None, "company": None, "industry": None, "position": None, "phone": None,
            "greeted": False, "saved_to_sheet": False, "last_question": "",
        },
    )


def _hist_add(user_id: int, role: str, content: str) -> None:
    now = int(time.time())
    arr = _history.setdefault(user_id, [])
    arr.append({"role": role, "content": (content or ""), "ts": now})
    cutoff = now - MEM_TTL
    arr[:] = [m for m in arr if m.get("ts", now) >= cutoff]
    if len(arr) > MEM_LIMIT:
        del arr[:-MEM_LIMIT]


def _hist_for_llm(user_id: int) -> List[Dict[str, str]]:
    return [{"role": m["role"], "content": m["content"]} for m in _history.get(user_id, [])[-MEM_LIMIT:]]


async def handle_event(
    user_id: int,
    user_text: Optional[str] = None,
    phone: Optional[str] = None,
    system_event: Optional[str] = None,
) -> Tuple[str, bool, Optional[str]]:
    profile = get_profile(user_id)

    if user_text:
        _hist_add(user_id, "user", user_text)
    if phone and not profile.get("phone"):
        profile["phone"] = phone

    first_turn = not profile.get("greeted")
    if first_turn:
        profile["greeted"] = True

    stage_before = _get_stage(profile)

    route = await llm.router_decide(
        state={k: profile.get(k) for k in ("name", "company", "industry", "position", "phone")},
        stage=stage_before,
        user_text=user_text or "",
        system_event=system_event or "message",
    )

    slots = route.get("slots") or {}
    for k in ("name", "company", "industry", "position", "phone"):
        v = slots.get(k)
        if v and not profile.get(k):
            if k == "name":
                v = v.split()[0].strip()
                if v: v = v[0].upper() + v[1:]
            profile[k] = v

    stage_target = route.get("stage_target") or _get_stage(profile)
    next_step = _current_step(profile) or "done"

    reply = await llm.responder_reply(
        stage=stage_target,
        state={k: profile.get(k) for k in ("name", "company", "industry", "position", "phone")},
        next_step=next_step,
        user_question=route.get("user_question"),
        last_assistant_question=profile.get("last_question") or "",
        first_turn=first_turn,
    )

    # ИЗМЕНЕНИЕ: Добавляем проверку на None, чтобы избежать падения в будущем.
    # Это "защита" на случай, если responder_reply по какой-то причине вернет None.
    if reply is None:
        reply = {"assistant_text": "Одну минуту, обрабатываю ваш запрос...", "ask_phone_button": False}

    text = (reply.get("assistant_text") or "").strip() or "Продолжим. Как называется ваш бизнес и чем вы занимаетесь?"
    ask_phone = bool(reply.get("ask_phone_button"))

    profile["last_question"] = text.strip().split("\n")[-1].strip()

    next_action: Optional[str] = None
    if _current_step(profile) is None and not profile.get("saved_to_sheet"):
        try:
            res = sheets.append_user(profile, tg_id=user_id)
            ok = await res if inspect.isawaitable(res) else bool(res)
            if ok:
                profile["saved_to_sheet"] = True
                next_action = "start_selection"
                # Убедимся, что текст не пустой
                if not text.strip():
                    text = "Спасибо за регистрацию! Перейдём к подбору инфлюенсеров."
            else:
                profile["saved_to_sheet"] = False
        except Exception:
            profile["saved_to_sheet"] = False

    _hist_add(user_id, "assistant", text)

    if next_step != "phone":
        ask_phone = False

    return text, ask_phone, next_action