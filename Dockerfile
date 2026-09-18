# Deployment candidate image (4A3). Not a released image: 12A1 accepts the real
# host, TLS and observability. Build context is the repository root.
FROM python:3.12-slim AS base

# Bytecode written at import time in a read-only-ish container buys nothing, and
# unbuffered output is what makes gunicorn's logs appear in `docker logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg[binary] ships its own libpq, so no build toolchain is installed here.
# Keeping the image without a compiler is one less thing reachable from a shell.
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY manage.py ./
COPY bazaar_kiosk/ ./bazaar_kiosk/
COPY orders/ ./orders/

# collectstatic runs at build time so the container needs no writable static
# directory and no startup step that could fail differently per restart.
# WhiteNoise's manifest storage requires the files to exist before the first
# request. DEBUG is stated because settings refuse to guess it, and the values
# below are build-time placeholders: nothing here reaches a running deployment,
# which receives its secrets as mounted files (D-046).
RUN DEBUG=1 DATABASE_URL=postgresql://build:build@127.0.0.1:5432/build \
    python manage.py collectstatic --noinput

# The application never writes to its own code, so it runs as a user that
# cannot. An attacker with code execution cannot patch the image contents.
RUN useradd --system --create-home --uid 10001 bazaar \
    && chown -R bazaar:bazaar /app/staticfiles
USER bazaar

EXPOSE 8000
