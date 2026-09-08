"""In-memory stand-in for `MicroscopeInterfaceLayer`.

The real MIL routes every call through one of three Micro-Manager
backends (Java, Python-headless, MMCore-Plus). For unit tests we need
the same *public surface* without any hardware or library shim —
hence this fake.

Scope: covers the read/write methods that tests are likely to hit
(stages, shutter, exposure, ROI, image acquisition, config groups, MDA
event construction). Anything not covered raises `NotImplementedError`
so a test catches the gap loudly. Add methods as new tests need them.

`MicroscopeInstance` is reported as `PYCROMANAGER_PYTHON` — an
in-memory backend is closest semantically to the python-headless one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from glados_pycromanager.Core.microscopeInterfaceLayer import (
    MicroscopeInstance,
)


@dataclass
class _Property:
    value: object
    lower_limit: float | None = None
    upper_limit: float | None = None


@dataclass
class _Device:
    name: str
    type: int = 1  # int matches CMMCore device-type ints; arbitrary here
    properties: dict[str, _Property] = field(default_factory=dict)


class FakeMicroscopeInterfaceLayer:
    """In-memory MIL with the same public surface tests need.

    A small `populate_demo_state()` helper seeds a "DemoCam +
    DemoStage + DemoXY + DemoShutter + Channel config group" world so
    tests don't have to spell out the setup every time.
    """

    def __init__(self):
        # Mirrors `MicroscopeInterfaceLayer.__init__` shape.
        self._core: object | None = None
        self._mi: MicroscopeInstance = MicroscopeInstance.PYCROMANAGER_PYTHON

        # In-memory state — what the real MM core would otherwise hold.
        self._devices: dict[str, _Device] = {}
        self._config_groups: dict[str, dict[str, dict[str, object]]] = {}
        self._current_config: dict[str, str] = {}
        self._exposure_ms: float = 100.0
        self._auto_shutter: bool = True
        self._shutter_open: bool = False
        self._shutter_device: str = ""
        self._focus_device: str = ""
        self._xy_stage_device: str = ""
        self._positions: dict[str, float] = {}
        self._xy_positions: dict[str, tuple[float, float]] = {}
        self._roi: tuple[int, int, int, int] = (0, 0, 512, 512)
        self._pixel_size_um: float = 1.0
        self._wait_calls: int = 0
        self._stop_seq_calls: int = 0
        self._snap_calls: int = 0
        self._image: np.ndarray = np.zeros((512, 512), dtype=np.uint16)

        # Circular-buffer emulation for the continuous-sequence primitives
        # (T-C1). Frames are pushed in with `push_frame()`; nothing here
        # generates them, so a test decides exactly what the buffer holds.
        self._seq_running: bool = False
        self._continuous_starts: list[float] = []
        self._circular_buffer: list[tuple[np.ndarray, dict]] = []
        self._clear_buffer_calls: int = 0

    # ----- lifecycle -------------------------------------------------

    def set_core(self, core):
        self._core = core

    def get_core(self):
        return self._core

    def get_microscope_interface(self) -> MicroscopeInstance:
        return self._mi

    def get_MI(self) -> MicroscopeInstance:  # alias used in the codebase
        return self._mi

    # ----- demo seeding ----------------------------------------------

    def populate_demo_state(self) -> None:
        """Seed a Channel config group + DemoCam + DemoStage + DemoXY."""
        self._devices = {
            "DemoCam": _Device(
                "DemoCam",
                properties={
                    "Exposure": _Property(100.0, 1.0, 5000.0),
                    "Binning": _Property("1", None, None),
                },
            ),
            "DemoStage": _Device("DemoStage"),
            "DemoXY": _Device("DemoXY"),
            "DemoShutter": _Device("DemoShutter"),
        }
        self._focus_device = "DemoStage"
        self._xy_stage_device = "DemoXY"
        self._shutter_device = "DemoShutter"
        self._positions["DemoStage"] = 0.0
        self._xy_positions["DemoXY"] = (0.0, 0.0)

        self._config_groups = {
            "Channel": {
                "DAPI": {"DemoCam.Mode": "DAPI"},
                "FITC": {"DemoCam.Mode": "FITC"},
                "Cy5": {"DemoCam.Mode": "Cy5"},
            }
        }
        self._current_config["Channel"] = "DAPI"

    # ----- read methods ----------------------------------------------

    def clear_roi(self) -> None:
        self._roi = (0, 0, 512, 512)

    def get_auto_shutter(self) -> bool:
        return self._auto_shutter

    def get_available_config_groups(self) -> list:
        return list(self._config_groups.keys())

    def get_available_configs(self, config_group) -> list:
        return list(self._config_groups.get(config_group, {}).keys())

    def get_current_config(self, config_group) -> str:
        return self._current_config.get(config_group, "")

    def get_exposure(self) -> float:
        return self._exposure_ms

    def get_focus_device(self) -> str:
        return self._focus_device

    def get_image(self) -> np.ndarray:
        return self._image.copy()

    def get_image_width(self) -> int:
        return int(self._image.shape[1])

    def get_image_height(self) -> int:
        return int(self._image.shape[0])

    def get_last_image_and_metadata(self) -> tuple[np.ndarray, dict]:
        """Newest buffered frame, left in the buffer (`latest` pull policy)."""
        if not self._circular_buffer:
            raise IndexError("circular buffer is empty")
        image, metadata = self._circular_buffer[-1]
        return image.copy(), dict(metadata)

    def get_loaded_devices(self) -> list:
        return list(self._devices.keys())

    def get_pixel_size_um(self):
        return self._pixel_size_um

    def get_position(self, device_name: str) -> tuple:
        # Real MIL returns a single float on the Java backend and a
        # 1-tuple on others — normalize to "just the float" here; tests
        # that care about that shape should assert explicitly.
        return self._positions.get(device_name, 0.0)

    def get_property(self, device_name, property_name):
        dev = self._devices.get(device_name)
        if dev is None or property_name not in dev.properties:
            raise KeyError(f"{device_name}.{property_name} not loaded")
        return dev.properties[property_name].value

    def has_property_limits(self, device_name, property_name) -> bool:
        dev = self._devices.get(device_name)
        if dev is None or property_name not in dev.properties:
            return False
        p = dev.properties[property_name]
        return p.lower_limit is not None and p.upper_limit is not None

    def get_property_lower_limit(self, device_name, property_name) -> float:
        return self._devices[device_name].properties[property_name].lower_limit or 0.0

    def get_property_upper_limit(self, device_name, property_name) -> float:
        return self._devices[device_name].properties[property_name].upper_limit or 0.0

    def get_remaining_image_count(self) -> int:
        return len(self._circular_buffer)

    def get_roi(self):
        return self._roi

    def get_shutter_device(self) -> str:
        return self._shutter_device

    def get_shutter_open(self) -> bool:
        return self._shutter_open

    def get_xy_position(self, xy_stage_name: str | None = None) -> tuple:
        name = xy_stage_name or self._xy_stage_device
        return self._xy_positions.get(name, (0.0, 0.0))

    def get_xy_stage_device(self) -> str:
        return self._xy_stage_device

    def get_xy_stage_position(self, xy_stage_name: str) -> tuple:
        return self._xy_positions.get(xy_stage_name, (0.0, 0.0))

    def get_device_type(self, device_name) -> int:
        return self._devices.get(device_name, _Device(device_name)).type

    def is_sequence_running(self) -> bool:
        return self._seq_running

    def pop_next_image_and_metadata(self) -> tuple[np.ndarray, dict]:
        """Oldest buffered frame, removed (`sequential` pull policy)."""
        if not self._circular_buffer:
            raise IndexError("circular buffer is empty")
        image, metadata = self._circular_buffer.pop(0)
        return image, metadata

    # ----- write methods ---------------------------------------------

    def set_auto_shutter(self, auto_shutter: bool) -> None:
        self._auto_shutter = bool(auto_shutter)

    def set_config(self, config_group, config_name) -> None:
        if config_group not in self._config_groups:
            raise KeyError(f"unknown config group: {config_group}")
        if config_name not in self._config_groups[config_group]:
            raise KeyError(f"unknown config {config_name} in {config_group}")
        self._current_config[config_group] = config_name

    def set_exposure(self, exposure_time: float) -> None:
        if exposure_time <= 0:
            raise ValueError("exposure must be positive")
        self._exposure_ms = float(exposure_time)

    def set_focus_device(self, focus_device) -> None:
        self._focus_device = focus_device

    def set_property(self, device_name, property_name, newval):
        dev = self._devices.setdefault(device_name, _Device(device_name))
        prop = dev.properties.setdefault(property_name, _Property(newval))
        prop.value = newval

    def set_relative_position(self, device_name: str, pos_change: float) -> None:
        current = self._positions.get(device_name, 0.0)
        self._positions[device_name] = current + float(pos_change)

    def set_relative_xy_position(self, pos_change: tuple) -> None:
        dx, dy = pos_change
        cx, cy = self._xy_positions.get(self._xy_stage_device, (0.0, 0.0))
        self._xy_positions[self._xy_stage_device] = (cx + float(dx), cy + float(dy))

    def set_roi(self, roi: tuple) -> None:
        if len(roi) != 4:
            raise ValueError("ROI must be (x, y, w, h)")
        self._roi = tuple(int(v) for v in roi)  # type: ignore[assignment]

    def set_shutter_device(self, shutter_device: str) -> None:
        self._shutter_device = shutter_device

    def set_shutter_open(self, open_shutter: bool) -> None:
        self._shutter_open = bool(open_shutter)

    def clear_circular_buffer(self) -> None:
        self._clear_buffer_calls += 1
        self._circular_buffer.clear()

    def snap_image(self) -> None:
        self._snap_calls += 1

    def start_continuous_sequence_acquisition(self, interval_ms: float = 0) -> None:
        self._continuous_starts.append(float(interval_ms))
        self._seq_running = True

    def stop_sequence_acquisition(self) -> None:
        self._stop_seq_calls += 1
        self._seq_running = False

    def wait_for_system(self) -> None:
        self._wait_calls += 1

    # ----- helpers (no real-MIL equivalent; for assertions) ----------

    def set_image(self, image: np.ndarray) -> None:
        """Pre-load the bytes that the next `get_image()` returns."""
        self._image = np.asarray(image)

    def push_frame(self, image: np.ndarray, metadata: dict | None = None) -> None:
        """Append one frame to the emulated circular buffer.

        The real buffer is filled by the camera; here a test fills it
        explicitly so pop/peek ordering can be asserted.
        """
        self._circular_buffer.append((np.asarray(image), dict(metadata or {})))

    # ----- explicit gap -----------------------------------------------

    def __getattr__(self, item):
        # Anything not covered fails loudly rather than via AttributeError
        # so a test failure points at the missing fake method.
        raise NotImplementedError(
            f"FakeMicroscopeInterfaceLayer does not implement {item!r}; "
            "add it to tests/fakes/fake_mil.py for this test."
        )
