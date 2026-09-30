"""Centralized async logger for Glados-PycroManager (Phase 11.1).

Call :func:`set_up_logger` once at application startup (before any other
logging).  It configures the root logger with:

* Two rotating file handlers (DEBUG and INFO) writing to the Glados
  AppData folder.
* A colored console handler when stdout is a TTY; plain otherwise.
* An async :class:`logging.handlers.QueueListener` so file I/O never
  blocks the calling thread.

Old log files (> 1 week) are pruned on each call.
"""

from __future__ import annotations

import atexit
import datetime
import logging
import logging.handlers
import os
import sys
from queue import Queue

import appdirs

_APP_NAME = "Glados-PycroManager"

_console_handler: logging.StreamHandler | None = None


class ColoredFormatter(logging.Formatter):
    """ANSI-colored formatter for terminal output."""

    _grey = "\x1b[38;20m"
    _yellow = "\x1b[33;20m"
    _red = "\x1b[31;20m"
    _bold_red = "\x1b[31;1m"
    _cyan = "\x1b[36;20m"
    _green = "\x1b[32;20m"
    _reset = "\x1b[0m"

    FORMATS = {
        logging.DEBUG: _grey + "%(asctime)s [%(levelname)-8s]" + _reset + " %(message)s " + _cyan + "[%(filename)s:%(lineno)d]" + _reset,
        logging.INFO: _green + "%(asctime)s [%(levelname)-8s]" + _reset + " %(message)s " + _cyan + "[%(filename)s:%(lineno)d]" + _reset,
        logging.WARNING: _yellow + "%(asctime)s [%(levelname)-8s]" + _reset + " %(message)s " + _cyan + "[%(filename)s:%(lineno)d]" + _reset,
        logging.ERROR: _red + "%(asctime)s [%(levelname)-8s]" + _reset + " %(message)s " + _cyan + "[%(filename)s:%(lineno)d]" + _reset,
        logging.CRITICAL: _bold_red + "%(asctime)s [%(levelname)-8s]" + _reset + " %(message)s " + _cyan + "[%(filename)s:%(lineno)d]" + _reset,
    }

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno, self.FORMATS[logging.DEBUG])
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def set_up_logger() -> None:
    """Configure the root logger with async file + console handlers.

    Idempotent: calling it a second time clears the previous handlers
    first so the log directory (or datetime stamp) stays current.
    """
    appdata_folder = appdirs.user_data_dir()
    if appdata_folder is None:
        raise OSError("APPDATA environment variable not found")
    app_specific_folder = os.path.join(appdata_folder, _APP_NAME)
    os.makedirs(app_specific_folder, exist_ok=True)

    # Prune log files older than one week
    one_week_ago = datetime.datetime.now() - datetime.timedelta(weeks=1)
    for fname in os.listdir(app_specific_folder):
        if fname.endswith(".log"):
            fpath = os.path.join(app_specific_folder, fname)
            try:
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
                if mtime < one_week_ago:
                    os.remove(fpath)
            except OSError:
                pass

    current_datetime = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        file_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)-8s] %(message)s [%(filename)s:%(lineno)d]",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        log_debug = os.path.join(app_specific_folder, f"Glados_logpath_DEBUG_{current_datetime}.log")
        log_info = os.path.join(app_specific_folder, f"Glados_logpath_INFO_{current_datetime}.log")

        handler_debug = logging.FileHandler(log_debug)
        handler_debug.setLevel(logging.DEBUG)
        handler_debug.setFormatter(file_formatter)

        handler_info = logging.FileHandler(log_info)
        handler_info.setLevel(logging.INFO)
        handler_info.setFormatter(file_formatter)

        global _console_handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(
            ColoredFormatter() if sys.stdout.isatty() else file_formatter
        )
        _console_handler = console_handler

        log_queue: Queue[logging.LogRecord] = Queue(-1)
        queue_handler = logging.handlers.QueueHandler(log_queue)
        queue_listener = logging.handlers.QueueListener(
            log_queue,
            handler_info,
            handler_debug,
            console_handler,
            respect_handler_level=True,
        )

        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.INFO)
        root.addHandler(queue_handler)

        queue_listener.start()
        atexit.register(queue_listener.stop)

    except (OSError, ValueError, RuntimeError) as exc:
        logging.error("Error setting up loggers: %s", exc)


def set_log_level(level_str: str) -> None:
    """Change the root logger level at runtime (e.g. "DEBUG", "INFO").

    The root logger gates what reaches the QueueHandler; the console handler
    inside the QueueListener must also be updated so DEBUG messages are visible
    in the terminal, not just in the debug log file.
    """
    level = getattr(logging, level_str.upper(), logging.INFO)
    logging.getLogger().setLevel(level)
    if _console_handler is not None:
        _console_handler.setLevel(level)
    logging.info("Log level changed to %s", level_str.upper())
