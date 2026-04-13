.PHONY: format lint typecheck test clean build

format:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

lint:
	uv run ruff check src/ tests/

typecheck:
	uv run mypy src/

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ -v --cov=synpareia_trust_mcp --cov-report=term-missing

clean:
	rm -rf dist/ build/ *.egg-info .mypy_cache .pytest_cache .ruff_cache .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +

build: clean
	uv run python -m build
