# syntax=docker/dockerfile:1
# Base image: Alpine 3.23 (penultimate stable release)
FROM alpine:3.23

# Install PostgreSQL 17 server, client, bash, and su-exec
RUN apk add --no-cache \
    bash \
    su-exec \
    postgresql17 \
    postgresql17-client \
    && mkdir -p /var/lib/postgresql/data /run/postgresql \
    && chown -R postgres:postgres /var/lib/postgresql /run/postgresql

ENV PGDATA=/var/lib/postgresql/data
ENV PATH="/usr/libexec/postgresql17:/usr/bin:$PATH"

COPY init-db.sh /usr/local/bin/init-db.sh
RUN chmod +x /usr/local/bin/init-db.sh

EXPOSE 5432

# No image-level HEALTHCHECK: docker-compose.yml is the source of truth and
# probes with the runtime ${DB_USER}/${DB_NAME} (image has no access to them).
# Compose defines: pg_isready -U "${DB_USER}" -d "${DB_NAME}".

ENTRYPOINT ["/usr/local/bin/init-db.sh"]

