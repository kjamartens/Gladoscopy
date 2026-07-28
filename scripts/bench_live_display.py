"""Hardware-free micro-benchmark for the live video feed display path.

Isolates the "camera frame -> visible napari layer" step
(`napariGlados.napariUpdateLive` / `_napariUpdateLive_locked`) from
acquisition/hardware concerns, so display-throughput candidates can be
A/B tested without a Micro-Manager backend. See docs/bench-live-display.md
for methodology and results.

Calls the real production functions directly (not a reimplementation) by
setting the `napariGlados` module-level `shared_data` global the same way
`runNapariPycroManager` does, and feeding synthetic frames through a
lightweight fake `shared_data`/`MILcore` (following the
`tests/fakes/fake_mil.py` pattern) instead of a real Micro-Manager core.

Usage:
    python -m scripts.bench_live_display --mode layer-update
    python -m scripts.bench_live_display --mode layer-update --contrast fixed
    python -m scripts.bench_live_display --mode layer-update --existing-layers 20
    python -m scripts.bench_live_display --mode queue-depth

Results are appended to docs/bench-live-display.txt.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import logging
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

os.environ.setdefault("NAPARI_ASYNC", "1")
os.environ.setdefault("NAPARI_OCTREE", "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RESULTS_FILE = REPO_ROOT / "docs" / "bench-live-display.txt"

FRAME_SIZES = [(512, 512), (1024, 1024), (2048, 2048)]


@dataclass
class LayerUpdateResult:
    label: str
    frame_shape: tuple
    first_frame_s: float
    steady_ms_mean: float
    steady_ms_p95: float
    n_frames: int


def _build_fake_shared_data(existing_layers: int, java_latency_ms: float, exposure_cached: bool):
    """A minimal stand-in for `Shared_data`, providing only the attributes
    `napariUpdateLive`/`_napariUpdateLive_locked` actually read. Deliberately
    not the real `Shared_data` (a `QObject` with heavyweight `__init__`
    side effects) -- mirrors the same "build only what's needed" approach
    as `tests/fakes/fake_mil.py`.
    """
    from tests.fakes.fake_mil import FakeMicroscopeInterfaceLayer

    from glados_pycromanager.GUI.sharedFunctions import Config

    mil = FakeMicroscopeInterfaceLayer()
    mil.populate_demo_state()

    real_get_exposure = mil.get_exposure
    call_count = {"n": 0}

    def _simulated_java_get_exposure():
        # No real Java bridge is available in this dev environment; model
        # its round-trip cost with a configurable sleep so the exposure-cache
        # candidate can be evaluated even without PYCROMANAGER_JAVA hardware.
        # See docs/bench-live-display.md for the caveat this implies.
        call_count["n"] += 1
        if java_latency_ms > 0:
            time.sleep(java_latency_ms / 1000.0)
        return real_get_exposure()

    if exposure_cached:
        _cache = {}

        def _cached_get_exposure():
            if "value" not in _cache:
                _cache["value"] = _simulated_java_get_exposure()
            return _cache["value"]

        mil.get_exposure = _cached_get_exposure
    else:
        mil.get_exposure = _simulated_java_get_exposure

    class _FakeSharedData:
        pass

    shared_data = _FakeSharedData()
    shared_data.MILcore = mil
    shared_data.config = Config()
    shared_data.config.mda_config.vis_method = "frameByFrame"
    shared_data.last_display_update_time = 0.0
    shared_data.liveModeUpdateOngoing = False
    shared_data.mdaZarrData = {}
    shared_data.mdaZarrTempDir = None
    shared_data.allMDAslicesRendered = {}
    shared_data._mdaModeParams = None
    shared_data._exposure_call_count = call_count
    return shared_data


def _make_viewer(existing_layers: int):
    import napari

    viewer = napari.Viewer(show=True)
    for i in range(existing_layers):
        viewer.add_image(np.zeros((8, 8), dtype=np.uint16), name=f"DummyLayer{i}")
    return viewer


def run_layer_update_benchmark(
    frame_shape: tuple,
    n_frames: int,
    contrast: str,
    existing_layers: int,
    java_latency_ms: float,
    exposure_cached: bool,
    logging_level: int,
) -> LayerUpdateResult:
    import glados_pycromanager.GUI.napariGlados as napariGlados
    from PyQt5.QtWidgets import QApplication

    logging.getLogger().setLevel(logging_level)

    app = QApplication.instance() or QApplication(sys.argv)
    viewer = _make_viewer(existing_layers)
    shared_data = _build_fake_shared_data(existing_layers, java_latency_ms, exposure_cached)
    napariGlados.shared_data = shared_data

    rng = np.random.default_rng(0)
    steady_timings = []
    first_frame_s = 0.0

    for i in range(n_frames):
        frame = rng.integers(0, 65535, size=frame_shape, dtype=np.uint16)
        data_structure = {
            "data": (frame, {}),
            "napariViewer": viewer,
            "acqState": True,
            "core": None,
            "image_queue_analysis": [],
            "analysisThreads": [],
            "layer_name": "Live",
            "layer_color_map": "gray",
            "finalisationProcedure": False,
        }
        # Force the rate-limit gate to always pass so every synthetic frame
        # actually executes the update body (we're measuring per-frame
        # display cost, not the FPS throttle).
        shared_data.last_display_update_time = 0.0

        t0 = time.perf_counter()
        napariGlados.napariUpdateLive(data_structure)
        app.processEvents()
        t1 = time.perf_counter()

        if i == 0:
            first_frame_s = t1 - t0
            live_layer = viewer.layers[[j for j, layer in enumerate(viewer.layers) if layer.name == "Live"][0]]
            if contrast == "fixed":
                live_layer._keep_auto_contrast = False
                live_layer.contrast_limits = (0, 65535)
        else:
            steady_timings.append((t1 - t0) * 1000.0)

    viewer.close()

    steady_timings.sort()
    p95_idx = max(0, int(len(steady_timings) * 0.95) - 1)
    return LayerUpdateResult(
        label=(
            f"contrast={contrast} existing_layers={existing_layers} "
            f"java_latency_ms={java_latency_ms} exposure_cached={exposure_cached} "
            f"log_level={logging.getLevelName(logging_level)}"
        ),
        frame_shape=frame_shape,
        first_frame_s=first_frame_s,
        steady_ms_mean=statistics.mean(steady_timings) if steady_timings else float("nan"),
        steady_ms_p95=steady_timings[p95_idx] if steady_timings else float("nan"),
        n_frames=n_frames,
    )


def run_queue_depth_simulation(render_cost_ms: float, arrival_interval_ms: float, duration_s: float):
    """Analytical (non-threaded) simulation of the visualisation queue's
    frame-drop behavior at different `maxlen` values, grounded in a real
    measured `render_cost_ms` (from `run_layer_update_benchmark`).

    Model: frames arrive every `arrival_interval_ms`. The UI thread can only
    start rendering the next queued frame once it finishes the previous one
    (`render_cost_ms`). A queue of depth `maxlen` holds unrendered frames;
    once full, the *newest* arriving frame is dropped (matches the
    production code's "if len(queue) < maxlen: append" behavior -- newer
    frames are dropped, not older ones).
    """
    results = []
    n_arrivals = int(duration_s * 1000 / arrival_interval_ms)
    for maxlen in (1, 2, 3):
        queue = 0
        rendered = 0
        dropped = 0
        next_render_free_at = 0.0
        t = 0.0
        for _ in range(n_arrivals):
            # Drain what the UI thread would have finished by now.
            while queue > 0 and next_render_free_at <= t:
                queue -= 1
                rendered += 1
                next_render_free_at += render_cost_ms
            if queue < maxlen:
                queue += 1
            else:
                dropped += 1
            t += arrival_interval_ms
        results.append((maxlen, rendered, dropped, n_arrivals))
    return results


def _write_results(lines: list[str]):
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(RESULTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n=== bench_live_display run {timestamp} ===\n")
        for line in lines:
            f.write(line + "\n")
            print(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["layer-update", "queue-depth"], default="layer-update")
    parser.add_argument("--frames", type=int, default=60, help="Synthetic frames per configuration (layer-update mode)")
    parser.add_argument("--contrast", choices=["auto", "fixed"], default="auto")
    parser.add_argument("--existing-layers", type=int, default=0, help="Pre-populate the viewer with N dummy layers to exercise the layer-lookup scan cost")
    parser.add_argument("--java-latency-ms", type=float, default=0.0, help="Modeled PYCROMANAGER_JAVA get_exposure() round-trip cost (no real Java bridge in this dev environment; 0 = disabled)")
    parser.add_argument("--exposure-cached", action="store_true", help="Simulate a single-value exposure cache instead of calling get_exposure() every frame")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING"], default="WARNING")
    parser.add_argument("--render-cost-ms", type=float, default=5.0, help="queue-depth mode: measured steady-state render cost to model against")
    parser.add_argument("--arrival-interval-ms", type=float, default=2.0, help="queue-depth mode: simulated camera frame period")
    parser.add_argument("--duration-s", type=float, default=5.0, help="queue-depth mode: simulated session length")
    args = parser.parse_args()

    if args.mode == "layer-update":
        lines = [f"mode=layer-update frames_per_config={args.frames}"]
        for shape in FRAME_SIZES:
            result = run_layer_update_benchmark(
                frame_shape=shape,
                n_frames=args.frames,
                contrast=args.contrast,
                existing_layers=args.existing_layers,
                java_latency_ms=args.java_latency_ms,
                exposure_cached=args.exposure_cached,
                logging_level=getattr(logging, args.log_level),
            )
            lines.append(
                f"  shape={result.frame_shape} {result.label} "
                f"first_frame={result.first_frame_s:.3f}s "
                f"steady_mean={result.steady_ms_mean:.3f}ms "
                f"steady_p95={result.steady_ms_p95:.3f}ms "
                f"(n={result.n_frames - 1})"
            )
        _write_results(lines)
    else:
        lines = [
            f"mode=queue-depth render_cost_ms={args.render_cost_ms} "
            f"arrival_interval_ms={args.arrival_interval_ms} duration_s={args.duration_s}"
        ]
        for maxlen, rendered, dropped, n_arrivals in run_queue_depth_simulation(
            args.render_cost_ms, args.arrival_interval_ms, args.duration_s
        ):
            lines.append(
                f"  maxlen={maxlen} arrivals={n_arrivals} rendered={rendered} "
                f"dropped={dropped} ({100 * dropped / n_arrivals:.1f}% dropped)"
            )
        _write_results(lines)


if __name__ == "__main__":
    main()
