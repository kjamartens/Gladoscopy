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
from scipy import signal
from scipy.ndimage import gaussian_filter
from skimage.feature.peak import peak_local_max

import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
from glados_pycromanager.autonomous.registry import register


# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "pSMLM": {
            "required_kwargs": [
                {"name": "ROIradius", "description": "ROIradius", "default": 3, "type": int}
            ],
            "optional_kwargs": [
                {"name": "stdmult", "description": "stdmult", "default": 2, "type": int}
            ],
            "help_string": "phasor-based SMLM.",
            "display_name": "pSMLM version",
            "run_delay": 20,
            "visualise_delay": 100,
            "visualisation_type": "points", #'image', 'points', 'value', or 'shapes'
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
@register("pSMLM.pSMLM")
class pSMLM:
    def __init__(self,core,**kwargs):
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        self.SMLMlocs = []
        self.fullSMLMlocs = []
        self.dummyValue = 0
        self.metadatav = []
        self.currentFrame = 0
        try:
            px = core.get_pixel_size_um()
            self.pxsizeum = px if px != 0 else 1
        except Exception:
            self.pxsizeum = 1
        return None

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
        import pandas as pd
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
        if len(self.fullSMLMlocs) == 0:
            self.fullSMLMlocs = pd.DataFrame(new_locs_with_mdaVals, columns=column_headers)
        else:
            new_df = pd.DataFrame(new_locs_with_mdaVals, columns=column_headers)
            self.fullSMLMlocs = pd.concat([self.fullSMLMlocs, new_df], ignore_index=True)
        
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
        layerType = 'points' #layerType has to be from image|labels|points|shapes|surface|tracks|vectors
        self.firstLayerInit = True
        return layerName,layerType
    
    def visualise(self,image,metadata,core,napariLayer,**kwargs):
        # create features for each point
        # features = {
        #     'outputval': self.currentFrame
        # }
        # textv = {
        #     'string': 'f: {outputval:.0f}',
        #     'size': 10,
        #     'color': 'red',
        #     'translation': np.array([0, 0]),
        #     'anchor': 'upper_left',
        # }
        try:
            logging.debug("pSMLM visualise: called, SMLMlocs len=%d, napariLayer type=%s",
                         len(self.SMLMlocs), type(napariLayer).__name__)
            if len(self.SMLMlocs) > 1:
                coords = self.SMLMlocs[:, [1, 0]].copy()  # (N,2): row, col for napari
                ndim = getattr(napariLayer, 'ndim', 2)
                if ndim > 2:
                    try:
                        import napari
                        _viewer = napari.current_viewer()
                        current_step = _viewer.dims.current_step
                        extra = np.array(current_step[:ndim - 2], dtype=float)
                        logging.debug("pSMLM visualise: viewer.dims.current_step=%s, using extra dims=%s",
                                     current_step, extra)
                    except Exception as e:
                        extra = np.zeros(ndim - 2)
                        logging.debug("pSMLM visualise: could not get current_step (%s), using zeros", e)
                    extra_cols = np.tile(extra, (coords.shape[0], 1))
                    coords = np.hstack([extra_cols, coords])
                logging.debug("pSMLM visualise: assigning coords shape=%s, row=[%.1f,%.1f] col=[%.1f,%.1f], ndim=%d",
                             coords.shape, coords[:,-2].min(), coords[:,-2].max(),
                             coords[:,-1].min(), coords[:,-1].max(), ndim)
                napariLayer.data = coords
                logging.debug("pSMLM visualise: data assigned, layer.data.shape=%s, first 3:\n%s",
                             napariLayer.data.shape, napariLayer.data[:3])
            napariLayer.selected_data = []
            try:
                napariLayer.symbol = 'disc'
            except Exception as e:
                logging.debug("pSMLM: symbol failed: %s", e)
            try:
                napariLayer.size = 8
            except Exception as e:
                logging.debug("pSMLM: size failed: %s", e)
            try:
                napariLayer.face_color = [0, 0, 0, 0]  # transparent fill
            except Exception as e:
                logging.debug("pSMLM: face_color failed: %s", e)
            for _attr in ('border_color', 'edge_color'):
                try:
                    setattr(napariLayer, _attr, 'red')
                    break
                except Exception as e:
                    logging.debug("pSMLM: %s failed: %s", _attr, e)
            for _attr in ('border_width', 'edge_width'):
                try:
                    setattr(napariLayer, _attr, 0.05)
                    break
                except Exception as e:
                    logging.debug("pSMLM: %s failed: %s", _attr, e)
        except Exception as exc:
            logging.debug('Issue with pSMLM layer update: %s', exc)
        return napariLayer