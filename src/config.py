# Налаштування середовища (за замовчуванням використано локальний SQLite, але готовий рядок і для PostgreSQL):

import os
from pathlib import Path

# Визначаю кореневу папку проєкту (на один рівень вище за папку src)
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "src" / "petitions.db"


class Settings:
    PROJECT_NAME: str = "Local Petitions Service"
    # Для PostgreSQL: postgresql+asyncpg://user:pass@localhost:5432/petitions_db
    # Для локального запуску:
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DB_PATH.as_posix()}")
    # 2 лаб
    # Параметри безпеки та автентифікації
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-for-lab2-highload")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60


settings = Settings()
