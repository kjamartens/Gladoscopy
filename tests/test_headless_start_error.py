"""When Micro-Manager fails to start, the error names the real cause, not the
generic 'Is the ZMQ server on 4827 enabled?' that connecting afterwards gives."""
import pytest

from glados_pycromanager.GUI.GUI_napari import MicroManagerStartError, connect_headless_core

ZMQ = "Couldn't create Core. Is Micro-Manager running and is the ZMQ server on 4827 option enabled?"
CAUSE = 'Property "Microtubules_Mode" of device "CellField" not found in cache'


def _failing_core():
    raise Exception(ZMQ)


def test_start_error_replaces_the_generic_connection_error():
    with pytest.raises(MicroManagerStartError, match="Microtubules_Mode") as info:
        connect_headless_core(_failing_core, Exception(CAUSE))
    assert "4827" not in str(info.value)
    assert ZMQ in str(info.value.__cause__)  # kept in the chain for the log


def test_connection_error_unchanged_without_a_start_error():
    with pytest.raises(Exception, match="4827"):
        connect_headless_core(_failing_core, None)


def test_core_returned_when_connecting_works_even_after_a_start_warning():
    assert connect_headless_core(lambda: "core", Exception(CAUSE)) == "core"
