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

mkdir -p /etc/rabbitmq /var/lib/rabbitmq /var/log/rabbitmq
chown -R rabbitmq:rabbitmq /etc/rabbitmq /var/lib/rabbitmq /var/log/rabbitmq

echo "[rabbit-queue] Starting RabbitMQ server in background..."
su-exec rabbitmq rabbitmq-server &
SERVER_PID=$!

# Trap signals for graceful shutdown
shutdown() {
    echo "[rabbit-queue] Received shutdown signal, stopping RabbitMQ..."
    su-exec rabbitmq rabbitmqctl stop || kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID"
    exit 0
}
trap shutdown SIGTERM SIGINT

echo "[rabbit-queue] Awaiting RabbitMQ startup..."
if command -v rabbitmqctl &>/dev/null; then
    for i in $(seq 1 60); do
        if rabbitmqctl await_startup 2>/dev/null; then
            echo "[rabbit-queue] RabbitMQ broker is online and ready."
            break
        fi
        [ "$i" -eq 60 ] && { echo "[rabbit-queue] RabbitMQ failed to start in time"; exit 1; }
        sleep 2
    done
fi

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

echo "[rabbit-queue] RabbitMQ configuration complete. Monitoring process PID $SERVER_PID..."
wait "$SERVER_PID"