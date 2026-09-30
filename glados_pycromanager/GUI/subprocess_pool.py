"""
Pre-warms a single blank subprocess ahead of time so the *first*
`__runInSubprocess__` RT-analysis node started in a session doesn't pay the
full spawn + package-tree (+ node-specific heavy library) import cost on the
critical path of pressing "start". See CLAUDE.md's RT-analysis
subprocess-isolation section for the surrounding design (this pool handles the
first-ever start; AnalysisClass.py's `_rt_subprocess_cache` handles repeated
restarts of the same node).
"""
import logging
import multiprocessing as mp
import queue as std_queue


def _blank_worker_bootstrap(assign_queue, ready_queue, in_queue, out_queue,
                            stop_event, control_in_queue, control_out_queue):
    """Runs in the pre-spawned child. Front-loads the generic (node-independent)
    import cost, then idles waiting to be handed a real node to run.

    Every channel the real worker will use (frame in/out, stop event, control
    pair) is passed in *here*, as Process args, because a multiprocessing
    Queue/Event can only cross a process boundary by inheritance -- putting one
    into `assign_queue` raises "Queue objects should only be shared between
    processes through inheritance" on the parent's queue-feeder thread. So the
    pool creates the channels at spawn time and `try_claim()` hands them to the
    caller; `assign_queue` then only ever carries plain picklable data.

    Kept as a free module-level function (not a method/closure) so it's
    picklable for multiprocessing's 'spawn' start method (required on
    Windows), mirroring `AnalysisClass._subprocess_analysis_worker`.
    """
    try:
        import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis  # noqa: F401
    except Exception:
        logging.exception('subprocess_pool: failed to pre-import Real_Time_Analysis package')

    # Only FFT_im.py opts into __runInSubprocess__ today, and its diplib import
    # is documented as taking "a few seconds" on its own (see FFT_im.py) --
    # pre-import it here too. If more nodes opt into subprocess isolation later
    # with their own heavy libraries, extend this list (or generalize via an
    # optional "__prewarm_imports__" key in a node's __function_metadata__).
    try:
        # diplib.viewer assumes IPython.terminal.pt_inputhooks is already an
        # attribute of IPython.terminal whenever 'IPython' is in sys.modules,
        # but modern IPython only sets that attribute once the submodule has
        # actually been imported -- pre-import it ourselves to dodge diplib's
        # `terminal.pt_inputhooks.register(...)` AttributeError.
        import sys
        if 'IPython' in sys.modules:
            import IPython.terminal.pt_inputhooks  # noqa: F401
        import diplib  # noqa: F401
    except ImportError:
        pass
    except Exception:
        logging.exception('subprocess_pool: failed to pre-import diplib')

    try:
        ready_queue.put(True)
    except Exception:
        logging.exception('subprocess_pool: failed to signal ready, exiting blank worker')
        return

    try:
        assignment = assign_queue.get()
    except (EOFError, OSError):
        return
    if assignment is None:  # pool torn down / not claimed before shutdown
        return

    rt_analysis_info, log_level = assignment
    # Imported here (not at module scope) to avoid AnalysisClass.py <->
    # subprocess_pool.py forming an import cycle at module-load time.
    from glados_pycromanager.GUI.AnalysisClass import _subprocess_analysis_worker
    _subprocess_analysis_worker(
        rt_analysis_info, in_queue, out_queue, stop_event,
        control_in_queue=control_in_queue, control_out_queue=control_out_queue,
        log_level=log_level,
    )


class WarmSubprocessPool:
    """Keeps at most one pre-spawned, pre-imported 'blank' worker process ready
    to be claimed by the next AnalysisProcess_customFunction cache-miss.

    Not thread-safe against concurrent try_claim() calls from multiple
    threads -- in practice AnalysisProcess_customFunction is only ever
    constructed on the Qt GUI thread, so this isn't a concern.
    """

    def __init__(self):
        self._ctx = mp.get_context('spawn')
        self._assign_queue = None
        self._ready_queue = None
        self._channels = None
        self._process = None

    def start(self):
        """Spawn a new blank process if one isn't already warming/warm. Safe to
        call repeatedly (e.g. after a claim, or redundantly at app startup)."""
        if self._process is not None:
            return
        self._assign_queue = self._ctx.Queue(maxsize=1)
        self._ready_queue = self._ctx.Queue(maxsize=1)
        # The frame/control channels are created *here*, before the spawn, and
        # inherited by the child as Process args -- they cannot be handed over
        # later through _assign_queue (see _blank_worker_bootstrap's docstring).
        # maxsize/type must stay in step with the cold-start path in
        # AnalysisProcess_customFunction.__init__, which is what the claiming
        # caller would otherwise have built for itself.
        self._channels = {
            'in_queue': self._ctx.Queue(maxsize=2),
            'out_queue': self._ctx.Queue(maxsize=2),
            'stop_event': self._ctx.Event(),
            'control_in_queue': self._ctx.Queue(maxsize=2),
            'control_out_queue': self._ctx.Queue(maxsize=2),
        }
        self._process = self._ctx.Process(
            target=_blank_worker_bootstrap,
            args=(self._assign_queue, self._ready_queue,
                  self._channels['in_queue'], self._channels['out_queue'],
                  self._channels['stop_event'],
                  self._channels['control_in_queue'],
                  self._channels['control_out_queue']),
            daemon=True,
        )
        self._process.start()

    def try_claim(self):
        """Returns (process, assign_queue, channels) if a warm process is ready
        right now, else None (never blocks -- this is called from the Qt GUI
        thread). On success, the caller owns the process, must use the returned
        `channels` dict (in_queue/out_queue/stop_event/control_in_queue/
        control_out_queue -- the child already inherited these) rather than
        queues of its own, and must assign_queue.put((analysisInfo, log_level));
        a replacement blank process is started in the background immediately."""
        if self._process is None or self._ready_queue is None:
            # Not started yet (or already claimed and not yet replenished) --
            # kick off a spawn for next time either way.
            self.start()
            return None
        try:
            self._ready_queue.get_nowait()
        except std_queue.Empty:
            return None
        except Exception:
            logging.exception('subprocess_pool: failed to check ready queue')
            return None
        claimed = (self._process, self._assign_queue, self._channels)
        self._process = None
        self._assign_queue = None
        self._ready_queue = None
        self._channels = None
        self.start()  # replenish in the background for the next claim
        return claimed

    def terminate(self):
        """Best-effort, non-blocking teardown -- used on app quit, where
        GUI_napari.py deliberately skips normal cleanup (see the os._exit(0)
        comment there) to avoid a hang."""
        if self._process is not None:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._process = None
            self._assign_queue = None
            self._ready_queue = None
            self._channels = None
