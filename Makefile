.PHONY: setup check format test clean

setup:
	@echo "Setting up Helios-Quant-Core development environment..."
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	.venv/bin/pre-commit install
	@echo "Setup complete. Run 'source .venv/bin/activate' to enter the environment."

check:
	@echo "Running Ruff Linter..."
	.venv/bin/ruff check src/ tests/
	@echo "Running Mypy Type Checker..."
	.venv/bin/mypy src/ tests/

format:
	@echo "Formatting code with Ruff..."
	.venv/bin/ruff check --fix src/ tests/

test:
	@echo "Running Pytest..."
	.venv/bin/pytest tests/

clean:
	@echo "Cleaning up caches..."
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
