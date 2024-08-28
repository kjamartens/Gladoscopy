

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
        "StarDistSegment_ImageVis": {
            "input":[
                {"name": "Image", "type": [ndtiff.NDTiffDataset]}
            ],
            "output":[
                {"name": "segmented_image", "type": [np.ndarray], "importance": "Default"},
                {"name": "n_segmented_cells", "type": [int]},
                {"name": "details", "type": dict}
            ],
            "required_kwargs": [
                {"name": "modelStorageLoc", "description": "The location of the stored model - Should be the folder in which TF_SavedModel is located"}
            ],
            "optional_kwargs": [
                {"name": "prob_thresh", "description": "Probability threshold of the model, if unused, it uses the build-in value of the stored model"},
                {"name": "nms_thresh", "description": "Overlapping threshold of the model, if unused, it uses the build-in value of the stored model"}
            ],
            "help_string": "StarDist segmentation based via a stored model. This is a rather slow implementation (look at StarDistSegment_preloadedModel for a faster implementation that requires pre-loading the stardist model).",
            "display_name": "StarDist Image Segmentation"
        },
        "StarDistSegment_preLoadedModel_use": {
            "input":[
                {"name": "Image", "type": [ndtiff.NDTiffDataset]}
            ],
            "output":[
                {"name": "segmented_image", "type": [np.ndarray], "importance": "Default"},
                {"name": "n_segmented_cells", "type": [int]},
                {"name": "details", "type": dict}
            ],
            "required_kwargs": [
                {"name": "model", "description": "The model pre-loaded via 'load preloaded model' function"}
            ],
            "optional_kwargs": [
                {"name": "prob_thresh", "description": "Probability threshold of the model, if unused, it uses the build-in value of the stored model"},
                {"name": "nms_thresh", "description": "Overlapping threshold of the model, if unused, it uses the build-in value of the stored model"}
            ],
            "help_string": "StarDist segmentation based via a pre-loaded model. Requires using the 'load preloaded model' function",
            "display_name": "StarDist Image Segmentation - via preloaded model"
        }
    }

#Normal stardist segmentation, requires image_data and modelStorageLoc as required kwargs
def StarDistSegment_ImageVis(core,**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore
    
    NDTIFFStack = kwargs['Image']
    
    mean_image = da.mean(NDTIFFStack.as_array(), axis=(0)).compute() #type:ignore
    from stardist.models import StarDist2D
    modelDirectory = kwargs["modelStorageLoc"].rsplit('/', 1)
    #Load the model - better to do this out of the loop for time reasons
    stardistModel = StarDist2D(None,name=modelDirectory[1],basedir=modelDirectory[0]+"/") #type:ignore

    #Run starDist on the normalised image with prob and nms_thresh provided by kwargs (or not)
    if "prob_thresh" in provided_optional_args and "nms_thresh" in provided_optional_args:
        print(f'prob_thresh changed to : {str(kwargs["prob_thresh"])}, nms_thresh changed to {str(kwargs["nms_thresh"])}')
        
        try:
            probThreshVal = float(kwargs["prob_thresh"])
            nmsThreshVal = float(kwargs["nms_thresh"])
            labels, details = stardistModel.predict_instances(normalize(mean_image),prob_thresh=float(kwargs["prob_thresh"]),nms_thresh=float(kwargs["nms_thresh"])) #type:ignore
        except:
            try:
                probThreshVal = float(kwargs["prob_thresh"])
                labels, details = stardistModel.predict_instances(normalize(mean_image),prob_thresh=float(kwargs["prob_thresh"])) #type:ignore
            except:
                try:
                    nmsThreshVal = float(kwargs["nms_thresh"])
                    labels, details = stardistModel.predict_instances(normalize(mean_image),nms_thresh=float(kwargs["nms_thresh"])) #type:ignore
                except:
                    labels, details = stardistModel.predict_instances(normalize(mean_image)) #type:ignore
    elif "prob_thresh" in provided_optional_args and "nms_thresh" not in provided_optional_args:
        print(f'prob_thresh changed to : {str(kwargs["prob_thresh"])}')
        labels, details = stardistModel.predict_instances(normalize(mean_image),prob_thresh=float(kwargs["prob_thresh"])) #type:ignore
    elif "prob_thresh" not in provided_optional_args and "nms_thresh" in provided_optional_args:
        print(f'nms_thresh changed to {str(kwargs["nms_thresh"])}')
        labels, details = stardistModel.predict_instances(normalize(mean_image),nms_thresh=float(kwargs["nms_thresh"])) #type:ignore
    else:
        labels, details = stardistModel.predict_instances(normalize(mean_image)) #type:ignore
    
    #Extract detailed info
    coord, points, prob = details['coord'], details['points'], details['prob'] #type:ignore
    # details['labels'] = labels

    # import matplotlib.pyplot as plt
    # plt.imshow(labels)
    # plt.show()


    output = {}
    output['segmented_image'] = labels
    output['n_segmented_cells'] = len(np.unique(labels))
    output['details'] = details
    
    return output

def StarDistGeneralVis(datastruct,core,**kwargs):
    #This is how datastruct is organised...
    output,layer = datastruct
    
    layer.data = output['segmented_image']
    layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()]
    layer.opacity = 0.6
    layer.contrast_limits=(0,0.1)#(0,rescaled.max())
    layer.blending = 'additive'

