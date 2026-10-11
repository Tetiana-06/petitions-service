# Комплексний набір юніт- та інтеграційних тестів для Лабораторної роботи №2
# Перевірка механізмів автентифікації, RBAC (вертикального) та IDOR (горизонтального) розмежування прав
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import Base, get_db
from src.main import app
from src.security import hash_password, verify_password

# Налаштовуємо тестову ізольовану базу даних SQLite в пам'яті
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


# Перевизначаємо залежність get_db для тестів
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_test_db():
    """Створює чисту схему БД перед кожним тестом та очищає після нього."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ---------------------------------------------------------------------------
# ЮНІТ-ТЕСТИ: Безпека та гешування паролів
# ---------------------------------------------------------------------------
def test_unit_password_hashing():
    raw_password = "SecretPassword123!"
    hashed = hash_password(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


# ---------------------------------------------------------------------------
# СЦЕНАРІЙ 1: Анонімний доступ (401 Unauthorized)
# Перевірка отримання статус-коду 401 при спробі доступу до захищених маршрутів
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_anonymous_access_denied_401(client: AsyncClient):
    # 1. Запит до кабінету користувача без токена
    res_user = await client.get("/users/me")
    assert res_user.status_code == 401
    assert "detail" in res_user.json()

    # 2. Запит до панелі адміністратора без токена
    res_admin = await client.get("/admin/dashboard")
    assert res_admin.status_code == 401

    # 3. Запит на створення петиції без токена
    res_create = await client.post("/petitions/", json={"title": "Анонімна петиція", "description": "Опис"})
    assert res_create.status_code == 401

    # 4. Спроба оновлення профілю без токена
    res_profile = await client.put("/users/1", json={"full_name": "Хакер"})
    assert res_profile.status_code == 401


# ---------------------------------------------------------------------------
# СЦЕНАРІЙ 2: Автентифікація та помилки входу (200 OK / 401 Unauthorized)
# Перевірка надання доступу з правильними даними та відмови при помилках
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_authentication_success_and_failures(client: AsyncClient):
    # Реєстрація користувача
    reg_res = await client.post(
        "/auth/register",
        json={"username": "test_citizen", "password": "secure_pass_123", "role": "user"},
    )
    assert reg_res.status_code == 201
    assert reg_res.json()["username"] == "test_citizen"

    # Спроба повторної реєстрації з тим самим іменем (має бути 400 Bad Request)
    reg_dup = await client.post(
        "/auth/register",
        json={"username": "test_citizen", "password": "another_password"},
    )
    assert reg_dup.status_code == 400

    # Помилка входу: невірний пароль -> 401 Unauthorized
    bad_login_res = await client.post(
        "/auth/login",
        data={"username": "test_citizen", "password": "WRONG_PASSWORD"},
    )
    assert bad_login_res.status_code == 401
    assert bad_login_res.json()["detail"] == "Incorrect username or password"

    # Помилка входу: неіснуючий користувач -> 401 Unauthorized
    nonexistent_res = await client.post(
        "/auth/login",
        data={"username": "unknown_user_999", "password": "some_password"},
    )
    assert nonexistent_res.status_code == 401

    # Успішна автентифікація -> 200 OK + валідний JWT access_token
    good_login_res = await client.post(
        "/auth/login",
        data={"username": "test_citizen", "password": "secure_pass_123"},
    )
    assert good_login_res.status_code == 200
    token_data = good_login_res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # Перевірка доступу до власного кабінету з отриманим токеном (200 OK)
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    me_res = await client.get("/users/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["username"] == "test_citizen"
    assert me_res.json()["role"] == "user"


# ---------------------------------------------------------------------------
# СЦЕНАРІЙ 3: Вертикальне розмежування ролей (403 Forbidden)
# Перевірка заборони доступу звичайному користувачу до адмін-панелі
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vertical_role_separation_403(client: AsyncClient):
    # 1. Створюємо звичайного користувача
    await client.post(
        "/auth/register",
        json={"username": "regular_user", "password": "userpass", "role": "user"},
    )
    login_user = await client.post(
        "/auth/login",
        data={"username": "regular_user", "password": "userpass"},
    )
    user_token = login_user.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # 2. Створюємо адміністратора
    await client.post(
        "/auth/register",
        json={"username": "admin_user", "password": "adminpass", "role": "admin"},
    )
    login_admin = await client.post(
        "/auth/login",
        data={"username": "admin_user", "password": "adminpass"},
    )
    admin_token = login_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Спроба звичайного користувача зайти до адмін-панелі -> 403 Forbidden
    forbidden_dashboard = await client.get("/admin/dashboard", headers=user_headers)
    assert forbidden_dashboard.status_code == 403
    assert "Admin privileges required" in forbidden_dashboard.json()["detail"]

    # Спроба звичайного користувача переглянути адмін-статистику -> 403 Forbidden
    forbidden_stats = await client.get("/admin/stats", headers=user_headers)
    assert forbidden_stats.status_code == 403

    # Спроба звичайного користувача переглянути список усіх користувачів -> 403 Forbidden
    forbidden_users = await client.get("/admin/users", headers=user_headers)
    assert forbidden_users.status_code == 403

    # Адміністратор має успішний доступ до адмін-панелі -> 200 OK
    admin_dashboard_ok = await client.get("/admin/dashboard", headers=admin_headers)
    assert admin_dashboard_ok.status_code == 200
    assert admin_dashboard_ok.json()["admin_user"] == "admin_user"

    # Адміністратор має успішний доступ до статистики -> 200 OK
    admin_stats_ok = await client.get("/admin/stats", headers=admin_headers)
    assert admin_stats_ok.status_code == 200
    assert "total_users" in admin_stats_ok.json()


# ---------------------------------------------------------------------------
# СЦЕНАРІЙ 4: Горизонтальне розмежування прав (IDOR) (403 Forbidden)
# Спроба авторизованого користувача змінити дані іншого користувача або чужу сутність
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_horizontal_privilege_separation_idor_403(client: AsyncClient):
    # Реєстрація Користувача А
    await client.post("/auth/register", json={"username": "user_alpha", "password": "password_a", "role": "user"})
    token_a = (await client.post("/auth/login", data={"username": "user_alpha", "password": "password_a"})).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Отримуємо ID користувача А
    user_a_info = (await client.get("/users/me", headers=headers_a)).json()
    user_a_id = user_a_info["id"]

    # Користувач А створює петицію
    create_pet_res = await client.post(
        "/petitions/",
        json={"title": "Петиція Користувача А", "description": "Опис проблеми", "target_votes": 300},
        headers=headers_a,
    )
    assert create_pet_res.status_code == 201
    petition_a_id = create_pet_res.json()["id"]

    # Реєстрація Користувача Б
    await client.post("/auth/register", json={"username": "user_beta", "password": "password_b", "role": "user"})
    token_b = (await client.post("/auth/login", data={"username": "user_beta", "password": "password_b"})).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. IDOR-перевірка сутності предметної області:
    # Користувач Б намагається змінити петицію Користувача А -> 403 Forbidden
    res_idor_pet = await client.put(
        f"/petitions/{petition_a_id}",
        json={"title": "Зламано користувачем Б", "description": "Спроба несанкціонованої модифікації"},
        headers=headers_b,
    )
    assert res_idor_pet.status_code == 403
    assert "You cannot modify someone else's petition" in res_idor_pet.json()["detail"]

    # 2. IDOR-перевірка даних профілю:
    # Користувач Б намагається змінити дані профілю Користувача А -> 403 Forbidden
    res_idor_prof = await client.put(
        f"/users/{user_a_id}",
        json={"full_name": "Ім'я підмінено зловмисником", "email": "hacked@example.com"},
        headers=headers_b,
    )
    assert res_idor_prof.status_code == 403
    assert "You cannot modify another user's profile" in res_idor_prof.json()["detail"]

    # 3. Легітимна зміна: Автор (Користувач А) успішно редагує власну петицію -> 200 OK
    res_own_pet = await client.put(
        f"/petitions/{petition_a_id}",
        json={"title": "Оновлена петиція від автора", "description": "Доповнений опис"},
        headers=headers_a,
    )
    assert res_own_pet.status_code == 200
    assert res_own_pet.json()["title"] == "Оновлена петиція від автора"

    # 4. Легітимна зміна: Користувач А успішно оновлює власний профіль -> 200 OK
    res_own_prof = await client.put(
        f"/users/{user_a_id}",
        json={"full_name": "Тарас Григорович", "email": "taras@patriot.ua"},
        headers=headers_a,
    )
    assert res_own_prof.status_code == 200
    assert res_own_prof.json()["full_name"] == "Тарас Григорович"


# ---------------------------------------------------------------------------
# БІЗНЕС-ЛОГІКА MVP: Підписання петицій та запобігання дублікатам
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mvp_business_logic_voting_and_moderation(client: AsyncClient):
    # Реєстрація двох користувачів та адміністратора
    await client.post("/auth/register", json={"username": "voter_1", "password": "pass1", "role": "user"})
    token_v1 = (await client.post("/auth/login", data={"username": "voter_1", "password": "pass1"})).json()["access_token"]
    headers_v1 = {"Authorization": f"Bearer {token_v1}"}

    await client.post("/auth/register", json={"username": "voter_2", "password": "pass2", "role": "user"})
    token_v2 = (await client.post("/auth/login", data={"username": "voter_2", "password": "pass2"})).json()["access_token"]
    headers_v2 = {"Authorization": f"Bearer {token_v2}"}

    await client.post("/auth/register", json={"username": "admin_mod", "password": "adminpass", "role": "admin"})
    token_admin = (await client.post("/auth/login", data={"username": "admin_mod", "password": "adminpass"})).json()["access_token"]
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    # Створення петиції
    res_pet = await client.post(
        "/petitions/",
        json={"title": "Облаштування набережної", "description": "Просимо створити пішохідну зону", "target_votes": 100},
        headers=headers_v1,
    )
    pet_id = res_pet.json()["id"]

    # Перший голос (voter_1) -> 201 Created
    vote_1 = await client.post(f"/petitions/{pet_id}/vote", json={}, headers=headers_v1)
    assert vote_1.status_code == 201
    assert vote_1.json()["status"] == "success"

    # Спроба повторного голосування тим самим користувачем -> 400 Bad Request
    vote_dup = await client.post(f"/petitions/{pet_id}/vote", json={}, headers=headers_v1)
    assert vote_dup.status_code == 400
    assert "Duplicate vote" in vote_dup.json()["detail"]

    # Другий голос від іншого користувача (voter_2) -> 201 Created
    vote_2 = await client.post(f"/petitions/{pet_id}/vote", json={}, headers=headers_v2)
    assert vote_2.status_code == 201

    # Перевірка списку петицій: votes_count має дорівнювати 2
    res_list = await client.get("/petitions/")
    assert res_list.status_code == 200
    pet_item = next(p for p in res_list.json() if p["id"] == pet_id)
    assert pet_item["votes_count"] == 2

    # Звичайний користувач НЕ може змінити статус петиції -> 403 Forbidden
    status_forbidden = await client.patch(f"/petitions/{pet_id}/status", json={"status": "approved"}, headers=headers_v1)
    assert status_forbidden.status_code == 403

    # Адміністратор успішно змінює статус петиції -> 200 OK
    status_admin_ok = await client.patch(f"/petitions/{pet_id}/status", json={"status": "approved"}, headers=headers_admin)
    assert status_admin_ok.status_code == 200
    assert status_admin_ok.json()["status"] == "approved"
