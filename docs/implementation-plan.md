# Play with Containers — Implementation Plan

Project: `/home/ertval/code/zone-modules/play-with-containers`
Date: 2026-08-27
Sources read: `docs/requirements/readme.md`, `docs/requirements/audit.md`,
https://github.com/01-edu/crud-master-py (README, config.yaml, .env.example,
all three services' source code, Dockerfiles, requirements.txt, setup scripts),
https://alpinelinux.org/releases/ (Alpine 3.24 current stable June 2026, 3.23 penultimate stable).

---

## 1. Goal

Implement the `play-with-containers` subject fully: a 6-service microservices
infrastructure managed exclusively by `docker-compose`, passing every item in
`audit.md` (including all conceptual questions), reusing/adapting the
`crud-master-py` reference services. A final review-agent pass verifies
correctness and completeness.

## 2. Key Decisions & Architectural Rules (Single Source of Truth)

| Item | Value | Rationale |
|---|---|---|
| Base image for ALL Dockerfiles | `alpine:3.23` (explicit tag, never `latest`) | Alpine 3.24 is the latest stable branch; 3.23 is the penultimate stable branch. Subject requires penultimate stable Alpine or Debian. |
| SQL engine | PostgreSQL 17 (`postgresql17`, `postgresql17-contrib`, `su-exec` via apk) | Ships in Alpine 3.23 main/community repo; mature stable major; uses POSIX `/bin/sh` + `su-exec` for clean privilege drop. |
| Message Broker | RabbitMQ (`rabbitmq-server` via apk, native declarative env config) | Native AMQP 5672; configured via `RABBITMQ_DEFAULT_USER/_PASS`; durable queue declared idempotently by apps. |
| Services / images / containers (names shared) | `inventory-database`, `billing-database`, `inventory-app`, `billing-app`, `rabbit-queue`, `api-gateway-app` | Matches audit `docker ps` & `docker images` listing. (`RabbitMQ` in audit sample is lowercase `rabbit-queue` because OCI/Docker image names strictly forbid uppercase). |
| Named volumes | `inventory-database`, `billing-database`, `api-gateway-app` (exact bare names via top-level `name:` override) | Audit `docker volume ls` expects these literal un-prefixed names. |
| Exposed ports | ONLY `3000:3000` on `api-gateway-app`. All others: internal network only (5432 ×2, 8080 ×2, 5672 on rabbit) | Subject rule: "Any outside request must access only api-gateway-app via 3000." |
| Network | One bridge network `play-with-containers-network` connecting all 6 services | Managed entirely by `docker-compose`. |
| Restart policy | `restart: on-failure` on every service (inspects as `{on-failure 0}`) | Subject rule: "Containers must be restarted in case of failure." |
| Secrets management | `.env` at root only; `.env.example` committed; `.env` in `.gitignore`; no secrets in code or Dockerfiles | Strict audit requirement. |
| Runtime language | Python 3 from Alpine apk; `py3-psycopg2` from apk; pip installs only pure-Python wheels (Flask, waitress, SQLAlchemy, flask-sqlalchemy, pika, requests) | Avoids C compilation on musl; ensures fast, deterministic, reproducible builds. |
| POST `/api/movies` status | `200` (reference solution returns 201) | Audit literally tests for success code `200`. |
| App ports & execution | `inventory-app` (waitress :8080), `billing-app` (waitress-less resilient queue consumer + internal :8080 EXPOSE), `api-gateway-app` (waitress :3000) | Matches `docker ps` audit expectations (8080/tcp exposed internally on apps). |
| Container security | Non-root users (`appuser:1000` for apps, `postgres:postgres` for DBs, `rabbitmq:rabbitmq` for broker) | Adheres to Docker and Linux least-privilege security best practices. |

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
      /api/movies│ (with trailing slash support)                        ▲ consume
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
- Gateway answers `200 {"message": "<payload> sent"}` immediately upon publishing to RabbitMQ with `delivery_mode=2` (persistent message) into durable `billing_queue`.
- When `billing-app` is stopped (`docker stop billing-app`), RabbitMQ buffers all incoming messages on disk.
- When `billing-app` restarts, its consumer reconnects, drains all unacknowledged messages, writes rows to `billing-database`, and acknowledges (`basic_ack`).

