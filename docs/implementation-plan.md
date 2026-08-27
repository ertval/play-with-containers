# Play with Containers — Implementation Plan (v2)

Project: `/home/ertval/code/zone-modules/play-with-containers`
Date: 2026-08-27 · Revised after independent review-agent critique (v1 → v2).
Sources read: `docs/requirements/readme.md`, `docs/requirements/audit.md`,
https://github.com/01-edu/crud-master-py (README, config.yaml, .env.example,
all three services' source code, Dockerfiles, requirements.txt, setup scripts),
https://alpinelinux.org/releases/ (version state as of 2026-08).

---

## 1. Goal

Implement the `play-with-containers` subject fully: a 6-service microservices
infrastructure managed exclusively by `docker-compose`, passing every item in
`audit.md` (including all conceptual questions), reusing/adapting the
`crud-master-py` reference services. A final review-agent pass verifies
correctness and completeness.

## 2. Key decisions (single source of truth)

| Item | Value | Why |
|---|---|---|
| Base image for ALL Dockerfiles | `alpine:3.23` (explicit tag, never `latest`; base-digest comment above each FROM for provenance) | Alpine 3.24 is latest stable branch (2026-06); 3.23 is penultimate stable. Only Alpine/Debian bases allowed. Pre-submission checklist re-validates against alpinelinux.org (v3.25 would shift penultimate → bump tag). |
| SQL engine | PostgreSQL 17 (`postgresql17` from Alpine v3.23 repos; port 5432 internal) | Ships in 3.23 main repo (verified via pkgs.alpinelinux.org); mature stable major. Throwaway-container probe confirms binaries exist before real builds. |
| Services / images / containers | `inventory-database`, `billing-database`, `inventory-app`, `billing-app`, `rabbit-queue`, `api-gateway-app` (`image:` == service name == `container_name`) | Matches audit `docker ps`. Uppercase `RabbitMQ` in audit sample is illegal as OCI repository name → lowercase, justified in README decision table. |
| Named volumes | `inventory-database`, `billing-database`, `api-gateway-app` (exact bare names via `name:` override) | Audit `docker volume ls` expects literal names. |
| Exposed ports | ONLY `3000:3000` published on `api-gateway-app`; others `EXPOSE` only (5432 ×2, 8080 ×2, 5672 + 15672) | Outside access only via gateway:3000. Internal reachability proven by exec probe (§5 step 10). |
| Network | One bridge network `play-with-containers-network` | Managed by compose. |
| Restart policy | `restart: on-failure` ×6 → inspects as exactly `{on-failure 0}` | Matches audit verbatim. |
| Secrets | `.env` root-only; `.env.example` committed; nothing hardcoded. Doctrine: changing credentials after first init requires `make clean` (volume wipe) or in-place `ALTER ROLE` | Roles bake into volume at initdb; documented to avoid evaluator confusion. |
| Runtime | Python 3 apk + pip pure-Python wheels only; psycopg2 via apk `py3-psycopg2`; `PYTHONDONTWRITEBYTECODE=1` & `PYTHONUNBUFFERED=1` in ALL three app images | Deterministic musl builds; no pyc noise under read-only dirs. |
| POST `/api/movies` status | `200` (reference returns 201) | Audit asks literally for 200. |
| GET response contract | `GET /api/movies` → `{\"movies\": [ ... newest appended last ... ]}`; created movie guaranteed present. Single-movie endpoints return one JSON object | Fixes ambiguous audit wording \"body contains information of the last added movie\"; matches crud-master-py shape. |
| Billing payloads | Consumer coerces explicitly: `int(number_of_items)`, `float(total_amount)`, `str(user_id)`; malformed message → log prominently + ack + skip (retry-capped); poison JSON also logged+acked | Audit posts string-typed values (`"20"`, `"99"`, `"250"`); removes fragile implicit-cast path; prevents redelivery spin (prefetch 1). |
| App ↔ DB deps | `service_healthy` ONLY for app→database edges (`pg_isready`). All other deps (`service_started`) + in-app infinite retry/backoff loops as true resilience mechanism; RMQ start_period 90s / PG 45–60s | Avoids compose hang if RMQ cold-boot outlives healthcheck window mid-audit. |
| CLI | README documents `docker-compose` ↔ `docker compose` equivalence (audit sample uses hyphenated legacy form) | Graded artifact says docker-compose. |

