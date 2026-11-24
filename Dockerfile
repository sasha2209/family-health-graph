# One image serves the API, web dashboard, clinic portal, intake links and the
# mobile app's web build (at /app). Used by Render (render.yaml); runs anywhere.

# --- 1. Build the mobile app for the web --------------------------------------------
FROM node:22-slim AS web
WORKDIR /src/mobile
COPY mobile/package.json mobile/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY mobile/ ./
# Empty API URL = same origin; the app is served under /app.
ENV EXPO_PUBLIC_API_URL="" EXPO_BASE_URL=/app
RUN npx expo export --platform web --output-dir /web

# --- 2. API server --------------------------------------------------------------------
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
# OCR for uploaded prescriptions and lab reports (read on this server; no AI needed for most documents).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-hin tesseract-ocr-mar poppler-utils \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY fhg/ fhg/
COPY --from=web /web /srv/webapp
ENV FHG_WEB_APP_DIR=/srv/webapp FHG_DB_PATH=/var/data/fhg.sqlite3
RUN mkdir -p /var/data
EXPOSE 8000
# Render provides $PORT; --proxy-headers so https and client IPs are seen correctly behind its proxy.
CMD ["sh", "-c", "exec uvicorn fhg.api:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
