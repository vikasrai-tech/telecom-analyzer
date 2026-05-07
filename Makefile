.PHONY: help dev test lint format clean

help:
	@echo "Available targets:"
	@echo "  make dev       - Run Streamlit dashboard"
	@echo "  make test      - Run pytest"
	@echo "  make lint      - Run ruff linter"
	@echo "  make format    - Auto-format with black"
	@echo "  make clean     - Remove __pycache__, .pytest_cache, etc."

dev:
	streamlit run src/dashboard/app.py

test:
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