---

## 4. Repository Layout

```
play-with-containers/
├── README.md                      # Full documentation: prerequisites, config table, setup, usage, audit Q&A guide
├── .env                           # Local environment secrets (GITIGNORED, copied from .env.example)
├── .env.example                   # Variable templates with safe default/dummy values
├── .gitignore                     # Ignores .env, __pycache__, *.pyc, venv/, *.log
├── .dockerignore                  # Ignores .git, .env, __pycache__, *.pyc, venv/, docs/
├── docker-compose.yml             # Single Compose file managing all 6 services, volumes, networks
├── Makefile                       # Convenience targets: up, down, build, logs, ps, clean, test
├── openapi.yaml                   # Bonus: OpenAPI 3.0 specification for API Gateway
├── postman/
│   └── play-with-containers.postman_collection.json # Bonus: Postman collection mirroring audit steps
├── scripts/
│   └── test_audit.sh              # Bonus automated end-to-end verification script
├── docs/
│   ├── requirements/              # Subject readme.md and audit.md
│   └── implementation-plan.md     # This comprehensive implementation plan
└── srcs/
    ├── api-gateway-app/
    │   ├── Dockerfile             # FROM alpine:3.23 (multi-layer cached, non-root)
    │   ├── requirements.txt
    │   ├── server.py              # Waitress runner, stdout + /var/log/api-gateway/gateway.log logging
    │   └── app/
    │       ├── __init__.py        # Flask factory, blueprints, strict_slashes=False
    │       ├── proxy.py           # Reverse proxy to inventory-app with trailing slash preservation
    │       └── queue_sender.py    # Pika publisher with connection management & retry
    ├── inventory-app/
    │   ├── Dockerfile             # FROM alpine:3.23 (py3-psycopg2, non-root)
    │   ├── requirements.txt
    │   ├── server.py              # Waitress runner on port 8080
    │   └── app/
    │       ├── __init__.py        # Flask app factory, SQLAlchemy init, DB retry on startup
    │       ├── extensions.py      # SQLAlchemy db instance
    │       ├── models.py          # Movie SQLAlchemy model
    │       └── movies.py          # /api/movies routes (GET, POST->200, PUT, DELETE)
    ├── billing-app/
    │   ├── Dockerfile             # FROM alpine:3.23 (py3-psycopg2, non-root)
    │   ├── requirements.txt
    │   ├── server.py              # Initializes schema, launches resilient consumer loop
    │   └── app/
    │       ├── extensions.py      # SQLAlchemy db instance
    │       ├── orders.py          # Order SQLAlchemy model
    │       └── consume_queue.py   # Resilient Pika consumer with reconnect & ACK logic
    ├── inventory-database/
    │   ├── Dockerfile             # FROM alpine:3.23 (postgresql17, su-exec)
    │   └── init-db.sh             # POSIX /bin/sh: initdb, listen_addresses='*', scram auth, exec postgres
    ├── billing-database/
    │   ├── Dockerfile             # FROM alpine:3.23 (postgresql17, su-exec)
    │   └── init-db.sh             # Reusable POSIX /bin/sh entrypoint for billing DB
    └── rabbit-queue/
        ├── Dockerfile             # FROM alpine:3.23 (rabbitmq-server, management plugin)
        └── entrypoint.sh          # POSIX /bin/sh: sets permissions, executes rabbitmq-server as PID 1
```

---

## 5. Detailed Implementation Steps

