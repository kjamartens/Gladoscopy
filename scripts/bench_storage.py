"""Hardware-free storage benchmark (T-D8): NDTiff vs OME-Zarr / OME-TIFF vs the scratch zarr.

Every (format, frame size) is written in its own subprocess, one synthetic uint16
frame at a time -- the way an acquisition hands frames over -- and a second, fresh
subprocess then opens the result and reads random single frames back, the way
napari scrubbing does. Frames are random noise (incompressible) cycled from a small
pre-generated pool, so the RNG is not what gets measured; every read is verified
against the frame that was written there.

Formats
-------
scratch-zarr            Glados' multiDstack display store: zarr-python
                        create_array, one frame per chunk, uncompressed
                        (napariGlados._create_mda_zarr).
ndtiff                  ndstorage.NDTiffDataset.put_image -- what the
                        pycromanager backends write.
ome-zarr                ome-writers with no overrides: exactly what
                        run_mda(output="x.ome.zarr") uses on pymmcore-plus 0.18
                        (backend auto = tensorstore here, 1-frame chunks, no shards).
ome-zarr-sharded        ome-writers / tensorstore, 1-frame chunks packed into
                        shards of --shard-frames frames along t.
ome-zarr-zarrpy-sharded The same shards through the zarr-python backend.
ome-tiff                ome-writers / tifffile: run_mda(output="x.ome.tiff").

Caveats, also written next to every result
------------------------------------------
* Reads are warm page cache: Windows cannot drop the OS file cache without
  admin rights. The reader runs in a fresh process, so Python-level caches are cold.
* The ome-writers rows drive OMEStream.append directly and so exclude the
  per-frame metadata conversion the pymmcore-plus sink adds (_frame_meta_to_ome).
* One machine, one disk.

Usage
-----
    python -m scripts.bench_storage
    python -m scripts.bench_storage --sizes 1024 --budget-mb 256 --formats ndtiff ome-zarr

Results are appended to docs/bench-storage.txt.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import io
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_FILE = REPO_ROOT / "docs" / "bench-storage.txt"

FORMATS = ["scratch-zarr", "ndtiff", "ome-zarr", "ome-zarr-sharded", "ome-zarr-zarrpy-sharded", "ome-tiff"]
POOL_SIZE = 8
N_READS = 50


def _frame_pool(h, w):
    rng = np.random.default_rng(1234)
    return [rng.integers(0, 2**16, (h, w), dtype=np.uint16) for _ in range(POOL_SIZE)]


def _data_path(fmt, root):
    if fmt == "ome-tiff":
        return root + ".ome.tiff"
    if fmt.startswith("ome-zarr"):
        return root + ".ome.zarr"
    return root


def _disk_usage(path):
    if os.path.isfile(path):
        return 1, os.path.getsize(path)
    files = [os.path.join(d, f) for d, _, fs in os.walk(path) for f in fs]
    return len(files), sum(os.path.getsize(f) for f in files)


class _PeakRSS(threading.Thread):
    """Samples this process' RSS every 5 ms; reports the peak above the baseline."""

    def __init__(self):
        super().__init__(daemon=True)
        import psutil

        self._proc = psutil.Process()
        self.baseline = self._proc.memory_info().rss
        self.peak = self.baseline
        self._halt = threading.Event()

    def run(self):
        while not self._halt.is_set():
            self.peak = max(self.peak, self._proc.memory_info().rss)
            self._halt.wait(0.005)

    def stop(self):
        self._halt.set()
        self.join()
        self.peak = max(self.peak, self._proc.memory_info().rss)
        return (self.peak - self.baseline) / 1e6


