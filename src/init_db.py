import asyncio
import hashlib
import sys
from pathlib import Path

from sqlalchemy import select

# Додаємо кореневу директорію проєкту до sys.path для підтримки прямого запуску
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.database import AsyncSessionLocal, Base, engine  # noqa: E402
from src.models import Petition, PetitionStatus, User, UserRole, Vote  # noqa: E402
from src.security import hash_password  # noqa: E402


async def init_models():
    async with engine.begin() as conn:
        # Безпечне створення всіх нових таблиць
        await conn.run_sync(Base.metadata.create_all)

        # Перевірка та автоматичне додавання відсутніх колонок (для збереження існуючої БД без збоїв)
        columns_to_ensure = [
            ("users", "full_name", "VARCHAR(100)"),
            ("users", "email", "VARCHAR(100)"),
            ("petitions", "status", "VARCHAR(30) DEFAULT 'active'"),
            ("votes", "user_id", "INTEGER REFERENCES users(id)"),
        ]
        for table, col, col_type in columns_to_ensure:
            try:
                await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except Exception:
                # Колонка вже існує
                pass

    print("Таблиці успішно створено та оновлено!")


async def seed_data():
    async with AsyncSessionLocal() as session:
        # 1. Перевірка наявності користувачів
        res = await session.execute(select(User).where(User.username == "admin"))
        admin_user = res.scalars().first()

        if not admin_user:
            admin_user = User(
                username="admin",
                hashed_password=hash_password("admin123"),
                role=UserRole.ADMIN.value,
                full_name="Головний Адміністратор",
                email="admin@petitions.gov.ua",
            )
            session.add(admin_user)

        res_ivan = await session.execute(select(User).where(User.username == "ivan_patriot"))
        ivan_user = res_ivan.scalars().first()
        if not ivan_user:
            ivan_user = User(
                username="ivan_patriot",
                hashed_password=hash_password("user123"),
                role=UserRole.USER.value,
                full_name="Іван Коваленко",
                email="ivan.kovalenko@example.com",
            )
            session.add(ivan_user)

        res_olena = await session.execute(select(User).where(User.username == "olena_kyiv"))
        olena_user = res_olena.scalars().first()
        if not olena_user:
            olena_user = User(
                username="olena_kyiv",
                hashed_password=hash_password("user123"),
                role=UserRole.USER.value,
                full_name="Олена Шевченко",
                email="olena.shevchenko@example.com",
            )
            session.add(olena_user)

        await session.commit()
        await session.refresh(admin_user)
        await session.refresh(ivan_user)
        await session.refresh(olena_user)

        # 2. Перевірка наявності петицій
        res_petitions = await session.execute(select(Petition))
        existing_petitions = res_petitions.scalars().all()

        if not existing_petitions:
            p1 = Petition(
                title="Капітальний ремонт міського парку культури та відпочинку",
                description=(
                    "Просимо міську раду виділити фінансування на благоустрій центрального парку: "
                    "встановлення нового освітлення, сучасних лавок, дитячого інклюзивного майданчика "
                    "та облаштування якісних велодоріжок."
                ),
                target_votes=500,
                status=PetitionStatus.ACTIVE.value,
                author_id=ivan_user.id,
            )
            p2 = Petition(
                title="Впровадження безконтактної оплати у всьому муніципальному транспорті",
                description=(
                    "Необхідно повністю завершити автоматизацію системи оплати проїзду в усіх міських автобусах, "
                    "тролейбусах та трамваях з підтримкою банківських карток та NFC-платежів."
                ),
                target_votes=1000,
                status=PetitionStatus.ACTIVE.value,
                author_id=olena_user.id,
            )
            p3 = Petition(
                title="Створення безбар'єрного простору та пандусів у центрі міста",
                description=(
                    "Звертаємось з вимогою провести аудит та ліквідувати високі бордюри й відсутність з'їздів "
                    "на ключових пішохідних переходах для вільного пересування маломобільних груп населення."
                ),
                target_votes=250,
                status=PetitionStatus.UNDER_REVIEW.value,
                author_id=ivan_user.id,
            )
            session.add_all([p1, p2, p3])
            await session.commit()

            # Додаємо кілька початкових голосів
            sig_ivan = hashlib.sha256(f"signature_user_{ivan_user.id}_pet_{p2.id}".encode()).hexdigest()
            sig_olena = hashlib.sha256(f"signature_user_{olena_user.id}_pet_{p1.id}".encode()).hexdigest()

            v1 = Vote(petition_id=p2.id, user_id=ivan_user.id, voter_signature_hash=sig_ivan)
            v2 = Vote(petition_id=p1.id, user_id=olena_user.id, voter_signature_hash=sig_olena)
            session.add_all([v1, v2])
            await session.commit()

            print("Початкові демо-дані успішно завантажено!")


async def main():
    await init_models()
    await seed_data()


if __name__ == "__main__":
    asyncio.run(main())