### Step 1: Project Scaffolding & Configuration
- Create `.gitignore` ignoring `.env`, `__pycache__`, `*.pyc`, `venv/`, `*.log`.
- Create `.dockerignore` for efficient context builds.
- Create `.env.example` with documented environment variable keys:
  - `INVENTORY_DB_USER`, `INVENTORY_DB_PASSWORD`, `INVENTORY_DB_NAME`, `INVENTORY_DB_HOST=inventory-database`, `INVENTORY_DB_PORT=5432`
  - `BILLING_DB_USER`, `BILLING_DB_PASSWORD`, `BILLING_DB_NAME`, `BILLING_DB_HOST=billing-database`, `BILLING_DB_PORT=5432`
  - `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `RABBITMQ_HOST=rabbit-queue`, `RABBITMQ_PORT=5672`, `RABBITMQ_QUEUE=billing_queue`
  - `INVENTORY_APP_HOST=inventory-app`, `INVENTORY_APP_PORT=8080`
  - `BILLING_APP_PORT=8080`
  - `APIGATEWAY_PORT=3000`
- Generate initial `.env` populated with local test values for testing.

### Step 2: Database Services (`inventory-database` & `billing-database`)
- **Dockerfile**:
  - `FROM alpine:3.23`
  - `RUN apk add --no-cache postgresql17 postgresql17-contrib su-exec`
  - `COPY init-db.sh /usr/local/bin/init-db.sh`
  - `RUN chmod +x /usr/local/bin/init-db.sh`
  - `EXPOSE 5432`
  - `ENTRYPOINT ["/usr/local/bin/init-db.sh"]`
- **`init-db.sh` (POSIX `/bin/sh`)**:
  1. Fix ownership of `$PGDATA` (`/var/lib/postgresql/data`) and `/run/postgresql` to `postgres:postgres`.
  2. If `$PGDATA/PG_VERSION` does not exist:
     - Run `su-exec postgres initdb -D "$PGDATA" --auth-local=trust --auth-host=scram-sha-256`.
     - Append `listen_addresses = '*'` to `$PGDATA/postgresql.conf`.
     - Append `host all all 0.0.0.0/0 scram-sha-256` to `$PGDATA/pg_hba.conf`.
     - Temporarily boot postgres on Unix socket via `su-exec postgres pg_ctl -D "$PGDATA" -o "-c listen_addresses=''" -w start`.
     - Execute idempotent SQL:
       ```sql
       CREATE USER "$DB_USER" WITH ENCRYPTED PASSWORD '$DB_PASSWORD';
       CREATE DATABASE "$DB_NAME" OWNER "$DB_USER";
       GRANT ALL PRIVILEGES ON DATABASE "$DB_NAME" TO "$DB_USER";
       ```
     - Stop temporary instance via `su-exec postgres pg_ctl -D "$PGDATA" -m fast -w stop`.
  3. Run `exec su-exec postgres postgres -D "$PGDATA"` so Postgres is PID 1 and receives signals cleanly.

### Step 3: RabbitMQ Service (`rabbit-queue`)
- **Dockerfile**:
  - `FROM alpine:3.23`
  - `RUN apk add --no-cache rabbitmq-server su-exec`
  - `RUN rabbitmq-plugins enable --offline rabbitmq_management`
  - `COPY entrypoint.sh /usr/local/bin/entrypoint.sh`
  - `RUN chmod +x /usr/local/bin/entrypoint.sh`
  - `EXPOSE 5672 15672`
  - `ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]`
- **`entrypoint.sh` (POSIX `/bin/sh`)**:
  - Ensure `/var/lib/rabbitmq` and `/var/log/rabbitmq` are owned by `rabbitmq:rabbitmq`.
  - Pass `RABBITMQ_DEFAULT_USER` and `RABBITMQ_DEFAULT_PASS` directly from environment to RabbitMQ runtime.
  - Execute `exec su-exec rabbitmq rabbitmq-server` as PID 1.
  - Queue declaration (`billing_queue`, `durable=True`) is performed by publisher and consumer upon connection, guaranteeing full idempotency without background race conditions.

### Step 4: Inventory Application (`inventory-app`)
- **Dockerfile**:
  - `FROM alpine:3.23`
  - `RUN apk add --no-cache python3 py3-pip py3-psycopg2`
  - `WORKDIR /usr/src/app`
  - `COPY requirements.txt .`
  - `RUN pip install --no-cache-dir -r requirements.txt --break-system-packages`
  - `COPY . .`
  - `RUN adduser -D -u 1000 appuser && chown -R appuser:appuser /usr/src/app`
  - `USER appuser`
  - `EXPOSE 8080`
  - `CMD ["python3", "server.py"]`
- **Endpoints & Behavior**:
  - Construct SQLAlchemy URI dynamically from `INVENTORY_DB_*` variables.
  - Implement startup DB connection retry (handles DB container initialization delay).
  - Blueprints configured with `strict_slashes=False`:
    - `POST /api/movies` & `POST /api/movies/`: Validates JSON `{"title": "...", "description": "..."}`, creates record, returns **HTTP 200** with movie JSON object.
    - `GET /api/movies` & `GET /api/movies/`: Returns JSON list of movies (with optional `?title=` search filter).
    - `GET /api/movies/<id>`, `PUT /api/movies/<id>`, `DELETE /api/movies/<id>`.
  - Served via Waitress WSGI server bound to `0.0.0.0:8080`.

### Step 5: Billing Application (`billing-app`)
- **Dockerfile**:
  - Identical secure Alpine base with `py3-psycopg2` and non-root execution.
  - `EXPOSE 8080` (matches audit `docker ps` display).
  - `CMD ["python3", "server.py"]`
- **Consumer & DB Logic**:
  - Construct SQLAlchemy URI from `BILLING_DB_*` environment variables.
  - Run database schema migration on startup (`db.create_all()` for `orders` table: `id`, `user_id`, `number_of_items`, `total_amount`).
  - Resilient consumer loop (`consume_queue.py`):
    - Connect to RabbitMQ using credentials with retry/backoff loop on connection failure.
    - Declare queue `billing_queue` with `durable=True`.
    - Set `basic_qos(prefetch_count=1)`.
    - On callback: parse JSON, insert record into `orders`, commit, and invoke `ch.basic_ack(delivery_tag=method.delivery_tag)`.
    - If DB error occurs, handle cleanly without losing messages.

### Step 6: API Gateway Application (`api-gateway-app`)
- **Dockerfile**:
  - `FROM alpine:3.23`
  - `RUN apk add --no-cache python3 py3-pip`
  - `WORKDIR /usr/src/app`
  - `COPY requirements.txt .`
  - `RUN pip install --no-cache-dir -r requirements.txt --break-system-packages`
  - `COPY . .`
  - Create log directory `/var/log/api-gateway`, ensure permissions for `appuser`.
  - `USER appuser`
  - `EXPOSE 3000`
  - `CMD ["python3", "server.py"]`
- **Routing & Proxy Logic**:
  - Configure Python `logging` with two outputs:
    1. Standard output (`StreamHandler(sys.stdout)`).
    2. File handler (`RotatingFileHandler('/var/log/api-gateway/gateway.log', maxBytes=5242880, backupCount=3)`).
  - Blueprint `/api/movies` (with `strict_slashes=False`):
    - Proxies all HTTP verbs (`GET`, `POST`, `PUT`, `DELETE`), query parameters, headers, and request body to `http://${INVENTORY_APP_HOST}:${INVENTORY_APP_PORT}/api/movies/`.
    - Returns exact upstream status code and JSON payload.
  - Blueprint `/api/billing` & `/api/billing/` (`POST`):
    - Validates incoming JSON (`user_id`, `number_of_items`, `total_amount`).
    - Connects to RabbitMQ, declares durable queue `billing_queue`, and publishes message with `pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent)`.
    - Returns `{"message": "<stringified payload> sent"}, 200`.
  - Bonus endpoint `/api/docs`: Serves OpenAPI 3.0 specification.
  - Served via Waitress on `0.0.0.0:3000`.

