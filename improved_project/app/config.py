from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Базовая папка проекта: .../improved_project
BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    GOOGLE_SHEET_ID: str = ""
    GOOGLE_SHEET_USERS_TAB: str = "users"
    GOOGLE_SHEETS_CREDENTIALS_FILE: str = ""
    GOOGLE_SHEETS_CREDENTIALS_JSON: str = ""

    BOT_TOKEN: str
    START_MODE: str = "strict"  # 'strict' => only via URL invite; 'loose' => allow /start without token
    MANAGER_CONTACT: str = "@your_manager"
    INVITE_TOKENS: str = ""  # comma-separated list for dev/demo, e.g., "nonna,demo"

    REG_MODEL: str = "gpt-5-nano"
    QA_MODEL: str = "gpt-5-nano"
    REG_MAX_TOKENS: int = 600
    QA_MAX_TOKENS: int = 500


    # LLM
    OPENAI_API_KEY: Optional[str] = None
    RESPONDER_MODEL: str = "gpt-4o-mini"
    MAX_HISTORY_TURNS: int = 15
    REPLY_LENGTH: str = "long"  # "short" | "medium" | "long"
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),  # <-- берём .env из корня проекта
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()