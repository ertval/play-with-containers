#!/usr/bin/env bash
set -euo pipefail

# ANSI color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Safe .env loader: KEY=VAL lines only, no source/eval (values stay literal,
# so backticks/$()/$(...) in values can never execute). KEY must match
# ^[A-Za-z_][A-Za-z0-9_]*= ; surrounding single/double quotes stripped once.
if [ -f "$REPO_ROOT/.env" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%$'\r'}"
        case "$line" in ''|\#*) continue ;; esac
        case "$line" in *=*) ;; *) continue ;; esac
        key="${line%%=*}"
        val="${line#*=}"
        # Trim surrounding whitespace from key only (values keep inner spaces).
        key="$(printf '%s' "$key" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
        case "$key" in
            ''|*[!A-Za-z0-9_]*|[0-9]*) continue ;;
            *) case "$key" in [A-Za-z_]*) ;; *) continue ;; esac ;;
        esac
        # Strip one level of matching surrounding quotes (no escape processing).
        case "$val" in
            \"*\") val="${val#\"}"; val="${val%\"}" ;;
            \'*\') val="${val#\'}"; val="${val%\'}" ;;
        esac
        # Only set if not already exported; assignment via printf -v/export arg
        # performs no evaluation of the value.
        if [ -z "${!key+x}" ]; then
            printf -v "$key" '%s' "$val"
            export "$key"
        fi
    done < "$REPO_ROOT/.env"
fi

GATEWAY_HOST="${GATEWAY_HOST:-127.0.0.1}"
GATEWAY_PORT="${GATEWAY_PORT:-3000}"
BASE_URL="http://${GATEWAY_HOST}:${GATEWAY_PORT}"
BILLING_DB_USER="${BILLING_DB_USER:-billing_user}"
BILLING_DB_NAME="${BILLING_DB_NAME:-billing_db}"

echo "============================================================"
echo "   Play with Containers - Automated Audit Verification"
echo "============================================================"

# Verify Docker availability
if ! command -v docker >/dev/null 2>&1; then
    log_fail "Docker CLI not found in PATH. Please install or activate Docker."
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    log_fail "Docker daemon is not running or unreachable. Please start Docker."
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    log_fail "Docker Compose v2 ('docker compose') is required; this suite needs the --wait flag (v2.1+)."
    exit 1
fi
DOCKER_COMPOSE="docker compose"

# Ensure stack is up. The timeout covers a cold boot where the broker alone needs
# ~40-60 s (depends_on: service_healthy gates the apps behind it).
log_info "Ensuring infrastructure is up..."
$DOCKER_COMPOSE up -d --wait --wait-timeout 240

SERVICES=("inventory-database" "billing-database" "rabbit-queue" "inventory-app" "billing-app" "api-gateway-app")

echo ""
echo "--- 1. Verification of Containers and Image Names ---"
for s in "${SERVICES[@]}"; do
    img=$(docker inspect -f '{{.Config.Image}}' "$s" 2>/dev/null || true)
    if [ "$img" = "$s" ]; then
        log_pass "Container '$s' uses image '$img'"
    else
        log_fail "Container '$s' has image '$img' (expected '$s')"
    fi
done

echo ""
echo "--- 2. Verification of Restart Policy ---"
for s in "${SERVICES[@]}"; do
    rp=$(docker inspect -f '{{.HostConfig.RestartPolicy}}' "$s" 2>/dev/null || true)
    if [ "$rp" = "{on-failure 0}" ]; then
        log_pass "Container '$s' restart policy is exactly {on-failure 0}"
    else
        log_fail "Container '$s' restart policy is '$rp' (expected '{on-failure 0}')"
    fi
done

echo ""
echo "--- 3. Verification of Named Volumes ---"
VOLUMES=$(docker volume ls --format '{{.Name}}')
EXPECTED_VOLUMES=("inventory-database" "billing-database" "api-gateway-app")
for v in "${EXPECTED_VOLUMES[@]}"; do
    if echo "$VOLUMES" | grep -qx "$v"; then
        log_pass "Volume '$v' exists with exact name"
    else
        log_fail "Volume '$v' not found in docker volume ls"
    fi
done

echo ""
echo "--- 4. Verification of Port Exposure and Isolation ---"
# Only 3000 should be mapped on host
PUBLISHED_PORTS=$(docker ps --format '{{.Names}}: {{.Ports}}' | grep -E 'inventory-database|billing-database|rabbit-queue|inventory-app|billing-app|api-gateway-app' | grep -E '0\.0\.0\.0|::' || true)
echo "Published ports across project containers:"
echo "$PUBLISHED_PORTS"

GATEWAY_PUBLISHED=$(echo "$PUBLISHED_PORTS" | grep "api-gateway-app" || true)
OTHER_PUBLISHED=$(echo "$PUBLISHED_PORTS" | grep -v "api-gateway-app" || true)

if echo "$GATEWAY_PUBLISHED" | grep -q "3000->3000" && [ -z "$OTHER_PUBLISHED" ]; then
    log_pass "Only api-gateway-app published port 3000 on host"
else
    log_fail "Port publication check failed: unexpected exposed ports found ($PUBLISHED_PORTS)"
fi

# Assert against Docker's own state rather than the host socket. `docker port`
# is authoritative for "did a container publish this?", whereas probing
# 127.0.0.1:<port> also succeeds for any unrelated daemon on the host and would
# report a false failure for a perfectly isolated stack.
for s in inventory-database billing-database inventory-app billing-app rabbit-queue; do
    PUBLISHED=$(docker port "$s" 2>/dev/null || true)
    if [ -z "$PUBLISHED" ]; then
        log_pass "Container '$s' publishes no host port (isolated)"
    else
        log_fail "Container '$s' unexpectedly publishes: $PUBLISHED"
    fi
done

# Belt-and-braces: from inside the project network the internal ports must be
# reachable, which proves they are exposed to containers and not to the host.
for target in "inventory-database:5432" "billing-database:5432" "rabbit-queue:5672"; do
    host="${target%%:*}"; port="${target##*:}"
    if docker exec api-gateway-app python3 -c "
import socket, sys
s = socket.socket()
s.settimeout(3)
sys.exit(0 if s.connect_ex(('$host', $port)) == 0 else 1)
" >/dev/null 2>&1; then
        log_pass "Internal service $host:$port reachable from the project network"
    else
        log_fail "Internal service $host:$port is NOT reachable from the project network"
    fi
done

echo ""
echo "--- 5. Internal Network Connectivity ---"
if docker exec api-gateway-app python3 -c "import urllib.request; urllib.request.urlopen('http://inventory-app:8080/health')" >/dev/null 2>&1 || \
   docker exec api-gateway-app wget -qO- http://inventory-app:8080/health >/dev/null 2>&1; then
    log_pass "Internal communication (api-gateway-app -> inventory-app:8080) OK"
else
    log_fail "Internal communication between containers failed"
fi

echo ""
echo "--- 6. Inventory API Endpoints (Audit Requirements) ---"
# Unique marker per run so assertions cannot be satisfied by rows left behind by
# a previous execution, and so repeated runs stay idempotent.
RUN_MARKER="audit-$$-$(date +%s)"
SENTINEL_USER="${RUN_MARKER}"
CREATED_MOVIE_ID=""
cleanup_inventory() {
    if [ -n "$CREATED_MOVIE_ID" ]; then
        curl -s -X DELETE "${BASE_URL}/api/movies/${CREATED_MOVIE_ID}" >/dev/null 2>&1 || true
    fi
}
# Never leave the stack in the audit's "billing-app stopped" state, whatever fails.
trap 'cleanup_inventory; docker start billing-app >/dev/null 2>&1 || true' EXIT

# POST /api/movies/
POST_RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/movies/" \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"${RUN_MARKER}\", \"description\": \"Very short description\"}")

