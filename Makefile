.PHONY: up down build logs ps clean rebuild restart help

help:
	@echo "targets:"
	@echo "  make up        - build and start the whole infrastructure"
	@echo "  make build     - build all images"
	@echo "  make logs      - follow compose logs"
	@echo "  make ps        - container status"
	@echo "  make restart   - restart all containers"
	@echo "  make down      - stop and remove containers + network (keeps volumes)"
	@echo "  make clean     - down AND remove volumes (all data lost)"

up:
	docker-compose up --build -d

build:
	docker-compose build

logs:
	docker-compose logs -f

ps:
	docker-compose ps

restart:
	docker-compose restart

down:
	docker-compose down

clean:
	docker-compose down -v --remove-orphans
