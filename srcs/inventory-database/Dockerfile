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

# COPY --chmod sets the executable bit in the same layer instead of adding a
# separate RUN chmod layer for a 20 kB metadata diff.
COPY --chmod=0755 init-db.sh /usr/local/bin/init-db.sh

EXPOSE 5432

# PostgreSQL maps SIGTERM to *smart* shutdown, which waits for every client to
# disconnect. Our application containers hold pooled connections, so a plain
# `docker stop` would hang until the grace period expires and the daemon
# SIGKILLs the server (exit 137). SIGINT is PostgreSQL's *fast* shutdown: it
# rolls back open transactions and disconnects clients immediately. This is the
# same signal the official postgres image ships with.
STOPSIGNAL SIGINT

# No image-level HEALTHCHECK: docker-compose.yml is the source of truth and
# probes with the runtime ${DB_USER}/${DB_NAME} (image has no access to them).
# Compose defines: pg_isready -U "${DB_USER}" -d "${DB_NAME}".

ENTRYPOINT ["/usr/local/bin/init-db.sh"]