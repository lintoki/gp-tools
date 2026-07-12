PYTHON ?= .venv/Scripts/python.exe

.PHONY: test lint verify help

help:
	$(PYTHON) -m a_share_research.cli --help

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check src tests

verify: test lint
	$(PYTHON) -m compileall -q src

