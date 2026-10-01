# Play with Containers — Audit Defense & Theory Guide

> **Study & defense manual for the `play-with-containers` project**
> Repository root: this repository. Requirements: [`docs/requirements/readme.md`](./readme.md) (the brief) and [`docs/requirements/audit.md`](./audit.md) (the checklist you will be walked through).
> How to use this document: every heading maps to a checklist item or an oral question. The **Direct answer** blocks are what you say; the **Verify** blocks are what you run in front of the evaluator. Every command and output block here has been executed against this repository.

---

## Table of Contents

1. [Pre-flight: prove it works before the evaluator arrives](#1-pre-flight-prove-it-works-before-the-evaluator-arrives)
2. [Repository, secrets and README](#2-repository-secrets-and-readme)
   - [2.1 Required files](#21-required-files-are-all-the-required-files-present)
   - [2.2 `.env` is excluded from Git](#22-was-the-env-file-excluded-from-git-files)
   - [2.3 No credentials in the repository](#23-are-all-pushed-files-clean-of-credentials)
   - [2.4 README completeness](#24-does-the-readme-contain-everything-needed-to-run-and-manage-it)
3. [Containers, VMs and Docker](#3-containers-vms-and-docker)
   - [3.1 Containers, their advantages, and containers vs VMs](#31-what-are-containers-and-what-are-their-advantages)
   - [3.2 What is Docker, and how the runtime works](#32-what-is-docker-and-what-is-it-used-for)
4. [Dockerfiles](#4-dockerfiles)
   - [4.1 What is a Dockerfile, and what each instruction does](#41-what-is-a-dockerfile-and-what-are-its-instructions)
   - [4.2 Layers, caching and the penultimate-stable rule](#42-layers-caching-and-the-penultimate-stable-base-image-rule)
5. [Volumes](#5-volumes)
   - [5.1 What is a Docker volume, and why use them](#51-what-is-a-docker-volume-and-why-do-we-use-them)
6. [Networking](#6-networking)
   - [6.1 What is a Docker network, and why use it](#61-what-is-a-docker-network-and-why-do-we-use-it)
7. [Images](#7-images)
   - [7.1 What is a Docker image, and why use images](#71-what-is-a-docker-image-and-why-do-we-use-images)
8. [Microservices](#8-microservices)
   - [8.1 What is a microservices architecture, and why use it](#81-what-is-a-microservices-architecture-and-why-do-we-use-it)
9. [Queues and RabbitMQ](#9-queues-and-rabbitmq)
   - [9.1 What is a queue, and what is RabbitMQ](#91-what-is-a-queue-and-what-is-rabbitmq)
10. [Running and inspecting the infrastructure](#10-running-and-inspecting-the-infrastructure)
    - [10.1 Does the infrastructure start correctly?](#101-does-the-infrastructure-start-correctly)
    - [10.2 Containers, ports and restart policy](#102-containers-ports-and-restart-policy)
    - [10.3 Docker images](#103-docker-images)
    - [10.4 Named volumes](#104-named-volumes)
    - [10.5 Network isolation](#105-is-the-api-gateway-the-only-service-exposed-outside-the-host)
    - [10.6 Secrets really are external](#106-prove-that-secrets-come-from-env-not-from-the-images)
11. [Endpoint tests](#11-endpoint-tests)
    - [11.1 Inventory endpoints](#111-inventory-endpoints-apimovies)
    - [11.2 Billing endpoint](#112-billing-endpoint-apibilling)
    - [11.3 The outage scenario](#113-the-outage-scenario-the-core-audit-test)
12. [Naming and technology deviations](#12-naming-and-technology-deviations-you-must-be-ready-to-justify)
13. [Bonus](#13-bonus)
14. [Quick command reference](#14-quick-command-reference)
15. [Verified answers to every audit.md item](#15-verified-answers-to-every-auditmd-item)

---

## 1. Pre-flight: prove it works before the evaluator arrives

Run this from a clean checkout. It rebuilds every image with no cache, recreates
the volumes, boots the stack, and runs the automated audit suite.

```bash
cp .env.example .env          # only step you must do once; .env is gitignored
make rebuild                  # down -v, build --no-cache, up -d --wait
make test                     # automated audit verification suite
make test-py                  # automated python unit/live suite
```

**Say this:** *"The infrastructure is entirely declarative. Everything you see
is described in `docker-compose.yml`; `make` is only a convenience wrapper around
`docker compose`, so `docker compose up -d --build` works identically."*

### What to know about the pre-flight

- `make up` uses `docker compose up --build -d --wait --wait-timeout 240`.
  `--wait` blocks until every container is **healthy**, not merely running. This
  matters: on a cold boot PostgreSQL spends ~20 s running `initdb` and RabbitMQ
  needs ~35-45 s to finish `await_startup` and user provisioning. Without
  `--wait` the evaluator's first request could arrive before the databases exist.
- Requires Compose **v2.1+**. `make up` checks this and fails with an explicit
  message rather than an obscure flag error.
- `make rebuild` deletes the volumes. Use `make down` / `make up` if you want to
  keep the data.

### Timing facts you can quote if asked "how long does a cold boot take?"

| Stage | Observed on a cold boot |
|---|---|
| All six images, `build --no-cache` | ~80 s |
| `docker compose up -d --wait` to all-healthy | ~45 s |
| Gateway answering `POST /api/movies/` | ~15 s after `up` |

---

## 2. Repository, secrets and README

### 2.1 Required files (are all the required files present?)

**Direct answer:** *"Yes. The repository contains the `README.md`, the
`docker-compose.yml` that defines every resource, one `Dockerfile` per service
under `srcs/`, the database-initialisation and broker entrypoint scripts, the
`Makefile` that drives the whole lifecycle, the `openapi.yaml` specification,
`.env.example`, and the automated test scripts. Every file needed to create,
delete and manage the infrastructure is committed."*

**Verify**

```bash
git ls-files | wc -l
git status --porcelain      # empty: nothing uncommitted, and .env is ignored
```

Say the exact number from `git ls-files | wc -l` rather than quoting one from
memory — a wrong count is worse than no count.

Key groups, and what each one exists for:

| Path | Purpose |
|---|---|
| `docker-compose.yml` | Declares all 6 services, the network, the 3 volumes, healthchecks, dependency conditions and restart policies. Nothing outside it is needed to run the stack. |
| `Makefile` | Lifecycle interface: `up`, `down`, `build`, `ps`, `logs`, `clean`, `rebuild`, `restart`, `config`, `lint`, `test`, `test-py`, `help`. |
| `README.md` | Architecture, prerequisites, configuration, usage, API examples, ADRs. |
| `openapi.yaml` | OpenAPI 3.0 spec for the four public gateway paths. |
| `srcs/*/Dockerfile` (×6) | One image build per service. |
| `srcs/*/server.py`, `srcs/*/app/*.py` | Application code for the three Python services. |
| `srcs/inventory-database/init-db.sh`, `srcs/billing-database/init-db.sh` | `initdb` + role/database creation, run as `ENTRYPOINT`. |
| `srcs/rabbit-queue/entrypoint.sh` | Broker startup, credential provisioning, permissions, graceful shutdown. |
| `srcs/*/requirements.txt` | Pinned Python dependencies. |
| `srcs/inventory-app/app/validation.py`, `srcs/billing-app/app/validation.py` | Dependency-free request-validation rules, unit-tested on the host by `make test-py`. |
| `srcs/*/.dockerignore` | Keeps host `__pycache__`, `.env` and logs out of the build context. |
| `postman/play-with-containers.postman_collection.json` | Collection covering `/health`, `/api/movies/`, `/api/billing/`. |
| `scripts/test_audit.sh` | Automated audit checklist (`make test`). |
| `scripts/test_api.py` | Python unit + live HTTP suite (`make test-py`). |
| `.env.example` | Template with every variable and non-sensitive placeholder values. |
| `.gitignore` | Excludes `.env`, Python caches and log output. |
| `.env` (not tracked) | Present only in your working copy; created by `cp .env.example .env`. |
| `docs/requirements/AUDIT_GUIDE.md` | This document. |

**If asked "what is `.commandcode/`?"** — it is a local editor scratch
directory, not part of the solution.

### 2.2 Was the `.env` file excluded from Git files?

**Direct answer:** *"Yes. `.env` is listed in `.gitignore` and has never been
staged or committed — not once in the entire history. What is committed instead
is `.env.example`, a template with the same variable names and placeholder
values, so a fresh clone can be brought up with `cp .env.example .env`."*

**Verify**

```bash
git ls-files | grep -E '^\.env$'        # no output: .env is untracked
git check-ignore -v .env                # .gitignore:2:.env   .env
git log --all --oneline -- .env          # no output: never committed
```

**Correct the record if asked:** *"`docker compose` also loads `.env`
automatically for variable interpolation, so the container environment and the
Compose interpolation come from the same single file."*

### 2.3 Are all pushed files clean of credentials?

**Direct answer:** *"Yes. There is no real credential anywhere in Git. Every
secret is read at runtime from an environment variable that Compose fills in
from `.env`. The application code **fails closed**: a missing or empty secret
raises immediately instead of falling back to a hardcoded default, and the shell
entrypoints use `: "${VAR:?...}"` guards. The only literal password-like strings
in the repository are the non-functional placeholders in `.env.example` and the
README table that documents them."*

**Verify** — run the broad sweep first, so you are answering the question that was
actually asked rather than a narrower one:

```bash
# Everything password-like in the tracked tree, with the literals called out.
git grep -inE 'password|secret|passwd|token' -- .
```

The hits fall into exactly three groups, and you should be able to name them:

1. **`.env.example` and `README.md`** — the placeholder values
   (`inventory_secret_pass`, `billing_secret_pass`, `rabbit_secret_pass`).
   These are documentation, they are not credentials for anything real, and the
   brief requires the variable names to be documented.
2. **`docker-compose.yml`** — only `${VAR}` interpolation, never a literal.
3. **Application and script source** — only variable *references*, e.g.
   `_require_env("RABBITMQ_PASSWORD")` and `: "${DB_PASSWORD:?...}"`.

To show there is no literal secret hiding in an image or compose file:

```bash
grep -nE 'inventory_secret_pass|billing_secret_pass|rabbit_secret_pass' \
     srcs/*/Dockerfile docker-compose.yml     # no output
```

**Be precise about the boundary you are claiming.** The strong claim is
"no *production* credential is committed", not "the string `password=` appears
nowhere". An evaluator who greps `password\s*=` will find variable assignments
such as `-v db_password="$DB_PASSWORD"`; those are references, not secrets. Say
so plainly instead of claiming the grep returns nothing.

**Say this as a design point, if it comes up:** *"`psql` and `rabbitmqctl` are
both invoked without the password in `argv`. A password passed as a command-line
argument is visible in `/proc/<pid>/cmdline` to every process in the container
for the lifetime of the process. Our `init-db.sh` feeds it to `psql` through a
`0600` file read by `psql -f`, and `entrypoint.sh` pipes it to
`rabbitmqctl add_user` on stdin."*

### 2.4 Does the README contain everything needed to run and manage it?

**Direct answer:** *"Yes. `README.md` is an end-to-end operational manual:
architecture overview with a topology diagram, a feature and architecture
summary, prerequisites, a configuration section with a `.env` variable reference
table, a usage section covering every Make target and the equivalent raw Compose
commands, an API walkthrough with `curl` examples and expected responses
including the outage demonstration, architectural decision records, and the
`crud-master` lineage crosswalk."*

**Verify**

```bash
grep -n '^#\{1,3\} ' README.md
```

Also demonstrate the two commands the README leads with, since that is what the
evaluator will actually run:

```bash
cp .env.example .env
make up
```

---

## 3. Containers, VMs and Docker

### 3.1 What are containers and what are their advantages?

**Direct answer:** *"A container is an isolated, lightweight process running on
the host's own kernel, bundled with its own filesystem and its dependencies. Its
advantages are portability — the image freezes the whole dependency tree, so it
runs identically on any host with a compatible kernel — density, because there
is no guest OS per unit; startup in milliseconds rather than the minutes a VM
boot takes; and isolation, because the process is confined by kernel namespaces
and its resource use is bounded by control groups."*

Then contrast with VMs, which is the follow-up question.

**Direct answer (containers vs VMs):** *"A VM virtualises hardware: a hypervisor
emulates the CPU, memory and devices, and each VM boots its own complete guest
operating system with its own kernel. A container virtualises the operating
system instead: it is process-level isolation provided by the host kernel, and
all containers on a host share that one kernel. So a VM costs gigabytes and
minutes to start; a container costs megabytes and milliseconds, at the price of
weaker isolation — a kernel bug or a hostile syscall affects every container on
that host."*

| Dimension | Virtual machine | Container |
|---|---|---|
| Virtualisation level | Hardware, via a hypervisor | OS, via kernel namespaces/cgroups |
| Kernel | Each VM boots its own guest kernel | Shares the single host kernel |
| Startup | Minutes (firmware, kernel, init) | Milliseconds (an ordinary process) |
| Disk / memory footprint | Gigabytes | Megabytes |
| Isolation barrier | Hardware-assisted (VT-x/AMD-V) | Kernel namespaces + cgroups |
| Density | Tens per server | Hundreds or thousands per server |

---

### 3.2 What is Docker, and what is it used for?

**Direct answer:** *"Docker is a platform for packaging an application together
with everything it needs to run — its code, its runtime, its libraries and its
configuration — into a portable unit called a container image, and then running
that image as an isolated process. It is used to ship software without
'works on my machine' problems, to run many applications on one host cheaply,
and to make deployment reproducible because an image is an immutable,
versionable artefact."*

**If asked what happens under the hood, this is the pipeline:**

```
docker CLI  ──REST over /var/run/docker.sock──►  dockerd
                                                │
                                                ▼
                                             containerd        (image pull, snapshots)
                                                │
                                                ▼
                                               runc             (namespaces + cgroups)
                                                │
                                                ▼
                                       the containerised process
```

Say this about the isolation primitives, because it is the substance of the
question:

> *"The kernel provides the isolation. `runc` creates **namespaces**, which
> control what a process can *see*: its own PID namespace so it is PID 1 and
> cannot see host processes; its own mount namespace so it only sees its own
> filesystem; its own network namespace so it has a private `eth0` and loopback;
> and separate UTS, IPC and user namespaces. **Control groups** control what a
> process can *use*: a memory ceiling enforced by the kernel OOM killer, a CPU
> weight and quota, a cap on the number of processes, and block-I/O throttling.
> Containers get their isolation from the same kernel the host runs, which is
> both their efficiency and their weaker security boundary compared to a VM."*

**Verify**

```bash
docker info --format '{{.ServerVersion}} {{.Driver}} {{.CgroupVersion}}'
docker exec inventory-app cat /proc/1/cgroup | head -1
```

---

## 4. Dockerfiles

### 4.1 What is a Dockerfile, and what are its instructions?

**Direct answer:** *"A Dockerfile is a declarative text document containing the
ordered instructions Docker executes to build an immutable image. Most
instructions create a filesystem layer; the rest record metadata. Every layer is
content-addressed and cached, so Docker skips any instruction whose inputs have
not changed."*

Know what each of ours does — you will be asked to explain the instructions your
own files use:

| Instruction | Creates a layer? | What it does | Where we use it |
|---|---|---|---|
| `FROM` | Yes (base) | Selects the parent image. | `FROM alpine:3.23` in all six. |
| `WORKDIR` | Directory only | Sets the working directory for later instructions. | `/usr/src/app` in the three apps, `/` elsewhere. |
| `ENV` | Metadata | Sets an environment variable available at build *and* run time. | `PYTHONUNBUFFERED=1`, `PGDATA`, `PATH`. |
| `RUN` | **Yes** | Runs a shell command in a temporary container and commits the filesystem change. | `apk add`, `pip install`, `adduser`, `mkdir /usr/src/logs`, build-time import smoke tests. |
| `COPY` | **Yes** | Copies files from the build context into the image. | `COPY server.py`, `COPY app/ ./app/`, `COPY --chmod=0755 entrypoint.sh ...`. |
| `USER` | Metadata | Switches the user for subsequent instructions *and for the running container*. | `USER app` in the three Python services. |
| `EXPOSE` | Metadata | Documents the port the service listens on. **It does not open a host port.** | `5432`, `8080`, `5672 15672`, `3000`. |
| `STOPSIGNAL` | Metadata | The signal Docker sends on `docker stop`. | `STOPSIGNAL SIGINT` on both database images (see 10.2). |
| `HEALTHCHECK` | Metadata | A periodic probe run by the daemon. | In all three app images and the broker image. |
| `CMD` | Metadata | The default command, in **exec form**. | `CMD ["python3", "server.py"]`. |
| `ENTRYPOINT` | Metadata | The fixed entrypoint, in exec form. | `ENTRYPOINT ["/usr/local/bin/init-db.sh"]`, `["/usr/local/bin/entrypoint.sh"]`. |

**Points to have ready, because they are the questions that follow:**

- *Why exec form (`CMD ["python3", "server.py"]`) rather than shell form?* Inside a
  container the app runs as PID 1, and the kernel does not apply default signal
  dispositions for unhandled terminating signals to a PID-namespace init
  process. With shell form, `/bin/sh -c` becomes PID 1 and never forwards
  `SIGTERM`, so `docker stop` waits out its grace period and the daemon has to
  `SIGKILL`. Exec form hands PID 1 to Python itself, which handles `SIGTERM`.
  This is not theoretical for us: it is why `billing-app` exits **0** on
  `docker stop` instead of 137 — we verify that in `make test`.
- *Why is there no `HEALTHCHECK` in the database images?* The probe needs
  `${DB_USER}` and `${DB_NAME}`, which are only known at run time. Declaring the
  healthcheck in `docker-compose.yml` lets the probe use the container's own
  environment, and keeps Compose as the single source of truth for runtime
  behaviour.
- *Why is there no `VOLUME` instruction?* Declaring volumes in the image would
  make them anonymous. The brief requires three specific, named volumes, so they
  are declared in `docker-compose.yml` with explicit `name:` values.
- *Why do the three Python images run as `USER app`?* They need no privileges.
  The database and broker images do start as root because they must drop
  privileges for their service account with `su-exec`; the process that actually
  serves is `postgres` or `rabbitmq`. You can show this:

  ```bash
  docker exec inventory-app id -u        # 100
  docker exec inventory-database sh -c 'awk "/^Uid:/{print \$2}" /proc/1/status'   # 70 (postgres)
  ```

### 4.2 Layers, caching and the penultimate-stable base image rule

**Direct answer (layers and caching):** *"Each instruction in a Dockerfile
produces a layer. At runtime those read-only layers are stacked and unioned into
the container's view, with a single writable layer on top. When a container
modifies a file that came from a lower layer, the filesystem copies it up before
writing (copy-on-write), so the image itself stays immutable. Docker caches
layers by the instruction and its inputs: if instruction N's inputs are
unchanged, Docker reuses N *and everything after it*. So the ordering rule is
put the things that change rarely first."*

Our app Dockerfiles follow exactly that order:

```dockerfile
RUN apk add --no-cache python3 py3-pip          # 1. system packages: rarely change
COPY requirements.txt ./                        # 2. dependency manifest: changes occasionally
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .                                # 3. application code: changes constantly
COPY app/ ./app/
```

**Say this:** *"Editing a line of application code re-runs only the final `COPY`
layers. If `COPY . .` came before `pip install`, one code change would force a
full dependency reinstall on every build."*

**Direct answer (why `alpine:3.23`):** *"The brief requires the penultimate
stable release of Alpine or Debian. Alpine 3.24 is the current stable and 3.23
is the penultimate, so all six images are `FROM alpine:3.23` — pinned, never
`latest`. A floating `latest` tag means today's build can break next month when
the tag moves, whereas a pinned minor tag gives reproducible builds within a
supported branch. Alpine is also about 4 MB compressed, and we build everything
from Alpine's own package repositories: no Docker Hub service images."*

Verify the tag, and be honest about its granularity:

```bash
grep -H '^FROM' srcs/*/Dockerfile
```

**Answer this if it comes up:** *"`alpine:3.23` is a pinned *minor* tag, not a
digest. That satisfies the 'not `latest`' requirement and keeps us on a
supported security branch — 3.23 receives fixes until November 2027 — while
still picking up patch releases within that branch. Pinning a digest would be
stricter but would block security updates."*

And if asked why not just use `postgres:17` or `rabbitmq:4`:

**Direct answer:** *"The brief says we must build our own images and may not use
pre-built images except Alpine and Debian. So the database is PostgreSQL 17
compiled from Alpine's `postgresql17` package, the broker is RabbitMQ 4.2 from
`rabbitmq-server`, and the three services are Python 3.12 from `python3`. Every
layer is reproducible from Alpine's repository metadata."*

---

## 5. Volumes

### 5.1 What is a Docker volume, and why do we use them?

**Direct answer:** *"A Docker volume is a persistent storage area that the
Docker Engine manages on the host, outside the container's union filesystem.
Container filesystems are ephemeral: they are destroyed with the container, and
`docker compose up --build` recreates a container whenever its image changes —
so without a volume, every database rebuild would lose its data. We use volumes
for the two database data directories and for the gateway's log files. Volumes
also bypass copy-on-write, so database writes go straight to host storage."*

| Mechanism | Host location | Managed by | Survives `docker rm`? |
|---|---|---|---|
| Named volume | `/var/lib/docker/volumes/<name>/_data` | Docker Engine | **Yes** |
| Bind mount | Any host path | You | Depends on the host |
| `tmpfs` | Host RAM | Kernel | No |
| Container layer | OverlayFS upper dir | Docker Engine | No |

**Why the databases specifically need one:**

1. **No data loss.** `docker compose up --build` recreates containers; the volume
   outlives them.
2. **I/O behaviour.** Transactional WAL traffic writes directly to host storage
   instead of through the overlay copy-on-write path.

**Our three volumes, with the exact names the brief requires:**

| Volume | Mounted at | Contents |
|---|---|---|
| `inventory-database` | `/var/lib/postgresql/data` | The inventory PostgreSQL cluster |
| `billing-database` | `/var/lib/postgresql/data` | The billing PostgreSQL cluster |
| `api-gateway-app` | `/usr/src/logs` | Rotating gateway access logs |

**Say this:** *"The `name:` key in `docker-compose.yml` is what makes the volume
appear as exactly `inventory-database` rather than
`play-with-containers_inventory-database`. The brief specifies the bare names, so
Compose's default project prefix would not have matched."*

---

## 6. Networking

### 6.1 What is a Docker network, and why do we use it?

**Direct answer:** *"A Docker network is a virtual network that gives containers
private IP addresses and lets them reach each other by name. We use a
user-defined bridge because it provides two things the default bridge does not:
embedded DNS, so `inventory-app` resolves to a container IP instead of a
hardcoded address, and isolation, so services on it are reachable from other
containers but not from outside the host unless a port is explicitly published."*

**Say this about DNS:** *"On a user-defined bridge, Docker runs an embedded
resolver at `127.0.0.11`. `api-gateway-app` addresses the inventory service as
`http://inventory-app:8080` and gets the container's IP from that resolver.
That is why there are no hardcoded IPs anywhere in our code, and why scaling or
recreating a container does not require a configuration change."*

**Say this about `ports:` versus `expose:`:** *"`ports:` publishes a container
port on the host by installing DNAT rules in `iptables`. `expose:` is metadata
only — it documents the intended port and populates the image metadata, but
creates no host rule at all. Our five internal services use `expose:`; only the
gateway uses `ports: 3000:3000`."*

Verify:

```bash
docker network inspect play-with-containers-network --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{println}}{{end}}'
```

---

## 7. Images

### 7.1 What is a Docker image, and why do we use images?

**Direct answer:** *"An image is an immutable, read-only, layered filesystem plus
the metadata needed to run it — essentially a template for a container. Running
a container creates a writable layer on top of exactly those shared layers.
Images are content-addressed: each layer's hash is derived from its contents, so
a layer is built once, cached, and reused everywhere that identical content is
needed."*

**Direct answer (why images):** *"An image gives us four things: reproducibility,
because the entire dependency tree is frozen into content-addressed layers;
distribution, because an image is a single artifact that moves between machines;
immutability with rollback, because a tagged image cannot change, so a bad
release is a matter of re-running an older tag; and efficiency, because layers
are shared between images and cached on each host, so six images over a common
Alpine base do not cost six copies of the base."*

**Verify — the image layer cache is visible:**

```bash
docker history api-gateway-app
```

---

## 8. Microservices

### 8.1 What is a microservices architecture, and why do we use it?

**Direct answer:** *"A microservices architecture decomposes an application into
small, autonomous services, each organised around one business capability, each
owning its own data, each deployed and scaled independently, and communicating
only over the network through standard protocols such as HTTP or AMQP. We use it
because each service can be built and deployed on its own schedule, and because a
failure is contained: if one service fails, the others keep serving."*

Map each point onto *this* project, because that is what makes the answer concrete:

| Property | In our project |
|---|---|
| Independent deployables | 6 containers from 6 images, each with its own Dockerfile |
| Database per service | `inventory-database` and `billing-database` are completely separate clusters; neither knows the other exists |
| Loose coupling | The gateway talks to `inventory-app` over HTTP; `billing-app` learns about orders only through RabbitMQ |
| Fault isolation | Stopping `billing-app` does not affect `/api/movies/`; inventory traffic is unaffected while an order sits in the queue |
| Asynchronous decoupling | Orders are accepted while the worker is down and processed when it returns |

**If asked "how would you scale `billing-app`?"** — say this, because the naive
answer is wrong for our configuration:

> *"Functionally it scales, because work is distributed one message at a time
> with `prefetch_count=1`. Mechanically it would need one change first: I set
> `container_name: billing-app` because the brief requires the container name to
> match the service name, and that fixed name prevents `docker compose up
> --scale billing-app=N`. Compose only allows scaling services without a
> `container_name`. It is a deliberate trade-off to satisfy the naming
> requirement."*

---

## 9. Queues and RabbitMQ

### 9.1 What is a queue, and what is RabbitMQ?

**Direct answer (queue):** *"A queue is a first-in-first-out buffer that
decouples a producer from a consumer in time. The producer hands work over and
continues; the consumer processes it whenever it is ready. That gives two
properties: temporal decoupling, so a producer can accept work while the consumer
is offline, and load levelling, so a burst of traffic is absorbed by the queue
instead of overwhelming the downstream service."*

**Direct answer (RabbitMQ):** *"RabbitMQ is an open-source message broker that
implements AMQP 0-9-1. It is the queue server in our architecture: the API
gateway publishes billing orders to it and `billing-app` consumes them."*

Then show the three reliability mechanisms, and connect each to a line of code:

1. **Durable queue and persistent messages.** `queue_declare(durable=True)` keeps
   the queue across a broker restart; `delivery_mode=2` tells the broker to write
   each message to disk before confirming it.
2. **Manual acknowledgements after commit.** The consumer sets `auto_ack=False`,
   commits the database transaction, and only then calls `basic_ack`. A crash
   before the ack means RabbitMQ redelivers the message. Conversely, if the
   insert keeps failing we `basic_nack(requeue=True)` rather than acknowledging,
   so a failed order is never silently discarded.
3. **Fair dispatch.** `basic_qos(prefetch_count=1)` means a worker holds one
   unacknowledged message at a time, so work spreads evenly instead of one
   worker hoarding the queue.

**Be precise about the delivery guarantee** — an evaluator who is sharp will ask:

> *"The guarantee is at-least-once for well-formed orders across a worker
> outage. A malformed payload cannot be retried into success, so we
> acknowledge and discard it rather than blocking the queue behind it — that
> path is at-most-once by design. And because the worker commits before it
> acknowledges, a crash in that window can produce a duplicate, so downstream
> logic would need to be idempotent on `user_id` plus order contents. I chose
> durability over de-duplication here because losing a customer order is worse
> than storing it twice."*

**If asked about the publisher side**, say that we use confirms:

> *"The gateway calls `confirm_delivery()` and publishes with `mandatory=True`,
> so an unroutable message or a broker nack is an error rather than a silent
> drop. A `200` from `POST /api/billing/` means the broker accepted the message,
> not merely that the bytes reached a socket."*

---

## 10. Running and inspecting the infrastructure

### 10.1 Does the infrastructure start correctly?

**Run it**

```bash
docker compose up --build -d      # or: make up
```

**Then show it:**

```bash
docker compose ps
```

Real output on a cold boot (the exact shape an evaluator will see):

```console
NAME                 IMAGE                COMMAND                  SERVICE              CREATED          STATUS                    PORTS
api-gateway-app      api-gateway-app      "python3 server.py"      api-gateway-app      48 seconds ago   Up 48 seconds (healthy)    0.0.0.0:3000->3000/tcp, :::3000->3000/tcp
billing-app          billing-app          "python3 server.py"      billing-app          29 seconds ago   Up 29 seconds (healthy)    8080/tcp
billing-database     billing-database     "/usr/local/bin/init…"   billing-database     1 minute ago     Up 1 minute (healthy)      5432/tcp
inventory-app        inventory-app        "python3 server.py"      inventory-app        54 seconds ago   Up 54 seconds (healthy)    8080/tcp
inventory-database   inventory-database   "/usr/local/bin/init…"   inventory-database   1 minute ago     Up 1 minute (healthy)      5432/tcp
rabbit-queue         rabbit-queue         "/usr/local/bin/entr…"   rabbit-queue         1 minute ago     Up 1 minute (healthy)      5672/tcp, 15672/tcp
```

**Direct answer:** *"Yes. All six services build and start, and every container
reaches the healthy state. The order is not arbitrary: Compose starts the two
databases and the broker, waits for their healthchecks, then starts the two
application services, and starts the gateway last — gated on `inventory-app`
and the broker being healthy. That dependency chain is why a cold boot has no
race."*

**The dependency gating is a real answer to a real question.** Explain it if asked
how a cold boot avoids races:

> *"`depends_on` with `condition: service_healthy` makes the gateway wait until
> `inventory-app` has answered its own healthcheck, not merely until its container
> was created. Before we made that change the gateway bound port 3000 while
> `inventory-app` was still connecting to PostgreSQL, so the very first request
> on a cold boot could return 502. The applications additionally retry their
> database connections for up to 60 s, which covers the window where PostgreSQL
> is still running `initdb`."*

**Say this if asked about the run order you observe:** *"The database
entrypoints run `initdb` only when `$PGDATA/PG_VERSION` is absent, so a restart
reuses the existing cluster instead of failing on a non-empty data directory."*

### 10.2 Containers, ports and restart policy

**Show the containers**

```bash
docker ps
```

Confirm the mapping the brief requires:

| Container | Internal port | Published to host? | Role |
|---|---|---|---|
| `inventory-database` | `5432/tcp` | No | Inventory SQL server |
| `billing-database` | `5432/tcp` | No | Billing SQL server |
| `inventory-app` | `8080/tcp` | No | Node/Python inventory service |
| `billing-app` | `8080/tcp` | No | Billing service, consumes the queue |
| `rabbit-queue` | `5672/tcp`, `15672/tcp` | No | RabbitMQ broker and management UI |
| `api-gateway-app` | `3000/tcp` | **Yes — `0.0.0.0:3000->3000/tcp`** | The only ingress point |

**Restart policy — the exact string the checklist expects**

```bash
for s in inventory-database billing-database inventory-app billing-app rabbit-queue api-gateway-app; do
  printf '%-20s %s\n' "$s" "$(docker inspect -f '{{.HostConfig.RestartPolicy}}' "$s")"
done
```

```console
inventory-database  {on-failure 0}
billing-database    {on-failure 0}
inventory-app       {on-failure 0}
billing-app         {on-failure 0}
rabbit-queue        {on-failure 0}
api-gateway-app     {on-failure 0}
```

**Direct answer:** *"Yes. All six containers are configured with
`restart: on-failure`, which the daemon reports as `{on-failure 0}`. The `0` is
the maximum retry count, and zero means unlimited, so a crashed service keeps
being restarted. Crucially, `on-failure` only restarts a *non-zero* exit: an
operator's `docker stop` produces exit 0, so a deliberate stop is respected and
does not fight the restart policy."*

**Prove it rather than claiming it** — this is a strong moment in an audit:

```bash
docker kill --signal=KILL inventory-app      # simulates a crash: non-zero exit
sleep 8
docker inspect -f 'running={{.State.Running}} restarts={{.RestartCount}}' inventory-app
```

Expect `restarts` to have incremented and the container to be running again.

**Be ready to explain the graceful-shutdown work.** `docker stop` should exit 0,
not 137:

```bash
docker stop billing-app
docker inspect -f 'exit={{.State.ExitCode}}' billing-app      # 0
```

> *"`billing-app` installs `SIGTERM`/`SIGINT` handlers, signals its consumer
> thread, and drains the AMQP channel before exiting — so an unacknowledged
> message stays unacknowledged and RabbitMQ requeues it. Exit 137 would mean the
> daemon had to `SIGKILL` after the grace period. The databases ship
> `STOPSIGNAL SIGINT` for the same reason: PostgreSQL maps `SIGTERM` to a *smart*
> shutdown that waits for clients to disconnect, and our application containers
> hold pooled connections, so a `SIGTERM` would hang until the grace period
> expired."*

### 10.3 Docker images

**Verify**

```bash
docker images
```

**Direct answer:** *"Yes — one image per service, and each image name is
identical to its service name, as the brief requires."*

```bash
for s in inventory-database billing-database inventory-app billing-app rabbit-queue api-gateway-app; do
  printf '%-20s image=%s\n' "$s" "$(docker inspect -f '{{.Config.Image}}' "$s")"
done
```

```console
inventory-database  image=inventory-database
billing-database    image=billing-database
inventory-app       image=inventory-app
billing-app         image=billing-app
rabbit-queue        image=rabbit-queue
api-gateway-app     image=api-gateway-app
```

**If asked "how do you know the images are yours, not pulled?"** show the history:

```bash
docker history --no-trunc inventory-database | head
```

All six are `FROM alpine:3.23` and install their software with `apk add`. No
`postgres`, `node`, `rabbitmq` or `python` base image is pulled from a registry.

### 10.4 Named volumes

**Verify**

```bash
docker volume ls
docker inspect -f '{{range .Mounts}}{{.Type}} {{.Name}} -> {{.Destination}}{{println}}{{end}}' inventory-database
docker inspect -f '{{range .Mounts}}{{.Type}} {{.Name}} -> {{.Destination}}{{println}}{{end}}' billing-database
docker inspect -f '{{range .Mounts}}{{.Type}} {{.Name}} -> {{.Destination}}{{println}}{{end}}' api-gateway-app
```

**Direct answer:** *"Yes. Exactly the three volumes the brief requires, with the
exact names, mounted where they belong."*

```console
volume inventory-database -> /var/lib/postgresql/data
volume billing-database   -> /var/lib/postgresql/data
volume api-gateway-app    -> /usr/src/logs
```

**Prove the log volume is actually in use** (an empty mount proves nothing):

```bash
docker exec api-gateway-app ls -l /usr/src/logs/
# -rw-r--r-- 1 app app ... gateway.log
docker exec api-gateway-app tail -3 /usr/src/logs/gateway.log
```

### 10.5 Is the API gateway the only service exposed outside the host?

**Verify — assert against Docker's own state, not the host socket**

```bash
for s in inventory-database billing-database inventory-app billing-app rabbit-queue; do
  printf '%-20s %s\n' "$s" "$(docker port "$s" 2>/dev/null || echo 'no published port')"
done
printf '%-20s %s\n' api-gateway-app "$(docker port api-gateway-app)"
```

```console
inventory-database  no published port
billing-database    no published port
inventory-app       no published port
billing-app         no published port
rabbit-queue        no published port
api-gateway-app     3000/tcp -> 0.0.0.0:3000
```

**Direct answer:** *"Yes. Only `api-gateway-app` has a `ports:` mapping, and it is
the only container the daemon publishes on the host. The other five use `expose:`,
which is metadata and creates no host rule, so the databases, the broker and the
internal services are reachable only from other containers on the bridge
network."*

**Verify from inside the network, to prove the services are alive but private:**

```bash
docker exec api-gateway-app python3 -c "import urllib.request; print(urllib.request.urlopen('http://inventory-app:8080/health').read().decode())"
# {"status":"healthy"}
```

**Do not demonstrate isolation by curling `localhost:5432`.** A refusal proves
only that nothing on that port speaks HTTP; a *success* would mean some unrelated
daemon on your machine answers, not that Docker published the port. The
`docker port` output above is the authoritative check, which is what
`scripts/test_audit.sh` asserts.

### 10.6 Prove that secrets come from env, not from the images

```bash
# No literal secret in any image layer
docker history --no-trunc inventory-database | grep -iE 'password|secret'   # no output

# But the container is running with it
docker exec inventory-database sh -c 'echo "user=$DB_USER db=$DB_NAME"'
# user=inventory_user db=inventory_db

# The app fails closed rather than defaulting
docker exec api-gateway-app python3 -c "
import os
os.environ.pop('RABBITMQ_PASSWORD', None)
from app.queue_sender import _require_env
try:
    _require_env('RABBITMQ_PASSWORD')
except RuntimeError as e:
    print('fails closed:', e)
"
# fails closed: Missing required secret environment variable: RABBITMQ_PASSWORD
```

**Direct answer:** *"Secrets exist at runtime in the container environment and
nowhere else. They arrive from `.env` through Compose interpolation; the images
carry no secret in any layer, and the code refuses to start rather than fall back
to a hardcoded default."*

---

## 11. Endpoint tests

All client traffic goes to the gateway: `http://localhost:3000`.

### 11.1 Inventory endpoints (`/api/movies`)

**POST — add a movie**

```bash
curl -i -X POST http://localhost:3000/api/movies/ \
  -H "Content-Type: application/json" \
  -d '{"title": "A new movie", "description": "Very short description"}'
```

```console
HTTP/1.1 200 OK
Content-Type: application/json

{"description":"Very short description","id":1,"title":"A new movie"}
```

**Direct answer:** *"Confirmed, the response code is `200`."* Note `200` and not
`201`: the audit expects success, and a `201` would still be a success code but
the checklist asks for `200`, so we return `200`.

**GET — list movies**

```bash
curl -i http://localhost:3000/api/movies/
```

```console
HTTP/1.1 200 OK
Content-Type: application/json

{"movies":[{"description":"Very short description","id":1,"title":"A new movie"}]}
```

**Direct answer:** *"Confirmed: `200`, the body is JSON, and it contains the
movie that was just added. On a fresh database the `id` is 1; after previous
inserts it will be higher."*

**Be ready for "the response is an object wrapping an array, not an array"** —
answer it rather than being surprised:

> *"The envelope is `{"movies": [...]}`. A bare array would be harder to extend —
> there is nowhere to add pagination metadata later without breaking clients.
> The audit only requires that the body is JSON containing the added movie,
> which it is."*

**Other endpoints, if asked to demonstrate more:**

```bash
curl -s "http://localhost:3000/api/movies?title=new"   # substring filter
curl -s http://localhost:3000/api/movies/1             # by id
curl -s -X PUT http://localhost:3000/api/movies/1 -H "Content-Type: application/json" \
     -d '{"title":"Updated","description":"Updated description"}'
curl -s -X DELETE http://localhost:3000/api/movies/1
```

**Explain the delete guard, because it looks unusual:**

> *"`DELETE /api/movies` clears the whole catalogue and it is reachable
> unauthenticated through the public gateway, so it requires an explicit
> `?confirm=all`. Without the guard a single stray request would destroy the data
> an evaluator is inspecting. Single-row deletion via `DELETE /api/movies/{id}`
> needs no flag."*

**Both path spellings work** — say so if the evaluator omits the trailing slash:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/api/movies    # 200
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/api/movies/   # 200
```

### 11.2 Billing endpoint (`/api/billing`)

```bash
curl -i -X POST http://localhost:3000/api/billing/ \
  -H "Content-Type: application/json" \
  -d '{"user_id": "20", "number_of_items": "99", "total_amount": "250"}'
```

```console
HTTP/1.1 200 OK
Content-Type: application/json

{"message":"{\"user_id\": \"20\", \"number_of_items\": \"99\", \"total_amount\": \"250\"} sent"}
```

**Direct answer:** *"Confirmed, `200`."* The `message` field echoes the request
body back verbatim, so what you see inside the string is exactly the JSON you
posted, including its whitespace.

**Verify it was really stored, not just accepted:**

```bash
docker exec billing-database psql -U billing_user -d billing_db -c \
  "SELECT id, user_id, number_of_items, total_amount FROM orders ORDER BY id;"
```

```console
 id | user_id | number_of_items | total_amount
----+---------+-----------------+--------------
  1 | 20      |              99 |          250.00
(1 row)
```

**Explain the string coercion** if asked why the audit posts numbers as strings:

> *"The audit payload sends `number_of_items` and `total_amount` as JSON
> strings. The consumer coerces them explicitly with `int()` and `float()`
> rather than trusting the JSON types. Coercion failures raise a validation
> error, and the message is acknowledged and discarded so one malformed order
> cannot block the queue behind it."*

### 11.3 The outage scenario (the core audit test)

**Step 1 — stop the worker**

```bash
docker stop billing-app
```

**Step 2 — confirm it is stopped**

```bash
docker ps -a --filter name=billing-app
docker inspect -f '{{.State.Running}}' billing-app
```

```console
billing-app   Exited (0) 2 seconds ago
false
```

**Direct answer:** *"Confirmed, `billing-app` is stopped — `State.Running` is
`false`. Note the exit code is `0`, which means it shut down gracefully on
`SIGTERM` rather than being killed."*

**Step 3 — send an order while the worker is down**

```bash
curl -i -X POST http://localhost:3000/api/billing/ \
  -H "Content-Type: application/json" \
  -d '{"user_id": "22", "number_of_items": "10", "total_amount": "50"}'
```

```console
HTTP/1.1 200 OK
Content-Type: application/json

{"message":"{\"user_id\": \"22\", \"number_of_items\": \"10\", \"total_amount\": \"50\"} sent"}
```

**Direct answer:** *"Confirmed, `200`, even though `billing-app` is not
running."*

**Then explain why — this is the question behind the question:**

> *"The gateway never writes to the billing database and never talks to
> `billing-app`. `POST /api/billing/` is handled by the gateway alone: it
> publishes the order to RabbitMQ and returns immediately. The queue is declared
> durable and the message is published with `delivery_mode=2`, so the broker has
> already written it to disk before it acknowledges, and the publisher confirms
> that. `billing-app` being down does not affect the gateway at all — the two
> services are coupled only through the broker. Temporal decoupling is the whole
> point of the queue."*

**Step 4 — restart and prove nothing was lost**

```bash
docker start billing-app
sleep 3
docker exec billing-database psql -U billing_user -d billing_db -c \
  "SELECT id, user_id, number_of_items, total_amount FROM orders WHERE user_id = '22';"
```

```console
 id | user_id | number_of_items | total_amount
----+---------+-----------------+--------------
  2 | 22      |              10 |           50.00
(1 row)
```

**Direct answer:** *"Confirmed — the order submitted while the worker was down
was buffered in RabbitMQ and persisted once the worker returned. There is no
data loss across the outage. The `id` is `2` on a fresh database; a higher value
just means earlier orders exist."*

**Show the timing from the worker log — it is convincing:**

```bash
docker logs billing-app --since 60s 2>&1 | grep -E "Connected to RabbitMQ|Successfully processed"
```

```console
[INFO] [billing-app] Connected to RabbitMQ. Waiting for billing messages on 'billing_queue'...
[INFO] [billing-app] Successfully processed and recorded order #2 for user '22' (items=10, total=$50.00)
```

---

## 12. Naming and technology deviations you must be ready to justify

Two places where our implementation is defensible but not literally what
`audit.md`'s sample output shows. Raise these yourself, before the evaluator has
to.

### The broker is named `rabbit-queue`, not `RabbitMQ`

**What the checklist shows:** `audit.md` prints `RabbitMQ` in the sample
`docker ps`, `docker images` and `docker-compose up` output.

**What we use:** `rabbit-queue` as the service key, the image name and the
container name.

**Your answer:**

> *"`RabbitMQ` is not a legal Docker name — repository names must be lowercase,
> so an image literally called `RabbitMQ` would be rejected by the daemon. The
> brief itself calls the service `rabbit-queue` in its own service list, which is
> the specification that governs; the capitalised `RabbitMQ` in the audit's
> sample output is a display convention. I chose the name that the brief uses and
> that the daemon accepts, and I applied it consistently: service key, image and
> container are all `rabbit-queue`, which is what 'the service and its image must
> share the same name' actually requires."*

### The services are Python, not Node.js

**What the checklist shows:** `audit.md` describes the three application
containers as "a Node.js server".

**What we use:** Python 3.12 with Flask and Waitress.

**Your answer:**

> *"The brief for this project points at the `crud-master` project and links a
> Python reference solution, and the brief's own service descriptions say only
> 'a server' — it never mandates a language. `audit.md`'s Node.js wording is
> carried over from the project description the checklist was written against.
> What the brief does mandate is that we use our own `crud-master` services, and
> those were Python, so Flask plus Waitress is the faithful implementation. The
> architecture, the ports, the queue and the volume topology are exactly as
> specified."*

---

## 13. Bonus

### Did the student use his or her own `crud-master` solution?

**Direct answer:** *"Yes. The three application services are my `crud-master`
microservices, adapted rather than replaced: same domain model (movies, orders),
same CRUD surface, moved from a single-process development server to a
production WSGI server behind the gateway."*

Point at the concrete adaptations:

| `crud-master` baseline | Here |
|---|---|
| Flask development server (`app.run()`) | **Waitress**, a multi-threaded production WSGI server |
| Hardcoded `localhost` database URLs | Docker-DNS service names from environment variables |
| Database per service in one process | Separate PostgreSQL container and volume per service |
| No restart policy | `restart: on-failure` on all six services |
| Response codes left to the framework's defaults | Explicit `200` on creation, to match the audit criteria |
| No startup coordination | Healthcheck-gated `depends_on` plus bounded connection retries |

**Do not over-claim the baseline.** Say "these are the changes I made to my
`crud-master` services" rather than asserting details of the earlier project you
would have to justify line by line.

### Did the student add any optional bonus?

**Direct answer:** *"Yes — several additions beyond the mandatory scope."*

Name them concretely, and be ready to demo any of them on request:

1. **Interactive OpenAPI documentation.** `http://localhost:3000/docs` serves a
   Swagger UI against `openapi.yaml`. *Caveat to state if asked:* the UI assets
   load from a CDN, so it needs internet access; the raw spec at
   `/openapi.yaml` works either way.
2. **Two automated test suites.** `make test` walks the audit checklist end to
   end — 36 assertions covering image names, restart policies, volume names,
   port isolation, live CRUD and the outage scenario. `make test-py` adds ten
   Python tests, four of which run real HTTP against the gateway.
3. **Complete lifecycle automation.** `make up|down|build|ps|logs|clean|rebuild|restart|config|lint|test|test-py|help`.
4. **Persistent dual-stream logging.** The gateway writes to stdout *and* to a
   rotating 5 MB × 3 file on the `api-gateway-app` volume, so logs survive a
   container replacement.
5. **Security hardening beyond the brief.** Non-root application containers; no
   password in any `argv`; secrets fail closed; destructive catalogue deletion
   gated behind `?confirm=all`; upstream path sanitisation and bounded retries
   in the proxy; publisher confirms and mandatory delivery.
6. **Operational health.** A `/health` endpoint on all three services, healthcheck
   gating of startup order, and a `Postman` collection mirroring the audit's
   requests.

### Is this project an outstanding project?

Have a short, specific answer ready rather than a claim:

> *"The parts I would point to are the correctness properties rather than the
> feature count. First, the ordering guarantees: the gateway is gated on
> `inventory-app` being *healthy*, not merely started, so there is no
> cold-boot race; the databases ship `STOPSIGNAL SIGINT`, so a `docker stop`
> exits 0 rather than being killed; and the consumer drains its AMQP channel
> before exiting, so an unacknowledged message is requeued instead of lost.
> Second, the failure semantics are honest: the consumer `nack`s an order it
> could not persist instead of acknowledging and dropping it, and the publisher
> uses confirms so a `200` means the broker accepted the message. Third, the
> test suite is adversarial rather than decorative — it uses a unique per-run
> sentinel so it cannot pass on rows left by a previous run, and it asserts
> against `docker port` rather than a host socket, which is what caught a
> false failure in an earlier version. And the security posture is consistent
> rather than incidental: no secret in any image layer, none in any `argv`,
> failing closed, non-root where possible, one published port."*

---

## 14. Quick command reference

| Checklist item | Command | Expected |
|---|---|---|
| Files present | `git ls-files | wc -l` \| `git status --porcelain` | a file count, and empty status |
| `.env` excluded | `git ls-files \| grep -E '^\.env$'` | no output |
| `.env` never committed | `git log --all --oneline -- .env` | no output |
| No credentials | `git grep -inE 'password\|secret' -- .` | placeholders and `${VAR}` refs only |
| No secret in images | `docker history --no-trunc inventory-database \| grep -i password` | no output |
| Base image | `grep -H '^FROM' srcs/*/Dockerfile` | `FROM alpine:3.23` ×6 |
| Start the stack | `make up` | all six healthy |
| Container status | `docker compose ps` | six `Up (healthy)` |
| Restart policy | `docker inspect -f '{{.HostConfig.RestartPolicy}}' <c>` | `{on-failure 0}` ×6 |
| Restart actually works | `docker kill -s KILL inventory-app; sleep 8` | `RestartCount` increments |
| Graceful stop | `docker stop billing-app` | exit `0` |
| Images | `docker inspect -f '{{.Config.Image}}' <c>` | name equals service name |
| Image history | `docker history api-gateway-app` | all `apk`/`pip`, no Hub service image |
| Volumes exist | `docker volume ls` | `inventory-database`, `billing-database`, `api-gateway-app` |
| Volume mounts | `docker inspect -f '{{range .Mounts}}{{.Name}} -> {{.Destination}}{{end}}' <c>` | correct destination |
| Only gateway published | `docker port <c>` | empty for the five internal services |
| Inter-container DNS | `docker exec api-gateway-app python3 -c "import urllib.request;print(urllib.request.urlopen('http://inventory-app:8080/health').read())"` | `{"status":"healthy"}` |
| POST `/api/movies/` | `curl -i -X POST http://localhost:3000/api/movies/ -H "Content-Type: application/json" -d '{"title":"A new movie","description":"Very short description"}'` | `200` + JSON with `id` |
| GET `/api/movies/` | `curl -i http://localhost:3000/api/movies/` | `200` + the movie just added |
| POST `/api/billing/` | `curl -i -X POST http://localhost:3000/api/billing/ -H "Content-Type: application/json" -d '{"user_id":"20","number_of_items":"99","total_amount":"250"}'` | `200` |
| Stop worker | `docker stop billing-app` | `Exited (0)` |
| POST during outage | `curl -i -X POST http://localhost:3000/api/billing/ -H "Content-Type: application/json" -d '{"user_id":"22","number_of_items":"10","total_amount":"50"}'` | `200` |
| Restart worker | `docker start billing-app` | reconnects |
| Order persisted | `docker exec billing-database psql -U billing_user -d billing_db -c "SELECT * FROM orders WHERE user_id='22';"` | one row |
| Full automated suite | `make test` | `ALL AUDIT CHECKS PASSED!` |
| Python suite | `make test-py` | `Ran 10 tests ... OK` |

---

## 15. Verified answers to every `audit.md` item

Every item in `docs/requirements/audit.md`, in order, with where it is answered
above and how it was verified.

| # | `audit.md` item | Answered in | Verified by |
|---|---|---|---|
| 1 | Required files present | [2.1](#21-required-files-are-all-the-required-files-present) | `git ls-files` |
| 2 | `.env` excluded from git | [2.2](#22-was-the-env-file-excluded-from-git-files) | `git ls-files`, `git check-ignore`, `git log` |
| 3 | No credentials in pushed files | [2.3](#23-are-all-pushed-files-clean-of-credentials) | `git grep -inE 'password\|secret'`, `docker history` |
| 4 | Containers and their advantages | [3.1](#31-what-are-containers-and-what-are-their-advantages) | Oral |
| 5 | Containers vs virtual machines | [3.1](#31-what-are-containers-and-what-are-their-advantages) | Oral |
| 6 | What is Docker, used for | [3.2](#32-what-is-docker-and-what-is-it-used-for) | Oral |
| 7 | Replies correct to the above | [3.1](#31-what-are-containers-and-what-are-their-advantages), [3.2](#32-what-is-docker-and-what-is-it-used-for) | — |
| 8 | README has all needed information | [2.4](#24-does-the-readme-contain-everything-needed-to-run-and-manage-it) | `grep '^#' README.md` |
| 9 | Architecture matches the subject | [10](#10-running-and-inspecting-the-infrastructure), [12](#12-naming-and-technology-deviations-you-must-be-ready-to-justify) | `docker compose ps` |
| 10 | Infrastructure starts correctly | [10.1](#101-does-the-infrastructure-start-correctly) | `make up`, `docker compose ps` |
| 11 | Microservices architecture | [8.1](#81-what-is-a-microservices-architecture-and-why-do-we-use-it) | Oral |
| 12 | Why microservices | [8.1](#81-what-is-a-microservices-architecture-and-why-do-we-use-it) | Oral |
| 13 | What is a queue | [9.1](#91-what-is-a-queue-and-what-is-rabbitmq) | Oral |
| 14 | What is RabbitMQ | [9.1](#91-what-is-a-queue-and-what-is-rabbitmq) | Oral |
| 15 | Replies correct to the above | [8.1](#81-what-is-a-microservices-architecture-and-why-do-we-use-it), [9.1](#91-what-is-a-queue-and-what-is-rabbitmq) | — |
| 16 | Dockerfile for each service | [4.1](#41-what-is-a-dockerfile-and-what-are-its-instructions) | `ls srcs/*/Dockerfile` |
| 17 | All based on Debian or Alpine | [4.2](#42-layers-caching-and-the-penultimate-stable-base-image-rule) | `grep -H '^FROM' srcs/*/Dockerfile` |
| 18 | Dockerfiles free of sensitive data | [2.3](#23-are-all-pushed-files-clean-of-credentials), [10.6](#106-prove-that-secrets-come-from-env-not-from-the-images) | `grep`, `docker history` |
| 19 | What is a Dockerfile | [4.1](#41-what-is-a-dockerfile-and-what-are-its-instructions) | Oral |
| 20 | Explain the Dockerfile instructions | [4.1](#41-what-is-a-dockerfile-and-what-are-its-instructions) | Oral, with the instruction table |
| 21 | Replies correct to the above | [4.1](#41-what-is-a-dockerfile-and-what-are-its-instructions) | — |
| 22 | Containers correct configuration | [10.2](#102-containers-ports-and-restart-policy) | `docker ps` |
| 23 | Restart policy `on-failure` | [10.2](#102-containers-ports-and-restart-policy) | `docker inspect` + live kill test |
| 24 | Volumes correct configuration | [10.4](#104-named-volumes) | `docker volume ls`, `docker inspect` |
| 25 | What is a Docker volume | [5.1](#51-what-is-a-docker-volume-and-why-do-we-use-them) | Oral |
| 26 | Why use Docker volumes | [5.1](#51-what-is-a-docker-volume-and-why-do-we-use-them) | Oral |
| 27 | Replies correct to the above | [5.1](#51-what-is-a-docker-volume-and-why-do-we-use-them) | — |
| 28 | Gateway the only external connection | [10.5](#105-is-the-api-gateway-the-only-service-exposed-outside-the-host) | `docker port` |
| 29 | What is a Docker network | [6.1](#61-what-is-a-docker-network-and-why-do-we-use-it) | Oral |
| 30 | Why use Docker networks | [6.1](#61-what-is-a-docker-network-and-why-do-we-use-it) | Oral |
| 31 | Replies correct to the above | [6.1](#61-what-is-a-docker-network-and-why-do-we-use-it) | — |
| 32 | One image per service, same name | [10.3](#103-docker-images) | `docker inspect -f '{{.Config.Image}}'` |
| 33 | What is a Docker image | [7.1](#71-what-is-a-docker-image-and-why-do-we-use-images) | Oral |
| 34 | Why use Docker images | [7.1](#71-what-is-a-docker-image-and-why-do-we-use-images) | Oral |
| 35 | Replies correct to the above | [7.1](#71-what-is-a-docker-image-and-why-do-we-use-images) | — |
| 36 | POST `/api/movies/` → `200` | [11.1](#111-inventory-endpoints-apimovies) | `curl -i` |
| 37 | GET `/api/movies/` → `200` with the movie | [11.1](#111-inventory-endpoints-apimovies) | `curl -i` |
| 38 | POST `/api/billing/` → `200` | [11.2](#112-billing-endpoint-apibilling) | `curl -i` |
| 39 | Stop `billing-app` and confirm stopped | [11.3](#113-the-outage-scenario-the-core-audit-test) | `docker stop`, `docker inspect` |
| 40 | POST `/api/billing/` → `200` while worker down | [11.3](#113-the-outage-scenario-the-core-audit-test) | `curl -i` + psql afterwards |
| 41 | Bonus: own `crud-master` used | [13](#13-bonus) | README crosswalk |
| 42 | Bonus: optional additions | [13](#13-bonus) | Demos on request |
| 43 | Bonus: outstanding project | [13](#13-bonus) | Oral |

---

*Every command and output block in this document was executed against this
repository. Where a block shows a state that depends on data, the dependency is
stated inline (for example "on a fresh database the `id` is 1").*