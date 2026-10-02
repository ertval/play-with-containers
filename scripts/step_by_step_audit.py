#!/usr/bin/env python3
"""Step-by-step audit runner for play-with-containers.

Mirrors crud-master's scripts/step_by_step_audit.py: it drives the audit
checklist command-by-command in a *visible* neighbouring pane (default: the
pane to the right of the caller, i.e. w4:p3 in the current workspace) so an
auditor can watch every check and its output in order.

Usage:
    python3 scripts/step_by_step_audit.py [PANE_ID]
    PANE_ID defaults to the herdr neighbour to the right, falling back to w4:p3.

Every step maps to docs/requirements/audit.md in order, with the verified
answers in docs/requirements/AUDIT_GUIDE.md and docs/audit-preparation.md.
Oral/theory questions have no command output and are therefore headers only;
everything executable is run live.
"""
import json
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Gateway address used by the audit (host side). Matches GATEWAY_HOST/PORT in .env.
BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000")


def resolve_default_pane() -> str:
    """Next pane to the right of the caller, else w4:p3 (this workspace layout)."""
    caller = os.environ.get("HERDR_PANE_ID", "")
    if caller:
        try:
            res = subprocess.run(
                ["herdr", "pane", "neighbor", "--direction", "right", "--pane", caller],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=10,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                nid = (
                    data.get("result", {})
                    .get("neighbor", {})
                    .get("neighbor_pane_id")
                )
                if nid:
                    return nid
        except Exception:
            pass
    return "w4:p3"


PANE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("STEP_AUDIT_PANE") or resolve_default_pane()

# (title, command) — titles carry the audit.md reference like crud-master does.
STEPS = [
    (
        "0. Workdir + ensure worker running (audit.md:31-46, start state)",
        'cd "$PWD" 2>/dev/null; cd /home/ertval/code/zone-modules/play-with-containers && pwd && docker start billing-app >/dev/null 2>&1; docker compose ps',
    ),
    (
        "1. Repo content: required files present (audit.md:7)",
        "git ls-files | sort | head -n 60; echo \"---\"; echo \"tracked files: $(git ls-files | wc -l)\"; git status --porcelain; echo \"(empty status above = clean)\"",
    ),
    (
        "2. .env excluded from git (audit.md:9)",
        "echo '$ git ls-files | grep -E \"^\\.env$\" (expect NO output)'; git ls-files | grep -E '^\\.env$'; echo \"exit=$? (1 = correctly untracked)\"; git check-ignore -v .env; echo '$ git log --all --oneline -- .env (expect NO output)'; git log --all --oneline -- .env; ls -l .env .env.example",
    ),
    (
        "3. No credentials in pushed files (audit.md:11)",
        "git grep -inE 'password|secret' -- . | head -n 40",
    ),
    (
        "4. No literal secret in images/compose (audit.md:66)",
        "echo '$ grep literals (expect NO output, exit=1)'; grep -nE 'inventory_secret_pass|billing_secret_pass|rabbit_secret_pass' srcs/*/Dockerfile docker-compose.yml; echo \"exit=$? (1 = clean, only \\${VAR} refs + .env.example placeholders)\"",
    ),
    (
        "5. README completeness (audit.md:25)",
        "grep -n '^#\\{1,3\\} ' README.md | head -n 40",
    ),
    (
        "6. Dockerfiles: one per service, Alpine base (audit.md:62-64)",
        "ls -1 srcs/*/Dockerfile; echo '---'; grep -H '^FROM' srcs/*/Dockerfile",
    ),
    (
        "7. Dockerfile instructions explained (audit.md:70-72, live file)",
        "grep -nE '^(FROM|WORKDIR|ENV|RUN|COPY|USER|EXPOSE|HEALTHCHECK|STOPSIGNAL|ENTRYPOINT|CMD)' srcs/api-gateway-app/Dockerfile",
    ),
    (
        "8. Containers + ports (audit.md:78-95)",
        "docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Ports}}\\t{{.Status}}'",
    ),
    (
        "9. Restart policy on-failure (audit.md:99-107)",
        "for s in inventory-database billing-database inventory-app billing-app rabbit-queue api-gateway-app; do echo -n \"$s: \"; docker inspect -f '{{.HostConfig.RestartPolicy}}' $s; done",
    ),
    (
        "10. Images: one per service, same name (audit.md:147-160)",
        "docker images --format 'table {{.Repository}}\\t{{.Tag}}\\t{{.Size}}' | head -n 20; echo '---'; for s in inventory-database billing-database inventory-app billing-app rabbit-queue api-gateway-app; do echo -n \"$s image=\"; docker inspect -f '{{.Config.Image}}' $s; done",
    ),
    (
        "11. Volumes: exact bare names (audit.md:111-117)",
        "docker volume ls --format '{{.Name}}' | grep -xE 'inventory-database|billing-database|api-gateway-app'; echo '--- (3 exact bare names above; Compose name: overrides suppress project prefix) ---'; for s in inventory-database billing-database api-gateway-app; do echo \"== $s ==\"; docker inspect -f '{{range .Mounts}}{{.Type}} {{.Name}} -> {{.Destination}}{{println}}{{end}}' $s; done",
    ),
    (
        "12. Gateway log volume in use (audit.md:121, api-gateway-app volume)",
        "docker exec api-gateway-app ls -l /usr/src/logs/; echo '---'; docker exec api-gateway-app tail -n 5 /usr/src/logs/gateway.log",
    ),
    (
        "13. Network: gateway is the ONLY published port (audit.md:136)",
        "docker ps --format '{{.Names}}: {{.Ports}}'; echo '--- authoritative check (docker port: empty = isolated, only gateway publishes) ---'; for s in inventory-database billing-database inventory-app billing-app rabbit-queue; do echo \"== $s ==\"; docker port $s; echo '(empty above = isolated, no host port)'; done; echo '== api-gateway-app =='; docker port api-gateway-app",
    ),
    (
        "14. Network: internal DNS + bridge members (audit.md:138-144)",
        "docker network inspect play-with-containers-network --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{println}}{{end}}'; echo '---'; docker exec api-gateway-app python3 -c \"import urllib.request; print(urllib.request.urlopen('http://inventory-app:8080/health', timeout=5).read().decode())\"",
    ),
    (
        "15. Inventory POST /api/movies/ -> 200 (audit.md:172-181)",
        'curl -i -X POST http://localhost:3000/api/movies/ -H "Content-Type: application/json" -d \'{"title": "A new movie", "description": "Very short description"}\'',
    ),
    (
        "16. Inventory GET /api/movies/ -> 200 + movie (audit.md:183-185)",
        "curl -i http://localhost:3000/api/movies/ | head -n 40",
    ),
    (
        "17. Billing POST /api/billing/ user 20 -> 200 (audit.md:189-199)",
        'curl -i -X POST http://localhost:3000/api/billing/ -H "Content-Type: application/json" -d \'{"user_id": "20", "number_of_items": "99", "total_amount": "250"}\'',
    ),
    (
        "18. Billing persisted: user 20 in orders (audit.md: billing DB check)",
        "sleep 2; docker exec billing-database psql -U billing_user -d billing_db -c \"SELECT id, user_id, number_of_items, total_amount FROM orders ORDER BY id DESC LIMIT 5;\"",
    ),
    (
        "19. Stop billing-app + confirm stopped (audit.md:201-203)",
        'docker stop billing-app; echo "---"; docker ps -a --filter name=billing-app --format \'table {{.Names}}\\t{{.Status}}\'; docker inspect -f \'Running={{.State.Running}} ExitCode={{.State.ExitCode}}\' billing-app',
    ),
    (
        "20. Billing POST user 22 while DOWN -> 200 (audit.md:205-215)",
        'curl -i -X POST http://localhost:3000/api/billing/ -H "Content-Type: application/json" -d \'{"user_id": "22", "number_of_items": "10", "total_amount": "50"}\'',
    ),
    (
        "21. Outage proof: user 22 buffered, shows after restart (audit.md: core test)",
        "echo '--- orders for 22 BEFORE restart (newest 5): ---'; docker exec billing-database psql -U billing_user -d billing_db -c \"SELECT id, user_id, number_of_items, total_amount FROM orders WHERE user_id = '22' ORDER BY id DESC LIMIT 5;\"; echo '--- restarting worker ---'; docker start billing-app; sleep 6; echo '--- orders for 22 AFTER restart (newest 5): ---'; docker exec billing-database psql -U billing_user -d billing_db -c \"SELECT id, user_id, number_of_items, total_amount FROM orders WHERE user_id = '22' ORDER BY id DESC LIMIT 5;\"; echo '--- worker log ---'; docker logs billing-app --since 90s 2>&1 | grep -E 'Connected to RabbitMQ|Successfully processed' | tail -n 5",
    ),
    (
        "22. Bonus surface: openapi + postman + suites (audit.md:217-223)",
        "ls -l openapi.yaml postman/ scripts/; echo '---'; grep -n '^  /' openapi.yaml | head -n 20",
    ),
]


def run_in_pane(cmd: str) -> None:
    subprocess.run(["herdr", "pane", "run", PANE, cmd], check=True)


def wait_for_prompt(timeout: int = 60) -> bool:
    """Wait until the pane looks idle at a shell prompt ($/#)."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            res = subprocess.run(
                ["herdr", "pane", "read", PANE, "--lines", "3"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=10,
            )
        except Exception:
            time.sleep(1.0)
            continue
        out = res.stdout or ""
        # herdr wraps output in JSON; extract plain lines heuristically.
        lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
        if lines:
            last = lines[-1]
            # Strip ANSI escapes for the prompt test.
            import re

            clean = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", last)
            clean = clean.strip().strip('"').strip("'").strip(",").strip()
            if clean.endswith("$") or clean.endswith("#"):
                return True
        time.sleep(1.0)
    return False


def sleep_for(cmd: str) -> float:
    if "docker compose ps" in cmd:
        return 3.0
    if "docker stop billing-app" in cmd:
        return 8.0
    if "docker start billing-app" in cmd and "psql" in cmd:
        return 12.0
    if "vagrant" in cmd or "newman" in cmd:
        return 5.0
    if "curl -i -X POST" in cmd:
        return 2.5
    if "docker exec" in cmd and "psql" in cmd:
        return 3.0
    if "docker logs" in cmd:
        return 2.0
    return 2.0


def main() -> int:
    print(f"Starting play-with-containers audit sequence in pane {PANE} ...")
    print(f"Repo: {REPO_ROOT}")
    # Sanity: pane must exist.
    chk = subprocess.run(["herdr", "pane", "get", PANE],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if chk.returncode != 0:
        print(f"ERROR: pane {PANE} not found. Pass an explicit pane id.", file=sys.stderr)
        return 1

    run_in_pane("clear")
    time.sleep(0.8)
    run_in_pane("echo -e '\\033[1;36m=== PLAY-WITH-CONTAINERS AUDIT STEP-BY-STEP (audit.md order) ===\\033[0m'")
    time.sleep(0.8)

    for i, (title, cmd) in enumerate(STEPS):
        print(f"[{i + 1}/{len(STEPS)}] {title}")
        # Header with yellow highlight, then the command itself.
        safe_title = title.replace("'", "'\\''")
        run_in_pane(f"echo -e '\\n\\033[1;33m>>> Step {i + 1}/{len(STEPS)}: {safe_title}\\033[0m'")
        time.sleep(0.6)
        run_in_pane(cmd)
        time.sleep(sleep_for(cmd))
        ok = wait_for_prompt(timeout=90)
        if not ok:
            print(f"  (warn) pane {PANE} did not return to prompt within 90s, continuing)")
        time.sleep(0.8)

    run_in_pane("echo -e '\\n\\033[1;32m=== ALL PLAY-WITH-CONTAINERS AUDIT COMMANDS FINISHED ===\\033[0m'")
    print("Done!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
