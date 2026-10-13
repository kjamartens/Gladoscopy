# One-click launch & startup speed — plan

Branch: `feature/one-click-launch` (off `main` @ `fdc7c10`). Standalone plan, like
`claude_throughput_project.md`: it is **not** advanced by "continue"; run it when asked
by name. Small conventional-commit steps; decisions go to `claude_decisions.md`.

## Goal

1. Start Glados with **one click from the taskbar / Start Menu**, with the Glados icon,
   no console window, and the running window grouped under that pinned icon.
2. Keep **edit code → relaunch** as the whole iteration loop (no rebuild step).
3. Make startup **measurably** faster, measured first, then optimised.

## Recommendation: launch the editable `.venv`; do not build a frozen installer

The launcher runs the existing editable install (`make dev` → `.venv`, `uv pip install -e`).
A source edit is live on the next click, with no build step.

Rejected: **PyInstaller / Briefcase / MSI / conda-constructor bundles.**
- tensorflow + torch + napari[all] + Qt WebEngine add up to a multi-GB bundle and a build
  that takes 10+ minutes. Every code change would need a rebuild, which defeats goal 2.
- `pycromanager` is installed from git main, unpinned. A frozen bundle would hide that
  drift instead of letting `make dev` pick it up.
- AppData plugin discovery (`importlib` of user `.py` nodes) needs a real interpreter
  plus every library those nodes import. Frozen builds strip libraries they can't see used.
- `multiprocessing` `spawn` (RT subprocess isolation, the warm pool) needs `freeze_support`
  and careful handling under PyInstaller. That would break a feature that works today.

"Installable" therefore means a **bootstrap script** that builds the same `.venv` and makes
the shortcuts (Phase L3). It is not a frozen artefact.

## Facts established while planning (2026-10-13)

- Entry: `glados_pycromanager.GUI.GUI_napari:main`, exposed through 4 console scripts.
  `.venv/Scripts/glados.exe` exists and is console-subsystem, so it opens a console window.
- Import of `GUI_napari`: **~3.7 s** (warm disk cache, this laptop). Top costs: `napari.qt`
  1.7 s, `pycromanager` 1.2 s (via `Core/microscopeInterfaceLayer.py` and
  `ndstorage`/`dask.array`), xarray/pandas through napari colormaps. The May baseline was
  5.0 s. **Imports are not most of startup**. The unknown part is everything after them:
  `Shared_data()`, warm-pool spawn, backend start (JVM / `loadSystemConfiguration`), viewer
  creation, docks, and `_finaliseStartupLayout`. L0 measures it.
- `main()` creates **two** `QApplication`s: `appSmall` for the backend dialog, then `app`.
  The ordering constraint is `import pymmcore` **before** napari/PyQt5 (access violation
  otherwise, see `docs/perf-runtime-recipe.md`).
- pycromanager's Java headless start (`mmpycorex/launcher.py:258`) runs `subprocess.Popen([java, ...])`
  with no `creationflags`. From a console-less parent (pythonw) this **opens a console
  window** for the JVM. The `Python` and `PyMMCorePlus` backends are unaffected.
- Icons available: `GUI/Icons/GladosIcon.ico`, `GladosSplash.png`, `GladosSplash_inv.png`.
- `pywin32` (`win32com`, `pythoncom`) is importable in `.venv`, but only transitively; it is
  not declared in `pyproject.toml`.
- Windows 11 has **no supported API to pin to the taskbar**. We create a Start Menu
  shortcut, and the user pins it once (right-click → Pin to taskbar).

## Phase L0 — Measure startup (before changing anything)

- [x] **L0.1** `observability/startup_timeline.py`: `mark(label)` records `perf_counter`
  deltas. t0 is the **process creation time** (`psutil.Process().create_time()`), so
  interpreter start and the click-to-`main` gap are counted too. Marks: main entered,
  imports done, Shared_data, backend dialog shown/closed, backend up, MicroscopeService
  started, viewer created, docks built, layout finalised, **first idle event loop** ("ready").
  At ready, log one INFO table.
