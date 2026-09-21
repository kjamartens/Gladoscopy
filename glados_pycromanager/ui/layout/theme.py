"""One source for fonts, spacing, margins and colours, turned into one stylesheet.

Widgets never set fonts, margins or colours themselves. They read spacing from
`current_theme()` when they build a layout, and mark themselves with a
`gladosRole` dynamic property (`set_role`) that the generated stylesheet styles.
Changing a `Theme` field (later: from a layout-settings UI, via `LayoutConfig`)
therefore restyles every migrated widget from this one place.

The defaults reproduce the stylesheet `napariGlados.runNapariPycroManager` used
to build inline: a 14 px base font and the Windows layout metrics (7 px spacing,
11 px margins), each scaled by 0.75.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

#: The scale `runNapariPycroManager` applied to every size in its stylesheet.
#: Still published as `shared_data.GUIscaleFactor` for the readers that remain.
LEGACY_SCALE_FACTOR = 0.75

# Roles understood by `build_stylesheet`. Set with `set_role(widget, ROLE_*)`.
ROLE_SECTION = "section"
ROLE_PRIMARY = "primary"
ROLE_READONLY = "readonly"
ROLE_WARNING = "warning"
ROLE_NORMAL = "normal"


@dataclass(frozen=True)
class Theme:
    font_family: str = ""               # "" keeps napari's font
    font_px: int = 10
    header_font_px: int = 10
    widget_padding_px: int = 5          # QSS padding on every widget
    widget_margin_px: int = 2           # QSS margin on every widget
    control_min_px: int = 18            # min height/width of line edits, combos, checkboxes
    indicator_px: int = 9               # checkbox indicator, icon, combo arrow
    section_margin_px: int = 4          # inside a Section, around its body
    section_spacing_px: int = 4         # between widgets inside a Section
    grid_spacing_px: int = 4            # between Sections
    table_min_rows: int = 5             # a ListEditor table shows at least this many rows
    accent: str = "#007acc"             # napari's 'current' colour
    accent_text: str = "#ffffff"
    muted_text: str = "#868e93"         # napari's 'secondary'
    border: str = "#D5D5E5"
    warning: str = "red"


_current = Theme()


def current_theme() -> Theme:
    """The theme widgets build against. Set once at startup via `set_current_theme`."""
    return _current


def set_current_theme(theme: Theme) -> None:
    global _current
    _current = theme


def theme_from_config(layout_config) -> Theme:
    """Build a `Theme` from a `LayoutConfig` (or anything with matching attributes).

    Fields the config does not carry keep the `Theme` default, and a value that
    cannot be coerced to the field's type is ignored rather than raised: a hand-
    edited glados_state.json must never stop the GUI building.
    """
    if layout_config is None:
        return Theme()
    values = {}
    for field in dataclasses.fields(Theme):
        if not hasattr(layout_config, field.name):
            continue
        raw = getattr(layout_config, field.name)
        try:
            values[field.name] = int(raw) if field.type in (int, "int") else str(raw)
        except (TypeError, ValueError):
            continue
    return Theme(**values)


def set_role(widget, role: str) -> None:
    """Mark `widget` with a stylesheet role and re-polish it so the change shows."""
    widget.setProperty("gladosRole", role)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


def build_stylesheet(theme: Theme | None = None) -> str:
    """The stylesheet applied to the Glados docks."""
    t = theme or current_theme()
    family = f'font-family: "{t.font_family}";' if t.font_family else ""
    m = t.widget_margin_px
    return f"""
    QWidget {{
        font-size: {t.font_px}px;
        {family}
        padding: {t.widget_padding_px}px {t.widget_padding_px}px;
        margin: {m}px {m}px {m}px {m}px;
    }}
    QLineEdit {{
        border-width: 3px 3px;
        min-height: {t.control_min_px}px;
        min-width: {t.control_min_px}px;
    }}
    QCheckBox::indicator {{
        width: {t.indicator_px}px;
        height: {t.indicator_px}px;
    }}
    QAbstractButton::icon {{
        width: {t.indicator_px}px;
        height: {t.indicator_px}px;
    }}
    QComboBox::down-arrow {{
        width: {t.indicator_px}px;
        height: {t.indicator_px}px;
    }}
    QComboBox {{
        min-height: {t.control_min_px}px;
        min-width: {t.control_min_px}px;
    }}
    QCheckBox {{
        min-height: {t.control_min_px}px;
        min-width: {t.control_min_px}px;
    }}
    QGroupBox {{
        margin: 0px;
        padding: 0px;
        spacing: 0px;
    }}
    QGroupBox[gladosRole="{ROLE_SECTION}"] {{
        font-weight: bold;
    }}
    QHeaderView::section {{
        font-size: {t.header_font_px}px;
        padding: 1px 4px;
        margin: 0px;
    }}
    QPushButton[gladosRole="{ROLE_PRIMARY}"] {{
        background-color: {t.accent};
        color: {t.accent_text};
        font-weight: bold;
    }}
    QPushButton[gladosRole="{ROLE_PRIMARY}"]:disabled {{
        background-color: {t.muted_text};
    }}
    QLabel[gladosRole="{ROLE_READONLY}"] {{
        color: {t.muted_text};
        font-style: italic;
    }}
    QLineEdit[gladosRole="{ROLE_NORMAL}"] {{
        border: 1px solid {t.border};
    }}
    QLineEdit[gladosRole="{ROLE_WARNING}"] {{
        border: 1px solid {t.warning};
    }}
    """
