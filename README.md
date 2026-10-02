# Play with Containers

A high-performance, fault-tolerant 6-service microservices infrastructure built with Docker and managed exclusively by Docker Compose. This project adheres strictly to all requirements from the `play-with-containers` subject and audit specification, featuring custom Alpine-based Docker images, named persistent volumes, isolated bridge networking, internal service discovery, and resilient asynchronous queue processing via RabbitMQ.

---

## 1. Architecture Overview

```
                          Host Port 3000 (Only Published Port)
                                           │
                                 ┌─────────▼─────────┐
                  HTTP /api/*    │  api-gateway-app  │── Publish AMQP ──►  ┌──────────────┐
                 (Proxy Routing) │ (Flask + Waitress)│    (Port 5672)      │ rabbit-queue │
                                 └─────────┬─────────┘ ◄───────────────────│  (RabbitMQ)  │
                                           │                               └──────────────┘
                         /api/movies       │                                      ▲
                                           ▼                                      │ Consume
                                 ┌───────────────────┐                     ┌──────┴───────┐
                                 │   inventory-app   │                     │ billing-app  │
                                 │ (Flask + Waitress)│                     │ (Worker App) │
                                 └─────────┬─────────┘                     └──────┬───────┘
                                           │ Port 5432                            │ Port 5432
                                 ┌─────────▼─────────┐                    ┌───────▼─────────┐
                                 │ inventory-database│                    │ billing-database│
                                 │  (PostgreSQL 17)  │                    │  (PostgreSQL 17)│
                                 └───────────────────┘                    └─────────────────┘
                                 [Vol: inventory-database]                [Vol: billing-database]

   ─── Single Bridge Network: play-with-containers-network (All services internal except Gateway) ───
   ─── Gateway Log Volume: api-gateway-app mounted at /usr/src/logs ────────────────────────────────
```

### Microservices Summary

| Service Name | Base Image | Internal Port(s) | Published Host Port | Volume Mount | Purpose |
|---|---|---|---|---|---|
| `api-gateway-app` | `alpine:3.23` | 3000 | **3000:3000** | `api-gateway-app:/usr/src/logs` | Central reverse proxy, billing message producer, OpenAPI docs |
| `inventory-app` | `alpine:3.23` | 8080 | *None* | *None* | REST API for movie catalogue CRUD |
| `billing-app` | `alpine:3.23` | 8080 | *None* | *None* | Asynchronous consumer worker storing orders into database |
| `rabbit-queue` | `alpine:3.23` | 5672, 15672 | *None* | *None* | Message broker buffering durable billing queues |
| `inventory-database` | `alpine:3.23` | 5432 | *None* | `inventory-database:/var/lib/postgresql/data` | Relational storage for inventory catalogue |
| `billing-database` | `alpine:3.23` | 5432 | *None* | `billing-database:/var/lib/postgresql/data` | Relational storage for billing orders |

---

## 2. Key Features & Architectural Decisions

