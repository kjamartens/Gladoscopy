"""Launch Glados N times with ``--startup-exit`` and summarise the startup timeline.

Each launch appends its own timeline to ``docs/perf-startup.txt``; this script reads
back what each run appended, takes the per-stage median and appends that as a summary
block. Everything after ``--`` is passed to Glados and must make the launch popup-free::

    python -m scripts.profile_startup_full --runs 3 -- --auto-demo
    python -m scripts.profile_startup_full --runs 3 -- --backend Python --config X.cfg --mm-path Y

Runs are sequential (they would compete for CPU otherwise) and each is killed after
``--timeout`` seconds, so a launch that never reaches "ready" cannot hang the script.
"""

import argparse
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPORT_FILE = Path(__file__).resolve().parents[1] / 'docs' / 'perf-startup.txt'
_ROW = re.compile(r'^(?P<label>.*?)\s+(?P<at>-?\d+\.\d+)\s+(?P<step>-?\d+\.\d+)$')


def parse_timeline(text: str) -> list[tuple[str, float]]:
    """``[(label, seconds since process start)]`` from one ``format_report`` table."""
    rows = []
    for line in text.splitlines():
        match = _ROW.match(line.rstrip())
        if match and not line.startswith('stage '):
            rows.append((match['label'], float(match['at'])))
    return rows


def median_timeline(runs: list[list[tuple[str, float]]]) -> list[tuple[str, float, float, int]]:
    """``[(label, median at, median step, n runs that had it)]``, in first-seen order.

    The step is the median of each run's own step, not the difference of two medians,
    so it stays the typical cost of that stage.
    """
    order: list[str] = []
    ats: dict[str, list[float]] = {}
    steps: dict[str, list[float]] = {}
    for rows in runs:
        prev = 0.0
        for label, at in rows:
            if label not in ats:
                order.append(label)
                ats[label], steps[label] = [], []
            ats[label].append(at)
            steps[label].append(at - prev)
            prev = at
    return [(label, statistics.median(ats[label]), statistics.median(steps[label]),
             len(ats[label])) for label in order]


def format_summary(summary, walls: list[float], n_runs: int, glados_args: list[str]) -> str:
    width = max(len(label) for label, *_ in summary)
    lines = [f"\n=== Startup summary {time.strftime('%Y-%m-%d %H:%M:%S')} "
             f"(median of {n_runs}, {' '.join(glados_args)}) ===",
             f"{'stage':<{width}}  {'at (s)':>8}  {'step (s)':>8}"]
    for label, at, step, n in summary:
        note = '' if n == n_runs else f'  (in {n}/{n_runs} runs)'
        lines.append(f'{label:<{width}}  {at:8.2f}  {step:8.2f}{note}')
    lines.append('wall time per launch (s): ' + ', '.join(f'{w:.1f}' for w in walls)
                 + f'  (median {statistics.median(walls):.1f})')
    return '\n'.join(lines) + '\n'


def run_once(glados_args: list[str], timeout_s: float) -> tuple[str, float]:
    """One launch; returns (the text it appended to REPORT_FILE, wall seconds)."""
    before = REPORT_FILE.stat().st_size if REPORT_FILE.exists() else 0
    cmd = [sys.executable, '-m', 'glados_pycromanager.GUI.GUI_napari', *glados_args,
           '--startup-exit']
    t0 = time.perf_counter()
    try:
        subprocess.run(cmd, timeout=timeout_s, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        print(f'  launch timed out after {timeout_s:.0f} s', file=sys.stderr)
    wall = time.perf_counter() - t0
    if not REPORT_FILE.exists():
        return '', wall
    with REPORT_FILE.open('rb') as f:
        f.seek(before)
        return f.read().decode('utf-8', errors='replace'), wall


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=180.0,
                        help='Seconds before a single launch is killed (default 180).')
    parser.add_argument('glados_args', nargs=argparse.REMAINDER,
                        help='Arguments for Glados, after a literal --.')
    args = parser.parse_args(argv)
    glados_args = [a for a in args.glados_args if a != '--']
    if not glados_args:
        parser.error('pass the Glados launch arguments after --, e.g. -- --auto-demo')

    runs, walls = [], []
    for i in range(args.runs):
        print(f'run {i + 1}/{args.runs}: {" ".join(glados_args)}')
        text, wall = run_once(glados_args, args.timeout)
        rows = parse_timeline(text)
        if not rows:
            print('  no timeline written -- did the launch reach "ready"?', file=sys.stderr)
            continue
        runs.append(rows)
        walls.append(wall)
        print(f'  ready at {rows[-1][1]:.2f} s, wall {wall:.1f} s')
    if not runs:
        return 1
    summary = format_summary(median_timeline(runs), walls, len(runs), glados_args)
    with REPORT_FILE.open('a', encoding='utf-8') as f:
        f.write(summary)
    print(summary)
    return 0


if __name__ == '__main__':
    sys.exit(main())
