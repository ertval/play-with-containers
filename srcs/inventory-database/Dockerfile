# syntax=docker/dockerfile:1
# Base image: Alpine 3.23 (penultimate stable release)
# base-digest: sha256:fd791d74b68913cbb027c6546007b3f0d3bc45125f797758156952bc2d6daf40
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

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=12 \
    CMD pg_isready -U postgres -h 127.0.0.1 || exit 1

ENTRYPOINT ["/usr/local/bin/init-db.sh"]

