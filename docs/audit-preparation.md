# Audit Preparation Guide — play-with-containers

> **Purpose**: Complete preparation for the live audit. It covers **every question in
> `docs/requirements/audit.md`** with the correct answer for *this* implementation, the exact
> commands the auditor will run with expected outputs, and additional questions an auditor
> may reasonably ask beyond the checklist.
>
> For generalized theory with examples (studied independently of this repo), see
> [`docs/theory-study-guide.md`](./theory-study-guide.md).

---

## Table of Contents

1. [Pre-Audit Checklist (before the auditor arrives)](#1-pre-audit-checklist)
2. [Section: General — Repo Content](#2-section-general--repo-content)
3. [Section: General — Theory Questions](#3-section-general--theory-questions)
4. [Section: README Review](#4-section-readme-review)
5. [Section: Infrastructure Check](#5-section-infrastructure-check)
6. [Section: Run the Infrastructure](#6-section-run-the-infrastructure)
7. [Section: Microservices & Queue Theory Questions](#7-section-microservices--queue-theory-questions)
8. [Section: Dockerfiles](#8-section-dockerfiles)
9. [Section: Containers](#9-section-containers)
10. [Section: Restart Policy](#10-section-restart-policy)
11. [Section: Docker Volumes](#11-section-docker-volumes)
12. [Section: Solution Network](#12-section-solution-network)
13. [Section: Docker Images](#13-section-docker-images)
14. [Section: Inventory API Endpoints](#14-section-inventory-api-endpoints)
15. [Section: Billing API Endpoints & Outage Resilience](#15-section-billing-api-endpoints--outage-resilience)
16. [Section: Bonus](#16-section-bonus)
17. [Anticipated Extra Auditor Questions](#17-anticipated-extra-auditor-questions)
18. [Command Cheat Sheet](#18-command-cheat-sheet)

---

## 1. Pre-Audit Checklist

Run through this **before** the audit starts:

- [ ] `git status` clean — nothing uncommitted, nothing sensitive staged.
- [ ] `.env` is **not** in git (`git ls-files | grep -c '^\.env$'` → `0`).
- [ ] `.env.example` present; `.gitignore` contains `.env`.
- [ ] Repo contains: `README.md`, `docker-compose.yml`, `Makefile`, `srcs/` with one
      Dockerfile per service, `openapi.yaml`, `postman/`, `scripts/`, `docs/`.
- [ ] No tracked file contains a credential literal. `.env.example` is the only tracked file
      that shows password *placeholders* (`inventory_secret_pass` and friends — deliberately
      non-production values); the real `.env` is git-ignored and untracked, so no grep over
      the working tree should be quoted as the proof. Verify against tracked files only:

      ```bash
      git grep -nE '(inventory|billing|rabbit)_secret_pass' -- . ':!.env.example'   # → no output
      git ls-files | grep -c '^\.env$'                                            # → 0
      ```
- [ ] `docker compose down -v --remove-orphans` then `make up` — cold boot from scratch works.
- [ ] `make test` (audit suite `scripts/test_audit.sh`) passes end-to-end.
- [ ] Postman collection imports and runs (`postman/play-with-containers.postman_collection.json`).
- [ ] You can explain every answer in this document **in your own words**.

---

## 2. Section: General — Repo Content

> Audit text: "A `README.md` file and all files used to create, delete and manage the
> student infrastructure must be submitted in the repo."

### "Are all the required files present?"

**Yes.** Demonstrate with:

```bash
git ls-files
```

- `README.md` — run & management documentation
- `docker-compose.yml` — infrastructure definition
- `Makefile` — lifecycle targets (up/down/clean/rebuild/test)
- `srcs/<service>/Dockerfile` for all six services
- `srcs/<service>/**` application code and init scripts
- `openapi.yaml`, `postman/`, `scripts/test_audit.sh`, `docs/`

### "Was the `.env` file excluded from the git files?"

**Yes.** Demonstrate:

```bash
git ls-files | grep '^\.env$'   # → no output (not tracked)
cat .gitignore | grep '^\.env$' # → .env is ignored
ls .env.example                 # → template exists with placeholder values
```

### "Are all pushed files in the repo clean of any credentials or passwords?"

**Yes.** All secrets live exclusively in the untracked `.env` (interpolated into containers
via Compose `${VAR}` substitution). Source, Dockerfiles, and compose file reference only
variable *names*. Demonstrate:

```bash
grep -rn --include='*.py' --include='*.yml' --include='Dockerfile' -iE 'password|secret' . \
  | grep -v '.env.example'
```

→ only `os.getenv(...)` reads and `${VAR}` references, no literal values.

---

## 3. Section: General — Theory Questions

> The auditor asks these verbatim. Answer concisely first, then offer depth.

### "What are containers and what are their advantages?"

A container is a lightweight, standalone, executable software package that bundles
application code with all its libraries, system tools, and runtime dependencies, running as
an **isolated process on the host kernel**.

**Advantages**: portability ("build once, run anywhere"), lightweight/high-density (shares
host kernel — no guest OS, megabytes not gigabytes), isolation (Linux namespaces + cgroups),
immutability and reproducibility (versioned images eliminate environment drift).

### "What is the difference between containers and virtual machines?"

VMs virtualize **hardware**: each VM runs a full guest OS (GBs) on a hypervisor (KVM,
VMware, Hyper-V) — strong isolation but heavy and slow to boot (minutes).

Containers virtualize the **OS**: all containers share the host Linux kernel and carry only
user-space app binaries (MBs), giving near-instant startup and native performance.
Isolation is process-level (namespaces/cgroups), not kernel-level.

### "What is Docker and what is it used for?"

Docker is an open-source platform for building, shipping, and running containers. It
consists of the Docker daemon (`dockerd`), the CLI client, images/registries, and Compose
for multi-container orchestration. It is used to package applications with their
environments once, then run them identically anywhere.

> ✔ "Did the student reply correctly to all the above questions?" — answer all three
> confidently without notes.

---

## 4. Section: README Review

> "Open and read the `README.md` file provided by the student."

### "Does the `README.md` contain all the required information to run and manage the solution (prerequisites, configuration, setup, usage, etc)?"

**Yes.** Walk the auditor through the section map:

- §3 Prerequisites (OS, Docker 24+, Compose v2, Make + curl)
- §4 Configuration — a table covering every variable in `.env.example`, plus the
  `cp .env.example .env` setup step. The password column repeats the non-production
  placeholders from `.env.example` (`inventory_secret_pass` and the two siblings) and
  the following note says to replace them before any real deployment.
- §5 Usage & Management — every `make` target (`help`, `up`, `build`, `ps`, `logs`, `restart`,
  `down`, `clean`, `rebuild`, `test`, `test-py`, `config`, `lint`), plus raw `docker compose`
  equivalents
- §6 API Walkthrough — every endpoint with `curl` examples and expected responses
- §1/§2 Architecture & design decisions
- §7 Architectural Decision Records with audit justifications

---

## 5. Section: Infrastructure Check

### "Does the student architecture reflect the infrastructure enforced by the subject?"

**Yes.** The subject requires: a SQL inventory DB + SQL billing DB, an inventory app, a
billing app consuming from a RabbitMQ queue, an API gateway as the only externally exposed
service (port 3000), all on one Docker network, all volumes and images per spec, all
managed exclusively by docker-compose.

Open the ASCII diagram in README §1 and show the mapping:
gateway → (proxy) inventory-app / (AMQP) rabbit-queue → billing-app → both databases;
single bridge network `play-with-containers-network`; only `3000:3000` published.

> **Note for the defense**: the audit sample output names a container `RabbitMQ` (uppercase)
> and calls the app servers "Node.js". OCI names must be lowercase and the subject allows any
> server implementation — hence our lowercase `rabbit-queue` and Python/Flask servers,
> functionally identical. Say this *before* the auditor asks.

---

## 6. Section: Run the Infrastructure

> Audit runs: `docker-compose up`

### "Does the infrastructure start correctly?"

**Yes.** Run it live:

```bash
make up        # = docker compose up --build -d --wait --wait-timeout 240
docker compose ps
```

All six containers start: `inventory-database`, `billing-database`, `inventory-app`,
`billing-app`, `rabbit-queue`, `api-gateway-app` — each reaching `healthy`/`running`.

**Why cold boot never deadlocks** (likely follow-up): databases run `pg_isready`
healthchecks; apps use two-tier dependencies — `service_healthy` on databases, plus
in-application fixed-interval retry loops (30 attempts × 2 s toward the database, 5 × 1 s
publish attempts in the gateway, a 3 s reconnect loop in the billing consumer) — so slow
first-time volume initialization never causes Compose startup failures. The waits are
constant, not exponentially backed off: Docker's own restart backoff is the only exponential
one in this stack (see §10).

---

## 7. Section: Microservices & Queue Theory Questions

### "What is a microservices' architecture?"

A design pattern structuring an application as a collection of small, loosely coupled,
independently deployable services. Each service handles one business domain (inventory,
billing, gateway) and communicates via well-defined protocols (HTTP REST, AMQP). In this
stack the two domain services each own their own database — `inventory-app` owns
`inventory-database`, `billing-app` owns `billing-database`, two completely separate
PostgreSQL clusters — while `api-gateway-app` is a stateless edge service that owns no
database and is the single public entry point.

### "Why do we use microservices architecture?"

- Independent scalability — scale one service without scaling everything.
- Fault isolation — a `billing-app` crash doesn't take down `inventory-app`.
- Independent deployment and evolvability.
- Faster, low-risk delivery for distributed teams.

One honest caveat: polyglot persistence is a capability of the pattern, not something this
build exercises — all three services are Python 3.12 with Flask and Waitress, and both
domain services speak PostgreSQL.

### "What is a queue and what is it used for?"

A FIFO data structure used in message-oriented middleware for asynchronous communication.
Used for: temporal decoupling (producer/consumer need not be concurrent — the exact
mechanism behind our billing outage demo), load leveling (buffer bursts), and reliability
(persist messages until acknowledged by a worker).

### "What is RabbitMQ?"

An open-source message broker implementing AMQP 0-9-1. It accepts messages from producers,
routes them through exchanges to queues, buffers them durably, and delivers them to
consumers with acknowledgements, QoS/prefetch limits, and clustering support.

> ✔ "Did the student reply correctly to all the above questions?"

---

## 8. Section: Dockerfiles

### "Is there a Dockerfile for each service?"

**Yes** — one per service, at `srcs/<service-name>/Dockerfile` (six total), each referenced
by `build: ./srcs/<service>` in `docker-compose.yml`.

### "Are all Dockerfiles based on Debian or Alpine?"

**Yes** — all six use `FROM alpine:3.23` (the penultimate stable Alpine release; Alpine 3.24
is current stable — subject rule "penultimate stable version"). No pre-built application
images from Docker Hub are used anywhere; only the bare `alpine` base.

### "Are Dockerfiles or any other solution files free from sensitive data?"

**Yes** — secrets exist only in `.env` (git-ignored). Dockerfiles contain no passwords; the
compose file interpolates `${VARS}` at runtime; databases receive credentials as
environment variables.

### "What is a Dockerfile?"

A text file containing ordered instructions executed by Docker to build a container image
layer by layer. Each instruction (RUN, COPY) typically creates a new cached layer; metadata
instructions (ENV, EXPOSE, CMD) configure the image.

### "Explain the instructions used on the Dockerfile."

Explain on the live `srcs/api-gateway-app/Dockerfile`:

| Instruction | Our usage |
|---|---|
| `FROM alpine:3.23` | Penultimate stable Alpine base (subject rule). |
| `WORKDIR /usr/src/app` | Working directory for all later instructions and runtime. |
| `ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1` | No `.pyc` writes; unbuffered logs reach `docker logs` immediately. |
| `RUN apk add --no-cache python3 py3-pip` | Installs Python at **build** time; `--no-cache` keeps the layer small. |
| `COPY requirements.txt .` → `RUN pip install ...` | Dependency layer **before** source copy → build cache keeps pip results across code changes. |
| `COPY server.py openapi.yaml ./`, `COPY app/ ./app/` | Application source into the image. |
| `RUN python3 -c "import flask, ..."` | Build-time smoke test — image build fails fast on broken deps. |
| `RUN mkdir -p /usr/src/logs` | Mount point for the named log volume. |
| `EXPOSE 3000` | Documentation of the listening port (publishing happens in compose `ports:`). |
| `HEALTHCHECK ... CMD python3 -c "urlopen('/health')"` | Daemon probes `/health`; `start-period` covers boot. Drives the `(healthy)` marker in `docker ps` only — the `service_healthy` gating uses the Compose-level DB probes (see §10). |
| `CMD ["python3", "server.py"]` | Exec form → Python *is* PID 1 and SIGTERM from `docker stop` is delivered to it directly. Receiving it is not the same as honouring it — PID 1's default disposition ignores signals that would kill a normal process, so with no handler installed the daemon escalates to SIGKILL. Full mechanism stated once in §17. |

> ✔ "Did the student reply correctly to all the above questions?"

---

## 9. Section: Containers

> Audit runs `docker ps` and checks each container's role and ports.

### Expected `docker ps` shape (ours)

| Container | Image | Ports visible |
|---|---|---|
| inventory-database | inventory-database | `5432/tcp` (exposed, **not** published) |
| billing-database | billing-database | `5432/tcp` |
| inventory-app | inventory-app | `8080/tcp` |
| billing-app | billing-app | `8080/tcp` |
| rabbit-queue | rabbit-queue | `5672/tcp`, `15672/tcp` |
| api-gateway-app | api-gateway-app | `0.0.0.0:3000->3000/tcp` (only published port) |

### Role answers (adapted from the audit's per-container description)

- **inventory-database** — SQL server (PostgreSQL 17) holding the inventory database,
  listening on 5432 *inside the network*.
- **billing-database** — SQL server (PostgreSQL 17) holding the billing `orders` table,
  5432 internal.
- **inventory-app** — REST server for the movie catalogue CRUD, connected to
  inventory-database, port 8080 internal.
- **billing-app** — worker consuming billing messages from the RabbitMQ queue and writing
  orders into billing-database, port 8080 internal.
- **rabbit-queue** — RabbitMQ server holding the durable `billing_queue`.
- **api-gateway-app** — reverse proxy forwarding `/api/movies` to inventory-app and
  publishing billing messages to RabbitMQ; the only published service, port 3000.

> **Wording note**: the audit text says "Node.js server". Our servers are Python/Flask — the
> subject's functional requirements (a server with those ports and behaviors) are met;
> language was our implementation choice.

---

## 10. Section: Restart Policy

```bash
for s in inventory-database billing-database inventory-app billing-app rabbit-queue api-gateway-app; do
  docker inspect -f "{{ .HostConfig.RestartPolicy }}" "$s"
done
# → {on-failure 0}   × 6
```

### "Do all containers have the correct configuration?" / "Are the containers configured to restart in case of failure?"

**Yes** — every service sets `restart: on-failure` in `docker-compose.yml`, inspecting
verbatim as `{on-failure 0}`: restart automatically on any non-zero exit, unlimited retries
(`0` = no maximum). The delay between Docker's own restart attempts *is* exponential (the
daemon backs off, capped around a minute); our applications' in-process retry loops are
constant-interval, not exponential (§6).

**Why `on-failure`** (follow-up): the trigger is the **exit status**, not intent. A clean
shutdown exits `0`, which `on-failure` does not treat as a failure, so the daemon leaves the
container stopped; only genuine failures (crashes, OOM, non-zero exits) are restarted.
That's the difference from `always`/`unless-stopped`, which restart cleanly-exited
containers too. (`always` and `unless-stopped` additionally distinguish a manually stopped
container, which is a separate mechanism from the exit-code test.)

---

## 11. Section: Docker Volumes

```bash
docker volume ls
# DRIVER    VOLUME NAME
# local     inventory-database      ← this project
# local     billing-database        ← this project
# local     api-gateway-app         ← this project
# local     <others>                 ← unrelated projects on the same host
```

### "Do all volumes have the correct configuration?"

**Yes** — the three volumes `audit.md` requires are present, under their exact bare names
(Compose `name:` overrides suppress the project prefix):

- `inventory-database` → mounted at `/var/lib/postgresql/data` (inventory catalogue data)
- `billing-database` → mounted at `/var/lib/postgresql/data` (billing orders data)
- `api-gateway-app` → mounted at `/usr/src/logs` (rotating `gateway.log`)

`rabbit-queue` has no volume. Queue durability for the audit outage comes from a durable
queue and persistent messages on the running broker, not from a named volume. Removing the
broker container discards that node state.

`docker volume ls` lists **every** volume on the host, including ones from unrelated
projects; to show only this stack's, filter by name (`docker volume ls | grep -E
'inventory-database|billing-database|api-gateway-app'`) or scope the evidence to
the project prefix-free names above.

### "What is a Docker volume?"

A directory managed by the Docker daemon outside the container's Union File System
(typically `/var/lib/docker/volumes/<name>/_data`), mounted into containers at a chosen
path.

### "Why do we use Docker volumes?"

- **Persistence** — container filesystems are ephemeral; volumes survive `docker rm` and
  image replacement (database data, logs).
- **Performance** — volumes bypass OverlayFS copy-on-write (native host I/O for DB writes).
- **Backup/migration and sharing** across containers.

> ✔ "Did the student reply correctly to all the above questions?"

---

## 12. Section: Solution Network

### "Is the connection to the api-gateway-app the only one exposed from outside of the Docker host?"

**Yes.** Demonstrate:

```bash
docker ps --format '{{.Names}}: {{.Ports}}'
# only api-gateway-app shows a host mapping: 0.0.0.0:3000->3000
curl -s http://localhost:3000/health            # → reachable
curl -s --connect-timeout 2 http://localhost:5432  # → connection refused (as expected)
```

All internal services use `expose:` (documentation) and are **not published on the host
interface**; container-to-container traffic uses the internal bridge network
`play-with-containers-network`. (Precisely: publishing is what makes a port reachable off the
Docker host — an un-published port is still open on the bridge subnet and reachable *by
container IP from the Docker host itself*. That is exactly why the audit's requirement is
that only the gateway is *published*.)

### "What is the Docker network?"

A software-defined virtual network connecting containers. Ours is a user-defined **bridge**:
containers get private interfaces; the daemon provides embedded DNS so containers resolve
each other by service name.

### "Why do we use the Docker network?"

- **Service discovery** — `http://inventory-app:8080`, `inventory-database:5432`,
  `rabbit-queue:5672` — names, never dynamic IPs.
- **Isolation & perimeter security** — nothing is reachable *off* the host unless published
  via `ports:`; the gateway is the single entry point.

> ✔ "Did the student reply correctly to all the above questions?"

---

## 13. Section: Docker Images

```bash
docker images
# inventory-database, billing-database, inventory-app,
# billing-app, rabbit-queue, api-gateway-app   ← one image per service
```

### "Is there a Docker image for each service with the same service name?"

**Yes.** Each service in `docker-compose.yml` sets `image: <service-name>` identical to the
service and container name (lowercase — OCI repository names must be lowercase; hence
`rabbit-queue` rather than the audit sample's uppercase `RabbitMQ`).

### "What is a Docker image?"

An immutable, read-only template of stacked layers defining the filesystem, libraries, and
binaries to run a container. It is the blueprint from which container instances are created.

### "Why do we use Docker images?"

Reproducibility — the same bytes run in dev, test, and production; versioning and rollback;
efficient sharing of common layers; registry distribution.

> ✔ "Did the student reply correctly to all the above questions?"

---

## 14. Section: Inventory API Endpoints

The auditor uses Postman against `http://localhost:3000` (all through the gateway).

### POST `/api/movies/`

```json
{ "title": "A new movie", "description": "Very short description" }
```

**"Can you confirm the response was the success code `200`?"** — Yes: `HTTP/1.1 200 OK` with
the created record echoed as JSON (`{"id": 1, ...}`).

> Note: the reference `crud-master-py` returned `201 Created`; the audit asks literally for
> `200`, which we return.

### GET `/api/movies/`

**"Can you confirm the response was success code `200` and the body is JSON with the
information of the last added movie?"** — Yes: `HTTP/1.1 200 OK`, body
`{"movies": [ ... {"title": "A new movie", "description": "Very short description"} ]}`.

Also ready: `GET /api/movies?title=new` (filter), `GET /api/movies/1`, `PUT`, `DELETE` —
full walkthrough in README §6.

---

## 15. Section: Billing API Endpoints & Outage Resilience

### POST `/api/billing/` (normal state)

```json
{ "user_id": "20", "number_of_items": "99", "total_amount": "250" }
```

**"Can you confirm the response was success code `200`?"** — Yes, immediately. The gateway
acknowledges on successful enqueue; processing is asynchronous.

### "Stop the billing-app container" → "Can you confirm the `billing-app` container was correctly stopped?"

```bash
docker stop billing-app
docker ps -a --filter name=billing-app     # → Exited
docker inspect -f '{{.State.Running}}' billing-app   # → false
```

### POST during outage → "Can you confirm the response was success code `200` even if the `billing_app` is not working?"

```json
{ "user_id": "22", "number_of_items": "10", "total_amount": "50" }
```

**Yes — `HTTP/1.1 200 OK` immediately.**

### The causal chain to explain verbally

1. The gateway publishes the order to RabbitMQ (`durable=True` queue, persistent messages)
   and returns 200. **It never writes to the billing DB itself.**
2. RabbitMQ buffers the message on the broker while no consumer is connected — nothing is
   lost.
3. On `docker start billing-app`, the consumer reconnects (retry loop, heartbeats) and receives
   the buffered message. Delivery uses `auto_ack=False` + manual acknowledgements: the order is
   inserted into `billing-database` and **only then** acked on success. A failed insert is
   retried a bounded number of times (5 attempts, 1 s apart) and then
   `basic_nack(requeue=True)`d, which returns the message to the head of the queue — so the
   broker redelivers rather than discarding. **There is no dead-letter queue in this build**:
   `queue_declare(queue=..., durable=True)` declares no `x-dead-letter-exchange` /
   `x-dead-letter-routing-key`, and the nack carries no redelivery counter, so the same message
   will be handed out again and the cycle repeats. Name that limitation out loud rather than
   claiming a DLQ that does not exist. If I added one, I would declare
   `x-dead-letter-exchange`/`x-dead-letter-routing-key` on the queue and cap redelivery by
   counting the `x-death` headers RabbitMQ attaches to a dead-lettered message.

**Prove persistence:**

```bash
docker start billing-app
docker exec billing-database psql -U billing_user -d billing_db \
  -c "SELECT * FROM orders WHERE user_id = '22';"
# → the buffered order row appears
```

---

## 16. Section: Bonus

- **"+Did the student use his/her own crud-master solution?"** — The architecture adopts and
  improves our `crud-master-py` lineage; the crosswalk table in README §8 documents each
  adaptation (env-driven DB hosts, 200 vs 201, restart policies, healthchecks, queue type
  coercion).
- **"+Did the student add any optional bonus?"** — Yes: embedded Swagger UI /
  OpenAPI 3.0 docs at `/api/docs` and `/openapi.yaml`, automated audit test suite
  (`make test` → `scripts/test_audit.sh`), Postman audit collection, rotating gateway log
  file on a named volume, comprehensive ADR documentation.
- **"+Is this project an outstanding project?"** — Make the case: every Dockerfile pinned to
  the penultimate stable Alpine release (no floating `latest`), a single published port with
  the rest of the stack internal to one user-defined bridge, network isolation and port
  publishing asserted by an automated test suite, at-least-once queue buffering demonstrated
  live (ack-only-on-success, and nack-and-requeue so a failed insert cycles back through the
  queue instead of vanishing — bounded retries inside one delivery, then requeue; there is no
  DLQ in this build, and that requeue loop is the limitation to name out loud rather than a
  dead-letter queue as a terminal backstop), structured dual-stream logging
  (stdout + a rotating file on a named volume), and complete docs (README + ADR + this audit
  guide + theory guide).

---

## 17. Anticipated Extra Auditor Questions

Beyond the checklist, be ready for these natural follow-ups:

| Question | Answer outline |
|---|---|
| Why Waitress and not `app.run()`? | Werkzeug is a dev server (single-threaded, debugger exposure). Waitress is a production pure-Python threaded WSGI server — no C build needed on musl/Alpine; threads suit I/O-bound proxy/DB workloads. |
| What happens on `docker stop`? What is PID 1? | SIGTERM → grace period (10 s) → SIGKILL. Our `CMD` is exec-form so the app **is** PID 1 and receives SIGTERM directly; unhandled-signal default of PID 1 is *ignore*, hence exec form matters. This is the single canonical statement of the mechanism — see also §8 (Dockerfile table) and §10 (restart policy). |
| Why did you choose musl/Alpine over Debian? | Smallest footprint, deterministic builds; pure-Python deps avoid the musllinux/manylinux wheel problem. Debian was the permitted alternative. |
| `EXPOSE` vs `ports:` vs `expose:`? | `EXPOSE`/`expose:` are documentation metadata only; a port is not reachable *off* the host until `ports:`/`-p` publishes it (iptables DNAT). We publish exactly one port. |
| What does `service_healthy` mean? | Compose waits until the dependency's HEALTHCHECK passes — unlike `service_started` (process merely launched). DBs gate the apps; the broker uses `service_started` + in-app retries. |
| Does `unhealthy` restart a container? | No — restart policies trigger on exit status only; unhealthy is used for `depends_on` gating and diagnostics. |
| Why `prefetch_count=1`? | Fair dispatch: the consumer holds one unacked message at a time; combining with manual acks means a crashed worker re-delivers, never loses work. |
| What if a message is malformed? | It is **acknowledged and discarded** — `basic_ack`, not nacked and not dead-lettered. A poison message can never be retried into success, and requeueing it would cycle it forever and block the queue behind it (head-of-line blocking), so discarding is the correct call. This path is therefore **at-most-once by design**, and a payload of that shape never reaches the database. If I wanted such messages inspectable I would route them to a DLQ instead of dropping them. |
| How is `pg_isready` different from a real login? | It only reports whether the server is accepting connections on that socket; it does **not** authenticate. Prove it: `docker exec inventory-database pg_isready -U bogus_user -d bogus_db -h 127.0.0.1; echo $?` prints `accepting connections` and returns `0` even with a non-existent user and database. So our DB healthchecks assert *readiness*, and real authentication (SCRAM-SHA-256, per `pg_hba.conf`) is what protects the data. |
| How would you scale billing? | Run N `billing-app` replicas on the same queue — RabbitMQ fair-dispatches (prefetch=1). State is in PostgreSQL, workers are stateless. |
| Where do credentials live at runtime? | Only in `.env` → Compose interpolation → container environment variables. Never baked into images. |
| Are containers running as root? | The three application containers run as a dedicated non-root `USER`. The two PostgreSQL images and the RabbitMQ broker start as root only to `su-exec` down to `postgres`/`rabbitmq` before exec'ing the server — the conventional pattern, because they must `chown` their data directories first, which requires privilege to start with. |
| Why not Kubernetes/Swarm? | Compose is single-host orchestration, matching the subject scope; K8s adds multi-node scheduling, self-healing rescheduling, and service discovery at cluster scale — unnecessary here. |
| Is this portable to Podman? | Yes — same OCI images; Podman is daemonless/rootless; compose works via `podman-compose` or Docker Compose with the Podman socket. |

---

## 18. Command Cheat Sheet

```bash
# Lifecycle
make up | make down | make restart | make clean | make rebuild

# Status
docker compose ps
docker ps                          # names, images, ports
docker volume ls | grep -E 'inventory-database|billing-database|api-gateway-app'
                                  # the 3 volumes required by audit.md
docker images                      # 6 images, names == services

# Audit-critical inspections
docker inspect -f "{{ .HostConfig.RestartPolicy }}" api-gateway-app   # {on-failure 0}
docker inspect -f '{{.Config.Image}}' billing-app                     # == service name

# Full automated audit suite
make test

# API smoke
curl -i http://localhost:3000/health
curl -i -X POST http://localhost:3000/api/movies/ \
  -H "Content-Type: application/json" \
  -d '{"title": "A new movie", "description": "Very short description"}'
curl -i http://localhost:3000/api/movies/
curl -i -X POST http://localhost:3000/api/billing/ \
  -H "Content-Type: application/json" \
  -d '{"user_id": "20", "number_of_items": "99", "total_amount": "250"}'

# Outage resilience demo
docker stop billing-app && docker ps -a --filter name=billing-app
curl -i -X POST http://localhost:3000/api/billing/ \
  -H "Content-Type: application/json" \
  -d '{"user_id": "22", "number_of_items": "10", "total_amount": "50"}'
docker start billing-app
docker exec billing-database psql -U billing_user -d billing_db \
  -c "SELECT * FROM orders WHERE user_id = '22';"

# Credentials hygiene proof
git ls-files | grep -c '^\.env$'   # → 0
```

---

*Related docs: [`README.md`](../README.md) (run & manage) ·
[`theory-study-guide.md`](./theory-study-guide.md) (generalized theory) ·
[`requirements/audit.md`](./requirements/audit.md) (verbatim audit checklist) ·
[`requirements/readme.md`](./requirements/readme.md) (subject statement).*