- **Alpine 3.23 Penultimate Release**: All 6 Docker images are built from `alpine:3.23`, the penultimate stable release of Alpine Linux (ensuring deterministic musl libc builds, small image footprints, and zero dependence on forbidden Docker Hub pre-built application images).
- **Strict Network Isolation**: Only the API Gateway publishes port `3000` to the host. Databases (5432), message broker (5672), and internal apps (8080) are strictly unexposed to the host and communicate exclusively over the internal `play-with-containers-network` bridge network.
- **Fail-Safe Startup & Healthchecks**: Database services utilize `pg_isready` health probes. Every application and the gateway depend on `service_healthy`, not `service_started`, so no container is reachable before the services behind it can actually answer. Combined with bounded retry loops in each application (30 attempts × 2 s for PostgreSQL, 5 attempts for RabbitMQ publishes) this removes the cold-boot race entirely: the first request after `docker compose up` returns `200`, not `502`.
- **Asynchronous Queue Buffering**: When the `billing-app` is stopped or undergoing maintenance, the API Gateway continues accepting orders and returns HTTP `200`. RabbitMQ safely buffers messages in durable storage, and the gateway uses publisher confirms so a `200` means the broker actually accepted and persisted the message. As soon as `billing-app` restarts, buffered orders are consumed and inserted into PostgreSQL. An order the consumer could not persist is `nack`ed and requeued rather than acknowledged, so a failed insert is never silently dropped.
- **Persistent Storage & Data Hygiene**: Persistent data is stored in three named Docker volumes (`inventory-database`, `billing-database`, `api-gateway-app`). The database entrypoints run `initdb` only when the data directory is empty, and reconcile the configured role and database credentials on every boot, so rotating a password in `.env` takes effect on the next `docker compose up`.
- **Structured Dual-Stream Logging**: The API Gateway writes structured logs simultaneously to the console stream (stderr, captured by `docker compose logs` alongside stdout) and to a persistent rotating log file at `/usr/src/logs/gateway.log` (mounted to volume `api-gateway-app`).
- **Standard Restart Policy**: All containers enforce `restart: on-failure` (inspects as `{on-failure 0}`), ensuring automated recovery from transient failures. An explicit `docker stop` still exits `0` and is respected, because only a non-zero exit triggers the policy.
- **Graceful Shutdown**: Every service handles `SIGTERM` and exits `0` on `docker stop` rather than being `SIGKILL`ed after the grace period. `billing-app` drains its AMQP channel so an unacknowledged message is requeued, and the database images ship `STOPSIGNAL SIGINT` because PostgreSQL maps `SIGTERM` to a *smart* shutdown that waits for clients to disconnect.
- **Least Privilege & Secret Hygiene**: The three Python services run as a non-root `app` user; only the database and broker images start as root, and they immediately drop to `postgres`/`rabbitmq` via `su-exec`. No secret is baked into any image layer, none is passed as a command-line argument (`psql` and `rabbitmqctl` receive it via a `0600` file and stdin respectively), and the application raises rather than falling back to a hardcoded default if a secret is missing.

---

## 3. Prerequisites

- **Operating System**: Linux (Ubuntu 22.04+, Debian 12+, Alpine 3.19+, Arch, etc.)
- **Docker Engine**: Docker 24.0+ (or compatible container runtime)
- **Docker Compose**: Docker Compose **v2.17.0+** (`docker compose`). `make up` and `make rebuild` run `docker compose up --build -d --wait --wait-timeout 240`; `--wait` reports container health rather than mere startup, but `--wait-timeout` on `up` only exists from v2.17.0, so older Compose answers `unknown flag: --wait-timeout`. `make up` only checks that `docker compose` is on `PATH` — it does not compare version numbers, so run `docker compose version` yourself. Verified on Docker Compose v5.5.1 / Docker Engine v29.8.1.
- **Make**, **bash**, **curl**, **grep** & **sed** (for the Makefile targets and `make test`, which runs `scripts/test_audit.sh`)
- **Python 3** (host-side only, for `make test-py`; the stack itself needs nothing installed on the host)
- Run every command from the repository root: Compose and the scripts resolve `docker-compose.yml`, `scripts/` and `.env` relative to the current directory.

---

## 4. Configuration (.env)

Configuration parameters and credentials reside entirely in `.env`. Secrets are never committed to version control (`.env` is excluded in `.gitignore`).

### Setting Up Environment Variables

```bash
cp .env.example .env
```

### Environment Variable Reference

