# Base image: Alpine 3.23 (penultimate stable release)
FROM alpine:3.23

RUN apk add --no-cache \
    bash \
    su-exec \
    rabbitmq-server \
    && mkdir -p /etc/rabbitmq /var/lib/rabbitmq /var/log/rabbitmq \
    && chown -R rabbitmq:rabbitmq /etc/rabbitmq /var/lib/rabbitmq /var/log/rabbitmq \
    && rabbitmq-plugins enable --offline rabbitmq_management

# COPY --chmod sets the executable bit in the same layer instead of adding a
# separate RUN chmod layer for a 20 kB metadata diff.
COPY --chmod=0755 entrypoint.sh /usr/local/bin/entrypoint.sh

EXPOSE 5672 15672

HEALTHCHECK --interval=10s --timeout=10s --start-period=60s --retries=15 \
    CMD rabbitmq-diagnostics -q ping || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]