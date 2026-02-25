import numpy as np
import inspect
import glados_pycromanager.GUI.utils as utils
import logging
import time
import sys, os

# Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling

def __function_metadata__():
    return { 
        "RealTimeFFT": {
            "required_kwargs": [
            ],
            "optional_kwargs": [
                {"name": "LogScale", "description": "Apply log scaling to FFT", "default": True, "type": bool}
            ],
            "help_string": "Calculates and displays the 2D FFT magnitude spectrum in real-time.",
            "display_name": "Real-Time FFT",
            "run_delay": 0,
            "visualise_delay": 200,
            "visualisation_type": "image", # Changed to 'image' for FFT display
            "input":[],
            "output":[],
        }
    }

#-------------------------------------------------------------------------------------------------------------------------------
# Callable functions
#-------------------------------------------------------------------------------------------------------------------------------

class RealTimeFFT():
    def __init__(self, core, **kwargs):
        logging.info('INITIALISING REAL-TIME FFT ANALYSIS')
        
        # Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(), class_name, kwargs) #type:ignore
        
        self.fft_display = np.zeros((512, 512)) # Placeholder
        self.log_scale = kwargs.get('LogScale', True)
        
        logging.info('FFT Initialised')
        return None

    def run(self, image, metadata, shared_data, core, **kwargs):
        """
        Performs the 2D FFT on the incoming image buffer.
        """
        run_start = time.time()
        
        try:
            # 1. Compute 2D FFT
            fft_data = np.fft.fft2(image)
            
            # 2. Shift zero-frequency component to the center
            fft_shifted = np.fft.fftshift(fft_data)
            
            # 3. Get Magnitude
            magnitude = np.abs(fft_shifted)
            
            # 4. Apply Log Scaling for visualization (standard practice)
            if self.log_scale:
                # log1p(x) is log(1+x), avoids log(0) and handles small values better
                self.fft_display = np.log1p(magnitude)
            else:
                self.fft_display = magnitude

        except Exception as e:
            logging.error(f"FFT Calculation failed: {e}")

        logging.info(f"FFT processing time: {time.time() - run_start:.4f}s")
    
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
            
        logging.info(f"Visualising FFT: {time.time() - vis_time:.4f}s")