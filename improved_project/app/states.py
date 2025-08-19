# app/states.py
from aiogram.fsm.state import State, StatesGroup

class InfluencerSearch(StatesGroup):
    # --- Базовый поиск ---
    choosing_city = State()
    choosing_topic = State()
    choosing_age = State()
    choosing_gender = State()
    choosing_language = State()

    # --- Выбор дальнейшего действия ---
    advanced_or_results = State()

    # --- Продвинутый поиск ---
    choosing_followers = State()
    choosing_budget = State()
    choosing_service = State()

    # --- Отображение результата ---
    showing_results = State()