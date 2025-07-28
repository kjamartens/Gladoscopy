
#Goal: a common interface layer for multiple backends to control micromannager.

#Supported for now:

#Pycromanager - JAVA
#Pycromanager - Python
#MMCore-plus

from enum import Enum
import numpy as np
from pycromanager import multi_d_acquisition_events

from pycromanager import JavaObject, Core as PycroManagerCore
from pymmcore import CMMCore as PymmcoreCore
from pymmcore_plus import CMMCorePlus as PymmcorePlusCore


class MicroscopeInstance(Enum):
    PYCROMANAGER_JAVA = 'PycromanagerJava'
    PYCROMANAGER_PYTHON = 'PycromanagerPython'
    MMCORE_PLUS = 'MMCorePlus'
    UNKNOWN = 'Unknown' # Add an unknown type for comprehensive handling

class MicroscopeInterfaceLayer:
    def __init__(self):
        self.core: PycroManagerCore | PymmcoreCore | PymmcorePlusCore | None = None
        self.mda: dict | None = None
    def set_core(self, core):
        self.core = core

    def get_core(self):
        return self.core

    def get_microscope_interface(self):
        if isinstance(self.core, PymmcorePlusCore):
            return MicroscopeInstance.MMCORE_PLUS
        elif isinstance(self.core, PymmcoreCore):
            return MicroscopeInstance.PYCROMANAGER_PYTHON
        elif isinstance(self.core, PycroManagerCore):
            return MicroscopeInstance.PYCROMANAGER_JAVA
        elif JavaObject and isinstance(self.core, JavaObject):
            return MicroscopeInstance.PYCROMANAGER_JAVA
        elif JavaObject and hasattr(self.core, '_interfaces') and len(self.core._interfaces) > 1 and self.core._interfaces[1] == 'java.lang.Object':
            return MicroscopeInstance.PYCROMANAGER_JAVA
        elif self.core is None:
            return MicroscopeInstance.UNKNOWN
        else:
            #Unknown!
            return MicroscopeInstance.UNKNOWN

    #Alternative method call for the same
    def MI(self):
        return self.get_microscope_interface()
    
    def get_MI(self):
        return self.get_microscope_interface()

    #Helper function
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
                    print(f"Warning: Could not convert Java object to list using .size() and .get(): {e}")
                    # Fallback: If it's still not a list, maybe it's a single string
                    # or something else unexpected.
                    print(f"Attempting direct conversion of unexpected type: {type(str_vector_obj)}")
                    python_list = [str(str_vector_obj)] if isinstance(str_vector_obj, (str, bytes)) else []
            else:
                # If it's not a Java object or simple iterable, treat as single item or error
                print(f"Warning: Unexpected object type for conversion: {type(str_vector_obj)}. Attempting direct conversion.")
                python_list = [str(str_vector_obj)] if isinstance(str_vector_obj, (str, bytes)) else []

        # Convert the Python list to a NumPy array
        # If the vector contains strings, the dtype will be object or string
        return np.array(python_list, dtype=object) # Use dtype=object for mixed types or strings


    #Callables

    def clear_roi(self) -> None:
        """
        Clear the region of interest (ROI) for the camera.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.clear_roi()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.clear_roi()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.clearROI()
        else:
            raise ValueError("Unsupported microscope interface type for clear_roi.")

    def get_auto_shutter(self) -> bool:
        """
        Get the current state of the auto shutter.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_auto_shutter()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_auto_shutter()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getAutoShutter()
        else:
            raise ValueError("Unsupported microscope interface type for get_auto_shutter.")
    
    def get_available_config_groups(self) -> list:
        """
        Get a list of available configuration groups.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.java_arr_to_numpy(self.core.get_available_config_groups())
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return np.array(self.core.get_available_config_groups())
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getAvailableConfigGroups()
        else:
            raise ValueError("Unsupported microscope interface type for get_available_config_group.")
    
    def get_available_configs(self, config_group) -> list:
        """
        Get a list of available configurations for a given configuration group.
        """
        
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.java_arr_to_numpy(self.core.get_available_configs(config_group))
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_available_configs(config_group)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getAvailableConfigs(config_group)
        else:
            raise ValueError("Unsupported microscope interface type for get_available_configs.")
    
    def get_config_data(self, config_group, config_name):
        """
        Get the configuration data for a specific configuration group and name.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_config_data(config_group, config_name)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_config_data(config_group, config_name)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getConfigData(config_group, config_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_config_data.")
    
    def get_config_device_label(self,config_data):
        """
        Get the device label from configuration data. Requires a config_data object (see get_config_data).
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return config_data.getSetting(0).get_device_label()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return config_data.getSetting(0).getDeviceLabel()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return config_data.getSetting(0).getDeviceLabel()
        else:
            raise ValueError("Unsupported microscope interface type for get_config_device_label.")
    
    def get_config_group_state(self, config_group):
        """
        Get the current state of a configuration group.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_config_group_state(config_group)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_config_group_state(config_group)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getConfigGroupState(config_group)
        else:
            raise ValueError("Unsupported microscope interface type for get_config_group_state.")
        
    def get_config_property_name(self,config_data):
        """
        Get the device label from configuration data. Requires a config_data object (see get_config_data).
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return config_data.getSetting(0).get_property_name()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return config_data.getSetting(0).getPropertyName()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return config_data.getSetting(0).getPropertyName()
        else:
            raise ValueError("Unsupported microscope interface type for get_config_device_label.")
    
    def get_current_config(self, config_group) -> str:
        """
        Get the current configuration for a specific configuration group.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_current_config(config_group)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_current_config(config_group)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getCurrentConfig(config_group)
        else:
            raise ValueError("Unsupported microscope interface type for get_current_config.")
    
    def get_device_type(self, device_name) -> int:
        """
        Get the type of a device by its name.
        """
        #TODO: currently we're returning a SWIG value, 1-15, see MMcontrols line 1404-1422 for interpretation of these. Probably just change this to a string in the future.
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_device_type(device_name).swig_value()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_device_type(device_name)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getDeviceType(device_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_device_type.")
    
    def get_exposure(self) -> float:
        """
        Get the exposure time for the microscope camera.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_exposure()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_exposure()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getExposure()
        else:
            raise ValueError("Unsupported microscope interface type for getting exposure.")
    
    def get_focus_device(self) -> str:
        if self.core is None:
            raise RuntimeError("Microscope core is not set.")
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_focus_device()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_focus_device()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getFocusDevice()
        else:
            # This case should ideally not be reached if all types are covered by the initial union
            raise TypeError(f"Unsupported core type: {type(self.core)}")
        
    def get_image(self) -> np.ndarray:
        """
        Get the most recently snapped image from the microscope camera.
        
        Return a NumPy array representing the image (Height x Width).
        The image is returned as a 2D array for grayscale images.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            newImage = self.core.get_tagged_image()
            return np.reshape(newImage.pix, newshape=[newImage.tags["Height"], newImage.tags["Width"]])
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return np.array(self.core.get_image())
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return np.array(self.core.getImage())
        else:
            raise ValueError("Unsupported microscope interface type for getting image.")
    
    def get_image_width(self) -> int:
        """
        Get the width of the image from the microscope camera.
        """
        return self.get_roi()[2]
    
    def get_image_height(self) -> int:
        """
        Get the height of the image from the microscope camera.
        """
        return self.get_roi()[3]
    
    def get_loaded_devices(self) -> list:
        """
        Get a list of loaded devices in the microscope core.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.java_arr_to_numpy(self.core.get_loaded_devices())
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_loaded_devices()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getLoadedDevices()
        else:
            raise ValueError("Unsupported microscope interface type for get_loaded_devices.")
        
    def get_pixel_size_um(self):
        """
        Get the pixel size of the camera.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_pixel_size_um()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_pixel_size_um()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getPixelSizeUm()
        else:
            return 1.0
    
    def get_position(self, device_name: str) -> tuple:
        """
        Get the current position of a device.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_position(device_name)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_position(device_name)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getPosition(device_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_position.")

    def get_property(self, device_name, property_name):
        """
        Get the value of a property for a specific device.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_property(device_name, property_name)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_property(device_name, property_name)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getProperty(device_name, property_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_property.")
    
    def has_property_limits(self, device_name, property_name):
        """
        Check if a property has limits.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.has_property_limits(device_name, property_name)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.has_property_limits(device_name, property_name)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.hasPropertyLimits(device_name, property_name)
        else:
            raise ValueError("Unsupported microscope interface type for has_property_limits.")
    
    def get_property_lower_limit(self, device_name, property_name):
        """
        Get the lower limit of a property.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_property_lower_limit(device_name, property_name)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_property_lower_limit(device_name, property_name)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getPropertyLowerLimit(device_name, property_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_property_lower_limit.")
    
    def get_property_upper_limit(self, device_name, property_name):
        """
        Get the upper limit of a property.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_property_upper_limit(device_name, property_name)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_property_upper_limit(device_name, property_name)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getPropertyUpperLimit(device_name, property_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_property_upper_limit.")
    
    def get_roi(self):
        """
        Get the current ROI.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return np.array(self.core.get_roi())
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_roi()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getROI()
        else:
            raise ValueError("Unsupported microscope interface type for get_roi.")
    
    def get_shutter_device(self) -> str:
        """
        Get the current shutter device.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_shutter_device()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_shutter_device()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getShutterDevice()
        else:
            raise ValueError("Unsupported microscope interface type for get_shutter_device.")
    
    def get_shutter_open(self) -> bool:
        """
        Get the current state of the shutter (open or closed).
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_shutter_open()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_shutter_open()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getShutterOpen()
        else:
            raise ValueError("Unsupported microscope interface type for get_shutter_open.")
    
    def get_xy_position(self, xy_stage_name: str | None = None) -> tuple:
        """
        Get the current X-Y position of a stage.
        """
        if xy_stage_name is None:
            xy_stage_name = self.get_xy_stage_device()
            
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_xy_position(xy_stage_name)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_xy_position(xy_stage_name)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getXYPosition(xy_stage_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_xy_position.")
    
    def get_xy_stage_device(self) -> str:
        """
        Get the name of the X-Y stage device.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.get_xy_stage_device()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_xy_stage_device()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getXYStageDevice()
        else:
            raise ValueError("Unsupported microscope interface type for get_xy_stage_device.")
    
    def get_xy_stage_position(self, xy_stage_name: str) -> tuple:
        """
        Get the current position of the X-Y stage.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            print('TODO: get_xy_stage_position not implemented for PYCROMANAGER_JAVA')
            return self.core.get_xy_stage_position(xy_stage_name)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.get_xy_position(xy_stage_name)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.getXYPosition(xy_stage_name)
        else:
            raise ValueError("Unsupported microscope interface type for get_xy_stage_position.")
    
    def set_auto_shutter(self, auto_shutter: bool) -> None:
        """
        Set the auto shutter state.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_auto_shutter(auto_shutter)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_auto_shutter(auto_shutter)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.setAutoShutter(auto_shutter)
        else:
            raise ValueError("Unsupported microscope interface type for set_auto_shutter.")
    
    def set_config(self, config_group, config_name) -> None:
        """
        Set the configuration for a specific configuration group.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_config(config_group, config_name)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_config(config_group, config_name)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.setConfig(config_group, config_name)
        else:
            raise ValueError("Unsupported microscope interface type for set_config.")
    
    def set_exposure(self,exposure_time: float) -> None:
        """
        Set the exposure time for the microscope camera.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_exposure(exposure_time)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_exposure(exposure_time)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.setExposure(exposure_time)
        else:
            raise ValueError("Unsupported microscope interface type for setting exposure.")

    def set_focus_device(self,focus_device) -> None:
        """
        Set the focus device.
        """
        if self.core is None:
            raise RuntimeError("Microscope core is not set.")
        
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_focus_device(focus_device)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_focus_device(focus_device)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.setFocusDevice(focus_device)
        else:
            raise ValueError("Unsupported microscope interface type for setting focus device.")
    
    def set_property(self, device_name, property_name, newval):
        """
        Get the value of a property for a specific device.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return self.core.set_property(device_name, property_name, newval)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return self.core.set_property(device_name, property_name, newval)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return self.core.setProperty(device_name, property_name, newval)
        else:
            raise ValueError("Unsupported microscope interface type for get_property.")
    
    def set_relative_position(self, device_name: str, pos_change: float) -> None:
        """
        Set the relative position of a device.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_relative_position(device_name, pos_change)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_relative_position(device_name, pos_change)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.setRelativePosition(device_name, pos_change)
        else:
            raise ValueError("Unsupported microscope interface type for set_relative_position.")
    
    def set_relative_xy_position(self, pos_change: tuple) -> None:
        """
        Set the relative position of the X-Y stage.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_relative_xy_position(pos_change[0], pos_change[1])
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_relative_xy_position(pos_change[0], pos_change[1])
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.setRelativeXYPosition(pos_change[0], pos_change[1])
        else:
            raise ValueError("Unsupported microscope interface type for set_relative_xy_position.")        
    
    def set_roi(self, roi: tuple) -> None:
        """
        Set the region of interest (ROI) for the camera.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_roi(roi[0], roi[1], roi[2], roi[3])
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_roi(roi[0], roi[1], roi[2], roi[3])
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.setROI(roi[0], roi[1], roi[2], roi[3])
        else:
            raise ValueError("Unsupported microscope interface type for set_roi.")
    
    def set_shutter_device(self, shutter_device: str) -> None:
        """
        Set the shutter device.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_shutter_device(shutter_device)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_shutter_device(shutter_device)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.setShutterDevice(shutter_device)
        else:
            raise ValueError("Unsupported microscope interface type for set_shutter_device.")
    
    def set_shutter_open(self, open_shutter: bool) -> None:
        """
        Set the state of the shutter (open or closed).
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.set_shutter_open(open_shutter)
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.set_shutter_open(open_shutter)
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.setShutterOpen(open_shutter)
        else:
            raise ValueError("Unsupported microscope interface type for set_shutter_open.")
    
    def snap_image(self) -> None:
        """
        Snap an image using the microscope camera.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.snap_image()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.snap_image()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.snapImage()
        else:
            raise ValueError("Unsupported microscope interface type for snapping image.")

    def stop_sequence_acquisition(self) -> None:
        """
        Stop the sequence acquisition of images.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.stop_sequence_acquisition()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.stop_sequence_acquisition()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.stopSequenceAcquisition()
        else:
            raise ValueError("Unsupported microscope interface type for stop_sequence_acquisition.")

    def verbose_info_from_config_group_state(self,config_group_state) -> str:
        """
        Get the verbose information from a configuration group state.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            return config_group_state.get_verbose()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            return config_group_state.getVerbose()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            return config_group_state.getVerbose()
        else:
            raise ValueError("Unsupported microscope interface type for verbose_info_from_config_group_state.")
    
    def wait_for_system(self) -> None:
        """
        Wait for the microscope system to be ready.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA:
            self.core.wait_for_system()
        elif self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON:
            self.core.wait_for_system()
        elif self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.core.waitForSystem()
        else:
            raise ValueError("Unsupported microscope interface type for wait_for_system.")
    
    def create_mda(self, num_time_points:int=10, time_interval_s=0.0,z_start=0.0,z_end=0.0,z_step=0.0,channel_group='Channel',channels=[],channel_exposures_ms=[],xy_positions=[],xyz_positions=[],position_labels=[],order='t'):
        """
        Create MDA acquisition via multi_d_acquisition_events or via useq.
        
        For now, return in Pycromanager format, which is a dictionary. Possibly later TODO: change default output to a useq object.
        """
        if self.MI() == MicroscopeInstance.PYCROMANAGER_JAVA or self.MI() == MicroscopeInstance.PYCROMANAGER_PYTHON or self.MI() == MicroscopeInstance.MMCORE_PLUS:
            self.mda = multi_d_acquisition_events(num_time_points=num_time_points, time_interval_s=time_interval_s,z_start=z_start,z_end=z_end,z_step=z_step,channel_group=channel_group,channels=channels,channel_exposures_ms=channel_exposures_ms,xy_positions=xy_positions,xyz_positions=xyz_positions,position_labels=position_labels,order=order)
            return self.mda
        else:
            raise ValueError("Unsupported microscope interface type for create_mda.")
            
    
        
        
        
        