# Керування конфігураціями тестового (Sandbox) та робочого (Production) середовищ
import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


def get_env_file_path(env_name: Optional[str] = None) -> Optional[Path]:
    """Визначає шлях до файлу конфігурацій середовища (.env.sandbox або .env.production)."""
    target_env = env_name or os.getenv("APP_ENV", "sandbox").strip().lower()
    specific_env_file = BASE_DIR / f".env.{target_env}"
    if specific_env_file.exists():
        return specific_env_file

    fallback_file = BASE_DIR / ".env"
    if fallback_file.exists():
        return fallback_file

    return None


class Settings(BaseSettings):
    """Типізована конфігурація застосунку через pydantic-settings."""

    # Назва середовища: sandbox або production
    APP_ENV: str = "sandbox"
    PROJECT_NAME: str = "Local Petitions Service"

    # Режим відладки (DEBUG = False для Production)
    DEBUG: bool = True

    # Підключення до БД (ізоляція для sandbox та production)
    DATABASE_URL: str = "sqlite+aiosqlite:///src/petitions_sandbox.db"
    DB_ECHO: bool = False

    # Безпека та JWT
    SECRET_KEY: str = "sandbox-insecure-secret-key-for-local-testing-only-12345"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Завантаження початкових демо-даних (True для Sandbox, False для Production)
    SEED_DEMO_DATA: bool = True

    model_config = SettingsConfigDict(
        env_file=get_env_file_path(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings(env_name: Optional[str] = None) -> Settings:
    """Фабрика налаштувань, що підтримує явний вибір середовища (для тестів чи запуску)."""
    if env_name:
        env_path = get_env_file_path(env_name)
        if env_path and env_path.exists():
            from dotenv import dotenv_values

            file_values = {k: v for k, v in dotenv_values(env_path).items() if v is not None}
            return Settings(_env_file=str(env_path), **file_values)
        return Settings(APP_ENV=env_name)
    return Settings()


# Екземпляр конфігурації за замовчуванням
settings = get_settings()
