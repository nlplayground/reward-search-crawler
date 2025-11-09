FROM ubuntu:22.04

# 1. Non-interactive & timezone
ARG DEBIAN_FRONTEND=noninteractive
ARG TZ=Australia/Melbourne
ENV TZ=${TZ} LANG=C.UTF-8 LC_ALL=C.UTF-8

# Install minimal system deps...
RUN apt-get update && apt-get install -y --no-install-recommends  vim lsof unzip \
    python3 python3-pip xvfb xserver-common \
    libgtk-3-0 libx11-xcb1 libasound2 fonts-liberation \
    libgbm1 libnss3 libxcomposite1 libxdamage1 \
    libxrandr2 libxkbcommon0 tzdata && \
    ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata && \
    rm -rf /var/lib/apt/lists/*

# Upgrade pip & wheel (cached)
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install --upgrade pip setuptools wheel

# Install Python deps
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --no-cache-dir -r requirements.txt

# Playwright OS deps
RUN python3 -m playwright install-deps

#  ❯ Use a dedicated cache for Camoufox browser fetch
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browser-cache \
    CAMOUFOX_CACHE_DIR=/opt/camoufox-cache

RUN mkdir -p /opt/camoufox-cache

RUN --mount=type=cache,target=/opt/camoufox-cache \
    python3 -m camoufox fetch

# 8. Copy application code
WORKDIR /app
COPY . .
RUN mkdir -p /app/db

ENTRYPOINT ["python3", "main.py"]
