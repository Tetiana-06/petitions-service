# ЗВІТ ПРО ВИКОНАННЯ ЛАБОРАТОРНОЇ РОБОТИ №5

**Тема:** Контейнеризація веб-системи за допомогою Docker.  
**Мета:** Запакувати застосунок у набір ізольованих Docker-контейнерів, налаштувати мультиконтейнерну оркестрацію за допомогою `docker-compose.yml` та забезпечити запуск усієї системи однією командою.  
**Проєкт:** Сервіс місцевих електронних петицій (`petitions-service`)  
**Стек:** Python 3.11, FastAPI, Uvicorn, SQLAlchemy (async), PostgreSQL 16, Docker 29, Docker Compose.

---

## Структура доданих файлів

| Файл | Призначення |
|---|---|
| `Dockerfile` | Багатоетапне збирання образу бекенду |
| `.dockerignore` | Виключення зайвих файлів із контексту збирання |
| `docker-compose.yml` | Опис сервісів `web` і `db`, volume, мережі, healthcheck |
| `docker-compose.override.yml` | Режим розробки: bind mount + `--reload` |
| `.env.docker.example` | Шаблон змінних оточення (копіюється у `.env`) |

Зміни в коді застосунку:
- `requirements.txt` — додано асинхронний драйвер PostgreSQL `asyncpg`.
- `src/models.py` — колонки дат змінено на `DateTime(timezone=True)`, бо `asyncpg` не приймає datetime з часовою зоною в колонку `TIMESTAMP WITHOUT TIME ZONE`.
- `src/init_db.py` — цикл `ALTER TABLE ... ADD COLUMN` (міграція старих SQLite-баз) виконується лише для SQLite: у PostgreSQL помилка в цьому циклі скасувала б усю транзакцію разом зі створенням таблиць.
- `src/main.py` — `/health` тепер показує лише назву БД. Раніше для URL PostgreSQL він показав би весь рядок підключення разом із паролем.

---

## 1. Dockerfile для бекенд-додатка

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src ./src
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- **Базовий образ:** `python:3.11-slim` — офіційний образ Debian без зайвих пакетів. Обрано замість `alpine`, бо для `slim` (glibc) є готові wheel-пакети `bcrypt`, `asyncpg`, `greenlet`, а на `alpine` (musl) їх часто доводиться компілювати.
- **Робоча директорія:** `WORKDIR /app`. Код лежить у `/app/src`, тому імпорти `from src...` працюють так само, як і локально.
- **Змінні Python:** `PYTHONDONTWRITEBYTECODE=1` вимикає створення `.pyc`, `PYTHONUNBUFFERED=1` вимикає буферизацію, щоб логи одразу з'являлися в `docker compose logs`.
- **Кешування шарів:** спочатку копіюється лише `requirements.txt` і встановлюються залежності, а вже потім код. Якщо змінився тільки код, шар із залежностями береться з кешу і перезбирання займає секунди.
- **Команда запуску:** `uvicorn src.main:app --host 0.0.0.0 --port 8000`. Адреса `0.0.0.0` потрібна, щоб сервер приймав з'єднання ззовні контейнера, а не лише з `localhost` усередині нього.

### `.dockerignore`

```
.git  .github  .idea  .vscode  venv  .venv  __pycache__  *.py[cod]
.pytest_cache  .ruff_cache  *.log  *.db  .env  .env.*
reports  docs  tests  *.md  img.png  locustfile.py
```

- `.git`, `__pycache__`, `*.log`, `venv` — історія, кеш і логи не потрібні для роботи сервера, а лише збільшують контекст збирання.
- `.env`, `.env.*` — **секрети не потрапляють в образ**. Змінні передаються контейнеру під час запуску через `env_file`.
- `*.db` — локальні SQLite-бази розробника не копіюються в образ.
- `tests`, `docs`, `reports`, `*.md`, `locustfile.py` — у робочому образі не потрібні.

---

## 2. Контейнеризація та ізоляція бази даних

```yaml
db:
  image: postgres:16-alpine
  env_file: .env
  volumes:
    - pgdata:/var/lib/postgresql/data
  networks:
    - backend
```

