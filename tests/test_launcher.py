"""One-click launcher (L1 of claude_launcher_project.md).

Covers what a console-less, taskbar-pinned launch relies on: the stdout/stderr redirect,
the AppUserModelID shared by process and shortcuts, the shortcut writer, ``--last``,
the stale-install stamp and the single-instance hand-off.
"""

import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from glados_pycromanager import install_check, shortcuts
from glados_pycromanager.GUI import startup

REPO = Path(__file__).resolve().parents[1]
windows_only = pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only')


# -- console-less streams ---------------------------------------------------------
@pytest.fixture
def no_std_streams(monkeypatch, tmp_path):
    """pythonw's view of sys, without touching the real streams pytest captures."""
    log = tmp_path / 'Glados_console.log'
    fake_sys = SimpleNamespace(stdout=None, stderr=None)
    monkeypatch.setattr(startup, 'console_log_path', lambda: str(log))
    monkeypatch.setattr(startup, 'sys', fake_sys)
    yield SimpleNamespace(log=log, sys=fake_sys)
    for stream in {fake_sys.stdout, fake_sys.stderr}:
        if stream is not None and not stream.closed:
            stream.close()


def test_streams_left_alone_when_a_console_exists(monkeypatch):
    monkeypatch.setattr(startup, 'console_log_path', lambda: pytest.fail('must not be used'))
    assert startup.redirect_missing_std_streams() is None


def test_missing_streams_go_to_the_console_log_and_the_old_one_is_kept(no_std_streams):
    log = no_std_streams.log
    log.write_text('previous session', encoding='utf-8')
    assert startup.redirect_missing_std_streams() == str(log)
    assert no_std_streams.sys.stdout is no_std_streams.sys.stderr
    no_std_streams.sys.stdout.write('hello\n')
    no_std_streams.sys.stderr.write('oops\n')
    assert log.read_text(encoding='utf-8') == 'hello\noops\n'
    assert Path(str(log) + '.previous').read_text(encoding='utf-8') == 'previous session'


def test_a_console_log_held_by_a_running_instance_gets_a_per_process_file(no_std_streams, monkeypatch):
    log = no_std_streams.log
    log.write_text('running instance', encoding='utf-8')

    def locked(*_a, **_k):
        raise PermissionError('in use')
    monkeypatch.setattr(startup.os, 'replace', locked)
    path = startup.redirect_missing_std_streams()
    assert path.endswith(f'_{os.getpid()}.log')
    assert log.read_text(encoding='utf-8') == 'running instance'


# -- taskbar identity -------------------------------------------------------------
def test_main_shortcut_shares_the_process_app_id_and_each_shortcut_has_its_own():
    assert shortcuts.APP_USER_MODEL_ID == startup.APP_USER_MODEL_ID == 'Glados.Pycromanager'
    specs = {s.name: s for s in shortcuts.build_specs(Path('S'), Path('W'))}
    assert specs['Glados'].app_id == startup.APP_USER_MODEL_ID  # groups the running window
    # The Start Menu lists apps by AppUserModelID: a shared one shows a single entry.
    assert len({s.app_id for s in specs.values()}) == len(specs)


@windows_only
def test_app_user_model_id_is_set_on_the_process():
    # Run in a child: the id is per process, and the test runner's should stay untouched.
    code = ('import ctypes; from glados_pycromanager.GUI import startup;'
            'assert startup.set_app_user_model_id("Glados.Test");'
            'p = ctypes.c_wchar_p(); s = ctypes.windll.shell32;'
            's.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(p)); print(p.value)')
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == 'Glados.Test', out.stderr


# -- shortcuts --------------------------------------------------------------------
def test_shortcut_specs():
    specs = {s.name: s for s in shortcuts.build_specs(Path('S'), Path('W'))}
    assert specs['Glados'].target == Path('S') / 'gladosw.exe'
    assert specs['Glados'].arguments == ''
    assert specs['Glados (last setup)'].target == Path('S') / 'gladosw.exe'
    assert specs['Glados (last setup)'].arguments == '--last'
    assert specs['Glados (debug console)'].target == Path('S') / 'glados.exe'
    assert all(s.working_dir == Path('W') and s.icon.name == 'GladosIcon.ico' for s in specs.values())
    assert shortcuts.ICON.is_file()


