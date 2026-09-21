# Settings for `make run-demo-smlm` — the one-command, no-popup launch against a
# local (demo) Micro-Manager install. THIS FILE is the place to change which
# backend / install / config / memory that target uses; the Makefile recipe
# itself stays generic.
#
# All assignments use `?=`, so a command-line override still wins:
#   make run-demo-smlm DEMO_BUFFER_MB=1024
#
# Note: DEMO_MAX_MEMORY_MB has no effect on the PyMMCorePlus backend (only
# DEMO_BUFFER_MB, the circular-buffer footprint, is applied there) — Glados logs
# a warning saying so. It matters for the JAVA / Python pycromanager backends.

DEMO_BACKEND       ?= PyMMCorePlus
DEMO_MM_PATH       ?= C:/Users/kjamartens/AppData/Local/pymmcore-plus/pymmcore-plus/mm/Micro-Manager_2.0.3_20260724
DEMO_CONFIG        ?= C:/Users/kjamartens/AppData/Local/pymmcore-plus/pymmcore-plus/mm/DemoSMLM.cfg
DEMO_BUFFER_MB     ?= 4096
DEMO_MAX_MEMORY_MB ?= 12000
