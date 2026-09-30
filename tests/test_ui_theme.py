"""The layout toolkit's theme: one Theme -> one stylesheet, fed from LayoutConfig.

The defaults must reproduce the stylesheet napariGlados used to build inline
(14 px font and Windows layout metrics, each x0.75), so moving to the theme does
not restyle the docks that have not been migrated.
"""
from __future__ import annotations

import dataclasses
import os

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_default_theme_reproduces_old_inline_stylesheet_values():
    from glados_pycromanager.ui.layout.theme import Theme, build_stylesheet

    t = Theme()
    assert (t.font_px, t.widget_padding_px, t.widget_margin_px) == (int(14 * .75), int(7 * .75), int(11 / 4 * .75))
    assert t.control_min_px == int(25 * .75)
    assert t.indicator_px == int(12 * .75)
    qss = build_stylesheet(t)
    assert "font-size: 10px;" in qss
    assert "padding: 5px 5px;" in qss
    assert "min-height: 18px;" in qss


def test_stylesheet_styles_every_role():
    from glados_pycromanager.ui.layout import theme

    qss = theme.build_stylesheet(theme.Theme(accent="#123456"))
    for role in (theme.ROLE_SECTION, theme.ROLE_PRIMARY, theme.ROLE_READONLY, theme.ROLE_WARNING, theme.ROLE_NORMAL):
        assert f'[gladosRole="{role}"]' in qss
    assert "#123456" in qss


def test_layout_config_matches_theme_fields():
    """LayoutConfig is the persisted form of Theme: every Theme field must be storable."""
    from glados_pycromanager.GUI.sharedFunctions import LayoutConfig
    from glados_pycromanager.ui.layout.theme import Theme

    config_fields = {f.name for f in dataclasses.fields(LayoutConfig)}
    assert {f.name for f in dataclasses.fields(Theme)} <= config_fields
    assert all(f.metadata["hidden"] for f in dataclasses.fields(LayoutConfig))


def test_theme_from_config_coerces_and_tolerates_bad_values():
    from glados_pycromanager.GUI.sharedFunctions import LayoutConfig
    from glados_pycromanager.ui.layout.theme import Theme, theme_from_config

    cfg = LayoutConfig()
    cfg.font_px = "12"          # JSON / Advanced-settings round trips can yield strings
    cfg.grid_spacing_px = "lots"
    t = theme_from_config(cfg)
    assert t.font_px == 12
    assert t.grid_spacing_px == Theme().grid_spacing_px
    assert theme_from_config(None) == Theme()


def test_hidden_section_keys_parses_comma_list():
    from glados_pycromanager.GUI.sharedFunctions import LayoutConfig

    cfg = LayoutConfig()
    cfg.hidden_sections = " mda.xy, ,controls.stages "
    assert cfg.hidden_section_keys() == {"mda.xy", "controls.stages"}


def test_set_role_sets_property(qapp):
    from PyQt5.QtWidgets import QPushButton

    from glados_pycromanager.ui.layout.theme import ROLE_PRIMARY, set_role

    button = QPushButton("Acquire")
    set_role(button, ROLE_PRIMARY)
    assert button.property("gladosRole") == ROLE_PRIMARY