- **Офіційний образ:** `postgres:16-alpine`. Під час першого запуску він сам створює користувача та базу з `POSTGRES_USER`, `POSTGRES_PASSWORD` і `POSTGRES_DB`.
- **Ізоляція:** порт 5432 **не публікується** на хост (`ports` відсутній). До бази можна звернутися лише з внутрішньої мережі `backend`, тобто тільки з контейнера `web`.
- **Збереження даних (Data Persistence):** іменований volume `pgdata` змонтовано в `/var/lib/postgresql/data`, де PostgreSQL зберігає файли бази. Volume існує окремо від контейнера, тому дані залишаються після `docker compose down`, після видалення контейнера і після перезбирання образу. Видалити їх можна лише явно: `docker compose down -v`.

**Перевірка:** створено петицію → `docker compose down` → `docker compose up -d` → петиція на місці (4 петиції до перезапуску і 4 після).

---

## 3. Оркестрація через docker-compose.yml

```yaml
services:
  db:
    image: postgres:16-alpine
    env_file: .env
    volumes: [pgdata:/var/lib/postgresql/data]
    networks: [backend]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10

  web:
    build: .
    env_file: .env
    ports: ["${APP_PORT:-8000}:8000"]
    networks: [backend]
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

volumes:
  pgdata:

networks:
  backend:
```

### 3.1. Змінні оточення з `.env`
Обидва сервіси отримують змінні через `env_file: .env`. Сам файл `.env` внесено в `.gitignore`, тому в репозиторії лежить лише шаблон `.env.docker.example`:

```
POSTGRES_USER=petitions
POSTGRES_PASSWORD=change-me
POSTGRES_DB=petitions
APP_ENV=docker
DEBUG=False
DATABASE_URL=postgresql+asyncpg://petitions:change-me@db:5432/petitions
SECRET_KEY=change-me-docker-secret-key
...
```

Код застосунку для цього не змінювався: `pydantic-settings` з Лаб. 3 читає змінні оточення процесу, а вони мають пріоритет над `.env`-файлами. У `DATABASE_URL` хостом вказано `db`, тобто ім'я сервісу. Docker DNS перетворює його на IP-адресу контейнера бази.

### 3.2. Внутрішня мережа
Створено мережу `backend` типу bridge, до якої підключено обидва сервіси. Вони звертаються один до одного за іменем сервісу, а назовні відкритий лише порт `web` (8000). Порт бази не публікується, тож підключитися до неї з хоста чи з інтернету неможливо.

### 3.3. Черговість запуску (depends_on + healthcheck)
Звичайний `depends_on` чекає лише **старту** контейнера БД, але PostgreSQL після старту ще кілька секунд ініціалізується. Якщо застосунок підключиться в цей момент, `init_models()` у `lifespan` завершиться помилкою.

Тому:
1. `db` має `healthcheck` на основі `pg_isready`, який повертає успіх, лише коли база приймає з'єднання (`$$` екранує `$`, щоб змінну підставив shell контейнера, а не Compose).
2. `web` використовує `depends_on: condition: service_healthy`, тобто запускається тільки після статусу `healthy` у `db`.
3. `web` має власний healthcheck на `/health`, тож `docker compose ps` показує, чи справді API відповідає.

Журнал запуску це підтверджує:
```
Container petitions-service-db-1 Waiting
Container petitions-service-db-1 Healthy
Container petitions-service-web-1 Starting
```

### 3.4. Порт хоста
Порт хоста можна змінити змінною `APP_PORT` (за замовчуванням 8000). Наприклад, `APP_PORT=8001 docker compose up --build`, якщо 8000 уже зайнятий іншим застосунком.

---

## 4. Перевірка та розгортання

Запуск:
```bash
cp .env.docker.example .env
docker compose up --build
```

Результати перевірки:

| Перевірка | Результат |
|---|---|
| `docker compose ps` | `db` — `Up (healthy)`, `web` — `Up (healthy)` |
| Міграції (створення таблиць) | Лог: `[DOCKER] Таблиці успішно ініціалізовано!`; `psql \dt` показує таблиці `users`, `petitions`, `votes` |
| Демо-дані | Лог: `Початкові демо-дані успішно завантажено!` |
| `GET /health` | `{"status":"ok","environment":"docker","debug":false,"database":"petitions"}` |
| `POST /auth/login` (pavlo) | JWT-токен отримано |
| `POST /petitions/` | `201`, петицію з `id=4` записано в PostgreSQL |
| `GET /petitions/` | 4 петиції |
| `down` → `up` | 4 петиції — дані збережено у volume |
| `pytest` (локально, SQLite) | 12 passed — зміни моделей не зламали тести |

Swagger-документація доступна за адресою `http://localhost:8000/docs`.

---

