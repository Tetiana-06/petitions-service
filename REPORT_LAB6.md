# ЗВІТ ПРО ВИКОНАННЯ ЛАБОРАТОРНОЇ РОБОТИ №6

**Тема:** Балансування навантаження за допомогою Nginx.
**Мета:** Налаштувати Nginx як зворотний проксі та балансувальник, розгорнути кілька реплік застосунку й рівномірно розподілити між ними трафік.
**Проєкт:** Сервіс місцевих електронних петицій (`petitions-service`).

---

## Що змінено

| Файл | Зміна |
|---|---|
| `docker-compose.yml` | `web`: `deploy.replicas: 3`, прибрано публікацію порту; додано сервіс `nginx` (порт 80) |
| `nginx/nginx.conf` | `upstream backend` + `server` з `proxy_pass`, пасивний health check |
| `src/main.py` | `/health` повертає `hostname` — ID контейнера, що обробив запит |

Схема: `клієнт → nginx:80 → upstream backend → web-1 / web-2 / web-3 → db`

---

## 1. Репліки застосунку

```yaml
web:
  build: .
  deploy:
    replicas: 3
  restart: on-failure
```

Порт `8000` більше не публікується на хост: три репліки не можуть зайняти один порт, і вхід має бути лише через балансувальник.

Ідентифікація сервера — у `/health`:
```python
"hostname": socket.gethostname(),  # у Docker = короткий ID контейнера
```

**Запуск:**
```powershell
docker compose -f docker-compose.yml up -d --build
docker compose ps
```
📸 **Зафіксувати:** вивід `docker compose ps` — три контейнери `petitions-service-web-1..3` у стані `healthy` та `nginx` з портом `0.0.0.0:80->80`.

---

## 2. Nginx як Load Balancer

```nginx
upstream backend {
    server web:8000 max_fails=1 fail_timeout=15s;
}

server {
    listen 80;
    location / {
        proxy_pass http://backend;
        proxy_connect_timeout 1s;
        proxy_next_upstream error timeout http_502 http_503;
        add_header X-Upstream $upstream_addr always;
    }
}
```

- `upstream backend` — група серверів. Ім'я `web` вбудований DNS Docker перетворює на IP **усіх трьох** реплік, і nginx додає кожну як окремий сервер групи.
- `server { listen 80; proxy_pass http://backend; }` — єдина точка входу, яка передає запити в групу.
- `X-Upstream` — заголовок із IP репліки, яка відповіла (для наочності).

📸 **Зафіксувати:** IP реплік у групі (має бути 3 рядки `Address:`):
```powershell
docker compose exec nginx nslookup web
```
_(`getent hosts web` не підходить — показує лише першу адресу.)_

---

## 3. Round Robin

Алгоритм не вказано, тому nginx використовує Round Robin — запити йдуть по колу.

```powershell
1..12 | % { (Invoke-RestMethod http://localhost/health).hostname }
```

**Результат:** 
```
cf7ba576c630
26bac5defe24
657a5373f133
cf7ba576c630
26bac5defe24
657a5373f133
cf7ba576c630
26bac5defe24
657a5373f133
cf7ba576c630
26bac5defe24
657a5373f133
```
✅ **Висновок:** три різні `hostname` чергуються в однаковому порядку, кожна репліка отримала 4 з 12 запитів.

---

## 4. Відмовостійкість (Health Checks)

Nginx OSS має **пасивні** перевірки: якщо до репліки не вдалося під'єднатися (`max_fails=1`), вона виключається з ротації на `fail_timeout=15s`. Запит, що впав, nginx повторює на наступній репліці (`proxy_next_upstream`), тому клієнт помилки не бачить.

```powershell
docker stop petitions-service-web-2
1..12 | % { $r = Invoke-WebRequest http://localhost/health -UseBasicParsing; "$($r.StatusCode) $(($r.Content | ConvertFrom-Json).hostname)" }
docker compose logs nginx --tail 5
```

**Результат:** _(вставити свій вивід)_
```
200 cf7ba576c630
200 26bac5defe24
200 cf7ba576c630
200 26bac5defe24
200 cf7ba576c630
200 26bac5defe24
200 cf7ba576c630
200 26bac5defe24
200 cf7ba576c630
200 26bac5defe24
200 cf7ba576c630
200 26bac5defe24
```
Лог nginx: `connect() failed (113: Host is unreachable) while connecting to upstream ... upstream: "http://172.x.x.x:8000/health"`

