# app/knowledge.py
import re
from typing import Optional, Dict

COMPANY = {
    "name": "Nonna Marketing",
    "what": "Мы медиа-маркетинговое агентство. Помогаем брендам подбирать и запускать кампании с инфлюенсерами в Казахстане и СНГ.",
    "services": [
        "Подбор инфлюенсеров под задачу и бюджет",
        "Медиаплан и бюджетирование",
        "Договоры, логистика, брифы",
        "Контроль публикаций и аналитика",
        "Оплата и финальная отчётность",
    ],
    "location": "Казахстан (работаем по СНГ)",
}

# простые шаблоны вопросов (регистронезависимые)
_PATTERNS: Dict[str, list[str]] = {
    "who": [r"\bкто вы\b", r"\bкакая вы компания\b", r"\bчто за компания\b", r"\bчем (вы )?занимаетесь\b", r"\bчто вы делаете\b"],
    "process": [r"\bкак вы работаете\b", r"\bпроцесс\b", r"\bэтап(ы|ов)\b", r"\bкак проходит\b"],
    "price": [r"\bцена\b", r"\bстоимост\b", r"\bбюджет\b", r"\bсколько стоит\b"],
    "pay": [r"\bоплат[аи]\b", r"\bплатеж\b", r"\bинвойс\b", r"\bсч[её]т\b"],
    "where": [r"\bгде вы\b", r"\bгде находитесь\b", r"\bгород\b", r"\bстрана\b"],
    "contact": [r"\bменеджер\b", r"\bконтакт\b", r"\bкак связаться\b"],
    # персональные уточнения
    "my_company": [r"\bгде я работаю\b", r"\bкак называется моя компания\b"],
    "my_name": [r"\bкак меня зовут\b", r"\bмо[её] имя\b"],
    "my_position": [r"\bкакая у меня должность\b", r"\bкто я в компании\b"],
}

def _match_any(text: str, pats: list[str]) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in pats)

def answer_from_kb(text: str, profile: dict, manager_contact: str) -> Optional[str]:
    """Возвращает готовый HTML-ответ или None, если ничего не нашли."""
    if _match_any(text, _PATTERNS["who"]):
        services = "• " + "\n• ".join(COMPANY["services"])
        return (
            f"<b>{COMPANY['name']}</b>\n"
            f"{COMPANY['what']}\n\n"
            f"<b>Что делаем:</b>\n{services}"
        )
    if _match_any(text, _PATTERNS["process"]):
        return (
            "<b>Как работаем</b>\n"
            "1) Бриф → цели и аудитория\n"
            "2) Подбор инфлюенсеров и медиаплан\n"
            "3) Согласование бюджета и условий\n"
            "4) Запуск, контроль публикаций\n"
            "5) Отчёт и метрики эффективности"
        )
    if _match_any(text, _PATTERNS["price"]):
        return (
            "<b>Стоимость</b>\n"
            "Зависит от ниши, охватов и состава инфлюенсеров. "
            "Чаще всего стартуют от 300–500K KZT на тест. "
            "После регистрации предложим диапазон под вашу задачу."
        )
    if _match_any(text, _PATTERNS["pay"]):
        return (
            "<b>Оплата</b>\n"
            "Безнал по счёту/инвойсу или по договорённости. Возможна поэтапная оплата по медиаплану."
        )
    if _match_any(text, _PATTERNS["where"]):
        return f"<b>Локация</b>\n{COMPANY['location']}"
    if _match_any(text, _PATTERNS["contact"]):
        return f"<b>Менеджер</b>\nСвязь: {manager_contact}"

    # персональные вопросы на основе профиля
    if _match_any(text, _PATTERNS["my_company"]):
        comp = profile.get("company")
        if comp:
            return f"<b>Ваша компания</b>\n{comp}"
        return "Пока не вижу названия компании — можно подсказать?"
    if _match_any(text, _PATTERNS["my_name"]):
        nm = profile.get("name")
        return f"<b>Ваше имя</b>\n{nm}" if nm else "Пока не записали имя — как к вам обращаться?"
    if _match_any(text, _PATTERNS["my_position"]):
        pos = profile.get("position")
        return f"<b>Ваша должность</b>\n{pos}" if pos else "Пока не записали должность — подскажете?"

    return None
