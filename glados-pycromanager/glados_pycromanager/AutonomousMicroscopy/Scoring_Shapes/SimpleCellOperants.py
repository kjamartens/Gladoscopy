from MainScripts import FunctionHandling
from shapely import Polygon, affinity
import math
import numpy as np
import inspect

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "lengthWidthRatio": {
            "required_kwargs": [
                {"name": "outline_coords", "description": "List of outline coordinates belonging to individual cells."},
            ],
            "optional_kwargs": [
            ],
            "help_string": "Returns the ratio between length and width of individual cells"
        },
        "cellArea": {
            "required_kwargs": [
                {"name": "outline_coords", "description": "List of outline coordinates belonging to individual cells."},
            ],
            "optional_kwargs": [
            ],
            "help_string": "Returns the area of individual cells"
        },
        "distToNearestNeighbour": {
            "required_kwargs": [
                {"name": "outline_coords", "description": "List of outline coordinates belonging to individual cells."},
            ],
            "optional_kwargs": [
            ],
            "help_string": "Returns the distance to the nearest neighbour cell"
        },
        "nrneighbours_basedonCellWidth": {
            "required_kwargs": [
                {"name": "outline_coords", "description": "List of outline coordinates belonging to individual cells."},
                {"name":"multiple_cellWidth_lookup","description":"Multiple of cell_width equavalent to which it considers a close-by cell a 'neighbour'"}
            ],
            "optional_kwargs": [
            ],
            "help_string": "Returns the number of neighbours of every cell that is within multiple_cellWidth_lookup small-axis sizes of the cell."
        }

        
    }

#-------------------------------------------------------------------------------------------------------------------------------
#Helper functions
#-------------------------------------------------------------------------------------------------------------------------------

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

#Get the area of an ROI
def getArea(ROI):
    return Polygon(ROI).area

#Get the minimum distance between ROI and otherROI
def distanceROItoOther(ROI,otherROI):
    return Polygon(ROI).distance(Polygon(otherROI))

#Get the hausdorff distance between ROI and otherROI
def hausdorff_distanceROItoOther(ROI,otherROI):
    return Polygon(ROI).hausdorff_distance(Polygon(otherROI))

#Get the distance (in px) to the nearest neighbouring ROI
def shortestDistanceToNeighbourROI(ROI,allROIs):
    currmindist = 1e9
    currmindistId = -1
    #Loop over all other ROIs
    for i in range(0,len(allROIs)):
        #Check the distance via distance
        foundmindist = distanceROItoOther(ROI,StarDistCoords_to_xyCoords(allROIs[i]))
        #Check if it's a new minimum, and if so, save this
        if foundmindist < currmindist and not  np.array_equal(ROI,StarDistCoords_to_xyCoords(allROIs[i])):
            currmindist = foundmindist
            currmindistId = i
    #return the
    return currmindist,currmindistId

#Small wrapper for stardist-coordinate system (required input) to xyCoords
def StarDistCoords_to_xyCoords(StarDistCoords):
    return np.rot90(StarDistCoords)

#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
def nrneighbours_basedonCellWidth(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore
    nr_neighbours = np.empty(len(kwargs["outline_coords"]))
    #Loop over all ROIs
    for i in range(0,len(kwargs["outline_coords"])):
        #Get axis lengths
        [celllongaxis, cellshortaxis] = getLongAndShortAxis(StarDistCoords_to_xyCoords(kwargs["outline_coords"][i]))
        #Loop over all other ROIs
        for j in range(0,len(kwargs["outline_coords"])):
            if i != j:
                #Get the minimum distance to the other ROI
                celltocelldist = distanceROItoOther(StarDistCoords_to_xyCoords(kwargs["outline_coords"][i]),StarDistCoords_to_xyCoords(kwargs["outline_coords"][j]))
                #If it's small enough, we have another neighbour
                if celltocelldist < cellshortaxis*float(kwargs["multiple_cellWidth_lookup"]):
                    nr_neighbours[i]+=1
    
    return np.int_(nr_neighbours)

def distToNearestNeighbour(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore
    dist_to_nn = np.empty(len(kwargs["outline_coords"]))
    for i in range(0,len(kwargs["outline_coords"])):
        [currmindist,currmindistId] = shortestDistanceToNeighbourROI(StarDistCoords_to_xyCoords(kwargs["outline_coords"][i]),kwargs["outline_coords"])
        dist_to_nn[i] = currmindist
    return dist_to_nn

def lengthWidthRatio(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore
    #Create an empty array for the length-to-width ratio
    lwratio = np.empty(len(kwargs["outline_coords"]))
    #Calculate the ratio via internal function for every cell
    for i in range(0,len(kwargs["outline_coords"])):
        lwratio[i] = getLongShortAxisRatio(StarDistCoords_to_xyCoords(kwargs["outline_coords"][i]))
    #return this
    return lwratio

def cellArea(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore
    cellarea = np.empty(len(kwargs["outline_coords"]))
    for i in range(0,len(kwargs["outline_coords"])):
        cellarea[i] = getArea(StarDistCoords_to_xyCoords(kwargs["outline_coords"][i]))
    return cellarea