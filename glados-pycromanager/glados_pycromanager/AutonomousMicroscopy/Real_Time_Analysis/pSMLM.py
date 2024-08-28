
def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
else:
    from MainScripts import FunctionHandling
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
            "help_string": "Real-time localization via pSMLM (phasor-based localization microscopy).",
            "display_name": "pSMLM localization",
            "run_delay": 0,
            "visualise_delay": 10,
            "input":[
            ],
            "output":[
            ],
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------


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

# From microEye:
class Filter:
    # Class attributes (shared among all instances)
    class_attribute = 0

    def __init__(self, param1=5, param2=5):
        # Constructor (initialize object-specific attributes)
        self.param1 = param1
        self.param2 = param2
        self.filterName = None
        self._radial_coordinates = None

    def instance_method(self):
        # Instance method (operates on an instance)
        return self.param1 + self.param2

    @classmethod
    def class_method(cls):
        # Class method (operates on the class)
        return cls.class_attribute
    
    def radial_coordinate(self, shape):
        '''Generates a 2D array with radial coordinates
        with according to the first two axis of the
        supplied shape tuple

        Returns
        -------
        R, Rsq
            Radius 2d matrix (R) and radius squared matrix (Rsq)
        '''
        y_len = np.arange(-shape[0]//2, shape[0]//2)
        x_len = np.arange(-shape[1]//2, shape[1]//2)

        X, Y = np.meshgrid(x_len, y_len)

        Rsq = (X**2 + Y**2)

        self._radial_coordinates = (np.sqrt(Rsq), Rsq)

        return self._radial_coordinates
    
    def butterworth_filter(self, shape = (128,128), center = 10, width = 20):
        '''Generates a Gaussian bandpass filter of shape

            Params
            -------
            shape
                the shape of filter matrix
            center
                the center frequency
            width
                the filter bandwidth

            Returns
            -------
            filter (np.ndarray)
                the filter in fourier space
        '''
        if self._radial_coordinates is None:
            R, Rsq = self.radial_coordinate(shape)
        elif self._radial_coordinates[0].shape != shape[:2]:
            R, Rsq = self.radial_coordinate(shape)
        else:
            R, Rsq = self._radial_coordinates

        with np.errstate(divide='ignore', invalid='ignore'):
            filter = 1 - (1 / (1+((R * width)/(Rsq - center**2))**10))
            filter[filter == np.inf] = 0

        a, b = np.unravel_index(R.argmin(), R.shape)

        filter[a, b] = 1
        self.filterName = 'butterWorth'
        self.filter = filter
        return filter
    
    def gauss_bandpass_filter(self, shape = (128,128), center = 10, width = 20):
        '''Generates a Gaussian bandpass filter of shape

            Params
            -------
            shape
                the shape of filter matrix
            center
                the center frequency
            width
                the filter bandwidth

            Returns
            -------
            filter (np.ndarray)
                the filter in fourier space
        '''
        if self._radial_coordinates is None:
            R, Rsq = self.radial_coordinate(shape)
        elif self._radial_coordinates[0].shape != shape[:2]:
            R, Rsq = self.radial_coordinate(shape)
        else:
            R, Rsq = self._radial_coordinates

        with np.errstate(divide='ignore', invalid='ignore'):
            filter = np.exp(-((Rsq - center**2)/(R * width))**2)
            filter[filter == np.inf] = 0

        a, b = np.unravel_index(R.argmin(), R.shape)

        filter[a, b] = 1
        self.filterName = 'GaussFilter'
        self.filter = filter
        return filter
    
    def DoGFilter(self, sigma1 = 2.5, sigma2 = 5):
        self.filterName = 'DoGFilter'
        self.filter = [sigma1,sigma2]
        return self.filter
        
    def applyFilter(self, image: np.ndarray):
        '''Applies an FFT bandpass filter to the 2D image.

            Params
            -------
            image (np.ndarray)
                the image to be filtered.
        '''
        if self.filterName != 'DoGFilter':
            rows, cols = image.shape
            nrows = cv2.getOptimalDFTSize(rows)
            ncols = cv2.getOptimalDFTSize(cols)
            nimg = np.zeros((nrows, ncols))
            nimg[:rows, :cols] = image

            ft = fftshift(cv2.dft(np.float64(nimg), flags=cv2.DFT_COMPLEX_OUTPUT))

            img = np.zeros(nimg.shape, dtype=np.uint8)
            ft[:, :, 0] *= self.filter
            ft[:, :, 1] *= self.filter
            idft = cv2.idft(ifftshift(ft))
            idft = cv2.magnitude(idft[:, :, 0], idft[:, :, 1])
            cv2.normalize(
                idft, img, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

            # exex = time.msecsTo(QDateTime.currentDateTime())
            return img[:rows, :cols]
        else:
            #We filter the image twice, with both sigma
            #The images are converted to float value to ensure negative numbers during subtraction
            Gauss1FilteredImage = gaussian_filter(im, sigma=self.filter[0]).astype(float);
            Gauss2FilteredImage = gaussian_filter(im, sigma=self.filter[1]).astype(float);
            #The difference of Gaussian is calculaed by subtracting the two images
            return Gauss1FilteredImage-Gauss2FilteredImage

class pSMLM():
    def __init__(self,core,**kwargs):
        print(core)
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore
        self.pxsize = core.get_pixel_size_um()*1000
        
        self.file = open("SMLM_locs.csv",'w')
        self.file.write("\"frame\",\"x [nm]\",\"y [nm]\"\n")
        
        self.SMLMlocs = []

        print('in RT_counter at time '+str(time.time()))
        return None

    def run(self,image,metadata,core,**kwargs):
        locPeaks = getLocalPeaks_rawIm(image, int(kwargs['ROIradius']),stdmult=int(kwargs['stdmult']))
        SMLMlocs_2 = getLocalizationList(locPeaks, image, 4)
        frameNumber = 0
        if 'ImageNumber' in metadata:
            frameNumber = float(metadata['ImageNumber'])
        else:
            frameNumber = float(metadata['Axes']['time'])
    
        
        for i in range(0,len(SMLMlocs_2)):
            self.file.write(str(int(frameNumber+1))+","+str(SMLMlocs_2[i,0]*self.pxsize)+","+str(SMLMlocs_2[i,1]*self.pxsize)+'\n')
            
        print(f"Nr locs: {len(SMLMlocs_2)} ")
        self.SMLMlocs=SMLMlocs_2
    def end(self,core,**kwargs):
        time.sleep(0.1)
        self.file.close()
        print('end of pSMLM')
        return
    
    
    def visualise_init(self): 
        layerName = 'pSMLM'
        layerType = 'points' #layerType has to be from image|labels|points|shapes|surface|tracks|vectors
        return layerName,layerType
    
    def visualise(self,image,metadata,core,napariLayer,**kwargs):
        napariLayer.data = self.SMLMlocs[:, [1, 0]].copy()
        time.sleep(0.05)
        napariLayer.symbol = 'disc'
        napariLayer.size = 5
        napariLayer.edge_color='red'
        napariLayer.face_color = [0,0,0,0]
        napariLayer.selected_data = []
        # napariLayer.data = np.append(napariLayer.data,self.SMLMlocs[:, [1, 0]].copy(),axis=0)

