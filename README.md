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
                                 [Vol: inventory-db]                      [Vol: billing-db]

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
- **Fail-Safe Startup & Healthchecks**: Database services utilize `pg_isready` health probes. Applications use two-tier dependency resolution (`service_healthy` towards databases, `service_started` towards queue) combined with in-application exponential retry loops to prevent Compose deadlocks during cold boots.
- **Asynchronous Queue Buffering**: When the `billing-app` is stopped or undergoing maintenance, the API Gateway continues accepting orders and returns HTTP `200`. RabbitMQ safely buffers messages in durable storage. As soon as `billing-app` restarts, all queued orders are consumed and inserted into PostgreSQL without data loss.
- **Persistent Storage & Data Hygiene**: Persistent data is stored in three named Docker volumes (`inventory-database`, `billing-database`, `api-gateway-app`). Database initialization scripts safely guard against re-running `initdb` on pre-existing data volumes.
- **Structured Dual-Stream Logging**: The API Gateway writes structured logs simultaneously to `stdout` (for `docker compose logs`) and to a persistent rotating log file at `/usr/src/logs/gateway.log` (mounted to volume `api-gateway-app`).
- **Standard Restart Policy**: All containers enforce `restart: on-failure` (inspects as `{on-failure 0}`), ensuring automated recovery from transient failures.

---

## 3. Prerequisites

- **Operating System**: Linux (Ubuntu 22.04+, Debian 12+, Alpine 3.19+, Arch, etc.)
- **Docker Engine**: Docker 24.0+ (or compatible container runtime)
- **Docker Compose**: Docker Compose v2 (e.g. `docker compose`) or v1 (`docker-compose`)
- **Make** & **curl** (for running the automated Makefile targets and audit tests)

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
| `BILLING_APP_PORT` | `8080` | Internal port for billing service |
| `GATEWAY_PORT` | `3000` | Host and container port for API Gateway |

> **Note on Credential Rotation**: PostgreSQL initializes roles upon first cluster creation. If you modify database credentials in `.env` after initialization, you must run `make clean` (which removes existing volumes) or perform an in-place `ALTER ROLE` query.

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
```

Alternatively, direct `docker compose` commands can be used:

```bash
# Start infrastructure
docker compose up --build -d

# Stop infrastructure
docker compose down

# Destroy infrastructure including volumes
docker compose down -v --remove-orphans
```

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
  "id": 1,
  "title": "A new movie",
  "description": "Very short description"
}
```

#### List All Movies (GET `/api/movies/`)
```bash
curl -i http://localhost:3000/api/movies/
```
**Expected Response**: `HTTP/1.1 200 OK`
```json
{
  "movies": [
    {
      "id": 1,
      "title": "A new movie",
      "description": "Very short description"
    }
  ]
}
```

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

---

### 3. Billing API & Queue Resilience Demonstration

#### Submit Billing Order (Normal State)
```bash
curl -i -X POST http://localhost:3000/api/billing/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "20",
    "number_of_items": "99",
    "total_amount": "250"
  }'
```
**Expected Response**: `HTTP/1.1 200 OK`
```json
{
  "message": "{\"user_id\": \"20\", \"number_of_items\": \"99\", \"total_amount\": \"250\"} sent"
}
```

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
     -d '{
       "user_id": "22",
       "number_of_items": "10",
       "total_amount": "50"
     }'
   ```
   **Result**: The request returns `HTTP/1.1 200 OK` immediately because the API Gateway safely pushes the message into the durable RabbitMQ broker.

4. **Restart the `billing-app` container**:
   ```bash
   docker start billing-app
   ```

5. **Verify order processing**:
   The `billing-app` reconnects, drains the durable message from RabbitMQ, and records the order into `billing-database`.
   ```bash
   docker exec billing-database psql -U billing_user -d billing_db -c "SELECT * FROM orders;"
   ```

---

### 4. Interactive API Documentation (Bonus)

The API Gateway hosts an embedded Swagger UI documentation explorer:
- Visit `http://localhost:3000/api/docs` or `http://localhost:3000/docs` in your browser.
- Raw OpenAPI 3.0 specification available at `http://localhost:3000/openapi.yaml`.

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

---

## 8. CRUD-Master Lineage & Adaptation Crosswalk

This project adopts and improves upon the architecture from `crud-master-py`:

| Component / Feature | Reference Implementation (`crud-master-py`) | Our Solution (`play-with-containers`) | Improvement / Rationale |
|---|---|---|---|
| **Base Image** | `python:3.12-alpine` (Docker Hub) | Custom `alpine:3.23` + system packages | Eliminates pre-built application images per subject rules. |
| **Database Hosts** | Hardcoded `localhost:5432` / local SQLite | Dynamic environment variables (`${INVENTORY_DB_HOST}`, etc.) | Enables container-to-container service discovery across Docker bridge network. |
| **HTTP Status Code** | POST returned `201 Created` | POST returns `200 OK` | Conforms strictly to audit assertion criteria. |
| **Restart Policy** | None / Default (`no`) | `restart: on-failure` across all 6 services | Satisfies audit restart policy check `{on-failure 0}`. |
| **Healthchecks** | None | Container healthchecks on databases and broker | Prevents startup race conditions and compose startup failures. |
| **Queue Type Coercion** | Implicit string handling | Explicit coercion (`int(number_of_items)`, `float(total_amount)`, `str(user_id)`) | Prevents poison message spin and worker crashes on string inputs. |

---

## 9. Appendix: Theoretical & Oral Exam Study Guide

This section contains thorough answers to all conceptual and architectural questions listed in the audit guide:

### Q1: What are containers and what are their advantages?
> **Answer**: A container is a lightweight, standalone, executable software package that bundles application code together with all of its libraries, system tools, and runtime dependencies.
> 
> **Advantages**:
> - **Portability**: Runs consistently across development, staging, and production environments ("build once, run anywhere").
> - **Lightweight & High Efficiency**: Shares the host OS kernel rather than virtualizing hardware, resulting in seconds-fast startup times and minimal CPU/RAM overhead.
> - **Isolation**: Uses Linux namespaces (PID, NET, MNT, IPC, UTS, USER) and Control Groups (cgroups) to isolate process execution and constrain resource usage.
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
> **Answer**: Docker is an open-source platform-as-a-service (PaaS) framework that automates the building, packaging, shipping, and running of applications within lightweight containers. It consists of the Docker Engine daemon (`dockerd`), Docker CLI client, Docker images, and Docker Compose orchestration tools.

---

### Q4: What is a microservices architecture and why do we use it?
> **Answer**: A microservices architecture is a software design pattern where a complex application is structured as a collection of small, loosely coupled, independently deployable services. Each service handles a distinct business domain (e.g., Catalogue/Inventory, Billing/Orders, API Gateway), owns its private database, and communicates via well-defined protocols (HTTP REST, AMQP).
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

