# app/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Эта строка вычисляет АБСОЛЮТНЫЙ путь к корневой папке проекта (где лежит run.py)
BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    # --- Core ---
    BOT_TOKEN: str
    START_MODE: str = "strict"
    MANAGER_CONTACT: str = "@your_manager"
    INVITE_TOKENS: str = ""

    # --- Google Sheets ---
    GOOGLE_SHEET_ID: str
    # Путь к файлу ключей из .env
    GOOGLE_SHEETS_CREDENTIALS_FILE: str | None = None
    # JSON с ключами напрямую из .env
    GOOGLE_SHEETS_CREDENTIALS_JSON: str | None = None

    # --- OpenAI ---
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TIMEOUT: int = 30
    REG_MODEL: str = "gpt-4o-mini"
    RESPONDER_MODEL: str = "gpt-4o-mini"

    # --- Bot behavior ---
    MAX_HISTORY_TURNS: int = 6

    # Новая переменная для АБСОЛЮТНОГО пути
    # Она не читается из .env, а вычисляется здесь
    CREDENTIALS_FILE_ABSPATH: Path | None = None

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

# Создаем объект настроек
settings = Settings()

# Если в .env указан путь к файлу, вычисляем его полный путь
if settings.GOOGLE_SHEETS_CREDENTIALS_FILE:
    settings.CREDENTIALS_FILE_ABSPATH = BASE_DIR / settings.GOOGLE_SHEETS_CREDENTIALS_FILE