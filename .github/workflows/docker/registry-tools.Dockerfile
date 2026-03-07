FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    TERM=dumb \
    CI=1 \
    PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring \
    PYTHON_KEYRING_DISABLED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/uv \
    && /opt/uv/bin/pip install --no-cache-dir uv \
    && ln -s /opt/uv/bin/uv /usr/local/bin/uv \
    && printf '#!/bin/sh\nexec /usr/local/bin/uv tool run "$@"\n' > /usr/local/bin/uvx \
    && chmod +x /usr/local/bin/uvx

WORKDIR /workspace
