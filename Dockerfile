# build stage: install python + node dependencies and bake the static assets, so the
# runtime image needs no node and serves precompressed css/js
FROM python:3.14-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /usr/local/bin/
COPY --from=oven/bun:1.3-slim /usr/local/bin/bun /usr/local/bin/bun

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY package.json bun.lock ./
# the less compiler is a node script; bun is a drop-in node runtime
RUN bun install --frozen-lockfile && ln -sf /usr/local/bin/bun node_modules/.bin/node

COPY . .
RUN ln -s settings.py.docker ureport/settings.py

# collect and offline-compress static assets; the secret is build-only and no database
# or broker is touched
RUN PATH="/app/node_modules/.bin:$PATH" DJANGO_SECRET_KEY=build-only \
    uv run --no-sync python manage.py collectstatic --noinput && \
    PATH="/app/node_modules/.bin:$PATH" DJANGO_SECRET_KEY=build-only \
    uv run --no-sync python manage.py compress --force && \
    rm -rf node_modules

# runtime stage
FROM python:3.14-slim

# libpq for psycopg, gettext-less runtime is fine (compiled .mo files ship in the repo)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --system --create-home ureport

WORKDIR /app
COPY --from=build --chown=ureport:ureport /app /app
# chown the workdir itself too (--chown covers the copied content, not the directory
# node), and media lives here when no object-store bucket is configured
RUN chown ureport:ureport /app && mkdir -p /app/media && chown ureport:ureport /app/media

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER ureport
EXPOSE 8000

# the web process; workers and beat run from the same image by overriding the command:
#   celery -A ureport worker -Q sync -Ofair --loglevel=INFO
#   celery -A ureport beat --loglevel=INFO
# (beat runs as its own process - RedBeat's redis lock keeps exactly one active, so
# running beat replicas is safe; the worker's embedded -B beat is not used as it fails
# to spawn on this celery/python combination)
CMD ["gunicorn", "ureport.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "--access-logfile", "-"]
