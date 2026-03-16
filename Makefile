# Makefile for Backend project

.PHONY: install run lint test clean vps-up vps-down

install:
	pip install -r requirements.txt

run:
	uvicorn app.main:app --reload --port 8000

dev:
	pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000

lint:
	flake8 app/

test:
	pytest

worker:
	celery -A app.jobs.celery_app.celery_app worker --loglevel=info --pool=threads --concurrency=3

docker-up:
	docker compose -f infra/docker-compose.dev.yml up --build -d --scale celery-worker=4

docker-up-main:
	docker compose -f infra/docker-compose.main.yml up --build -d --scale celery-worker=4

docker-up-dev:
	docker compose -f infra/docker-compose.dev.yml up --build -d --scale celery-worker=4

docker-down:
	docker compose -f infra/docker-compose.dev.yml down

docker-down-main:
	docker compose -f infra/docker-compose.main.yml down

docker-down-dev:
	docker compose -f infra/docker-compose.dev.yml down

vps-up:
	set -a; . ./.env; set +a; \
	export VPS_HOST="$$VPS_HOST" VPS_USER="$$VPS_USER" SSH_KEY="$$SSH_KEY"; \
	bash infra/vps-up.sh

vps-down:
	set -a; . ./.env; set +a; \
	export VPS_HOST="$$VPS_HOST" VPS_USER="$$VPS_USER" SSH_KEY="$$SSH_KEY"; \
	bash infra/vps-down.sh

clean:
	rm -rf __pycache__
	find . -type d -name '__pycache__' -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

.PHONY: venv
venv:
	python3 -m venv .venv
	@echo "To activate venv:"
	@echo "macOS/Linux (zsh/bash): source .venv/bin/activate"
	@echo "Windows (cmd): .venv\\Scripts\\activate.bat"
	@echo "Windows (PowerShell): .venv\\Scripts\\Activate.ps1"

# To activate venv:
# macOS/Linux (zsh/bash): source .venv/bin/activate
# Windows (cmd): .venv\Scripts\activate.bat
# Windows (PowerShell): .venv\Scripts\Activate.ps1
