.DEFAULT_GOAL := help
.PHONY: all up down build logs ps clean rebuild restart help config lint test test-py

all: up

help:
	@echo "targets:"
	@echo "  make up        - build and start the whole infrastructure, wait until healthy"
	@echo "  make build     - build all images"
	@echo "  make logs      - follow compose logs"
	@echo "  make ps        - container status"
	@echo "  make config    - validate compose file"
	@echo "  make lint      - lint Dockerfiles (hadolint)"
	@echo "  make test      - run audit E2E suite"
	@echo "  make test-py   - run automated python test suite"
	@echo "  make restart   - restart all containers"
	@echo "  make rebuild   - clean rebuild from scratch (no cache) and start"
	@echo "  make down      - stop and remove containers + network (keeps volumes)"
	@echo "  make clean     - down AND remove volumes (all data lost)"

COMPOSE := docker compose

up:
	@$(COMPOSE) version >/dev/null 2>&1 || { \
		echo "error: Docker Compose v2 ('docker compose') is required."; \
		echo "       The --wait flag used here needs v2.1+."; exit 1; }
	$(COMPOSE) up --build -d --wait --wait-timeout 240

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

restart:
	$(COMPOSE) restart

rebuild:
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d --wait --wait-timeout 240

down:
	$(COMPOSE) down

clean:
	$(COMPOSE) down -v --remove-orphans

config:
	$(COMPOSE) config --quiet && echo "compose OK"

lint:
	@if command -v hadolint >/dev/null 2>&1; then \
		hadolint srcs/**/Dockerfile; \
	elif command -v docker >/dev/null 2>&1; then \
		for df in srcs/*/Dockerfile; do \
			echo "Linting $$df..."; \
			docker run --rm -i hadolint/hadolint < "$$df" || true; \
		done; \
	else \
		echo "Neither hadolint nor docker found for linting"; \
	fi

test:
	bash scripts/test_audit.sh

test-py:
	python3 scripts/test_api.py

