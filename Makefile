.PHONY: install test typecheck lint format build clean

install:
	pip install --upgrade pip
	pip install -e ".[dev]"

test:
	pytest --cov=ftmg --cov-report=term-missing tests/

typecheck:
	mypy ftmg/

lint:
	ruff check ftmg tests
	ruff format --check ftmg tests

format:
	ruff check --fix ftmg tests
	ruff format ftmg tests

build:
	python -m build

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .coverage htmlcov
