"""Phase 13.0 — argparse for the new headless-bypass CLI flags in GUI_napari.main.

The full `main()` boots napari/Qt/pycromanager so we cannot exercise it from
the test suite. We instead build the same parser used inside `main()` and
assert its surface — choices, defaults, mutual-requirement validation.

If `main()` ever drifts away from this parser definition, this test goes
stale; the parser shape is small enough that drift is easy to catch by eye.
"""

from __future__ import annotations

import argparse
import io
import os

import pytest


def _build_parser() -> argparse.ArgumentParser:
    """Mirror the parser constructed at the top of GUI_napari.main()."""
    parser = argparse.ArgumentParser(
        description="Glados-PycroManager-Napari: an interface for autonomous microscopy via PycroManager"
    )
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--backend", choices=["JAVA", "Python", "PyMMCorePlus"])
    parser.add_argument("--config")
    parser.add_argument("--mm-path")
    parser.add_argument("--buffer-mb", type=int)
    parser.add_argument("--max-memory-mb", type=int)
    parser.add_argument("--auto-demo", action="store_true")
    return parser


def _apply_main_validation(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Mirror the validation block in GUI_napari.main() right after parse_args()."""
    if args.backend and not (args.config or args.auto_demo):
        parser.error("--backend requires --config (or use --auto-demo)")
    if args.config and not (args.backend or args.auto_demo):
        parser.error("--config requires --backend (or use --auto-demo)")


def test_no_args_parses_without_overrides() -> None:
    parser = _build_parser()
    args = parser.parse_args([])
    assert args.backend is None
    assert args.config is None
    assert args.auto_demo is False


def test_backend_choices_rejects_unknown() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--backend", "wat"])


def test_backend_without_config_or_demo_errors() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--backend", "Python"])
    with pytest.raises(SystemExit):
        _apply_main_validation(parser, args)


def test_config_without_backend_or_demo_errors() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--config", "foo.cfg"])
    with pytest.raises(SystemExit):
        _apply_main_validation(parser, args)


def test_backend_plus_config_is_valid() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--backend", "PyMMCorePlus", "--config", "foo.cfg"])
    _apply_main_validation(parser, args)  # should not raise
    assert args.backend == "PyMMCorePlus"
    assert args.config == "foo.cfg"


def test_auto_demo_alone_is_valid() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--auto-demo"])
    _apply_main_validation(parser, args)  # should not raise
    assert args.auto_demo is True


def test_int_overrides_parse_as_ints() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        ["--backend", "Python", "--config", "x.cfg", "--buffer-mb", "1024", "--max-memory-mb", "8192"]
    )
    assert args.buffer_mb == 1024
    assert args.max_memory_mb == 8192


def test_help_mentions_new_flags() -> None:
    """Sanity: the help text actually documents the new flags."""
    parser = _build_parser()
    buf = io.StringIO()
    parser.print_help(file=buf)
    out = buf.getvalue()
    for flag in ("--backend", "--config", "--mm-path", "--buffer-mb", "--max-memory-mb", "--auto-demo"):
        assert flag in out, f"{flag} missing from --help output"
