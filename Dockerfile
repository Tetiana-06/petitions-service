# ---------- Етап 1: збирання залежностей ----------
# Багатоетапне збирання образу бекенду
FROM python:3.11-slim AS builder

WORKDIR /app

# Компілятор потрібен лише тут, у фінальний образ він не потрапить
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Етап 2: фінальний легкий образ
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Копіюємо лише встановлені пакети з етапу builder
COPY --from=builder /install /usr/local

COPY src ./src

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
