"""Common interface layer for the three supported Micro-Manager backends
(Pycromanager-Java, Pycromanager-Python, MMCore-plus).

**Thread safety.** Every public method that touches ``self.core`` is wrapped in
``@_hardware_locked``, which takes a single per-instance ``threading.RLock``.
This enforces threading invariant 2 of ``claude_throughput_project.md``: all
microscope access is serialized, regardless of which thread calls it.

The lock is not theoretical. Commit ``cd01032`` exists because two threads drove
the same ``core.mda``/``Acquisition`` object concurrently and produced a **native
access violation / JVM fatal crash**. Hardware is touched from at least five
thread contexts today: the Qt/GUI thread (``MMcontrols.py``,
``LaserControlScripts.py``), the acquisition worker, RT-analysis QThreads
(``LaserAdjustment.py`` calls ``set_property()`` per frame), nodz executor
``QRunnable``s (``AutoFocusBF.py``, ``Strobo_lasers.py``), and a
``ThreadPoolExecutor`` in ``utils.forceReset``. Interleaving two threads' serial
writes to a TriggerScope is a hardware-correctness bug, not just a performance
one.

On ``PYCROMANAGER_JAVA`` this serialization already existed implicitly —
``pyjavaz``'s ``Bridge.send_and_receive`` holds one global ``_communication_lock``
per round trip — but ``PYCROMANAGER_PYTHON`` and ``MMCORE_PLUS`` bind straight to
CMMCore with no such lock.

The lock is **re-entrant** because MIL methods compose: ``get_image_width()``
calls ``get_roi()``. It is deliberately **untimed** — a deadlock here should be
diagnosed, not silently skipped. The ``get_exposure`` / ``get_pixel_size_um``
cache-hit fast paths return *before* acquiring it, so the per-frame display path
is never serialized behind a slow stage move.
"""

import functools
import logging
import threading
from enum import Enum

import numpy as np
from pycromanager import Core as PycroManagerCore
from pycromanager import JavaObject, multi_d_acquisition_events
from pymmcore import CMMCore as PymmcoreCore
from pymmcore import Metadata as PymmcoreMetadata
from pymmcore_plus import CMMCorePlus as PymmcorePlusCore

from glados_pycromanager.errors import BackendError, MDAEventError

logger = logging.getLogger(__name__)


class MicroscopeInstance(Enum):
    PYCROMANAGER_JAVA = 'PycromanagerJava'
    PYCROMANAGER_PYTHON = 'PycromanagerPython'
    MMCORE_PLUS = 'MMCorePlus'
    UNKNOWN = 'Unknown' # Add an unknown type for comprehensive handling

