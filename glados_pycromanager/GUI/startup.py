"""Light entry point: put a splash on screen, then import and run the real app.

Importing ``GUI_napari`` takes 5-8 s warm and ~25 s cold (napari, pycromanager and
every Glados module), and all of it used to happen before any window existed. This
module imports only pymmcore and PyQt5, creates the app's one ``QApplication``, shows
the startup splash and only then imports ``GUI_napari``.

Before the splash it also does what a one-click (taskbar) launch needs:

* **No console** (``gladosw.exe`` runs under pythonw): ``sys.stdout``/``sys.stderr`` are
  ``None`` there, so they are pointed at ``<AppData>/Glados-PycroManager/Glados_console.log``.
  A fatal startup error is then shown in a message box instead of disappearing.
* **Taskbar identity**: an explicit AppUserModelID, matching the one on the Start Menu
  shortcuts (``glados_pycromanager/shortcuts.py``), so the running window groups under
  the pinned Glados icon rather than under "Python".
* **One instance per user** (``GUI/single_instance.py``): a second launch brings the
  running Glados forward and exits. ``--allow-second-instance`` skips the check.

Reached three ways: the console/GUI scripts in ``pyproject.toml``, ``python -m
glados_pycromanager.GUI.GUI_napari`` (its ``__main__`` branch delegates here before
its own heavy imports) and ``python -m glados_pycromanager.GUI.startup``.
"""

import os
import sys

if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from glados_pycromanager.observability import startup_timeline

#: Must equal the AppUserModelID written on the shortcuts (shortcuts.APP_USER_MODEL_ID).
APP_USER_MODEL_ID = 'Glados.Pycromanager'
CONSOLE_LOG_NAME = 'Glados_console.log'
ALLOW_SECOND_INSTANCE_FLAG = '--allow-second-instance'


def set_qt_application_attributes() -> None:
    """Attributes Qt only honours when set before the QApplication exists."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)  # type:ignore
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)  # type:ignore
    QApplication.setAttribute(Qt.AA_UseStyleSheetPropagationInWidgetStyles, True)  # type:ignore


def _wants_help(argv) -> bool:
    return any(a in ('-h', '--help') for a in argv[1:])


def console_log_path() -> str:
    import appdirs
    folder = os.path.join(appdirs.user_data_dir(), 'Glados-PycroManager')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, CONSOLE_LOG_NAME)


def redirect_missing_std_streams() -> str | None:
    """Give pythonw's ``None`` stdout/stderr a file; returns its path, or None if not needed.

    ``print`` tolerates a ``None`` stream, but ``sys.stderr.write`` in a library raises,
    and tracebacks would vanish. The previous session's file is kept as ``.previous``.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None
    def _open(p):
        return open(p, 'w', encoding='utf-8', buffering=1, errors='replace')  # noqa: SIM115 (lives as long as the process)

    path = None
    try:
        path = console_log_path()
        if os.path.exists(path):
            os.replace(path, path + '.previous')
        stream = _open(path)
    except Exception:
        # Typically a still-running Glados holding the file open (Windows will not
        # rename an open file): use a file of our own instead of losing the output.
        try:
            base, ext = os.path.splitext(path or console_log_path())
            path = f'{base}_{os.getpid()}{ext}'
            stream = _open(path)
        except Exception:
            stream, path = open(os.devnull, 'w'), None  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    return path


def set_app_user_model_id(app_id: str = APP_USER_MODEL_ID) -> bool:
    """Group our windows under the pinned Glados shortcut instead of python(w).exe."""
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        shell32 = ctypes.WinDLL('shell32', use_last_error=True)
        shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        return shell32.SetCurrentProcessExplicitAppUserModelID(app_id) == 0  # S_OK
    except Exception:
        return False


def open_log_file(path: str) -> bool:
    """Open `path` in the user's default viewer for it."""
    from PyQt5.QtCore import QUrl
    from PyQt5.QtGui import QDesktopServices
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()  # the traceback was just written to it
        except Exception:
            pass
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))


#: How much of the end of the log the error box's "Show Details..." pane holds.
LOG_TAIL_LINES = 400


