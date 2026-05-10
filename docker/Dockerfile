# Bookworm: wkhtmltopdf still exists in apt; python:3.12-slim (trixie) dropped it.
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wkhtmltopdf \
        tesseract-ocr \
        tesseract-ocr-por \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic alembic
COPY alembic.ini alembic.ini
COPY app app
COPY playground playground
COPY docker docker
COPY pyproject.toml pyproject.toml

RUN chmod +x docker/backend-entry.sh

EXPOSE 8000

ENTRYPOINT ["bash", "docker/backend-entry.sh"]
