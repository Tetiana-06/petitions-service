# Імпортуємо стандартний клас для роботи з датою та часом
from datetime import datetime

# Імпортуємо типи колонок, обмеження та зовнішній ключ із ядра SQLAlchemy
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

# Імпортуємо сучасні інструменти декларативної типізації SQLAlchemy 2.0:
# Mapped — тип поля в Python, mapped_column — опис колонки в БД
from sqlalchemy.orm import Mapped, mapped_column

# Імпортуємо спільний базовий клас (декларативну базу), створений раніше в database.py
from src.database import Base


# Модель таблиці петицій, успадкована від Base
class Petition(Base):
    # Назва фізичної таблиці в базі даних
    __tablename__ = "petitions"

    # Унікальний ідентифікатор: ціле число, первинний ключ (primary_key=True),
    # для якого створюється B-Tree індекс для швидкого пошуку (index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Назва петиції: рядок до 255 символів (VARCHAR(255)), обов'язкове поле (nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # Повний текст петиції: необмежений за довжиною текст (TEXT), обов'язкове поле
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Необхідна кількість голосів для розгляду: за замовчуванням встановлюється 500
    target_votes: Mapped[int] = mapped_column(Integer, default=500)

    # Дата й час створення: тип DATETIME, автоматично генерується поточний час при збереженні
    # (передається саме функція datetime.utcnow як callback без круглих дужок)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# Модель таблиці голосів користувачів
class Vote(Base):
    # Назва фізичної таблиці в базі даних
    __tablename__ = "votes"

    # Первинний ключ запису голосу з індексом
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Зовнішній ключ (Foreign Key): посилається на колонку `id` з таблиці `petitions`
    # index=True оптимізує підрахунок кількості голосів для кожної конкретної петиції
    petition_id: Mapped[int] = mapped_column(Integer, ForeignKey("petitions.id"), nullable=False, index=True)

    # Геш КЕП/токену громадянина для криптографічного забезпечення унікальності:
    # Рядок фіксованого розміру (наприклад, SHA-512 дає 128 hex-символів), обов'язковий та індексований
    voter_signature_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Дата й час фіксації голосу (за замовчуванням поточний час створення)
    voted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Гарантія на рівні БД: один підпис — один голос за петицію
    # __table_args__ задає додаткові параметри та обмеження таблиці
    __table_args__ = (
        # Складений унікальний констрейнт: пара значень (petition_id + voter_signature_hash)
        # не може повторюватися; спроба проголосувати вдруге викличе помилку IntegrityError на рівні БД
        UniqueConstraint("petition_id", "voter_signature_hash", name="uq_petition_voter"),
    )
