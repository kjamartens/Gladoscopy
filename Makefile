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
    # Use the base-env's uv (not $(PYTHON), which is .venv's python once it
    # exists and doesn't have uv installed in it). Target .venv explicitly
    # via --python — relying on uv's auto-detection is unsafe when a conda
    # env is active, since uv can prefer CONDA_PREFIX over .venv/, silently
    # installing into the wrong environment (the one $(PYTHON) does NOT read).
    PIP    ?= python -m uv pip install --python $(_VENV_PYTHON)
    # Whatever "python" is on PATH (base conda env, GladosEnv, plain venv...)
    # may never have had uv bootstrapped into it — ensure it before using PIP.
    _ENSURE_UV = python -c "import importlib.util,sys,subprocess as s; sys.exit(0) if importlib.util.find_spec('uv') else s.check_call([sys.executable,'-m','pip','install','--quiet','uv'])"
else
    _VENV_PYTHON := .venv/bin/python
    _VENV_CREATE := uv venv --python 3.13 .venv
    PYTHON ?= $(if $(wildcard $(_VENV_PYTHON)),$(_VENV_PYTHON),python)
    PIP    ?= uv pip install --python $(_VENV_PYTHON)
    _ENSURE_UV = command -v uv >/dev/null 2>&1 || python -m pip install --quiet uv
endif
PYTEST ?= $(PYTHON) -m pytest
RUFF   ?= $(PYTHON) -m ruff
MYPY   ?= $(PYTHON) -m mypy
BANDIT ?= $(PYTHON) -m bandit
PACKAGE := glados_pycromanager

.PHONY: help env venv install dev build ensure-uv \
        test test-fast test-cov \
        lint lint-fix format mypy bandit \
        run run-dev run-prod run-mm run-demo profile-runtime profile-startup bench-live-display \
        ci verify \
        clean

help:  ## Show this help.
	@$(PYTHON) -c "import re; print('Targets:'); [print('  {:<18} {}'.format(*m.groups())) for l in open('Makefile',encoding='utf-8',errors='replace') for m in [re.match(r'^([a-zA-Z_-]+):.*?## (.*)', l)] if m]"

# ── Environment & install ─────────────────────────────────────────────────────

# Real (file, not directory) target — so a corrupt/partial .venv left behind
# by e.g. a locked python.exe during `make clean` gets rebuilt, not reused.
.venv/pyvenv.cfg:
	$(_VENV_CREATE)
	@echo ".venv created with uv — run 'make dev' to install."

.venv: .venv/pyvenv.cfg

venv: .venv  ## Create .venv using the system Python (skipped if already present).

env:  ## Create or update the GladosEnv conda env from environment.yaml (conda users).
	conda env create --name GladosEnv -f environment.yaml 2>/dev/null \
	    || conda env update --name GladosEnv -f environment.yaml

ensure-uv:  ## Make sure uv is importable for the active interpreter (installs quietly if missing).
	@$(_ENSURE_UV)

install: .venv ensure-uv  ## Non-editable production install into .venv (no dev extras).
	$(PIP) .

dev: .venv ensure-uv  ## Editable install with dev extras into .venv (creates .venv if absent).
	$(PIP) -e ".[dev]"
	@$(PYTHON) -c "import diplib" || ( \
		echo "diplib failed to import after install -- this is usually a Windows locked-file pip reinstall (a stale python.exe, VSCode's Pylance, or an AV scan held PyDIP_bin*.pyd open, so pip renamed the old folder to '~iplib' and left diplib/ a stale/new mix); forcing a clean reinstall..." && \
		$(PIP) --force-reinstall --no-cache-dir diplib==3.6.0 && \
		$(PYTHON) -c "import diplib" \
	)

build: ensure-uv  ## Build wheel + sdist into dist/.
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
# NOTE: do NOT add `-X faulthandler` to these targets. Whenever a JVM is in the
# process -- any pycromanager/Micro-Manager path, and it can be loaded even when
# the selected backend is pymmcore-plus -- HotSpot deliberately raises
# EXCEPTION_ACCESS_VIOLATION as part of normal operation (implicit null checks,
# safepoint polling) and handles them itself. faulthandler's Windows exception
# handler runs first, prints "Windows fatal exception: access violation" for each
# one, and dumps every thread's traceback; eventually one of those dumps walks
# the frames of a thread that is still running and faults inside `dump_frame`,
# which kills the process for real. That was diagnosed from `hs_err_pid*.log`:
# "Current thread: JavaThread ... [_thread_in_Java]", "Problematic frame:
# python313.dll dump_frame", reached via `faulthandler_exc_handler`.
# Set FAULTHANDLER=1 to opt back in when debugging a genuine native crash in a
# JVM-free run.
FAULTHANDLER ?= 0
ifeq ($(FAULTHANDLER),1)
PYFLAGS := -X faulthandler
else
PYFLAGS :=
endif

run:  ## Launch the standalone Glados-PycroManager GUI.
	$(PYTHON) $(PYFLAGS) -m glados_pycromanager.GUI.GUI_napari

run-dev: dev  ## Editable install (dev extras) then launch Glados — one-shot dev workflow.
	$(PYTHON) $(PYFLAGS) -m glados_pycromanager.GUI.GUI_napari

run-prod: .venv ensure-uv  ## Non-editable (production) install then launch Glados — simulate end-user install.
	$(PIP) .
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
	python -c "import shutil,glob,os,sys; \
	    paths=['build','dist','.pytest_cache','.ruff_cache','.mypy_cache','.venv']+glob.glob('*.egg-info'); \
	    failed=[p for p in paths if os.path.exists(p) and (shutil.rmtree(p,ignore_errors=True) or os.path.exists(p))]; \
	    [os.remove(f) for f in glob.glob('startup.log') if os.path.isfile(f)]; \
	    (print('WARNING: could not fully remove:', ', '.join(failed), '-- a locked file (running process, AV scan, open shell/IDE) blocked deletion; close it and re-run make clean', file=sys.stderr), sys.exit(1)) if failed else None"