✅ **Висновок:** усі відповіді `200`, трафік ділиться лише між двома живими репліками; nginx сам виявив збій (видно в лозі) і виключив репліку.

Повернення: `docker start petitions-service-web-2` — через `fail_timeout` репліка знову з'явиться в ротації.

---

## Додаткове 1. IP Hash

У `nginx/nginx.conf` розкоментувати `ip_hash;` у блоці `upstream`, потім:
```powershell
docker compose restart nginx
1..12 | % { (Invoke-RestMethod http://localhost/health).hostname }
```
**Результат:** усі 12 відповідей мають **однаковий** `hostname`.

✅ **Висновок:** `ip_hash` прив'язує клієнта до однієї репліки за IP (sticky sessions) — корисно, коли сесія зберігається в пам'яті сервера. Нашому сервісу це не потрібно (JWT без стану), тому для роботи повертаємо Round Robin (закоментувати `ip_hash;` і перезапустити nginx).

---

## Додаткове 2. Порівняння: 1 репліка vs 3 репліки

Використано сценарій із Лаб. №4 (`locustfile.py`, фіксований профіль 60 с, пік 40 користувачів). Обидва прогони — через той самий nginx, тому різниця лише в кількості реплік.

```powershell
# 3 репліки
locust -f locustfile.py --headless --host http://localhost --csv reports/lab6_3replicas

# 1 репліка (після зміни кількості реплік nginx треба перезапустити — він резолвить "web" при старті)
docker compose -f docker-compose.yml up -d --scale web=1
docker compose restart nginx
locust -f locustfile.py --headless --host http://localhost --csv reports/lab6_1replica
```
Значення взяти з рядка `Aggregated` у `reports/lab6_*_stats.csv`.

| Показник (Aggregated) | 1 репліка | 3 репліки | Зміна |
|---|---|---|---|
| Запитів усього | 915 | 974 | +6 % |
| RPS | 15.17 | 16.12 | +6 % |
| Середня затримка, мс | 309 | 215 | **−30 %** |
| Медіана (p50), мс | 12 | 25 | +13 мс |
| p95, мс | 2800 | 1300 | **−54 %** |
| p99, мс | 5800 | 4500 | −22 % |
| Максимум, мс | 6488 | 5582 | −14 % |
| Помилки | 0 | 0 | — |

Найважчий запит — логін (bcrypt):

| `POST /auth/login` | 1 репліка | 3 репліки |
|---|---|---|
| Медіана, мс | 3300 | 1800 (−45 %) |
| Середня, мс | 3244 | 2397 (−26 %) |

✅ **Висновок:**
- **Затримка під піком помітно нижча:** p95 зменшився з 2.8 с до 1.3 с, а середня затримка — на 30 %. Одна репліка є одним процесом Python, і CPU-важкі запити (bcrypt при логіні) стають у чергу. З трьома репліками їх паралельно обробляють три процеси, тому найбільше виграв саме логін (медіана −45 %).
- **RPS майже не змінився (+6 %).** Locust генерує фіксовану кількість користувачів (пік 40) з паузою 0.5–2 с між запитами, тому RPS обмежує сам сценарій, а не сервер. Навіть одна репліка встигала обробити цей потік без помилок, тільки повільніше. Щоб побачити приріст пропускної здатності, потрібне навантаження, яке насичує одну репліку.
- **Медіана трохи зросла (12 → 25 мс).** Легкі запити й так швидкі, а три контейнери на одному комп'ютері конкурують за ті самі ядра CPU та одну PostgreSQL. Різниця в мілісекунди на загальний результат не впливає.
- Помилок немає в обох конфігураціях.

Головна користь від реплік у цьому тесті — **стабільніша затримка під сплеском трафіку** (менші «хвости» p95/p99). Пропускна здатність у цьому сценарії не зросла, бо RPS обмежував сам сценарій, а не сервер.

---

## Загальний висновок

Розгорнуто 3 репліки бекенду за Nginx. Round Robin рівномірно розподіляє запити (видно за `hostname`), зупинка однієї репліки не призводить до помилок у клієнта — nginx автоматично виключає її з ротації. Досліджено `ip_hash` та порівняно продуктивність 1 і 3 реплік.