def read_log_tail(path: str, max_lines: int = LOG_TAIL_LINES) -> str:
    """The last `max_lines` lines of `path` ('' if unreadable)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            lines = fh.readlines()
    except OSError:
        return ''
    skipped = len(lines) - max_lines
    head = [f'... ({skipped} earlier lines: use "Open log file" for all of it)\n'] if skipped > 0 else []
    return ''.join(head + lines[-max_lines:])


def _show_fatal_startup_error(exc: BaseException, log_path: str | None) -> None:
    """Console-less launch: say that startup failed, and where the traceback is.

    With a log file, "Show Details..." unfolds its tail (traceback included) in a
    selectable text box, and "Open log file" opens the whole file. The box stays
    up until OK, since the process exits right after it closes.
    """
    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox, QTextEdit
        if QApplication.instance() is None:
            return
        where = log_path or 'the Glados log folder'
        box = QMessageBox(QMessageBox.Critical, 'Glados could not start',
                          f'Glados stopped during startup:\n\n{type(exc).__name__}: {exc}\n\n'
                          f'The full error is in:\n{where}')
        ok = box.addButton(QMessageBox.Ok)
        open_log = None
        if log_path and os.path.isfile(log_path):
            tail = read_log_tail(log_path)
            if tail:
                box.setDetailedText(tail)
                for details in box.findChildren(QTextEdit):
                    details.setMinimumSize(700, 300)  # default is a few lines wide
            open_log = box.addButton('Open log file', QMessageBox.ActionRole)
        box.setDefaultButton(ok)
        while True:
            box.exec_()
            if open_log is None or box.clickedButton() is not open_log:
                break
            open_log_file(log_path)
    except Exception:
        pass


def _another_instance_handled(argv) -> bool:
    """True if this launch should stop because a running Glados took over."""
    if ALLOW_SECOND_INSTANCE_FLAG in argv:
        return False
    from glados_pycromanager.GUI import single_instance
    outcome = single_instance.ask_running_instance_to_activate()
    if outcome == single_instance.NOT_RUNNING:
        return False
    if outcome == single_instance.ACTIVATED:
        print('Glados is already running; brought it to the front.')
        return True
    # Connected, but no answer: still busy starting up, or hung.
    from PyQt5.QtWidgets import QMessageBox
    answer = QMessageBox.question(
        None, 'Glados is already running',
        'Glados is already running (or still starting), but is not responding.\n\n'
        'Starting a second Glados can conflict over the camera and other hardware. '
        'Start another one anyway?',
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    return answer != QMessageBox.Yes


def main():
    startup_timeline.mark('launcher started')
    console_log = redirect_missing_std_streams()
    if _wants_help(sys.argv):
        # No window for --help.
        from glados_pycromanager.GUI import GUI_napari
        return GUI_napari.main()

    # Before any window exists, so every window carries it.
    set_app_user_model_id()

    # Historically had to precede PyQt5 (see docs/perf-runtime-recipe.md "Known
    # gotchas"); the actual guard is now glados_pycromanager/_msvc_runtime.py.
    import pymmcore  # noqa: F401
    from PyQt5.QtWidgets import QApplication

    set_qt_application_attributes()
    app = QApplication.instance() or QApplication(sys.argv)
    startup_timeline.mark('QApplication created')

    if _another_instance_handled(sys.argv):
        return 0
    if ALLOW_SECOND_INSTANCE_FLAG not in sys.argv:
        from glados_pycromanager.GUI.single_instance import InstanceServer
        app._glados_instance_server = InstanceServer(parent=app)  # kept alive by the app
        app._glados_instance_server.listen()

    splash = None
    try:
        from glados_pycromanager.GUI.startup_splash import StartupSplash
        splash = StartupSplash()
        splash.start_listening()
        splash.show_now()
        startup_timeline.mark('splash shown')
    except Exception:
        # A splash is a nicety; never let it stop the app from starting.
        import logging
        logging.getLogger(__name__).exception('Could not show the startup splash')
        splash = None

    try:
        from glados_pycromanager.GUI import GUI_napari
        return GUI_napari.main(app=app, splash=splash)
    except SystemExit:
        raise
    except BaseException as exc:
        if console_log is None:
            raise  # a console is there to show the traceback
        import traceback
        traceback.print_exc()  # into the console log
        if splash is not None:
            splash.done()
        _show_fatal_startup_error(exc, console_log)
        return 1


if __name__ == '__main__':
    sys.exit(main())
