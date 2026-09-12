# Play with Containers — Definitive Audit Defense & Theory Guide

> **Official Study & Examination Defense Manual**  
> **Project**: `play-with-containers`  
> **Target Audience**: Students, Reviewers, and Evaluators  
> **Repository Location**: `/home/ertval/code/zone-modules/play-with-containers`  
> **Compliance Standard**: 100% Alignment with `audit.md` and `docs/requirements/audit.md`

---

## Table of Contents

1. [Audit Strategy & Pre-Flight Checklist](#1-audit-strategy--pre-flight-checklist)
2. [General & Repository Structure](#2-general--repository-structure)
   - [Required Files Verification](#21-required-files-verification)
   - [Environment File (`.env`) Git Exclusion](#22-environment-file-env-git-exclusion)
   - [Credential & Secret Hygiene](#23-credential--secret-hygiene)
   - [README Completeness Review](#24-readme-completeness-review)
   - [Architectural Conformity](#25-architectural-conformity)
3. [Theory Questions & Comprehensive Deep Dives](#3-theory-questions--comprehensive-deep-dives)
   - [Q1: What is a Container vs a Virtual Machine?](#31-what-is-a-container-vs-a-virtual-machine)
   - [Q2: Docker Engine & Container Runtime Internals (Namespaces & cgroups)](#32-docker-engine--container-runtime-internals-namespaces--cgroups)
   - [Q3: Dockerfiles, Layer Caching & Base Image Discipline](#33-dockerfiles-layer-caching--base-image-discipline)
   - [Q4: Docker Storage & Named Volume Persistence](#34-docker-storage--named-volume-persistence)
   - [Q5: Docker Networking, DNS Resolution & Port Publishing](#35-docker-networking-dns-resolution--port-publishing)
   - [Q6: Docker Compose & Multi-Container Orchestration](#36-docker-compose--multi-container-orchestration)
   - [Q7: Microservices Architecture & Design Principles](#37-microservices-architecture--design-principles)
   - [Q8: Message Queues & RabbitMQ Fundamentals](#38-message-queues--rabbitmq-fundamentals)
4. [Architecture & Infrastructure Walkthrough](#4-architecture--infrastructure-walkthrough)
   - [Booting the Stack (`docker compose up -d`)](#41-booting-the-stack-docker-compose-up--d)
   - [Inspecting the 6 Containers & Restart Policies](#42-inspecting-the-6-containers--restart-policies)
   - [Verifying Named Volumes](#43-verifying-named-volumes)
   - [Verifying Network Isolation & Host Ports](#44-verifying-network-isolation--host-ports)
   - [Verifying Environment Configuration](#45-verifying-environment-configuration)
5. [Endpoint Testing & Outage Resilience Scenarios](#5-endpoint-testing--outage-resilience-scenarios)
   - [Inventory Movie Catalogue Testing (`/api/movies`)](#51-inventory-movie-catalogue-testing-apimovies)
   - [Billing Asynchronous Enqueueing (`/api/billing`)](#52-billing-asynchronous-enqueueing-apibilling)
   - [Outage Resilience Simulation (Audit Core Scenario)](#53-outage-resilience-simulation-audit-core-scenario)
6. [Bonus Defense & Architectural Excellence](#6-bonus-defense--architectural-excellence)
   - [Lineage from `crud-master` in Python](#61-lineage-from-crud-master-in-python)
   - [Makefile Automation Suite](#62-makefile-automation-suite)
   - [Interactive OpenAPI 3.0 / Swagger UI](#63-interactive-openapi-30--swagger-ui)
   - [Automated E2E Test Suites](#64-automated-e2e-test-suites)
   - [Dual-Stream Logging & Hardened Defaults](#65-dual-stream-logging--hardened-defaults)
7. [Quick Command Reference for the Oral Audit](#7-quick-command-reference-for-the-oral-audit)

---

## 1. Audit Strategy & Pre-Flight Checklist

During an audit defense, you must demonstrate both **hands-on mastery** of the running infrastructure and **rigorous theoretical understanding** of Linux containerization. Follow this presentation protocol:

1. **Answer clearly and concisely first**: Give a direct, 1–2 sentence definition before diving into technical depth.
2. **Back answers with live verification**: Whenever explaining a feature (e.g. restart policies or network isolation), run the corresponding inspection command.
3. **Be transparent about implementation choices**: Explain why Python 3.12 / Waitress was chosen over Node.js (custom microservices lineage), why `alpine:3.23` satisfies the penultimate stable version requirement, and why port `3000` is the single ingress point.

### Pre-Flight Verification Commands

Run these checks prior to the evaluation:

```bash
# 1. Ensure working directory is clean
git status

# 2. Confirm .env is ignored and not tracked
git ls-files | grep '^\.env$'   # (Must return nothing)
cat .gitignore | grep '^\.env$' # (Must match .env)

# 3. Verify clean boot of infrastructure
make rebuild
# or: docker compose down -v --remove-orphans && docker compose up --build -d

# 4. Run automated E2E audit verification test suite
make test
# or: bash scripts/test_audit.sh

# 5. Run Python automated unit and integration suite
make test-py
# or: python3 scripts/test_api.py
```

---

## 2. General & Repository Structure

### 2.1 Required Files Verification

> **Audit Checklist Item**:  
> *"A `README.md` file and all files used to create, delete and manage the student infrastructure must be submitted in the repo. Are all the required files present?"*

#### Direct Oral Answer
> **"Yes. The repository contains all required declarative configuration files (`docker-compose.yml`), dedicated Dockerfiles for all 6 microservices located under `srcs/`, complete lifecycle automation tools (`Makefile`), the OpenAPI specification (`openapi.yaml`), the Postman collection (`postman/`), test scripts (`scripts/`), and comprehensive documentation (`README.md`, `AUDIT_GUIDE.md`)."**

#### Live Verification Command
```bash
git ls-files
```

#### Expected File Inventory Table

| File / Path | Purpose & Description |
|---|---|
| `docker-compose.yml` | Multi-container composition defining services, networks, volumes, environment bindings, and restart policies. |
| `Makefile` | Command-line management interface providing targets: `up`, `down`, `build`, `ps`, `logs`, `clean`, `rebuild`, `restart`, `test`, `test-py`. |
| `README.md` | Primary documentation containing architecture diagrams, prerequisites, configuration guides, API examples, and ADRs. |
| `openapi.yaml` | OpenAPI 3.0 specification documenting all endpoints, schemas, request bodies, and responses. |
| `srcs/api-gateway-app/Dockerfile` | Alpine 3.23 Dockerfile for the API Gateway reverse proxy and RabbitMQ publisher. |
| `srcs/inventory-app/Dockerfile` | Alpine 3.23 Dockerfile for the movie catalogue CRUD REST microservice. |
| `srcs/billing-app/Dockerfile` | Alpine 3.23 Dockerfile for the asynchronous order worker and queue consumer. |
| `srcs/rabbit-queue/Dockerfile` | Alpine 3.23 Dockerfile building the custom RabbitMQ message broker. |
| `srcs/inventory-database/Dockerfile` | Alpine 3.23 Dockerfile building PostgreSQL 17 for inventory data. |
| `srcs/billing-database/Dockerfile` | Alpine 3.23 Dockerfile building PostgreSQL 17 for billing data. |
| `postman/play-with-containers.postman_collection.json` | Postman test collection covering `/health`, `/api/movies/`, and `/api/billing/`. |
| `scripts/test_audit.sh` | Shell test script automating the entire audit checklist. |
| `scripts/test_api.py` | Python automated unit/integration test suite. |
| `.env.example` | Template demonstrating required environment variable keys with non-sensitive defaults. |
| `.gitignore` | Enforces exclusion of `.env`, python caches, and temporary runtime artifacts. |

---

### 2.2 Environment File (`.env`) Git Exclusion

> **Audit Checklist Item**:  
> *"Was the `.env` file excluded from the git files?"*

#### Direct Oral Answer
> **"Yes. The `.env` file is explicitly ignored in `.gitignore` and has never been staged or committed to Git history. A sanitized template `.env.example` is committed instead to allow users to generate their local `.env`."**

#### Live Verification Commands
```bash
# 1. Confirm .env is NOT in the git index (must produce no output)
git ls-files | grep -E '^\.env$'

# 2. Confirm .gitignore contains .env
grep -E '^\.env$' .gitignore

# 3. Confirm .env.example exists as a template
ls -l .env.example
```

---

### 2.3 Credential & Secret Hygiene

> **Audit Checklist Item**:  
> *"Are all pushed files in the repo clean of any credentials or passwords?"*

#### Direct Oral Answer
> **"Yes. No secrets or production passwords are hardcoded in application source code, Dockerfiles, or `docker-compose.yml`. Docker Compose substitutes environment variables at runtime using `${VAR}` interpolation from the local `.env`. Dockerfiles only configure placeholders and runtime arguments."**

#### Live Verification Command
```bash
# Scan all tracked repository files for sensitive keyword assignments
git grep -iE 'password\s*=|secret\s*=' -- ':!.env.example'
```

*Expected output*: No hardcoded secret values found in source code or compose files. Only `.env.example` displays placeholder documentation values (e.g. `inventory_secret_pass`).

---

### 2.4 README Completeness Review

> **Audit Checklist Item**:  
> *"Open and read the `README.md` file provided by the student. Does the `README.md` file contain all the required information to run and manage the solution (prerequisites, configuration, setup, usage, etc)?"*

#### Direct Oral Answer
> **"Yes. The `README.md` provides an end-to-end operational manual divided into structured sections: Architecture Overview with ASCII topology, Microservices Summary table, Prerequisites, Configuration and `.env` reference table, Usage and Makefile targets, comprehensive API Walkthrough with curl examples and expected JSON responses, Architectural Decision Records (ADRs), and CRUD-Master Lineage crosswalk."**

#### Key Sections in `README.md`
- **Section 1**: Architecture diagram showing gateway, internal network, databases, and message broker.
- **Section 3**: Prerequisites (Linux, Docker 24+, Docker Compose v2, Make, curl).
- **Section 4**: Configuration guide (`cp .env.example .env` and variable documentation).
- **Section 5**: Complete lifecycle commands (`make up`, `make down`, `make clean`, `make rebuild`, `make test`).
- **Section 6**: Verifiable API examples with input payloads and status codes.
- **Section 7**: Architectural Decision Records (ADRs) explaining technical choices.

---

### 2.5 Architectural Conformity

> **Audit Checklist Item**:  
> *"Check the student infrastructure. Does the student architecture reflect the infrastructure enforced by the subject?"*

#### Direct Oral Answer
> **"Yes. The architecture strictly complies with all 6 required services: an inventory SQL database, a billing SQL database, an inventory app, a billing worker app, a RabbitMQ queue broker, and an API Gateway. Only the API Gateway is exposed to the host network (port 3000); all other services communicate exclusively over a private bridge network."**

#### Architectural Topology
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

---

## 3. Theory Questions & Comprehensive Deep Dives

---

### 3.1 What is a Container vs a Virtual Machine?

> **Audit Core Question**:  
> *"What are containers and what are their advantages? What is the difference between containers and virtual machines?"*

#### Direct Oral Answer
> **"A container is an isolated, lightweight user-space process running directly on the host Linux kernel, bundled with its complete filesystem and runtime dependencies. A Virtual Machine (VM), by contrast, virtualizes physical hardware via a hypervisor and runs an entire Guest Operating System with its own separate kernel."**

#### Technical Comparison Deep Dive

```
+------------------------------------+    +------------------------------------+
|         VIRTUAL MACHINES           |    |             CONTAINERS             |
|                                    |    |                                    |
|  +--------------+  +------------+  |    |  +------------+  +--------------+  |
|  |    App A     |  |   App B    |  |    |  |   App A    |  |    App B     |  |
|  |  (User Space)|  | (User Space|  |    |  | (User Space|  | (User Space) |  |
|  +--------------+  +------------+  |    |  +------------+  +--------------+  |
|  |   Guest OS   |  |  Guest OS  |  |    |  | Container Runtime (containerd) |  |
|  | (Kernel+Lib) |  | (Kernel+Lib|  |    +--+--------------------------------+--+
|  +--------------+  +------------+  |    |         Host Linux Kernel          |
|  | Hypervisor (Type 1 or Type 2)   |    |    (Shared cgroups + namespaces)   |
+--+---------------------------------+    +------------------------------------+
|           Host Hardware            |    |           Host Hardware            |
+------------------------------------+    +------------------------------------+
```

| Dimension | Virtual Machine (VM) | Linux Container |
|---|---|---|
| **Virtualization Level** | **Hardware-level**: Emulates CPU, RAM, NIC, BIOS via Hypervisor (KVM, ESXi, Xen). | **Operating System-level**: Virtualizes user-space using Linux kernel primitives. |
| **Kernel Model** | Each VM boots an independent, isolated **Guest OS Kernel**. | All containers share the **single Host Linux Kernel**. |
| **Startup Latency** | Minutes (BIOS POST, kernel boot, systemd initialization). | Milliseconds (spawning an ordinary Linux process). |
| **Disk & Memory Footprint** | Gigabytes per VM (redundant OS files, kernel memory). | Megabytes per image (only application binaries and shared libs). |
| **I/O Performance** | Emulated device drivers incur hypervisor trap overhead. | **Native bare-metal performance** with zero translation overhead. |
| **Density** | Low density (tens of VMs per high-end server). | High density (hundreds to thousands of containers per host). |
| **Isolation Barrier** | Hardware-enforced isolation (VT-x / AMD-V CPU rings). | Process-level isolation via kernel namespaces and cgroups. |

#### Key Advantages of Containers
1. **Portability ("Build Once, Run Anywhere")**: Eliminates the "works on my machine" syndrome because the image freezes the entire dependency tree.
2. **Resource Efficiency & High Density**: No hypervisor overhead or redundant guest OS kernels eating RAM.
3. **Immutability & Rapid Deployment**: Versioned images ensure declarative infrastructure without configuration drift.

---

### 3.2 Docker Engine & Container Runtime Internals (Namespaces & cgroups)

> **Audit Core Question**:  
> *"What is Docker and what is it used for? How does the container runtime work?"*

#### Direct Oral Answer
> **"Docker is an open-source platform that automates packaging, distributing, and running applications in containers. Under the hood, Docker delegates container creation to `containerd` and `runc`, which configure the Linux kernel using Namespaces for process isolation and Control Groups (cgroups) for resource constraints."**

#### Docker Runtime Architecture
```
[ Docker CLI ]  (Client)
      │  REST API / Unix Socket (/var/run/docker.sock)
      ▼
[ dockerd ]     (Daemon: manages images, networks, volumes)
      │  gRPC API
      ▼
[ containerd ]  (OCI supervisor: image pull, snapshotting)
      │
      ▼
[ runc ]        (OCI reference runtime: invokes clone/setns/unshare syscalls)
      │
      ▼
[ Linux Process ] (Sandboxed in private namespaces & bounded by cgroups)
```

#### Linux Kernel Primitives Explained

##### 1. Kernel Namespaces (Isolation: "What a process can SEE")
Linux namespaces wrap global system resources into isolated abstractions:
- **PID Namespace**: Isolates process IDs. The container's entrypoint process sees itself as `PID 1`, while on the host it is an ordinary unprivileged process (e.g. `PID 48291`).
- **NET Namespace**: Isolates network devices, routing tables, port bindings, and iptables rules. Each container receives its own loopback interface (`lo`) and virtual ethernet interface (`eth0`).
- **MNT (Mount) Namespace**: Isolates filesystem mount points. The container sees only its OverlayFS rootfs without access to the host disk.
- **IPC Namespace**: Isolates Inter-Process Communication resources (System V IPC, POSIX message queues, shared memory).
- **UTS Namespace**: Isolates the system hostname and domain name.
- **USER Namespace**: Maps UIDs and GIDs between container and host (e.g. UID 0 inside maps to UID 10000 on host).
- **CGROUP Namespace**: Masks the host's full cgroup hierarchy.

##### 2. Control Groups (cgroups) (Resource Limits: "What a process can USE")
Control groups enforce hard boundaries and metering on physical hardware:
- **Memory (`memory.max`, `memory.oom_control`)**: Limits RAM consumption; triggers the kernel OOM Killer if exceeded.
- **CPU (`cpu.weight`, `cpu.max`)**: Restricts CPU quota and bandwidth shares via CFS (Completely Fair Scheduler).
- **PIDs (`pids.max`)**: Caps the maximum number of child processes to prevent `fork bomb` denial of service.
- **Block I/O (`io.weight`, `io.max`)**: Throttles read/write disk throughput and IOPS.

##### 3. The PID 1 Init Problem & Signal Handling
Inside a container, your application is **PID 1**. PID 1 has unique kernel semantics:
- **Default Signal Ignorance**: The Linux kernel ignores signals (such as `SIGTERM`) for PID 1 unless the process has installed an explicit signal handler.
- **Exec-Form vs Shell-Form**:
  - `CMD ["python3", "server.py"]` (**Exec form**): Spawns `python3` directly as PID 1. Signals from `docker stop` (`SIGTERM`) reach the Python process directly, allowing graceful shutdown.
  - `CMD python3 server.py` (**Shell form**): Spawns `/bin/sh -c "python3 server.py"`. `/bin/sh` becomes PID 1 and **does not forward signals** to child processes. When `docker stop` is run, the container hangs for 10 seconds until Docker issues a forceful `SIGKILL`.
- **Zombie Process Reaping**: When child processes terminate, PID 1 must call `wait()` or `waitpid()` to reap their exit status; otherwise, defunct processes leak kernel memory.

---

### 3.3 Dockerfiles, Layer Caching & Base Image Discipline

> **Audit Core Question**:  
> *"What is a Dockerfile? Explain the instructions. Why use penultimate stable Alpine images instead of latest?"*

#### Direct Oral Answer
> **"A Dockerfile is a declarative text script containing ordered instructions that Docker executes to construct an immutable container image. Each instruction creates a read-only filesystem layer. We optimize layer caching by placing infrequently changing dependencies first and use `alpine:3.23`—the penultimate stable release—to guarantee deterministic package versions, small image footprints, and zero dependency on unvetted Docker Hub images."**

#### Dockerfile Instructions Deep Dive

| Instruction | Execution Timing | Filesystem Layer Created? | Description & Project Usage |
|---|---|---|---|
| `FROM` | Build time | Yes (Base layer) | Initializes build stage and sets parent image: `FROM alpine:3.23`. |
| `WORKDIR` | Build time | Metadata | Sets execution directory inside container: `WORKDIR /usr/src/app`. |
| `ENV` | Build & Runtime | Metadata | Sets persistent environment variables: `ENV PYTHONUNBUFFERED=1`. |
| `RUN` | Build time | **Yes (Delta layer)** | Executes shell command inside temporary container and commits filesystem changes (e.g. `apk add --no-cache python3`). |
| `COPY` | Build time | **Yes (Data layer)** | Copies files from host build context into image: `COPY requirements.txt .`. |
| `EXPOSE` | Runtime info | Metadata | **Documentation only**. Informs operators of listening ports (does **not** open host ports). |
| `HEALTHCHECK` | Runtime | Metadata | Defines periodic probe command executed by daemon: `HEALTHCHECK CMD pg_isready`. |
| `CMD` | Container startup| Metadata | Provides default arguments or executable command in exec form: `CMD ["python3", "server.py"]`. |

#### OverlayFS & Image Layer Mechanics
Docker images utilize **OverlayFS** (a union filesystem) composed of:
1. **`lowerdir`**: Stack of read-only image layers.
2. **`upperdir`**: A single thin, writable container layer.
3. **`merged`**: Unified virtual filesystem presented to the container.

When a container modifies an existing file from an image layer, OverlayFS performs a **Copy-on-Write (CoW)** operation: it duplicates the file from `lowerdir` up into `upperdir` before writing. The underlying image layers remain completely immutable.

```
┌────────────────────────────────────────────────────────┐
│ Writable Container Layer (upperdir: modifications)     │  <-- Ephemeral (Lost on docker rm)
├────────────────────────────────────────────────────────┤
│ Layer 4: Application Code (COPY . .)                   │
├────────────────────────────────────────────────────────┤
│ Layer 3: Python Packages (RUN pip install ...)         │  <-- Read-only Image Layers
├────────────────────────────────────────────────────────┤
│ Layer 2: System Packages (RUN apk add ...)             │      (lowerdir: cached & shared)
├────────────────────────────────────────────────────────┤
│ Layer 1: Base Operating System (FROM alpine:3.23)      │
└────────────────────────────────────────────────────────┘
```

#### Layer Caching Strategy: Why Cache Ordering Matters
Docker reuses previously built layers if the instruction and its inputs have not changed. An invalidation at layer $N$ forces Docker to rebuild layer $N$ and **all subsequent layers**.

**Optimal Dockerfile Ordering Pattern**:
```dockerfile
# 1. System packages (change very rarely) -> CACHED
RUN apk add --no-cache python3 py3-pip

# 2. Dependency manifests (change occasionally) -> CACHED
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Application source code (changes frequently) -> ONLY THIS REBUILDS
COPY . .
```
If `COPY . .` were placed *before* `pip install`, any single-line change in application code would invalidate the cache and force a complete re-download and compilation of all dependencies on every build.

#### Why Penultimate Stable Alpine (`alpine:3.23`) vs `latest`?
1. **Strict Subject Requirement**: The subject specification explicitly mandates creating containers from the *penultimate stable version* of Alpine or Debian. Alpine 3.24 is the latest stable version; Alpine 3.23 is the penultimate release.
2. **Deterministic Reproducibility**: Using `:latest` represents a mutable floating pointer. A build today might succeed, while a build next month pulls updated package manifests that break backwards compatibility.
3. **Small Footprint & Minimal Attack Surface**: The base Alpine image is only ~5 MB and runs on `musl libc` without bloated desktop or systemd daemons, dramatically reducing CVE vulnerabilities.
4. **No Docker Hub Pre-Built Application Images**: We do not use `postgres:latest`, `node:latest`, or `rabbitmq:latest`. All 6 images compile and configure their software from clean, auditable Alpine 3.23 repositories.

---

### 3.4 Docker Storage & Named Volume Persistence

> **Audit Core Question**:  
> *"What is a Docker volume and why do we use Docker volumes?"*

#### Direct Oral Answer
> **"A Docker volume is a persistent storage directory managed entirely by the Docker Engine on the host filesystem outside the container's Union File System. We use Docker volumes because container filesystems are ephemeral; volumes preserve stateful data across container lifecycles, deliver native host disk I/O performance by bypassing Copy-on-Write overhead, and allow secure data sharing between containers."**

#### Storage Comparison

| Storage Mechanism | Host Location | Managed By | Lifecycle | Best Used For |
|---|---|---|---|---|
| **Named Volume** | `/var/lib/docker/volumes/<name>/_data` | Docker Engine | **Persistent** (survives `docker rm` and container upgrades) | Production databases (`postgresql/data`), stateful logs. |
| **Bind Mount** | Arbitrary host path (e.g. `/home/user/app`) | User / Host OS | Depends on host filesystem | Live source-code reloading in local development. |
| **tmpfs Mount** | Host RAM (System memory) | Host Kernel | **Ephemeral** (lost on container stop) | Sensitive cryptographic keys, high-speed temporary buffers. |
| **Container Layer** | OverlayFS upperdir | Docker Engine | **Ephemeral** (destroyed on `docker rm`) | Ephemeral scratch files only. |

#### Why Databases Require Named Volumes
1. **Zero Data Loss**: When `docker compose down` or `docker compose up --build` updates a database container to a new image, the container is destroyed and recreated. Without a volume, the entire database cluster is erased.
2. **I/O Performance**: Writing high-frequency transactional WAL logs and tables directly to native host storage bypasses the OverlayFS copy-on-write driver, preventing disk bottlenecking.

In our project, three named volumes are defined with exact bare names via top-level `name:` attributes:
- `inventory-database`: Persists `/var/lib/postgresql/data` for movie inventory.
- `billing-database`: Persists `/var/lib/postgresql/data` for customer orders.
- `api-gateway-app`: Persists `/usr/src/logs` for rotating access logs.

---

### 3.5 Docker Networking, DNS Resolution & Port Publishing

> **Audit Core Question**:  
> *"What is a Docker network and why do we use it? Explain bridge networks, DNS resolution, and port forwarding vs expose."*

#### Direct Oral Answer
> **"A Docker network is a software-defined virtual network providing private connectivity between containers. We use user-defined bridge networks because they provide automatic internal DNS service discovery—allowing containers to address each other by service name—and enforce strict perimeter isolation so internal databases and brokers are invisible to the outside host."**

#### How Docker Bridge Networking Works
```
+-----------------------------------------------------------------------------------+
| Host System (Physical Network Stack)                                              |
|                                                                                   |
|  iptables DNAT: Host Port 3000 ──► Container Port 3000 (api-gateway-app)         |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | User-Defined Bridge: play-with-containers-network (Subnet 172.x.x.x/16)     |  |
|  |                                                                             |  |
|  |   [ Embedded Docker DNS Server: 127.0.0.11 ]                                |  |
|  |       ├── "inventory-app"     ──► 172.x.0.4                                 |  |
|  |       ├── "inventory-database"──► 172.x.0.2                                 |  |
|  |       ├── "rabbit-queue"      ──► 172.x.0.5                                 |  |
|  |       └── "billing-database"  ──► 172.x.0.3                                 |  |
|  |                                                                             |  |
|  |   +-------------------+     veth pair     +-------------------+             |  |
|  |   |  api-gateway-app  |◄─────────────────►|   inventory-app   |             |  |
|  |   +-------------------+                   +-------------------+             |  |
|  |             ▲                                       ▲                       |  |
|  |             │ veth                                  │ veth                  |  |
|  |             ▼                                       ▼                       |  |
|  |   +-------------------+                   +-------------------+             |  |
|  |   |   rabbit-queue    |◄─────────────────►|    billing-app    |             |  |
|  |   +-------------------+                   +-------------------+             |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

1. **Virtual Ethernet Pairs (`veth`)**: Each container gets a virtual interface (`eth0`) in its private network namespace. Its peer end is plugged into the Linux bridge (`pwc-network`) on the host.
2. **Embedded DNS Resolver (`127.0.0.11`)**: User-defined bridge networks run an internal DNS server. When `api-gateway-app` connects to `http://inventory-app:8080`, Docker DNS automatically resolves the name `inventory-app` to its dynamic container IP. (The default legacy bridge lacks this capability and required hardcoded `--link` flags).
3. **Port Forwarding (`ports:`) vs Port Documentation (`expose:`)**:
   - `ports: ["3000:3000"]`: **Publishes** container port 3000 to the host network by configuring Linux `iptables` DNAT (Destination NAT) rules. Traffic arriving on host interface port 3000 is forwarded into the container.
   - `expose: [5432]`: **Metadata only**. It documents intended ports for inter-container communication on the bridge network. It does **not** create host iptables rules. Internal ports are completely unreachable from outside the host.

---

### 3.6 Docker Compose & Multi-Container Orchestration

> **Audit Core Question**:  
> *"What is Docker Compose and how does multi-container orchestration work?"*

#### Direct Oral Answer
> **"Docker Compose is a declarative tool for defining and running multi-container Docker applications from a single YAML file. It coordinates service creation, shared networks, named volumes, environment injection, and startup sequencing via healthchecks and dependency trees."**

#### Key Compose Capabilities in this Stack
1. **Declarative State Reconciliation**: Running `docker compose up -d` inspects current system state against `docker-compose.yml`, builds missing images, and brings up containers in topological dependency order.
2. **Dependency Conditions (`depends_on`)**:
   - `condition: service_healthy`: Forces `inventory-app` and `billing-app` to wait until PostgreSQL has fully initialized and passed its `pg_isready` healthcheck before launching.
   - `condition: service_started`: Allows asynchronous services to launch once the target container process is spawned.
3. **Preventing Cold-Boot Deadlocks**: PostgreSQL takes several seconds to run its initial cluster creation (`initdb`). To prevent startup crashes, our Python applications include **exponential backoff and retry loops** for database and AMQP connections, ensuring zero race conditions during cold boot.

---

### 3.7 Microservices Architecture & Design Principles

> **Audit Core Question**:  
> *"What is a microservices architecture and why do we use it?"*

#### Direct Oral Answer
> **"A microservices architecture is a software engineering paradigm that decomposes an application into a collection of small, autonomous, loosely coupled services organized around specific business domains. Each microservice manages its own data persistence and communicates over standard network protocols like HTTP REST or AMQP."**

#### Architectural Comparison

| Dimension | Monolithic Architecture | Microservices Architecture (Our Project) |
|---|---|---|
| **Deployable Unit** | Single unified binary or archive. | 6 independent, containerized services. |
| **Database Ownership** | Single shared database for all tables. | **Database-per-Service**: `inventory-database` is strictly isolated from `billing-database`. |
| **Fault Blast Radius** | A memory leak or crash takes down the entire application. | **Fault Isolation**: If `billing-app` crashes, `inventory-app` and `api-gateway-app` continue functioning with zero degradation. |
| **Scalability** | Scale the entire monolith vertically or replicate everything. | **Targeted Horizontal Scaling**: We can scale worker consumers (`billing-app`) without spending resources on inventory. |
| **Technology Stack** | Locked into a single language/framework runtime. | Polyglot: Each service can use the optimal tool for its specific domain. |

---

### 3.8 Message Queues & RabbitMQ Fundamentals

> **Audit Core Question**:  
> *"What is a queue and what is it used for? What is RabbitMQ?"*

#### Direct Oral Answer
> **"A queue is a First-In-First-Out (FIFO) buffer used in message-oriented middleware for asynchronous inter-process communication. RabbitMQ is an enterprise message broker implementing the AMQP 0-9-1 standard. We use it for temporal decoupling—allowing orders to be accepted even when the billing service is offline—and load leveling to absorb traffic spikes without overwhelming databases."**

#### RabbitMQ AMQP 0-9-1 Messaging Topology
```
[ Producer: api-gateway-app ]
      │
      │  basic_publish(exchange='', routing_key='billing_queue', delivery_mode=2)
      ▼
[ Default Direct Exchange ]
      │
      │  Direct Routing
      ▼
[ Durable Queue: "billing_queue" ]  <-- Persisted in RabbitMQ storage
      │
      │  basic_consume(auto_ack=False, prefetch_count=1)
      ▼
[ Consumer Worker: billing-app ]
      │
      ├── 1. Parse JSON payload & coerce types
      ├── 2. INSERT INTO orders (user_id, number_of_items, total_amount)
      └── 3. channel.basic_ack(delivery_tag)
```

#### Key Reliability Mechanisms
1. **Temporal Decoupling**: The producer (`api-gateway-app`) does not need the consumer (`billing-app`) to be running. If the consumer is offline, the broker stores the message indefinitely until a worker connects.
2. **Durable Queues & Persistent Messages**:
   - `queue_declare(queue='billing_queue', durable=True)` ensures the queue configuration survives broker restarts.
   - `pika.BasicProperties(delivery_mode=2)` marks each message as persistent on disk.
3. **Manual Acknowledgments (`basic_ack`)**: We set `auto_ack=False`. The worker processes the order and commits the database transaction **before** sending an acknowledgment. If the worker crashes mid-processing, RabbitMQ automatically re-queues the message for another worker.
4. **Fair Dispatch (`basic_qos(prefetch_count=1)`)**: Instructs RabbitMQ not to give more than one message to a worker until that worker has acknowledged its previous message, preventing worker starvation or overload.

---

## 4. Architecture & Infrastructure Walkthrough

---

### 4.1 Booting the Stack (`docker compose up -d`)

> **Audit Step**:  
> Run the student infrastructure: `docker-compose up` (or `docker compose up -d`). Does the infrastructure start correctly?

#### Execution
```bash
make up
# Equivalent to: docker compose up --build -d
```

#### Verification Command
```bash
docker compose ps
```

#### Expected Terminal Output
```console
NAME                 IMAGE                COMMAND                  SERVICE              CREATED          STATUS                    PORTS
api-gateway-app      api-gateway-app      "python3 server.py"      api-gateway-app      10 seconds ago   Up 9 seconds (healthy)    0.0.0.0:3000->3000/tcp, :::3000->3000/tcp
billing-app          billing-app          "python3 server.py"      billing-app          10 seconds ago   Up 9 seconds              8080/tcp
billing-database     billing-database     "/usr/local/bin/init…"   billing-database     10 seconds ago   Up 9 seconds (healthy)    5432/tcp
inventory-app        inventory-app        "python3 server.py"      inventory-app        10 seconds ago   Up 9 seconds              8080/tcp
inventory-database   inventory-database   "/usr/local/bin/init…"   inventory-database   10 seconds ago   Up 9 seconds (healthy)    5432/tcp
rabbit-queue         rabbit-queue         "/usr/local/bin/entr…"   rabbit-queue         10 seconds ago   Up 9 seconds (healthy)    5672/tcp, 15672/tcp
```

---

### 4.2 Inspecting the 6 Containers & Restart Policies

> **Audit Step**:  
> Verify all 6 containers have image names matching service names and restart policy is `{on-failure 0}`.

#### 1. Image and Container Name Matching
```bash
for s in inventory-database billing-database inventory-app billing-app rabbit-queue api-gateway-app; do
  echo "$s -> image: $(docker inspect -f '{{.Config.Image}}' $s)"
done
```
*Expected Output*:
```console
inventory-database -> image: inventory-database
billing-database -> image: billing-database
inventory-app -> image: inventory-app
billing-app -> image: billing-app
rabbit-queue -> image: rabbit-queue
api-gateway-app -> image: api-gateway-app
```

#### 2. Restart Policy Inspection
```bash
for s in inventory-database billing-database inventory-app billing-app rabbit-queue api-gateway-app; do
  echo "$s -> restart policy: $(docker inspect -f '{{.HostConfig.RestartPolicy}}' $s)"
done
```
*Expected Output*:
```console
inventory-database -> restart policy: {on-failure 0}
billing-database -> restart policy: {on-failure 0}
inventory-app -> restart policy: {on-failure 0}
billing-app -> restart policy: {on-failure 0}
rabbit-queue -> restart policy: {on-failure 0}
api-gateway-app -> restart policy: {on-failure 0}
```

#### Why `restart: on-failure`?
The policy `{on-failure 0}` means the Docker daemon will automatically restart a container if it terminates with a non-zero exit status (crash or unexpected error), with zero indicating unlimited restart attempts. Crucially, if an operator explicitly stops a container (`docker stop`), its exit status is 0, so the daemon respects the command and does **not** restart it.

---

### 4.3 Verifying Named Volumes

> **Audit Step**:  
> Check the Docker volumes using `docker volume ls`.

#### Verification Command
```bash
docker volume ls
```

#### Expected Terminal Output
```console
DRIVER    VOLUME NAME
local     api-gateway-app
local     billing-database
local     inventory-database
```

#### Detailed Volume Mapping Inspection
```bash
# Verify volume mount destinations
docker inspect -f '{{ range .Mounts }}{{ .Name }} -> {{ .Destination }}{{ end }}' inventory-database
# Expected: inventory-database -> /var/lib/postgresql/data

docker inspect -f '{{ range .Mounts }}{{ .Name }} -> {{ .Destination }}{{ end }}' billing-database
# Expected: billing-database -> /var/lib/postgresql/data

docker inspect -f '{{ range .Mounts }}{{ .Name }} -> {{ .Destination }}{{ end }}' api-gateway-app
# Expected: api-gateway-app -> /usr/src/logs
```

---

### 4.4 Verifying Network Isolation & Host Ports

> **Audit Step**:  
> Check the solution network. Is the connection to `api-gateway-app` the only one exposed from outside of the Docker host?

#### 1. Inspect Host Port Publishing
```bash
docker ps --format '{{.Names}}: {{.Ports}}'
```
*Expected Output*:
```console
api-gateway-app: 0.0.0.0:3000->3000/tcp, :::3000->3000/tcp
billing-app: 8080/tcp
billing-database: 5432/tcp
inventory-app: 8080/tcp
inventory-database: 5432/tcp
rabbit-queue: 5672/tcp, 15672/tcp
```
Only `api-gateway-app` maps a host port (`3000->3000`). All other services list internal container ports without host bindings.

#### 2. Confirm Host Rejection on Internal Ports
```bash
# Gateway is reachable
curl -i http://localhost:3000/health
# HTTP/1.1 200 OK

# Direct connections to internal ports are refused
curl -s --connect-timeout 2 http://localhost:5432 || echo "Port 5432 connection refused (Isolated)"
curl -s --connect-timeout 2 http://localhost:8080 || echo "Port 8080 connection refused (Isolated)"
curl -s --connect-timeout 2 http://localhost:5672 || echo "Port 5672 connection refused (Isolated)"
```

#### 3. Confirm Internal Inter-Container Connectivity
```bash
# The gateway can reach the internal inventory-app via Docker bridge DNS
docker exec api-gateway-app python3 -c "import urllib.request; print(urllib.request.urlopen('http://inventory-app:8080/health').read().decode())"
# Expected: {"status":"healthy"}
```

---

### 4.5 Verifying Environment Configuration

Demonstrate that `.env` is loaded automatically by Compose and no passwords are leaked in the Git tree:

```bash
# Verify .env variables are actively used inside containers
docker exec inventory-database sh -c 'echo "User: $DB_USER, DB: $DB_NAME"'
# Expected: User: inventory_user, DB: inventory_db

docker exec billing-database sh -c 'echo "User: $DB_USER, DB: $DB_NAME"'
# Expected: User: billing_user, DB: billing_db
```

---

## 5. Endpoint Testing & Outage Resilience Scenarios

All client requests are directed to the API Gateway at `http://localhost:3000`.

---

### 5.1 Inventory Movie Catalogue Testing (`/api/movies`)

> **Audit Step**:  
> 1. Make a `POST` request to `http://[GATEWAY_IP]:[GATEWAY_PORT]/api/movies/` with payload `{"title": "A new movie", "description": "Very short description"}`. Confirm HTTP 200 response.  
> 2. Make a `GET` request to `http://[GATEWAY_IP]:[GATEWAY_PORT]/api/movies/`. Confirm HTTP 200 and body contains the added movie.

#### 1. POST `/api/movies/` (Add Movie)
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

#### 2. GET `/api/movies/` (List Movies)
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

#### 3. Additional CRUD Demonstrations
```bash
# Filter movies by title substring
curl -i "http://localhost:3000/api/movies?title=new"

# Get movie by ID
curl -i http://localhost:3000/api/movies/1

# Update movie title and description (PUT)
curl -i -X PUT http://localhost:3000/api/movies/1 \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated movie title",
    "description": "Updated movie description"
  }'

# Delete movie by ID (DELETE)
curl -i -X DELETE http://localhost:3000/api/movies/1
```

---

### 5.2 Billing Asynchronous Enqueueing (`/api/billing`)

> **Audit Step**:  
> Make a `POST` request to `http://[GATEWAY_IP]:[GATEWAY_PORT]/api/billing/` with payload `{"user_id": "20", "number_of_items": "99", "total_amount": "250"}`. Confirm HTTP 200 response.

#### Execution
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

Verify that the message was consumed by `billing-app` and stored in PostgreSQL:
```bash
docker exec billing-database psql -U billing_user -d billing_db -c "SELECT * FROM orders WHERE user_id = '20';"
```

---

### 5.3 Outage Resilience Simulation (Audit Core Scenario)

> **Audit Golden Test**:  
> 1. Stop the `billing-app` container.  
> 2. Confirm `billing-app` is stopped.  
> 3. Send a `POST` request to `/api/billing/` with payload `{"user_id": "22", "number_of_items": "10", "total_amount": "50"}`.  
> 4. Confirm the response was success code `200` even though `billing-app` is down.  
> 5. Restart `billing-app` and confirm the message was preserved and persisted.

#### Step 1: Stop the Worker Container
```bash
docker compose stop billing-app
# or: docker stop billing-app
```

#### Step 2: Confirm Container is Stopped
```bash
docker ps -a --filter name=billing-app
# Inspect status
docker inspect -f '{{.State.Running}}' billing-app
```
*Expected Output*: `false` (State: `Exited`).

#### Step 3: Submit Order While Worker is Down
```bash
curl -i -X POST http://localhost:3000/api/billing/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "22",
    "number_of_items": "10",
    "total_amount": "50"
  }'
```

**Expected Output**: `HTTP/1.1 200 OK`
```json
{
  "message": "{\"user_id\": \"22\", \"number_of_items\": \"10\", \"total_amount\": \"50\"} sent"
}
```

#### Step 4: The Oral Explanation of Why This Succeeded
> **"The API Gateway does not write directly to the database. Instead, it publishes the order message to RabbitMQ. Because the queue is declared durable (`durable=True`) and messages are published with persistence (`delivery_mode=2`), RabbitMQ safely holds the order in its buffer. The client receives an immediate HTTP 200 OK confirmation."**

#### Step 5: Restart the Worker
```bash
docker compose start billing-app
# or: docker start billing-app
```

#### Step 6: Verify Consumed Order in the Database
Wait 1–2 seconds for the worker to reconnect and consume the buffered message:
```bash
docker exec billing-database psql -U billing_user -d billing_db \
  -c "SELECT id, user_id, number_of_items, total_amount, created_at FROM orders WHERE user_id = '22';"
```

*Expected Terminal Output*:
```console
 id | user_id | number_of_items | total_amount |         created_at         
----+---------+-----------------+--------------+----------------------------
  2 | 22      |              10 |           50 | 2026-09-12 14:40:12.184912
(1 row)
```

**Conclusion**: Zero data loss. The message survived complete service downtime and was processed seamlessly upon worker revival.

---

## 6. Bonus Defense & Architectural Excellence

> **Audit Bonus Questions**:  
> 1. *"+Did the student use his/her own `crud-master` solution?"*  
> 2. *"+Did the student add any optional bonus?"*  
> 3. *"+Is this project an outstanding project?"*

---

### 6.1 Lineage from `crud-master` in Python

Our microservices architecture inherits and elevates the principles from our previous `crud-master-py` project:

| Feature / Architectural Pattern | Baseline `crud-master-py` | Our Production Solution (`play-with-containers`) |
|---|---|---|
| **Base Images** | Heavy `python:3.12` Docker Hub images | Custom, auditable `alpine:3.23` + system packages |
| **WSGI Web Server** | Development server (`app.run()`) | **Waitress**: Multi-threaded production WSGI server |
| **Database Binding** | Localhost hardcoded connections | Dynamic container DNS discovery via environment variables |
| **HTTP Response Codes** | POST returned `201 Created` | Returns `200 OK` strictly conforming to audit criteria |
| **Failure Recovery** | Default `restart: no` | `restart: on-failure` across all 6 services |
| **Startup Coordination** | Prone to cold-boot race conditions | `service_healthy` database gates + exponential retry loops |
| **Type Coercion Hygiene** | Weak type handling | Explicit type coercion (`int(number_of_items)`, `float(total_amount)`) preventing poison message crashes |

---

### 6.2 Makefile Automation Suite

A complete lifecycle automation interface is provided via `Makefile`:

```bash
make help        # Prints all targets and self-documentation
make up          # Builds and starts stack in detached mode
make down        # Stops containers and removes network (preserves volumes)
make clean       # Destroys containers, network, AND persistent volumes
make rebuild     # Full clean rebuild from scratch (--no-cache)
make ps          # Status of all containers
make logs        # Streams aggregate container logs
make test        # Executes automated bash audit verification suite
make test-py     # Executes automated Python test suite
make config      # Validates docker-compose.yml syntax
make lint        # Lints all Dockerfiles using Hadolint
```

---

### 6.3 Interactive OpenAPI 3.0 / Swagger UI

The API Gateway hosts interactive documentation:
- **Web UI**: Navigate to `http://localhost:3000/api/docs` or `http://localhost:3000/docs`.
- **Raw OpenAPI Specification**: Available at `http://localhost:3000/openapi.yaml`.

This allows evaluators to interactively inspect schema contracts and execute queries directly from their browser.

---

### 6.4 Automated E2E Test Suites

Two standalone test suites automate verification without requiring Postman:
1. **`scripts/test_audit.sh`** (`make test`):
   - Validates all 6 image names.
   - Asserts `{on-failure 0}` restart policies.
   - Asserts exact named volumes.
   - Tests host port isolation (asserting ports 5432, 8080, 5672 refuse external connections).
   - Executes live Movie CRUD assertions.
   - Executes the automated `billing-app` stop, POST during outage, restart, and PostgreSQL query check.
2. **`scripts/test_api.py`** (`make test-py`):
   - Standard Python `unittest` suite testing payload validation, type coercion logic, and HTTP endpoint contracts.

---

### 6.5 Dual-Stream Logging & Hardened Defaults

- **Dual-Stream Logging**: The API Gateway outputs log events simultaneously to `stdout` (for `docker compose logs`) and to a persistent rotating log file at `/usr/src/logs/gateway.log` on the named volume `api-gateway-app`.
- **Production WSGI Server**: Uses Waitress instead of the single-threaded Flask development server, guaranteeing concurrent request handling without thread starvation.
- **Strict Network Segmentation**: Zero ports are published other than ingress port 3000.

---

## 7. Quick Command Reference for the Oral Audit

| Audit Checklist Step | Verification Command to Run | Expected Output |
|---|---|---|
| **Check git cleanliness** | `git status` | `nothing to commit, working tree clean` |
| **Verify `.env` excluded** | `git ls-files \| grep '^\.env$'` | *(Empty output - not tracked)* |
| **Verify no passwords committed** | `git grep -iE 'password\s*=' -- ':!.env.example'` | *(Empty output - no hardcoded secrets)* |
| **Start infrastructure** | `docker compose up -d` | All 6 services start successfully |
| **Check all 6 containers** | `docker compose ps` | 6 containers `Up` or `healthy` |
| **Check container restart policy** | `docker inspect -f "{{ .HostConfig.RestartPolicy }}" <name>` | `{on-failure 0}` across all containers |
| **Check named volumes** | `docker volume ls` | `inventory-database`, `billing-database`, `api-gateway-app` |
| **Check network isolation** | `docker ps --format '{{.Names}}: {{.Ports}}'` | Only `api-gateway-app` has `3000->3000` |
| **Check internal port isolation** | `curl -s --connect-timeout 2 http://localhost:5432` | *(Connection refused)* |
| **POST `/api/movies/`** | `curl -i -X POST http://localhost:3000/api/movies/ -H "Content-Type: application/json" -d '{"title":"A new movie","description":"Very short description"}'` | `HTTP/1.1 200 OK` + JSON body with id |
| **GET `/api/movies/`** | `curl -i http://localhost:3000/api/movies/` | `HTTP/1.1 200 OK` + JSON listing movie |
| **POST `/api/billing/`** | `curl -i -X POST http://localhost:3000/api/billing/ -H "Content-Type: application/json" -d '{"user_id":"20","number_of_items":"99","total_amount":"250"}'` | `HTTP/1.1 200 OK` |
| **Stop billing worker** | `docker stop billing-app` | `billing-app` stops (Exit 0) |
| **Verify worker stopped** | `docker inspect -f '{{.State.Running}}' billing-app` | `false` |
| **POST `/api/billing/` during outage** | `curl -i -X POST http://localhost:3000/api/billing/ -H "Content-Type: application/json" -d '{"user_id":"22","number_of_items":"10","total_amount":"50"}'` | `HTTP/1.1 200 OK` (Buffered in RabbitMQ) |
| **Restart billing worker** | `docker start billing-app` | `billing-app` restarts and reconnects |
| **Verify buffered order processed** | `docker exec billing-database psql -U billing_user -d billing_db -c "SELECT * FROM orders WHERE user_id = '22';"` | Row with `user_id = 22` appears |
| **Run complete automated audit suite** | `make test` | `ALL AUDIT CHECKS PASSED!` |

---

*Authored by the Audit Preparation Specialist for play-with-containers.*
