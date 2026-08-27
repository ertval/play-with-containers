.PHONY: up down build logs ps clean rebuild restart help config lint test

help:
	@echo "targets:"
	@echo "  make up        - build and start the whole infrastructure"
	@echo "  make build     - build all images"
	@echo "  make logs      - follow compose logs"
	@echo "  make ps        - container status"
	@echo "  make config    - validate compose file"
	@echo "  make lint      - lint Dockerfiles (hadolint)"
	@echo "  make test      - run audit E2E suite"
	@echo "  make restart   - restart all containers"
	@echo "  make rebuild   - clean rebuild from scratch and start"
	@echo "  make down      - stop and remove containers + network (keeps volumes)"
	@echo "  make clean     - down AND remove volumes (all data lost)"

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

rebuild:
	docker compose down -v --remove-orphans
	docker compose build --no-cache
	docker compose up -d

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
