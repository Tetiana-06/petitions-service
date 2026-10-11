# ЗВІТ ПРО ВИКОНАННЯ ЛАБОРАТОРНОЇ РОБОТИ №3

**Тема:** Розділення конфігурацій для тестового і робочого середовищ. Впровадження CI/CD.  
**Мета:** Опанувати методики безпечного керування конфігураціями системи, навчитися розділяти тестове і робоче середовища. Навчитися налаштувати базовий Continuous Delivery.  
**Проєкт:** Сервіс місцевих електронних петицій (`petitions-service`)  
**Стек:** Python 3.12/3.14, FastAPI, Pydantic-Settings, SQLAlchemy, Pytest, Ruff, GitHub Actions.

---

## 1. ОГЛЯД ТА МІСЦЕ РЕАЛІЗАЦІЇ ЗАВДАНЬ

| Завдання | Де реалізовано у проєкті | Суть реалізованого рішення |
| :--- | :--- | :--- |
| **1. Розділення конфігурацій** | [`src/config.py`](src/config.py)<br>[`.env.sandbox`](.env.sandbox)<br>[`.env.production`](.env.production)<br>[`.env.example`](.env.example) | Усі hardcoded значення вилучено з коду. Використано `pydantic-settings` (`BaseSettings`). Зчитування потрібного файлу здійснюється автоматично залежно від змінної `APP_ENV` (`sandbox` чи `production`). |
| **2. Ізоляція баз даних** | [`src/database.py`](src/database.py)<br>[`src/init_db.py`](src/init_db.py) | Для кожного середовища визначено окремий URL: `petitions_sandbox.db` та `petitions_production.db`. Демо-дані завантажуються виключно в пісочниці (`SEED_DEMO_DATA=True`), у production база залишається чистою (`SEED_DEMO_DATA=False`). |
| **3. Режими безпеки та 500 помилки** | [`src/main.py`](src/main.py#L53-L85) | `DEBUG=False` для Production. Реалізовано централізоване HTTP-middleware перехоплення непередбачених помилок: у Production при 500 внутрішній стектрейс приховується та повертається безпечне повідомлення. |
| **4. Документування** | [`README.md`](README.md) | Оновлено документацію: наведено чіткі інструкції для запуску в Sandbox та Production, змінні оточення та опис пайплайну. |
| **5. CI/CD пайплайн (Додаткове)** | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | Створено GitHub Actions пайплайн (тригери: `push` та `pull_request` до `main`). Виконує автоматичну перевірку лінтерами Ruff та прогін 12 тестів `pytest`. |

---

## 2. ПОЯСНЕННЯ ПРИНЦИПУ РОБОТИ

### 2.1. Керування середовищами (`src/config.py`)
Клас `Settings` наслідує `BaseSettings` з бібліотеки `pydantic-settings`:
- Функція `get_env_file_path()` зчитує системну змінну `APP_ENV` (за замовчуванням `sandbox`) та завантажує файл `.env.sandbox` або `.env.production`.
- **Sandbox:** `DEBUG=True`, `SEED_DEMO_DATA=True`, база `petitions_sandbox.db`.
- **Production:** `DEBUG=False`, `SEED_DEMO_DATA=False`, база `petitions_production.db`, коротший час життя JWT-токенів (30 хв).

### 2.2. Ізоляція баз даних (`src/database.py` та `src/init_db.py`)
- Функція `resolve_database_url()` гарантує точне відкриття відповідного файлу БД незалежно від робочої директорії.
- У функції `seed_data()` встановлено умову:
  ```python
  if not settings.SEED_DEMO_DATA:
      print(f"[{settings.APP_ENV.upper()}] Пропуск завантаження демо-даних (SEED_DEMO_DATA=False)")
      return
  ```
  Це запобігає витоку або засміченню робочої бази тестовими даними.

### 2.3. Безпека та обробка помилок 500 (`src/main.py`)
Для захисту від витоку внутрішніх деталей архітектури та стек-трейсів застосовано HTTP-middleware:
```python
@app.middleware("http")
async def security_exception_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        logger.error(f"Internal unhandled error: {exc}", exc_info=True)
        if settings.DEBUG:
            return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "debug_error": str(exc)})
        return JSONResponse(status_code=500, content={"detail": "Внутрішня помилка сервера. Будь ласка, зверніться до служби підтримки."})
```
Для демонстрації додано тестовий маршрут `GET /system/trigger-error`.

### 2.4. CI/CD Пайплайн (`.github/workflows/ci.yml`)
Пайплайн налаштовано у GitHub Actions. Складається з двох зв'язаних робіт:
1. **lint:** перевіряє код за допомогою `ruff check src tests` та `ruff format --check src tests`.
2. **test:** виконує `pytest -v` у чистому віртуальному оточенні після успішного лінтингу.

---

## 3. ЯК ПРОДЕМОНСТРУВАТИ ВИКОНАНИЙ ФУНКЦІОНАЛ

### 1. Демонстрація тестового середовища (Sandbox)
У терміналі:
```powershell
$env:APP_ENV="sandbox"
uvicorn src.main:app --reload --port 8000
```
- Відкрийте `http://localhost:8000/`.
- У верхньому барі відобразиться зелений бейдж: `SANDBOX 🛠️ (DEBUG: ON)`.
- База даних містить тестові петиції та користувачів (`ivan_patriot`, `admin`).
- На «Стенді безпеки» (картка 5) натисніть `💥 Викликати збій 500` — консоль покаже діагностичну інформацію розробника.

### 2. Демонстрація робочого середовища (Production)
У терміналі:
```powershell
$env:APP_ENV="production"
uvicorn src.main:app --port 8000
```
- Відкрийте `http://localhost:8000/`.
- У верхньому барі відобразиться червоний бейдж: `PRODUCTION 🛡️ (DEBUG: OFF)`.
- Використовується ізольована база `petitions_production.db` без тестових записів.
- Натисніть `💥 Викликати збій 500` — сервер поверне статус **500**, але внутрішній стектрейс **повністю приховано**, користувач бачить лише безпечне загальне повідомлення.

### 3. Автоматизоване тестування Pytest (12 тестів)
```bash
pytest -v
```
**Результат:**
```text
tests/test_auth_access.py::test_unit_password_hashing PASSED             [  8%]
tests/test_auth_access.py::test_anonymous_access_denied_401 PASSED       [ 16%]
tests/test_auth_access.py::test_authentication_success_and_failures PASSED [ 25%]
tests/test_auth_access.py::test_vertical_role_separation_403 PASSED      [ 33%]
tests/test_auth_access.py::test_horizontal_privilege_separation_idor_403 PASSED [ 41%]
tests/test_auth_access.py::test_mvp_business_logic_voting_and_moderation PASSED [ 50%]
tests/test_lab3_config_cicd.py::test_sandbox_configuration_loading PASSED [ 58%]
tests/test_lab3_config_cicd.py::test_production_configuration_loading PASSED [ 66%]
tests/test_lab3_config_cicd.py::test_database_isolation_between_environments PASSED [ 75%]
tests/test_lab3_config_cicd.py::test_500_error_masks_stacktrace_in_production PASSED [ 83%]
tests/test_lab3_config_cicd.py::test_500_error_reveals_debug_in_sandbox PASSED [ 91%]
tests/test_lab3_config_cicd.py::test_system_env_endpoints PASSED         [100%]
============================= 12 passed in 4.89s ==============================
```

### 4. Перевірка CI/CD лінтерів локально
```bash
ruff check src tests
ruff format --check src tests
# All checks passed! 10 files already formatted.
```

---

## 4. ВИСНОВКИ

1. Усунено всі захардкоджені параметри та реалізовано динамічне завантаження конфігурацій через змінні оточення та бібліотеку `pydantic-settings`.
2. Забезпечено повну ізоляцію баз даних для Sandbox та Production середовищ.
3. Налаштовано надійну обробку 500 помилок із маскуванням стек-трейсів для запобігання витоку конфіденційної інформації у Production.
4. Розроблено та протестовано автоматизований CI/CD пайплайн на основі GitHub Actions, що гарантує контроль якості коду та успішне проходження всіх 12 тестів.
