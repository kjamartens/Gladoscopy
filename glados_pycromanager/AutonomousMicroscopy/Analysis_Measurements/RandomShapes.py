import sys,os
#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
# from shapely import Polygon, affinity
import math
import numpy as np
import inspect
import dask.array as da
import ndtiff

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "DrawRandomShape": {
            "input":[
                {"name": "Image", "type": [ndtiff.NDTiffDataset]}
            ],
            "output":[
            ],
            "required_kwargs": [
            ],
            "optional_kwargs": [
            ],
            "help_string": "Draw a random shape.",
            "display_name": "Explanatory - draw random shape",
            "visualisation_type" : "shapes" #'Image', 'points', 'value', or 'shapes'
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
def DrawRandomShape(core,**kwargs):
    
    output = {}
    return output


def DrawRandomShape_visualise(datastruct,core,**kwargs):
    # This is how datastruct is organised...
    output,shapesLayer = datastruct

    # Generate random points
    points = np.random.rand(5, 2) * 512 

    #Make a convex hull out of this to get a nicer polygon
    from scipy.spatial import ConvexHull
    hull = ConvexHull(points)
    convex_shape = points[hull.vertices]

    # Set this to the layer data
    shapesLayer.data = [convex_shape]
    shapesLayer.shape_type = 'polygon'
    shapesLayer.edge_color = 'red'
    shapesLayer.face_color = 'royalblue'
    