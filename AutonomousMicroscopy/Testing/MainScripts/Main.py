from csbdeep.io import save_tiff_imagej_compatible
from stardist import _draw_polygons, export_imagej_rois
import tifffile
from shapely import Polygon, affinity
import numpy as np
import math
import matplotlib.pyplot as plt

from stardist.models import StarDist2D
import sys, os
# Add the folder 2 folders up to the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#Import all scripts in the custom script folders
from CellSegmentScripts import *
from CellScoringScripts import *
from ROICalcScripts import *
from ScoringMetrics import *
#Obtain the helperfunctions
import HelperFunctions

#Required PIPs:
# pip install csbdeep stardist tensorflow matplotlib tifffile numpy shapely

# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# Main script
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------

testImageLoc = "./AutonomousMicroscopy/Testing/ExampleData/BF_test_avg.tiff"

# Open the TIFF file
with tifffile.TiffFile(testImageLoc) as tiff:
    # Read the image data
    ImageData = tiff.asarray()

#Example of non-preloaded stardistsegmentation
l,d = eval(HelperFunctions.createFunctionWithKwargs("StarDist.StarDistSegment",image_data="ImageData",modelStorageLoc="\"./AutonomousMicroscopy/Testing/ExampleData/StarDistModel\"",prob_thresh="0.35",nms_thresh="0.2"))

#print eccentricities for now
cellCrowdedness = eval(HelperFunctions.createFunctionWithKwargs("SimpleCellOperants.nrneighbours_basedonCellWidth",outline_coords="d",multiple_cellWidth_lookup="1"))
print(cellCrowdedness)
kk=eval(HelperFunctions.createFunctionWithKwargs("DefaultScoringMetrics.lowerUpperBound",value="cellCrowdedness",lower_bound="0",upper_bound="99"))
kk=eval(HelperFunctions.createFunctionWithKwargs("DefaultScoringMetrics.gaussScore",value="cellCrowdedness",meanVal="5",sigmaVal="2"))

cellArea = eval(HelperFunctions.createFunctionWithKwargs("SimpleCellOperants.cellArea",outline_coords="d"))
print(cellArea)
scoreVisual = eval(HelperFunctions.createFunctionWithKwargs("DefaultScoringMetrics.gaussScore",value="cellArea",meanVal="250",sigmaVal="50"))

scoreVisual = eval(HelperFunctions.createFunctionWithKwargs("DefaultScoringMetrics.gaussScore",value="cellCrowdedness",meanVal="10",sigmaVal="5"))


# fn = HelperFunctions.functionNamesFromDir("ScoringMetrics")
# print(fn)


#Get cell image
cellIm = ImageData
#start creating celloverlayimage
cellOverlayIm = np.zeros(l.shape)
for i in range(1,np.amax(l)):
    cellOverlayIm[l==i] = scoreVisual[i-1]

# Create a figure with two subplots
fig, axs = plt.subplots(1, 2)

# Plot the first image in the left subplot
axs[0].imshow(cellIm)
axs[0].axis('off')

# Plot the second image in the right subplot
im = axs[1].imshow(cellOverlayIm)
axs[1].axis('off')
fig.tight_layout()
plt.colorbar(im, orientation='vertical')
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