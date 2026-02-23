# Makefile for Backend project

.PHONY: install run lint test clean

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
