# Stage 1: System dependencies
FROM python:3.11-slim AS base
RUN apt-get update && apt-get install -y \
    gcc \
    iptables \
    curl \
    unzip \
    jq \
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
    /usr/local/bin/rathole --version || true; \
    /usr/local/bin/gost -V || true

# Stage 3: Install backhaul (cached layer)
FROM base AS backhaul-bin
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /opt/backhaul; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
        x86_64|amd64) PLATFORM="amd64" ;; \
        aarch64|arm64) PLATFORM="arm64" ;; \
        *) echo "Unsupported architecture: $ARCH"; exit 1 ;; \
    esac; \
    RELEASE_JSON="$(curl -fsSL https://api.github.com/repos/Musixal/Backhaul/releases/latest)"; \
    ASSET_URL="$(printf '%s' "$RELEASE_JSON" | jq -r --arg platform "$PLATFORM" '.assets[] | select(.name | test("linux_" + $platform)) | .browser_download_url' | head -n1)"; \
    if [ -z "$ASSET_URL" ] || [ "$ASSET_URL" = "null" ]; then \
        echo "Unable to find Backhaul release asset for platform: $PLATFORM"; \
        exit 1; \
    fi; \
    TMP_FILE="$(mktemp)"; \
    curl -fsSL "$ASSET_URL" -o "$TMP_FILE"; \
    FILE_NAME="$(basename "$ASSET_URL")"; \
    case "$FILE_NAME" in \
        *.tar.gz|*.tgz) \
            tar -xzf "$TMP_FILE" -C /opt/backhaul; \
            ;; \
        *.zip) \
            unzip -q "$TMP_FILE" -d /opt/backhaul; \
            ;; \
        *) \
            mv "$TMP_FILE" /opt/backhaul/backhaul-download; \
            ;; \
    esac; \
    if [ -f /opt/backhaul/backhaul-download ]; then \
        mv /opt/backhaul/backhaul-download /opt/backhaul/backhaul; \
    else \
        BIN_PATH="$(find /opt/backhaul -maxdepth 1 -type f -name 'backhaul*' | head -n1)"; \
        if [ -z "$BIN_PATH" ]; then \
            echo "Backhaul binary not found after extracting $FILE_NAME"; \
            ls -R /opt/backhaul; \
            exit 1; \
        fi; \
        if [ "$BIN_PATH" != "/opt/backhaul/backhaul" ]; then \
            mv "$BIN_PATH" /opt/backhaul/backhaul; \
        fi; \
    fi; \
    chmod +x /opt/backhaul/backhaul; \
    rm -f "$TMP_FILE" 2>/dev/null || true; \
    /opt/backhaul/backhaul --version || true

# Stage 4: Python dependencies (cached layer)
FROM base AS deps
WORKDIR /app
COPY requirements.txt .
# Use pip cache if available
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# Stage 5: Final image
FROM base
WORKDIR /app

# Copy binaries from binary stages
COPY --from=rathole-bin /usr/local/bin/rathole /usr/local/bin/rathole
COPY --from=backhaul-bin /opt/backhaul/backhaul /usr/local/bin/backhaul

# Copy Python dependencies from deps stage
COPY --from=deps /usr/local /usr/local

# Copy application code (changes most frequently)
COPY . .

EXPOSE 8888

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8888", "--log-level", "info", "--access-log"]
