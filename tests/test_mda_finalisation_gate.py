"""The end-of-MDA finalisation pass runs, and only its repaint touches napari.

The old gate compared `backend_method` (only ever 'process'/'saved') against
the vis_method value 'multiDstack' and required the layer to be named 'MDA',
so the backfill never ran - and a recipe node's layer never has that name.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from glados_pycromanager.GUI import napariGlados
from glados_pycromanager.GUI.napariGlados import napariHandler


def _handler(store):
    bridge = MagicMock()
    handler = SimpleNamespace(shared_data=SimpleNamespace(mdaZarrData={'acquisition_1': store}),
                              _napari_bridge=lambda: bridge)
    return handler, bridge


def test_finalise_backfills_off_the_gui_thread_and_repaints_on_it(monkeypatch):
    backfilled = []
    monkeypatch.setattr(napariGlados, '_backfill_missing_slices',
                        lambda sd, name: backfilled.append(name))
    handler, bridge = _handler(store=object())

    napariHandler._finalise_mda_layer(handler, 'acquisition_1')

    assert backfilled == ['acquisition_1']            # ran here, synchronously
    bridge.submit.assert_called_once()                # repaint marshalled

    layer = MagicMock()
    viewer = SimpleNamespace(layers=[layer])
    monkeypatch.setattr(napariGlados, 'getLayerIdFromName', lambda name, v, sd: [0])
    bridge.submit.call_args.args[0](viewer)
    layer.refresh.assert_called_once()


def test_finalise_skips_a_layer_without_a_store(monkeypatch):
    backfill = MagicMock()
    monkeypatch.setattr(napariGlados, '_backfill_missing_slices', backfill)
    handler, bridge = _handler(store=None)

    napariHandler._finalise_mda_layer(handler, 'acquisition_1')

    backfill.assert_not_called()
    bridge.submit.assert_not_called()


def test_backfill_failure_still_repaints(monkeypatch):
    def boom(sd, name):
        raise OSError('dataset closed')
    monkeypatch.setattr(napariGlados, '_backfill_missing_slices', boom)
    handler, bridge = _handler(store=object())

    napariHandler._finalise_mda_layer(handler, 'acquisition_1')

    bridge.submit.assert_called_once()
