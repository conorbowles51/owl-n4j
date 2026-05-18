FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app:/backend:/ingestion/scripts

COPY evidence-engine/pyproject.toml .
RUN pip install --no-cache-dir .

COPY evidence-engine/alembic.ini .
COPY evidence-engine/alembic/ alembic/
COPY evidence-engine/app/ app/
COPY ingestion/ /ingestion/
COPY backend/ /backend/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
