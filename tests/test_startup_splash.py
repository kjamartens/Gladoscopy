"""Startup splash (GUI/startup_splash.py) and the light launcher (GUI/startup.py).

The splash follows the startup timeline by mark *label*, so these tests pin that every
label it reacts to is still stamped somewhere: a renamed mark would otherwise silently
freeze the splash on an old message.
"""

import re
import tomllib
from pathlib import Path

import pytest

from glados_pycromanager.GUI import startup_splash
from glados_pycromanager.observability import startup_timeline

REPO = Path(__file__).resolve().parents[1]
GUI = REPO / 'glados_pycromanager' / 'GUI'


def _stamped_marks() -> set[str]:
    labels = set()
    for name in ('GUI_napari.py', 'napariGlados.py', 'startup.py'):
        text = (GUI / name).read_text(encoding='utf-8')
        labels.update(re.findall(r"startup_timeline\.mark\('([^']+)'\)", text))
    return labels


@pytest.fixture
def app():
    # Same attributes the launcher sets. AA_ShareOpenGLContexts in particular must be
    # set before the QApplication exists, or a later QtWebEngine import (napariGlados,
    # via GUI.utils) fails for every test that runs after this one.
    from PyQt5.QtWidgets import QApplication

    from glados_pycromanager.GUI.startup import set_qt_application_attributes
    set_qt_application_attributes()
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _fresh_timeline():
    startup_timeline.reset()
    yield
    startup_timeline.reset()


def test_every_label_the_splash_follows_is_a_real_mark():
    stamped = _stamped_marks()
    followed = set(startup_splash.STEP_AFTER_MARK) | {startup_splash.OWNER_WINDOW_MARK}
    assert followed - stamped == set()


def test_splash_image_is_the_small_light_copy():
    from PIL import Image
    path = Path(startup_splash.SPLASH_IMAGE)
    assert path.name == 'GladosSplash_720.png'
    with Image.open(path) as image:
        assert image.width == 720
    # The light source, not the dark one: the corner pixel of the pattern is light.
    with Image.open(path) as image:
        assert sum(image.convert('RGB').getpixel((2, 2))) > 3 * 180


def test_backend_dialog_uses_the_same_splash_image():
    text = (GUI / 'GUI_napari.py').read_text(encoding='utf-8')
    assert 'splash_png = SPLASH_IMAGE' in text
    assert "'GladosSplash_inv.png'" not in text


def test_splash_follows_marks_and_stops_when_done(app):
    splash = startup_splash.StartupSplash()
    assert splash._step == startup_splash.FIRST_STEP
    splash.start_listening()
    startup_timeline.mark('dock built: Controls')
    assert splash._step == startup_splash.STEP_AFTER_MARK['dock built: Controls']
    startup_timeline.mark('not a followed mark')
    assert splash._step == startup_splash.STEP_AFTER_MARK['dock built: Controls']
    splash.done()
    startup_timeline.mark('dock built: Multi-D acquisition')
    assert splash._step == startup_splash.STEP_AFTER_MARK['dock built: Controls']


def test_splash_does_not_stay_on_top(app):
    from PyQt5.QtCore import Qt
    splash = startup_splash.StartupSplash()
    assert not splash.windowFlags() & Qt.WindowStaysOnTopHint
    splash.close()


def test_failing_listener_does_not_break_a_mark():
    calls = []
    startup_timeline.add_listener(lambda label: 1 / 0)
    startup_timeline.add_listener(calls.append)
    startup_timeline.mark('x')
    assert calls == ['x']
    assert [r[0] for r in startup_timeline.report()] == ['x']


def test_gui_napari_hands_over_to_the_launcher_before_its_heavy_imports():
    text = (GUI / 'GUI_napari.py').read_text(encoding='utf-8')
    delegate = text.index("if __name__ == '__main__':\n    from glados_pycromanager.GUI.startup import main")
    assert delegate < text.index('\nimport napari')
    assert delegate < text.index('\nimport pymmcore')


def test_launcher_imports_nothing_heavy_at_module_scope():
    text = (GUI / 'startup.py').read_text(encoding='utf-8')
    module_scope = [line for line in text.splitlines()
                    if line.startswith(('import ', 'from '))]
    assert all(('napari' not in line and 'GUI_napari' not in line and 'PyQt5' not in line)
               for line in module_scope), module_scope


def test_console_scripts_start_through_the_launcher():
    project = tomllib.loads((REPO / 'pyproject.toml').read_text(encoding='utf-8'))
    scripts = project['project']['scripts']
    assert set(scripts.values()) == {'glados_pycromanager.GUI.startup:main'}
