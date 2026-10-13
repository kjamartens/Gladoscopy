"""L2.2 of claude_launcher_project.md: the warm RT-analysis pool starts once startup is ready.

Started right after ``Shared_data()``, its child re-imported the package tree and diplib
while the GUI was still being built, competing for the same cores: deferring it took
the PyMMCorePlus demo's ready from 16.7 to 10.9 s (median of 5). Starting it after
``apply_foreground_scheduling_hints`` also lets the child inherit the priority class.
"""

import inspect

from glados_pycromanager.GUI import GUI_napari


def _main_source():
    return inspect.getsource(GUI_napari.main)


def test_pool_starts_only_in_the_startup_ready_callback():
    src = _main_source()
    assert src.count('_rt_subprocess_pool.start()') == 1
    ready_cb = src.index('def _on_startup_ready')
    registered = src.index('call_when_startup_ready(_on_startup_ready)')
    assert ready_cb < src.index('_rt_subprocess_pool.start()') < registered


def test_pool_starts_after_the_scheduling_hints_and_not_for_startup_exit():
    src = _main_source()
    start = src.index('_rt_subprocess_pool.start()')
    assert src.index('apply_foreground_scheduling_hints(') < start
    callback = src[src.index('def _on_startup_ready'):start]
    exit_branch = callback[callback.index('if args.startup_exit:'):]
    assert 'return' in exit_branch  # a --startup-exit run quits without spawning it