def StarDistSegment_ImageVis_visualise(datastruct,core,**kwargs):
    StarDistGeneralVis(datastruct,core,**kwargs)
    
def StarDistSegment_preLoadedModel_use_visualise(datastruct,core,**kwargs):
    StarDistGeneralVis(datastruct,core,**kwargs)
    
def StarDistSegment_preLoadedModel_use(core,**kwargs):
    NDTIFFStack = kwargs['Image']
    mean_image = da.mean(NDTIFFStack.as_array(), axis=(0)).compute() #type:ignore
    from stardist.models import StarDist2D
    #Load the model - better to do this out of the loop for time reasons
    stardistModel = kwargs["model"] #type:ignore

    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore
    
    #Run starDist on the normalised image with prob and nms_thresh provided by kwargs (or not)
    if "prob_thresh" in provided_optional_args and "nms_thresh" in provided_optional_args:
        print(f'prob_thresh changed to : {str(kwargs["prob_thresh"])}, nms_thresh changed to {str(kwargs["nms_thresh"])}')
        
        try:
            probThreshVal = float(kwargs["prob_thresh"])
            nmsThreshVal = float(kwargs["nms_thresh"])
            labels, details = stardistModel.predict_instances(normalize(mean_image),prob_thresh=float(kwargs["prob_thresh"]),nms_thresh=float(kwargs["nms_thresh"])) #type:ignore
        except:
            try:
                probThreshVal = float(kwargs["prob_thresh"])
                labels, details = stardistModel.predict_instances(normalize(mean_image),prob_thresh=float(kwargs["prob_thresh"])) #type:ignore
            except:
                try:
                    nmsThreshVal = float(kwargs["nms_thresh"])
                    labels, details = stardistModel.predict_instances(normalize(mean_image),nms_thresh=float(kwargs["nms_thresh"])) #type:ignore
                except:
                    labels, details = stardistModel.predict_instances(normalize(mean_image)) #type:ignore
    elif "prob_thresh" in provided_optional_args and "nms_thresh" not in provided_optional_args:
        print(f'prob_thresh changed to : {str(kwargs["prob_thresh"])}')
        labels, details = stardistModel.predict_instances(normalize(mean_image),prob_thresh=float(kwargs["prob_thresh"])) #type:ignore
    elif "prob_thresh" not in provided_optional_args and "nms_thresh" in provided_optional_args:
        print(f'nms_thresh changed to {str(kwargs["nms_thresh"])}')
        labels, details = stardistModel.predict_instances(normalize(mean_image),nms_thresh=float(kwargs["nms_thresh"])) #type:ignore
    else:
        labels, details = stardistModel.predict_instances(normalize(mean_image)) #type:ignore
    
    #Extract detailed info
    coord, points, prob = details['coord'], details['points'], details['prob'] #type:ignore
    # details['labels'] = labels

    # import matplotlib.pyplot as plt
    # plt.imshow(labels)
    # plt.show()


    output = {}
    output['segmented_image'] = labels
    output['n_segmented_cells'] = len(np.unique(labels))
    output['details'] = details
    
    return output