- [x] **L0.2** `--startup-exit` flag: quit at ready and append the timeline to
  `docs/perf-startup.txt`, with a header naming the backend/config, in the same style as
  `--profile-runtime`. `make profile-startup-full` runs it 3× with `--auto-demo`
  (PyMMCorePlus) and 3× with the `demo_settings.mk` Python backend. Estimate: ~20–40 s per
  run, so < 5 min total.
- [x] **L0.3** Record the baseline (median of 3, cold *and* warm: first run after a reboot
  vs. repeat) in `docs/perf-startup.txt`. Set the L2 target from it.

### Baseline (2026-10-13, i7-1355U laptop, `main` @ `fdc7c10` + timeline only)

`make profile-startup-full`: 2 × 3 launches, ~2.3 min total. Times are seconds from
process start, median of 3 warm runs. "Cold" is the session's first launch, taken after
the edited modules had just been byte-compiled. It was not after a reboot.

| stage (step cost, s)              | PyMMCorePlus demo | Python + `MMConfig_demo.cfg` | cold (PyMMCorePlus) |
|-----------------------------------|------:|------:|------:|
| interpreter → `GUI_napari` start  | 0.2   | 0.2   | 1.0   |
| Glados module imports             | 7.9   | 5.5   | **25.3** |
| backend up (after config load / `start_headless`) | 1.5 | 1.5 | 3.8 |
| QApplication created              | 0.7   | 0.4   | 1.2   |
| napari viewer created             | 2.6   | 1.9   | 5.4   |
| **dock built: Controls**          | **7.7** | **6.5** | **17.3** |
| dock built: Multi-D acquisition   | 1.7   | 1.3   | 1.8   |
| everything else                   | ~1.1  | ~0.9  | ~3.8  |
| **ready**                         | **23.4** | **18.2** | **59.8** |

Findings that redirect L2:
- **The Controls dock (`microManagerControlsUI`) is the biggest single step**: 30–35 % of
  every warm start and 17 s cold. The log shows no GUI-thread hardware-block warnings
  (`note_gui_block`), so the cause is not yet known. **New L2.0: profile it first.**
