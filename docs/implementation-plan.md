# Play with Containers — Implementation Plan

Project: `/home/ertval/code/zone-modules/play-with-containers`
Date: 2026-08-27
Sources read: `docs/requirements/readme.md`, `docs/requirements/audit.md`,
https://github.com/01-edu/crud-master-py (README, config.yaml, .env.example,
all three services' source code, Dockerfiles, requirements.txt, setup scripts),
https://alpinelinux.org/releases/ (Alpine 3.24.1 current stable 2026-06-13, 3.23.5 penultimate stable).

---

## 1. Goal

Implement the `play-with-containers` subject fully: a 6-service microservices
infrastructure managed exclusively by `docker compose`, passing every item in
`audit.md` (including all conceptual questions), reusing/adapting the
`crud-master-py` reference services. A final review-agent pass verifies
correctness and completeness.

## 2. Key Decisions & Architectural Rules (Single Source of Truth)

| Item | Value | Rationale |
|---|---|---|
| Base image for ALL Dockerfiles | `alpine:3.23.5` (explicit patch pin, never `latest`; optional `@sha256:` digest) | Alpine 3.24.1 is latest stable 2026-06-13; 3.23.5 is latest patch of penultimate stable branch. Subject requires penultimate stable Alpine or Debian. Pin patch for reproducibility (hadolint DL3006); `alpine:3.23` floats. |
| SQL engine | PostgreSQL 17 (`postgresql17`, `postgresql17-contrib`, `su-exec` via apk, port 5432 internal) | Ships in Alpine 3.23 main/community repo; mature stable major; uses POSIX `/bin/sh` + `su-exec` for clean privilege drop without bash/gosu. |
| Message Broker | RabbitMQ (`rabbitmq-server` via apk, native declarative env config, AMQP 5672 internal only) | Native AMQP 5672; configured via `RABBITMQ_DEFAULT_USER/_PASS`; `rabbitmq_management` plugin enabled offline but port 15672 not published — audit `docker ps` shows only `5672/tcp`. Durable queue declared idempotently by publisher/consumer. |
| Services / images / containers (names shared) | `inventory-database`, `billing-database`, `inventory-app`, `billing-app`, `rabbit-queue`, `api-gateway-app` | Matches audit `docker ps` & `docker images` REPOSITORY/NAMES listing. Subject prose `inventory-db` vs audit `inventory-database` — audit console output is graded artifact. `RabbitMQ` uppercase in audit sample is OCI-forbidden (Docker spec: lowercase only), so `rabbit-queue` lowercase justified in README. |
| Named volumes | `inventory-database`, `billing-database`, `api-gateway-app` (exact bare names via top-level `name:` override) | Audit `docker volume ls` expects literal un-prefixed names; without `name:` compose prefixes with project name. |
| Exposed ports | ONLY `3000:3000` on `api-gateway-app`. Others: internal `EXPOSE` only (`5432`×2, `8080`×2, `5672` on rabbit) | Subject rule: "Any outside request must access only api-gateway-app via 3000." `EXPOSE` appears in `docker ps` as `5432/tcp`/`8080/tcp` without host publish. |
| Network | One bridge network `play-with-containers-network` (explicit `name:`, `driver: bridge`) connecting all 6 services | Managed entirely by `docker compose`; explicit name avoids project prefix. |
| Restart policy | `restart: on-failure` on every service (inspects as `{on-failure 0}`) | Subject: "Containers must be restarted in case of failure." Audit literally runs `docker inspect -f "{{ .HostConfig.RestartPolicy }}"`. Production best practice `unless-stopped` would show different value and fail audit — documented as audit-forced trade-off. |
| Secrets management | `.env` at root only; `.env.example` committed with dummy values; `.env` in `.gitignore` and `.dockerignore`; no secrets hardcoded in code/Dockerfiles/compose | Strict audit requirement; verified via `grep -R` in Step 10. |
| Runtime language | Python 3 from Alpine apk (`python3`, `py3-pip`, `py3-psycopg2` from apk); pip installs only pure-Python wheels (Flask, waitress, SQLAlchemy, flask-sqlalchemy, pika, requests) | `py3-psycopg2` precompiled avoids musl C compilation of `psycopg2-binary`; deterministic fast builds. `PYTHONUNBUFFERED=1` set. |
| POST `/api/movies` status | `200` (reference solution returns `201`) | Audit `audit.md:181` literally tests success code `200`; deviation documented in README. |
| App ports & execution | `inventory-app` (waitress `0.0.0.0:8080`), `billing-app` (resilient Pika consumer loop + `EXPOSE 8080` for audit shape + `GET /health`), `api-gateway-app` (waitress `0.0.0.0:3000`) | Audit `docker ps` expects `8080/tcp` on both apps; `billing-app` exposes port even if primary role is queue consumer. |
| Container security | Non-root users (`appuser:1000` for apps, `postgres:70` for DBs, `rabbitmq:rabbitmq` for broker); `USER` set before `CMD`; minimal apk layers | Least-privilege best practice; official postgres image also runs as `postgres`. |