HTTP_CODE=$(echo "$POST_RESP" | tail -n1)
BODY=$(echo "$POST_RESP" | sed '$d')

# Capture the new row's id so cleanup can remove exactly that row (the
# delete-all route takes no filter and must never be used here).
CREATED_MOVIE_ID=$(printf '%s' "$BODY" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p')

if [ "$HTTP_CODE" -eq 200 ]; then
    log_pass "POST /api/movies/ returned status 200"
else
    log_fail "POST /api/movies/ returned status $HTTP_CODE (expected 200): $BODY"
fi

# The audit's literal payload must also be accepted verbatim.
AUDIT_POST=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/movies/" \
    -H "Content-Type: application/json" \
    -d '{"title": "A new movie", "description": "Very short description"}')
if [ "$AUDIT_POST" -eq 200 ]; then
    log_pass "POST /api/movies/ with the audit's exact payload returned 200"
else
    log_fail "POST /api/movies/ with the audit's exact payload returned $AUDIT_POST (expected 200)"
fi

# GET /api/movies/
GET_RESP=$(curl -s -w "\n%{http_code}" -X GET "${BASE_URL}/api/movies/")
HTTP_CODE=$(echo "$GET_RESP" | tail -n1)
BODY=$(echo "$GET_RESP" | sed '$d')

if [ "$HTTP_CODE" -eq 200 ] && echo "$BODY" | grep -q "$RUN_MARKER"; then
    log_pass "GET /api/movies/ returned 200 and body contains the movie just added"
else
    log_fail "GET /api/movies/ check failed (HTTP $HTTP_CODE): $BODY"
fi

# Query filter ?title=
FILTER_RESP=$(curl -s "${BASE_URL}/api/movies?title=${RUN_MARKER}")
if echo "$FILTER_RESP" | grep -q "$RUN_MARKER"; then
    log_pass "GET /api/movies?title=... successfully filters by title"
else
    log_fail "GET /api/movies?title=... failed to find movie: $FILTER_RESP"
fi

cleanup_inventory

echo ""
echo "--- 7. Billing API Endpoints & Queue Resilience ---"
# POST /api/billing/ (Normal operation)
BILLING_RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/billing/" \
    -H "Content-Type: application/json" \
    -d '{"user_id": "20", "number_of_items": "99", "total_amount": "250"}')

HTTP_CODE=$(echo "$BILLING_RESP" | tail -n1)
BODY=$(echo "$BILLING_RESP" | sed '$d')

if [ "$HTTP_CODE" -eq 200 ]; then
    log_pass "POST /api/billing/ returned status 200 under normal operation"
else
    log_fail "POST /api/billing/ failed with status $HTTP_CODE: $BODY"
fi

# The audit's literal payload must also be accepted verbatim.
AUDIT_BILLING=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/billing/" \
    -H "Content-Type: application/json" \
    -d '{"user_id": "20", "number_of_items": "99", "total_amount": "250"}')
if [ "$AUDIT_BILLING" -eq 200 ]; then
    log_pass "POST /api/billing/ with the audit's exact payload returned 200"
else
    log_fail "POST /api/billing/ with the audit's exact payload returned $AUDIT_BILLING (expected 200)"
fi

sleep 2

# Stop billing-app container
log_info "Stopping billing-app container to test resilience..."
STOP_START=$(date +%s)
docker stop billing-app >/dev/null
STOP_ELAPSED=$(( $(date +%s) - STOP_START ))
EXIT_CODE=$(docker inspect -f '{{.State.ExitCode}}' billing-app 2>/dev/null || echo "unknown")

STATUS=$(docker inspect -f '{{.State.Running}}' billing-app 2>/dev/null || true)
if [ "$STATUS" = "false" ]; then
    log_pass "billing-app container is confirmed stopped"
else
    log_fail "billing-app is still running!"
fi

# A graceful SIGTERM shutdown exits 0. Exit 137 means Docker had to SIGKILL the
# process after its 10 s grace period, i.e. the app ignored SIGTERM.
if [ "$EXIT_CODE" = "0" ]; then
    log_pass "billing-app shut down gracefully on SIGTERM (exit 0, ${STOP_ELAPSED}s)"
else
    log_fail "billing-app exit code is $EXIT_CODE (expected 0 = graceful SIGTERM shutdown, took ${STOP_ELAPSED}s)"
fi

# POST /api/billing/ while billing-app is DOWN
# Uses the audit's exact payload for the status check, plus a run-unique
# sentinel id so the later persistence assertion can identify this run's row.
OUTAGE_RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/billing/" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\": \"${SENTINEL_USER}\", \"number_of_items\": \"10\", \"total_amount\": \"50\"}")