### Step 7: Complete Docker Compose Orchestration (`docker-compose.yml`)
- Managed exclusively by `docker-compose`.
- Define 6 services:
  1. `inventory-database`: `image: inventory-database`, `container_name: inventory-database`, `restart: on-failure`, volume mount `inventory-database:/var/lib/postgresql/data`, healthcheck `pg_isready -U $${INVENTORY_DB_USER} -d $${INVENTORY_DB_NAME}`.
  2. `billing-database`: `image: billing-database`, `container_name: billing-database`, `restart: on-failure`, volume mount `billing-database:/var/lib/postgresql/data`, healthcheck `pg_isready -U $${BILLING_DB_USER} -d $${BILLING_DB_NAME}`.
  3. `rabbit-queue`: `image: rabbit-queue`, `container_name: rabbit-queue`, `restart: on-failure`, healthcheck `rabbitmq-diagnostics -q ping`.
  4. `inventory-app`: `image: inventory-app`, `container_name: inventory-app`, `restart: on-failure`, `depends_on: inventory-database: condition: service_healthy`.
  5. `billing-app`: `image: billing-app`, `container_name: billing-app`, `restart: on-failure`, `depends_on: {billing-database: condition: service_healthy, rabbit-queue: condition: service_healthy}`.
  6. `api-gateway-app`: `image: api-gateway-app`, `container_name: api-gateway-app`, `restart: on-failure`, `ports: ["3000:3000"]`, volume mount `api-gateway-app:/var/log/api-gateway`, `depends_on: {inventory-app: condition: service_started, rabbit-queue: condition: service_healthy}`.