def _open_writer(fmt, root, n, h, w, shard_frames):
    """Returns (put(index, frame), close()) for one format."""
    if fmt == "scratch-zarr":
        import zarr

        arr = zarr.create_array(store=root, shape=(n, h, w), chunks=(1, h, w),
                                dtype="uint16", compressors=None, overwrite=True)
        return (lambda i, f: arr.__setitem__(i, f)), (lambda: None)
    if fmt == "ndtiff":
        from ndstorage import NDTiffDataset

        ds = NDTiffDataset(root, summary_metadata={"bench": True}, writable=True)

        def close():
            ds.finish()
            ds.close()

        return (lambda i, f: ds.put_image({"time": i}, f, {"i": i})), close

    import ome_writers as ow

    tdim = {"name": "t", "count": n, "type": "time"}
    if "sharded" in fmt:
        tdim.update(chunk_size=1, shard_size_chunks=min(shard_frames, n))
    dims = (ow.Dimension(**tdim),
            ow.Dimension(name="y", count=h, type="space"),
            ow.Dimension(name="x", count=w, type="space"))
    if fmt == "ome-tiff":
        fmt_obj = ow.OmeTiffFormat()
    else:
        backend = "zarr-python" if "zarrpy" in fmt else ("tensorstore" if "sharded" in fmt else "auto")
        fmt_obj = ow.OmeZarrFormat(backend=backend)
    settings = ow.AcquisitionSettings(root_path=_data_path(fmt, root), dimensions=dims,
                                      dtype="uint16", format=fmt_obj, overwrite=True)
    stream = ow.create_stream(settings)
    return (lambda i, f: stream.append(f)), stream.close


def _preimport(fmt):
    """Import the format's libraries before any clock or RSS baseline starts.

    ndstorage pulls in dask, ome-writers pulls in tensorstore/pydantic: seconds of
    import time and tens of MB that would otherwise be charged to the first write.
    """
    import zarr  # noqa: F401

    if fmt == "ndtiff":
        import ndstorage  # noqa: F401
    elif fmt == "ome-tiff":
        import ome_writers  # noqa: F401
        import tifffile  # noqa: F401
    elif fmt.startswith("ome-zarr"):
        import ome_writers  # noqa: F401
        import tensorstore  # noqa: F401


def worker_write(fmt, root, n, h, w, shard_frames):
    pool = _frame_pool(h, w)
    _preimport(fmt)
    rss = _PeakRSS()
    rss.start()
    t_setup = time.perf_counter()
    put, close = _open_writer(fmt, root, n, h, w, shard_frames)
    setup_ms = (time.perf_counter() - t_setup) * 1e3
    # Setup (stream creation, OME-XML) is paid once per acquisition, so it is
    # reported on its own rather than smeared across the per-frame figure.
    t_io = time.perf_counter()
    append_ms = []
    for i in range(n):
        t0 = time.perf_counter()
        put(i, pool[i % POOL_SIZE])
        append_ms.append((time.perf_counter() - t0) * 1e3)
    t_close = time.perf_counter()
    close()
    close_ms = (time.perf_counter() - t_close) * 1e3
    io_s = time.perf_counter() - t_io
    peak_mb = rss.stop()
    n_files, n_bytes = _disk_usage(_data_path(fmt, root))
    append_ms.sort()
    return {
        "setup_ms": setup_ms,
        "append_ms_mean": statistics.fmean(append_ms),
        "append_ms_p95": append_ms[int(0.95 * (len(append_ms) - 1))],
        "close_ms": close_ms,
        "effective_ms_per_frame": io_s * 1e3 / n,
        "mb_per_s": n * h * w * 2 / 1e6 / io_s,
        "files": n_files,
        "disk_mb": n_bytes / 1e6,
        "peak_rss_mb": peak_mb,
    }


def worker_read(fmt, root, n, h, w):
    pool = _frame_pool(h, w)
    idx = [int(i) for i in np.random.default_rng(7).integers(0, n, N_READS)]
    path = _data_path(fmt, root)
    _preimport(fmt)
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):  # NDTiff prints an index progress bar
        if fmt == "ndtiff":
            from ndstorage import NDTiffDataset

            ds = NDTiffDataset(path)
            get = lambda i: ds.read_image(time=i)  # noqa: E731
        elif fmt == "ome-tiff":
            import tifffile

            tf = tifffile.TiffFile(path)
            pages = tf.pages
            get = lambda i: pages[i].asarray()  # noqa: E731
        else:
            import zarr

            arr = zarr.open_array(path if fmt == "scratch-zarr" else os.path.join(path, "0"), mode="r")
            get = lambda i: arr[i]  # noqa: E731
        open_ms = (time.perf_counter() - t0) * 1e3
        read_ms, verified = [], True
        for i in idx:
            t1 = time.perf_counter()
            frame = np.asarray(get(i))
            read_ms.append((time.perf_counter() - t1) * 1e3)
            verified &= bool(frame.shape == (h, w) and np.array_equal(frame, pool[i % POOL_SIZE]))
    return {"open_ms": open_ms, "read_ms_first": read_ms[0],
            "read_ms_mean": statistics.fmean(read_ms[1:]), "verified": verified}