| Variable | Default Value | Description |
|---|---|---|
| `INVENTORY_DB_HOST` | `inventory-database` | Hostname of inventory PostgreSQL container |
| `INVENTORY_DB_PORT` | `5432` | Port for inventory PostgreSQL service |
| `INVENTORY_DB_USER` | `inventory_user` | Database user for inventory |
| `INVENTORY_DB_PASSWORD` | `inventory_secret_pass` | Database password for inventory user |
| `INVENTORY_DB_NAME` | `inventory_db` | Database name for inventory catalogue |
| `BILLING_DB_HOST` | `billing-database` | Hostname of billing PostgreSQL container |
| `BILLING_DB_PORT` | `5432` | Port for billing PostgreSQL service |
| `BILLING_DB_USER` | `billing_user` | Database user for billing |
| `BILLING_DB_PASSWORD` | `billing_secret_pass` | Database password for billing user |
| `BILLING_DB_NAME` | `billing_db` | Database name for billing orders |
| `RABBITMQ_HOST` | `rabbit-queue` | Hostname of RabbitMQ message broker |
| `RABBITMQ_PORT` | `5672` | AMQP protocol port for RabbitMQ |
| `RABBITMQ_USER` | `rabbit_user` | RabbitMQ administrative user |
| `RABBITMQ_PASSWORD` | `rabbit_secret_pass` | RabbitMQ user password |
| `RABBITMQ_QUEUE` | `billing_queue` | Target queue name for order processing |
| `INVENTORY_APP_HOST` | `inventory-app` | Internal hostname for inventory service |
| `INVENTORY_APP_PORT` | `8080` | Internal port for inventory service |
| `GATEWAY_HOST` | `127.0.0.1` | Host the test scripts target. Not read by `docker-compose.yml`. |
| `GATEWAY_PORT` | `3000` | Port the test scripts target on the gateway |

> **There is deliberately no `BILLING_APP_*` variable.** The gateway never
> contacts `billing-app`; it only publishes to RabbitMQ. A `BILLING_APP_HOST` key
> would misleadingly suggest otherwise.

> **Note on credential rotation**: the database entrypoints reconcile the
> configured role and password on **every** boot, and the broker entrypoint
> re-applies its credentials if the user already exists. Changing a credential in
> `.env` and running `make up` is therefore sufficient — you do not need to
> destroy the volumes. Run `make clean` only if you also want to discard the
> stored data.

> **Note on placeholder values**: the `*_secret_pass` values above are
> non-functional placeholders from `.env.example`. They exist so the variable
> names can be documented; replace them with your own values before deploying
> anything.

---

## 5. Usage & Management

A comprehensive `Makefile` is provided to simplify container lifecycle management:

```bash
# View available Makefile targets
make help

# Build and start all 6 services in detached mode
make up

# Check container status
make ps

# Follow container logs across all microservices
make logs

# Restart all services
make restart

# Stop all containers and network (preserves volumes)
make down

# Complete teardown (removes containers, networks, AND named volumes)
make clean

# Clean rebuild of all images from scratch
make rebuild

# Run full automated audit test suite
make test

# Run automated Python test suite
make test-py
```

Alternatively, direct `docker compose` commands can be used:

```bash
# Start infrastructure
docker compose up --build -d

# Start and block until every container reports healthy (recommended)
docker compose up --build -d --wait --wait-timeout 240

# Stop infrastructure
docker compose down

# Destroy infrastructure including volumes
docker compose down -v --remove-orphans
```

A cold boot needs roughly 45 seconds: PostgreSQL runs `initdb` (~20 s) and
RabbitMQ completes `await_startup` plus user provisioning (~35-45 s). Compose
starts the databases and the broker first, waits for their healthchecks, then
starts the applications, and starts the gateway last — so by the time port 3000
accepts a connection, everything behind it can already answer.

---

