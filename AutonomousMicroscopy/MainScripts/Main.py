# from csbdeep.io import save_tiff_imagej_compatible
# from stardist import _draw_polygons, export_imagej_rois
import sys, os
# Add the folder 2 folders up to the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tifffile
# from shapely import Polygon, affinity
# import numpy as np
# import math
# from stardist.models import StarDist2D
import matplotlib.pyplot as plt
from matplotlib import colormaps

#Import all scripts in the custom script folders
from CellSegmentScripts import *
from CellScoringScripts import *
from ROICalcScripts import *
from ScoringMetrics import *
#Obtain the helperfunctions
import HelperFunctions

#Created Conda environment (Python 3.8.16)
#Required PIPs:
# pip install --upgrade setuptools
# pip install csbdeep tensorflow matplotlib tifffile numpy shapely pyqt5 pyqtgraph pycromanager stardist pyqt5 pyqtgraph

# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# Main script
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------

testImageLoc = "./AutonomousMicroscopy/ExampleData/BF_test_avg.tiff"

# Open the TIFF file
with tifffile.TiffFile(testImageLoc) as tiff:
    # Read the image data
    ImageData = tiff.asarray()

#Non-preloaded stardistsegmentation
coords = eval(HelperFunctions.createFunctionWithKwargs("StarDist.StarDistSegment",image_data="ImageData",modelStorageLoc="\"./AutonomousMicroscopy/ExampleData/StarDistModel\"",prob_thresh="0.35",nms_thresh="0.2"))

#Three examples
cellCrowdedness = eval(HelperFunctions.createFunctionWithKwargs("SimpleCellOperants.nrneighbours_basedonCellWidth",outline_coords="coords",multiple_cellWidth_lookup="1"))
cellCrowdedness_gauss=eval(HelperFunctions.createFunctionWithKwargs("DefaultScoringMetrics.gaussScore",value="cellCrowdedness",meanVal="3",sigmaVal="2"))

cellArea = eval(HelperFunctions.createFunctionWithKwargs("SimpleCellOperants.cellArea",outline_coords="coords"))
cellArea_bounds=eval(HelperFunctions.createFunctionWithKwargs("DefaultScoringMetrics.lowerUpperBound",value="cellArea",lower_bound="300",upper_bound="500"))

cellAssym = eval(HelperFunctions.createFunctionWithKwargs("SimpleCellOperants.lengthWidthRatio",outline_coords="coords"))
cellAssym_relativeToMax = eval(HelperFunctions.createFunctionWithKwargs("DefaultScoringMetrics.relativeToMaxScore",value="cellAssym"))

 
# fn = HelperFunctions.functionNamesFromDir("ScoringMetrics")
# print(fn)


#Get cell image
cellIm = ImageData
# #start creating celloverlayimage
# cellOverlayIm = np.zeros(l.shape)
# for i in range(1,np.amax(l)):
#     cellOverlayIm[l==i] = scoreVisual[i-1]

# Create a figure with two subplots
fig, axs = plt.subplots(2, 2)

# Plot the first image in the left subplot
axs[0,0].imshow(cellIm, cmap='gray')
axs[0,0].axis('off')

cmap = colormaps.get_cmap('bwr')
# Plot the second image in the right subplot
im = axs[0,1].imshow(cellIm, cmap='gray')
# Plot colorful outlines on the image
for i in range(0,len(coords)):
    contour = coords[i]
    axs[0,1].plot(contour[1], contour[0], color=cmap(cellCrowdedness_gauss[i]))
axs[0,1].set_xlim(0, cellIm.shape[1])
axs[0,1].set_ylim(cellIm.shape[0], 0)
axs[0,1].axis('off')
axs[0,1].set_title('cellCrowdedness_gauss')

cmap = colormaps.get_cmap('bwr')
# Plot the second image in the right subplot
im = axs[1,0].imshow(cellIm, cmap='gray')
# Plot colorful outlines on the image
for i in range(0,len(coords)):
    contour = coords[i]
    axs[1,0].plot(contour[1], contour[0], color=cmap(cellArea_bounds[i]))
axs[1,0].set_xlim(0, cellIm.shape[1])
axs[1,0].set_ylim(cellIm.shape[0], 0)
axs[1,0].axis('off')
axs[1,0].set_title('cellArea_bounds')

cmap = colormaps.get_cmap('bwr')
# Plot the second image in the right subplot
im = axs[1,1].imshow(cellIm, cmap='gray')
# Plot colorful outlines on the image
for i in range(0,len(coords)):
    contour = coords[i]
    axs[1,1].plot(contour[1], contour[0], color=cmap(cellAssym_relativeToMax[i]))
axs[1,1].set_xlim(0, cellIm.shape[1])
axs[1,1].set_ylim(cellIm.shape[0], 0)
axs[1,1].axis('off')
axs[1,1].set_title('cellAssym_relativeToMax')



fig.tight_layout()
# plt.colorbar(im, orientation='vertical')
plt.show()

z=2
# parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# print(HelperFunctions.infoFromMetadata("SimpleCellOperants.CellArea_lowerUpperBound",showKwargs=True,showHelp=True))


# #Load the model outside the function - heavy speed increase for gridding specifically
# stardistModel = StarDist2D(None,name='StarDistModel',basedir="./AutonomousMicroscopy/Testing/ExampleData")
# #Run the stardistsegment with a preloaded model
# l,d = eval(HelperFunctions.createFunctionWithKwargs("StarDist.StarDistSegment_preloadedModel",image_data="ImageData",model="stardistModel",prob_thresh="0.35",nms_thresh="0.2"))

# #Export the ROIs for ImageJ
# export_imagej_rois("./AutonomousMicroscopy/Testing/ExampleData/example_rois.zip",d)

# #Export the labeled image
# save_tiff_imagej_compatible('./AutonomousMicroscopy/Testing/ExampleData/example_labels.tif', l, axes='YX')


# # fn = functionNamesFromDir("ROICalcScripts")
# # print(fn)