#Goal: real-time localization of SMLM data, testing different methods
from scipy.ndimage import gaussian_filter
from skimage.feature.peak import peak_local_max
import numpy as np
from PIL import Image
import time
import matplotlib.pyplot as plt

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

#Load example image
im = np.double(Image.open('Testing/TestSingleFullFrame512px.tiff'))

print('Im Loaded')

nrit = 100

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