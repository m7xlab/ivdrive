# Two stages: wheels are built with the compiler in `builder`; the runtime image
# carries no gcc, no -dev headers and installs from the hash-pinned requirements.lock.
# Regenerate the lock after editing requirements.txt:
#   docker run --rm -v "$PWD":/w -w /w python:3.12-slim sh -c \
#     "pip install -q pip-tools && pip-compile --generate-hashes --strip-extras -o requirements.lock requirements.txt"
FROM python:3.12-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*
COPY requirements.lock .
RUN python -m pip install --no-cache-dir --upgrade pip setuptools && \
    pip wheel --no-cache-dir --require-hashes -r requirements.lock -w /wheels


FROM python:3.12-slim AS base

WORKDIR /app
# apt-get upgrade picks up the Debian point-release fixes the base image lags behind;
# pip/setuptools are upgraded because the base image bundles versions with open advisories
# (libpq/zlib advisories, 2026-11). No compiler or headers in the runtime image.
RUN apt-get update && apt-get upgrade -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
COPY requirements.lock .
RUN python -m pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir --no-index --find-links=/wheels --require-hashes -r requirements.lock && \
    rm -rf /wheels

COPY . .

RUN useradd --create-home --shell /bin/bash --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS collector
CMD ["python", "-m", "app.services"]
