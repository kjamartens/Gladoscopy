#Goal: real-time localization of SMLM data, testing different methods
from scipy.ndimage import gaussian_filter
from skimage.feature.peak import peak_local_max
import numpy as np
from PIL import Image
import time
import matplotlib.pyplot as plt
import math

import cv2
import numpy as np
from scipy import signal
from scipy.fftpack import fft2, fftshift, ifft2, ifftshift

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


#Load example image
im = np.double(Image.open('Testing/TestSingleFullFrame512px.tiff'))




newFilter = Filter()
# vv = newFilter.butterworth_filter(shape=(512,512),center = 60,width=60)
# vv = newFilter.gauss_bandpass_filter(shape=(512,512),center = 20,width=100)
vv = newFilter.DoGFilter(sigma1 = 2.5, sigma2 = 4.5)


start_time = time.perf_counter()
for _ in range(50):
    newim = newFilter.applyFilter(im)
end_time = time.perf_counter()
elapsed_time_ms_1 = 1000*(end_time - start_time)/50
print(elapsed_time_ms_1)

# Set up the blob detector parameters
params = cv2.SimpleBlobDetector_Params()
params.filterByArea = True
params.minArea = 10
params.maxArea = 60
params.filterByColor = False
params.minDistBetweenBlobs = 3
params.filterByCircularity = False
params.filterByConvexity = False
params.filterByInertia = False
# Create a blob detector with the specified parameters
detector = cv2.SimpleBlobDetector_create(params)

newim -= np.min(newim) - 50

start_time = time.perf_counter()
for _ in range(10):
    # Detect blobs in the grayscale image
    keypoints = detector.detect(newim.astype(np.uint8))
    # Extract (x, y) positions of the keypoints
    keypoint_positions = [keypoint.pt for keypoint in keypoints]
# Print the positions
for (x, y) in keypoint_positions:
    print(f"KeyPoint at (x={x}, y={y})")
end_time = time.perf_counter()
elapsed_time_ms_1 = 1000*(end_time - start_time)/10
print(elapsed_time_ms_1)


# Draw detected blobs on the original image
output_image = cv2.drawKeypoints(newim.astype(np.uint8), keypoints, None, (0, 0, 255),
                                  cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
cv2.imshow("Blob Detection", output_image)
cv2.waitKey(0)
cv2.destroyAllWindows()


# # Create a figure with two subplots
# fig, axes = plt.subplots(1, 3)

# # Display the first image on the left subplot
# axes[0].imshow(im, cmap='gray')
# axes[0].set_title('Image 1')

# # Display the second image on the right subplot
# axes[1].imshow(newim, cmap='gray')
# axes[1].set_title('Image 2')

# # Adjust the layout and spacing between subplots
# plt.tight_layout()

# # Show the figure with the subplots and images
# plt.show()



nrit = 10

start_time_full = time.perf_counter()
start_time = time.perf_counter()
for _ in range(0,nrit):
    imout = DoGFilter(im,2.5,4) #~15ms
end_time = time.perf_counter()
elapsed_time_ms_1 = 1000*(end_time - start_time)/nrit

start_time = time.perf_counter()
for _ in range(0,nrit):
    localpeaks = getLocalPeaks(imout,3) #~10ms
end_time = time.perf_counter()
elapsed_time_ms_2 = 1000*(end_time - start_time)/nrit

start_time = time.perf_counter()
for _ in range(0,nrit):
    SMLMlocs = getLocalizationList(localpeaks, im, 4) #~3ms
end_time = time.perf_counter()
elapsed_time_ms_3 = 1000*(end_time - start_time)/nrit

start_time = time.perf_counter()
for _ in range(0,nrit):
    localpeaks_2 = getLocalPeaks_rawIm(im,3,5)
end_time = time.perf_counter()
elapsed_time_ms_4 = 1000*(end_time - start_time)/nrit
elapsed_time_tot = (end_time - start_time_full)

for _ in range(0,nrit):
    SMLMlocs_2 = getLocalizationList(localpeaks_2, im, 4) #~3ms


print(f"Functions with {nrit:.0f} its took total {elapsed_time_tot:.8f} s to execute.")
print(f"Function 1 took average {elapsed_time_ms_1:.8f} ms to execute.")
print(f"Function 2 took average {elapsed_time_ms_2:.8f} ms to execute.")
print(f"Function 3 took average {elapsed_time_ms_3:.8f} ms to execute.")
print(f"Function 4 took average {elapsed_time_ms_4:.8f} ms to execute.")


#Show the found local maxima on top of the original image
plt.imshow(im,cmap='gray',vmin = 0, vmax = 1500)
plt.scatter(SMLMlocs[:,0], SMLMlocs[:,1], facecolors='none', edgecolors='r', s=80)
plt.scatter(SMLMlocs_2[:,0], SMLMlocs_2[:,1], facecolors='none', edgecolors='b', s=110)
plt.show()
z=0