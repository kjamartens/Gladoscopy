"""Shared layout toolkit for the Glados docks: theme, sections, list editor, responsive grid.

See CLAUDE.md, "UI toolkit", for the rules (never set fonts/margins per widget;
use `set_role` and the theme) and how to add a section.
"""
from glados_pycromanager.ui.layout.list_editor import ListEditor, configure_table_header
from glados_pycromanager.ui.layout.responsive import (
    ALL_BUCKETS,
    LANDSCAPE,
    PORTRAIT,
    TALL,
    WIDE,
    Placement,
    ResponsiveGrid,
    classify_shape,
)
from glados_pycromanager.ui.layout.sections import FlowLayout, FlowRow, FormGrid, Section, apply_section_spacing
from glados_pycromanager.ui.layout.theme import (
    ROLE_NORMAL,
    ROLE_PRIMARY,
    ROLE_READONLY,
    ROLE_SECTION,
    ROLE_WARNING,
    Theme,
    build_stylesheet,
    current_theme,
    set_current_theme,
    set_role,
    theme_from_config,
)

__all__ = [
    "ALL_BUCKETS", "LANDSCAPE", "PORTRAIT", "TALL", "WIDE",
    "FlowLayout", "FlowRow", "FormGrid", "ListEditor", "Placement", "ResponsiveGrid", "Section",
    "ROLE_NORMAL", "ROLE_PRIMARY", "ROLE_READONLY", "ROLE_SECTION", "ROLE_WARNING",
    "Theme", "apply_section_spacing", "build_stylesheet", "classify_shape", "configure_table_header",
    "current_theme", "set_current_theme", "set_role", "theme_from_config",
]