## 5.1 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Ports are not available: exposing port TCP 0.0.0.0:3000: bind: address already in use` | Something else on the host holds port 3000 | Find it with `ss -tlnp \| grep 3000`, or change the published side only: `ports: ["3000:3000"]` → `["3001:3000"]` in `docker-compose.yml` |
| `unknown flag: --wait` or `unknown flag: --wait-timeout` | Docker Compose older than v2.17.0 (`--wait-timeout` on `up` landed in v2.17.0) | Upgrade Compose, or run `docker compose up --build -d` and re-run `docker compose ps` until every service reports `healthy` |
| `make up` times out waiting for a service | Slow host; the broker is the last to become healthy | Raise `--wait-timeout` (currently 240 s) in the `Makefile`, or check `docker compose logs rabbit-queue` |
| An app container is restarting with `password authentication failed` | Credentials changed in `.env` but the database container has not restarted | `docker compose up -d --force-recreate inventory-database billing-database`. The entrypoints reconcile roles on every boot, so the container must actually restart |
| An app container is restarting and the log says `ValueError: invalid literal for int()` | A non-numeric value in a `*_PORT` variable in `.env` | Correct the value; the port falls back to its default and logs a warning for a malformed value, but a non-numeric value is a configuration error worth fixing |
| A port such as `8080` answers on the host | An unrelated host process listens there, not a container | Check with `docker port inventory-app` — if that is empty, nothing is published. Verify isolation with `docker port`, not by curling the port |
| `make test` reports a port-isolation failure | A previous run left `billing-app` stopped | The suite restarts it on exit; if needed run `docker compose up -d billing-app` |
| Swagger UI at `/docs` renders blank | The UI assets load from a CDN | Needs internet access. The raw specification at `http://localhost:3000/openapi.yaml` always works |
| Movies or orders accumulate between test runs | `make test` cleans up after itself, but manual `curl` calls do not | `curl -X DELETE "http://localhost:3000/api/movies?confirm=all"` and `docker compose down -v` to reset |
| Gateway returns `502` for `/api/movies/` | `inventory-app` is not answering yet, or is down | `docker compose ps` and `docker compose logs inventory-app`. The gateway retries a bounded number of times; a persistent `502` means the upstream is genuinely down |

---

## 6. API Walkthrough & Verification

All API interactions must be performed through the API Gateway at `http://localhost:3000`.

### 1. Healthcheck

```bash
curl -i http://localhost:3000/health
```
**Expected Response**: `HTTP/1.1 200 OK`
```json
{
  "status": "healthy"
}
```

---

### 2. Movies Inventory API

#### Add a Movie (POST `/api/movies/`)
```bash
curl -i -X POST http://localhost:3000/api/movies/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "A new movie",
    "description": "Very short description"
  }'
```
**Expected Response**: `HTTP/1.1 200 OK`
```json
{
  "description": "Very short description",
  "id": <id>,
  "title": "A new movie"
}
```

> Flask serialises JSON with alphabetically sorted keys, so the real body is
> `{"description": "Very short description", "id": 1, "title": "A new movie"}`.
> `id` is whatever the sequence returns next; on a freshly initialised volume
> the first movie is `1`.

#### List All Movies (GET `/api/movies/`)
```bash
curl -i http://localhost:3000/api/movies/
```
**Expected Response**: `HTTP/1.1 200 OK`
```json
{
  "movies": [
    {
      "description": "Very short description",
      "id": <id>,
      "title": "A new movie"
    }
  ]
}
```

> Flask serialises JSON with alphabetically sorted keys, so the real body is
> `{"description": "Very short description", "id": 1, "title": "A new movie"}`.
> `id` is whatever the sequence returns next; on a freshly initialised volume
> the first movie is `1`.

#### Filter Movies by Title (GET `/api/movies?title=new`)
```bash
curl -i "http://localhost:3000/api/movies?title=new"
```

#### Get Movie by ID (GET `/api/movies/1`)
```bash
curl -i http://localhost:3000/api/movies/1
```

#### Update Movie (PUT `/api/movies/1`)
```bash
curl -i -X PUT http://localhost:3000/api/movies/1 \
  -H "Content-Type: application/json" \
  -d '{
    "title": "An updated movie title",
    "description": "Updated description"
  }'
```

#### Delete Movie by ID (DELETE `/api/movies/1`)
```bash
curl -i -X DELETE http://localhost:3000/api/movies/1
```

#### Delete the Whole Catalogue (DELETE `/api/movies?confirm=all`)

