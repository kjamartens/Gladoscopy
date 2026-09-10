import os
import sys

#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import inspect
import logging

# from shapely import Polygon, affinity
# from shapely import Polygon, affinity
import math
import time

import dask.array as da
import numpy as np
import pandas as pd
from scipy import signal
from scipy.ndimage import gaussian_filter, zoom
from skimage.feature.peak import peak_local_max

import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
from glados_pycromanager.autonomous.registry import register


# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "pSMLM_image": {
            "required_kwargs": [
                {"name": "ROIradius", "description": "ROIradius", "default": 3, "type": int}
            ],
            "optional_kwargs": [
                {"name": "stdmult", "description": "stdmult", "default": 2, "type": int},
                {
                    "name": "hist_width",
                    "description": "Histogram Kernel Width (upsampled px)",
                    "default": 3,
                    "type": int,
                },
            ],
            "help_string": "phasor-based SMLM.",
            "display_name": "pSMLM image",
            "run_delay": 1,
            "visualise_delay": 1000,
            "visualisation_type": "image", #'image', 'points', 'value', or 'shapes'
            "input":[
            ],
            "output":[
            ],
        }
    }



def DoGFilter(im,g1,g2):
    #The sigma of the Gaussian filters is specificied for the Difference-of-Gaussian filter
    GaussFilterSigma1 = g1; #Sigma of the first Gaussian Filter (in pixels)
    GaussFilterSigma2 = g2; #Sigma of the second Gaussian Filter (in pixels)

    #We filter the image twice, with both sigma
    #The images are converted to float value to ensure negative numbers during subtraction
    Gauss1FilteredImage = gaussian_filter(im, sigma=GaussFilterSigma1).astype(float);
    Gauss2FilteredImage = gaussian_filter(im, sigma=GaussFilterSigma2).astype(float);
    #The difference of Gaussian is calculaed by subtracting the two images
    return Gauss1FilteredImage-Gauss2FilteredImage

def getLocalPeaks(DoGFilteredImage, ROIradius, stdmult = 2):
    MinValueLocalMax = np.std(DoGFilteredImage)*stdmult
    localpeaks = peak_local_max(DoGFilteredImage,min_distance=ROIradius,threshold_abs = MinValueLocalMax,exclude_border=ROIradius*2,num_peaks=500)
    return localpeaks

def getLocalPeaks_rawIm(im, ROIradius, stdmult = 2):
    MinValueLocalMax = np.std(im)*stdmult
    medianVal = np.median(im)
    localpeaks = peak_local_max(im,min_distance=ROIradius,threshold_abs = medianVal+MinValueLocalMax,exclude_border=ROIradius*2,num_peaks=500)
    return localpeaks

def getLocalizationList(localpeaks, im, ROIradius):
    localization_list = np.zeros((len(localpeaks),2))
    for l in range(0, len(localpeaks)):
        #Extract the ROI
        ROI = im[localpeaks[l,0]-ROIradius:localpeaks[l,0]+ROIradius+1,
                            localpeaks[l,1]-ROIradius:localpeaks[l,1]+ROIradius+1]
        #Get locations from phasor function
        t=phasor_fitting(ROI,ROIradius,[localpeaks[l,0],localpeaks[l,1]] )
        localization_list[l,:] = t
    return localization_list

#Function for phasor fitting
def phasor_fitting(ROI,ROIradius,localpeak):
    #Perform 2D Fourier transform over the complete ROI
    ROI_F = np.fft.fft2(ROI)

    #We have to calculate the phase angle of array entries [0,1] and [1,0] for
    #the sub-pixel x and y values, respectively
    #This phase angle can be calculated as follows:
    xangle = np.arctan(ROI_F[0,1].imag/ROI_F[0,1].real) - np.pi
    #Correct in case it's positive
    if xangle > 0:
        xangle -= 2*np.pi
    #Calculate position based on the ROI radius
    PositionX = abs(xangle)/(2*np.pi/(ROIradius*2+1));

    #Do the same for the Y angle and position
    yangle = np.arctan(ROI_F[1,0].imag/ROI_F[1,0].real) - np.pi
    if yangle > 0:
        yangle -= 2*np.pi
    PositionY = abs(yangle)/(2*np.pi/(ROIradius*2+1));

    #Get the final localization based on the ROI position
    LocalizationX = localpeak[1]-ROIradius+PositionX
    LocalizationY = localpeak[0]-ROIradius+PositionY
    return [LocalizationX, LocalizationY]


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------