HTTP_CODE=$(echo "$OUTAGE_RESP" | tail -n1)
BODY=$(echo "$OUTAGE_RESP" | sed '$d')

if [ "$HTTP_CODE" -eq 200 ]; then
    log_pass "POST /api/billing/ returned status 200 even with billing-app DOWN (RabbitMQ buffered)"
else
    log_fail "POST /api/billing/ during outage failed with status $HTTP_CODE: $BODY"
fi

# Restart billing-app and verify consumed message
log_info "Restarting billing-app container..."
docker start billing-app >/dev/null

# Verify the row produced by THIS run, not one left by a previous run: rows are
# never deleted, so matching a fixed user_id would pass even if this run's
# message had been lost. A unique sentinel cannot collide with an earlier run.
log_info "Awaiting consumption of buffered order (sentinel user_id=${SENTINEL_USER})..."
DB_ORDERS=""
for _ in $(seq 1 15); do
    sleep 1
    DB_ORDERS=$(docker exec billing-database psql -U "$BILLING_DB_USER" -d "$BILLING_DB_NAME" -t \
        -c "SELECT user_id, number_of_items, total_amount FROM orders WHERE user_id = '${SENTINEL_USER}';" 2>/dev/null || true)
    if echo "$DB_ORDERS" | grep -q "$SENTINEL_USER"; then
        break
    fi
done

if echo "$DB_ORDERS" | grep -q "$SENTINEL_USER"; then
    log_pass "Buffered order (${SENTINEL_USER}) was consumed and persisted after billing-app restart"
else
    log_fail "Buffered order was not found in billing-database after restart: $DB_ORDERS"
fi

echo ""
echo "--- 8. Verification of Persistent Volume Logs ---"
LOG_EXISTS=$(docker exec api-gateway-app ls -l /usr/src/logs/gateway.log 2>/dev/null || true)
if [ -n "$LOG_EXISTS" ]; then
    log_pass "Gateway log file exists at /usr/src/logs/gateway.log on named volume"
else
    log_fail "Gateway log file /usr/src/logs/gateway.log not found"
fi

echo ""
echo "============================================================"
echo "Audit Verification Summary: ${PASS_COUNT} Passed, ${FAIL_COUNT} Failed"
echo "============================================================"

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "${GREEN}ALL AUDIT CHECKS PASSED!${NC}"
    exit 0
else
    echo -e "${RED}SOME AUDIT CHECKS FAILED!${NC}"
    exit 1
fi

