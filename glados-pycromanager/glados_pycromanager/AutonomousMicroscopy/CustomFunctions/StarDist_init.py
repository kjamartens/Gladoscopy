
def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
else:
    from MainScripts import FunctionHandling
# from stardist.models import StarDist2D
from csbdeep.utils import normalize
import inspect
import dask.array as da
import ndtiff
import numpy as np
# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "StarDistSegment_preLoadedModel_init": {
            "input":[
            ],
            "output":[
                {"name": "stardist_model", "type": [None], "importance": "Default"}
            ],
            "required_kwargs": [
                {"name": "modelStorageLoc", "description": "The location of the stored model - Should be the folder in which TF_SavedModel is located"}
            ],
            "help_string": "INIT of StarDist segmentation based via a pre-loaded model. Requires using the 'load preloaded model' function",
            "display_name": "StarDist Image Segmentation - initialise preloaded model"
        }
    }


def StarDistSegment_preLoadedModel_init(core,**kwargs):
    from stardist.models import StarDist2D
    modelDirectory = kwargs["modelStorageLoc"].rsplit('/', 1)
    #Load the model - better to do this out of the loop for time reasons
    stardistModel = StarDist2D(None,name=modelDirectory[1],basedir=modelDirectory[0]+"/") #type:ignore

    #Return the model
    output = {}
    output["stardist_model"] = stardistModel
    return output

