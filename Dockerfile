FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Tashkent

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --create-home --uid 1000 bot && chown -R bot /app
USER bot

# Migratsiyalar avtomatik qo'llanadi, keyin bot ishga tushadi
CMD ["sh", "-c", "alembic upgrade head && exec python -m app"]
