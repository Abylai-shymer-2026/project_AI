# app/states.py
from aiogram.fsm.state import State, StatesGroup

class CommonStates(StatesGroup):
    pre_registration = State()

class RegistrationStates(StatesGroup):
    name = State()
    company = State()
    industry = State()
    position = State()
    phone = State()

class SelectionBasicStates(StatesGroup):
    cities = State()     # обязательный мультивыбор
    topics = State()     # обязательный мультивыбор
    age = State()        # опционально (с уточнением «24»)
    gender = State()     # авто/текст
    language = State()   # кнопки: Казахский/Русский/Двуязычный/Пропустить

class SelectionDecisionStates(StatesGroup):
    decide = State()     # показать кнопки: Advanced / Показать результат

class SelectionAdvancedStates(StatesGroup):
    marital = State()
    children = State()
    children_count = State()
    followers = State()
    formats = State()
    budget = State()
