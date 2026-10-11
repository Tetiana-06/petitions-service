# Стандартний клас для роботи з датою та часом
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

# Типи колонок, обмеження та зовнішній ключ із ядра SQLAlchemy
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

# Сучасні інструменти декларативної типізації SQLAlchemy 2.0:
# Mapped — тип поля в Python, mapped_column — опис колонки в БД
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Спільний базовий клас (декларативну базу), створений раніше в database.py
from src.database import Base


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class PetitionStatus(str, Enum):
    ACTIVE = "active"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.USER.value, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now)

    petitions = relationship("Petition", back_populates="author", cascade="all, delete-orphan")
    votes = relationship("Vote", back_populates="user", cascade="all, delete-orphan")


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

    # Необхідна кількість голосів для розгляду 1000
    target_votes: Mapped[int] = mapped_column(Integer, default=1000)

    # Статус петиції (активна, на розгляді, схвалена, відхилена)
    status: Mapped[str] = mapped_column(String(30), default=PetitionStatus.ACTIVE.value, nullable=False)

    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # Дата й час створення: тип DATETIME, поточний час у форматі UTC
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now)

    author = relationship("User", back_populates="petitions")
    votes = relationship("Vote", back_populates="petition", cascade="all, delete-orphan")


# Модель таблиці голосів користувачів
class Vote(Base):
    # Назва фізичної таблиці в базі даних
    __tablename__ = "votes"

    # Первинний ключ запису голосу з індексом
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Зовнішній ключ (Foreign Key): посилається на колонку `id` з таблиці `petitions`
    # index=True оптимізує підрахунок кількості голосів для кожної конкретної петиції
    petition_id: Mapped[int] = mapped_column(Integer, ForeignKey("petitions.id"), nullable=False, index=True)

    # Зв'язок з користувачем, який підписав (опціонально для зворотньої сумісності з КЕП)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Геш КЕП/токену громадянина для криптографічного забезпечення унікальності:
    # Рядок фіксованого розміру (наприклад, SHA-512 дає 128 hex-символів), обов'язковий та індексований
    voter_signature_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Дата й час фіксації голосу (за замовчуванням поточний час створення)
    voted_at: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now)

    petition = relationship("Petition", back_populates="votes")
    user = relationship("User", back_populates="votes")

    # Гарантія на рівні БД: один підпис — один голос за петицію
    # __table_args__ задає додаткові параметри та обмеження таблиці
    __table_args__ = (
        # Складений унікальний констрейнт: пара значень (petition_id + voter_signature_hash)
        # не може повторюватися; спроба проголосувати вдруге викличе помилку IntegrityError на рівні БД
        UniqueConstraint("petition_id", "voter_signature_hash", name="uq_petition_voter"),
    )
