FROM python:3.11-slim AS base
RUN apt-get update && apt-get install -y \
    gcc \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

FROM node:18-alpine AS frontend-build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then \
        npm ci --prefer-offline --no-audit --no-fund; \
    else \
        npm install --prefer-offline --no-audit --no-fund; \
    fi
COPY frontend ./
RUN npm run build

FROM base AS deps
WORKDIR /app
COPY panel/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

FROM base
WORKDIR /app

ARG SMITE_VERSION=latest
LABEL org.opencontainers.image.version="${SMITE_VERSION}"
LABEL smite.version="${SMITE_VERSION}"
ENV SMITE_VERSION="${SMITE_VERSION}"
RUN echo "${SMITE_VERSION}" > /app/VERSION

COPY --from=deps /usr/local /usr/local
COPY --from=frontend-build /app/dist ./static
COPY panel .
# Note: .git is excluded in .dockerignore, so git tag extraction at runtime won't work in Docker
# Version is set via SMITE_VERSION build arg (extract with: git describe --tags --abbrev=0)

EXPOSE 8000 443/tcp 443/udp

RUN echo '#!/bin/sh' > /app/start.sh && \
    echo 'set -e' >> /app/start.sh && \
    echo 'exec uvicorn main:app --host "${PANEL_HOST:-0.0.0.0}" --port "${PANEL_PORT:-8000}"' >> /app/start.sh && \
    chmod +x /app/start.sh

CMD ["/bin/sh", "/app/start.sh"]
