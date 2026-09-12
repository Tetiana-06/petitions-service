# Налаштування середовища (за замовчуванням використано локальний SQLite, але готовий рядок і для PostgreSQL):

import os


class Settings:
    PROJECT_NAME: str = "Local Petitions Service"
    # Для PostgreSQL: postgresql+asyncpg://user:pass@localhost:5432/petitions_db
    # Для локального запуску:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./petitions.db")


settings = Settings()
