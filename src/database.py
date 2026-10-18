# Асинхронна ініціалізація підключення до БД з підтримкою ізоляції середовищ (Lab 3)
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from src.config import BASE_DIR, settings


def resolve_database_url(url: str) -> str:
    """Забезпечує абсолютний шлях для SQLite БД для уникнення колізій директорій."""
    sqlite_prefix = "sqlite+aiosqlite:///"
    if url.startswith(sqlite_prefix) and not url.startswith("sqlite+aiosqlite:////") and ":\\" not in url:
        rel_path = url[len(sqlite_prefix) :]
        abs_path = (BASE_DIR / rel_path).resolve()
        return f"{sqlite_prefix}{abs_path.as_posix()}"
    return url


# 1. Створюємо асинхронний рушій із параметрами з конфігурації
db_url = resolve_database_url(settings.DATABASE_URL)
#!!!!!!!!!!!!!!!
engine = create_async_engine(db_url, echo=settings.DB_ECHO)

# 2. Фабрика асинхронних сесій
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# 3. Базовий клас для декларативних ORM-моделей
Base = declarative_base()


# 4. Асинхронний генератор сесії (FastAPI Dependency)
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
