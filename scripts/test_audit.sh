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
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1090
    source <(sed -e 's/\r$//' -e '/^#/d' -e '/^$/d' "$REPO_ROOT/.env")
    set +a
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

if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    DOCKER_COMPOSE="docker compose"
fi

# Ensure stack is up
log_info "Ensuring infrastructure is up..."
$DOCKER_COMPOSE up -d --wait --wait-timeout 120

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

# Assert external host curl to internal ports 5432, 8080, 5672 is refused
for port in 5432 8080 5672 15672; do
    if curl -s --connect-timeout 2 "http://127.0.0.1:$port" >/dev/null 2>&1; then
        log_fail "Port $port is unexpectedly reachable from host!"
    else
        log_pass "Port $port is properly isolated from host network"
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
# POST /api/movies/
POST_RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/movies/" \
    -H "Content-Type: application/json" \
    -d '{"title": "A new movie", "description": "Very short description"}')

HTTP_CODE=$(echo "$POST_RESP" | tail -n1)
BODY=$(echo "$POST_RESP" | sed '$d')

if [ "$HTTP_CODE" -eq 200 ]; then
    log_pass "POST /api/movies/ returned status 200"
else
    log_fail "POST /api/movies/ returned status $HTTP_CODE (expected 200): $BODY"
fi

# GET /api/movies/
GET_RESP=$(curl -s -w "\n%{http_code}" -X GET "${BASE_URL}/api/movies/")
HTTP_CODE=$(echo "$GET_RESP" | tail -n1)
BODY=$(echo "$GET_RESP" | sed '$d')

if [ "$HTTP_CODE" -eq 200 ] && echo "$BODY" | grep -q "A new movie"; then
    log_pass "GET /api/movies/ returned 200 and body contains last added movie"
else
    log_fail "GET /api/movies/ check failed (HTTP $HTTP_CODE): $BODY"
fi

# Query filter ?title=new
FILTER_RESP=$(curl -s "${BASE_URL}/api/movies?title=new")
if echo "$FILTER_RESP" | grep -q "A new movie"; then
    log_pass "GET /api/movies?title=new successfully filters by title"
else
    log_fail "GET /api/movies?title=new failed to find movie: $FILTER_RESP"
fi

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

sleep 2

# Stop billing-app container
log_info "Stopping billing-app container to test resilience..."
docker stop billing-app >/dev/null

STATUS=$(docker inspect -f '{{.State.Running}}' billing-app 2>/dev/null || true)
if [ "$STATUS" = "false" ]; then
    log_pass "billing-app container is confirmed stopped"
else
    log_fail "billing-app is still running!"
fi

# POST /api/billing/ while billing-app is DOWN
OUTAGE_RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/billing/" \
    -H "Content-Type: application/json" \
    -d '{"user_id": "22", "number_of_items": "10", "total_amount": "50"}')

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

# Check logs or billing database for order 22 with polling retry
log_info "Awaiting message consumption and persistence to billing-database..."
DB_ORDERS=""
for _ in $(seq 1 10); do
    sleep 1
    DB_ORDERS=$(docker exec billing-database psql -U "$BILLING_DB_USER" -d "$BILLING_DB_NAME" -t -c "SELECT user_id, number_of_items, total_amount FROM orders WHERE user_id = '22';" 2>/dev/null || true)
    if echo "$DB_ORDERS" | grep -q "22"; then
        break
    fi
done

if echo "$DB_ORDERS" | grep -q "22"; then
    log_pass "Buffered order (user_id=22) was consumed and persisted to billing-database upon restart"
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

