.PHONY: help up down api web test clean install dev

help:
	@echo "Galvana Development Commands"
	@echo ""
	@echo "  make install    - Install all dependencies"
	@echo "  make up         - Start infrastructure (DB, Redis, MinIO)"
	@echo "  make down       - Stop infrastructure"
	@echo "  make api        - Run API server (development)"
	@echo "  make web        - Run web frontend (development)"
	@echo "  make worker     - Run simulation worker"
	@echo "  make test       - Run all tests"
	@echo "  make clean      - Clean build artifacts"
	@echo "  make dev        - Start everything for development"

# Install dependencies
install:
	@echo "Installing Python dependencies..."
	pip install poetry
	poetry install
	@echo "Installing Node dependencies..."
	cd apps/web && npm install

# Infrastructure
up:
	docker compose -f infra/compose/docker-compose.dev.yml up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@echo "Infrastructure is ready!"

down:
	docker compose -f infra/compose/docker-compose.dev.yml down

# Development servers
api:
	cd services/api && python main.py

web:
	cd apps/web && npm run dev

worker:
	python workers/sim-fenicsx/simple_solver.py

# Combined development
dev: up
	@echo "Starting development environment..."
	@trap 'make down' EXIT; \
	(cd services/api && python main.py) & \
	(cd apps/web && npm run dev) & \
	wait

# Testing
test:
	pytest services/api/tests -v
	cd apps/web && npm test

# Clean up
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf apps/web/.next
	rm -rf apps/web/node_modules
	rm -rf dist build *.egg-info

# Quick start
quickstart: install up
	@echo "========================================"
	@echo "Galvana MVP is ready!"
	@echo ""
	@echo "API:      http://localhost:8080"
	@echo "Web:      http://localhost:3000"
	@echo "MinIO:    http://localhost:9001"
	@echo ""
	@echo "Run 'make api' and 'make web' in separate terminals"
	@echo "========================================"