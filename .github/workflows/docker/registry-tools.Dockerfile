FROM node:22-bookworm-slim AS node-runtime

FROM ubuntu:24.04

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
        libgomp1 \
        libnss-wrapper \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY docker/registry-entrypoint.sh /usr/local/bin/registry-entrypoint.sh

RUN rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
    && ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -s ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack \
    && python3 -m venv /opt/uv \
    && /opt/uv/bin/pip install --no-cache-dir uv \
    && ln -s /opt/uv/bin/uv /usr/local/bin/uv \
    && printf '#!/bin/sh\nexec /usr/local/bin/uv tool run "$@"\n' > /usr/local/bin/uvx \
    && chmod +x /usr/local/bin/uvx /usr/local/bin/registry-entrypoint.sh

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/registry-entrypoint.sh"]