Clearing the catalogue is destructive and reachable unauthenticated through the
public gateway, so it is refused unless the caller opts in explicitly:

```bash
curl -i -X DELETE "http://localhost:3000/api/movies?confirm=all"
```

Without `?confirm=all` the gateway returns `400` and nothing is deleted.

> Both `/api/movies` and `/api/movies/` are accepted; the trailing slash is not
> significant.

---

### 3. Billing API & Queue Resilience Demonstration

#### Submit Billing Order (Normal State)
```bash
curl -i -X POST http://localhost:3000/api/billing/ \
  -H "Content-Type: application/json" \
  -d '{"user_id": "20", "number_of_items": "99", "total_amount": "250"}'
```
**Expected Response**: `HTTP/1.1 200 OK`
```json
{
  "message": "{\"user_id\": \"20\", \"number_of_items\": \"99\", \"total_amount\": \"250\"} sent"
}
```

> The gateway echoes the request body verbatim, so keep the payload on one line
> for the response above to match. A pretty-printed body comes back as
> `"{\n    \"user_id\": \"20\",\n ... } sent"`.

#### Test Outage Resilience (Audit Requirement)
1. **Stop the `billing-app` container**:
   ```bash
   docker stop billing-app
   ```

2. **Verify `billing-app` is stopped**:
   ```bash
   docker ps -a --filter name=billing-app
   ```

3. **Submit another order while `billing-app` is down**:
   ```bash
   curl -i -X POST http://localhost:3000/api/billing/ \
     -H "Content-Type: application/json" \
     -d '{"user_id": "22", "number_of_items": "10", "total_amount": "50"}'
   ```
   **Result**: The request returns `HTTP/1.1 200 OK` immediately because the API Gateway safely pushes the message into the durable RabbitMQ broker.

4. **Restart the `billing-app` container**:
   ```bash
   docker start billing-app
   ```

5. **Verify order processing**:
   The `billing-app` reconnects, drains the durable message from RabbitMQ, and records the order into `billing-database`.
   ```bash
   docker exec billing-database psql -U billing_user -d billing_db -c \
     "SELECT id, user_id, number_of_items, total_amount FROM orders WHERE user_id = '22';"
   ```

   Expected: the order submitted while the worker was down appears in the table.
   ```console
    id | user_id | number_of_items | total_amount
   ----+---------+-----------------+--------------
     2 | 22      |              10 |           50.00
   (1 row)
   ```

   > The order submitted while the worker was down is row 2 — the order from
   > "Normal State" above is row 1. Note that `orders` also has a `created_at`
   > column, so `SELECT *` prints five columns.

6. **Watch it happen** (optional but convincing):
   ```bash
   docker logs billing-app --since 60s | grep -E "Connected to RabbitMQ|Successfully processed"
   ```
   ```console
   2026-10-02 17:05:37,452 [INFO] [billing-app] Connected to RabbitMQ. Waiting for billing messages on 'billing_queue'...
   2026-10-02 17:05:37,466 [INFO] [billing-app] Successfully processed and recorded order #2 for user '22' (items=10, total=$50.00)
   ```

   > Every line is prefixed with a timestamp (`%(asctime)s`, set in
   > `srcs/billing-app/app/__init__.py:11`), and the grep also returns pika's own
   > `AMQPConnectionWorkflow` lines. Order `#2` is what a fresh database returns.

> `docker stop billing-app` exits `0`, not `137`: the service handles `SIGTERM`
> and drains its AMQP channel, so an unacknowledged message is requeued rather
> than lost.

---

### 4. Interactive API Documentation (Bonus)

The API Gateway hosts an embedded Swagger UI documentation explorer:
- Visit `http://localhost:3000/api/docs` or `http://localhost:3000/docs` in your browser.
- Raw OpenAPI 3.0 specification available at `http://localhost:3000/openapi.yaml`.

