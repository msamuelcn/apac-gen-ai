# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Cloud Run injects PORT; default to 8080.
ENV PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Gunicorn: 1 worker keeps memory low on Cloud Run free tier.
# Increase --workers for higher concurrency needs.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "120", "main:app"]