def _run_worker(args):
    cmd = [sys.executable, "-m", "scripts.bench_storage", *args]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT "):])
    raise RuntimeError(f"worker failed ({' '.join(args)}):\n{proc.stderr[-3000:]}")


def _versions():
    import importlib.metadata as md

    out = {}
    for dist in ("ndstorage", "ome-writers", "tensorstore", "zarr", "tifffile", "pymmcore-plus"):
        with contextlib.suppress(Exception):
            out[dist] = md.version(dist)
    return out


HEADER = (f"{'format':<24}{'size':>6}{'frames':>7}{'setup ms':>9}{'ms/frame':>10}{'p95 append':>11}{'close ms':>10}"
          f"{'MB/s':>8}{'files':>7}{'peakRSS':>9}{'open ms':>9}{'read ms':>9}  ok")


def _format_row(r):
    return (f"{r['format']:<24}{r['size']:>6}{r['frames']:>7}{r['setup_ms']:>9.0f}{r['effective_ms_per_frame']:>10.2f}"
            f"{r['append_ms_p95']:>11.2f}{r['close_ms']:>10.0f}{r['mb_per_s']:>8.0f}{r['files']:>7}"
            f"{r['peak_rss_mb']:>8.0f}M{r['open_ms']:>9.1f}{r['read_ms_mean']:>9.2f}  "
            f"{'yes' if r['verified'] else 'NO'}")


def _report(rows, args):
    lines = [
        f"=== bench_storage {datetime.datetime.now():%Y-%m-%d %H:%M} | {platform.platform()} | "
        f"{os.cpu_count()} cpus | budget {args.budget_mb} MB/config | shards {args.shard_frames} frames",
        f"    versions: {_versions()}",
        "    ms/frame = (all appends + close) / frames, setup excluded; peakRSS is above the post-import",
        "    baseline; reads are warm page cache, fresh process;",
        "    ome-writers rows exclude the pymmcore-plus sink's per-frame metadata conversion.",
        HEADER,
    ]
    lines += [_format_row(r) for r in rows]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sizes", type=int, nargs="+", default=[512, 1024, 2048])
    parser.add_argument("--budget-mb", type=int, default=384, help="Data written per configuration")
    parser.add_argument("--min-frames", type=int, default=48)
    parser.add_argument("--shard-frames", type=int, default=64)
    parser.add_argument("--formats", nargs="+", default=FORMATS, choices=FORMATS)
    parser.add_argument("--data-dir", default=tempfile.gettempdir())
    parser.add_argument("--no-append", action="store_true", help="Do not append to docs/bench-storage.txt")
    parser.add_argument("--worker", choices=["write", "read"], help=argparse.SUPPRESS)
    parser.add_argument("--fmt", help=argparse.SUPPRESS)
    parser.add_argument("--root", help=argparse.SUPPRESS)
    parser.add_argument("--n", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker:
        h = w = args.sizes[0]
        if args.worker == "write":
            result = worker_write(args.fmt, args.root, args.n, h, w, args.shard_frames)
        else:
            result = worker_read(args.fmt, args.root, args.n, h, w)
        print("RESULT " + json.dumps(result))
        return

    base = tempfile.mkdtemp(prefix="glados-bench-storage-", dir=args.data_dir)
    rows = []
    try:
        print(HEADER, flush=True)
        for size in args.sizes:
            n = max(args.min_frames, args.budget_mb * 1_000_000 // (size * size * 2))
            for fmt in args.formats:
                root = os.path.join(base, f"{fmt}-{size}")
                common = ["--fmt", fmt, "--root", root, "--n", str(n), "--sizes", str(size),
                          "--shard-frames", str(args.shard_frames)]
                row = {"format": fmt, "size": size, "frames": n}
                row.update(_run_worker(["--worker", "write", *common]))
                row.update(_run_worker(["--worker", "read", *common]))
                rows.append(row)
                print(_format_row(row), flush=True)
                path = _data_path(fmt, root)
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                elif os.path.exists(path):
                    os.remove(path)
    finally:
        shutil.rmtree(base, ignore_errors=True)

    report = _report(rows, args)
    print("\n" + report)
    if not args.no_append:
        RESULTS_FILE.parent.mkdir(exist_ok=True)
        with open(RESULTS_FILE, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")


if __name__ == "__main__":
    main()