def test_gladosw_is_a_gui_script_for_the_launcher():
    import tomllib
    project = tomllib.loads((REPO / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    assert project['gui-scripts'] == {'gladosw': 'glados_pycromanager.GUI.startup:main'}


def test_install_refuses_when_the_launcher_is_missing(tmp_path):
    specs = shortcuts.build_specs(tmp_path / 'no-venv', tmp_path)
    with pytest.raises(FileNotFoundError, match='make dev'):
        shortcuts.install([tmp_path / 'out'], specs)


def test_uninstall_waits_out_a_scanner_holding_a_fresh_shortcut(tmp_path, monkeypatch):
    lnk = tmp_path / 'Glados.lnk'
    lnk.write_bytes(b'')
    real_unlink, calls = Path.unlink, []

    def busy_twice(self, *a, **k):
        calls.append(self)
        if len(calls) <= 2:
            raise PermissionError(32, 'being used by another process')
        return real_unlink(self, *a, **k)
    monkeypatch.setattr(Path, 'unlink', busy_twice)
    monkeypatch.setattr(shortcuts, 'UNLINK_RETRY_S', 0)
    specs = [s for s in shortcuts.build_specs(tmp_path, tmp_path) if s.name == 'Glados']
    assert shortcuts.uninstall([tmp_path], specs) == [lnk]
    assert len(calls) == 3 and not lnk.exists()


@windows_only
def test_shortcuts_round_trip_with_app_id(tmp_path):
    scripts = tmp_path / 'Scripts'
    scripts.mkdir()
    for exe in ('gladosw.exe', 'glados.exe'):
        (scripts / exe).write_bytes(b'')
    specs = shortcuts.build_specs(scripts, tmp_path)
    folder = tmp_path / shortcuts.FOLDER_NAME
    written = shortcuts.install([folder], specs)
    assert len(written) == 3
    last = shortcuts.read_shortcut(folder / 'Glados (last setup).lnk')
    assert Path(last['target']) == scripts / 'gladosw.exe'
    assert last['arguments'] == '--last'
    assert Path(last['working_dir']) == tmp_path
    assert last['app_id'] == f'{startup.APP_USER_MODEL_ID}.LastSetup'
    assert shortcuts.read_shortcut(folder / 'Glados.lnk')['app_id'] == startup.APP_USER_MODEL_ID
    assert len(shortcuts.uninstall([folder], specs)) == 3
    assert not folder.exists()  # empty Glados folder removed too


# -- --last -----------------------------------------------------------------------
def _mm_cfg(tmp_path, backend='PyMMCorePlus', config=True, install=True):
    cfg = tmp_path / 'scope.cfg'
    mm = tmp_path / 'mm'
    if config:
        cfg.write_text('# cfg', encoding='utf-8')
    if install:
        mm.mkdir(exist_ok=True)
    return SimpleNamespace(headless_backend=backend, config_path=str(cfg), path=str(mm))


@pytest.fixture(scope='module')
def resolve_last_setup():
    from glados_pycromanager.GUI.GUI_napari import resolve_last_setup
    return resolve_last_setup


def test_last_setup_reuses_the_saved_backend(tmp_path, resolve_last_setup):
    cfg = _mm_cfg(tmp_path)
    assert resolve_last_setup(cfg) == ('PyMMCorePlus', cfg.config_path, cfg.path)


@pytest.mark.parametrize('kwargs', [dict(backend='Bogus'), dict(config=False), dict(install=False),
                                    dict(backend='')])
def test_last_setup_falls_back_when_anything_is_gone(tmp_path, kwargs, resolve_last_setup):
    assert resolve_last_setup(_mm_cfg(tmp_path, **kwargs)) is None


def test_main_accepts_the_launcher_flags():
    out = subprocess.run([sys.executable, '-m', 'glados_pycromanager.GUI.GUI_napari', '--help'],
                         capture_output=True, text=True, timeout=180, cwd=REPO)
    assert out.returncode == 0, out.stderr[-2000:]
    assert '--last' in out.stdout and '--allow-second-instance' in out.stdout


# -- stale install ----------------------------------------------------------------
def _pyproject(tmp_path, deps):
    path = tmp_path / 'pyproject.toml'
    path.write_text('[project]\nname = "x"\ndependencies = [' + ', '.join(f'"{d}"' for d in deps)
                    + ']\n[tool.other]\nignored = 1\n', encoding='utf-8')
    return path


def test_install_stamp_round_trip(tmp_path):
    pyproject, stamp = _pyproject(tmp_path, ['numpy==2.2.6']), tmp_path / 'stamp.txt'
    assert install_check.stale_install_message(pyproject, stamp) is None  # never stamped: quiet
    install_check.write_stamp(pyproject, stamp)
    assert install_check.stale_install_message(pyproject, stamp) is None
    pyproject.write_text(pyproject.read_text().replace('ignored = 1', 'ignored = 2'), encoding='utf-8')
    assert install_check.stale_install_message(pyproject, stamp) is None  # not install-relevant
    _pyproject(tmp_path, ['numpy==2.3.0'])
    assert 'make dev' in install_check.stale_install_message(pyproject, stamp)


def test_no_pyproject_means_nothing_to_say(tmp_path):
    assert install_check.stale_install_message(tmp_path / 'missing.toml', tmp_path / 's') is None


# -- single instance --------------------------------------------------------------
@pytest.fixture
def qt_app():
    from PyQt5.QtWidgets import QApplication
    startup.set_qt_application_attributes()
    return QApplication.instance() or QApplication([])


def _ask_in_thread(name):
    """The asking side blocks, so it runs off the thread whose event loop serves."""
    from glados_pycromanager.GUI import single_instance
    result = {}
    thread = threading.Thread(
        target=lambda: result.setdefault('outcome', single_instance.ask_running_instance_to_activate(name)))
    thread.start()
    return thread, result


def _serve_until(app, thread, timeout_s=10):
    deadline = time.monotonic() + timeout_s
    while thread.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    thread.join(1)


def test_nobody_running(qt_app):
    from glados_pycromanager.GUI import single_instance
    assert single_instance.ask_running_instance_to_activate(f'glados-test-{uuid.uuid4()}') == \
        single_instance.NOT_RUNNING


def test_second_launch_activates_the_first(qt_app, monkeypatch):
    from glados_pycromanager.GUI import single_instance
    activated = []
    monkeypatch.setattr(single_instance, 'activate_frontmost_window', lambda: activated.append(1))
    name = f'glados-test-{uuid.uuid4()}'
    server = single_instance.InstanceServer(name)
    assert server.listen()
    thread, result = _ask_in_thread(name)
    _serve_until(qt_app, thread)
    for _ in range(50):  # the "activate" line can land just after the client returns
        if activated:
            break
        qt_app.processEvents()
        time.sleep(0.01)
    assert result['outcome'] == single_instance.ACTIVATED
    assert activated == [1]


def test_a_running_instance_that_never_answers_is_reported(qt_app, monkeypatch):
    from PyQt5.QtNetwork import QLocalServer

    from glados_pycromanager.GUI import single_instance
    monkeypatch.setattr(single_instance, 'REPLY_TIMEOUT_MS', 300)
    name = f'glados-test-{uuid.uuid4()}'
    mute = QLocalServer()  # listens, never writes a PID
    assert mute.listen(name)
    thread, result = _ask_in_thread(name)
    _serve_until(qt_app, thread)
    assert result['outcome'] == single_instance.NOT_RESPONDING
    mute.close()
