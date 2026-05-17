# Common developer tasks. Works on Windows via Git-Bash `make`, on macOS
# / Linux via system `make`. Targets are intentionally thin wrappers so
# CI can call the same commands.

PYTHON ?= python
PIP ?= $(PYTHON) -m pip
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
MYPY ?= $(PYTHON) -m mypy
BANDIT ?= $(PYTHON) -m bandit
PACKAGE := glados_pycromanager

.PHONY: help install test lint lint-fix format mypy bandit run profile-startup verify clean

help:  ## Show this help.
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  %-18s %s\n", $$1, $$2}'

install:  ## Editable install with dev extras.
	$(PIP) install -e ".[dev]"

test:  ## Run the pytest suite.
	$(PYTEST) -q

lint:  ## Run ruff (check) + mypy (informational) across the package.
	$(RUFF) check $(PACKAGE) tests
	-$(MYPY) $(PACKAGE)

lint-fix:  ## Apply ruff's auto-fixes.
	$(RUFF) check --fix $(PACKAGE) tests

format:  ## Apply ruff-format in place.
	$(RUFF) format $(PACKAGE) tests

mypy:  ## Run mypy only.
	$(MYPY) $(PACKAGE)

bandit:  ## Run bandit security scan (informational).
	$(BANDIT) -r $(PACKAGE) --exclude $(PACKAGE)/GUI/nodz

run:  ## Launch the standalone Glados-PycroManager GUI.
	$(PYTHON) -m glados_pycromanager.GUI.GUI_napari

profile-startup:  ## Capture cold-import timings into startup.log.
	$(PYTHON) -X importtime -c "import glados_pycromanager.GUI.GUI_napari" 2> startup.log
	@echo "wrote startup.log"

verify:  ## Full pre-push gate: lint + tests.
	$(MAKE) lint
	$(MAKE) test

clean:  ## Remove build / cache artefacts.
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache .mypy_cache