- **Imports are the second-biggest cost and dominate cold starts** (25 s cold vs. 5.5–8 s
  warm). That points at disk and Defender scanning thousands of `.venv` files. L2.6
  (Defender exclusion, the user's decision) may be the largest cold-start lever. A
  splash (L2.1) is what makes that wait bearable.
- **"backend up" costs 1.5 s even on PyMMCorePlus, after the config has loaded**: the
  step covers `setCircularBufferMemoryFootprint(4096)` plus registering the resilient MDA
  engine. RSS at ready is ~4–4.8 GB with a 4 GB buffer. Check how that splits.
- `napariGlados` itself imports `pycromanager` at module scope (line 38), so L2.3
  (lazy pycromanager) must cover it as well as MIL.
- **Blocker found:** the `demo_settings.mk` backend (`Python` + `insiliscope.cfg`) segfaults in
  `start_headless`. This happens on unmodified `main` and in a bare script, so it is
  outside Glados; see `claude_decisions.md` (2026-10-13). The Python numbers above
  use `MMConfig_demo.cfg` in the same install.

**L2 target (accepted 2026-10-13):** warm ready ≤ 15 s on the PyMMCorePlus demo (from 23.4),
and a splash on screen ≤ 1.5 s after the click, on every launch, cold or warm.

- [x] **L2.0** Profile `microManagerControlsUI` construction and fix the top item(s).
  - **Cause:** the dock did almost no widget work. It was **importing libraries**: node
    discovery imports every Real_Time_Analysis module, and `BioImageModelZoo.py` ran three
    bioimageio compatibility patches **at module scope**. They imported `bioimageio.spec`,
    `bioimageio.core` and its PyTorch backend, so torch came in too. Several nodes also had
    a module-scope `from scipy import signal` (+ `scipy.stats`, ~1 s), unused in three of them.
  - **Fix:** `_ensure_bioimageio_patched()`, called before the first bioimageio import on
    each path (`getModel`, `setupSample`, `__init__`). scipy.signal now imports inside the
    functions that use it (or is dropped where unused). Regression test:
    `tests/test_node_packages_import_light.py`.
  - **Interleaved A/B** (fixed/original ×2, on a loaded machine: Firefox was using ~1.5 cores):
    Controls dock 2.8–4.0 s vs 10.0–14.5 s, ready **12.1–15.5 s vs 19.8–35.3 s**. The node
    packages import in ~0.1 s, down from 2.3 s standalone.
  - Not a GUI cost: `_readOneDstagePosition` showed 2.6 s in the profile. It runs on the
    owner thread (`submitHardware` is fire-and-forget) and was most likely starved of the
    GIL while the GUI thread imported; Python 3.13's cProfile records other threads too.
  - Still open: re-run `make profile-startup-full` on an idle machine for clean numbers.

## Phase L1 — One-click launcher (Windows)

- [ ] **L1.1** `[project.gui-scripts] gladosw = "glados_pycromanager.GUI.GUI_napari:main"`
  gives a windowed (no console) launcher. It is editable-install aware, so it still points
  at the source tree. Keep the console scripts for terminal/debug use.
- [ ] **L1.2 Console-less safety** at the very top of `main()`:
  - Under pythonw, `sys.stdout`/`sys.stderr` are `None`. `print` tolerates that;
    `sys.stderr.write` in third-party code raises. Redirect both to
    `<AppData>/Glados-PycroManager/logs/glados_console.log` (rotate on start).
  - A startup crash would be invisible. Install a `sys.excepthook` that logs and, when a
    `QApplication` exists, shows a `QMessageBox` with the log path.
  - Check that the `spawn` children (warm pool, subprocess RT nodes) are fine with
    `sys.executable == pythonw.exe`, and that they don't open console windows.
- [ ] **L1.3 JVM console window.** Try passing `java_loc=<MM install>/jre/bin/javaw.exe`
  to `start_headless` (the parameter already exists) when that file exists. Fall back to
  `java`. Verify on the JAVA backend that no window appears and the bridge still connects:
  the stdout `PIPE` read loop must still see the startup line under `javaw`. If it doesn't,
  fall back to a narrow `Popen` `creationflags=CREATE_NO_WINDOW` wrapper around the
  `mmpycorex` call.
- [ ] **L1.4 Taskbar identity.** Call
  `SetCurrentProcessExplicitAppUserModelID("Glados.Pycromanager")` before the first window
  is created, so the running window groups under the pinned icon rather than under
  "Python". The `.lnk` must carry the **same** AUMID (`PKEY_AppUserModel_ID`, set through
  pywin32 `propsys`). Add `pywin32; sys_platform == 'win32'` to `pyproject.toml` explicitly.
- [ ] **L1.5** `python -m glados_pycromanager.launcher install-shortcuts [--desktop]
  [--uninstall]` creates the Start Menu shortcut(s) (target `.venv\Scripts\gladosw.exe`,
  icon `GladosIcon.ico`, working dir = repo root, AUMID) and prints "right-click → Pin to
  taskbar". Shortcuts:
  - **Glados**: current behaviour (backend dialog).
  - **Glados (last setup)**: `--last`, a new flag that reuses the persisted
    `headless_backend`/`config_path`/`path`/memory settings through the existing CLI-override
    path and skips the dialog. If the saved config file is missing, fall back to the dialog.
  - **Glados (debug console)**: `glados.exe` (console visible) for tracebacks.
  `make shortcuts` wraps the command. Keep the arg/target construction a pure function so it
  can be unit-tested.
- [ ] **L1.6 Single instance.** A second launch while Glados runs should bring the existing
  window to the front rather than start a second process that fights over the camera / port
  4827. Use a `QLocalServer` named per user. Use `--allow-second-instance` to bypass.
- [ ] **L1.7 Stale-install warning.** If `pyproject.toml`'s dependency block changed since
  the last `make dev` (hash stamped into `.venv`), log a warning and show a status-bar note:
  "dependencies changed — run `make dev`". The launch is not blocked.

## Phase L2 — Startup speed (each item is an A/B against the L0 timeline; keep only wins)

- [x] **L2.1 Splash immediately.** Done as planned, with these details:
  - `GUI/startup.py` is the light entry point. The console scripts point at it, and
    `GUI_napari.py`'s `__main__` branch delegates to it before its heavy imports. It imports
    pymmcore, then PyQt5, creates the single `QApplication` and shows `GUI/startup_splash.py`'s
    `StartupSplash`. Only then does it import `GUI_napari`. `appSmall` is gone: the backend
    dialog runs in a local `QEventLoop` on the same app.
  - The splash follows the timeline marks (`STEP_AFTER_MARK`) and shows the next step plus
    elapsed seconds. It closes at ready.
  - The image is the **light** splash downscaled to 720 px (`GladosSplash_720.png`, from
    `scripts/make_splash_images.py`; the 4372 px source alone took ~350 ms to load). The
    backend dialog uses the same file.
  - **Not stay-on-top** (user request): it comes up on top once via a Win32
    topmost/not-topmost bring-to-front, so any window can then go over it. Once napari's
    window exists the splash becomes its *owned* window (`setTransientParent`), so it stays
    above Glados but not above other apps.
  - On screen 0.6–4 s after launch, depending on machine load. A screen grab confirmed that
    the repaint-only updates (no event loop) reach the screen.
- [ ] **L2.2 Defer the warm RT subprocess pool** until ready (`QTimer.singleShot` after
  layout finalisation). Today it spawns and re-imports the package tree while startup is
  still competing for the same cores.
- [ ] **L2.3 Lazy `pycromanager`** in `microscopeInterfaceLayer.py` / `GUI_napari.py`: import
  it only on the JAVA/Python branches (~1.2 s saved on PyMMCorePlus). Also check whether
  `ndstorage`/`dask.array` can follow.
- [ ] **L2.4 Investigate after L0:** napari/npe2 plugin discovery at viewer creation (napari[all]
  brings plugins), dock construction for tabs not visible at start, AppData node discovery,
  `cleanUpTemporaryFiles`. Optimise only what the timeline shows is large.
- [ ] **L2.5 Maybe: overlap backend start with GUI build.** JVM start / `loadSystemConfiguration`
  run serially before the viewer. Running them on a thread while napari builds could hide
  seconds. **Gated:** it touches the single-owner-thread invariant and the documented
  pymmcore/Qt crash. Only attempt it if L0 shows backend start dominates, and get user
  approval first.
- [ ] **L2.6 Document only (user decision):** `compileall` after `make dev`, and a Defender
  exclusion for `.venv`, which is often the biggest *cold* start cost on managed Windows. This
  is a security setting, so we document it and don't apply it.

## Phase L3 — Installable bootstrap (optional, for other lab PCs)

- [ ] **L3.1** `scripts/install_windows.ps1`: check/install `uv` and git, `uv venv --python 3.13`,
  `uv pip install -e .`, run `glados_pycromanager.launcher install-shortcuts`. Run it from an
  existing checkout, or have it clone to a chosen folder. Idempotent: re-running it is an
  update. Update `win_create_env.bat` (conda path) to call the same shortcut step, and
  update the README / UserManual (which still mentions Python 3.10).
- [ ] **L3.2** Optional "Update Glados" shortcut: `git pull` + `make dev`. Show the result in a
  console window.

## Verification gates

- After L0: the baseline table exists. Agree the L2 target with the user.
- After L1: clicking the pinned icon shows no console window on any backend, the window
  groups under the pinned icon, a code edit is live on the next click, and a second click
  focuses the existing window. Tests (`tests/test_launcher_*.py`, < 1 min): shortcut spec
  builder, `--last` arg resolution, stdout redirection, AUMID call (mocked ctypes), single
  instance guard.
- After L2: the timeline beats the baseline on median-of-3 for both backends, with no
  regression in `make test`.

## Open questions (defaults in brackets)

1. AUMID / shortcut names [`Glados.Pycromanager`, "Glados", "Glados (last setup)"].
2. Should the pinned icon default to the dialog or to `--last`? [dialog; `--last` as the second shortcut]
3. L3 scope: other machines (SMIPC rigs) now, or later? [later]
4. L2.5 (parallel backend start) is in scope only with explicit approval.
