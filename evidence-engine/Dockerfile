FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-osd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app:/backend

COPY evidence-engine/pyproject.toml .
RUN pip install --no-cache-dir .

# 05 section 17.3: ALEAPP and iLEAPP (MIT) pinned by release and git commit, each in its own venv under /opt/leapp.
# Only the re-parse runner calls them, as a child with no network; they are never on the engine's own path.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY evidence-engine/leapp/ /opt/leapp/
RUN sh /opt/leapp/install.sh /opt/leapp/pins.json
# The compiler only builds the packages above; nothing compiles at runtime. Removing it also removes linux-libc-dev
# (kernel headers, never loaded), which carried CVE-2024-21963 and CVE-2026-0004 in the 12 Nov image scan.
RUN apt-get purge -y --auto-remove build-essential && rm -rf /var/lib/apt/lists/*

COPY evidence-engine/alembic.ini .
COPY evidence-engine/alembic/ alembic/
COPY evidence-engine/app/ app/
COPY backend/ /backend/
# Loupe's writing standard (backend/services/writing_standard.py finds it at /shared).
COPY shared/ /shared/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