- Top-level named volumes with explicit name overrides:
  ```yaml
  volumes:
    inventory-database:
      name: inventory-database
    billing-database:
      name: billing-database
    api-gateway-app:
      name: api-gateway-app
  ```
- Top-level bridge network:
  ```yaml
  networks:
    play-with-containers-network:
      name: play-with-containers-network
      driver: bridge
  ```

### Step 8: Comprehensive README & Audit Study Guide
- Document prerequisites (Linux, Docker Engine 24+, Docker Compose v2).
- Complete environment configuration table with descriptions.
- Quickstart guide (`cp .env.example .env`, `docker-compose up --build`).
- Step-by-step curl & Postman testing walkthrough.
- Justification of key technical choices (Alpine 3.23 penultimate tag, lowercase `rabbit-queue` OCI compliance, HTTP 200 alignment).
- **Comprehensive Oral Exam Study Guide**:
  - Containers vs. Virtual Machines (OS kernel sharing vs. hypervisor hardware virtualization).
  - Docker architecture (Client, Daemon/Engine, containerd, runc, OCI specifications).
  - Dockerfile instructions (`FROM`, `RUN`, `COPY`, `WORKDIR`, `USER`, `EXPOSE`, `ENTRYPOINT`, `CMD`).
  - Docker Volumes (Anonymous, Named, Bind mounts; persistence lifecycle).
  - Docker Networks (Bridge, Host, Overlay, Macvlan; DNS service discovery).
  - Microservices architecture (Single responsibility, loose coupling, independent scalability vs. monoliths).
  - Message Queues & RabbitMQ (Asynchronous processing, buffering, decoupling, AMQP exchanges/queues/bindings, durability, acknowledgments).

### Step 9: Makefile & Automation Harness
- Standard targets: `up`, `down`, `build`, `logs`, `ps`, `restart`, `clean` (`down -v --remove-orphans`).
- Bonus automated test harness `test` invoking `scripts/test_audit.sh`.

### Step 10: Automated & Manual End-to-End Verification
- Run `make build` and verify clean caching without build warnings.
- Run `make up` and confirm all 6 containers start in correct dependency order.
- Verify `docker ps` outputs exact expected port bindings and container names.
- Verify `docker inspect -f "{{ .HostConfig.RestartPolicy }}" <name>` returns `{on-failure 0}` for all 6 containers.
- Verify `docker volume ls` lists `inventory-database`, `billing-database`, `api-gateway-app`.
- Verify host port isolation: `curl localhost:5432`, `curl localhost:8080`, `curl localhost:5672` are refused; `curl localhost:3000` responds.
- Run `scripts/test_audit.sh` to test:
  1. `POST /api/movies/` -> HTTP 200 and valid JSON.
  2. `GET /api/movies/` -> HTTP 200 with saved movie.
  3. `POST /api/billing/` -> HTTP 200.
  4. `docker stop billing-app` -> Container stops cleanly.
  5. `POST /api/billing/` -> HTTP 200 while worker is dead (RabbitMQ buffering test).
  6. `docker start billing-app` -> Worker starts and consumes buffered message into Postgres.
  7. Verify logs exist inside `api-gateway-app` volume.

