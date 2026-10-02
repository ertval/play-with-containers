# Theory Study Guide — Containers, Docker & Microservices

> **Purpose**: Generalized, textbook-style reference for the conceptual material behind the
> play-with-containers project. This guide explains the *theory* with examples, independent of
> this specific implementation. For the audit itself — every checklist question, verified
> commands, expected outputs, and project-specific answers — see
> [`docs/audit-preparation.md`](./audit-preparation.md).

---

## Table of Contents

1. [Containerization Fundamentals](#1-containerization-fundamentals)
2. [Containers vs Virtual Machines](#2-containers-vs-virtual-machines)
3. [Docker: Architecture & Components](#3-docker-architecture--components)
4. [Images, Layers & the Build Cache](#4-images-layers--the-build-cache)
5. [Dockerfiles & Instructions](#5-dockerfiles--instructions)
6. [Container Runtime Internals: PID 1, Signals, Namespaces, cgroups](#6-container-runtime-internals-pid-1-signals-namespaces-cgroups)
7. [Storage: Volumes vs Bind Mounts vs Container FS](#7-storage-volumes-vs-bind-mounts-vs-container-fs)
8. [Networking: Bridges, Service Discovery, Port Publishing](#8-networking-bridges-service-discovery-port-publishing)
9. [Orchestration with Docker Compose](#9-orchestration-with-docker-compose)
10. [Microservices Architecture](#10-microservices-architecture)
11. [Message Queues & RabbitMQ / AMQP](#11-message-queues--rabbitmq--amqp)
12. [Reliability: Healthchecks & Restart Policies](#12-reliability-healthchecks--restart-policies)
13. [The Python/Alpine Stack: WSGI, Waitress, musl](#13-the-pythonalpine-stack-wsgi-waitress-musl)
14. [Security Considerations](#14-security-considerations)

---

## 1. Containerization Fundamentals

A **container** is a lightweight, standalone, executable unit of software that packages
application code together with all of its runtime dependencies — libraries, interpreters,
system tools, configuration — into an isolated process running on top of the host operating
system's kernel.

### Advantages

- **Portability** — "Build once, run anywhere." The same image runs identically on a
  developer laptop, a CI runner, and a production server. The image *is* the environment.
- **Density & efficiency** — Containers share the host kernel. There is no guest OS, no
  hypervisor tax: typical startup is sub-second and per-container overhead is measured in
  megabytes, not gigabytes.
- **Isolation** — Each container gets its own view of processes, network stack, filesystem
  mounts, and users (via kernel namespaces) and bounded resource usage (via cgroups).
- **Immutability** — Images are read-only templates. You never "patch" a running container;
  you build a new image and replace the container. This eliminates configuration drift.
- **Reproducibility** — The exact bits that passed tests are the bits that get deployed.

### Mental model

> A container is **a process**, not a machine. `docker run` is closer to `exec` than to
> booting a VM — it is a heavily sandboxed process with a private filesystem view.

---

## 2. Containers vs Virtual Machines

| Aspect | Virtual Machines | Containers |
|---|---|---|
| Virtualization level | Hardware-level (hypervisor) | OS-level (host kernel features) |
| Guest OS | Full OS per VM (GBs) | None — shares host kernel |
| Boot time | Minutes | Sub-second |
| Size | Gigabytes | Megabytes |
| Performance | Hypervisor overhead; near-native at best | Native bare-metal execution |
| Isolation strength | Strong (separate kernel) | Process-level (namespaces/cgroups, same kernel) |
| Density | Tens per host | Hundreds per host |
| Examples | KVM, VMware, Hyper-V, VirtualBox | Docker, Podman, containerd, LXC |

**Kernel sharing** is the key difference: all containers on a host run under *one* Linux
kernel. A container cannot run a different kernel (no Windows containers on a Linux host
without a Linux VM underneath), and a kernel panic affects every container.

**When to choose which**: VMs when you need strong tenant isolation, different kernels/OSes,
or full control of the OS; containers when you need fast, dense, reproducible application
deployment. In practice they are combined — containers often run *inside* cloud VMs.

---

## 3. Docker: Architecture & Components

Docker is an open-source platform for building, packaging, shipping, and running
applications in containers. It is a **client–daemon** architecture:

```
docker CLI ──REST/unix socket──► dockerd (daemon) ──► containerd ──► runc ──► container
                                      │
                                      ├── images (local cache)
                                      ├── volumes
                                      └── networks
```

- **`dockerd` (Docker daemon)** — manages images, containers, networks, volumes. Listens on
  a Unix socket (`/var/run/docker.sock`) or TCP endpoint for the client.
- **Docker CLI** — thin client sending REST requests to the daemon. `docker` commands are
  never executed "in" the target container directly; they are daemon API calls.
- **containerd / runc** — the lower-layer runtime that actually creates the container process
  using kernel primitives (the OCI runtime specification).
- **Images** — immutable build artifacts stored in a local cache and in **registries**
  (Docker Hub, GHCR, private registries).
- **Docker Compose** — declarative multi-container orchestration from a YAML file
  (see §9).

> **Daemonless alternative**: Podman runs rootless and daemonless (fork-exec model), using
> the same OCI images. Docker's daemon being a single privileged process (root-owned socket)
> is both its operational convenience and its main security criticism.

---

## 4. Images, Layers & the Build Cache

### What an image is

A Docker image is an **immutable, read-only template** consisting of stacked **layers**.
Each layer is a filesystem diff (tar archive of changed files) plus metadata. Stacking them
produces the final filesystem view via **OverlayFS**:

- `lowerdir` — the read-only image layers
- `upperdir` — the container's writable layer
- `merged` — the unified view the container sees

Files modified in a running container are **copied up** from a lower layer to the upper
layer (**copy-on-write**). Original layers are never mutated — this is why removing a file
created in a lower layer does not shrink the image.

### Why layers matter

1. **Sharing** — two images both starting `FROM alpine:3.23` share the base layers on disk
   and in RAM page cache. Ten Python services = one copy of Python.
2. **Build cache** — a layer is rebuilt only if its instruction *or its inputs* changed.
   Docker invalidates a layer and everything after it when the instruction's inputs change.
3. **Push/pull efficiency** — registries transfer only missing layers.

### Cache ordering best practice

Order instructions from *least* to *most frequently changing*:

```dockerfile
COPY requirements.txt .        # 1. dependencies manifest (rarely changes)
RUN pip install -r requirements.txt   # 2. → cached across source edits
COPY . .                       # 3. source code (changes constantly) — LAST
```

Placing `COPY . .` *before* `pip install` would reinstall all dependencies on every code
change — a classic build-performance bug.

### Multi-stage builds

A build stage compiles artifacts; a final stage copies only the artifacts into a clean,
minimal runtime image — keeping compilers and build tooling out of production:

```dockerfile
FROM golang:1.22 AS build
WORKDIR /src
COPY . .
RUN go build -o /out/app .

FROM alpine:3.20
COPY --from=build /out/app /usr/local/bin/app
ENTRYPOINT ["app"]
```

Benefits: drastically smaller images, fewer packages → smaller attack surface, no build
secrets leaking into the runtime image.

---

## 5. Dockerfiles & Instructions

A **Dockerfile** is a text file of ordered instructions the builder executes layer-by-layer
to produce an image.

| Instruction | Purpose | Layer created? |
|---|---|---|
| `FROM` | Sets the parent base image; starts a new build stage | yes |
| `WORKDIR` | Sets the working directory for subsequent instructions | metadata (dir created) |
| `RUN` | Executes a shell command at **build** time (installs packages, compiles) | yes |
| `COPY` | Copies files from the build context into the image | yes |
| `ADD` | Like COPY plus URL fetch / local tar auto-extraction (prefer COPY) | yes |
| `ENV` | Persistent environment variables (build **and** runtime) | metadata |
| `ARG` | Build-time-only variables (`docker build --build-arg`) | metadata |
| `EXPOSE` | *Documentation* of listening ports — does **not** publish anything | metadata |
| `HEALTHCHECK` | Command the daemon runs to judge container health | metadata |
| `USER` | User (and group) the image runs as (default: `root`) | metadata |
| `VOLUME` | Declares a mount point for ephemeral or externally managed volumes | metadata |
| `ENTRYPOINT` | The fixed executable the container runs | metadata |
| `CMD` | Default arguments for ENTRYPOINT, or the command if no ENTRYPOINT | metadata |

### ENTRYPOINT vs CMD — the exam trap

- `ENTRYPOINT` = the **what** (the binary); `CMD` = the **default arguments** (the how).
- `docker run <image> <args>` **replaces** CMD but is *appended* to ENTRYPOINT.

```dockerfile
ENTRYPOINT ["python3", "server.py"]
CMD ["--port", "3000"]
```

### Exec form vs shell form — why it matters

- Shell form: `CMD python3 server.py` → actually runs `/bin/sh -c "python3 server.py"`.
  The **shell becomes PID 1**; signals (SIGTERM from `docker stop`) go to the shell, which
  does not forward them. Result: 10 s grace period wasted, then SIGKILL.
- Exec form: `CMD ["python3", "server.py"]` → Python is PID 1 directly and receives signals.

**Always use exec form** for the final command in service images.

### `.dockerignore`

Excludes files from the build context (like `.gitignore` for builds): keeps `.git`,
`node_modules`, secrets, and tests out of images — smaller context uploads and no accidental
secret embedding.

---

## 6. Container Runtime Internals: PID 1, Signals, Namespaces, cgroups

### PID 1 and the init problem

Inside every container, your entrypoint process **is PID 1** in that PID namespace. PID 1
has two special kernel responsibilities ordinary processes don't:

1. **Signal default-disposition**: unhandled signals that would terminate a normal process
   are *ignored* by PID 1. If your app doesn't install a SIGTERM handler, `docker stop`
   will never terminate it gracefully — the daemon waits out the grace period and SIGKILLs.
2. **Zombie reaping**: orphaned children of dead processes are reparented to PID 1, which
   must `wait()` on them or they accumulate as zombies.

**Solutions**: install signal handlers (Python: `signal.signal`), or use an init process —
`docker run --init` (tini), `ENTRYPOINT ["/sbin/tini", "--", ...]`, or a real init like
s6/dumb-init.

### Signals & `docker stop`

`docker stop` sends **SIGTERM**, waits the grace period (default 10 s, `docker stop -t`),
then **SIGKILL** (which cannot be caught). Graceful shutdown = catch SIGTERM, stop
accepting work, finish/drain in-flight work, persist state, exit 0.

### Namespaces — the "what you can see"

| Namespace | Isolates |
|---|---|
| PID | process tree (container sees only its own processes) |
| NET | network stack: interfaces, routes, iptables, ports |
| MNT | mount points / filesystem view |
| UTS | hostname |
| IPC | System V / POSIX shared memory, semaphores |
| USER | UID/GID mappings (root inside ≠ root outside) — **only with user-namespace remapping enabled** (see below) |
| CGROUP | cgroup root view |

> **USER namespace caveat**: Docker supports the namespace but does **not** enable remapping
> by default — out of the box the container's `root` is the host's `root` (same UID 0), so
> "root inside ≠ root outside" is only true once you opt in via `--userns-remap` (daemon-level)
> or `--userns=host`/`--userns=keep-id` at run time. This is why dropping privileges with a
> non-root `USER` in the Dockerfile matters on a default daemon.

### cgroups — the "what you can use"

Control groups **limit and account** resources: `--memory`, `--cpus`, `--pids-limit`,
I/O and blkio weights. Namespaces restrict *visibility*; cgroups restrict *consumption*.
Two axes, one container.

> **cgroups v1 vs v2**: modern hosts use the unified v2 hierarchy (single tree, better
> pressure stall metrics, rootless-container support). Legacy tooling sometimes assumes v1.

---

## 7. Storage: Volumes vs Bind Mounts vs Container FS

A container's writable layer is **ephemeral** — destroyed with the container — and slow
(lives under OverlayFS copy-on-write). Anything that must outlive a container needs a mount:

| | Named volume | Bind mount | tmpfs |
|---|---|---|---|
| Managed by | Docker daemon | You (a host path) | Memory |
| Location | `/var/lib/docker/volumes/<name>/_data` | Anywhere on host | RAM |
| Portable | yes | no (host path dependent) | n/a |
| Survives `docker rm` | yes | yes | no |
| Typical use | DB data, app state | Dev source mounting, config injection | Secrets, scratch |

### Why databases use named volumes

1. **Persistence** — volume contents survive `docker rm` and image replacement.
2. **Performance** — writes go straight to the host FS, bypassing copy-on-write overhead.
3. **Backup/migration** — `docker run --rm -v <vol>:/data -v $PWD:/backup alpine tar czf /backup/db.tgz /data`.
4. **Sharing** — multiple containers can mount one volume (e.g., a log shipper).

`docker volume ls`, `docker volume inspect`, `docker volume rm` manage them. In Compose,
top-level `volumes:` with a `name:` key controls the literal name (bypassing the automatic
`<project>_` prefix).

---

## 8. Networking: Bridges, Service Discovery, Port Publishing

### Network types

- **bridge** (default `docker0`, or user-defined) — private internal network on one host;
  containers reach the outside world via NAT.
- **host** — no isolation; container shares the host network stack directly.
- **none** — no networking at all.
- **macvlan / overlay** — advanced: host LAN identity / multi-host clusters.

### User-defined bridges vs the default bridge

User-defined bridges provide **automatic DNS service discovery**: containers resolve each
other *by name* (`inventory-app:8080`, `rabbit-queue:5672`). The default legacy bridge only
offers legacy `--link` behavior — no embedded DNS. This single feature is why Compose
networks are user-defined.

### How it works under the hood

1. Each container gets a **veth pair** — one end in the container's NET namespace, the other
   plugged into the bridge.
2. The daemon runs an **embedded DNS server at 127.0.0.11** for container name resolution.
3. Outbound traffic is NAT'd (masqueraded) through the host.
4. Publishing a port (`-p 3000:3000`) installs an **iptables DNAT rule**: host:3000 →
   container:3000. `EXPOSE` in a Dockerfile and `expose:` in Compose are *documentation
   only* — nothing is reachable until `ports:`/`-p` publishes it.

### Security consequence

Un-published ports are not reachable **from outside the Docker host** **even though the
container port is open**. (Precisely: publishing is what exposes a port off the host — an
un-published port remains open on the bridge subnet and reachable *by container IP from the
Docker host itself*.) Perimeter control = publish as little as possible: one ingress (a
gateway), everything else internal.

---

## 9. Orchestration with Docker Compose

Compose manages the **full lifecycle of a multi-container stack** from one declarative YAML
file: `docker compose up / down / ps / logs / restart`.

Key semantics:

- **Project prefixing** — by default all resources are named `<project>_<service>`. Top-level
  `name:` keys for volumes and networks override the prefix to produce exact literal names.
- **`.env` interpolation** — `${VAR}` in the YAML is substituted from the `.env` file beside
  the compose file. This keeps secrets out of the YAML and out of version control.
- **Dependency ordering** — `depends_on` with conditions:
  - `service_started`: dependency's process has launched (no health guarantee).
  - `service_healthy`: dependency's HEALTHCHECK reports `healthy`.
  - `service_completed_successfully`: one-shot job exited 0.
- **`up` is declarative** — it creates, starts, and *reconciles*; re-running `up` applies
  only diffs.
- **Scope** — Compose is a **single-host** tool. It is not an orchestrator: no multi-node
  scheduling, self-healing rescheduling, or service mesh. That's the domain of Swarm /
  Kubernetes — a natural "what would you use at scale?" follow-up question.

---

## 10. Microservices Architecture

A **microservices architecture** structures an application as a suite of small, loosely
coupled, independently deployable services, each owning a single business capability and
its **private database**, communicating over lightweight protocols (HTTP/REST, AMQP).

Compare with the **monolith**: one deployable unit, one shared database, in-process calls
between modules. A monolith is simpler to develop/debug initially; microservices pay off at
organizational and scaling scale.

### Why we use microservices

- **Independent scalability** — scale only the hot service (e.g., replicate the billing
  worker) instead of the entire application.
- **Fault isolation** — a crash in one service degrades one capability, not the whole
  system; the rest keeps serving (with graceful degradation patterns like queues).
- **Independent deployment** — ship services on their own cadence; no big-bang releases.
- **Polyglot technology** — each service picks the stack fitting its domain.
- **Team autonomy** — small services map to small teams with clear ownership.

### The costs (know the trade-offs)

- Distributed-system complexity: network failures, partial failures, latency.
- Data consistency across services (eventual consistency, sagas/outbox patterns).
- Operational overhead: more deploy units, monitoring, tracing.
- Testing is harder (contract testing, integration environments).

### Supporting patterns

- **API Gateway** — single entry point that routes, aggregates, and shields internal
  services from external clients.
- **Database-per-service** — no shared tables; services integrate via APIs/events only.
- **Async messaging** — decouple producers from consumers in time (next section).

---

## 11. Message Queues & RabbitMQ / AMQP

### What a queue is

A queue is a **First-In-First-Out (FIFO) buffer** used in message-oriented middleware for
**asynchronous** inter-process communication. A *producer* sends messages; a *consumer*
receives them; a *broker* holds messages durably in between.

### What queues are for

- **Temporal decoupling** — producers and consumers don't need to be up at the same time.
  Work submitted while a consumer is down is buffered and processed when it returns.
- **Load leveling** — absorbs traffic spikes; consumers process at their own sustainable
  rate instead of being crushed by bursts.
- **Reliability** — durable messages persist until **acknowledged**; a consumer crash
  re-delivers, so work isn't lost.
- **Distribution** — one message can fan out to many consumers (or be load-balanced across
  a worker pool).

### RabbitMQ

RabbitMQ is an open-source **message broker** implementing **AMQP 0-9-1**. Producers never
send to queues directly — they publish to **exchanges**, which route messages to queues via
**binding keys / routing rules**:

```
producer ──publish──► exchange ──binding──► queue ──push──► consumer
```

Exchange types:
- **direct** — exact routing-key match
- **fanout** — broadcast to all bound queues
- **topic** — wildcard pattern match (`order.*.created`)
- **headers** — route on message headers

Core delivery concepts:

- **Durable queue / persistent messages** — survive a broker restart (`durable=True` on
  `queue_declare`, `delivery_mode=2` on messages; both required).
- **Acknowledgements (`basic_ack`)** — the broker re-queues a message delivered to a
  consumer that dies before acking. `auto_ack=True` = at-most-once (message lost on
  crash); manual ack = at-least-once (possible duplicates, usually handled with idempotency).
- **Prefetch / QoS (`basic_qos(prefetch_count=N)`)** — how many unacked messages a consumer
  may hold. `prefetch_count=1` gives **fair dispatch**: each worker gets the next message
  only after finishing the previous one, preventing one slow worker from hoarding work.
- **Dead-lettering** — rejected/nacked messages can be routed to a dead-letter queue for
  inspection instead of being lost.
- **Head-of-line blocking** — a single poison message that keeps crashing consumers blocks
  everything behind it; standard remedy is ack-and-discard (or dead-letter) bad messages so
  the queue keeps flowing.
- **Heartbeats** — keepalive frames detecting dead TCP connections between client and
  broker within network timeouts.

---

## 12. Reliability: Healthchecks & Restart Policies

### HEALTHCHECK

The daemon periodically runs the healthcheck command:

```dockerfile
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1
```

- `start_period` — failures during this window don't count against `retries` (boot grace).
- Exit 0 → healthy; non-zero → after `retries` consecutive failures → `unhealthy`.
- `CMD-SHELL` runs via `/bin/sh -c` (supports env expansion, pipes); plain `CMD` is exec-form
  (no shell). Compose needs `$$` to escape literal `$` for the shell inside `test:`.

**Critical gotcha**: `unhealthy` is *informational* — it does **not** trigger the restart
policy by itself. Its real power is as a gate: `depends_on: condition: service_healthy`
makes dependents wait for genuine readiness rather than mere process launch.

### Restart policies

| Policy | Restarts when | Notes |
|---|---|---|
| `no` (default) | never | |
| `always` | always on exit (even clean), and on daemon start | includes manually stopped containers after daemon restart |
| `unless-stopped` | like `always`, but stays stopped if you stopped it manually | survives reboots only if previously running |
| `on-failure[:N]` | only on **non-zero exit**; `N` = max retry count (`0`/unset = unlimited) | most common for services |

`on-failure` semantics: exit code 0 is *success* — no restart. Non-zero = failure → restart
(with exponential backoff). This is why audit checks read the literal value
`{on-failure 0}`: on-failure restarts, unlimited retries.

---

## 13. The Python/Alpine Stack: WSGI, Waitress, musl

### WSGI and production servers

WSGI is Python's standard interface between web servers and applications. Flask's built-in
server (`app.run()`) is the **Werkzeug development server**: single-process by default,
debugger-exposing, explicitly not for production.

Production WSGI servers: **Waitress** (pure Python, threaded, cross-platform — no C build
pain on musl/Alpine), **Gunicorn** (pre-fork, C-ext performance, needs glibc comfort),
uWSGI. Waitress's threading model suits I/O-bound workloads; the GIL is not a bottleneck
when threads spend their time waiting on sockets and databases.

### Alpine & musl libc

Alpine uses **musl** instead of glibc: smaller (~5 MB base image), simpler, but with
subtle differences — DNS resolution behavior, locale handling, and Python wheel
compatibility. Pip wheels built for glibc (`manylinux`) don't run on musl; wheels built for
musl (`musllinux`) do, or pip falls back to compiling from source (hence build tooling on
Alpine images). For pure-Python dependencies (Flask, Waitress, Pika) this is a non-issue —
one reason it's a clean fit for Alpine-based images.

### Alpine image discipline

Pin the minor version (`alpine:3.23`), optionally pin the digest for full reproducibility,
and always `apk add --no-cache` to avoid leaving the package index in the layer.

---

## 14. Security Considerations

Standard container hardening checklist (each item is a fair audit follow-up):

- **Don't run as root** — add `USER appuser` in the Dockerfile; root inside the container
  (absent user-namespace remapping) maps to root-level privileges against the host kernel
  surface.
- **Secrets hygiene** — secrets live only in `.env` (git-ignored), injected as environment
  variables; never hard-coded in Dockerfiles, YAML, or source; never committed.
- **Minimal base images** — Alpine/distroless reduce attack surface; pin versions/digests.
- **Capabilites & seccomp** — Docker applies a default seccomp profile and drops most Linux
  capabilities; tighten further with `--cap-drop=ALL`, read-only root filesystems
  (`--read-only`), and `--security-opt=no-new-privileges`.
- **Network perimeter** — publish the minimum set of ports; databases and brokers stay on
  the internal network only.
- **Image scanning** — scan images for CVEs (Trivy, Grype) in CI.

---

*End of theory guide — for project-specific audit Q&A, commands, and live-defense prep, see
[`audit-preparation.md`](./audit-preparation.md).*