> The Swagger UI assets are loaded from a CDN, so the rendered page needs
> internet access. The raw specification at `/openapi.yaml` is served from the
> container and always works offline.

---

## 7. Architectural Decision Records (ADR)

| Decision | Selection | Rationale | Subject/Audit Justification |
|---|---|---|---|
| **Base Image** | `alpine:3.23` | Penultimate stable version of Alpine Linux (Alpine 3.24 is current stable). Guarantees reproducible, lightweight musl packages. | Subject §Instructions: *"containers should be created from the penultimate stable version of either Alpine or Debian"*. |
| **SQL Engine** | PostgreSQL 17 | Stable relational DBMS available in Alpine 3.23 official repositories. | Subject §Docker Containers: *"SQL database server that contains your inventory/billing database"*. |
| **Container & Image Naming** | `inventory-database`, `billing-database`, `inventory-app`, `billing-app`, `rabbit-queue`, `api-gateway-app` | OCI repository names require lowercase characters. Service name, image name, and container name are set identically. | Audit §Docker Containers: Container name matching. Subject §Instructions: *"service and Docker image must share the same name"*. |
| **Volume Names** | `inventory-database`, `billing-database`, `api-gateway-app` | Docker Compose `name:` volume overrides generate exact bare names without project prefix. | Audit §Check the Docker volumes: `docker volume ls` expects literal names. |
| **POST Status Code** | `200 OK` | Handlers return HTTP 200 upon successful creation and queue enqueueing. | Audit §Inventory & §Billing: *"Can you confirm the response was the success code 200?"* |
| **Restart Policy** | `restart: on-failure` | Inspects verbatim as `{on-failure 0}` on all 6 containers. | Audit §Check Container restart policy: `docker inspect -f "{{ .HostConfig.RestartPolicy }}"` == `{on-failure 0}`. |
| **Port Exposure** | Only `3000:3000` published on host | All internal ports (5432, 8080, 5672) use `expose:` and remain unreachable from host network. | Subject §Docker Network & Audit §Check the solution network. |
| **Startup Gating** | `depends_on` with `condition: service_healthy` everywhere | `service_started` would let the gateway accept requests while `inventory-app` was still connecting to PostgreSQL, producing a `502` on the first cold-boot request. | Subject §Docker Containers: *"Containers must be restarted in case of failure"*; correctness under cold boot. |
| **Graceful Shutdown** | `SIGTERM` handlers; `STOPSIGNAL SIGINT` on the database images | `docker stop` exits `0` instead of `137`. PostgreSQL maps `SIGTERM` to a *smart* shutdown that waits for clients, and our pooled connections would hang it until the grace period expired. | Keeps an unacknowledged queue message requeued rather than lost. |
| **Message Acknowledgement** | `basic_nack(requeue=True)` when an insert fails after retries | Acknowledging a failed insert would silently discard a customer order. | Subject §Docker Containers: billing app *"consuming the messages from the RabbitMQ queue"*. |
| **Non-root Services** | `USER app` in the three Python images | Least privilege. The database and broker images must start as root to drop privileges with `su-exec`; the serving process is `postgres`/`rabbitmq`. | Security hardening beyond the brief. |
| **Secret Handling** | Secrets from `.env` only; no secret in any image layer or `argv` | `psql` reads the password from a `0600` file, `rabbitmqctl` from stdin, and application code raises rather than defaulting. | Subject: *"the credentials and passwords must be in the `.env` file"*. |

---

## 8. CRUD-Master Lineage & Adaptation Crosswalk

This project adopts and improves upon the architecture from `crud-master-py`:

