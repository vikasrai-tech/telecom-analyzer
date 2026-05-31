.PHONY: help dev api test test-all lint format clean

help:
	@echo "Available targets:"
	@echo "  make dev       - Run Streamlit dashboard"
	@echo "  make api       - Run FastAPI REST server (port 8000)"
	@echo "  make test      - Run smoke tests (stubs, fast)"
	@echo "  make test-all  - Run full integration tests (requires test data)"
	@echo "  make lint      - Run ruff linter"
	@echo "  make format    - Auto-format with black"
	@echo "  make clean     - Remove __pycache__, .pytest_cache, etc."

dev:
	streamlit run src/dashboard/app.py

api:
	uvicorn src.api.main:app --reload --port 8000

test:
	pytest tests/test_walking_skeleton.py -v

test-all:
	pytest tests/ -v --cov=src

lint:
	ruff check src/ tests/

format:
	black src/ tests/
	ruff check --fix src/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