def generate_gaussian_kernel(width, sigma=1.0):
    """Generates a normalized 2D Gaussian kernel for rendering localizations."""
    radius = width // 2
    y, x = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    kernel = np.exp(-(x**2 + y**2) / (2 * sigma**2))
    return kernel.astype(np.float32)

@register("pSMLM_image.pSMLM_image")
class pSMLM_image:
    def __init__(self,core,**kwargs):
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        self.SMLMlocs = []
        # Per-frame localization DataFrames, concatenated lazily via the fullSMLMlocs
        # property instead of every frame - pd.concat on every run() copies the whole
        # accumulated history each time, making a long session O(n^2) in frame count.
        self._smlm_frames = []
        self.dummyValue = 0
        self.metadatav = []
        self.currentFrame = 0
        # Additive SR canvas tracking
        self.sr_canvas = None
        self._sr_canvas_shape = None
        self._last_processed_loc_idx = 0
        
        
        # Pre-compute initial kernel in __init__
        self.hist_width = int(kwargs.get("hist_width", 3))
        if self.hist_width % 2 == 0:
            self.hist_width += 1
        self.radius = self.hist_width // 2
        self.kernel = generate_gaussian_kernel(
            self.hist_width, sigma=max(1.0, self.radius / 2.0)
        )
        
        try:
            px = core.get_pixel_size_um()
            self.pxsizeum = px if px != 0 else 1
        except Exception:
            self.pxsizeum = 1
        return None

    @property
    def fullSMLMlocs(self):
        if not self._smlm_frames:
            return pd.DataFrame()
        return pd.concat(self._smlm_frames, ignore_index=True)

    def run(self,image,metadata,shared_data,core,**kwargs):
        # logging.info(f'Starting Updating pSMLM running at time: {time.time()}')
        self.dummyValue = np.random.randint(0, 101)
        locPeaks = getLocalPeaks_rawIm(image, int(kwargs['ROIradius']),stdmult=int(kwargs['stdmult']))
        logging.debug("pSMLM: image min/max/mean=%.1f/%.1f/%.1f, peaks found=%d (ROIradius=%s, stdmult=%s)",
                     image.min(), image.max(), image.mean(), len(locPeaks),
                     kwargs['ROIradius'], kwargs['stdmult'])
        self.SMLMlocs = getLocalizationList(locPeaks, image, 4)*self.pxsizeum
        logging.debug("pSMLM: localizations after phasor fit=%d", len(self.SMLMlocs))
        if len(self.SMLMlocs) > 0:
            logging.debug("pSMLM: loc x range=[%.1f, %.1f], y range=[%.1f, %.1f]",
                         self.SMLMlocs[:, 0].min(), self.SMLMlocs[:, 0].max(),
                         self.SMLMlocs[:, 1].min(), self.SMLMlocs[:, 1].max())
            logging.debug("pSMLM: first 3 locs: %s", self.SMLMlocs[:3])
        
        #Append to full list with frame info
        _dims = utils.getDimensionsFromAcqData(shared_data._mdaModeParams)
        if _dims is not None:
            self.dimensionOrder, self.n_entries_in_dims, self.uniqueEntriesAllDims = _dims
            column_headers = np.hstack([list(self.uniqueEntriesAllDims.keys()), ['x_pos', 'y_pos']])
            mda_values = []
            for v in list(self.uniqueEntriesAllDims.keys()):
                mda_values = np.hstack((mda_values, metadata.get('Axes', {}).get(v, 0)))
            mda_val_column = np.full((self.SMLMlocs.shape[0], 1), mda_values)
            new_locs_with_mdaVals = np.hstack((mda_val_column, self.SMLMlocs))
        else:
            column_headers = ['x_pos', 'y_pos']
            new_locs_with_mdaVals = self.SMLMlocs
        # Stash this frame's localizations; fullSMLMlocs concatenates them lazily on read.
        self._smlm_frames.append(pd.DataFrame(new_locs_with_mdaVals, columns=column_headers))
        
        self.lastImage = image
        self.lastMetadata = metadata
        # logging.info(f'Finishing Updating pSMLM running at time: {time.time()}')
        # logging.info(f"Nr locs: {len(self.SMLMlocs)} ")
        
        # self.dimensionOrder, self.n_entries_in_dims, self.uniqueEntriesAllDims = utils.getDimensionsFromAcqData(shared_data._mdaModeParams)
        # mda_values = []
        # for v in list(self.uniqueEntriesAllDims.keys()):
        #     mda_values = np.hstack((mda_values,metadata['Axes'][v]))
            
        # self.currentFrame = metadata['Axes'][v]
        
        return f'pSMLM2 result - frame'
    
    def end(self,core,**kwargs):
        self.fullSMLMlocs
        # all_possible_z = set(range(100))  # 0 to 99
        # existing_z = set(self.fullSMLMlocs['z'].unique())
        # missing_z = all_possible_z - existing_z

        # print("Missing z values:")
        # print(sorted(missing_z))
        return
    
    def visualise_init(self): 
        layerName = 'pSMLM'
        layerType = 'image' #layerType has to be from image|labels|points|shapes|surface|tracks|vectors
        
        self.firstLayerInit = True
        return layerName,layerType

    def visualise(self, image, metadata, core, napariLayer, **kwargs):
        """Additive SR visualization using pre-computed kernel from init."""
        try:
            scale_factor = 10  # 10x upsampling factor

            # Check if user updated hist_width via GUI kwargs dynamically
            current_width = int(kwargs.get("hist_width", self.hist_width))
            if current_width % 2 == 0:
                current_width += 1

            # Recompute kernel ONLY if hist_width was changed at runtime
            if current_width != self.hist_width:
                self.hist_width = current_width
                self.radius = self.hist_width // 2
                self.kernel = generate_gaussian_kernel(
                    self.hist_width, sigma=max(1.0, self.radius / 2.0)
                )

            # 1. Determine base image dimensions
            if hasattr(image, "shape") and image.ndim == 2:
                base_shape = image.shape
            elif hasattr(napariLayer, "data") and hasattr(
                napariLayer.data, "shape"
            ):
                base_shape = napariLayer.data.shape[:2]
            else:
                base_shape = (512, 512)

            target_sr_shape = (
                base_shape[0] * scale_factor,
                base_shape[1] * scale_factor,
            )

            # 2. Initialize persistent empty SR canvas
            if (
                self.sr_canvas is None
                or self._sr_canvas_shape != target_sr_shape
            ):
                self.sr_canvas = np.zeros(target_sr_shape, dtype=np.float32)
                self._sr_canvas_shape = target_sr_shape
                self._last_processed_loc_idx = 0

                # Set Napari layer scale 1/10
                try:
                    scale_tuple = (1.0 / scale_factor, 1.0 / scale_factor)
                    if napariLayer.ndim > 2:
                        scale_tuple = (1.0,) * (
                            napariLayer.ndim - 2
                        ) + scale_tuple
                    napariLayer.scale = scale_tuple
                except Exception as e:
                    logging.debug("pSMLM: failed to set layer scale: %s", e)

            # 3. Retrieve localizations
            df_locs = self.fullSMLMlocs

            if not df_locs.empty and "x_pos" in df_locs and "y_pos" in df_locs:
                total_locs = len(df_locs)

                if total_locs > self._last_processed_loc_idx:
                    new_df = df_locs.iloc[self._last_processed_loc_idx :]

                    x_coords_px = new_df["x_pos"].to_numpy() / self.pxsizeum
                    y_coords_px = new_df["y_pos"].to_numpy() / self.pxsizeum

                    scaled_x = np.round(x_coords_px * scale_factor).astype(int)
                    scaled_y = np.round(y_coords_px * scale_factor).astype(int)

                    h_up, w_up = self.sr_canvas.shape
                    rad = self.radius

                    # Filter valid bounds for the kernel radius
                    valid = (
                        (scaled_x >= rad)
                        & (scaled_x < w_up - rad)
                        & (scaled_y >= rad)
                        & (scaled_y < h_up - rad)
                    )

                    scaled_x = scaled_x[valid]
                    scaled_y = scaled_y[valid]

                    # 4. Stamp pre-computed kernel
                    for x, y in zip(scaled_x, scaled_y):
                        self.sr_canvas[
                            y - rad : y + rad + 1, x - rad : x + rad + 1
                        ] += self.kernel

                    self._last_processed_loc_idx = total_locs

            napariLayer.data = self.sr_canvas

        except Exception as exc:
            logging.debug("Issue with pSMLM SR histogram update: %s", exc)

        return napariLayer