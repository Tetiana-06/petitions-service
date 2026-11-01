# Lab 7: шар кешування на Redis (спільний для всіх реплік застосунку).
# Якщо REDIS_URL порожній або Redis недоступний — застосунок просто працює без кешу.
import json
import logging

import redis.asyncio as redis

from src.config import settings

logger = logging.getLogger("petitions_service")

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None


async def cache_get(key: str):
    """Повертає збережене значення (dict/list) або None, якщо в кеші нічого немає."""
    if redis_client is None:
        return None
    try:
        value = await redis_client.get(key)
        return json.loads(value) if value else None
    except Exception as exc:
        logger.warning(f"Redis недоступний (get): {exc}")
        return None


async def cache_set(key: str, value, ttl: int = settings.CACHE_TTL_SECONDS):
    """Зберігає значення в кеші на ttl секунд (TTL — час життя запису)."""
    if redis_client is None:
        return
    try:
        await redis_client.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:
        logger.warning(f"Redis недоступний (set): {exc}")


async def cache_delete(*keys: str):
    """Видаляє застарілі записи після зміни даних (інвалідація кешу)."""
    if redis_client is None:
        return
    try:
        await redis_client.delete(*keys)
    except Exception as exc:
        logger.warning(f"Redis недоступний (delete): {exc}")
