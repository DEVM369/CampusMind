FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src
COPY migrations ./migrations
COPY infra/postgres ./infra/postgres
COPY frontend/dist ./frontend/dist
COPY alembic.ini ./
COPY scripts/check_runtime.py scripts/smoke_api_image.py ./scripts/

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "campusmind.main:app", "--host", "0.0.0.0", "--port", "8000"]
