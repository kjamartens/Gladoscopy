from MainScripts import FunctionHandling
from shapely import Polygon, affinity
import math
import numpy as np
import inspect

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "CellArea_lowerUpperBound": {
            "required_kwargs": [
                {"name": "outline_coords", "description": "List of outline coordinates belonging to individual cells."},
                {"name": "size_bounds", "description": "[lower, upper] bounds in pixel units"}
            ],
            "optional_kwargs": [
            ],
            "help_string": "Score cells 1 or 0 based on whether they are within area lower/upper bounds."
        },
        "Temp_printEccentricity": {
            "required_kwargs": [
                {"name": "outline_coords", "description": "List of outline coordinates belonging to individual cells."},
            ],
            "optional_kwargs": [
            ],
            "help_string": "Prints eccentricity of all ROIs"
        }
    }

#Get the rotation (in degrees!) of a ROI
def getRotation(ROI):
    #Get the rotated rectangle (i.e. rotated bounds) of this ROI
    mrr = Polygon(ROI).minimum_rotated_rectangle
    # Calculate the rotation angle (in radian)
    rotation_angle = math.atan2(mrr.exterior.xy[0][1]-mrr.exterior.xy[0][0],mrr.exterior.xy[1][1]-mrr.exterior.xy[1][0])
    return(math.degrees(rotation_angle))

#Get the long and short axis of a ROI
def getLongAndShortAxis(ROI):
    rotation_angle = getRotation(ROI)
    #Rotate the original ROI with this rotation angle - now the long axis should be vertical, short axis horizontal
    rotated_ROI = affinity.rotate(Polygon(ROI),rotation_angle, use_radians=False)
    #Calculate the ROI long and short axes based on the bounding rectangle on the rotated ROI
    rotated_long_axis = rotated_ROI.bounds[2] - rotated_ROI.bounds[0] 
    rotated_short_axis = rotated_ROI.bounds[3] - rotated_ROI.bounds[1]
    return [rotated_long_axis,rotated_short_axis]

#Get the eccentricity of a ROI
def getEccentricity(ROI):
    [rotated_long_axis,rotated_short_axis] = getLongAndShortAxis(ROI)
    #calculate eccentricity via the semi-major/minor axis (i.e. axis/2)
    eccentricity = math.sqrt(1-(((rotated_short_axis/2)**2)/((rotated_long_axis/2)**2)))
    return eccentricity

#Get the ratio of long:short axis of a ROI
def getLongShortAxisRatio(ROI):
    [rotated_long_axis,rotated_short_axis] = getLongAndShortAxis(ROI)
    #Return the ratio of the axes
    return rotated_long_axis/rotated_short_axis

#Small wrapper for stardist-coordinate system (required input) to xyCoords
def StarDistCoords_to_xyCoords(StarDistCoords):
    return np.rot90(StarDistCoords)

def CellArea_lowerUpperBound(**kwargs):
    return 1

def Temp_printEccentricity(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs)
    for i in range(0,len(kwargs["outline_coords"])):
        print(i)
        # print(getRotation(StarDistCoords_to_xyCoords(kwargs["outline_coords"][i])))
        # print(getLongAndShortAxis(StarDistCoords_to_xyCoords(kwargs["outline_coords"][i])))
        print(getLongShortAxisRatio(StarDistCoords_to_xyCoords(kwargs["outline_coords"][i])))
