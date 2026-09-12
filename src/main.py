# Каркас FastAPI з ендпоінтами перевірки працездатності:
# Імпортуємо декоратор для створення асинхронного контекстного менеджера (життєвий цикл застосунку)
from contextlib import asynccontextmanager

# Імпортуємо головний клас вебфреймворка FastAPI
from fastapi import FastAPI

# Імпортуємо з нашого модуля БД спільний базовий клас моделей (Base) та рушій підключень (engine)
from src.database import Base, engine


# Декоратор перетворює асинхронну функцію-генератор на контекстний менеджер для FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Код ДО ключового слова yield виконується один раз під час запуску (startup) сервера:
    # engine.begin() відкриває транзакційне асинхронне з'єднання (Connection)
    async with engine.begin() as conn:
        # Base.metadata.create_all — синхронний метод SQLAlchemy, тому run_sync запускає його
        # в окремому потоці, створюючи всі відсутні таблиці в БД згідно з наявними моделями
        await conn.run_sync(Base.metadata.create_all)

    # yield передає керування запущеному застосунку й тримає його активним для обробки запитів.
    # Код ПІСЛЯ yield (якщо його додати) виконається один раз при вимкненні (shutdown) сервера
    yield


# Створюємо головний екземпляр застосунку FastAPI з метаданими для документації Swagger/ReDoc
app = FastAPI(
    title="Local Petitions Service API",  # Назва сервісу в документації (/docs)
    description="Highload API для місцевих петицій",  # Опис призначення API
    version="1.0.0",  # Поточна версія API
    lifespan=lifespan,  # Підключаємо наш контекстний менеджер життєвого циклу
)


# Декоратор реєструє обробник для GET-запиту на шлях /health;
# tags=["System"] групує цей ендпоінт в окрему секцію "System" в інтерфейсі Swagger
@app.get("/health", tags=["System"])
async def health_check():
    # Повертає простий JSON для моніторингу працездатності (використовується оркестраторами, наприклад, Docker/K8s)
    return {"status": "ok", "service": "petitions-service"}


# Декоратор реєструє обробник для кореневого URL (GET /)
@app.get("/", tags=["Root"])
async def root():
    # Повертає вітальне JSON-повідомлення, підтверджуючи, що сервіс успішно піднявся
    return {"message": "Сервіс місцевих електронних петицій працює"}
