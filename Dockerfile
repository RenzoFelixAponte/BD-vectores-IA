## Stage 1: build frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

## Stage 2: runtime (Python + nginx + supervisord)
FROM python:3.12-slim

RUN apt-get update && apt-get install -y nginx supervisor && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Backend
COPY back/requirements.txt .
COPY scripts/benchmarks/requirements.txt benchmark-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r benchmark-requirements.txt
COPY back/ ./back/
COPY scripts/ ./scripts/
COPY run.py .
RUN mkdir -p back/data

# Frontend (built static files)
COPY --from=frontend-build /app/dist /var/www/html

# nginx config
COPY nginx.conf /etc/nginx/sites-available/default

# supervisord config
COPY supervisord.conf /etc/supervisor/conf.d/app.conf

EXPOSE 80

CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
