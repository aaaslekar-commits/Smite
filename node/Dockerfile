ARG BACKHAUL_VERSION=v0.7.2
ARG BACKHAUL_SHA256_AMD64=57bf95c2eabeddb1152d2e94ac42f4310883ce0fb909ee2a57bd53503b2dabbc
ARG BACKHAUL_SHA256_ARM64=9a424c97ff16fc3f682e8314c418790d2b5bf3136e008edbb6cd402ea00999f6

# Stage 1: System dependencies
FROM python:3.11-slim AS base
RUN apt-get update && apt-get install -y \
    gcc \
    iptables \
    curl \
    unzip \
    gzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Install rathole (cached layer)
FROM base AS rathole-bin
RUN set -eux; \
    ARCH_RAW="$(uname -m)"; \
    case "$ARCH_RAW" in \
        x86_64) ARCH="amd64"; RATHOLE_ARCH="x86_64" ;; \
        aarch64) ARCH="arm64"; RATHOLE_ARCH="aarch64" ;; \
        *) ARCH="amd64"; RATHOLE_ARCH="x86_64" ;; \
    esac; \
    RATHOLE_URL="https://github.com/rapiz1/rathole/releases/download/v0.5.0/rathole-$RATHOLE_ARCH-unknown-linux-gnu.zip"; \
    TMP_DIR="$(mktemp -d)"; \
    curl -fsSL "$RATHOLE_URL" -o "$TMP_DIR/rathole.zip"; \
    unzip -q "$TMP_DIR/rathole.zip" -d "$TMP_DIR"; \
    RATHOLE_BIN="$(find "$TMP_DIR" -type f -name 'rathole' | head -n1)"; \
    install -Dm755 "$RATHOLE_BIN" /usr/local/bin/rathole; \
    rm -rf "$TMP_DIR"; \
    GOST_URL="https://github.com/ginuerzh/gost/releases/download/v2.12.0/gost_2.12.0_linux_${ARCH}.tar.gz"; \
    GOST_TMP="$(mktemp -d)"; \
    curl -fsSL "$GOST_URL" -o "$GOST_TMP/gost.tar.gz"; \
    tar -xzf "$GOST_TMP/gost.tar.gz" -C "$GOST_TMP"; \
    GOST_BIN="$(find "$GOST_TMP" -type f -name 'gost' | head -n1)"; \
    install -Dm755 "$GOST_BIN" /usr/local/bin/gost; \
    rm -rf "$GOST_TMP"; \
    echo "Fetching chisel release"; \
    CHISEL_URL="https://github.com/jpillora/chisel/releases/download/v1.11.3/chisel_1.11.3_linux_${ARCH}.gz"; \
    CHISEL_TMP="$(mktemp -d)"; \
    curl -fsSL "$CHISEL_URL" -o "$CHISEL_TMP/chisel.gz"; \
    gunzip "$CHISEL_TMP/chisel.gz"; \
    install -Dm755 "$CHISEL_TMP/chisel" /usr/local/bin/chisel; \
    rm -rf "$CHISEL_TMP"; \
    /usr/local/bin/rathole --version || true; \
    /usr/local/bin/gost -V || true; \
    /usr/local/bin/chisel --version || true

# Stage 3: Install backhaul (cached layer)
FROM base AS backhaul-bin
ARG BACKHAUL_VERSION
ARG BACKHAUL_SHA256_AMD64
ARG BACKHAUL_SHA256_ARM64
RUN set -eux; \
    mkdir -p /opt/backhaul; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
        x86_64|amd64) PLATFORM="amd64"; EXPECTED_SHA="$BACKHAUL_SHA256_AMD64" ;; \
        aarch64|arm64) PLATFORM="arm64"; EXPECTED_SHA="$BACKHAUL_SHA256_ARM64" ;; \
        *) echo "Unsupported architecture: $ARCH"; exit 1 ;; \
    esac; \
    ASSET_URL="https://github.com/Musixal/Backhaul/releases/download/${BACKHAUL_VERSION}/backhaul_linux_${PLATFORM}.tar.gz"; \
    TMP_DIR="$(mktemp -d)"; \
    curl -fsSL "$ASSET_URL" -o "$TMP_DIR/backhaul.tar.gz"; \
    echo "${EXPECTED_SHA}  $TMP_DIR/backhaul.tar.gz" | sha256sum -c -; \
    tar -xzf "$TMP_DIR/backhaul.tar.gz" -C "$TMP_DIR"; \
    BIN_PATH="$(find "$TMP_DIR" -type f -name 'backhaul' | head -n1)"; \
    if [ -z "$BIN_PATH" ]; then \
        echo "Backhaul binary not found in archive"; \
        ls -R "$TMP_DIR"; \
        exit 1; \
    fi; \
    install -Dm755 "$BIN_PATH" /opt/backhaul/backhaul; \
    rm -rf "$TMP_DIR"; \
    /opt/backhaul/backhaul --version || true

# Stage 4: Python dependencies (cached layer)
FROM base AS deps
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# Stage 5: Final image
FROM base
WORKDIR /app

ARG SMITE_VERSION=latest
LABEL org.opencontainers.image.version="${SMITE_VERSION}"
LABEL smite.version="${SMITE_VERSION}"
ENV SMITE_VERSION="${SMITE_VERSION}"

# Copy binaries from binary stages
COPY --from=rathole-bin /usr/local/bin/rathole /usr/local/bin/rathole
COPY --from=rathole-bin /usr/local/bin/chisel /usr/local/bin/chisel
COPY --from=backhaul-bin /opt/backhaul/backhaul /usr/local/bin/backhaul

# Copy Python dependencies from deps stage
COPY --from=deps /usr/local /usr/local

# Copy application code (changes most frequently)
COPY . .

EXPOSE 8888

RUN echo '#!/bin/sh' > /app/start.sh && \
    echo 'exec uvicorn main:app --host 0.0.0.0 --port "${NODE_API_PORT:-8888}" --log-level info --access-log' >> /app/start.sh && \
    chmod +x /app/start.sh

CMD ["/bin/sh", "/app/start.sh"]
