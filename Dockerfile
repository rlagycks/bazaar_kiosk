# Deployment candidate image (4A3, 10A). Not a released image: 12A1 accepts the
# real host, TLS and observability. Build context is the repository root.
#
# Two targets. `app` is the application; `proxy` is nginx carrying the static
# files this build produced. They are one file because the assets and the
# templates that name them have to come from the same build -- a shared
# volume would be populated once and then quietly serve last week's bundle
# against this week's manifest (10A).
FROM python:3.12-slim AS app

# Bytecode written at import time in a read-only-ish container buys nothing, and
# unbuffered output is what makes the server's logs appear in `docker logs`.
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


# 10A: the proxy serves /static/ off disk. WhiteNoise's middleware is
# synchronous and has no async version upstream, and Django adapts a
# sync-only middleware by wrapping the whole chain inside it in
# async_to_sync -- which would put every request, streaming or not, on a
# borrowed thread in a second event loop. Moving the files out of the
# application is what keeps the request path async.
FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 AS proxy

# Built by `collectstatic` above: hashed names, a manifest, and .gz siblings
# that gzip_static serves without compressing anything at request time.
COPY --from=app /app/staticfiles /usr/share/nginx/html/static
COPY scripts/nginx_prod.conf /etc/nginx/conf.d/default.conf
# Included by every proxied location; kept out of conf.d so nginx does not
# also load it into the http context on its own.
COPY scripts/nginx_proxy_headers.conf /etc/nginx/bk_proxy_headers.conf
