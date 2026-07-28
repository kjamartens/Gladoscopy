# Common developer tasks. Works on Windows (GnuWin32 make or Git-Bash make),
# macOS, and Linux. Targets are thin wrappers so CI can call the same commands.
#
# Quick start (new contributor — no conda needed):
#   make dev       ← creates .venv if absent, then editable install with dev extras
#   make run-dev   ← dev install + launch in one step
#   make run-prod  ← non-editable (production) install + launch in one step
#   make run-mm    ← launch with pre-set backend/config (bypasses popup; for testing)
#                    BACKEND=PyMMCorePlus CONFIG=/path/to/MMConfig.cfg [MM_PATH=...]
#   make run-demo  ← launch against the pymmcore-plus bundled demo (no popup, no hardware)
#   make test      ← run the test suite
#   make ci        ← full local gate: lint + bandit + tests
#
# Conda alternative (existing GladosEnv users):
#   make env      ← create / update GladosEnv conda env
#   conda activate GladosEnv && make dev
#
# Windows: GnuWin32 make (C:\Program Files (x86)\GnuWin32\bin\make.exe)
# works from PowerShell / cmd.  Git-Bash make also works.

# Auto-detect .venv so no manual activation is ever needed.
# Override by setting PYTHON explicitly: make test PYTHON=python3.13
ifeq ($(OS),Windows_NT)
    _VENV_PYTHON := .venv/Scripts/python.exe
    # Bootstrap uv via Anaconda pip, then let uv fetch Python 3.13 if needed.
    # uv venv does not install pip, so PIP uses the base-env uv (auto-detects .venv).
    _VENV_CREATE  = python -m pip install --quiet uv && python -m uv venv --python 3.13 --seed .venv
    PYTHON ?= $(if $(wildcard $(_VENV_PYTHON)),$(subst /,\,$(_VENV_PYTHON)),python)
    PIP    ?= $(PYTHON) -m pip
else
    _VENV_PYTHON := .venv/bin/python
    _VENV_CREATE := uv venv --python 3.13 .venv
    PYTHON ?= $(if $(wildcard $(_VENV_PYTHON)),$(_VENV_PYTHON),python)
    PIP    ?= uv pip
endif
PYTEST ?= $(PYTHON) -m pytest
RUFF   ?= $(PYTHON) -m ruff
MYPY   ?= $(PYTHON) -m mypy
BANDIT ?= $(PYTHON) -m bandit
PACKAGE := glados_pycromanager

.PHONY: help env venv install dev build \
        test test-fast test-cov \
        lint lint-fix format mypy bandit \
        run run-dev run-prod run-mm run-demo profile-runtime profile-startup bench-live-display \
        ci verify \
        clean

help:  ## Show this help.
	@$(PYTHON) -c "import re; print('Targets:'); [print('  {:<18} {}'.format(*m.groups())) for l in open('Makefile',encoding='utf-8',errors='replace') for m in [re.match(r'^([a-zA-Z_-]+):.*?## (.*)', l)] if m]"

# ── Environment & install ─────────────────────────────────────────────────────

.venv:
	$(_VENV_CREATE)
	@echo ".venv created with uv — run 'make dev' to install."

venv: .venv  ## Create .venv using the system Python (skipped if already present).

env:  ## Create or update the GladosEnv conda env from environment.yaml (conda users).
	conda env create --name GladosEnv -f environment.yaml 2>/dev/null \
	    || conda env update --name GladosEnv -f environment.yaml

install:  ## Non-editable production install into the active env (no dev extras).
	$(PIP) install .

dev: .venv  ## Editable install with dev extras into .venv (creates .venv if absent).
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
	$(PYTHON) -X faulthandler -m glados_pycromanager.GUI.GUI_napari

run-dev: dev  ## Editable install (dev extras) then launch Glados — one-shot dev workflow.
	$(PYTHON) -X faulthandler -m glados_pycromanager.GUI.GUI_napari

run-prod: .venv  ## Non-editable (production) install then launch Glados — simulate end-user install.
	$(PIP) install .
	$(PYTHON) -m glados_pycromanager.GUI.GUI_napari

# run-mm: launch with pre-set MM backend / config — bypasses the startup popup.
# Override on cmdline: make run-mm BACKEND=PyMMCorePlus CONFIG=/path/to/MMConfig.cfg MM_PATH=/path/to/mm
BACKEND       ?=
CONFIG        ?=
MM_PATH       ?=
BUFFER_MB     ?=
MAX_MEMORY_MB ?=

run-mm:  ## Launch Glados with pre-set MM backend/config (bypasses popup). Vars: BACKEND CONFIG [MM_PATH BUFFER_MB MAX_MEMORY_MB].
	$(PYTHON) -m glados_pycromanager.GUI.GUI_napari \
	    $(if $(BACKEND),--backend "$(BACKEND)") \
	    $(if $(CONFIG),--config "$(CONFIG)") \
	    $(if $(MM_PATH),--mm-path "$(MM_PATH)") \
	    $(if $(BUFFER_MB),--buffer-mb $(BUFFER_MB)) \
	    $(if $(MAX_MEMORY_MB),--max-memory-mb $(MAX_MEMORY_MB))

run-demo:  ## Launch Glados against the pymmcore-plus bundled demo install + MMConfig_demo.cfg (no popup).
	$(PYTHON) -m glados_pycromanager.GUI.GUI_napari --auto-demo

# Default sample window for `make profile-runtime`. Override: make profile-runtime PROFILE_SECS=12
PROFILE_SECS ?= 8

profile-runtime:  ## Auto-launch demo, profile live mode for PROFILE_SECS seconds, append top-25 to docs/perf-runtime.txt.
	$(PYTHON) -m glados_pycromanager.GUI.GUI_napari --auto-demo --profile-runtime $(PROFILE_SECS)

profile-startup:  ## Capture cold-import timings; appends to docs/perf-baseline.txt.
	pwsh -File scripts/profile_startup.ps1

BENCH_FRAMES ?= 60

bench-live-display:  ## Hardware-free live-display micro-benchmark; appends to docs/bench-live-display.txt.
	$(PYTHON) -m scripts.bench_live_display --mode layer-update --frames $(BENCH_FRAMES)
	$(PYTHON) -m scripts.bench_live_display --mode queue-depth

# ── Gates ─────────────────────────────────────────────────────────────────────

ci: lint bandit test  ## Full local CI gate (lint + bandit + tests).

verify: ci  ## Alias for ci (backwards compat).

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:  ## Remove build / cache artefacts and .venv (works on Windows and Unix).
	$(PYTHON) -c "import shutil,glob,os; \
	    [shutil.rmtree(p,True) for p in \
	        ['build','dist','.pytest_cache','.ruff_cache','.mypy_cache','.venv'] \
	        + glob.glob('*.egg-info')]; \
	    [os.remove(f) for f in glob.glob('startup.log') if os.path.isfile(f)]"
