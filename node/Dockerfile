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
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then ARCH="x86_64"; \
    elif [ "$ARCH" = "aarch64" ]; then ARCH="aarch64"; \
    else ARCH="x86_64"; fi && \
    echo "Getting latest rathole version..." && \
    RATHOLE_VERSION=$(curl -sL https://api.github.com/repos/rapiz1/rathole/releases | jq -r '.[0].tag_name // "v0.5.0"') && \
    echo "Downloading rathole ${RATHOLE_VERSION} for ${ARCH}..." && \
    RATHOLE_ASSET=$(curl -sL "https://api.github.com/repos/rapiz1/rathole/releases" | jq -r --arg arch "$ARCH" '.[0].assets[] | select(.name | contains($arch) and (contains("linux-gnu") or contains("linux-musl"))) | .browser_download_url' | head -1) && \
    if [ -z "$RATHOLE_ASSET" ] || [ "$RATHOLE_ASSET" = "null" ]; then \
        echo "Error: Could not find rathole binary for ${ARCH}"; \
        exit 1; \
    fi && \
    echo "Downloading from: $RATHOLE_ASSET" && \
    if echo "$RATHOLE_ASSET" | grep -q "\.zip$"; then \
        curl -L "$RATHOLE_ASSET" -o /tmp/rathole.zip -f && \
        unzip -q /tmp/rathole.zip -d /tmp && \
        rm /tmp/rathole.zip; \
    else \
        curl -L "$RATHOLE_ASSET" -o /tmp/rathole.tar.gz -f && \
        tar -xzf /tmp/rathole.tar.gz -C /tmp && \
        rm /tmp/rathole.tar.gz; \
    fi && \
    find /tmp -name "rathole" -type f -executable -exec mv {} /usr/local/bin/ \; && \
    chmod +x /usr/local/bin/rathole && \
    rathole --version && \
    rm -rf /tmp/rathole*

# Stage 3: Install backhaul (cached layer)
FROM base AS backhaul-bin
ARG BACKHAUL_MODULE=github.com/Musixal/Backhaul
ARG BACKHAUL_VERSION=latest
ARG BACKHAUL_GIT_TOKEN=
ENV GO111MODULE=on
ENV GOBIN=/usr/local/bin
RUN set -eux; \
    apt-get update; \
    apt-get install -y git golang; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /opt/backhaul; \
    if [ -n "${BACKHAUL_GIT_TOKEN}" ]; then \
        git config --global url."https://${BACKHAUL_GIT_TOKEN}:x-oauth-basic@github.com/".insteadOf "https://github.com/"; \
    fi; \
    GOBIN=/tmp/backhaul-bin go install ${BACKHAUL_MODULE}/cmd/backhaul@${BACKHAUL_VERSION}; \
    if [ -f /tmp/backhaul-bin/backhaul ]; then \
        install -Dm755 /tmp/backhaul-bin/backhaul /opt/backhaul/backhaul; \
    elif [ -f "$(go env GOPATH)/bin/backhaul" ]; then \
        install -Dm755 "$(go env GOPATH)/bin/backhaul" /opt/backhaul/backhaul; \
    else \
        echo "Backhaul binary missing after installation"; \
        ls -R "$(go env GOPATH)/bin" || true; \
        exit 1; \
    fi; \
    if [ -n "${BACKHAUL_GIT_TOKEN}" ]; then \
        rm -f /root/.gitconfig; \
    fi; \
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
