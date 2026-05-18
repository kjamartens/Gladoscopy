"""Phase 10.7 — MicroscopeInterfaceLayer.set_core is stricter.

- P1: each of the three real backend types (mocked via isinstance-only
  surrogates) sets the cached :class:`MicroscopeInstance` correctly.
- N1: ``set_core(None)`` raises :class:`BackendError` instead of
  silently leaving ``core=None`` for every downstream method.
- N2: an unrecognised object reaches the ``UNKNOWN`` branch and logs
  a warning so the misconfiguration is visible.
"""

from __future__ import annotations

import logging

import pytest

from glados_pycromanager.Core import microscopeInterfaceLayer as mil_mod
from glados_pycromanager.Core.microscopeInterfaceLayer import (
    MicroscopeInterfaceLayer,
    MicroscopeInstance,
)
from glados_pycromanager.errors import BackendError


def test_set_core_none_raises() -> None:
    mil = MicroscopeInterfaceLayer()
    with pytest.raises(BackendError, match="None"):
        mil.set_core(None)


def test_set_core_unknown_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mil = MicroscopeInterfaceLayer()

    class _SomethingElse:
        pass

    with caplog.at_level(logging.WARNING, logger=mil_mod.logger.name):
        mil.set_core(_SomethingElse())
    assert mil.MI() is MicroscopeInstance.UNKNOWN
    assert any("not recognised" in rec.message for rec in caplog.records)


@pytest.mark.parametrize(
    "real_type_attr, expected",
    [
        ("PycroManagerCore", MicroscopeInstance.PYCROMANAGER_JAVA),
        ("PymmcoreCore", MicroscopeInstance.PYCROMANAGER_PYTHON),
        ("PymmcorePlusCore", MicroscopeInstance.MMCORE_PLUS),
    ],
)
def test_set_core_dispatch_each_backend(
    real_type_attr: str,
    expected: MicroscopeInstance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Substitute a tiny class for each backend isinstance() target so
    the detection branch in set_core can be exercised without a real
    Java/Python bridge handle."""

    class _Stub:
        pass

    monkeypatch.setattr(mil_mod, real_type_attr, _Stub)
    mil = MicroscopeInterfaceLayer()
    mil.set_core(_Stub())
    assert mil.MI() is expected