## 5. Додаткове завдання 1: Multi-stage Build

Dockerfile складається з двох етапів:

1. **`builder`** — встановлюється `build-essential` (gcc, make, заголовкові файли), а потім усі залежності через `pip install --prefix=/install`. Ключ `--prefix` складає пакети в окрему теку `/install`, щоб їх можна було скопіювати одним шаром.
2. **Фінальний етап** — чистий `python:3.11-slim`, у який копіюється лише `/install` (`COPY --from=builder /install /usr/local`) та код `src`.

У фінальний образ **не потрапляють** компілятор, списки пакетів `apt`, кеш `pip` (`--no-cache-dir`) і тимчасові файли збирання. Лише `build-essential` важить понад 200 МБ. Підсумковий розмір образу — **418 МБ**. Більшу частину займають залежності з `requirements.txt`, зокрема інструменти розробки (`locust`, `pytest`, `ruff`, `pre-commit`), які можна винести в окремий файл, щоб зменшити образ ще більше.

---

## 6. Додаткове завдання 2: Hot-Reload у режимі розробки

```yaml
# docker-compose.override.yml
services:
  web:
    volumes:
      - ./src:/app/src
    command: ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

- **Bind mount** `./src:/app/src` накладає локальну теку з кодом поверх скопійованої в образ. Контейнер бачить зміни файлів одразу, без перезбирання.
- **`--reload`** змушує Uvicorn стежити за файлами і перезапускати сервер після кожної зміни.
- Compose **автоматично** об'єднує `docker-compose.override.yml` з основним файлом, тому `docker compose up --build` запускає режим розробки. Для production-подібного запуску без bind mount і без `--reload` override-файл не використовується:
  ```bash
  docker compose -f docker-compose.yml up --build
  ```

**Перевірка:** у `src/schemas.py` додано рядок при запущеному контейнері, і в логах з'явилося:
```
WARNING:  StatReload detected changes in 'src/schemas.py'. Reloading...
```
Uvicorn використовує `StatReload` (опитування часу зміни файлів). Цей механізм коректно працює з bind mount на Windows, де події файлової системи inotify з хоста в контейнер не передаються.

---

## 7. Алгоритм демонстрації

Демонстрацію починаємо з чистого стану, щоб було видно повну ініціалізацію бази: `docker compose down -v`.

1. **Запуск однією командою.** Виконати `cp .env.docker.example .env` і `docker compose up --build -d`. Показати, що образ збирається у два етапи (`builder` і фінальний).
2. **Черговість запуску.** У виводі команди видно `db-1 Waiting` → `db-1 Healthy` → `web-1 Starting`: застосунок стартує лише після healthcheck бази.
3. **Стан контейнерів.** `docker compose ps`: обидва сервіси мають статус `Up (healthy)`. У колонці `PORTS` порт є лише в `web` (`0.0.0.0:8000->8000`), у `db` його немає.
4. **Ініціалізація БД.** `docker compose logs web`: рядки `Таблиці успішно ініціалізовано!` і `Початкові демо-дані успішно завантажено!`. Потім `docker compose exec db psql -U petitions -d petitions -c "\dt"` показує таблиці `users`, `petitions`, `votes`.
5. **Робота API.** Відкрити `http://localhost:8000/health`: `"environment":"docker"`, `"database":"petitions"`, пароля у відповіді немає. Відкрити `http://localhost:8000/docs`, натиснути **Authorize**, увійти як `pavlo` / `user123` і через `POST /petitions/` створити петицію (відповідь `201`). `GET /petitions/` показує її у списку.
6. **Ізоляція бази.** На хості виконати `Test-NetConnection localhost -Port 5432` (PowerShell) або `nc -zv localhost 5432`: з'єднання не встановлюється, бо порт бази не опубліковано.
7. **Збереження даних.** `docker compose down` (контейнери видалено), потім `docker compose up -d`. `GET /petitions/` знову показує створену петицію, бо дані лежать у volume `pgdata` (`docker volume ls`).
8. **Секрети поза образом.** `docker compose exec web ls -a /app`: є лише `src`, файлу `.env` в образі немає. `git status` підтверджує, що `.env` не відстежується Git.
9. **Multi-stage build.** `docker images`: розмір образу ~418 МБ. `docker compose exec web which gcc` нічого не повертає, отже компілятора у фінальному образі немає.
10. **Hot-reload.** Запустити `docker compose logs -f web`, змінити будь-який файл у `src/` і зберегти. У логах з'явиться `StatReload detected changes ... Reloading...`, а зміна стане доступною без перезбирання образу.
11. **Завершення.** `docker compose down` зупиняє систему зі збереженням даних, `docker compose down -v` видаляє також volume з базою.