| Component / Feature | Reference Implementation (`crud-master-py`) | Our Solution (`play-with-containers`) | Improvement / Rationale |
|---|---|---|---|
| **Base Image** | `python:3.12-alpine` (Docker Hub) | Custom `alpine:3.23` + system packages | Eliminates pre-built application images per subject rules. |
| **Database Hosts** | Hardcoded `localhost:5432` / local SQLite | Dynamic environment variables (`${INVENTORY_DB_HOST}`, etc.) | Enables container-to-container service discovery across Docker bridge network. |
| **HTTP Status Code** | POST returned `201 Created` | POST returns `200 OK` | Conforms strictly to audit assertion criteria. |
| **Restart Policy** | None / Default (`no`) | `restart: on-failure` across all 6 services | Satisfies audit restart policy check `{on-failure 0}`. |
| **Healthchecks** | None | Healthchecks on all six *services* — image-level `HEALTHCHECK` on the four app/broker images, Compose-level `healthcheck:` on the two database images, which need the runtime `${DB_USER}`/`${DB_NAME}` — plus health-gated `depends_on` | Prevents startup race conditions; the first request after a cold boot returns `200`. |
| **Queue Type Coercion** | Implicit string handling | Explicit, validated coercion in a dependency-free module (`app/validation.py`) | Prevents poison-message spin; the rules are now unit-testable on the host. |
| **WSGI Server** | Flask development server (`app.run()`) | Waitress | Multi-threaded and production-oriented; the development server is single-threaded and not intended for this. |
| **Database Binding** | `localhost:5432` hardcoded | Docker-DNS service names from environment variables | Service discovery across the bridge network; recreating a container needs no config change. |

---

## 9. Appendix: Theoretical Study Guide

This section contains thorough answers to all conceptual and architectural questions listed in the audit guide:

### Q1: What are containers and what are their advantages?
> **Answer**: A container is a lightweight, standalone, executable software package that bundles application code together with all of its libraries, system tools, and runtime dependencies.
> 
> **Advantages**:
> - **Portability**: Runs consistently across development, staging, and production environments ("build once, run anywhere").
> - **Lightweight & High Efficiency**: Shares the host OS kernel rather than virtualizing hardware, resulting in millisecond startup instead of the minutes a VM boot takes, and minimal CPU/RAM overhead.
> - **Isolation**: Uses Linux namespaces (PID, NET, MNT, IPC, UTS) and Control Groups (cgroups) to isolate process execution and constrain resource usage. A **user** namespace is available but not enabled by default on a stock Docker daemon, which is why the three Python images still drop to a non-root `USER`.
> - **Immutability & Reproducibility**: Container images are versioned and immutable, eliminating environment drift.

---

### Q2: What is the difference between containers and virtual machines (VMs)?
> **Answer**:
> - **Virtual Machines (Hardware-level Virtualization)**:
>   - Each VM packages a complete Guest Operating System (GBs in size) running on top of a Hypervisor (e.g., KVM, VMware, Hyper-V).
>   - Higher resource overhead, longer boot times (minutes), and redundant kernel duplication.
> - **Containers (OS-level Virtualization)**:
>   - Containers share the host system's Linux kernel and only package user-space application binaries and dependencies (MBs in size).
>   - No hypervisor or guest OS overhead, near-instantaneous startup, and native bare-metal execution performance.

---

### Q3: What is Docker and what is it used for?
> **Answer**: Docker is an open-source container platform: the Engine (client, daemon, `containerd`, `runc`), a build system for images, a local image store and a registry client. The subject brief describes it as a set of "platform as a service" products; more precisely it is a container runtime and packaging tool — a true PaaS would also own the runtime environment, scaling and routing for you.

---

### Q4: What is a microservices architecture and why do we use it?
> **Answer**: A microservices architecture is a software design pattern where a complex application is structured as a collection of small, loosely coupled, independently deployable services. Each service handles a distinct business domain (Catalogue/Inventory, Billing/Orders, API Gateway) and communicates via well-defined protocols (HTTP REST, AMQP). In this stack the two domain services each own their own database — `inventory-app` owns `inventory-database` and `billing-app` owns `billing-database`, two completely separate PostgreSQL clusters that cannot see each other — while `api-gateway-app` is a stateless edge service that owns no database and exists to be the single public entry point.
>
> **Why we use it**:
> - **Independent Scalability**: High-traffic services can be scaled horizontally without scaling the entire application.
> - **Fault Isolation**: A crash in one service (e.g. `billing-app`) does not take down unrelated services (e.g. `inventory-app`).
> - **Polyglot & Modular Technology**: Services can leverage different tech stacks suited for their specific domain.
> - **Continuous Delivery**: Smaller codebases enable rapid, low-risk deployments by distributed teams.

