"""Picklable stand-ins for utils.realTimeAnalysis_init/run/end.

Used to unit-test AnalysisClass._subprocess_analysis_worker without depending
on the GUI-widget-derived rt_analysis_info dict format or any real analysis
node (e.g. diplib-based FFT_im.RealTimeFFT). Must stay at module level (not a
closure/lambda) so multiprocessing's 'spawn' start method can pickle them.
"""
from __future__ import annotations


class FakeRTAnalysisObject:
    """Mimics an RT-analysis node instance: accumulates a running sum on
    `self.total` (picklable state a real node like RealTimeFFT would store
    on `self` for `.visualise()` to read) and records init/end calls."""

    def __init__(self, initial_value=0):
        self.total = initial_value
        self.init_calls = 0
        self.end_calls = 0

    def snapshot(self):
        """Opt into the subprocess state mirror (T-G5).

        A node declares what `visualise()` needs either via "__snapshot_attrs__"
        in its `__function_metadata__` (the usual way, see FFT_im) or with this
        method, which takes precedence. Nothing is mirrored by default.
        """
        return {"total": self.total,
                "init_calls": self.init_calls,
                "end_calls": self.end_calls}


def fake_init_fn(rt_analysis_info, core=None, nodzInfo=None):
    assert core is None, "subprocess worker must never pass a live core into init"
    assert nodzInfo is None, "subprocess worker must never pass nodzInfo into init"
    obj = FakeRTAnalysisObject(initial_value=rt_analysis_info.get("initial_value", 0))
    obj.init_calls += 1
    return obj


def fake_run_fn(RT_analysis_object, rt_analysis_info, image, metadata, shared_data, core, nodzInfo=None):
    assert shared_data is None, "subprocess worker must never pass shared_data into run"
    assert core is None, "subprocess worker must never pass a live core into run"
    assert nodzInfo is None, "subprocess worker must never pass nodzInfo into run"
    RT_analysis_object.total += int(image.sum())
    return RT_analysis_object.total


def fake_end_fn(RT_analysis_object, rt_analysis_info, core, nodzInfo=None):
    RT_analysis_object.end_calls += 1
    return RT_analysis_object.end_calls


def fake_run_fn_raises(RT_analysis_object, rt_analysis_info, image, metadata, shared_data, core, nodzInfo=None):
    raise RuntimeError("synthetic run() failure")
