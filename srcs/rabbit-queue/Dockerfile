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

# `test -f` on the readiness sentinel is what makes this healthcheck meaningful:
# the broker answers TCP and `rabbitmq-diagnostics ping` long before the
# application user exists and its vhost permissions are granted, so without the
# sentinel a client could start against an unauthorized broker and every
# POST /api/billing would fail with "(530) NOT_ALLOWED - access to vhost '/'
# refused" while the container reports itself healthy. The sentinel is written by
# entrypoint.sh only after `rabbitmqctl authenticate_user` succeeds.
# docker-compose.yml repeats this same probe with the same timings; the only
# difference is that this form appends `|| exit 1`, since a HEALTHCHECK CMD run
# through a shell already yields the command's exit status.
HEALTHCHECK --interval=10s --timeout=10s --start-period=90s --retries=30 \
    CMD test -f /tmp/rabbit-queue-ready && rabbitmq-diagnostics -q check_running || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]