---

### Q5: What is a queue and what is it used for?
> **Answer**: A queue is a First-In-First-Out (FIFO) data structure used in message-oriented middleware for asynchronous inter-process communication.
>
> **What it is used for**:
> - **Temporal Decoupling**: Producers and consumers do not need to execute at the same time. Producers can publish messages even if consumers are temporarily offline.
> - **Load Leveling (Buffering / Throttling)**: Absorbs bursts of traffic and prevents backend databases or worker nodes from being overwhelmed.
> - **Reliability & Delivery Guarantees**: Persists messages to durable storage until acknowledged (`ack`) by a worker.

---

### Q6: What is RabbitMQ?
> **Answer**: RabbitMQ is an enterprise open-source message broker that implements the Advanced Message Queuing Protocol (AMQP 0-9-1). It acts as an intermediary that accepts messages from producers, routes them through exchanges using binding keys, buffers them in queues, and delivers them to consumers with delivery acknowledgments, quality-of-service (prefetch limits), and clustering capabilities.

---

### Q7: What is a Dockerfile and what do its instructions do?
> **Answer**: A Dockerfile is a text file containing ordered instructions used by the Docker Engine to build a container image layer by layer.
>
> **Key Instructions**:
> - `FROM`: Defines the parent base image (e.g. `FROM alpine:3.23`).
> - `WORKDIR`: Sets the current working directory inside the container for subsequent instructions.
> - `RUN`: Executes shell commands during image build time to install packages and configure dependencies (each creates a new image layer).
> - `COPY`: Copies files or directories from the build context on the host machine into the container filesystem.
> - `ENV`: Sets persistent environment variables accessible during build and runtime.
> - `EXPOSE`: Documents the network ports on which the container listens at runtime (metadata documentation for internal networking).
> - `HEALTHCHECK`: Specifies a command test to verify container operational health.
> - `ENTRYPOINT`: Configures the default executable to run when the container starts.
> - `CMD`: Provides default arguments or fallback command for the `ENTRYPOINT`.

---

### Q8: What is a Docker volume and why do we use it?
> **Answer**: A Docker volume is a storage directory managed by the Docker daemon located outside the Union File System (typically under `/var/lib/docker/volumes/`).
>
> **Why we use it**:
> - **Data Persistence**: Container root filesystems are ephemeral (destroyed when a container is removed). Volumes preserve persistent database files and application logs across container recreations.
> - **Performance**: Volumes bypass the copy-on-write storage driver, providing native host filesystem I/O performance.
> - **Sharing & Backups**: Can be mounted across multiple containers or easily backed up and migrated.

---

### Q9: What is a Docker network and why do we use it?
> **Answer**: A Docker network is a software-defined virtual network that enables isolated communication between containers on the same host or across hosts.
>
> **Why we use it**:
> - **Service Discovery via Automatic DNS**: Containers on the same user-defined bridge network can resolve each other using their service/container names (e.g. `http://inventory-app:8080` or `inventory-database:5432`) without hardcoding dynamic IP addresses.
> - **Security & Perimeter Isolation**: Containers on a private bridge network cannot be reached from outside the Docker host unless explicitly published via `ports:`.

---

### Q10: What is a Docker image and why do we use it?
> **Answer**: A Docker image is an immutable, read-only template consisting of stacked layers that defines the environment, filesystem, libraries, and binaries required to run an application.
>
> **Why we use it**:
> - It represents the blueprint from which multiple identical running container instances are instantiated.
> - It ensures complete reproducibility across development, testing, CI/CD, and production.

---