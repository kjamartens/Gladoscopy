from MainScripts import FunctionHandling
from stardist.models import StarDist2D
from csbdeep.utils import normalize
import inspect
import dask.array as da

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "StarDistSegment_ImageVis": {
            "required_kwargs": [
                {"name": "modelStorageLoc", "description": "The location of the stored model - Should be the folder in which TF_SavedModel is located"}
            ],
            "optional_kwargs": [
                {"name": "prob_thresh", "description": "Probability threshold of the model, if unused, it uses the build-in value of the stored model"},
                {"name": "nms_thresh", "description": "Overlapping threshold of the model, if unused, it uses the build-in value of the stored model"}
            ],
            "help_string": "StarDist segmentation based via a stored model. This is a rather slow implementation (look at StarDistSegment_preloadedModel for a faster implementation that requires pre-loading the stardist model)."
        }
    }

#Normal stardist segmentation, requires image_data and modelStorageLoc as required kwargs
def StarDistSegment_ImageVis(NDTIFFStack,core,**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore
    
    mean_image = da.mean(NDTIFFStack.as_array(), axis=(0)).compute() #type:ignore

    modelDirectory = kwargs["modelStorageLoc"].rsplit('/', 1)
    #Load the model - better to do this out of the loop for time reasons
    stardistModel = StarDist2D(None,name=modelDirectory[1],basedir=modelDirectory[0]+"/") #type:ignore

    #Run starDist on the normalised image with prob and nms_thresh provided by kwargs (or not)
    if "prob_thresh" in provided_optional_args and "nms_thresh" in provided_optional_args:
        print(f'prob_thresh changed to : {str(kwargs["prob_thresh"])}, nms_thresh changed to {str(kwargs["nms_thresh"])}')
        labels, details = stardistModel.predict_instances(normalize(mean_image),prob_thresh=kwargs["prob_thresh"], nms_thresh=kwargs["nms_thresh"]) #type:ignore
    elif "prob_thresh" in provided_optional_args and "nms_thresh" not in provided_optional_args:
        print(f'prob_thresh changed to : {str(kwargs["prob_thresh"])}')
        labels, details = stardistModel.predict_instances(normalize(mean_image),prob_thresh=kwargs["prob_thresh"]) #type:ignore
    elif "prob_thresh" not in provided_optional_args and "nms_thresh" in provided_optional_args:
        print(f'nms_thresh changed to {str(kwargs["nms_thresh"])}')
        labels, details = stardistModel.predict_instances(normalize(mean_image),nms_thresh=kwargs["nms_thresh"]) #type:ignore
    else:
        labels, details = stardistModel.predict_instances(normalize(mean_image)) #type:ignore
    
    #Extract detailed info
    coord, points, prob = details['coord'], details['points'], details['prob'] #type:ignore
    details['labels'] = labels

    #Return the coordinates of the ROIs (could also return the labeled inage via 'labels')
    return details

def StarDistSegment_ImageVis_visualise(datastruct,core,**kwargs):
    #This is how datastruct is organised...
    output,layer,mdaDataobject = datastruct
    
    rescaled = output['labels']
    
    layer.data = rescaled
    layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()]
    layer.opacity = 0.6
    layer.contrast_limits=(0,rescaled.max())
    layer.blending = 'additive'
