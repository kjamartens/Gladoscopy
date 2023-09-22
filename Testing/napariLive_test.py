from pathlib import Path
import napari
import numpy as np
from useq import MDASequence

try:
    from mda_simulator.mmcore import FakeDemoCamera
except ModuleNotFoundError:
    FakeDemoCamera = None

v = napari.Viewer()
dw, main_window = v.window.add_plugin_dock_widget("napari-micromanager")

core = main_window._mmc
core.loadSystemConfiguration("C:/Users/SMIPC2/Desktop/MM-config/MMconfig_20230711_Expert.cfg")

if FakeDemoCamera is not None:
    # override snap to look at more realistic images from a microscoppe
    # with underlying random walk simulation of spheres
    # These act as though "Cy5" is BF and other channels are fluorescent
    fake_cam = FakeDemoCamera(timing=2)
    # make sure we start in a valid channel group
    core.setConfig("Channel", "Cy5")

sequence = MDASequence(
    time_plan={"interval": 0.05, "loops": 10},
)

main_window._show_dock_widget("MDA")
mda = v.window._dock_widgets.get("MDA").widget()
mda.set_state(sequence)

# fill napari-console with useful variables
v.window._qt_viewer.console.push(
    {"main_window": main_window, "mmc": core, "sequence": sequence, "np": np}
)

napari.run()