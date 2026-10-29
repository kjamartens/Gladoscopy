# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
There are no tagged releases yet; `main` is the current version.

## [Unreleased]

Changes since May 2026. Design notes and per-step decisions from this period are archived in
`docs/plans/`.

### Added

- **One-click Windows install and launch**: `install_windows.bat` sets up a `.venv` with
  [uv](https://docs.astral.sh/uv/) (Python 3.13 included, no conda), Start Menu shortcuts
  ("Glados", "last setup", "debug console"), a console-less `gladosw` launcher, a startup splash, a
  single running instance per user, `--last` and `--auto-demo` start options, and a readable
  "could not start" dialog with the log.
- **Microscope service**: one owner thread for all microscope access, with a priority queue, so
  hardware calls no longer block the GUI.
- **Live mode from a continuous sequence acquisition** instead of a long MDA, with a selectable
  pull policy.
- **Configurations**: device property browser, config group/preset editor (Micro-Manager's own
  methodology), read-only groups, automatic refresh, and the active preset shown in dropdowns.
- **Controls dock redesign**: a shared layout toolkit (theme, sections, responsive grid), an XY
  stage dial, compact Stages and Configurations, and a new Real-time analysis panel where several
  methods run side by side.
- **Real-time analysis**: subprocess isolation by default (`__runInSubprocess__` /
  `__needsLiveCore__`), a pre-warmed worker pool, several napari layers per node, overlays drawn
  against the frame they belong to, and replay of results while scrolling a finished acquisition.
  New nodes: `pSMLM_live`, `pSMLM_live_precision` (live NeNA/FRC), SIM phase check.
- **Storage**: pymmcore-plus acquisitions are saved (NDTiff by default, or OME-TIFF/OME-Zarr),
  written from a dedicated thread.
- **MDA**: "Wait for Z to settle" toggle (fixes lost external triggers during z-stacks), live
  step count/distance next to the Z fields, a stalled camera burst no longer aborts the
  acquisition.
- **Autonomous microscopy**: node functions are dispatched through a registry
  (`@register("Module.Function")`) instead of `eval`; *Plugins → Reload Glados Custom Nodes*;
  four example recipes for a simulated SMLM microscope in `ExampleRecipes/`.
- **Slack settings…** dialog; credentials are stored per user, not in the source.
- Performance Mode (CPU/memory capture) and a startup timeline profiler.
- Documentation site (MkDocs Material) at <https://kjamartens.github.io/Gladoscopy/>, with an
  API reference generated from the source; the Help buttons open it.
- Test suite (~1450 tests, no hardware needed), ruff/mypy/bandit, pre-commit and CI.

### Changed

- Licence: CC BY-NC-SA 4.0 (`LICENCE`). The vendored Nodz editor keeps its MIT licence.
- Startup is several seconds faster: heavy libraries (pycromanager, dask, pandas, torch…) load on
  first use, and the circular buffer is allocated in the background.
- Live display is faster: frames go through a bounded ring buffer, the display only draws frames
  it can keep up with, and 2-D layers skip napari's asynchronous slicer.
- Recipe runs: nodes hand off through the event loop, failures and *Interrupt run* reliably stop a
  run, and late work from a stopped run cannot drive the next one.
- The process stays off Windows' efficiency cores when the window is not focused.
- Slack messages use `slack_sdk` (the old `slack` package was a different project).

### Removed

- The site-specific laser control UI (`LaserControlScripts.py` and its Qt Designer files).
- Dead code: the old `GUI.py` entry, `MainScripts/Main.py`/`HelperFunctions.py`, the RT-analysis
  `eval` dispatch fallback, unused helpers, and large commented-out blocks.
- Unused dependencies (torchvision, segment-anything, mobile-sam, timm, flask, slackeventsapi,
  bioio, markdown); `torch`, `stardist` and `scikit-image` are now declared, since nodes import them.
- The pdoc HTML pages, the `.docx` manuals and the conda environment files.

### Fixed

- Non-editable installs left out `Core/` (no `__init__.py`).
- Many acquisition and display bugs: stale zarr stores reused across differently shaped
  acquisitions, black live view during multi-D acquisitions, ROI and exposure changes during live
  mode, races between stopping and starting live mode, crashes when a state file section was
  missing.

## [0.0.2]: earlier

The state of the project before May 2026. No changelog was kept; see `git log` for the history.
