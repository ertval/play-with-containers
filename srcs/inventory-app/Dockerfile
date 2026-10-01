# Base image: Alpine 3.23 (penultimate stable release)
FROM alpine:3.23

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# psycopg2 comes from pip only (requirements.txt). Installing the Alpine
# py3-psycopg2 package as well would put two providers in the same
# site-packages/psycopg2 directory and corrupt apk's package database, because
# pip's binary overwrites the files apk believes it owns.
RUN apk add --no-cache \
    python3 \
    py3-pip

COPY requirements.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

RUN addgroup -S app && adduser -S -G app -H -s /sbin/nologin app

COPY --chown=app:app server.py ./
COPY --chown=app:app app/ ./app/

# Smoke test import assertion at build time (runs as the unprivileged user)
USER app
RUN python3 -c "import flask, waitress, flask_sqlalchemy, sqlalchemy, psycopg2"

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')" || exit 1

CMD ["python3", "server.py"]