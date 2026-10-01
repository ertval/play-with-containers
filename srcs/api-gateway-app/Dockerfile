# Base image: Alpine 3.23 (penultimate stable release)
FROM alpine:3.23

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apk add --no-cache \
    python3 \
    py3-pip

COPY requirements.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

RUN addgroup -S app && adduser -S -G app -H -s /sbin/nologin app

# /usr/src/logs is the mount point for the persistent named volume declared in
# docker-compose.yml. It must be owned by `app`, otherwise Docker seeds the
# fresh volume from this directory with root:root ownership and the gateway's
# RotatingFileHandler fails with PermissionError at runtime.
RUN mkdir -p /usr/src/logs && chown -R app:app /usr/src/logs

COPY --chown=app:app server.py openapi.yaml ./
COPY --chown=app:app app/ ./app/

# Smoke test import assertion at build time (runs as the unprivileged user)
USER app
RUN python3 -c "import flask, waitress, pika, requests"

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/health')" || exit 1

CMD ["python3", "server.py"]