import inspect
import logging
import os
import sys
import time

import numpy as np
from scipy.signal.windows import tukey

import glados_pycromanager.GUI.utils as utils

# Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
from glados_pycromanager.autonomous.registry import register


def __function_metadata__():
    return { 
        "RealTimeFFT": {
            "required_kwargs": [
            ],
            "optional_kwargs": [
                {"name": "LogScale", "description": "Apply log scaling to FFT", "default": True, "type": bool},
                {"name": "WindowTaper", "description": "Apply a Tukey window taper to the image before the FFT, to reduce edge/streaking artifacts", "default": False, "type": bool},
                {"name": "WindowTaperStrength", "description": "Tukey window taper strength, 0-1 (0 = no taper/rectangular, 1 = full cosine taper across the whole image, like a Hann window)", "default": 0.25, "type": float},
            ],
            "help_string": "Calculates and displays the 2D FFT magnitude spectrum in real-time.",
            "display_name": "Real-Time FFT",
            "run_delay": 0,
            "visualise_delay": 200,
            "visualisation_type": "image", # Changed to 'image' for FFT display
            "input":[],
            "output":[],
            # diplib's FourierTransform holds the Python GIL for most of its
            # runtime (benchmarked ~80%+), which starves the Qt main thread when
            # frames arrive faster than the FFT can keep up -- see
            # https://github.com/kjamartens/Gladoscopy/issues/16. Run this node's
            # init/run/end in a separate process instead of a QThread so it can
            # never block the UI regardless of exposure time.
            "__runInSubprocess__": True,
            # visualise() runs against a shadow instance in the main process (a
            # napari layer cannot cross a process boundary), so the child mirrors
            # these attributes back after every frame. Declare only what
            # visualise() actually reads: this used to be *every* picklable
            # attribute, which shipped the cached Tukey window alongside the FFT
            # on every frame. `firstLayerInit` is set by visualise_init() on the
            # shadow itself and must not be overwritten from the child.
            "__snapshot_attrs__": ["fft_display"],
        }
    }

#-------------------------------------------------------------------------------------------------------------------------------
# Callable functions
#-------------------------------------------------------------------------------------------------------------------------------

@register("FFT_im.RealTimeFFT")
class RealTimeFFT:
    def __init__(self, core, **kwargs):
        # Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(), class_name, kwargs) #type:ignore

        # diplib.viewer assumes IPython.terminal.pt_inputhooks is already an
        # attribute of IPython.terminal whenever 'IPython' is in sys.modules,
        # but modern IPython only sets that attribute once the submodule has
        # actually been imported -- pre-import it ourselves to dodge diplib's
        # `terminal.pt_inputhooks.register(...)` AttributeError.
        if 'IPython' in sys.modules:
            import IPython.terminal.pt_inputhooks  # noqa: F401
        import diplib as dip
        self._dip = dip

        self.fft_display = np.zeros((512, 512)) # Placeholder
        self.log_scale = kwargs.get('LogScale', True)
        self.window_taper = str(kwargs.get('WindowTaper', False)).lower() in ('true', '1')
        self.window_taper_strength = min(max(float(kwargs.get('WindowTaperStrength', 0.25)), 0.0), 1.0)
        self._taper_window = None
        self._taper_window_shape = None
        return None

    def _get_taper_window(self, shape):
        """Builds (and caches) a separable 2D Tukey window matching `shape`."""
        if self._taper_window is None or self._taper_window_shape != shape:
            window_y = tukey(shape[0], self.window_taper_strength)
            window_x = tukey(shape[1], self.window_taper_strength)
            self._taper_window = np.outer(window_y, window_x)
            self._taper_window_shape = shape
        return self._taper_window

    def run(self, image, metadata, shared_data, core, **kwargs):
        """
        Performs the 2D FFT on the incoming image buffer.
        """
        run_start = time.time()
        try:
            # 1. Compute 2D FFT
            # fft_data = np.fft.fft2(image)

            if self.window_taper:
                image = image * self._get_taper_window(image.shape)

            img_dip = self._dip.Image(image)
            fft_dip = self._dip.FourierTransform(img_dip)
            magnitude = self._dip.Abs(fft_dip)
            magnitude = np.array(magnitude)
            # fft_data = dip.FourierTransform(image)
            
            # # 2. Shift zero-frequency component to the center
            # fft_shifted = np.fft.fftshift(fft_data)
            
            # # 3. Get Magnitude
            # magnitude = np.abs(fft_shifted)
            
            # 4. Apply Log Scaling for visualization (standard practice)
            if self.log_scale:
                # log1p(x) is log(1+x), avoids log(0) and handles small values better
                self.fft_display = np.log(magnitude)
            else:
                self.fft_display = magnitude

        except Exception as e:
            logging.error(f"FFT Calculation failed: {e}")

        logging.debug(f"FFT processing time: {time.time() - run_start:.4f}s")
    
    def end(self, core, **kwargs):
        logging.info('ENDING REAL-TIME FFT ANALYSIS')
        return
    
    def visualise_init(self): 
        logging.info('INITIALISING VISUALISATION FOR FFT')
        layerName = 'FFT Magnitude'
        layerType = 'image' # Using image layer to show the 2D spectrum
        self.firstLayerInit = True
        return layerName, layerType
    
    def visualise(self, image, metadata, core, napariLayer, **kwargs):
        """
        Updates the Napari image layer with the calculated FFT data.
        """
        vis_time = time.time()
        
        # Update the image data in the Napari layer
        napariLayer.data = self.fft_display
        
        if self.firstLayerInit:
            # Set a colormap that makes frequency peaks easier to see
            napariLayer.colormap = 'magma'
            # Auto-contrast the first frame
            napariLayer.contrast_limits = [np.min(self.fft_display), np.max(self.fft_display)]
            self.firstLayerInit = False
            
        logging.debug(f"Visualising FFT: {time.time() - vis_time:.4f}s")