Reference-solution violations we deliberately fix:
`python:3.12-alpine` Hub image → forbidden pre-built base; hardcoded `@localhost:5432`
→ breaks cross-container DNS; `POST 201` → `200`; no healthchecks/restart logic →
added; `bash`/`gosu` → POSIX `sh`/`su-exec`.

---

## 3. Architecture Diagram & Traffic Flow

```
                           Host Port 3000
                                 │
                      ┌──────────▼──────────┐
       HTTP (any verb)│   api-gateway-app   │── publish JSON ──►  ┌──────────────┐
        proxy /api/*  │  (Flask + waitress) │      AMQP 5672      │ rabbit-queue │
                 ┌────┴─────────────────────┘ ◄───────────────────│  (RabbitMQ)  │
                 │                                                └──────────────┘
      /api/movies│ (strict_slashes=False, trailing slash support)       ▲ consume
                 ▼                                           billing-app│ durable queue
       ┌───────────────────┐                                  ┌──────────────┐
       │   inventory-app   │ SQLAlchemy                       │ billing-app  │ SQLAlchemy
       │ (Flask + waitress)│                                  │   consumer   │
       └─────────┬─────────┘                                  └──────┬───────┘
                 │ 5432                                              │ 5432
       ┌─────────▼─────────┐                                 ┌────────▼────────┐
       │ inventory-database│ (volume: inventory-database)    │ billing-database│ (volume: billing-database)
       └───────────────────┘                                 └─────────────────┘
         All on bridge network: play-with-containers-network
         Gateway file logs -> Volume: api-gateway-app mounted at /var/log/api-gateway
```

### Queue Resilience Guarantee

- Gateway answers `200 {"message": "<payload> sent"}` immediately upon publishing to RabbitMQ with `delivery_mode=2` (persistent) into durable `billing_queue` (`durable=True`, publisher confirms).
- When `billing-app` is stopped (`docker stop billing-app`), RabbitMQ buffers messages on disk (durable queue).
- On restart consumer reconnects with backoff, drains unacked messages, inserts rows into `billing-database`, `basic_ack`; DB errors `basic_nack(requeue=True)` without loss.

---

## 4. Repository Layout

```
play-with-containers/
├── README.md                      # Full docs: prerequisites, config table, setup, usage, audit Q&A
├── .env                           # Local secrets (GITIGNORED, copied from .env.example)
├── .env.example                   # Variable templates with safe dummy values
├── .gitignore                     # Ignores .env, __pycache__, *.pyc, venv/, *.log
├── .dockerignore                  # Ignores .git, .env, __pycache__, *.pyc, venv/, docs/
├── docker-compose.yml             # Single Compose managing all 6 services, 3 volumes, 1 network
├── Makefile                       # Convenience targets: up, down, build, logs, ps, clean, test
├── openapi.yaml                   # Bonus: OpenAPI 3.0 spec for gateway served at /api/docs
├── postman/
│   └── play-with-containers.postman_collection.json # Bonus: Postman collection mirroring audit steps
├── scripts/
│   └── test_audit.sh              # Bonus: automated end-to-end verification (audit flow)
├── docs/
│   ├── requirements/              # Subject readme.md and audit.md
│   ├── implementation-plan.md     # This plan
│   └── audit_preparation.md       # Comprehensive 15-question audit preparation guide
└── srcs/
    ├── api-gateway-app/
    │   ├── Dockerfile             # FROM alpine:3.23.5 (multi-layer cached, non-root, curl/wget for healthcheck)
    │   ├── requirements.txt
    │   ├── server.py              # Waitress runner, stdout + /var/log/api-gateway/gateway.log logging
    │   └── app/
    │       ├── __init__.py        # Flask factory, blueprints, strict_slashes=False
    │       ├── proxy.py           # Reverse proxy to inventory-app with method/query/body/status passthrough
    │       └── queue_sender.py    # Pika publisher with confirm + retry/backoff
    ├── inventory-app/
    │   ├── Dockerfile             # FROM alpine:3.23.5 (py3-psycopg2, non-root)
    │   ├── requirements.txt
    │   ├── server.py              # Waitress runner on 0.0.0.0:8080, PYTHONUNBUFFERED=1
    │   └── app/
    │       ├── __init__.py        # Flask factory, SQLAlchemy init, DB retry on startup
    │       ├── extensions.py      # SQLAlchemy db instance
    │       ├── models.py          # Movie model (id, title, description)
    │       └── movies.py          # /api/movies routes (GET, POST->200, PUT, DELETE, ?title= filter)
    ├── billing-app/
    │   ├── Dockerfile             # FROM alpine:3.23.5 (py3-psycopg2, non-root, HEALTHCHECK via wget)
    │   ├── requirements.txt
    │   ├── server.py              # Initializes schema, launches resilient consumer loop + /health
    │   └── app/
    │       ├── extensions.py      # SQLAlchemy db instance
    │       ├── orders.py          # Order model (id, user_id, number_of_items, total_amount)
    │       └── consume_queue.py   # Resilient Pika consumer with reconnect, prefetch=1, ack/nack
    ├── inventory-database/
    │   ├── Dockerfile             # FROM alpine:3.23.5 (postgresql17, postgresql17-contrib, su-exec)
    │   └── init-db.sh             # POSIX /bin/sh: initdb, listen_addresses='*', scram auth, exec postgres PID1
    ├── billing-database/
    │   ├── Dockerfile             # FROM alpine:3.23.5 (postgresql17, su-exec) — same template
    │   └── init-db.sh             # Reusable POSIX entrypoint parameterized via env
    └── rabbit-queue/
        ├── Dockerfile             # FROM alpine:3.23.5 (rabbitmq-server, management plugin offline)
        └── entrypoint.sh          # POSIX /bin/sh: chown, RABBITMQ_DEFAULT_USER/PASS, exec rabbitmq-server PID1
```

