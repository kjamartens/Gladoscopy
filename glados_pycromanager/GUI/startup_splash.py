"""Startup splash: shows that Glados is working, and on what, from the first second.

Shown by ``GUI/startup.py`` before the heavy imports. It follows the startup timeline:
every ``startup_timeline.mark`` that has an entry in ``STEP_AFTER_MARK`` switches the
message to the step that starts next. ``GUI_napari.main`` closes it once startup is
ready.

Startup runs on the GUI thread, so nothing can paint the splash between two marks.
At each mark it repaints itself. Before the main event loop runs (``pump=True``) it also
processes non-input events, so Windows keeps seeing a responsive window. Once the event
loop runs, Glados' own posted events and timers are queued, so it only repaints:
processing them from inside a mark would run them re-entrantly, in the middle of
building a dock.

Light on purpose: PyQt5 only, no Glados GUI modules.
"""

import os
import sys
import threading
import time

from PyQt5.QtCore import QEventLoop, QRect, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QMainWindow, QSplashScreen

#: 720 px light splash, written by scripts/make_splash_images.py from the oversampled
#: GladosSplash_inv.png (which alone takes ~350 ms to load). Also used by the backend dialog.
SPLASH_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Icons',
                            'GladosSplash_720.png')
#: Fallback size when the image is missing; matches the shipped image.
SPLASH_SIZE = (720, 430)
#: Height of the text band at the bottom of the splash.
BAND_HEIGHT = 70

FIRST_STEP = 'Loading Glados…'

#: Mark label -> the step that starts once that mark is stamped. A mark is stamped when
#: its step *ends*, so the message names what comes next. Labels not listed here leave
#: the message unchanged. Every key must be a real mark (tests/test_startup_splash.py).
STEP_AFTER_MARK = {
    'Glados modules imported': 'Preparing settings…',
    'napari settings read': 'Starting the microscope backend…',
    'backend up': 'Starting the hardware service…',
    'MicroscopeService started': 'Opening the napari viewer…',
    'event loop running, building GUI': 'Opening the napari viewer…',
    'napari UI initialised': 'Building the Controls panel…',
    'dock built: Controls': 'Building the Multi-D acquisition panel…',
    'dock built: Multi-D acquisition': 'Building the Autonomous microscopy panel…',
    'dock built: Autonomous microscopy': 'Arranging the window…',
}


#: Mark after which the main window exists; see StartupSplash._stay_above_main_window.
OWNER_WINDOW_MARK = 'napari viewer created'


def _bring_to_front_once(widget) -> None:
    """Put ``widget`` above every normal window *now*, without keeping it there.

    ``raise_()`` alone is refused by Windows' foreground lock unless this process owns the
    foreground (true for a shortcut click, not for a launch from a busy terminal).
    Topmost-then-not-topmost is the usual way round it: the window ends at the
    top of the normal z-order and any window activated later goes above it, unlike
    ``Qt.WindowStaysOnTopHint``.
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        hwnd = ctypes.c_void_p(int(widget.winId()))
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        user32.SetWindowPos(hwnd, ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0, flags)
        user32.SetWindowPos(hwnd, ctypes.c_void_p(HWND_NOTOPMOST), 0, 0, 0, 0, flags)
    except Exception:
        pass


HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010


def _load_pixmap() -> QPixmap:
    pixmap = QPixmap(SPLASH_IMAGE)
    if pixmap.isNull():
        pixmap = QPixmap(*SPLASH_SIZE)
        pixmap.fill(QColor(240, 240, 240))
    return pixmap


class StartupSplash(QSplashScreen):
    """Splash with a title, the current step and the elapsed time."""

    def __init__(self, title: str = 'Glados-PycroManager'):
        # Not WindowStaysOnTopHint: it comes up on top (show_now), but any other window
        # may then be put over it.
        super().__init__(_load_pixmap())
        self._title = title
        self._step = FIRST_STEP
        self._t0 = time.perf_counter()
        #: True while no main event loop runs; see the module docstring.
        self.pump = True
        self._listening = False

    # -- progress ---------------------------------------------------------------
    def set_step(self, text: str) -> None:
        self._step = text
        self._refresh()

    def on_mark(self, label: str) -> None:
        """startup_timeline listener."""
        if label == OWNER_WINDOW_MARK:
            self._stay_above_main_window()
        step = STEP_AFTER_MARK.get(label)
        if step is not None:
            self.set_step(step)

    def _stay_above_main_window(self) -> None:
        """Become an owned window of the just-created main window.

        The napari window appears long before startup is done, and as the newest,
        active window it would cover the splash. An owned window always stays above its
        owner (Qt maps a transient parent to the Win32 owner), so the splash stays above
        Glados' own window while any other application's window can still go over both.
        """
        if threading.current_thread() is not threading.main_thread() or not self.isVisible():
            return
        app = QApplication.instance()
        main = next((w for w in app.topLevelWidgets()
                     if isinstance(w, QMainWindow) and w.isVisible() and w is not self), None)
        if main is None or main.windowHandle() is None or self.windowHandle() is None:
            return
        self.windowHandle().setTransientParent(main.windowHandle())
        self.raise_()

    def _refresh(self) -> None:
        # Marks can come from any thread; only the GUI (= main) thread may paint.
        app = QApplication.instance()
        if (app is None or threading.current_thread() is not threading.main_thread()
                or not self.isVisible()):
            return
        if self.pump:
            app.processEvents(QEventLoop.ExcludeUserInputEvents)
        self.repaint()

    def start_listening(self) -> None:
        from glados_pycromanager.observability import startup_timeline
        if not self._listening:
            startup_timeline.add_listener(self.on_mark)
            self._listening = True

    def stop_listening(self) -> None:
        from glados_pycromanager.observability import startup_timeline
        startup_timeline.remove_listener(self.on_mark)
        self._listening = False

    def show_now(self) -> None:
        """Show on top and paint immediately, before any event loop runs."""
        self.show()
        self.raise_()
        _bring_to_front_once(self)
        app = QApplication.instance()
        if app is not None:
            # The window must be mapped before a synchronous repaint reaches the screen.
            app.processEvents(QEventLoop.ExcludeUserInputEvents)
        self.repaint()

    def done(self) -> None:
        self.stop_listening()
        self.close()

    # -- painting ---------------------------------------------------------------
    def drawContents(self, painter: QPainter) -> None:
        w, h = self.width(), self.height()
        band = QRect(0, h - BAND_HEIGHT, w, BAND_HEIGHT)
        painter.fillRect(band, QColor(255, 255, 255, 215))
        painter.setPen(QColor(25, 25, 25))
        title_font = QFont(painter.font())
        title_font.setPointSize(15)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(band.adjusted(16, 8, -16, -BAND_HEIGHT // 2),
                         Qt.AlignLeft | Qt.AlignVCenter, self._title)
        step_font = QFont(painter.font())
        step_font.setPointSize(10)
        step_font.setBold(False)
        painter.setFont(step_font)
        painter.setPen(QColor(70, 70, 70))
        lower = band.adjusted(16, BAND_HEIGHT // 2, -16, -8)
        painter.drawText(lower, Qt.AlignLeft | Qt.AlignVCenter, self._step)
        painter.drawText(lower, Qt.AlignRight | Qt.AlignVCenter,
                         f'{time.perf_counter() - self._t0:.0f} s')
