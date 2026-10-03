#!/bin/bash
set -euo pipefail

: "${RABBITMQ_USER:?RABBITMQ_USER environment variable must be set}"
: "${RABBITMQ_PASSWORD:?RABBITMQ_PASSWORD environment variable must be set}"

# `guest` is the broker's built-in default account. Configuring it and then
# deleting it (below) would leave the broker with zero usable users, so reject
# the name up front with an actionable message instead of failing later.
if [ "$RABBITMQ_USER" = "guest" ]; then
    echo "[rabbit-queue] ERROR: RABBITMQ_USER must not be 'guest' - that is the built-in default account which this entrypoint removes." >&2
    exit 1
fi

# Readiness sentinel, consumed by the healthcheck in docker-compose.yml (and by
# the Dockerfile's own HEALTHCHECK).
# Lives in /tmp rather than /var/lib/rabbitmq because /var/lib/rabbitmq is where
# the broker keeps its Mnesia state -- the one directory that *would* survive a
# restart if this service were ever given a volume. Keeping the sentinel outside
# it means the file can only ever mean "configured during this boot", never
# "configured at some point in the image's history".
# Note that `rabbit-queue` currently mounts no volumes at all, so today
# /var/lib/rabbitmq is discarded with the container and the distinction is
# belt-and-braces rather than load-bearing. It starts to matter the moment
# someone adds a volume, which is the obvious production change; the credential
# reconciliation below depends on the same assumption in the other direction
# (it only finds an existing user if the Mnesia dir persisted).
READY_SENTINEL=/tmp/rabbit-queue-ready
rm -f "${READY_SENTINEL}"

mkdir -p /etc/rabbitmq /var/lib/rabbitmq /var/log/rabbitmq
chown -R rabbitmq:rabbitmq /etc/rabbitmq /var/lib/rabbitmq /var/log/rabbitmq

# `rabbitmqctl` run as root needs root's erlang cookie to match the one the
# broker (running as the rabbitmq user) generated, otherwise every CLI call fails
# with "CookieMismatch" while the broker itself looks perfectly healthy.
#
# ADAPTATION vs the reference implementation: there, every CLI call is wrapped in
# `su-exec rabbitmq` because the official rabbitmq image ships the CLI in
# /usr/local/bin and a bare call as root can pick up a different Erlang home.
# This image is `alpine:3.23` + `apk add rabbitmq-server`, whose rabbitmqctl /
# rabbitmq-diagnostics live in /usr/sbin and are already on root's PATH - and
# su-exec does NOT reset the environment, so a `su-exec rabbitmq rabbitmqctl`
# call would still inherit HOME=/root and fail to read the cookie as an
# unprivileged user. Copying the broker's cookie to root is therefore both the
# simpler and the more reliable fix here, and it also keeps the healthcheck's own
# `rabbitmq-diagnostics -q check_running` (which docker runs as root) working.
sync_erlang_cookie() {
    if [ -f /var/lib/rabbitmq/.erlang.cookie ] && [ ! -f /root/.erlang.cookie ]; then
        cp -f /var/lib/rabbitmq/.erlang.cookie /root/.erlang.cookie 2>/dev/null || true
        chmod 400 /root/.erlang.cookie 2>/dev/null || true
    fi
}

echo "[rabbit-queue] Starting RabbitMQ server in background..."
su-exec rabbitmq rabbitmq-server &
SERVER_PID=$!

# Trap signals for graceful shutdown
shutdown() {
    echo "[rabbit-queue] Received shutdown signal, stopping RabbitMQ..."
    sync_erlang_cookie
    rabbitmqctl stop || kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID"
    exit 0
}
trap shutdown SIGTERM SIGINT

echo "[rabbit-queue] Awaiting RabbitMQ startup..."
if command -v rabbitmqctl &>/dev/null; then
    for i in $(seq 1 60); do
        # Synced every iteration: the broker only writes its cookie once it is far
        # enough along, so the first attempts can legitimately fail on a missing
        # cookie and the loop is what turns that into a retry instead of an abort.
        sync_erlang_cookie
        if rabbitmqctl await_startup 2>/dev/null; then
            echo "[rabbit-queue] RabbitMQ broker is online and ready."
            break
        fi
        [ "$i" -eq 60 ] && { echo "[rabbit-queue] RabbitMQ failed to start in time"; exit 1; }
        sleep 2
    done
fi

sync_erlang_cookie

echo "[rabbit-queue] Configuring credentials and permissions for user '$RABBITMQ_USER'..."

# The password is fed on stdin, never as a command-line argument. Anything in
# argv is world-readable through /proc/<pid>/cmdline for the whole lifetime of
# the process, so `rabbitmqctl add_user "$user" "$pass"` would expose it. With
# this form rabbitmqctl prompts for the password and reads it from stdin.
user_exists() {
    rabbitmqctl list_users --silent 2>/dev/null | awk '{print $1}' | grep -qx "$RABBITMQ_USER"
}

if user_exists; then
    # Reconcile on every boot so a rotated credential in .env takes effect.
    printf '%s\n' "$RABBITMQ_PASSWORD" | rabbitmqctl change_password "$RABBITMQ_USER" >/dev/null
    echo "[rabbit-queue] Existing user '$RABBITMQ_USER' password synchronised."
else
    printf '%s\n' "$RABBITMQ_PASSWORD" | rabbitmqctl add_user "$RABBITMQ_USER" >/dev/null
    echo "[rabbit-queue] Created user '$RABBITMQ_USER'."
fi

rabbitmqctl set_user_tags "$RABBITMQ_USER" administrator
rabbitmqctl set_permissions -p / "$RABBITMQ_USER" ".*" ".*" ".*"

# Delete default guest user if it exists for security hygiene
rabbitmqctl delete_user guest 2>/dev/null || true

# Prove the credentials actually work before declaring the broker ready.
# Without this the broker accepts AMQP connections (and passes a
# `rabbitmq-diagnostics ping` probe) while the broker account is still
# unauthorized, so api-gateway receives
# "(530) NOT_ALLOWED - access to vhost '/' refused" and the audit's
# POST /api/billing/ returns HTTP 500 after the container is already reported
# healthy. `authenticate_user` is a subcommand of the same `rabbitmqctl` this
# script already calls (list_users / add_user / change_password /
# set_user_tags / set_permissions / delete_user / await_startup), so it needs no
# additional binary or plugin.
# The one place a credential reaches `argv`, and `rabbitmqctl` offers no stdin
# form of `authenticate_user` -- it takes the password positionally by design.
# Unlike add_user/change_password above, which run on every boot and therefore
# use stdin, this runs once, exits immediately, and is never visible to another
# process in this single-purpose container. Stated rather than hidden, because a
# documentation claim of "never in argv" that this line contradicts is worse
# than the argv itself.
if rabbitmqctl authenticate_user "$RABBITMQ_USER" "$RABBITMQ_PASSWORD" >/dev/null 2>&1; then
    touch "${READY_SENTINEL}"
    echo "[rabbit-queue] User '$RABBITMQ_USER' verified; readiness sentinel written to ${READY_SENTINEL}."
else
    echo "[rabbit-queue] ERROR: user '$RABBITMQ_USER' could not authenticate after configuration." >&2
    exit 1
fi

echo "[rabbit-queue] RabbitMQ configuration complete. Monitoring process PID $SERVER_PID..."
wait "$SERVER_PID"