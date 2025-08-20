# app/routers/influencers.py
from __future__ import annotations

import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from typing import Set, List, Optional
import re

from ..states import SelectionBasicStates, SelectionDecisionStates, SelectionAdvancedStates
from ..keyboards import paginated_multiselect_kb, results_nav_kb, result_item_kb
from ..influencers import list_cities, list_topics, parse_age_range, query_influencers, paginate
from ..config import settings
from ..influencers import export_pdf, export_excel
from aiogram.types import BufferedInputFile
from .. import sheets as gs
from ..formatting import ensure_min_words

router = Router(name="influencer_selection")

CITIES_LIMIT = 25
TOPICS_LIMIT = 10

# ===== helpers =====

def _infer_gender_from_text(text: str) -> Optional[str]:
    t = text.lower()
    if any(w in t for w in ["жен", "девушка", "она"]):
        return "ж"
    if any(w in t for w in ["муж", "парень", "он"]):
        return "м"
    return None

def _age_is_ambiguous(text: str) -> bool:
    # «24» — неясно: ровно/до/от/диапазон
    return bool(re.fullmatch(r"\d{1,2}", text.strip()))

def _ask_age_clarify(msg: Message):
    kb = paginated_multiselect_kb(
        items=["Ровно", "До", "От", "Диапазон 20–24"],
        callback_prefix="ageclar",
        items_per_page=20,
        always_show_done=False,
    )
    return msg.answer(
        ensure_min_words("Вы указали «24». Уточните: ровно 24, до 24, от 24, или диапазон 20–24?"),
        reply_markup=kb
    )

# ===== entrypoint =====

async def start_selection(message: Message, state: FSMContext):
    # города (обязательный мультивыбор)
    await state.set_state(SelectionBasicStates.cities)
    cities = list_cities(limit=CITIES_LIMIT)
    await state.update_data(sel_cities=set(), cities_page=0)
    await message.answer(
        ensure_min_words("Супер! Начнём с городов. Можно выбрать несколько — галочка появится рядом."),
        reply_markup=paginated_multiselect_kb(
            cities, "city", selected_items=set(), page=0, items_per_page=10, show_skip=False, always_show_done=True
        ),
    )

# ===== cities =====