Reference-solution violations we deliberately fix: `python:3.12-alpine`
(forbidden Hub image) → alpine:3.23 + system python; hardcoded `@localhost:5432`
→ env-driven hosts; POST 201 → 200; no restart policy / healthchecks.

## 3. Architecture

```
                          host port 3000 (only published port)
                               │
                     ┌─────────▼─────────┐
      HTTP (any verb) │   api-gateway-app  │── publish JSON ──►  ┌──────────────┐
       proxy /api/*   │  (Flask + waitress)│      AMQP 5672      │ rabbit-queue │
                ┌─────┴────────────────────┘ ◄────────────────────│  (RabbitMQ)  │
                │                                                 └──────────────┘
     /api/movies│                                                       ▲ consume
                ▼                                             billing-app│ durable queue
      ┌───────────────────┐                                    ┌──────────────┐
      │   inventory-app   │ SQLAlchemy                         │ billing-app  │ SQLAlchemy
      │ (Flask + waitress)│                                    │   consumer   │
      └─────────┬─────────┘                                    └──────┬───────┘
                │ 5432                                                │ 5432
      ┌─────────▼─────────┐                                   ┌────────▼────────┐
      │ inventory-database│ (volume: inventory-database)      │ billing-database│ (volume: billing-database)
      └───────────────────┘                                   └─────────────────┘
        all on one bridge network; gateway logs volume → api-gateway-app
```

Queue semantics satisfy audit resilience check: gateway always answers 200
while RabbitMQ buffers durable messages even when billing-app is down; on
restart the consumer processes outstanding messages and acks. Note in README:
billing is asynchronous — a just-posted order may not appear instantly until
consumed (pre-empts auditor confusion).

## 4. Repo layout (to create)

```
play-with-containers/
├── README.md                      # full docs + decision-record table + crud-master crosswalk + audit Q&A appendix
├── .env                           # local secrets (gitignored, from .env.example)
├── .env.example                   # all variables, dummy values (symmetric HOST/PORT pairs)
├── .gitignore                     # .env, __pycache__, *.pyc, venv/, logs/, *.log
├── Makefile                       # up/down/build/logs/ps/restart/clean targets
├── docker-compose.yml             # single composer managing EVERYTHING
├── openapi.yaml                   # bonus: gateway API spec served at /api/docs
├── postman/play-with-containers.postman_collection.json   # bonus
├── scripts/
│   └── test_audit.sh              # machine-checkable audit assertions (bonus)
└── srcs/
    ├── api-gateway-app/{Dockerfile, requirements.txt, server.py,
    │                    app/{__init__.py, proxy.py, queue_sender.py}}
    ├── inventory-app/{Dockerfile, requirements.txt, server.py,
    │                  app/{__init__.py, extensions.py, movies.py}}
    ├── billing-app/{Dockerfile, requirements.txt, server.py,
    │               app/{orders.py, consume_queue.py}}
    ├── inventory-database/{Dockerfile, init-db.sh}
    ├── billing-database/{Dockerfile, init-db.sh}
    └── rabbit-queue/{Dockerfile, entrypoint.sh}
```

## 5. Implementation steps

1. **Scaffold** — reconcile existing files: add `*.log` to `.gitignore`;
   remove half-orphan `BILLING_APP_PORT` from `.env.example` or pair it with a
   consumer-facing purpose; drop unused `rebuild` from `.PHONY` (or implement).
2. **Pre-flight probe (gate before any Dockerfile work)** — run throwaway
   container once:
   `docker run --rm alpine:3.23 sh -ec 'apk add -U postgresql17 rabbitmq-server py3-psycopg2 && command -v pg_isready rabbitmq-diagnostics || true && find /usr -name initdb -o -name postgres'`
   Records actual PostgreSQL bindir location (`/usr/lib/postgresql17/bin` vs
   `/usr/libexec/postgresql…`). Result feeds Step 3 ENV PATH.