def _hardware_locked(method):
    """Serialize a MIL method against all other hardware access.

    Applied to every public method that touches ``self.core``. See the module
    docstring for why. Re-entrant, so composing MIL methods is safe.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._hw_lock:
            return method(self, *args, **kwargs)
    return wrapper


class MicroscopeInterfaceLayer:
    def __init__(self):
        # One re-entrant lock per MIL instance, guarding every method that
        # touches self.core (see the module docstring and @_hardware_locked).
        self._hw_lock = threading.RLock()
        self.core: PycroManagerCore | PymmcoreCore | PymmcorePlusCore | None = None
        # Cached backend tag — computed once in `set_core` so each MIL call
        # doesn't re-run the isinstance + Java-bridge attribute chain.
        # Phase 6.1 of claude_project.md.
        self._mi: MicroscopeInstance = MicroscopeInstance.UNKNOWN
        # Phase 13.2: cache pixel size so repeated calls in napariUpdateLive
        # don't hit the Java bridge or CMMCore on every layer-creation event.
        # Reset in set_core() so objective/config changes are picked up.
        self._pixel_size_um_cache: float | None = None
        # bench_live_display measured ~257ms/call for a PYCROMANAGER_JAVA
        # bridge round trip (matching the pixel-size cost before it was
        # cached); napariUpdateLive's rate-limit gate calls get_exposure()
        # on every candidate frame, so an uncached call there is a
        # per-displayed-frame Java-bridge round trip. Invalidated in
        # set_exposure() so a user-changed exposure is picked up immediately.
        self._exposure_cache: float | None = None
        # T-C1: the circular-buffer primitives reshape flat pixel buffers
        # once per popped frame, so the (height, width) they reshape to
        # cannot come from a per-frame get_roi() call. Invalidated wherever
        # the frame geometry can change: set_core(), set_roi(), clear_roi().
        self._image_shape_cache: tuple[int, int] | None = None
        self.mda: dict | None = None

    @_hardware_locked
    def set_core(self, core):
        """Bind a backend core object and cache its :class:`MicroscopeInstance`.

        Raises:
            BackendError: If ``core`` is ``None``. Callers can no longer
                accidentally bind an empty core that would silently
                short-circuit every subsequent MIL call.

        Logs a single ``warning`` (not error — some test fixtures pass
        custom mock objects on purpose) when the backend type cannot be
        classified, so an UNKNOWN backend is visible in the log file.
        """
        if core is None:
            raise BackendError("MIL.set_core(None) is not allowed")
        self.core = core
        self._mi = self._detect_microscope_instance(core)
        self._pixel_size_um_cache = None  # invalidate on core change
        self._exposure_cache = None  # invalidate on core change
        self._image_shape_cache = None  # invalidate on core change
        if self._mi is MicroscopeInstance.UNKNOWN:
            logger.warning(
                "MIL.set_core: backend type %r not recognised as Pycromanager/"
                "MMCore-Plus; downstream calls will raise. core=%r",
                type(core).__name__,
                core,
            )

    def get_core(self):
        return self.core

    @staticmethod
    def _detect_microscope_instance(core) -> "MicroscopeInstance":
        """Pure classification of `core` → `MicroscopeInstance`.

        Extracted so `set_core` can compute the tag once and stash it on
        `self._mi`. Public callers should keep using
        `get_microscope_interface()` / `MI()` / `get_MI()`, all of which
        return the cached value.
        """
        if isinstance(core, PymmcorePlusCore):
            return MicroscopeInstance.MMCORE_PLUS
        if isinstance(core, PymmcoreCore):
            return MicroscopeInstance.PYCROMANAGER_PYTHON
        if isinstance(core, PycroManagerCore):
            return MicroscopeInstance.PYCROMANAGER_JAVA
        if JavaObject and isinstance(core, JavaObject):
            return MicroscopeInstance.PYCROMANAGER_JAVA
        if (
            JavaObject
            and hasattr(core, "_interfaces")
            and len(core._interfaces) > 1
            and core._interfaces[1] == "java.lang.Object"
        ):
            return MicroscopeInstance.PYCROMANAGER_JAVA
        return MicroscopeInstance.UNKNOWN

    def get_microscope_interface(self) -> "MicroscopeInstance":
        return self._mi

    #Alternative method call for the same
    def MI(self):
        return self._mi

    def get_MI(self):
        return self._mi

    #Helper function
    @_hardware_locked
    def java_arr_to_numpy(self, str_vector_obj)-> np.ndarray:
        """
        Converts a pyjavaz.bridge.mmcorej_StrVector object to a NumPy array.
        """
        if str_vector_obj is None:
            return np.array([]) # Return empty array for None input

        # First, try to convert it to a Python list
        python_list = []

        try:
            for item in str_vector_obj:
                python_list.append(str(item)) # Ensure items are string type
        except TypeError:
            # If not directly iterable, it might have a 'toArray()' or similar method
            # that py4j exposes. This is less common for simple lists/vectors.
            # Check if it's a Java object that can be converted to a list
            if hasattr(str_vector_obj, '_java_class') and str_vector_obj._java_class == 'mmcorej.StrVector':
                # Attempt to call common Java collection methods
                try:
                    # Assuming it behaves like a List and has a size() and get() method
                    # This is more robust for general Java List/Vector objects
                    size = str_vector_obj.size()
                    for i in range(size):
                        python_list.append(str(str_vector_obj.get(i)))
                except Exception as e:
                    logging.warning("Could not convert Java object to list using .size()/.get(): %s", e)
                    logging.debug("Attempting direct conversion of unexpected type: %s", type(str_vector_obj))
                    python_list = [str(str_vector_obj)] if isinstance(str_vector_obj, (str, bytes)) else []
            else:
                # If it's not a Java object or simple iterable, treat as single item or error
                logging.warning("Unexpected object type for conversion: %s. Attempting direct conversion.", type(str_vector_obj))
                python_list = [str(str_vector_obj)] if isinstance(str_vector_obj, (str, bytes)) else []

        # Convert the Python list to a NumPy array
        # If the vector contains strings, the dtype will be object or string
        return np.array(python_list, dtype=object) # Use dtype=object for mixed types or strings

    # ---- circular-buffer normalisation helpers (T-C1) ----------------
    #
    # The continuous-sequence primitives below must hand every caller the
    # same thing regardless of backend -- a 2-D ndarray plus a plain dict --
    # so the normalisation lives here instead of being repeated in each
    # dispatch method.

    @staticmethod
    def _metadata_to_dict(md) -> dict:
        """Normalise a backend metadata object to a plain ``dict``.

        ``pymmcore_plus``'s ``Metadata`` is already a ``Mapping`` and the
        tagged-image backends hand back a dict-alike ``.tags``; the raw SWIG
        ``pymmcore.Metadata`` is neither and needs the
        ``GetKeys()``/``GetSingleTag()`` walk that mmpycorex's own
        ``pop_next_tagged_image`` shim uses.
        """
        if md is None:
            return {}
        try:
            return dict(md)
        except (TypeError, ValueError):
            pass
        try:
            return {key: md.GetSingleTag(key).GetValue() for key in md.GetKeys()}
        except Exception as exc:  # pragma: no cover -- unknown metadata shape
            logger.debug(
                "Could not convert metadata object of type %r to dict: %s",
                type(md).__name__, exc,
            )
            return {}

    def _get_image_shape(self) -> tuple[int, int]:
        """Return the cached ``(height, width)`` of one camera frame.

        Read once per popped frame on the live path, so it must not hit the
        hardware every time -- the same reasoning behind the exposure and
        pixel-size caches.
        """
        if self._image_shape_cache is None:
            roi = self.get_roi()
            # ROI is (x, y, width, height); cf. get_image_width/get_image_height.
            self._image_shape_cache = (int(roi[3]), int(roi[2]))
        return self._image_shape_cache

    def invalidate_image_shape_cache(self) -> None:
        """Force the next frame reshape to re-read the ROI."""
        self._image_shape_cache = None

    def _reshape_if_flat(self, pix, tags: dict | None = None) -> np.ndarray:
        """Return ``pix`` as a 2-D array, reshaping a flat buffer if needed.

        ``popNextImageAndMD`` reshapes for us (``fix=True``), but the SWIG and
        Java tagged-image paths hand back a flat buffer. Prefer the frame's
        own Height/Width tags when it carries them, and fall back on the
        cached ROI shape when it does not.
        """
        arr = np.asarray(pix)
        if arr.ndim != 1:
            return arr
        if tags:
            try:
                return arr.reshape(int(tags["Height"]), int(tags["Width"]))
            except (KeyError, TypeError, ValueError):
                pass
        return arr.reshape(self._get_image_shape())

    #Callables
    @_hardware_locked
    def clear_circular_buffer(self) -> None:
        """Discard every frame currently sitting in the circular buffer.

        Called before starting a continuous sequence so the first displayed
        frame is not a stale one left over from the previous run.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.clear_circular_buffer()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.clear_circular_buffer()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.clearCircularBuffer()
        else:
            raise ValueError("Unsupported microscope interface type for clear_circular_buffer.")

    @_hardware_locked
    def clear_roi(self) -> None:
        """
        Clear the region of interest (ROI) for the camera.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.clear_roi()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.clear_roi()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.clearROI()
        else:
            raise ValueError("Unsupported microscope interface type for clear_roi.")
        self.invalidate_image_shape_cache()

    @_hardware_locked
    def get_auto_shutter(self) -> bool:
        """
        Get the current state of the auto shutter.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_auto_shutter()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_auto_shutter()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getAutoShutter()
        else:
            raise ValueError("Unsupported microscope interface type for get_auto_shutter.")
    
    @_hardware_locked
    def get_available_config_groups(self) -> list:
        """
        Get a list of available configuration groups.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.java_arr_to_numpy(self.core.get_available_config_groups())
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return np.array(self.core.get_available_config_groups())
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getAvailableConfigGroups()
        else:
            raise ValueError("Unsupported microscope interface type for get_available_config_group.")
    
    @_hardware_locked
    def get_available_configs(self, config_group) -> list:
        """
        Get a list of available configurations for a given configuration group.
        """
        
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.java_arr_to_numpy(self.core.get_available_configs(config_group))
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_available_configs(config_group)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getAvailableConfigs(config_group)
        else:
            raise ValueError("Unsupported microscope interface type for get_available_configs.")
    
    @_hardware_locked
    def get_config_data(self, config_group, config_name):
        """
        Get the configuration data for a specific configuration group and name.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_config_data(config_group, config_name)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_config_data(config_group, config_name)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getConfigData(config_group, config_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_config_data.")
    
    @_hardware_locked
    def get_config_device_label(self,config_data):
        """
        Get the device label from configuration data. Requires a config_data object (see get_config_data).
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return config_data.getSetting(0).get_device_label()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return config_data.getSetting(0).getDeviceLabel()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return config_data.getSetting(0).getDeviceLabel()
        else:
            raise ValueError("Unsupported microscope interface type for get_config_device_label.")
    
    @_hardware_locked
    def get_config_group_state(self, config_group):
        """
        Get the current state of a configuration group.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_config_group_state(config_group)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_config_group_state(config_group)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getConfigGroupState(config_group)
        else:
            raise ValueError("Unsupported microscope interface type for get_config_group_state.")
        
    @_hardware_locked
    def get_config_property_name(self,config_data):
        """
        Get the device label from configuration data. Requires a config_data object (see get_config_data).
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return config_data.getSetting(0).get_property_name()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return config_data.getSetting(0).getPropertyName()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return config_data.getSetting(0).getPropertyName()
        else:
            raise ValueError("Unsupported microscope interface type for get_config_device_label.")
    
    @_hardware_locked
    def get_current_config(self, config_group) -> str:
        """
        Get the current configuration for a specific configuration group.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_current_config(config_group)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_current_config(config_group)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getCurrentConfig(config_group)
        else:
            raise ValueError("Unsupported microscope interface type for get_current_config.")
    
    @_hardware_locked
    def get_device_type(self, device_name) -> int:
        """
        Get the type of a device by its name.
        """
        #TODO: currently we're returning a SWIG value, 1-15, see MMcontrols line 1404-1422 for interpretation of these. Probably just change this to a string in the future.
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_device_type(device_name).swig_value()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_device_type(device_name)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getDeviceType(device_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_device_type.")
    
    def get_exposure(self, *, use_cache: bool = True) -> float:
        """Return the camera exposure time, caching after the first call.

        napariUpdateLive's rate-limit gate calls this on every candidate
        displayed frame; bench_live_display measured a ~257ms/call cost for
        an uncached PYCROMANAGER_JAVA round trip at that call frequency
        (matching the pixel-size cost before Phase 13.2 cached it), so this
        mirrors get_pixel_size_um's cache pattern. Pass ``use_cache=False``
        to force a fresh hardware query; the cache is also invalidated
        automatically by set_exposure().
        """
        # NOT @_hardware_locked: the cache-hit fast path must return *before*
        # acquiring the hardware lock, so the per-frame display rate-limit gate
        # is never serialized behind a slow stage move or config switch.
        if use_cache and self._exposure_cache is not None:
            return self._exposure_cache
        with self._hw_lock:
            # Re-check under the lock: another thread may have populated the
            # cache while we were waiting for it.
            if use_cache and self._exposure_cache is not None:
                return self._exposure_cache
            if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
                value = self.core.get_exposure()
            elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
                value = self.core.get_exposure()
            elif self._mi == MicroscopeInstance.MMCORE_PLUS:
                value = self.core.getExposure()
            else:
                raise ValueError("Unsupported microscope interface type for getting exposure.")
            self._exposure_cache = value
            return value

    def invalidate_exposure_cache(self) -> None:
        """Force the next :meth:`get_exposure` call to query the hardware."""
        self._exposure_cache = None
    
    @_hardware_locked
    def get_focus_device(self) -> str:
        if self.core is None:
            raise RuntimeError("Microscope core is not set.")
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_focus_device()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_focus_device()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getFocusDevice()
        else:
            # This case should ideally not be reached if all types are covered by the initial union
            raise TypeError(f"Unsupported core type: {type(self.core)}")
        
    @_hardware_locked
    def get_image(self) -> np.ndarray:
        """
        Get the most recently snapped image from the microscope camera.
        
        Return a NumPy array representing the image (Height x Width).
        The image is returned as a 2D array for grayscale images.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            # One bridge round trip for the pixels, then the cached ROI shape.
            # The old code fetched .pix, .tags["Height"] and .tags["Width"]
            # separately -- three Java-bridge attribute fetches per frame --
            # and passed `newshape=`, a np.reshape keyword removed in NumPy
            # 2.1 (this project pins 2.2.6, so that call always raised).
            return self._reshape_if_flat(self.core.get_tagged_image().pix)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return np.asarray(self.core.get_image())
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return np.asarray(self.core.getImage())
        else:
            raise ValueError("Unsupported microscope interface type for getting image.")
    
    @_hardware_locked
    def get_image_width(self) -> int:
        """
        Get the width of the image from the microscope camera.
        """
        return self.get_roi()[2]
    
    @_hardware_locked
    def get_image_height(self) -> int:
        """
        Get the height of the image from the microscope camera.
        """
        return self.get_roi()[3]
    
    @_hardware_locked
    def get_last_image_and_metadata(self) -> tuple[np.ndarray, dict]:
        """Return the newest frame in the circular buffer without removing it.

        This is the ``live_pull_policy == 'latest'`` primitive (T-C2): the
        display wants the most recent frame and does not care how many it
        skipped, so nothing is consumed and the buffer cannot overflow.

        Returns a backend-blind ``(2-D ndarray, dict)``.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            tagged = self.core.get_last_tagged_image()
            tags = self._metadata_to_dict(tagged.tags)
            return self._reshape_if_flat(tagged.pix, tags), tags
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            md = PymmcoreMetadata()
            pix = self.core.get_last_image_md(0, 0, md)
            tags = self._metadata_to_dict(md)
            return self._reshape_if_flat(pix, tags), tags
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            pix, md = self.core.getLastImageAndMD()
            tags = self._metadata_to_dict(md)
            return self._reshape_if_flat(pix, tags), tags
        else:
            raise ValueError("Unsupported microscope interface type for get_last_image_and_metadata.")

    @_hardware_locked
    def get_loaded_devices(self) -> list:
        """
        Get a list of loaded devices in the microscope core.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.java_arr_to_numpy(self.core.get_loaded_devices())
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_loaded_devices()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getLoadedDevices()
        else:
            raise ValueError("Unsupported microscope interface type for get_loaded_devices.")
        
    def get_pixel_size_um(self, *, use_cache: bool = True) -> float:
        """Return the pixel size in µm, caching after the first call.

        Pass ``use_cache=False`` to force a fresh hardware query (e.g. after
        an objective change).
        """
        # NOT @_hardware_locked -- same reason as get_exposure(): the cache-hit
        # fast path returns before acquiring the hardware lock.
        if use_cache and self._pixel_size_um_cache is not None:
            return self._pixel_size_um_cache
        with self._hw_lock:
            if use_cache and self._pixel_size_um_cache is not None:
                return self._pixel_size_um_cache
            if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
                value = self.core.get_pixel_size_um()
            elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
                value = self.core.get_pixel_size_um()
            elif self._mi == MicroscopeInstance.MMCORE_PLUS:
                value = self.core.getPixelSizeUm()
            else:
                value = 1.0
            self._pixel_size_um_cache = value
            return value

    def invalidate_pixel_size_cache(self) -> None:
        """Force the next :meth:`get_pixel_size_um` call to query the hardware."""
        self._pixel_size_um_cache = None
    
    @_hardware_locked
    def get_position(self, device_name: str) -> tuple:
        """
        Get the current position of a device.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_position(device_name)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_position(device_name)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getPosition(device_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_position.")

    @_hardware_locked
    def get_property(self, device_name, property_name):
        """
        Get the value of a property for a specific device.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_property(device_name, property_name)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_property(device_name, property_name)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getProperty(device_name, property_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_property.")
    
    @_hardware_locked
    def has_property_limits(self, device_name, property_name):
        """
        Check if a property has limits.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.has_property_limits(device_name, property_name)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.has_property_limits(device_name, property_name)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.hasPropertyLimits(device_name, property_name)
        else:
            raise ValueError("Unsupported microscope interface type for has_property_limits.")
    
    @_hardware_locked
    def get_property_lower_limit(self, device_name, property_name):
        """
        Get the lower limit of a property.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_property_lower_limit(device_name, property_name)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_property_lower_limit(device_name, property_name)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getPropertyLowerLimit(device_name, property_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_property_lower_limit.")
    
    @_hardware_locked
    def get_property_upper_limit(self, device_name, property_name):
        """
        Get the upper limit of a property.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_property_upper_limit(device_name, property_name)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_property_upper_limit(device_name, property_name)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getPropertyUpperLimit(device_name, property_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_property_upper_limit.")
    
    @_hardware_locked
    def get_remaining_image_count(self) -> int:
        """Number of frames waiting in the circular buffer.

        Poll this before :meth:`pop_next_image_and_metadata` -- popping an
        empty buffer raises on every backend. A count that keeps climbing
        means the consumer is slower than the camera.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_remaining_image_count()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_remaining_image_count()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getRemainingImageCount()
        else:
            raise ValueError("Unsupported microscope interface type for get_remaining_image_count.")

    @_hardware_locked
    def get_roi(self):
        """
        Get the current ROI.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return np.array(self.core.get_roi())
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_roi()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getROI()
        else:
            raise ValueError("Unsupported microscope interface type for get_roi.")
    
    @_hardware_locked
    def get_sensor_size(self) -> tuple:
        """Return (width, height) of the full camera sensor independent of any active ROI.

        Implemented by temporarily clearing the ROI, reading the full-frame dimensions,
        then restoring the original ROI.  Safe to call from any thread that is not
        actively running an acquisition; the caller is responsible for pausing live
        mode beforehand if needed (the same pattern used by setROI()).
        """
        original_roi = self.get_roi()
        try:
            self.clear_roi()
            full = self.get_roi()
            return (int(full[2]), int(full[3]))
        except Exception as exc:
            import logging as _logging
            _logging.warning("get_sensor_size: could not determine sensor size: %s", exc)
            # Fallback: treat current ROI extent as the sensor limit.
            return (int(original_roi[2]), int(original_roi[3]))
        finally:
            try:
                self.set_roi(original_roi)
            except Exception:
                pass  # best-effort restore

    @_hardware_locked
    def get_shutter_device(self) -> str:
        """
        Get the current shutter device.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_shutter_device()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_shutter_device()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getShutterDevice()
        else:
            raise ValueError("Unsupported microscope interface type for get_shutter_device.")
    
    @_hardware_locked
    def get_shutter_open(self) -> bool:
        """
        Get the current state of the shutter (open or closed).
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_shutter_open()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_shutter_open()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getShutterOpen()
        else:
            raise ValueError("Unsupported microscope interface type for get_shutter_open.")
    
    @_hardware_locked
    def get_xy_position(self, xy_stage_name: str | None = None) -> tuple:
        """
        Get the current X-Y position of a stage.
        """
        try:
            if xy_stage_name is None:
                xy_stage_name = self.get_xy_stage_device()
            if not xy_stage_name:
                #No XY stage configured in the MM config - nothing to query.
                return [0,0]

            if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
                return self.core.get_xy_position(xy_stage_name)
            elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
                return self.core.get_xy_position(xy_stage_name)
            elif self._mi == MicroscopeInstance.MMCORE_PLUS:
                return self.core.getXYPosition(xy_stage_name)
            else:
                raise ValueError("Unsupported microscope interface type for get_xy_position.")
        except (RuntimeError, OSError, AttributeError) as exc:
            logger.warning('get_xy_position(%s) failed: %s', xy_stage_name, exc)
            return [0,0]

    @_hardware_locked
    def get_xy_stage_device(self) -> str:
        """
        Get the name of the X-Y stage device.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_xy_stage_device()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_xy_stage_device()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getXYStageDevice()
        else:
            raise ValueError("Unsupported microscope interface type for get_xy_stage_device.")
    
    @_hardware_locked
    def get_xy_stage_position(self, xy_stage_name: str) -> tuple:
        """
        Get the current position of the X-Y stage.
        """
        try:
            if not xy_stage_name:
                #No XY stage configured in the MM config - nothing to query.
                return [0,0]
            if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
                logging.info("get_xy_stage_position not fully implemented for PYCROMANAGER_JAVA; attempting fallback")
                return self.core.get_xy_stage_position(xy_stage_name)
            elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
                return self.core.get_xy_position(xy_stage_name)
            elif self._mi == MicroscopeInstance.MMCORE_PLUS:
                return self.core.getXYPosition(xy_stage_name)
            else:
                raise ValueError("Unsupported microscope interface type for get_xy_stage_position.")
        except (RuntimeError, OSError, AttributeError) as exc:
            logger.warning('get_xy_stage_position(%s) failed: %s', xy_stage_name, exc)
            return [0,0]
        
    @_hardware_locked
    def is_sequence_running(self) -> bool:
        """Whether a (continuous or finite) sequence acquisition is running."""
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.is_sequence_running()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.is_sequence_running()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.isSequenceRunning()
        else:
            raise ValueError("Unsupported microscope interface type for is_sequence_running.")

    @_hardware_locked
    def pop_next_image_and_metadata(self) -> tuple[np.ndarray, dict]:
        """Remove and return the oldest frame in the circular buffer.

        This is the ``live_pull_policy == 'sequential'`` primitive (T-C2):
        every frame is delivered in order, at the cost of overflowing the
        buffer if the consumer falls behind. Guard the call with
        :meth:`get_remaining_image_count`.

        Returns a backend-blind ``(2-D ndarray, dict)``.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            tagged = self.core.pop_next_tagged_image()
            tags = self._metadata_to_dict(tagged.tags)
            return self._reshape_if_flat(tagged.pix, tags), tags
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            # mmpycorex injects pop_next_tagged_image onto the snake_case
            # CMMCore subclass (launcher.py) -- it is not a CMMCore method.
            tagged = self.core.pop_next_tagged_image()
            tags = self._metadata_to_dict(tagged.tags)
            return self._reshape_if_flat(tagged.pix, tags), tags
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            pix, md = self.core.popNextImageAndMD()
            tags = self._metadata_to_dict(md)
            return self._reshape_if_flat(pix, tags), tags
        else:
            raise ValueError("Unsupported microscope interface type for pop_next_image_and_metadata.")

    @_hardware_locked
    def set_auto_shutter(self, auto_shutter: bool) -> None:
        """
        Set the auto shutter state.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_auto_shutter(auto_shutter)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_auto_shutter(auto_shutter)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.setAutoShutter(auto_shutter)
        else:
            raise ValueError("Unsupported microscope interface type for set_auto_shutter.")
    
    @_hardware_locked
    def set_config(self, config_group, config_name) -> None:
        """
        Set the configuration for a specific configuration group.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_config(config_group, config_name)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_config(config_group, config_name)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.setConfig(config_group, config_name)
        else:
            raise ValueError("Unsupported microscope interface type for set_config.")
    
    @_hardware_locked
    def set_exposure(self,exposure_time: float) -> None:
        """
        Set the exposure time for the microscope camera.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_exposure(exposure_time)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_exposure(exposure_time)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.setExposure(exposure_time)
        else:
            raise ValueError("Unsupported microscope interface type for setting exposure.")
        self.invalidate_exposure_cache()

    @_hardware_locked
    def set_focus_device(self,focus_device) -> None:
        """
        Set the focus device.
        """
        if self.core is None:
            raise RuntimeError("Microscope core is not set.")
        
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_focus_device(focus_device)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_focus_device(focus_device)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.setFocusDevice(focus_device)
        else:
            raise ValueError("Unsupported microscope interface type for setting focus device.")
    
    @_hardware_locked
    def set_property(self, device_name, property_name, newval):
        """
        Get the value of a property for a specific device.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.set_property(device_name, property_name, newval)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.set_property(device_name, property_name, newval)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return self.core.setProperty(device_name, property_name, newval)
        else:
            raise ValueError("Unsupported microscope interface type for get_property.")
    
    @_hardware_locked
    def set_relative_position(self, device_name: str, pos_change: float) -> None:
        """
        Set the relative position of a device.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_relative_position(device_name, pos_change)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_relative_position(device_name, pos_change)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.setRelativePosition(device_name, pos_change)
        else:
            raise ValueError("Unsupported microscope interface type for set_relative_position.")
    
    @_hardware_locked
    def set_relative_xy_position(self, pos_change: tuple) -> None:
        """
        Set the relative position of the X-Y stage.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_relative_xy_position(pos_change[0], pos_change[1])
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_relative_xy_position(pos_change[0], pos_change[1])
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.setRelativeXYPosition(pos_change[0], pos_change[1])
        else:
            raise ValueError("Unsupported microscope interface type for set_relative_xy_position.")        
    
    @_hardware_locked
    def set_roi(self, roi: tuple) -> None:
        """
        Set the region of interest (ROI) for the camera.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_roi(roi[0], roi[1], roi[2], roi[3])
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_roi(roi[0], roi[1], roi[2], roi[3])
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.setROI(roi[0], roi[1], roi[2], roi[3])
        else:
            raise ValueError("Unsupported microscope interface type for set_roi.")
        self.invalidate_image_shape_cache()
    
    @_hardware_locked
    def set_shutter_device(self, shutter_device: str) -> None:
        """
        Set the shutter device.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_shutter_device(shutter_device)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_shutter_device(shutter_device)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.setShutterDevice(shutter_device)
        else:
            raise ValueError("Unsupported microscope interface type for set_shutter_device.")
    
    @_hardware_locked
    def set_shutter_open(self, open_shutter: bool) -> None:
        """
        Set the state of the shutter (open or closed).
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_shutter_open(open_shutter)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_shutter_open(open_shutter)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.setShutterOpen(open_shutter)
        else:
            raise ValueError("Unsupported microscope interface type for set_shutter_open.")
    
    @_hardware_locked
    def snap_image(self) -> None:
        """
        Snap an image using the microscope camera.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.snap_image()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.snap_image()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.snapImage()
        else:
            raise ValueError("Unsupported microscope interface type for snapping image.")

    @_hardware_locked
    def start_continuous_sequence_acquisition(self, interval_ms: float = 0) -> None:
        """Start a free-running acquisition into the circular buffer.

        The camera runs as fast as its exposure allows and drops frames into
        the circular buffer; no acquisition engine, no ``MDAEvent``, no
        per-frame pydantic validation. This is what MM's own live window,
        napari-micromanager and any plain pycromanager script use, and it is
        what T-C3's live worker will pull from. ``interval_ms=0`` means "as
        fast as the camera allows".

        Stop it with :meth:`stop_sequence_acquisition`.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.start_continuous_sequence_acquisition(interval_ms)
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.start_continuous_sequence_acquisition(interval_ms)
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.startContinuousSequenceAcquisition(interval_ms)
        else:
            raise ValueError(
                "Unsupported microscope interface type for start_continuous_sequence_acquisition."
            )

    @_hardware_locked
    def stop_sequence_acquisition(self) -> None:
        """
        Stop the sequence acquisition of images.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.stop_sequence_acquisition()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.stop_sequence_acquisition()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.stopSequenceAcquisition()
            try:
                if self.core.mda.is_running():
                    self.core.mda.cancel()
            except Exception as exc:  # pragma: no cover — defensive
                logging.warning("mda.cancel() failed during stop_sequence_acquisition: %s", exc)
        else:
            raise ValueError("Unsupported microscope interface type for stop_sequence_acquisition.")

    @_hardware_locked
    def verbose_info_from_config_group_state(self,config_group_state) -> str:
        """
        Get the verbose information from a configuration group state.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            return config_group_state.get_verbose()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return config_group_state.getVerbose()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            return config_group_state.getVerbose()
        else:
            raise ValueError("Unsupported microscope interface type for verbose_info_from_config_group_state.")
    
    @_hardware_locked
    def wait_for_system(self) -> None:
        """
        Wait for the microscope system to be ready.
        """
        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.wait_for_system()
        elif self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.wait_for_system()
        elif self._mi == MicroscopeInstance.MMCORE_PLUS:
            self.core.waitForSystem()
        else:
            raise ValueError("Unsupported microscope interface type for wait_for_system.")
    
    def create_mda(self, num_time_points:int=10, time_interval_s=0.0,z_start=0.0,z_end=0.0,z_step=0.0,channel_group='Channel',channels=None,channel_exposures_ms=None,xy_positions=None,xyz_positions=None,position_labels=None,order='t'):
        """Build a pycromanager MDA event list from a synthetic plan.

        Validates the plan first and raises :class:`MDAEventError` on
        any impossible combination — negative frame counts, a z range
        with a zero step, channels named with empty strings, or a
        ``channel_exposures_ms`` length that doesn't match ``channels``.

        Mutable defaults have been replaced with ``None``; inside the
        function the empty-list axes are then dropped (pycromanager
        rejects ``xy_positions=[]`` *and* ``xyz_positions=[]`` together
        as "incompatible arguments"). A bare ``create_mda(num_time_points=2)``
        now produces a 2-event time-only plan instead of raising
        ValueError from the pycromanager helper.
        """
        # Plan-level validation — raise MDAEventError, never let nonsense
        # silently propagate into the pycromanager helper.
        if not isinstance(num_time_points, int) or num_time_points < 1:
            raise MDAEventError(
                f"num_time_points must be a positive int, got {num_time_points!r}"
            )
        if z_step == 0 and z_start != z_end:
            raise MDAEventError(
                f"z_step=0 with z_start={z_start!r} != z_end={z_end!r} would "
                f"produce an infinite z-stack"
            )
        if channels:
            for c in channels:
                if not isinstance(c, str) or c == "":
                    raise MDAEventError(
                        f"channels must be non-empty strings; got {c!r}"
                    )
            if channel_exposures_ms is not None and len(channel_exposures_ms) and len(channel_exposures_ms) != len(channels):
                raise MDAEventError(
                    f"channel_exposures_ms length {len(channel_exposures_ms)} "
                    f"does not match channels length {len(channels)}"
                )
        if not channel_group:
            if channels:
                raise MDAEventError(
                    "channels supplied but channel_group is empty"
                )

        if self._mi == MicroscopeInstance.PYCROMANAGER_JAVA or self._mi == MicroscopeInstance.PYCROMANAGER_PYTHON or self._mi == MicroscopeInstance.MMCORE_PLUS:
            # Forward None for any axis the caller didn't supply so the
            # pycromanager helper's mutex check (xy vs xyz, channels vs
            # exposures, etc.) sees genuine absence rather than empty-list
            # presence.
            try:
                self.mda = multi_d_acquisition_events(
                    num_time_points=num_time_points,
                    time_interval_s=time_interval_s,
                    z_start=z_start,
                    z_end=z_end,
                    z_step=z_step,
                    channel_group=channel_group,
                    channels=channels,
                    channel_exposures_ms=channel_exposures_ms,
                    xy_positions=xy_positions,
                    xyz_positions=xyz_positions,
                    position_labels=position_labels,
                    order=order,
                )
            except ValueError as exc:
                # Surface as MDAEventError so downstream callers can catch
                # one type for "the plan was rejected".
                raise MDAEventError(str(exc)) from exc
            return self.mda
        else:
            raise ValueError("Unsupported microscope interface type for create_mda.")
            
    
        
        
        
        