---

## Висновки

Застосунок і PostgreSQL розгорнуто в окремих ізольованих контейнерах, а вся система піднімається однією командою `docker compose up --build`. Дані бази зберігаються в іменованому volume і переживають перезапуск та видалення контейнерів. Секрети передаються через `.env` і не потрапляють ні в Git, ні в образ. Порядок запуску гарантують healthcheck і `depends_on: service_healthy`, а база доступна лише через внутрішню мережу. Багатоетапне збирання прибрало з образу компілятор і тимчасові файли, а override-файл з bind mount і `--reload` дає змогу розробляти без перезбирання образу.

---

## Додаток: сценарій демонстрації

### Підготовка

Відкрити в редакторі `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml` і `.dockerignore`, щоб показати їх за потреби.

### Хід демонстрації

| # | Команда / дія | Що показати |
|---|---|---|
| 0 | `docker compose down -v` | Чистий стан: бази ще немає |
| 1 | `cp .env.docker.example .env`, потім `docker compose up --build -d` | Уся система запускається однією командою. У виводі збирання видно два етапи: `builder` і фінальний (multi-stage) |
| 2 | Той самий вивід | `db-1 Waiting` → `db-1 Healthy` → `web-1 Starting`: бекенд чекає, поки healthcheck бази стане healthy (`depends_on: service_healthy`) |
| 3 | `docker compose ps` | Обидва сервіси `Up (healthy)`. Порт є лише в `web`, у `db` колонка `PORTS` порожня |
| 4 | `docker compose logs web` | Рядки `Таблиці успішно ініціалізовано!` і `Початкові демо-дані успішно завантажено!` |
| 4б | `docker compose exec db psql -U petitions -d petitions -c "\dt"` | Таблиці `users`, `petitions`, `votes` створено в PostgreSQL |
| 5 | Браузер: `http://localhost:8000/health` | `"environment":"docker"`, `"database":"petitions"`, пароля у відповіді немає |
| 5б | `http://localhost:8000/docs` → **Authorize** (`pavlo` / `user123`) → `POST /petitions/` | Відповідь `201`, створену петицію видно в `GET /petitions/` |
| 6 | `Test-NetConnection localhost -Port 5432` | `TcpTestSucceeded : False`: база недоступна ззовні, лише з внутрішньої мережі `backend` |
| 7 | `docker compose down`, потім `docker compose up -d`, потім знову `GET /petitions/` | Петиція з кроку 5б на місці. `docker volume ls` показує volume `petitions-service_pgdata` |
| 8 | `docker compose exec web ls -a /app`, `git check-ignore .env` | В образі є лише `src`, файлу `.env` немає. Git ігнорує `.env`: секрети не потрапляють ні в образ, ні в репозиторій |
| 9 | `docker images`, `docker compose exec web gcc --version` | Розмір образу ~418 МБ. Друга команда завершується помилкою `executable file not found`: компілятора у фінальному образі немає, він залишився на етапі `builder` |
| 10 | `docker compose logs -f web`, змінити файл у `src/` (наприклад, текст у `/health` в `src/main.py`) і зберегти | У логах `StatReload detected changes ... Reloading...`. Після оновлення `/health` у браузері видно зміну без перезбирання образу (hot-reload) |
| 11 | `docker compose down` | Зупинка системи зі збереженням даних (`-v` видалив би й volume) |

### Ключові докази виконання

1. **Одна команда** `docker compose up --build` піднімає всю систему.
2. **Черговість запуску:** `Waiting → Healthy → Starting`.
3. **Збереження даних:** петиція залишається після `down` / `up`.
4. **Ізоляція бази:** у `docker compose ps` немає порту в `db`, а `Test-NetConnection` повертає `False`.

### Можливі запитання

- **Чому `slim`, а не `alpine`?** Для `slim` (glibc) є готові wheel-пакети `bcrypt` і `asyncpg`, а на `alpine` (musl) їх довелося б компілювати.
- **Навіщо `--host 0.0.0.0`?** Щоб сервер приймав з'єднання ззовні контейнера, а не лише з `localhost` усередині нього.
- **Навіщо `$$` у healthcheck?** Щоб змінну підставив shell контейнера, а не Compose під час читання файлу.
