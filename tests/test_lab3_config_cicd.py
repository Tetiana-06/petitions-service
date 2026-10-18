# Автоматизовані тести для Лабораторної роботи №3
# Перевірка розділення конфігурацій, ізоляції баз даних та приховування стектрейсів помилок 500
import pytest
from httpx import ASGITransport, AsyncClient

from src.config import get_settings
from src.database import resolve_database_url
from src.main import app

# Тестова зміна для перевірки PR в GitHub Actions


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch):
    """Гарантує ізоляцію: видаляє глобальні змінні оточення сесії перед кожним тестом."""
    monkeypatch.delenv("APP_ENV", raising=False)


# 1. ТЕСТУВАННЯ РОЗДІЛЕННЯ КОНФІГУРАЦІЙ ЧЕРЕЗ ЗМІННІ ОТОЧЕННЯ


def test_sandbox_configuration_loading():
    """Перевірка зчитування налаштувань тестового середовища (.env.sandbox)."""
    sandbox_settings = get_settings("sandbox")

    assert sandbox_settings.APP_ENV == "sandbox"
    assert sandbox_settings.DEBUG is True
    assert sandbox_settings.SEED_DEMO_DATA is True
    assert "petitions_sandbox" in sandbox_settings.DATABASE_URL
    assert sandbox_settings.SECRET_KEY != ""


def test_production_configuration_loading():
    """Перевірка зчитування налаштувань робочого середовища (.env.production)."""
    prod_settings = get_settings("production")

    assert prod_settings.APP_ENV == "production"
    assert prod_settings.DEBUG is False
    assert prod_settings.SEED_DEMO_DATA is False
    assert "petitions_production" in prod_settings.DATABASE_URL
    assert prod_settings.SECRET_KEY != ""
    assert prod_settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30


# 2. ТЕСТУВАННЯ ІЗОЛЯЦІЇ БАЗ ДАНИХ


def test_database_isolation_between_environments():
    """Перевірка того, що Sandbox та Production використовують фізично різні БД."""
    sand_settings = get_settings("sandbox")
    prod_settings = get_settings("production")

    sand_db = resolve_database_url(sand_settings.DATABASE_URL)
    prod_db = resolve_database_url(prod_settings.DATABASE_URL)

    # Бази даних повинні бути чітко розмежовані
    assert sand_db != prod_db
    assert "sandbox" in sand_db
    assert "production" in prod_db


# 3. ТЕСТУВАННЯ РЕЖИМІВ БЕЗПЕКИ ТА ОБРОБКИ ПОМИЛОК 500


@pytest.mark.asyncio
async def test_500_error_masks_stacktrace_in_production(monkeypatch):
    """Перевірка того, що при DEBUG=False стектрейс та внутрішні деталі не показуються."""
    from src.config import settings

    # Симулюємо Production-режим (DEBUG = False)
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "APP_ENV", "production")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/system/trigger-error")

        assert res.status_code == 500
        data = res.json()
        # Переконуємося, що немає витоку інформації про виняток (Traceback / exception message)
        assert "debug_error" not in data
        assert "RuntimeError" not in str(data)
        assert data["detail"] == "Внутрішня помилка сервера. Будь ласка, зверніться до служби підтримки."


@pytest.mark.asyncio
async def test_500_error_reveals_debug_in_sandbox(monkeypatch):
    """Перевірка того, що при DEBUG=True у Sandbox показується діагностична інформація."""
    from src.config import settings

    # Симулюємо Sandbox-режим (DEBUG = True)
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "APP_ENV", "sandbox")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/system/trigger-error")

        assert res.status_code == 500
        data = res.json()
        assert "debug_error" in data
        assert data["environment"] == "sandbox"
        assert "Симульований збій бази даних" in data["debug_error"]


# 4. ТЕСТУВАННЯ ЕНДПОІНТІВ ІНФОРМАЦІЇ ПРО СЕРЕДОВИЩЕ


@pytest.mark.asyncio
async def test_system_env_endpoints():
    """Перевірка ендпоінтів /health та /system/env-info."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Health check містить інформацію про середовище
        res_health = await client.get("/health")
        assert res_health.status_code == 200
        assert "environment" in res_health.json()
        assert "debug" in res_health.json()

        # Env-info містить повні параметри конфігурації
        res_env = await client.get("/system/env-info")
        assert res_env.status_code == 200
        env_data = res_env.json()
        assert "app_env" in env_data
        assert "debug_mode" in env_data
        assert "database_url" in env_data
