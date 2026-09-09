"""Tests for GUI/subprocess_pool.py's WarmSubprocessPool hand-off.

The bug these pin: the pool used to spawn a blank child and then send the real
node's *channels* (in/out queues, stop event, control queue pair) to it through
`assign_queue`. multiprocessing forbids that -- a Queue/Event can only cross a
process boundary by inheritance -- and the failure surfaces as a RuntimeError
("Queue objects should only be shared between processes through inheritance")
raised on the parent's queue-feeder *thread*, so the parent sails on while the
child blocks forever on assign_queue.get() and the node never processes a frame.
The pool therefore creates every channel before the spawn and hands it back from
try_claim(); only plain picklable data goes through assign_queue.
"""
from __future__ import annotations

import multiprocessing as mp
import pickle
import queue as std_queue
import sys
import time

import numpy as np
import pytest

from glados_pycromanager.GUI.subprocess_pool import WarmSubprocessPool

_CHANNEL_KEYS = {'in_queue', 'out_queue', 'stop_event',
                 'control_in_queue', 'control_out_queue'}


def test_multiprocessing_queue_cannot_be_pickled():
    """Pins the constraint the pool design exists to satisfy. If a future
    refactor puts a channel back into the assign_queue payload, this is the
    rule it will be breaking -- and it breaks silently at runtime."""
    with pytest.raises(RuntimeError, match='inheritance'):
        pickle.dumps(mp.get_context('spawn').Queue())


def _claim_when_warm(pool, timeout=120):
    """try_claim() is deliberately non-blocking (it's called from the Qt GUI
    thread); poll it until the cold spawn + package-tree import finishes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        claimed = pool.try_claim()
        if claimed is not None:
            return claimed
        time.sleep(0.2)
    raise AssertionError(f'no warm pool process became ready within {timeout}s')


@pytest.mark.slow
def test_claim_returns_inherited_channels_and_a_picklable_assignment():
    pool = WarmSubprocessPool()
    pool.start()
    try:
        process, assign_queue, channels = _claim_when_warm(pool)
        assert process.is_alive()
        assert set(channels) == _CHANNEL_KEYS
        # The documented payload -- and nothing but plain data in it.
        pickle.dumps(({'__selectedDropdownEntryRTAnalysis__': 'x'}, 'INFO'))
        assign_queue.put(None)  # release the claimed child without running a node
        process.join(timeout=20)
        assert not process.is_alive()
    finally:
        pool.terminate()


@pytest.mark.slow
def test_claimed_pool_process_runs_the_real_fft_node_end_to_end():
    """The regression test proper: claim a warm process, assign it the real FFT
    node, and push a frame through the *inherited* channels. Before the fix the
    assignment never arrived and this hung until the timeout."""
    # diplib/IPython pt_inputhooks gotcha (see CLAUDE.md): once any earlier test
    # has pulled IPython into sys.modules -- napari does -- `import diplib`
    # raises AttributeError, which importorskip does not catch.
    if 'IPython' in sys.modules:
        import IPython.terminal.pt_inputhooks  # noqa: F401
    pytest.importorskip('diplib')

    # One LineEdit# entry per kwarg in RealTimeFFT's __function_metadata__ --
    # see tests/test_analysis_process.py for why a minimal subset won't do.
    rt_analysis_info = {
        "__selectedDropdownEntryRTAnalysis__": "Real-Time FFT",
        "__displayNameFunctionNameMap__": [("Real-Time FFT", "FFT_im.RealTimeFFT")],
        "LineEdit#FFT_im.RealTimeFFT#LogScale": "True",
        "LineEdit#FFT_im.RealTimeFFT#WindowTaper": "False",
        "LineEdit#FFT_im.RealTimeFFT#WindowTaperStrength": "0.25",
    }
    pool = WarmSubprocessPool()
    pool.start()
    process = None
    channels = None
    try:
        process, assign_queue, channels = _claim_when_warm(pool)
        assign_queue.put((rt_analysis_info, 'INFO'))

        channels['in_queue'].put((np.random.rand(64, 64).astype(np.uint16), {'frame': 0}))
        deadline = time.monotonic() + 90
        while True:
            try:
                _result, metadata, snapshot = channels['out_queue'].get(timeout=0.5)
                break
            except std_queue.Empty:
                if not process.is_alive():
                    raise AssertionError(
                        f'claimed pool process died (exitcode={process.exitcode}) '
                        'before returning a result') from None
                if time.monotonic() > deadline:
                    raise AssertionError(
                        'claimed pool process never processed a frame -- the '
                        'assignment did not reach the child') from None
        assert metadata == {'frame': 0}
        assert snapshot['fft_display'].shape == (64, 64)
    finally:
        if channels is not None:
            channels['stop_event'].set()
            channels['in_queue'].put(None)
        if process is not None:
            process.join(timeout=20)
            assert not process.is_alive()
        pool.terminate()
