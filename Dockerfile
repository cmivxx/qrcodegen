FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY qr_generator.py .
COPY preview_app.py .
COPY gunicorn_config.py .
COPY templates/ ./templates/

RUN useradd -r -u 1001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["gunicorn", "--config", "gunicorn_config.py", "preview_app:app"]
