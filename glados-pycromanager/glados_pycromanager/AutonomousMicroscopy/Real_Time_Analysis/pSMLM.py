
def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
    import glados_pycromanager.GUI.utils as utils
else:
    from MainScripts import FunctionHandling
    import utils
from shapely import Polygon, affinity
import math
import logging
import numpy as np
import inspect
import dask.array as da
import time
from scipy import signal
from shapely import Polygon, affinity
import math
import numpy as np
import inspect
import dask.array as da
import time
from scipy.ndimage import gaussian_filter
from skimage.feature.peak import peak_local_max

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
class pSMLM():
    def __init__(self,core,**kwargs):
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        self.SMLMlocs = []
        self.fullSMLMlocs = []
        self.dummyValue = 0
        self.metadatav = []
        self.currentFrame = 0
        self.pxsizeum = core.get_pixel_size_um()
        return None

    def run(self,image,metadata,shared_data,core,**kwargs):
        logging.info(f'Starting Updating pSMLM running at time: {time.time()}')
        self.dummyValue = np.random.randint(0, 101)
        locPeaks = getLocalPeaks_rawIm(image, int(kwargs['ROIradius']),stdmult=int(kwargs['stdmult']))
        self.SMLMlocs = getLocalizationList(locPeaks, image, 4)*self.pxsizeum
        
        #Append to full list with frame info
        self.dimensionOrder, self.n_entries_in_dims, self.uniqueEntriesAllDims = utils.getDimensionsFromAcqData(shared_data._mdaModeParams)
        #Get the headers
        column_headers = np.hstack([list(self.uniqueEntriesAllDims.keys()), ['x_pos', 'y_pos']])
        mda_values = []
        for v in list(self.uniqueEntriesAllDims.keys()):
            mda_values = np.hstack((mda_values,metadata['Axes'][v]))
        #Get the columns for the MDA values and append to the current localizations
        mda_val_column = np.full((self.SMLMlocs.shape[0], 1), mda_values)
        new_locs_with_mdaVals = np.hstack((mda_val_column, self.SMLMlocs))
        
        import pandas as pd
        if len(self.fullSMLMlocs) == 0:
            self.fullSMLMlocs = pd.DataFrame(new_locs_with_mdaVals, columns=column_headers)
        else:
            new_df = pd.DataFrame(new_locs_with_mdaVals, columns=column_headers)
            self.fullSMLMlocs = pd.concat([self.fullSMLMlocs, new_df], ignore_index=True)
        
        self.lastImage = image
        self.lastMetadata = metadata
        logging.info(f'Finishing Updating pSMLM running at time: {time.time()}')
        logging.info(f"Nr locs: {len(self.SMLMlocs)} ")
        
        self.dimensionOrder, self.n_entries_in_dims, self.uniqueEntriesAllDims = utils.getDimensionsFromAcqData(shared_data._mdaModeParams)
        mda_values = []
        for v in list(self.uniqueEntriesAllDims.keys()):
            mda_values = np.hstack((mda_values,metadata['Axes'][v]))
            
        self.currentFrame = metadata['Axes'][v]
        
        return f'pSMLM2 result - frame {self.currentFrame}'
    
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
            logging.info(f'Starting Updating pSMLM layer at time: {time.time()}')
            logging.info(f"SMLM locs: {self.SMLMlocs}")
                # napariLayer.size = 0
            # napariLayer.data = np.array([[100,100]])
            # napariLayer.text = text
            if len(self.SMLMlocs) > 1:
                logging.info('Actually SMLM loc vissing')
                napariLayer.data = self.SMLMlocs[:, [1, 0]].copy() #Needs to be transposed
                time.sleep(0.005)
            # napariLayer.features = features
            # napariLayer.text = textv
            napariLayer.selected_data = []
            napariLayer.symbol = 'disc'
            napariLayer.size = 0.5
            napariLayer.edge_color='red'
            napariLayer.face_color = [0,0,0,0]
        except:
            logging.info(f"Issue with pSMLM layer update")
        return napariLayer