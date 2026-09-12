# Асинхронна ініціалізація підключення до БД

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from src.config import settings

# Цей фрагмент коду налаштовує асинхронну роботу з базою даних через SQLAlchemy 2.0+

# 1. Створюємо асинхронний рушій (пул підключень до бази даних)
#    echo=True вмикає виведення всіх сирих SQL-запитів у термінал (для дебагу)
engine = create_async_engine(settings.DATABASE_URL, echo=True)

# 2. Фабрика сесій: налаштовує шаблон, за яким створюватимуться сесії
#    - bind=engine: прив'язуємо сесії до нашого рушія
#    - class_=AsyncSession: явно кажемо створювати саме асинхронні сесії
#    - expire_on_commit=False: запобігає «скиданню» даних з пам'яті після commit,
#      щоб уникнути помилки MissingGreenlet при повторному зверненні до полів об'єкта
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# 3. Базовий клас для майбутніх ORM-моделей (від нього наслідуються моделі таблиць)
Base = declarative_base()


# 4. Асинхронний генератор залежності (Dependency Injection для FastAPI)
#    Типізація: генерує (yield) сесію типу AsyncSession, при завершенні нічого не повертає (None)
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    # 5. Створюємо екземпляр сесії всередині асинхронного контекстного менеджера;
    #    він гарантує закриття сесії навіть у разі помилок/виключень
    async with AsyncSessionLocal() as session:
        # 6. Віддаємо створену сесію в ендпоінт роутера та ставимо виконання на паузу
        yield session
        # Після завершення обробки запиту виконання повертається сюди,
        # блок async with виходить і безпечно закриває з'єднання
