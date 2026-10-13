"""Light entry point: put a splash on screen, then import and run the real app.

Importing ``GUI_napari`` takes 5-8 s warm and ~25 s cold (napari, pycromanager and
every Glados module), and all of it used to happen before any window existed. This
module imports only pymmcore and PyQt5, creates the app's one ``QApplication``, shows
the startup splash and only then imports ``GUI_napari``.

Reached three ways: the console scripts in ``pyproject.toml``, ``python -m
glados_pycromanager.GUI.GUI_napari`` (its ``__main__`` branch delegates here before
its own heavy imports) and ``python -m glados_pycromanager.GUI.startup``.
"""

import os
import sys

if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from glados_pycromanager.observability import startup_timeline


def set_qt_application_attributes() -> None:
    """Attributes Qt only honours when set before the QApplication exists."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)  # type:ignore
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)  # type:ignore
    QApplication.setAttribute(Qt.AA_UseStyleSheetPropagationInWidgetStyles, True)  # type:ignore


def _wants_help(argv) -> bool:
    return any(a in ('-h', '--help') for a in argv[1:])


def main():
    startup_timeline.mark('launcher started')
    if _wants_help(sys.argv):
        # No window for --help.
        from glados_pycromanager.GUI import GUI_napari
        return GUI_napari.main()

    # Must precede PyQt5: Qt first and a pymmcore.CMMCore later crashes on Windows
    # (see docs/perf-runtime-recipe.md "Known gotchas").
    import pymmcore  # noqa: F401
    from PyQt5.QtWidgets import QApplication

    set_qt_application_attributes()
    app = QApplication.instance() or QApplication(sys.argv)
    startup_timeline.mark('QApplication created')

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

    from glados_pycromanager.GUI import GUI_napari
    return GUI_napari.main(app=app, splash=splash)


if __name__ == '__main__':
    sys.exit(main())