---

## 5. Detailed Implementation Steps

### Step 1: Project Scaffolding & Configuration

- Create `.gitignore` ignoring `.env`, `__pycache__/`, `*.pyc`, `venv/`, `*.log`, `logs/`.
- Create `.dockerignore` ignoring `.git`, `.env`, `__pycache__/`, `*.pyc`, `venv/`, `docs/`, `*.md` (except README) for efficient context.
- Create `.env.example` with documented keys and dummy values:
  - `INVENTORY_DB_USER`, `INVENTORY_DB_PASSWORD`, `INVENTORY_DB_NAME`, `INVENTORY_DB_HOST=inventory-database`, `INVENTORY_DB_PORT=5432`
  - `BILLING_DB_USER`, `BILLING_DB_PASSWORD`, `BILLING_DB_NAME`, `BILLING_DB_HOST=billing-database`, `BILLING_DB_PORT=5432`
  - `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `RABBITMQ_HOST=rabbit-queue`, `RABBITMQ_PORT=5672`, `RABBITMQ_QUEUE=billing_queue`
  - `INVENTORY_APP_HOST=inventory-app`, `INVENTORY_APP_PORT=8080`
  - `BILLING_APP_HOST=billing-app`, `BILLING_APP_PORT=8080`
  - `APIGATEWAY_PORT=3000`
- Generate local `.env` from `.env.example` for testing; never commit.

### Step 2: Database Services (`inventory-database` & `billing-database`)

- **Dockerfile** (both DBs, parameterized via compose `environment:`):
  ```dockerfile
  FROM alpine:3.23.5
  RUN apk add --no-cache postgresql17 postgresql17-contrib su-exec
  ENV PGDATA=/var/lib/postgresql/data
  RUN mkdir -p $PGDATA /run/postgresql && chown -R postgres:postgres $PGDATA /run/postgresql
  COPY init-db.sh /usr/local/bin/init-db.sh
  RUN chmod +x /usr/local/bin/init-db.sh
  EXPOSE 5432
  VOLUME /var/lib/postgresql/data
  ENTRYPOINT ["/usr/local/bin/init-db.sh"]
  ```
  Layer: single `apk add --no-cache` (no separate `apk cache` layer), pinned patch.

- **`init-db.sh` (POSIX `/bin/sh`, `set -eu`)**:
  1. Ensure `$PGDATA` and `/run/postgresql` owned by `postgres:postgres` (fix volume mount permissions).
  2. If `[ ! -s "$PGDATA/PG_VERSION" ]`:
     - `su-exec postgres initdb -D "$PGDATA" --auth-local=trust --auth-host=scram-sha-256 --username="$POSTGRES_USER"`
     - Append `listen_addresses = '*'` to `$PGDATA/postgresql.conf`.
     - Append `host all all 0.0.0.0/0 scram-sha-256` to `$PGDATA/pg_hba.conf`.
     - Temp boot on Unix socket: `su-exec postgres pg_ctl -D "$PGDATA" -o "-c listen_addresses=''" -w start`
     - Idempotent SQL (guarded by `PG_VERSION` check; `DO $$` also safe if re-entered):
       ```sql
       DO $$ BEGIN
         IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'db_user') THEN
           CREATE ROLE :"db_user" WITH LOGIN ENCRYPTED PASSWORD :'db_password';
         END IF;
       END $$;
       SELECT 'CREATE DATABASE :"db_name" OWNER :"db_user"' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db_name') \gexec
       GRANT ALL PRIVILEGES ON DATABASE :"db_name" TO :"db_user";
       ```
       Invoked via `psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -v db_user="$DB_USER" -v db_password="$DB_PASSWORD" -v db_name="$DB_NAME"`.
     - Stop temp: `su-exec postgres pg_ctl -D "$PGDATA" -m fast -w stop`
  3. Final: `exec su-exec postgres postgres -D "$PGDATA"` — PID 1, signal clean, `chmod 0700 "$PGDATA"` enforced.

  Compose maps `INVENTORY_DB_USER` → `POSTGRES_USER`/`DB_USER` etc. via `environment:`.

### Step 3: RabbitMQ Service (`rabbit-queue`)

- **Dockerfile**:
  ```dockerfile
  FROM alpine:3.23.5
  RUN apk add --no-cache rabbitmq-server su-exec
  RUN rabbitmq-plugins enable --offline rabbitmq_management
  COPY entrypoint.sh /usr/local/bin/entrypoint.sh
  RUN chmod +x /usr/local/bin/entrypoint.sh
  EXPOSE 5672
  ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
  ```
  Note: 15672 not exposed/published — management UI internal only.

- **`entrypoint.sh` (POSIX `/bin/sh`, `set -eu`)**:
  - `chown -R rabbitmq:rabbitmq /var/lib/rabbitmq /var/log/rabbitmq` (volume-safe).
  - Export `RABBITMQ_DEFAULT_USER="$RABBITMQ_USER"` and `RABBITMQ_DEFAULT_PASS="$RABBITMQ_PASSWORD"` to runtime (native declarative, no background `rabbitmqctl add_user` race).
  - `exec su-exec rabbitmq rabbitmq-server` as PID 1 (no `&`/`wait`).
  - Queue `billing_queue` durability `durable=True` declared by publisher/consumer on connect — fully idempotent, no entrypoint race.

- Healthcheck (in compose, not Dockerfile):
  ```yaml
  healthcheck:
    test: ["CMD-SHELL", "rabbitmq-diagnostics -q ping"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 20s
  ```

### Step 4: Inventory Application (`inventory-app`)

- **Dockerfile**:
  ```dockerfile
  FROM alpine:3.23.5
  ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
  RUN apk add --no-cache python3 py3-pip py3-psycopg2 wget
  WORKDIR /usr/src/app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt --break-system-packages
  COPY . .
  RUN adduser -D -u 1000 appuser && chown -R appuser:appuser /usr/src/app
  USER appuser
  EXPOSE 8080
  CMD ["python3", "server.py"]
  ```
  `wget` included for healthcheck without adding `curl`; layer order caches `pip install`.

- **Endpoints & Behavior**:
  - Build SQLAlchemy URI from `INVENTORY_DB_HOST/PORT/USER/PASSWORD/NAME` (no `localhost`).
  - Startup DB retry loop (5× with backoff) to survive DB init race even with `depends_on`.
  - Blueprints `strict_slashes=False`:
    - `POST /api/movies` & `POST /api/movies/`: validate `{"title": "...", "description": "..."}`, create, return **200** with movie JSON.
    - `GET /api/movies` & `GET /api/movies/` (+`?title=` filter `%LIKE%`), `GET /api/movies/<id>`, `PUT /api/movies/<id>`, `DELETE /api/movies/<id>` & `/api/movies/`.
  - Waitress `serve(app, host="0.0.0.0", port=8080)`.
  - `GET /health` → `200 {"status":"ok"}` for compose healthcheck.

### Step 5: Billing Application (`billing-app`)

- **Dockerfile**: identical base to inventory-app (apk `py3-psycopg2`, non-root, `wget`), `EXPOSE 8080`, `CMD ["python3", "server.py"]`.
- **Consumer & DB Logic**:
  - URI from `BILLING_DB_*`.
  - On startup `db.create_all()` for `orders` table (`id PK, user_id TEXT, number_of_items INT, total_amount FLOAT`); idempotent.
  - Resilient loop `consume_queue.py`:
    - `pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)`, `ConnectionParameters(host=RABBITMQ_HOST, port=5672, heartbeat=30, blocked_connection_timeout=300, retry_delay=5, connection_attempts=10)` with outer `while True: try: connect ... except: sleep 5`.
    - `channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)`
    - `channel.basic_qos(prefetch_count=1)`
    - Callback: `json.loads` → `Order(...)` → `db.session.commit()` → `ch.basic_ack(delivery_tag=method.delivery_tag)`; on `json` error `basic_ack` (poison), on DB error `db.session.rollback(); ch.basic_nack(requeue=True)`.
  - `server.py` starts health HTTP thread (`GET /health`) alongside consumer so `EXPOSE 8080` + healthcheck valid.

### Step 6: API Gateway Application (`api-gateway-app`)

- **Dockerfile**:
  ```dockerfile
  FROM alpine:3.23.5
  ENV PYTHONUNBUFFERED=1
  RUN apk add --no-cache python3 py3-pip wget
  WORKDIR /usr/src/app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt --break-system-packages
  COPY . .
  RUN mkdir -p /var/log/api-gateway && adduser -D -u 1000 appuser && chown -R appuser:appuser /usr/src/app /var/log/api-gateway
  USER appuser
  EXPOSE 3000
  CMD ["python3", "server.py"]
  ```

- **Routing & Proxy Logic**:
  - Logging: `logging` to both `StreamHandler(sys.stdout)` and `RotatingFileHandler('/var/log/api-gateway/gateway.log', maxBytes=5*1024*1024, backupCount=3)` (prevents volume fill).
  - Blueprint `/api/movies` (and `/api/movies/` via `strict_slashes=False`): proxies **all verbs** (`GET, POST, PUT, DELETE`), query string, headers, body via `requests.request(method, f"http://{INVENTORY_APP_HOST}:{INVENTORY_APP_PORT}/api/movies{path}", params=request.args, data=request.get_data(), headers={k:v for k,v in request.headers if k.lower()!="host"}, timeout=5)`, returns exact upstream `status_code` + `content` + `headers`. Handles trailing slash preservation.
  - Blueprint `/api/billing` & `/api/billing/` `POST`: validates JSON requires `user_id`, `number_of_items`, `total_amount` (400 if missing/invalid), then via `queue_sender.py` declares `billing_queue durable=True` and `basic_publish(exchange='', routing_key=RABBITMQ_QUEUE, body=json.dumps(payload), properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent, content_type="application/json"))` with channel confirms and retry; returns `{"message": "<stringified payload> sent"}, 200`.
  - `GET /api/docs` serves `openapi.yaml` static.
  - Waitress `0.0.0.0:3000`.

### Step 7: Complete Docker Compose Orchestration (`docker-compose.yml`)

- Managed exclusively by `docker compose` (v2, no deprecated `version:`).
- Define 6 services with `image:` == service name, `container_name:` fixed, `restart: on-failure`, explicit `networks:` and `volumes:`:

  1. `inventory-database`:
     ```yaml
     image: inventory-database
     container_name: inventory-database
     restart: on-failure
     environment:
       POSTGRES_USER: ${INVENTORY_DB_USER}
       POSTGRES_PASSWORD: ${INVENTORY_DB_PASSWORD}
       DB_USER: ${INVENTORY_DB_USER}
       DB_PASSWORD: ${INVENTORY_DB_PASSWORD}
       DB_NAME: ${INVENTORY_DB_NAME}
       PGDATA: /var/lib/postgresql/data
     volumes: ["inventory-database:/var/lib/postgresql/data"]
     healthcheck: {test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${DB_NAME}"], interval: 10s, timeout: 5s, retries: 5, start_period: 30s}
     networks: [play-with-containers-network]
     logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}
     ```
  2. `billing-database`: same template with `BILLING_DB_*`, `billing-database` volume.
  3. `rabbit-queue`:
     ```yaml
     image: rabbit-queue
     container_name: rabbit-queue
     restart: on-failure
     environment: {RABBITMQ_USER: ${RABBITMQ_USER}, RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD}, RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER}, RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}}
     healthcheck: {test: ["CMD-SHELL", "rabbitmq-diagnostics -q ping"], interval: 10s, timeout: 5s, retries: 5, start_period: 20s}
     networks: [play-with-containers-network]
     logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}
     ```
  4. `inventory-app`:
     ```yaml
     image: inventory-app
     container_name: inventory-app
     restart: on-failure
     environment: {INVENTORY_DB_HOST: ${INVENTORY_DB_HOST}, INVENTORY_DB_PORT: ${INVENTORY_DB_PORT}, INVENTORY_DB_USER: ${INVENTORY_DB_USER}, INVENTORY_DB_PASSWORD: ${INVENTORY_DB_PASSWORD}, INVENTORY_DB_NAME: ${INVENTORY_DB_NAME}}
     depends_on: {inventory-database: {condition: service_healthy}}
     healthcheck: {test: ["CMD-SHELL", "wget -qO- http://localhost:8080/health || exit 1"], interval: 15s, timeout: 5s, retries: 3, start_period: 15s}
     networks: [play-with-containers-network]
     logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}
     ```
  5. `billing-app`:
     ```yaml
     image: billing-app
     container_name: billing-app
     restart: on-failure
     environment: {BILLING_DB_HOST: ${BILLING_DB_HOST}, BILLING_DB_PORT: ${BILLING_DB_PORT}, BILLING_DB_USER: ${BILLING_DB_USER}, BILLING_DB_PASSWORD: ${BILLING_DB_PASSWORD}, BILLING_DB_NAME: ${BILLING_DB_NAME}, RABBITMQ_HOST: ${RABBITMQ_HOST}, RABBITMQ_PORT: ${RABBITMQ_PORT}, RABBITMQ_USER: ${RABBITMQ_USER}, RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD}, RABBITMQ_QUEUE: ${RABBITMQ_QUEUE}}
     depends_on: {billing-database: {condition: service_healthy}, rabbit-queue: {condition: service_healthy}}
     healthcheck: {test: ["CMD-SHELL", "wget -qO- http://localhost:8080/health || exit 1"], interval: 15s, timeout: 5s, retries: 3, start_period: 15s}
     networks: [play-with-containers-network]
     logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}
     ```
  6. `api-gateway-app`:
     ```yaml
     image: api-gateway-app
     container_name: api-gateway-app
     restart: on-failure
     ports: ["${APIGATEWAY_PORT:-3000}:3000"]
     environment: {INVENTORY_APP_HOST: ${INVENTORY_APP_HOST}, INVENTORY_APP_PORT: ${INVENTORY_APP_PORT}, RABBITMQ_HOST: ${RABBITMQ_HOST}, RABBITMQ_PORT: ${RABBITMQ_PORT}, RABBITMQ_USER: ${RABBITMQ_USER}, RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD}, RABBITMQ_QUEUE: ${RABBITMQ_QUEUE}}
     volumes: ["api-gateway-app:/var/log/api-gateway"]
     depends_on: {inventory-app: {condition: service_healthy}, rabbit-queue: {condition: service_healthy}}
     healthcheck: {test: ["CMD-SHELL", "wget -qO- http://localhost:3000/health || exit 1"], interval: 15s, timeout: 5s, retries: 3, start_period: 15s}
     networks: [play-with-containers-network]
     logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}
     ```

- Top-level volumes with explicit `name:` (audit expects bare names):
  ```yaml
  volumes:
    inventory-database: {name: inventory-database}
    billing-database: {name: billing-database}
    api-gateway-app: {name: api-gateway-app}
  ```

- Top-level bridge network:
  ```yaml
  networks:
    play-with-containers-network:
      name: play-with-containers-network
      driver: bridge
  ```

- No `version:` field; `name: play-with-containers` optional top-level.
### Step 8: Documentation & Theoretical Audit Preparation Guide

- Prerequisites (Linux, Docker Engine 24+, Docker Compose v2.20+, `make`, `curl`/`Postman`).
- Env table with descriptions, `cp .env.example .env` setup.
- Usage: `docker compose up --build -d`, `docker compose logs -f`, `docker compose down` vs `down -v`.
- Curl & Postman walkthrough mirroring audit: `POST /api/movies/` 200, `GET /api/movies/` 200+JSON, `POST /api/billing/` 200, stop billing → POST 200 → restart → DB row appears, `docker volume ls`/`docker ps`/`docker inspect` checks, network isolation `curl localhost:5432` refused.
- Design justifications: Alpine 3.23.5 penultimate patch pin, lowercase `rabbit-queue` OCI compliance, `POST 200` vs 201, `restart: on-failure` audit-forced.
- Oral study guide: containers vs VMs, Docker engine (client/daemon/containerd/runc/OCI), Dockerfile instructions, volumes (named/bind/anonymous), networks (bridge/host/overlay/macvlan, DNS), microservices vs monolith, queues & RabbitMQ (AMQP, exchanges, durability, acks, prefetch).
This step produces two distinct, high-value documentation artifacts:

#### 8A. Root `README.md` (Project & Operational Documentation)
- **Title & Overview**: Architecture summary, microservices map, and design philosophy.
- **Prerequisites**: Linux environment, Docker Engine 24+, Docker Compose v2.20+, `make`, `curl`/`Postman`.
- **Configuration Reference**: Complete markdown table of all environment variables (`.env`), default dummy values, types, and descriptions.
- **Installation & Lifecycle**:
  - Quickstart: `cp .env.example .env && make up`
  - Management commands: `make build`, `make logs`, `make ps`, `make restart`, `make down`, `make clean`.
- **API Reference & Manual Audit Walkthrough**:
  - `POST /api/movies/` (JSON payload, HTTP 200 response specification).
  - `GET /api/movies/` (retrieval with query parameters `?title=` and trailing-slash handling).
  - `POST /api/billing/` (asynchronous queue dispatch, HTTP 200 response).
  - Resilience Demo: exact commands for stopping `billing-app`, dispatching billing requests while buffered in RabbitMQ, restarting `billing-app`, and verifying database persistence.
- **Architectural Justifications**:
  - Penultimate stable Alpine base image selection (`alpine:3.23.5`).
  - Strict lowercase naming compliance for OCI container images (`rabbit-queue`).
  - HTTP 200 return code alignment for POST endpoints.
  - Restart policy `{on-failure 0}` and single-gateway port exposure (`3000:3000`).
- **Links**: Direct link to the comprehensive theoretical study guide in `docs/audit_preparation.md`.

#### 8B. `docs/audit_preparation.md` (Complete Theoretical Study Guide & Audit Q&A Manual)
A standalone, exhaustive educational guide tailored for the student to master every container concept and ace the oral audit defense:
- **Part 1: In-Depth Theoretical Foundations**:
  1. *Containers vs. Virtual Machines*: OS kernel sharing, Linux isolation primitives (Namespaces: `pid`, `net`, `ipc`, `mnt`, `uts`, `user`; Control Groups: `cgroups v2` for CPU, memory, I/O limits), hypervisors (Type 1 vs Type 2), overhead, density, startup speed comparison.
  2. *Docker Engine & Architecture*: Client-Server model, `dockerd`, `containerd`, `runc`, OCI runtime and image specifications.
  3. *Dockerfile Deep-Dive & Layer Mechanics*: Union file systems (`overlay2`), layer caching, avoiding duplicate layers, instruction anatomy (`FROM`, `RUN`, `COPY`, `WORKDIR`, `USER`, `EXPOSE`, `ENV`, `ENTRYPOINT` vs `CMD` exec vs shell forms) — answers "What is Dockerfile? Explain instructions".
  4. *Docker Images & Build*: Read-only template, OCI image spec, image vs container vs Dockerfile, layer content-addressability, `docker images` REPOSITORY/TAG, why images are built not pulled (subject forbids pre-built except Alpine/Debian), image naming `image: == service` — answers "What is Docker image? Why use?".
  5. *Docker Volumes & Data Persistence*: Anonymous vs. Named vs. Bind Mounts, container write layers vs persistent storage, lifecycle across container removal — answers "What is volume? Why use?".
  6. *Docker Networking & Service Discovery*: User-defined bridge networks, container embedded DNS (`127.0.0.11`), network namespaces, port publishing (`-p host:container`) vs internal exposure (`EXPOSE`), why isolated bridge needed, only gateway `3000` exposed — answers "What is network? Why use?".
  7. *Microservices Architecture*: Principles (Single Responsibility, loose coupling, high cohesion, domain-driven boundaries), benefits (fault isolation, independent scalability, polyglot), tradeoffs vs monoliths (network latency, distributed state) — answers "What is microservices? Why use?".
  8. *Message Queuing & RabbitMQ*: Queue definition (FIFO buffer, decoupling), async vs sync HTTP blocking, AMQP 0-9-1, Producer/Exchange/Binding/Queue/Consumer, exchange types (`direct`, `fanout`, `topic`, `headers`), durability (`delivery_mode=2` + `durable=True`), acks (`basic_ack`/`basic_nack`), prefetch (`basic_qos`) — answers "What is queue? What is RabbitMQ?".
- **Part 2: Question-by-Question Model Answers for Audit (15 Questions)**:
  - Verbatim text of every question from `docs/requirements/audit.md`.
  - Structured 3-tier response format for each question:
    1. **Direct Oral Answer**: Concise, professional explanation to speak aloud to the auditor.
    2. **Deep Technical Breakdown**: The underlying mechanism explaining *why* it works that way.
    3. **Project Context**: Exact references to where and how this concept is implemented in `play-with-containers`.
- **Part 3: Interactive Audit Simulation & Terminal Commands**:
  - Step-by-step reproduction of every terminal command the auditor executes (`docker-compose up`, `docker ps`, `docker inspect -f "{{ .HostConfig.RestartPolicy }}"`, `docker volume ls`, `docker images`, Postman/curl requests, stopping/starting `billing-app`).


### Step 9: Makefile & Automation Harness

Standardize on `docker compose` (space) for v2:
```make
.PHONY: up down build logs ps clean restart help config lint test

