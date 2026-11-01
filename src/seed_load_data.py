# Lab 7: наповнення БД реалістичним обсягом даних для навантажувального тестування.
# Вірусна петиція №1 після посту в Telegram має тисячі підписів, а в каталозі — сотні петицій.
# Запуск (у Docker):  docker compose exec web python -m src.seed_load_data
import asyncio
import hashlib
import random

from sqlalchemy import func, insert, select

from src.database import AsyncSessionLocal
from src.init_db import init_models, seed_data
from src.models import Petition, User, Vote

PETITIONS_COUNT = 200  # скільки петицій додати в каталог
VIRAL_VOTES = 10_000  # скільки підписів має вірусна петиція №1
OTHER_MAX_VOTES = 50  # інші петиції мають від 0 до 50 підписів


async def main():
    await init_models()
    await seed_data()  # демо-користувачі та 3 демо-петиції

    random.seed(42)  # однакові дані для прогонів «ДО» і «ПІСЛЯ»
    async with AsyncSessionLocal() as session:
        if (await session.execute(select(func.count(Petition.id)))).scalar() > 10:
            print("Дані для навантаження вже є — пропуск")
            return

        author_id = (await session.execute(select(User.id).where(User.username == "pavlo"))).scalar()

        petitions = [
            {
                "title": f"Тестова петиція №{i}",
                "description": "Опис петиції для навантажувального тестування. " * 5,
                "target_votes": 1000,
                "status": "active",
                "author_id": author_id,
            }
            for i in range(PETITIONS_COUNT)
        ]
        await session.execute(insert(Petition), petitions)

        petition_ids = (await session.execute(select(Petition.id))).scalars().all()
        votes = []
        for pid in petition_ids:
            count = VIRAL_VOTES if pid == 1 else random.randint(0, OTHER_MAX_VOTES)
            for n in range(count):
                sig = hashlib.sha256(f"load_voter_{pid}_{n}".encode()).hexdigest()
                votes.append({"petition_id": pid, "user_id": None, "voter_signature_hash": sig})

        # Вставляємо пачками по 5000 рядків
        for start in range(0, len(votes), 5000):
            await session.execute(insert(Vote), votes[start : start + 5000])
        await session.commit()
        print(f"Додано {len(petitions)} петицій і {len(votes)} голосів")


if __name__ == "__main__":
    asyncio.run(main())