@router.callback_query(SelectionBasicStates.cities, F.data.startswith("city:"))
async def on_city(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: Set[str] = set(data.get("sel_cities") or [])
    page = int(data.get("cities_page") or 0)
    cities = list_cities(limit=CITIES_LIMIT)

    _, action, value = cb.data.split(":", 2)
    if action == "pick":
        if value in selected:
            selected.remove(value)
        else:
            selected.add(value)
        await state.update_data(sel_cities=selected)
    elif action == "page":
        page = max(0, int(value))
        await state.update_data(cities_page=page)
    elif action == "done":
        if not selected:
            await cb.answer("Нужно выбрать хотя бы один город", show_alert=True)
        else:
            # Переходим к тематикам
            await state.set_state(SelectionBasicStates.topics)
            await state.update_data(sel_topics=set(), topics_page=0)
            topics = list_topics(limit=TOPICS_LIMIT)
            await cb.message.edit_text(
                ensure_min_words("Отличный выбор городов! Теперь тематики — тоже можно несколько."),
                reply_markup=paginated_multiselect_kb(
                    topics, "topic", selected_items=set(), page=0, items_per_page=10, show_skip=False, always_show_done=True
                ),
            )
            await cb.answer()
            return
    # re-render
    await cb.message.edit_reply_markup(
        reply_markup=paginated_multiselect_kb(
            cities, "city", selected_items=selected, page=page, items_per_page=10, show_skip=False, always_show_done=True
        )
    )
    await cb.answer()

# ===== topics =====

@router.callback_query(SelectionBasicStates.topics, F.data.startswith("topic:"))
async def on_topic(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: Set[str] = set(data.get("sel_topics") or [])
    page = int(data.get("topics_page") or 0)
    topics = list_topics(limit=TOPICS_LIMIT)

    _, action, value = cb.data.split(":", 2)
    if action == "pick":
        if value in selected:
            selected.remove(value)
        else:
            selected.add(value)
        await state.update_data(sel_topics=selected)
    elif action == "page":
        page = max(0, int(value))
        await state.update_data(topics_page=page)
    elif action == "done":
        if not selected:
            await cb.answer("Нужно выбрать хотя бы одну тематику", show_alert=True)
        else:
            # Переходим к возрасту (optional)
            await state.set_state(SelectionBasicStates.age)
            await cb.message.edit_text(
                ensure_min_words("Какой возраст блогеров предпочтителен? Можно написать диапазон (например, 20-24) или оставить пустым."),
                reply_markup=None
            )
            await cb.answer()
            return

    await cb.message.edit_reply_markup(
        reply_markup=paginated_multiselect_kb(
            topics, "topic", selected_items=selected, page=page, items_per_page=10, show_skip=False, always_show_done=True
        )
    )
    await cb.answer()

# ===== age (optional, с уточнением «24») =====

@router.message(SelectionBasicStates.age, F.text)
async def on_age_text(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    if not text:
        await state.update_data(age_text=None)
    else:
        if _age_is_ambiguous(text):
            await state.update_data(pending_age=text)
            await _ask_age_clarify(msg)
            return
        await state.update_data(age_text=text)

    # Переходим к языку
    await state.set_state(SelectionBasicStates.language)
    kb = paginated_multiselect_kb(
        items=["Казахский", "Русский", "Двуязычный", "Пропустить"],
        callback_prefix="lang",
        items_per_page=4,
        always_show_done=False
    )
    await msg.answer(ensure_min_words("Какой язык контента желателен? Выберите один вариант или «Пропустить»."), reply_markup=kb)

@router.callback_query(F.data.startswith("ageclar:"))
async def on_age_clarify(cb: CallbackQuery, state: FSMContext):
    choice = cb.data.split(":", 2)[2]
    base = (await state.get_data()).get("pending_age") or "24"
    mapping = {
        "Ровно": base,
        "До": f"<= {base}",
        "От": f">= {base}",
        "Диапазон 20–24": "20-24",
    }
    await state.update_data(age_text=mapping.get(choice, base), pending_age=None)
    await cb.message.edit_reply_markup(None)
    # дальше спросим язык
    await state.set_state(SelectionBasicStates.language)
    kb = paginated_multiselect_kb(
        items=["Казахский", "Русский", "Двуязычный", "Пропустить"],
        callback_prefix="lang",
        items_per_page=4,
        always_show_done=False
    )
    await cb.message.answer(ensure_min_words("Понял возраст. Теперь язык контента?"), reply_markup=kb)
    await cb.answer()

# ===== language (buttons) =====

@router.callback_query(SelectionBasicStates.language, F.data.startswith("lang:"))
async def on_language(cb: CallbackQuery, state: FSMContext):
    choice = cb.data.split(":", 2)[2]
    language = None if choice == "Пропустить" else choice
    await state.update_data(language=language)

    # Пол попытаемся определить из текста пользователя дальше, но сейчас спрашивать не будем.
    await state.update_data(gender=None)
    # Переходим к решению: Advanced / Показать результат
    await state.set_state(SelectionDecisionStates.decide)
    kb = paginated_multiselect_kb(
        items=["Advanced", "Показать результат"],
        callback_prefix="decide",
        items_per_page=2,
        always_show_done=False
    )
    await cb.message.edit_text(
        ensure_min_words("Хочешь добавить точные фильтры (семейное положение, подписчики, форматы, бюджет) или сразу показать результат?"),
        reply_markup=kb
    )
    await cb.answer()

# ===== decision =====

@router.callback_query(SelectionDecisionStates.decide, F.data.startswith("decide:"))
async def on_decide(cb: CallbackQuery, state: FSMContext):
    action = cb.data.split(":", 2)[2]
    if action == "Advanced":
        await state.set_state(SelectionAdvancedStates.marital)
        kb = paginated_multiselect_kb(
            items=["замужем/женат", "не замужем/не женат", "разведен(а)", "Пропустить"],
            callback_prefix="marital",
            items_per_page=4,
            always_show_done=False,
        )
        await cb.message.edit_text(
            ensure_min_words("Можем уточнить семейное положение, если это важно для вашего бренда."),
            reply_markup=kb,
        )
    else:
        await _show_results_or_pay(cb, state)
    await cb.answer()


# ===== advanced: marital =====

@router.callback_query(SelectionAdvancedStates.marital, F.data.startswith("marital:"))
async def on_marital(cb: CallbackQuery, state: FSMContext):
    choice = cb.data.split(":", 2)[2]
    if choice != "Пропустить":
        await state.update_data(marital=choice)
        # Доп-вопрос: дети
        await state.set_state(SelectionAdvancedStates.children)
        kb = paginated_multiselect_kb(
            items=["Да", "Нет", "Пропустить"],
            callback_prefix="children",
            items_per_page=3,
            always_show_done=False,
        )
        await cb.message.edit_text(ensure_min_words("Поняла. Есть ли дети у блогера? Это поможет точнее сегментировать аудиторию."), reply_markup=kb)
    else:
        # Здесь пока просто завершим базовый этап — на следующем шаге подключим оплату и выдачу.
        await cb.message.edit_text("Принято. На следующем шаге подключу оплату и покажу результаты.")
        # Пропустить — идем дальше
        await state.set_state(SelectionAdvancedStates.followers)
        await cb.message.edit_text(ensure_min_words("Окей, пропустим. Укажите желаемый диапазон подписчиков, например 10k-50k или 'до 100k'."))
    await cb.answer()


@router.callback_query(SelectionAdvancedStates.children, F.data.startswith("children:"))
async def on_children(cb: CallbackQuery, state: FSMContext):
    choice = cb.data.split(":", 2)[2]
    if choice == "Да":
        await state.update_data(has_children=True)
        await state.set_state(SelectionAdvancedStates.children_count)
        kb = paginated_multiselect_kb(
            items=["1", "2", "3", "4", "более 4", "Пропустить"],
            callback_prefix="chcount",
            items_per_page=6,
            always_show_done=False,
        )
        await cb.message.edit_text(ensure_min_words("Сколько детей у блогера? Поможет уточнить портрет аудитории."), reply_markup=kb)
    elif choice == "Нет":
        await state.update_data(has_children=False)
        await state.set_state(SelectionAdvancedStates.followers)
        await cb.message.edit_text(ensure_min_words("Принято. Теперь желаемый диапазон подписчиков? Напишите форматом 10k-50k или 'от 5k'."))
    else:
        # Пропустить
        await state.set_state(SelectionAdvancedStates.followers)
        await cb.message.edit_text(ensure_min_words("Хорошо, пропустим. Укажите желаемый диапазон подписчиков."))
    await cb.answer()


@router.callback_query(SelectionAdvancedStates.children_count, F.data.startswith("chcount:"))
async def on_children_count(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":", 2)[2]
    await state.update_data(children_count=("more" if val == "более 4" else val if val != "Пропустить" else None))
    await state.set_state(SelectionAdvancedStates.followers)
    await cb.message.edit_text(ensure_min_words("Спасибо! Теперь укажите диапазон подписчиков блогера."))
    await cb.answer()


# followers, formats, budget — текстовые ответы

@router.message(SelectionAdvancedStates.followers, F.text)
async def on_followers(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    await state.update_data(followers_text=txt)
    await state.set_state(SelectionAdvancedStates.formats)
    await msg.answer(ensure_min_words("Какие форматы интеграций вам подходят: stories, reels, post? Можно несколько, перечислите через запятую."))


@router.message(SelectionAdvancedStates.formats, F.text)
async def on_formats(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    await state.update_data(formats=txt)
    await state.set_state(SelectionAdvancedStates.budget)
    await msg.answer(ensure_min_words("Какой бюджет комфортен? Можно указать диапазон, например 50-150 тысяч, или 'до 80 тысяч'."))


@router.message(SelectionAdvancedStates.budget, F.text)
async def on_budget(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    await state.update_data(budget_text=txt)
    # Завершили advanced — показать оплату/результаты
    await _show_results_or_pay(msg, state)


# ===== results and payments (mock) =====

async def _parse_followers_range(text: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    if not text:
        return None, None
    t = text.lower().replace(" ", "").replace("к", "000").replace("k", "000").replace("тыс", "000")
    import re
    # форматы: 10k-50k, от 5000, до 20000
    m = re.match(r"^(\d+)-(\d+)$", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    m = re.match(r"^>=?(\d+)$|^от(\d+)$", t)
    if m:
        num = int(next(g for g in m.groups() if g))
        return (num, None)
    m = re.match(r"^<=?(\d+)$|^до(\d+)$", t)
    if m:
        num = int(next(g for g in m.groups() if g))
        return (None, num)
    m = re.match(r"^(\d+)$", t)
    if m:
        x = int(m.group(1)); return (x, x)
    return (None, None)


async def _parse_budget_max(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    t = text.lower().replace(" ", "").replace("к", "000").replace("k", "000").replace("тыс", "000")
    import re
    # берем верхнюю границу
    m = re.match(r"^(\d+)-(\d+)$", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return max(a, b)
    m = re.match(r"^<=?(\d+)$|^до(\d+)$", t)
    if m:
        return int(next(g for g in m.groups() if g))
    m = re.match(r"^(\d+)$", t)
    if m:
        return int(m.group(1))
    return None


async def _show_results_or_pay(event: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cities = list(data.get("sel_cities") or [])
    topics = list(data.get("sel_topics") or [])
    age_text = data.get("age_text")
    lang = data.get("language")
    gender = data.get("gender")
    marital = data.get("marital")
    has_children = data.get("has_children")
    children_count = data.get("children_count")
    followers_text = data.get("followers_text")
    budget_text = data.get("budget_text")

    age_rng = parse_age_range(age_text) if age_text else None
    fmin, fmax = await _parse_followers_range(followers_text)
    bmax = await _parse_budget_max(budget_text)

    df = query_influencers(
        city=cities or None,
        topic=topics or None,
        age_range=age_rng,
        gender=gender,
        language=lang,
        marital_status=("married" if marital == "замужем/женат" else "single" if marital == "не замужем/не женат" else "divorced" if marital == "разведен(а)" else None),
        has_children=has_children,
        children_count=children_count,
        followers_min=fmin,
        followers_max=fmax,
        budget_max=bmax,
        limit=None,
    )

    await state.update_data(results_df=df.to_dict(orient="records"), res_page=1, picked=set())

    # MOCK paywall: если нет флага paid, предложим оплату; иначе сразу показываем
    paid = bool(data.get("paid"))
    if not paid and settings.PAYMENT_MODE != "mock_free":
        price = settings.PAYMENT_PRICE
        text = ensure_min_words(f"Чтобы получить результаты подбора, требуется оплата {price} {settings.PAYMENT_CURRENCY}. После оплаты сразу покажу персональный список.")
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=paginated_multiselect_kb(["Оплатить", "Отмена"], "pay", items_per_page=2, always_show_done=False))
        else:
            await event.answer(text, reply_markup=paginated_multiselect_kb(["Оплатить", "Отмена"], "pay", items_per_page=2, always_show_done=False))
        return

    # Показ результатов
    await _render_results(event, state)


async def _render_results(evt: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    records = data.get("results_df") or []
    page = int(data.get("res_page") or 1)
    per = settings.RESULTS_PER_PAGE
    import math
    total = max(1, int(math.ceil(len(records) / float(per))))
    page = max(1, min(page, total))
    s, e = (page - 1) * per, (page - 1) * per + per
    chunk = records[s:e]
    text_lines = []
    usernames = []
    for i, row in enumerate(chunk, start=1):
        name = row.get("name") or "—"
        username = (row.get("username") or "").lstrip("@")
        usernames.append(username)
        city = row.get("city") or "—"
        topics = row.get("topics") or "—"
        lang = row.get("language") or "—"
        followers = row.get("followers") or "—"
        price = row.get("price") or "—"
        text_lines.append(f"{i}. {name} (@{username}) — {city} | {topics} | {lang} | подписчики: {followers} | цена: {price}")
    if not text_lines:
        msg_text = ensure_min_words("Похоже, по этим параметрам никого не нашлось. Можем скорректировать фильтры и попробовать иначе.")
    else:
        msg_text = ensure_min_words("\n".join(text_lines))

    selected: set[str] = set(data.get("picked") or [])
    kb_select = result_item_kb(usernames, selected)
    kb_nav = results_nav_kb(page, total, allow_select_done=True)

    if isinstance(evt, CallbackQuery):
        await evt.message.edit_text(msg_text)
        await evt.message.edit_reply_markup(kb_select)
        # Отправим навигацию отдельным сообщением один раз на страницу
        await evt.message.answer("Навигация по результатам:", reply_markup=kb_nav)
        await evt.answer()
    else:
        await evt.answer(msg_text, reply_markup=kb_select)
        await evt.answer("Навигация по результатам:", reply_markup=kb_nav)


@router.callback_query(F.data.startswith("res:"))
async def on_results_nav(cb: CallbackQuery, state: FSMContext):
    _, action, value = cb.data.split(":", 2)
    if action == "page":
        await state.update_data(res_page=max(1, int(value)))
        await _render_results(cb, state)
    elif action == "done":
        data = await state.get_data()
        picked = list(set(data.get("picked") or []))
        if not picked:
            await cb.answer("Выберите хотя бы одного блогера", show_alert=True)
            return
        # Запишем выбор в Sheets и сообщим менеджеру
        try:
            user = cb.from_user
            user_line = f"Пользователь: id={user.id}, username=@{user.username or '-'}, name={user.full_name}"
            chosen = ", ".join(f"@{u}" for u in picked)
            try:
                await asyncio.to_thread(gs.append_selection, user.id, user.username, picked, None, None)
            except Exception:
                pass
            await cb.message.bot.send_message(
                settings.MANAGER_CONTACT,
                f"Новый подбор завершен.\n{user_line}\nВыбранные блогеры: {chosen}"
            )
        except Exception:
            pass
        await cb.message.edit_text(ensure_min_words("Спасибо! Я передам менеджеру ваши контакты и выбранных блогеров. Мы свяжемся с вами в ближайшее время. Хотите начать новый подбор? Нажмите 'Новый подбор'."))
        await cb.answer()
    elif action == "export":
        kb = paginated_multiselect_kb(["PDF", "Excel", "Отмена"], "expfmt", items_per_page=3, always_show_done=False)
        await cb.message.answer("Выберите формат экспорта:", reply_markup=kb)
        await cb.answer()
    elif action == "new":
        # Перезапуск сценария подбора без повторной оплаты
        await start_selection(cb.message, state)
        await cb.answer()


@router.callback_query(F.data.startswith("pick:"))
async def on_pick(cb: CallbackQuery, state: FSMContext):
    username = cb.data.split(":", 1)[1]
    data = await state.get_data()
    picked: set[str] = set(data.get("picked") or [])
    if username in picked:
        picked.remove(username)
    else:
        picked.add(username)
    await state.update_data(picked=picked)
    # пере-рендер кнопок выбора под текущей страницей
    # Вытянем видимых на странице юзернеймов
    records = data.get("results_df") or []
    page = int(data.get("res_page") or 1)
    per = settings.RESULTS_PER_PAGE
    s, e = (page - 1) * per, (page - 1) * per + per
    usernames = [(r.get("username") or "").lstrip("@") for r in records[s:e]]
    await cb.message.edit_reply_markup(result_item_kb(usernames, picked))
    await cb.answer()


# ===== payments (mock) =====

@router.callback_query(F.data.startswith("pay:"))
async def on_pay(cb: CallbackQuery, state: FSMContext):
    action = cb.data.split(":", 2)[2]
    if action == "Оплатить":
        # Mock: просто ставим флаг paid и показываем результаты
        await state.update_data(paid=True)
        await cb.message.edit_text(ensure_min_words("Оплата прошла успешно. Готовлю результаты подбора."))
        await _render_results(cb, state)
    else:
        await cb.message.edit_text(ensure_min_words("Отменено. Можем вернуться к фильтрам или начать заново."))
    await cb.answer()


# ===== export =====

@router.callback_query(F.data.startswith("expfmt:"))
async def on_export(cb: CallbackQuery, state: FSMContext):
    fmt = cb.data.split(":", 1)[1]
    if fmt == "Отмена":
        await cb.answer("Отмена")
        return
    data = await state.get_data()
    records = data.get("results_df") or []
    picked = set(data.get("picked") or [])
    if not picked:
        await cb.answer("Сначала выберите блогеров для экспорта", show_alert=True)
        return
    import pandas as pd
    df = pd.DataFrame(records)
    df = df[df["username"].astype(str).str.lstrip("@").isin(picked)]
    if df.empty:
        await cb.answer("Не удалось сформировать экспорт", show_alert=True)
        return
    if fmt == "PDF":
        content = export_pdf(df)
        file = BufferedInputFile(content, filename="influencers.pdf")
        await cb.message.answer_document(file, caption="Экспорт выбранных блогеров (PDF)")
    elif fmt == "Excel":
        content = export_excel(df)
        file = BufferedInputFile(content, filename="influencers.xlsx")
        await cb.message.answer_document(file, caption="Экспорт выбранных блогеров (Excel)")
    await cb.answer()
