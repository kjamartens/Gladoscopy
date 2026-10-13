"""L2.4 of claude_launcher_project.md: two napari costs on the startup path.

* The scale bar is the first user of pint's application registry, whose build parses
  pint's definitions file (~0.8 s); ``use_cached_unit_registry`` gives it pint's disk
  cache (~0.05 s once written).
* napari saves its whole settings file each time a dock's area is recorded: eight
  saves of 50-100 ms while napari's and Glados' docks are added. Saving is suspended
  from just before ``napari.Viewer()`` until the startup layout is final, then done once.
"""

import inspect
import json
import subprocess
import sys

_PINT_PROBE = r"""
import json, pathlib, sys
import platformdirs, pint
from glados_pycromanager.GUI import napariHelperFunctions as nhf
cache = pathlib.Path(sys.argv[1])
platformdirs.user_cache_path = lambda **kw: cache
out = {}
out['enabled'] = nhf.use_cached_unit_registry()
reg = pint.get_application_registry()
out['still_lazy'] = type(reg.get()) is pint.LazyRegistry
out['pixel'] = str(reg('um').units)
out['cache_written'] = any(cache.glob('*.pickle'))
out['again_once_built'] = nhf.use_cached_unit_registry()
blocked = cache / 'a_file'
blocked.write_text('')
platformdirs.user_cache_path = lambda **kw: blocked / 'sub'
pint.set_application_registry(pint.LazyRegistry())
out['unwritable'] = nhf.use_cached_unit_registry()
out['unwritable_left_default'] = 'cache_folder' not in pint.get_application_registry().get().__dict__['params'][1]
print(json.dumps(out))
"""


def test_scale_bar_unit_registry_uses_a_disk_cache(tmp_path):
    result = subprocess.run([sys.executable, '-c', _PINT_PROBE, str(tmp_path / 'pint')],
                            capture_output=True, text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out == {'enabled': True, 'still_lazy': True, 'pixel': 'micrometer',
                   'cache_written': True, 'again_once_built': False,
                   'unwritable': False, 'unwritable_left_default': True}


def test_show_scale_bar_enables_the_cache_first():
    from glados_pycromanager.GUI import napariHelperFunctions as nhf
    src = inspect.getsource(nhf.showScaleBar)
    assert src.index('use_cached_unit_registry()') < src.index('scale_bar.visible')


class _FakeSettings:
    def __init__(self):
        self._save_on_change = True
        self.saves = 0

    def _maybe_save(self):
        if self._save_on_change:
            self.saves += 1


def test_settings_saves_are_suspended_and_done_once(monkeypatch):
    import napari.settings
    from glados_pycromanager.GUI import napariGlados
    fake = _FakeSettings()
    monkeypatch.setattr(napari.settings, 'get_settings', lambda: fake)
    token = napariGlados._suspend_napari_settings_saves()
    for _ in range(8):  # what adding and tabifying the startup docks does
        fake._maybe_save()
    assert fake.saves == 0
    napariGlados._resume_napari_settings_saves(token)
    assert fake._save_on_change is True and fake.saves == 1
    napariGlados._resume_napari_settings_saves(None)  # suspend failed: nothing to do


def test_suspend_spans_viewer_creation_to_layout_finalised():
    from glados_pycromanager.GUI import napariGlados
    run = inspect.getsource(napariGlados.runNapariPycroManager)
    assert run.index('_suspend_napari_settings_saves()') < run.index('napari.Viewer(')
    size = inspect.getsource(napariGlados._correctControlsDockHeight)
    assert size.index('_resume_napari_settings_saves(') < size.index("mark('startup layout finalised')")
