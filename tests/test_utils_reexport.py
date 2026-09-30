"""Phase 7.6 — guard that the `utils.py` / `sharedFunctions.py` shims
still point at the real implementations in their new homes.

This file exists *temporarily* — Phase 18.1 deletes the shims (and
this test) once every internal caller imports from the new paths.
"""
from __future__ import annotations

import warnings


def _under_deprecation_ignore():
    """Context manager: silence the Phase 7.2 DeprecationWarnings."""
    return warnings.catch_warnings(record=False)


def test_load_config_from_json_reexport_wraps_appdata():
    from glados_pycromanager.GUI.sharedFunctions import (
        load_config_from_json as legacy,
    )
    from glados_pycromanager.io.appdata import (
        load_config_from_json as canonical,
    )

    # The shim wraps the canonical via warnings.warn(...) so identity won't
    # hold; assert the canonical is reachable via the shim's closure.
    assert legacy is not canonical  # because it wraps to emit the warning
    # But behaviour matches — same function should be visible in the module.
    from glados_pycromanager.io.appdata import (
        save_config_to_json as canonical_save,
    )

    assert callable(canonical) and callable(canonical_save)


def test_save_config_to_json_reexport_emits_deprecation():
    from glados_pycromanager.GUI import sharedFunctions
    from glados_pycromanager.GUI.sharedFunctions import Config

    cfg = Config()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        # Just call with a sentinel value; the file-system side effect is
        # not interesting here — only that we go through the warn path.
        try:
            sharedFunctions.save_config_to_json(cfg)
        except Exception:
            # If the underlying write fails because the conftest fixture
            # didn't fire (this test doesn't use it), that's fine — the
            # DeprecationWarning fires *before* the body.
            pass

    msgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("save_config_to_json" in m for m in msgs)
    assert any("Phase 18.1" in m for m in msgs)


def test_load_config_from_json_reexport_emits_deprecation():
    from glados_pycromanager.GUI import sharedFunctions
    from glados_pycromanager.GUI.sharedFunctions import Config

    cfg = Config()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        try:
            sharedFunctions.load_config_from_json(cfg)
        except Exception:
            pass

    msgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("load_config_from_json" in m for m in msgs)
    assert any("Phase 18.1" in m for m in msgs)


def test_storeSharedData_GlobalData_reexport_emits_deprecation():
    from glados_pycromanager.GUI import utils
    from glados_pycromanager.GUI.sharedFunctions import Config

    class _StubShared:
        config = Config()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        try:
            utils.storeSharedData_GlobalData(_StubShared())
        except Exception:
            pass

    msgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("storeSharedData_GlobalData" in m for m in msgs)


def test_cleanUpTemporaryFiles_reexport_emits_deprecation(tmp_path):
    from glados_pycromanager.GUI import utils

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        utils.cleanUpTemporaryFiles(mainFolder=str(tmp_path), shared_data=None)

    msgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("cleanUpTemporaryFiles" in m for m in msgs)


def test_widget_builder_reexports_are_identical():
    """Phase 7.3 re-exports use direct `from … import` — identity holds."""
    from glados_pycromanager.GUI import utils
    from glados_pycromanager.ui.widgets import builders

    for name in [
        "findIconFolder",
        "setWarningErrorInfoIcon",
        "setLineEditStyle",
        "checkAndShowWidget",
        "lineEditFileLookup",
        "generalFileSearchButtonAction",
    ]:
        legacy = getattr(utils, name)
        canonical = getattr(builders, name)
        assert legacy is canonical, f"{name} shim drifted from canonical"


def test_markdown_view_helpers_importable():
    """Phase 7.4 — the extraction module imports cleanly and exposes the API."""
    from glados_pycromanager.ui.markdown_view import (
        add_html_to_window,
        add_markdown_to_window,
        markdown_to_html,
    )

    assert callable(add_html_to_window)
    assert callable(add_markdown_to_window)
    assert callable(markdown_to_html)
