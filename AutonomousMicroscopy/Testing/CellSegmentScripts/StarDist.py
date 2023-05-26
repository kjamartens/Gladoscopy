from MainScripts import FunctionHandling
from stardist.models import StarDist2D
from csbdeep.utils import normalize
import inspect

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "StarDistSegment": {
            "required_kwargs": [
                {"name": "image_data", "description": "The image data"},
                {"name": "modelStorageLoc", "description": "The location of the stored model - Should be the folder in which TF_SavedModel is located"}
            ],
            "optional_kwargs": [
                {"name": "prob_thresh", "description": "Probability threshold of the model, if unused, it uses the build-in value of the stored model"},
                {"name": "nms_thresh", "description": "Overlapping threshold of the model, if unused, it uses the build-in value of the stored model"}
            ],
            "help_string": "StarDist segmentation based via a stored model. This is a rather slow implementation (look at StarDistSegment_preloadedModel for a faster implementation that requires pre-loading the stardist model)."
        },
        "StarDistSegment_preloadedModel": {
            "required_kwargs": [
                {"name": "image_data", "description": "The image data"},
                {"name": "model", "description": "The StarDist model pre-loaded via StarDist2D()"}
            ],
            "optional_kwargs": [
                {"name": "prob_thresh", "description": "Probability threshold of the model, if unused, it uses the build-in value of the stored model"},
                {"name": "nms_thresh", "description": "Overlapping threshold of the model, if unused, it uses the build-in value of the stored model"}
            ],
            "help_string": "StarDist segmentation based via a pre-loaded model. Faster implementation compared to StarDistSegment, but requires pre-loading of the model."
        }
    }

#Normal stardist segmentation, requires image_data and modelStorageLoc as required kwargs
def StarDistSegment(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs)

    modelDirectory = kwargs["modelStorageLoc"].rsplit('/', 1)
    #Load the model - better to do this out of the loop for time reasons
    stardistModel = StarDist2D(None,name=modelDirectory[1],basedir=modelDirectory[0]+"/")

    #Run starDist on the normalised image with prob and nms_thresh provided by kwargs (or not)
    if "prob_thresh" in provided_optional_args and "nms_thresh" in provided_optional_args:
        print(f'prob_thresh changed to : {str(kwargs["prob_thresh"])}, nms_thresh changed to {str(kwargs["nms_thresh"])}')
        labels, details = stardistModel.predict_instances(normalize(kwargs["image_data"]),prob_thresh=kwargs["prob_thresh"], nms_thresh=kwargs["nms_thresh"])
    elif "prob_thresh" in provided_optional_args and "nms_thresh" not in provided_optional_args:
        print(f'prob_thresh changed to : {str(kwargs["prob_thresh"])}')
        labels, details = stardistModel.predict_instances(normalize(kwargs["image_data"]),prob_thresh=kwargs["prob_thresh"])
    elif "prob_thresh" not in provided_optional_args and "nms_thresh" in provided_optional_args:
        print(f'nms_thresh changed to {str(kwargs["nms_thresh"])}')
        labels, details = stardistModel.predict_instances(normalize(kwargs["image_data"]),nms_thresh=kwargs["nms_thresh"])
    else:
        labels, details = stardistModel.predict_instances(normalize(kwargs["image_data"]))
    
    #Extract detailed info
    coord, points, prob = details['coord'], details['points'], details['prob']

    #Return the labeled image, and the coordinates of the ROIs
    return [labels,coord]

def StarDistSegment_preloadedModel(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs)

    #Run starDist on the normalised image with prob and nms_thresh provided by kwargs (or not)
    if "prob_thresh" in provided_optional_args and "nms_thresh" in provided_optional_args:
        print(f'prob_thresh changed to : {str(kwargs["prob_thresh"])}, nms_thresh changed to {str(kwargs["nms_thresh"])}')
        labels, details = kwargs["model"].predict_instances(normalize(kwargs["image_data"]),prob_thresh=kwargs["prob_thresh"], nms_thresh=kwargs["nms_thresh"])
    elif "prob_thresh" in provided_optional_args and "nms_thresh" not in provided_optional_args:
        print(f'prob_thresh changed to : {str(kwargs["prob_thresh"])}')
        labels, details = kwargs["model"].predict_instances(normalize(kwargs["image_data"]),prob_thresh=kwargs["prob_thresh"])
    elif "prob_thresh" not in provided_optional_args and "nms_thresh" in provided_optional_args:
        print(f'nms_thresh changed to {str(kwargs["nms_thresh"])}')
        labels, details = kwargs["model"].predict_instances(normalize(kwargs["image_data"]),nms_thresh=kwargs["nms_thresh"])
    else:
        labels, details = kwargs["model"].predict_instances(normalize(kwargs["image_data"]))

    #Extract detailed info
    coord, points, prob = details['coord'], details['points'], details['prob']

    #Return the labeled image, and the coordinates of the ROIs
    return [labels,coord]
