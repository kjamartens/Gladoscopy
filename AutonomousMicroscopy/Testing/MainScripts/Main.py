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
# sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"CellSegmentScripts"))

#Import all scripts in the custom script folders
from CellSegmentScripts import *
from CellScoringScripts import *
from ROICalcScripts import *
#Obtain the helperfunctions
import HelperFunctions #works

#Required PIPs:
# pip install csbdeep stardist tensorflow matplotlib tifffile numpy shapely

# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# Main script
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------


print(Polygon([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]).area)

testImageLoc = "./AutonomousMicroscopy/Testing/ExampleData/BF_test_avg.tiff"

# Open the TIFF file
with tifffile.TiffFile(testImageLoc) as tiff:
    # Read the image data
    ImageData = tiff.asarray()

#Example of non-preloaded stardistsegmentation
l,d = eval(HelperFunctions.createFunctionWithKwargs("StarDist.StarDistSegment",image_data="ImageData",modelStorageLoc="\"./AutonomousMicroscopy/Testing/ExampleData/StarDistModel\"",prob_thresh="0.35",nms_thresh="0.2"))

#print eccentricities for now
eval(HelperFunctions.createFunctionWithKwargs("SimpleCellOperants.Temp_printEccentricity",outline_coords="d"))
print(HelperFunctions.infoFromMetadata("SimpleCellOperants.Temp_printEccentricity",showKwargs=True,showHelp=True))

z=2
# parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# print(HelperFunctions.infoFromMetadata("SimpleCellOperants.CellArea_lowerUpperBound",showKwargs=True,showHelp=True))

# fn = HelperFunctions.functionNamesFromDir("CellScoringScripts")
# print(fn)

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