3. **Both DB images** — Dockerfile: FROM alpine:3.23; `apk add --no-cache
   bash postgresql17 py3-psycopg2`; explicit
   `ENV PATH="<verified-bindir>:$PATH"`; COPY init script; ENTRYPOINT bash.
   `init-db.sh`: chown `$PGDATA` to postgres ONLY when `$PGDATA/PG_VERSION`
   absent (avoids per-restart recursive chown cost); as postgres user:
   `initdb` when empty → temp instance on unix socket → **psql WITHOUT
   dollar-quote interpolation** (psql vars don't expand inside `$$`):
   ```sql
   SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'db_user', :'db_password')
     WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'db_user') \gexec
   SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'db_user')
     WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db_name') \gexec
   SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', :'db_name', :'db_user') \gexec
   ```
   → stop temp → `exec postgres`. Parameterized via compose-passed env names so
   one template serves both DBs.
4. **rabbit-queue image** — FROM alpine:3.23; `apk add --no-cache
   rabbitmq-server`; `rabbitmq-plugins enable --offline rabbitmq_management`;
   COPY entrypoint; entrypoint launches server bg, awaits node
   (rabbitmq-diagnostics ping loop), idempotent user/tag/permission setup with
   backoff retries (up to N attempts, not bare `|| true` so races surface),
   `wait` keeps PID 1 alive. Healthcheck: `rabbitmq-diagnostics -q ping`
   start_period 90s interval 10s retries 30.
5. **inventory-app** — reference code ported: DB URI from
   `INVENTORY_DB_HOST/PORT/USER/PASSWORD/NAME`; waitress APP_PORT 8080;
   blueprint `strict_slashes=False` (both slash spellings work through proxy);
   GET(+`?title=` filter)/POST(→**200**)/DELETE-all, `/:id` GET/PUT/DELETE;
   GET returns `{"movies":[...]}` per contract row §2.
   Pinned deps (see §8).
6. **billing-app** — orders model (id, user_id str/int per contract decision,
   number_of_items int, total_amount float); `consume_queue`: durable queue,
   `basic_qos(prefetch_count=1)`, callback = coerce types explicitly → insert →
   ack; malformed/poison message → log + ack (no infinite nack-requeue spin);
   transient DB error → log + leave unacked (redelivered later) but count
   redeliveries and cap before log+ack+skip. server.py creates schema first.
7. **api-gateway-app** — proxy bp (env-driven INVENTORY_APP_HOST/PORT,
   method/query/body/status passthrough) + `/api/billing/` POST (JSON-required
   → publish stringified body → `{"message": "... sent"}, 200`);
   queue_sender uses pika PlainCredentials env vars, durable declare+publish;
   logging dual-writes stdout + `/usr/src/logs/gateway.log` with shared formatter.
8. **docker-compose.yml** — six services: image==container_name==service name;
   DB services get healthcheck `pg_isready -U $user -d $db` (start_period 60s);
   apps depend_on their database `service_healthy` ONLY; gateway→inventory-app/
   rabbit-queue are `service_started` (in-app retry handles readiness);
   `restart: on-failure` all; one network + three named volumes with exact
   `name:` overrides; gateway log volume mount at `/usr/src/logs`; NO
   deprecated top-level `version:`. All env via `${VAR}` interpolation.
9. **Pinned Python stacks (build reproducibility)** — enumerate exact versions
   in each requirements.txt during implementation (Flask 3.x line, waitress
   3.x, SQLAlchemy 2.x, Flask-SQLAlchemy 3.1.x, pika 1.3.x, requests 2.32.x);
   assert import smoke test inside build (`python -c "import flask,waitress,
   sqlalchemy,pika"` in gateway/apps).
10. **README.md** — prerequisites (Linux + Docker Engine + compose plugin +
    `docker-compose` compat note); .env variable table incl. credential-rotation
    doctrine; setup/usage (`cp .env.example .env`, `docker-compose up --build`,
    down `-v`); Postman/curl walkthrough mirroring every audit call including
    stop-billing resilience demo; async-billing caveat note; **decision-record
    table** consolidating deliberate deviations (HTTP 200 vs 201; lowercase
    `rabbit-queue`; `on-failure` vs prod-common alternatives; internal-only
    ports) each citing subject/audit lines; **crud-master lineage crosswalk**
    (endpoint/entity/config-key mapping proving own-solution adaptation);
    **study-answer appendix** for every oral question (containers, VMs vs
    containers, Docker, microservices, queues, RabbitMQ, Dockerfile
    instructions walkthrough, volumes, networks, images).
11. **scripts/test_audit.sh (machine-checkable)** — assertions:
    - 6× `docker inspect -f "{{ .HostConfig.RestartPolicy }}"` == `{on-failure 0}`
    - `docker volume ls --format` yields exactly {inventory-database,
      billing-database, api-gateway-app}
    - `docker ps --format '{{.Names}} {{.Ports}}'` shows exactly ONE published
      mapping (gateway 3000)
    - movies POST → 200 → GET shows created record (both slash spellings)
    - stop billing-app → POST billing → 200 → start → row lands in orders
    - external isolation: curl to :5432/:8080/:5672 refused from host
    - internal reachability: `docker exec api-gateway-app wget -qO-
      http://inventory-app:8080/api/movies` succeeds (proves 8080/5432
      accessible inside network per subject wording)
    Harness gated on `docker-compose up --wait --wait-timeout 180` so hangs are
    loud and bounded rather than silent deadlocks.
12. **Local verification** — full build, up, run test_audit.sh, manually re-run
    representative audit flows; fix whatever surfaces; grep repo for leaked
    secrets as final hygiene pass.
13. **Review agents (re-run)** — same two agents as this v2 cycle:
    correctness + completeness; iterate until clean; then update Alpine
    penultimate re-validation checklist item (check alpinelinux.org immediately
    before submission; bump FROM tags if needed).

## 6. Audit checklist → coverage map

| Audit item | Covered by |
|---|---|
| Required files submitted | §4 tree |
| `.env` excluded; no creds pushed | `.gitignore`, placeholders, verification grep |
| README complete | Step 10 |
| Architecture reflects subject | §3 diagram; 6 containers, 3 volumes, 1 network |
| `docker-compose up` clean start | healthchecks + two-tier deps (step 8); bounded wait harness |
| Dockerfile per service; Debian/Alpine based | alpine:3.23 everywhere |
| Restart policy `{on-failure 0}` | step 8; asserted by test_audit.sh |
| Volumes correct | 3 named volumes, exact names |
| Only gateway exposed outside | single `ports:`; isolation assertion |
| Images same name as service | `image:` == service name |
| Movies POST/GET ⇒ 200 + last-added visible | steps 5+7; asserted |
| Billing POST ⇒ 200 even with billing-app stopped | durable queue buffering; asserted |
| Oral questions answered | README study appendix |

## 7. Risks & mitigations

- **PostgreSQL binary paths on Alpine**: resolved by step-2 probe + explicit
  ENV PATH (previously silent breaker).
- **psql var interpolation inside dollar quotes**: eliminated — `\gexec` +
  `format('%I/%L')` pattern mandated.
- **Health-gate deadlock on RMQ cold boot**: two-tier dependencies; healthchecks
  sized generously; bounded `--wait` harness makes any residual hang obvious.
- **musl wheel gaps**: pip limited to pure-Python; psycopg2 via apk; smoke-import
  assertion catches gaps at build time.
- **Poison-message spin**: prefetch 1, type-coercion, retry-cap with log+ack skip.
- **Volume/perms for Postgres**: guarded chown only when PGDATA empty.
- **Trailing-slash redirects through proxy**: strict_slashes=False; tested both spellings.
- **Audit naming ambiguity (RabbitMQ uppercase)**: lowercase enforced by OCI
  spec; defended in README decision table.
- **Credential rotation vs persisted volumes**: doctrine documented in README.

## 8. Pinned dependency baseline (enumerate at implementation time)

Gateway: Flask==3.1.*, waitress==3.0.*, pika==1.3.*, requests==2.32.*, Werkzeug==3.1.* (+transitives pinned exactly at freeze).
Inventory: Flask, Flask-SQLAlchemy==3.1.*, SQLAlchemy==2.0.*, waitress, psycopg2(apk).
Billing: SQLAlchemy, pika, psycopg2(apk).
Exact minor/patch pins chosen against what py3-psycopg2/apk resolve cleanly on alpine:3.23; recorded here at implementation time.

## 10. Canonical artifacts (pre-drafted in-plan)

These are pinned here so implementation reproduces them faithfully rather than
improvising. Final cosmetic detail may adapt to the Step-2 probe results, but
decisions encoded below are binding.

### 10.1 docker-compose.yml (full draft)

```yaml
services:
  inventory-database:
    build: ./srcs/inventory-database
    image: inventory-database
    container_name: inventory-database
    restart: on-failure
    environment:
      DB_USER: ${INVENTORY_DB_USER}
      DB_PASSWORD: ${INVENTORY_DB_PASSWORD}
      DB_NAME: ${INVENTORY_DB_NAME}
    volumes:
      - inventory-database:/var/lib/postgresql/data
    networks: [pwc-network]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \"$${DB_USER}\" -d \"$${DB_NAME}\""]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 60s

  billing-database:
    build: ./srcs/billing-database
    image: billing-database
    container_name: billing-database
    restart: on-failure
    environment:
      DB_USER: ${BILLING_DB_USER}
      DB_PASSWORD: ${BILLING_DB_PASSWORD}
      DB_NAME: ${BILLING_DB_NAME}
    volumes:
      - billing-database:/var/lib/postgresql/data
    networks: [pwc-network]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \"$${DB_USER}\" -d \"$${DB_NAME}\""]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 60s

  rabbit-queue:
    build: ./srcs/rabbit-queue
    image: rabbit-queue
    container_name: rabbit-queue
    restart: on-failure
    environment:
      RABBITMQ_USER: ${RABBITMQ_USER}
      RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD}
    expose: [5672, 15672]
    networks: [pwc-network]
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 10s
      retries: 30
      start_period: 90s

  inventory-app:
    build: ./srcs/inventory-app
    image: inventory-app
    container_name: inventory-app
    restart: on-failure
    environment:
      APP_PORT: 8080
      INVENTORY_DB_HOST: ${INVENTORY_DB_HOST}
      INVENTORY_DB_PORT: ${INVENTORY_DB_PORT}
      INVENTORY_DB_USER: ${INVENTORY_DB_USER}
      INVENTORY_DB_PASSWORD: ${INVENTORY_DB_PASSWORD}
      INVENTORY_DB_NAME: ${INVENTORY_DB_NAME}
    expose: [8080]
    networks: [pwc-network]
    depends_on:
      inventory-database:
        condition: service_healthy

  billing-app:
    build: ./srcs/billing-app
    image: billing-app
    container_name: billing-app
    restart: on-failure
    environment:
      APP_PORT: 8080            # exposed per subject; worker itself serves no HTTP
      BILLING_DB_HOST: ${BILLING_DB_HOST}
      BILLING_DB_PORT: ${BILLING_DB_PORT}
      BILLING_DB_USER: ${BILLING_DB_USER}
      BILLING_DB_PASSWORD: ${BILLING_DB_PASSWORD}
      BILLING_DB_NAME: ${BILLING_DB_NAME}
      RABBITMQ_HOST: ${RABBITMQ_HOST}
      RABBITMQ_PORT: ${RABBITMQ_PORT}
      RABBITMQ_USER: ${RABBITMQ_USER}
      RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD}
      RABBITMQ_QUEUE: ${RABBITMQ_QUEUE}
    expose: [8080]
    networks: [pwc-network]
    depends_on:
      billing-database:
        condition: service_healthy
      rabbit-queue:
        condition: service_started   # consumer loops/retries internally

  api-gateway-app:
    build: ./srcs/api-gateway-app
    image: api-gateway-app
    container_name: api-gateway-app
    restart: on-failure
    ports:
      - "3000:3000"             # ONLY published port in the whole project
    environment:
      APP_PORT: 3000
      INVENTORY_APP_HOST: ${INVENTORY_APP_HOST}
      INVENTORY_APP_PORT: ${INVENTORY_APP_PORT}
      RABBITMQ_HOST: ${RABBITMQ_HOST}
      RABBITMQ_PORT: ${RABBITMQ_PORT}
      RABBITMQ_USER: ${RABBITMQ_USER}
      RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD}
      RABBITMQ_QUEUE: ${RABBITMQ_QUEUE}
    volumes:
      - api-gateway-app:/usr/src/logs
    networks: [pwc-network]
    depends_on:
      inventory-app:
        condition: service_started
      rabbit-queue:
        condition: service_started

networks:
  pwc-network:
    name: play-with-containers-network
    driver: bridge

volumes:
  inventory-database:
    name: inventory-database
  billing-database:
    name: billing-database
  api-gateway-app:
    name: api-gateway-app
```

Binding properties of this draft: exactly one `ports:` mapping project-wide;
`image:` == `container_name:` == service key everywhere; two-tier depends_on
(healthy only toward databases); volume `name:` overrides produce the bare
audit names; `restart: on-failure` produces `{on-failure 0}`; no deprecated
top-level `version:`.

### 10.2 Database entrypoint init-db.sh (algorithmic draft, one template both DBs)

Binding decisions: guarded first-boot-only init/chown (presence of
`$PGDATA/PG_VERSION`); temp-server bootstrap pass; **psql `\gexec` + `format()`
pattern (never `DO $$` interpolation)**; idempotent CREATE-or-ALTER so later
`make clean` isn't required merely to sync an edited `.env` password; final
process model is `exec postgres` (PID 1 = real server, SIGTERM clean shutdown).

```bash
#!/bin/bash
set -euo pipefail

PGDATA="${PGDATA:-/var/lib/postgresql/data}"
: "${DB_USER:?}" ; : "${DB_PASSWORD:?}" ; : "${DB_NAME:?}"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  echo "[init] first boot: creating cluster"
  chown -R postgres:postgres "$PGDATA"
  su-exec postgres initdb -D "$PGDATA" -U postgres \
    --auth-host=scram-sha-256 --auth-local=trust

  su-exec postgres pg_ctl -D "$PGDATA" -w start        # temp instance, unix sock
  psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
       -v db_user="$DB_USER" -v db_password="$DB_PASSWORD" -v db_name="$DB_NAME" \
     <<'PSQL'
SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'db_user', :'db_password')
 WHERE NOT EXISTS (SELECT FROM pg_roles    WHERE rolname = :'db_user') \gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'db_user', :'db_password')
 WHERE     EXISTS (SELECT FROM pg_roles    WHERE rolname = :'db_user') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'db_user')
 WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db_name') \gexec
SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I',
              :'db_name', :'db_user') \gexec
PSQL
  su-exec postgres pg_ctl -D "$PGDATA" -m fast -w stop
else
  echo "[init] existing cluster detected: skipping init"
fi

exec su-exec postgres postgres -D "$PGDATA"
```

### 10.3 rabbit-queue entrypoint.sh (algorithmic draft)

Binding decisions: management plugin enabled offline at BUILD time (not
boot); boot = background server → bounded ping-await loop (retries, not bare
sleep) → idempotent user/tag/perms setup → `wait $PID`; consumer clients own
the durable queue declaration (`queue_declare durable=True`) so broker-side
setup stays minimal.

```bash
#!/bin/bash
set -euo pipefail
: "${RABBITMQ_USER:?}" ; : "${RABBITMQ_PASSWORD:?}"

rabbitmq-server &
SERVER_PID=$!

for i in $(seq 1 60); do                       # ~60x2s max await
  rabbitmq-diagnostics -q ping >/dev/null 2>&1 && break
  [ "$i" -eq 60 ] && { echo "rabbit node never became ready"; exit 1; }
  sleep 2
done

rabbitmqctl add_user "$RABBITMQ_USER" "$RABBITMQ_PASSWORD" 2>/dev/null || true
rabbitmqctl authenticate_user "$RABBITMQ_USER" "$RABBITMQ_PASSWORD" || true
rabbitmqctl set_user_tags "$RABBITMQ_USER" administrator
rabbitmqctl set_permissions -p / "$RABBITMQ_USER" ".*" ".*" ".*"

wait "$SERVER_PID"                              # PID1 semantics live here
```

### 10.4 App-code contracts (fixed signatures the implementations must satisfy)

- inventory-app Flask blueprint routes: `/api/movies` + `/api/movies/<int:id>`
  with `strict_slashes=False`; GET-all honors `?title=` substring filter;
  POST success returns `(body, 200)`; response envelope `{"movies": [...]}`;
  single-movie endpoints return bare JSON objects.
- billing-app callback order: log receive → json.loads (failure → log+ack) →
  explicit coercion `int(number_of_items)`, `float(total_amount)`,
  `str(user_id)` → insert → ack. Redelivery counter guards transient failures.
- gateway `/api/billing/`: reject non-JSON 400 → publish stringified body →
  reply `{"message": "<raw payload> sent"}, 200`.
- Logging (gateway): python logging → StreamHandler(stdout) +
  RotatingFileHandler('/usr/src/logs/gateway.log'), same formatter/timezone;
  request line + upstream status recorded.

## 11. Validation loop (build-time quality gate)

Every implementation milestone passes through gates G0–G5; a failed gate sends
work back to the ROOT CAUSE fix, then **reruns from the earliest affected gate**
(Dockerfile/script edits ⇒ G1 restart; compose/env edits ⇒ G2 restart; pure
code edits ⇒ G4 restart). Review agents (G5) sit OUTSIDE the inner loop and
their confirmed findings re-enter it. Completion requires ALL gates green AND
review findings resolved.

| Gate | Trigger | Command / criterion | Fail action |
|---|---|---|---|
| **G0 Pre-flight** | before any Dockerfile | throwaway `alpine:3.23` run: apk adds succeed; `initdb`, `pg_isready`, `rabbitmq-diagnostics` locations recorded | adjust pkg names/ENV PATH in plan §5.2–3 |
| **G1 Build** | each build of images | `docker-compose build` exit 0; per-image smoke `python -c "import flask,waitress,sqlalchemy,pika"`; hadolint optional | fix Dockerfile/deps → re-probe G0 |
| **G2 Up** | infrastructure start | `docker-compose up --wait --wait-timeout 180` exit 0; 6 containers `running` | logs triage; compose/healthcheck fix → G2 |
| **G3 Static config** | after every `up` | inspect asserts: 6× RestartPolicy==`{on-failure 0}`; `docker volume ls` == exactly 3 bare names; network present; `docker ps` shows exactly ONE published port (0.0.0.0:3000); REPOSITORY list == 6 service names | compose edit → G2 |
| **G4 Functional** | code or compose change | scripts/test_audit.sh all-pass: movies POST 200 both slash variants → GET contains last-added + `?title=` filter; billing POST 200 normal; STOP billing-app → POST 200; START → order row appears; external curl to 5432/8080/5672 refused; intra-net `wget http://inventory-app:8080` succeeds; gateway.log grows | code fix → G4 |
| **G5 Hygiene + review** | before declaring done | git check-ignore .env verified; repo-wide secret grep; **correctness agent** reimplement-level sanity; **completeness agent** line-by-line vs readme.md+audit.md; iterate until zero confirmed findings | fix findings → re-enter loop from G1 |

Additionally bounded randomness is eliminated: `--wait` caps hang risk (§7),
and the harness prints a PASS/FAIL matrix per assertion so any regression is
attributable to exactly one gate.

## 12. Bonus items (implemented)

- Own adapted crud-master services ✔ (crosswalk documented)
- Healthchecks + start-order resilience ✔
- Gateway structured logging to persistent volume ✔ (size-rotation + stdout copy)
- OpenAPI/Swagger spec served at /api/docs ✔
- Postman collection reproducing every audit call ✔
- Machine-checkable scripts/test_audit.sh (CI-ready) ✔
- Makefile convenience targets ✔