### Step 11: Multi-Agent Review Pass
- **Correctness Review**: Verify syntax, security (no secrets committed, `.gitignore` active), and clean Docker layer rules.
- **Completeness Review**: Line-by-line audit checklist validation against `audit.md`.

---

## 6. Audit Checklist & Requirement Traceability Matrix

| Audit Requirement | Verification Method | Implemented In |
|---|---|---|
| Required files present | `README.md`, `docker-compose.yml`, `srcs/**`, `Makefile` | §4 Repository Layout |
| `.env` excluded from Git & no secrets in repo | `git status`, `.gitignore`, grep for sensitive values | Step 1, Step 10 |
| Comprehensive `README.md` with audit Q&A | Full study guide covering containers, VMs, Docker, microservices, queues | Step 8 |
| Infrastructure starts cleanly with `docker-compose up` | `docker-compose up --build -d` | Step 7, Step 10 |
| Dockerfile for every service based on Alpine/Debian | `FROM alpine:3.23` in all 6 services | Steps 2–6 |
| Restart policy `{on-failure 0}` on all containers | `docker inspect -f "{{ .HostConfig.RestartPolicy }}" <name>` | Step 7 |
| 3 named volumes matching exact audit names | `docker volume ls` | Step 7 |
| Port 3000 on gateway is the ONLY exposed port | `docker ps` + host curl port scan | Step 7, Step 10 |
| Docker image names match service names | `docker images` REPOSITORY column matches service names | Step 7 |
| POST `/api/movies/` returns 200 + created movie JSON | `curl -X POST .../api/movies/` | Step 4, Step 6 |
| GET `/api/movies/` returns 200 + movie list | `curl -X GET .../api/movies/` | Step 4, Step 6 |
| POST `/api/billing/` returns 200 | `curl -X POST .../api/billing/` | Step 5, Step 6 |
| POST `/api/billing/` returns 200 with `billing-app` stopped | `docker stop billing-app` then POST request | Step 5, Step 6, Step 10 |
| Queued messages processed upon `billing-app` restart | `docker start billing-app` then inspect `billing-database` | Step 5, Step 10 |
| Oral theoretical questions answered | Comprehensive README section | Step 8 |

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation Strategy |
|---|---|---|
| **Alpine Musl C-Extension Compilation** | Build failure or bloated images | Use `py3-psycopg2` from Alpine apk; use only pure-Python wheels via pip. |
| **Database Permission & PGDATA Initialization** | Postgres fails on container restart | Script checks `[ ! -s "$PGDATA/PG_VERSION" ]` before running `initdb`; sets ownership with `su-exec`. |
| **Trailing Slash Redirection (HTTP 308)** | Client POST requests fail on `/api/movies/` | Set `strict_slashes=False` on all Flask blueprints; configure proxy to preserve URI paths. |
| **RabbitMQ Audit Image Naming (`RabbitMQ` uppercase)** | Docker/OCI spec forbids uppercase image names | Name image `rabbit-queue` and document the OCI naming standard in README for auditors. |
| **Cold-Start Service Races** | App fails before DB/RabbitMQ is ready | Compose `depends_on: condition: service_healthy` + in-app retry loops. |
| **Log Directory Volume Permissions** | Gateway crashes writing log file | Create `/var/log/api-gateway` in Dockerfile with proper `appuser` ownership. |

---

## 8. Bonus Features Included

- Reusing and adapting the `crud-master-py` architecture for full custom solution ✔
- Robust Docker healthchecks with dependency-ordered startup ✔
- Gateway structured dual logging (stdout + named persistent volume) ✔
- Complete OpenAPI 3.0 specification (`openapi.yaml`) served at `/api/docs` ✔
- Postman Collection (`postman/play-with-containers.postman_collection.json`) ✔
- Automated E2E verification test suite (`scripts/test_audit.sh`) ✔
- Enhanced `Makefile` with diagnostic and test targets ✔

