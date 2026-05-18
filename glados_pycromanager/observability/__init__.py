"""Cross-cutting observability hooks (logging, exception capture).

Phase 11 will move the logger setup here. Phase 10.13 introduces the
global ``sys.excepthook`` / ``threading.excepthook`` / Qt message
handler so uncaught exceptions land in the rotating log file rather
than silently disappearing from a worker thread.
"""
