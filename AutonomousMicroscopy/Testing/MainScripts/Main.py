from csbdeep.io import save_tiff_imagej_compatible
from stardist import _draw_polygons, export_imagej_rois
import tifffile

from stardist.models import StarDist2D

#Import all scripts in the custom script folders
from CellSegmentScripts import *
from ROICalcScripts import *

import HelperFunctions

#Required PIPs:
# pip install stardist
# pip install tensorflow
# pip install matplotlib
# pip install tifffile
# pip install csbdeep
# pip install numpy

# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# Main script
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------

print(HelperFunctions.infoFromMetadata("StarDist.StarDistSegment",showKwargs=True,showHelp=True))

# fn = functionNamesFromDir("CellSegmentScripts")
# print(fn)

testImageLoc = "./ExampleData/BF_test_avg.tiff"

# Open the TIFF file
with tifffile.TiffFile(testImageLoc) as tiff:
    # Read the image data
    ImageData = tiff.asarray()

#Example of non-preloaded stardistsegmentation
l,d = eval(HelperFunctions.createFunctionWithKwargs("StarDist.StarDistSegment",image_data="ImageData",modelStorageLoc="\"./ExampleData/StarDistModel\"",prob_thresh="0.35",nms_thresh="0.2"))

#Load the model outside the function - heavy speed increase for gridding specifically
stardistModel = StarDist2D(None,name='StarDistModel',basedir="./ExampleData")
#Run the stardistsegment with a preloaded model
l,d = eval(HelperFunctions.createFunctionWithKwargs("StarDist.StarDistSegment_preloadedModel",image_data="ImageData",model="stardistModel",prob_thresh="0.35",nms_thresh="0.2"))

#Export the ROIs for ImageJ
export_imagej_rois("./ExampleData/example_rois.zip",d)

#Export the labeled image
save_tiff_imagej_compatible('./ExampleData/example_labels.tif', l, axes='YX')


# fn = functionNamesFromDir("ROICalcScripts")
# print(fn)