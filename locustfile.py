# Сценарій навантажувального тестування (Locust) для Лабораторної роботи №4
# ТЕМА: Сервіс місцевих електронних петицій
# СЦЕНАРІЙ: Різкий стрибок трафіку після публікації посилання на петицію
#           в популярному Telegram-каналі з необхідністю суворої криптографічної
#           перевірки унікальності голосів.

import hashlib
import random

from locust import HttpUser, LoadTestShape, between, task

VIRAL_PETITION_ID = 1  # ID вірусної петиції, на яку опубліковано посилання в Telegram
TELEGRAM_CHANNEL_URL = "https://t.me/city_news_channel/12345"


# Користувач із Telegram
# Джерело переходу: запити надсилаються із заголовком Referer: https://t.me/city_news_channel/12345 (імітація переходу за посиланням із каналу)
# 60% запитів: відкриття тексту вірусної петиції GET /petitions/1.
# 40% запитів: голосування POST /petitions/1/vote із передачею унікального хешу hashlib.sha256.
class TelegramViralCitizenUser(HttpUser):
    """
    Імітує мобільного користувача, який перейшов за посиланням із Telegram-каналу:
    1. Відкриває безпосередньо вірусну петицію (GET /petitions/1 з Referer Telegram).
    2. Авторизується або отримує JWT-токен.
    3. Здійснює криптографічне підписання петиції з формуванням SHA-256 хешу підпису.
    4. Сервер виконує сувору криптографічну перевірку унікальності голосу в БД.
    """

    # Швидка реакція мобільного користувача (0.5 - 2.0 секунди)
    wait_time = between(0.5, 2.0)

    def on_start(self):
        """Ініціалізація сесії: вхід у систему під одним із тестових акаунтів."""
        self.username = random.choice(["pavlo", "khrystyna", "tetiana"])
        self.password = "admin123" if self.username == "tetiana" else "user123"
        self.token = None
        self.login()

    def login(self):
        """Авторизація та отримання JWT токена для підписання."""
        res = self.client.post(
            "/auth/login",
            data={"username": self.username, "password": self.password},
            name="[Auth] POST /auth/login",
        )
        if res.status_code == 200:
            self.token = res.json().get("access_token")

    @task(6)
    def open_viral_petition_from_telegram(self):
        """
        Найбільш масовий запит (60% трафіку): перехід за прямим посиланням
        з Telegram-каналу на вірусну петицію.
        """
        headers = {
            "Referer": TELEGRAM_CHANNEL_URL,
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
        }
        self.client.get(
            f"/petitions/{VIRAL_PETITION_ID}",
            headers=headers,
            name="[Telegram-Link] GET /petitions/{viral_id}",
        )

    @task(4)
    def sign_viral_petition_with_crypto_signature(self):
        """
        Підписання вірусної петиції (40% трафіку):
        Генерується суворий цифровий криптографічний хеш підпису (SHA-256).
        Сервер перевіряє унікальність підпису:
        - 201 Created: голос унікальний і успішно врахований.
        - 400 Bad Request: спроба повторного голосування відхилена (криптографічний захист спрацював).
        """
        if not self.token:
            return

        # Формування криптографічного цифрового підпису голосу на основі даних громадянина та ID петиції
        sig_payload = f"telegram_voter:{self.username}:petition:{VIRAL_PETITION_ID}:salt_{random.randint(100, 999)}"
        voter_sig_hash = hashlib.sha256(sig_payload.encode()).hexdigest()

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Referer": TELEGRAM_CHANNEL_URL,
        }

        with self.client.post(
            f"/petitions/{VIRAL_PETITION_ID}/vote",
            headers=headers,
            json={"voter_signature_hash": voter_sig_hash},
            catch_response=True,
            name="[Crypto-Vote] POST /petitions/{viral_id}/vote",
        ) as res:
            if res.status_code in (200, 201):
                res.success()
            elif res.status_code == 400 and "Duplicate vote" in res.text:
                # Це успішна робота криптографічного фільтра унікальності (захист від накрутки)
                res.success()
            else:
                res.failure(f"Збій перевірки або помилка сервера: статус {res.status_code}")

    @task(1)
    def browse_other_catalog(self):
        """Лише мала частка користувачів (10%) переходить на загальний каталог."""
        self.client.get("/petitions", name="[Catalog] GET /petitions")


# ПРОФІЛЬ НАВАНТАЖЕННЯ: СПЛЕСК ТРАФІКУ З TELEGRAM (Spike Shape)


class TelegramSpikeLoadShape(LoadTestShape):
    """
    замість повільного монотонного тесту Locust автоматично імітує графік хвилі переглядів:
    (Імітує хвилю переходів після публікації в Telegram):
    - 0-10 сек: Спокійний фоновий трафік(стан) (5 користувачів)
    - 10-35 сек: РІЗКИЙ СТРИБОК (Spike) до 40 користувачів (вихід посту в каналі) (пост вийшов у Telegram, люди миттєво побігли підписувати!).
    - 35-60 сек: Плавне зниження до 10 користувачів (інтерес до новини спадає)
    """

    stages = [
        {"duration": 10, "users": 5, "spawn_rate": 2},  # До публікації посту
        {"duration": 35, "users": 40, "spawn_rate": 20},  # СТРІМКИЙ СПЛЕСК (Spike)
        {"duration": 60, "users": 10, "spawn_rate": 5},  # Спадання навантаження
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return stage["users"], stage["spawn_rate"]
        return None
