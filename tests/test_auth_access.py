import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_all_security_scenarios():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Сценарій: Анонімний доступ (має повернути 401 Unauthorized)
        res = await client.get("/users/me")
        assert res.status_code == 401

        # 2. Реєстрація звичайного користувача (User A)
        reg_user = await client.post(
            "/auth/register",
            json={
                "username": "user_a",
                "password": "password123",
                "role": "user",
            },
        )
        assert reg_user.status_code in [201, 400]

        # 3. Сценарій: Помилка входу (невірний пароль -> 401)
        res_bad_login = await client.post(
            "/auth/login",
            data={"username": "user_a", "password": "wrongpassword"},
        )
        assert res_bad_login.status_code == 401

        # 4. Сценарій: Успішна автентифікація (статус 200 та отримання токена)
        res_login = await client.post(
            "/auth/login",
            data={"username": "user_a", "password": "password123"},
        )
        assert res_login.status_code == 200
        token_a = res_login.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Перевірка доступу до власної сторінки-заглушки (200 OK)
        res_me = await client.get("/users/me", headers=headers_a)
        assert res_me.status_code == 200

        # 5. Сценарій: Вертикальне розмежування ролей (User лізе в Admin -> 403 Forbidden)
        res_admin_forbidden = await client.get("/admin/dashboard", headers=headers_a)
        assert res_admin_forbidden.status_code == 403

        # 6. Реєстрація адміністратора та перевірка доступу
        reg_admin = await client.post(
            "/auth/register",
            json={
                "username": "admin_boss",
                "password": "adminpassword",
                "role": "admin",
            },
        )
        assert reg_admin.status_code in [201, 400]

        res_admin_login = await client.post(
            "/auth/login",
            data={"username": "admin_boss", "password": "adminpassword"},
        )
        admin_token = res_admin_login.json()["access_token"]
        headers_admin = {"Authorization": f"Bearer {admin_token}"}

        res_admin_ok = await client.get("/admin/dashboard", headers=headers_admin)
        assert res_admin_ok.status_code == 200

        # 7. Сценарій: Горизонтальне розмежування прав (IDOR)
        # Створюємо петицію від імені User A
        create_pet = await client.post(
            "/petitions/",
            json={"title": "Ремонт парку", "description": "Опис петиції"},
            headers=headers_a,
        )
        assert create_pet.status_code == 201
        petition_id = create_pet.json()["id"]

        # Реєструємо другого користувача (User B)
        await client.post(
            "/auth/register",
            json={
                "username": "user_b",
                "password": "password123",
                "role": "user",
            },
        )
        res_login_b = await client.post(
            "/auth/login",
            data={"username": "user_b", "password": "password123"},
        )
        token_b = res_login_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User B намагається змінити петицію User A -> 403 Forbidden (IDOR захист)
        res_idor = await client.put(
            f"/petitions/{petition_id}",
            json={"title": "Зламаний заголовок від хакера"},
            headers=headers_b,
        )
        assert res_idor.status_code == 403
