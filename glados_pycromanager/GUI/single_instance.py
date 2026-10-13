"""One Glados per user: a second launch brings the running one to the front instead.

Two processes would fight over the camera, the serial ports and the Java bridge port
(4827). Clicking the pinned taskbar icon is the easiest way to launch a second one by
accident. The first instance listens on a per-user ``QLocalServer`` (a named pipe on
Windows). A later launch connects and receives the first instance's PID. Because the
user just clicked it, the later launch owns the foreground, so it calls
``AllowSetForegroundWindow(pid)`` and then asks the first instance to activate.

Protocol (one line each way, UTF-8):
    first -> second:  "<pid>\\n" on connect
    second -> first:  "activate\\n"
If the pipe accepts a connection but no PID arrives, the first instance is hung (or still
blocked in a long startup step). The caller then decides what to do; see
``GUI/startup.py``.
"""

import getpass
import logging
import os
import re

from PyQt5.QtCore import QObject
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_MS = 300
#: How long a second launch waits for the running instance to answer. The running
#: instance answers from its event loop, which can be busy for a few seconds during its
#: own startup, so this is generous.
REPLY_TIMEOUT_MS = 3000

#: Outcomes of ``ask_running_instance_to_activate``.
NOT_RUNNING, ACTIVATED, NOT_RESPONDING = 'not-running', 'activated', 'not-responding'


def server_name() -> str:
    """Per-user pipe name, so two users on one PC each get their own Glados."""
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get('USERNAME', 'user')
    return 'glados-pycromanager-' + re.sub(r'[^A-Za-z0-9_.-]', '_', user)


def ask_running_instance_to_activate(name: str | None = None) -> str:
    """From a new launch: is Glados already running? If so, bring it forward."""
    from glados_pycromanager.GUI.window_focus import allow_set_foreground
    socket = QLocalSocket()
    socket.connectToServer(name or server_name())
    if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
        return NOT_RUNNING
    try:
        line = b''
        while not line.endswith(b'\n'):
            if not socket.waitForReadyRead(REPLY_TIMEOUT_MS):
                return NOT_RESPONDING
            line += bytes(socket.readAll())
        try:
            allow_set_foreground(int(line.strip() or b'0'))
        except ValueError:
            pass
        socket.write(b'activate\n')
        socket.waitForBytesWritten(REPLY_TIMEOUT_MS)
        return ACTIVATED
    finally:
        socket.disconnectFromServer()


class InstanceServer(QObject):
    """Owned by the first instance; activates its frontmost window on request."""

    def __init__(self, name: str | None = None, parent=None):
        super().__init__(parent)
        self._name = name or server_name()
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)

    def listen(self) -> bool:
        # A pipe left behind by a crashed instance (Unix only; Windows pipes vanish with
        # their process) would otherwise block listen().
        QLocalServer.removeServer(self._name)
        ok = self._server.listen(self._name)
        if not ok:
            logger.warning('Single-instance server could not listen on %r: %s',
                           self._name, self._server.errorString())
        return ok

    def _on_new_connection(self):
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            socket.write(f'{os.getpid()}\n'.encode())
            socket.flush()
            socket.readyRead.connect(lambda s=socket: self._on_request(s))
            socket.disconnected.connect(socket.deleteLater)

    def _on_request(self, socket):
        if b'activate' in bytes(socket.readAll()):
            logger.info('Another Glados launch asked this instance to come to the front')
            activate_frontmost_window()


def activate_frontmost_window() -> None:
    """Show the main window if it exists, else whatever Glados window is up."""
    from PyQt5.QtWidgets import QApplication, QMainWindow

    from glados_pycromanager.GUI.window_focus import bring_to_front_once
    app = QApplication.instance()
    if app is None:
        return
    visible = [w for w in app.topLevelWidgets() if w.isVisible() or w.isMinimized()]
    main = [w for w in visible if isinstance(w, QMainWindow)]
    target = (main or visible or [None])[0]
    if target is None:
        return
    if target.isMinimized():
        target.showNormal()
    bring_to_front_once(target, activate=True)