help:
	@echo "  make up        - build and start infrastructure"
	@echo "  make build     - build all images"
	@echo "  make logs      - follow compose logs"
	@echo "  make ps        - container status"
	@echo "  make config    - validate compose file"
	@echo "  make lint      - hadolint Dockerfiles"
	@echo "  make test      - run audit E2E suite"

up:
	docker compose up --build -d

build:
	docker compose build

logs:
	docker compose logs -f

ps:
	docker compose ps

restart:
	docker compose restart

down:
	docker compose down

clean:
	docker compose down -v --remove-orphans

config:
	docker compose config --quiet && echo "compose OK"

lint:
	hadolint srcs/**/Dockerfile

test:
	bash scripts/test_audit.sh
```
Bonus `test` invokes `scripts/test_audit.sh`.

### Step 10: Automated & Manual End-to-End Verification

- `make config` and `make build` clean (no apk/pip warnings, layer cache hits on re-build).
- `make up` 6 containers `service_healthy` order; `docker compose ps` shows `healthy`.
- `docker ps` port shape: only `0.0.0.0:3000->3000` published; `5432/tcp`, `8080/tcp`, `5672/tcp` internal.
- `docker inspect -f "{{ .HostConfig.RestartPolicy }}" <name>` → `{on-failure 0}` ×6.
- `docker volume ls` → `inventory-database`, `billing-database`, `api-gateway-app` bare names.
- Host isolation: `curl -f localhost:5432`/`8080`/`5672` → refused; `curl -f localhost:3000/health` → 200.
- `scripts/test_audit.sh`:
  1. `POST /api/movies/` → 200 + movie JSON
  2. `GET /api/movies/` → 200 + list contains movie; `?title=` filter works; trailing slash both forms
  3. `POST /api/billing/` → 200
  4. `docker stop billing-app` → stopped
  5. `POST /api/billing/` → 200 while dead (buffer)
  6. `docker start billing-app` → row appears in `billing-database` via `psql`
  7. `docker exec api-gateway-app cat /var/log/api-gateway/gateway.log` grows; `docker compose logs` shows startup order.
- `grep -R "change_me" --exclude-dir=.git` must find no secrets outside `.env.example` (dummy only).

### Step 11: Multi-Agent Review Pass

- **Correctness**: syntax (`docker compose config`), Docker layer best practices (single `apk add`, non-root `USER`, `PYTHONUNBUFFERED`, hadolint), security (no secrets, `.gitignore`/`.dockerignore` effective), no malicious code.
- **Completeness**: line-by-line diff against `readme.md` + `audit.md` checklist `§6`; produce findings list; fix, re-verify until clean.

---

## 6. Audit Checklist & Requirement Traceability Matrix

| Audit Requirement | Verification Method | Implemented In |
|---|---|---|
| Required files present (`README.md`, `docker-compose.yml`, `srcs/**`, `Makefile`) | `ls` repo tree | §4 Repository Layout |
| `.env` excluded from Git & no secrets in repo | `git status --ignored`, `.gitignore`/`.dockerignore`, `grep -R` dummy values only in `.env.example` | Step 1, Step 10 |
| Comprehensive `README.md` with audit Q&A | Full study guide (containers, VMs, Docker, microservices, queues) | Step 8 |
| Infrastructure starts cleanly with `docker compose up` | `docker compose up --build -d` `service_healthy` chain | Step 7, Step 10 |
| Dockerfile per service based on Alpine/Debian, pinned | `FROM alpine:3.23.5` ×6, `apk add --no-cache` pinned | Steps 2–6 |
| Restart policy `{on-failure 0}` on all containers | `docker inspect -f "{{ .HostConfig.RestartPolicy }}"` ×6 | Step 7, Step 10 |
| 3 named volumes matching exact audit names | `docker volume ls` | Step 7 (name: override) |
| Port 3000 on gateway is ONLY host-exposed port | `docker ps` + `curl localhost:5432/8080/5672` refused | Step 7, Step 10 |
| Docker image names match service names | `docker images` REPOSITORY column | Step 7 (`image:` == service) |
| POST `/api/movies/` returns 200 + created movie JSON | `curl -X POST .../api/movies/` | Step 4, Step 6 |
| GET `/api/movies/` returns 200 + movie list (incl. trailing slash & `?title=`) | `curl -X GET .../api/movies/` | Step 4, Step 6 |
| POST `/api/billing/` returns 200 | `curl -X POST .../api/billing/` | Step 5, Step 6 |
| POST `/api/billing/` returns 200 with `billing-app` stopped | `docker stop billing-app` then POST | Step 5, Step 6, Step 10 |
| Queued messages processed upon `billing-app` restart | `docker start billing-app` then `psql` row appears | Step 5, Step 10 |
| Gateway logs persisted in `api-gateway-app` volume | `docker exec` cat `/var/log/api-gateway/gateway.log` | Step 6, Step 7 |
| Oral theoretical questions answered | Comprehensive README §8 study guide | Step 8 |

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation Strategy |
|---|---|---|
| **Alpine musl C-extension compilation** | Build failure / bloated images | Use `py3-psycopg2` from apk; pip only pure-Python wheels; `pip --no-cache-dir`; pin versions. |
| **Database PGDATA permission / re-init** | Postgres fails on restart or volume re-attach | Check `[ ! -s "$PGDATA/PG_VERSION" ]` before `initdb`; `chown postgres` + `chmod 0700`; `VOLUME` at `/var/lib/postgresql/data`. |
| **Trailing slash 308 redirect** | `POST /api/movies` 308 via proxy | `strict_slashes=False` on Flask blueprints + proxy preserves raw path; integration test covers both spellings. |
| **RabbitMQ audit image name (`RabbitMQ` uppercase)** | OCI spec forbids uppercase → audit mismatch | Name image `rabbit-queue`; document OCI lower-case requirement in README justification. |
| **Cold-start races (DB/RabbitMQ not ready)** | App crash on first connect | Compose `depends_on: condition: service_healthy` + in-app retry/backoff loops + `healthcheck` `start_period`. |
| **Log volume permissions / fill** | Gateway crash or host disk fill | `mkdir -p /var/log/api-gateway` + `chown appuser`; `RotatingFileHandler` 5MB×3 + `json-file` `max-size:10m`. |
| **Floating base tag drift** | Non-reproducible builds across hosts | Pin `alpine:3.23.5` (+ sha256), `apk add pkg=version`, `requirements.txt` pinned hashes. |

---

## 8. Bonus Features Included

- Reusing/adapting `crud-master-py` architecture for full custom solution ✔
- Robust Docker healthchecks (`interval`/`timeout`/`retries`/`start_period`) with dependency-ordered `service_healthy` startup ✔
- Gateway structured dual logging (stdout + `api-gateway-app` persistent volume with rotation) ✔
- Complete OpenAPI 3.0 spec (`openapi.yaml`) served at `/api/docs` ✔
- Postman Collection (`postman/play-with-containers.postman_collection.json`) mirroring audit curls ✔
- Automated E2E verification suite (`scripts/test_audit.sh`) covering resilience (stop → POST → restart) ✔
- Enhanced `Makefile` with `config`/`lint`/`test` diagnostic targets ✔
