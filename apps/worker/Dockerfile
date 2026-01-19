FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    git \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api /app/apps/api
COPY apps/worker /app/apps/worker
COPY packages/shared /app/packages/shared

# Set python path
ENV PYTHONPATH=/app

CMD ["arq", "apps.worker.main.WorkerSettings"]
