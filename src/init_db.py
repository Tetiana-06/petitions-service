import asyncio

from src.database import Base, engine
from src.models import Petition, Vote  # noqa: F401


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Таблиці успішно створено!")


if __name__ == "__main__":
    asyncio.run(init_models())
