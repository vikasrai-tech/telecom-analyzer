.PHONY: help dev demo api web test test-all retrain lint format clean

help:
	@echo "Available targets:"
	@echo "  make web       - Run modern Vue 3 Web UI + FastAPI REST server (port 8000)"
	@echo "  make demo      - Run SIMPLE dashboard (easy view for demo)"
	@echo "  make dev       - Run full technical dashboard"
	@echo "  make api       - Run FastAPI REST server (port 8000)"
	@echo "  make test      - Run smoke tests (stubs, fast)"
	@echo "  make test-all  - Run full integration tests (requires test data)"
	@echo "  make retrain   - Run nightly detector retraining from feedback"
	@echo "  make lint      - Run ruff linter"
	@echo "  make format    - Auto-format with black"
	@echo "  make clean     - Remove __pycache__, .pytest_cache, etc."
	@echo ""
	@echo "  Cron example (daily 2am):"
	@echo "  0 2 * * * cd /mnt/e/telecom-analyzer && make retrain >> logs/retrain.log 2>&1"

demo:
	streamlit run src/dashboard/app_simple.py

dev:
	streamlit run src/dashboard/app.py

api:
	uvicorn src.api.main:app --reload --port 8000

test:
	pytest tests/test_walking_skeleton.py -v

test-all:
	pytest tests/ -v --cov=src

retrain:
	python scripts/nightly_retrain.py

lint:
	ruff check src/ tests/

format:
	black src/ tests/
	ruff check --fix src/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# ── Research evaluation targets ───────────────────────────────────────
evaluate:
	python scripts/run_detection_benchmark.py

benchmark-forecast:
	python scripts/run_forecast_benchmark.py

benchmark-rca:
	python scripts/run_rca_evaluation.py

benchmark-scale:
	python scripts/run_scalability_benchmark.py

benchmark-all:
	python scripts/run_detection_benchmark.py && \
	python scripts/run_forecast_benchmark.py && \
	python scripts/run_rca_evaluation.py && \
	python scripts/run_scalability_benchmark.py
