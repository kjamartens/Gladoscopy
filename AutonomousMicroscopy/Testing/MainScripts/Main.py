from csbdeep.io import save_tiff_imagej_compatible
from stardist import _draw_polygons, export_imagej_rois
import tifffile
from shapely import Polygon, affinity
import numpy as np
import math

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
eval(HelperFunctions.createFunctionWithKwargs("SimpleCellOperants.nrneighbours_basedonCellWidth",outline_coords="d",multiple_cellWidth_lookup="1"))
print(HelperFunctions.infoFromMetadata("DefaultScoringMetrics",showKwargs=True,showHelp=True))

kk=eval(HelperFunctions.createFunctionWithKwargs("DefaultScoringMetrics.lowerUpperBound",value="1",lower_bound="0",upper_bound="2"))
kk=eval(HelperFunctions.createFunctionWithKwargs("DefaultScoringMetrics.gaussScore",value="[-5,-4,-3,-2,-1,0,1,2,3,4,5,99]",meanVal="2",sigmaVal="2"))
print(kk)

fn = HelperFunctions.functionNamesFromDir("ScoringMetrics")
print(fn)

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