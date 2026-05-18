# Common developer tasks. Works on Windows (GnuWin32 make or Git-Bash make),
# macOS, and Linux. Targets are thin wrappers so CI can call the same commands.
#
# Quick start (new contributor):
#   make env               ← create / update GladosEnv conda environment
#   conda activate GladosEnv   ← must be active before any other target
#   make dev               ← editable install with dev extras
#   make test              ← run the test suite
#   make ci                ← full local gate: lint + bandit + tests
#
# IMPORTANT: activate GladosEnv before running any target that installs,
# tests, or runs code — otherwise PYTHON resolves to the system Python.
#
# Windows: GnuWin32 make (C:\Program Files (x86)\GnuWin32\bin\make.exe)
# works from PowerShell / cmd.  Git-Bash make also works.

PYTHON  ?= python
PIP     ?= $(PYTHON) -m pip
PYTEST  ?= $(PYTHON) -m pytest
RUFF    ?= $(PYTHON) -m ruff
MYPY    ?= $(PYTHON) -m mypy
BANDIT  ?= $(PYTHON) -m bandit
PACKAGE := glados_pycromanager

.PHONY: help env install dev build \
        test test-fast test-cov \
        lint lint-fix format mypy bandit \
        run profile-startup \
        ci verify \
        clean

help:  ## Show this help.
	@$(PYTHON) -c "import re; print('NOTE: run \"conda activate GladosEnv\" before any target that installs, tests, or runs code.\n\nTargets:'); [print('  {:<18} {}'.format(*m.groups())) for l in open('Makefile',encoding='utf-8',errors='replace') for m in [re.match(r'^([a-zA-Z_-]+):.*?## (.*)', l)] if m]"

# ── Environment & install ─────────────────────────────────────────────────────

env:  ## Create or update the GladosEnv conda env from environment.yaml.
	conda env create --name GladosEnv -f environment.yaml 2>/dev/null \
	    || conda env update --name GladosEnv -f environment.yaml

install:  ## Non-editable production install (no dev extras).
	$(PIP) install .

dev:  ## Editable install with dev extras (typical day-to-day command).
	$(PIP) install -e ".[dev]"

build:  ## Build wheel + sdist into dist/.
	uv build

# ── Tests ─────────────────────────────────────────────────────────────────────

test:  ## Run the full pytest suite.
	$(PYTEST) -q

test-fast:  ## Stop on first failure, quiet output.
	$(PYTEST) -x -q

test-cov:  ## Run tests with branch coverage report.
	$(PYTEST) --cov=$(PACKAGE) --cov-report=term-missing -q

# ── Code quality ──────────────────────────────────────────────────────────────

lint:  ## ruff check + mypy (informational) across the package.
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

# ── Run ───────────────────────────────────────────────────────────────────────

run:  ## Launch the standalone Glados-PycroManager GUI.
	$(PYTHON) -m glados_pycromanager.GUI.GUI_napari

profile-startup:  ## Capture cold-import timings; appends to docs/perf-baseline.txt.
	pwsh -File scripts/profile_startup.ps1

# ── Gates ─────────────────────────────────────────────────────────────────────

ci: lint bandit test  ## Full local CI gate (lint + bandit + tests).

verify: ci  ## Alias for ci (backwards compat).

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:  ## Remove build / cache artefacts (works on Windows and Unix).
	$(PYTHON) -c "import shutil,glob,os; \
	    [shutil.rmtree(p,True) for p in \
	        ['build','dist','.pytest_cache','.ruff_cache','.mypy_cache'] \
	        + glob.glob('*.egg-info')]; \
	    [os.remove(f) for f in glob.glob('startup.log') if os.path.isfile(f)]"
