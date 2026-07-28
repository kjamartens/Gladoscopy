"""Spike: compare a bare pyqtgraph ImageItem against napari's Image layer
for raw live-preview frame updates. See docs/bench-live-display.md for the
result and decision (spoiler: napari wins; this script is kept only for
reproducibility, not because pyqtgraph is being adopted).

IMPORTANT (Windows): PyQt5 must be imported before pyqtgraph, or the
process crashes with no traceback (same class of Qt-binding-order issue
documented in docs/perf-runtime-recipe.md for napari vs pymmcore-plus).

Usage:
    python -m scripts.bench_pyqtgraph_vs_napari
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("NAPARI_ASYNC", "1")
os.environ.setdefault("NAPARI_OCTREE", "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from PyQt5.QtWidgets import QApplication  # noqa: E402 -- must precede pyqtgraph import, see module docstring

FRAME_SHAPE = (2048, 2048)
N_FRAMES = 80


def _time_updates(update_fn, process_events) -> float:
    rng = np.random.default_rng(0)
    frame0 = rng.integers(0, 65535, size=FRAME_SHAPE, dtype=np.uint16)
    update_fn(frame0)
    process_events()
    time.sleep(0.2)

    timings = []
    for i in range(N_FRAMES):
        frame = rng.integers(0, 65535, size=FRAME_SHAPE, dtype=np.uint16)
        t0 = time.perf_counter()
        update_fn(frame)
        process_events()
        t1 = time.perf_counter()
        if i > 0:
            timings.append((t1 - t0) * 1000.0)
    return sum(timings) / len(timings)


def bench_napari(app) -> float:
    import napari

    viewer = napari.Viewer(show=True)
    layer = viewer.add_image(np.zeros(FRAME_SHAPE, dtype=np.uint16), name="Live")
    layer._keep_auto_contrast = False
    layer.contrast_limits = (0, 65535)

    def update(frame):
        layer.data[:] = frame
        layer.refresh()

    mean_ms = _time_updates(update, app.processEvents)
    viewer.close()
    return mean_ms


def bench_pyqtgraph_bare_imageitem(app) -> float:
    import pyqtgraph as pg

    win = pg.GraphicsLayoutWidget()
    win.show()
    view_box = win.addViewBox()
    img_item = pg.ImageItem()
    view_box.addItem(img_item)

    def update(frame):
        img_item.setImage(frame, autoLevels=False)

    mean_ms = _time_updates(update, app.processEvents)
    win.close()
    return mean_ms


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    napari_ms = bench_napari(app)
    pg_ms = bench_pyqtgraph_bare_imageitem(app)
    print(f"napari Image layer (fixed contrast):     {napari_ms:.3f} ms/frame @ {FRAME_SHAPE}")
    print(f"bare pyqtgraph ImageItem (no chrome):     {pg_ms:.3f} ms/frame @ {FRAME_SHAPE}")


if __name__ == "__main__":
    main()
