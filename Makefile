# Makefile for Docker and Python tasks

# Variables
IMAGE_NAME=gtfs-dublin
CONTAINER_NAME=gtfs-dublin
DOCKER_COMPOSE_FILE=docker-compose.yml
PYTHON=python3

# Docker tasks
build:
	docker build -t $(IMAGE_NAME) .

run:
	docker run --rm -it -p 8000:8000 --name $(CONTAINER_NAME) $(IMAGE_NAME)

run-mcp:
	docker run --rm -it -p 8001:8001 --name $(CONTAINER_NAME)-mcp $(IMAGE_NAME) \
		uv run --project mcp-server python mcp-server/main.py --transport streamable-http

stop:
	docker stop $(CONTAINER_NAME) $(CONTAINER_NAME)-mcp || true

down:
	docker-compose -f $(DOCKER_COMPOSE_FILE) down

up:
	docker-compose -f $(DOCKER_COMPOSE_FILE) up --build

up-api:
	docker-compose -f $(DOCKER_COMPOSE_FILE) up transport-api --build

up-mcp:
	docker-compose -f $(DOCKER_COMPOSE_FILE) up mcp-server --build

# Python tasks
test:
	uv run pytest

format:
	uv run black gtfs_core/ gtfs_dublin/ mcp-server/

lint:
	uv run ruff check gtfs_core/ gtfs_dublin/ mcp-server/

lint-fix:
	uv run ruff check --fix gtfs_core/ gtfs_dublin/ mcp-server/

type-check:
	uv run mypy gtfs_core/ gtfs_dublin/ mcp-server/main.py

check: format lint type-check
	@echo "✅ All code quality checks passed!"

update-gtfs:
	python scripts/update_gtfs.py

pre-commit-install:
	pre-commit install

pre-commit-run:
	pre-commit run --all-files

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache *.pyc *.pyo *.egg-info dist build

.PHONY: build run stop down up test format lint lint-fix type-check update-gtfs pre-commit-install pre-commit-run clean
