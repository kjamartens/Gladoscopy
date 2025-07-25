
def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
    import glados_pycromanager.GUI.utils as utils
else:
    from MainScripts import FunctionHandling
    import utils
# from shapely import Polygon, affinity
import math
import logging
import numpy as np
import inspect
import dask.array as da
import time
from scipy import signal
# from shapely import Polygon, affinity
import math
import numpy as np
import inspect
import dask.array as da
import time
from scipy.ndimage import gaussian_filter
from skimage.feature.peak import peak_local_max
# Load general dependencies
from imageio.v2 import imread
from bioimageio.spec.utils import download
from pprint import pprint
import matplotlib.pyplot as plt
import numpy as np
from bioimageio.core import load_description
from bioimageio.core import test_model
from bioimageio.spec.utils import load_array
from bioimageio.spec.model import v0_5
from bioimageio.core import create_prediction_pipeline
from bioimageio.core.digest_spec import create_sample_for_model
from bioimageio.core import Sample
from bioimageio.core import Tensor
import imageio

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "BioImageModelZoo": {
            "required_kwargs": [
                {"name": "model_id", "description": "ID of the Model", "default": "affable-shark", "type": str}
            ],
            "optional_kwargs": [
                {"name": "imageLayerId", "description": "model layer id", "default": 0, "type": int}
            ],
            "help_string": "phasor-based SMLM.",
            "display_name": "BioImage Model Zoo",
            "run_delay": 200,
            "visualise_delay": 200,
            "visualisation_type": "image", #'image', 'points', 'value', or 'shapes'
            "input":[
            ],
            "output":[
            ],
        }
    }




def getModel(model_id="",model_doi="",model_url=""):
    if model_id != "":
        model = load_description(model_id)
    elif model_doi != "":
        model = load_description(model_doi)
    elif model_url != "":
        model = load_description(model_url)
    else:
        print("\nPlease specify a model ID, DOI or URL")
    return model

def getOutputImages(prediction,modelSample):
    
    if tuple(sorted(prediction.members[modelSample['model_tensor_outputName']].data.dims)) == tuple(sorted(('batch','channel','y','x'))):
        outputImages = prediction.members[modelSample['model_tensor_outputName']].data.transpose('batch','channel','x','y').data
    elif tuple(sorted(prediction.members[modelSample['model_tensor_outputName']].data.dims)) == tuple(sorted(('batch','y','x','channel'))):
        outputImages = prediction.members[modelSample['model_tensor_outputName']].data.transpose('b','c','x','y').data
    elif tuple(sorted(prediction.members[modelSample['model_tensor_outputName']].data.dims)) == tuple(sorted(('batch','y','x','channel','object'))):
        outputImages = prediction.members[modelSample['model_tensor_outputName']].data.transpose('batch','channel','x','y','object').data
        #delete final axis:
        outputImages = np.squeeze(outputImages,axis=4)
    return outputImages

def setupSample(model=None,input_image=None):
    if model == None:
        print('Model input required!')
        return
    if type(input_image) == type(None):
        print('Input image required!')
        return
    if hasattr(model.inputs[0],'name'):
        model_tensor_inputName = model.inputs[0].name
        model_tensor_outputName = model.outputs[0].name
    elif hasattr(model.inputs[0],'id'):
        model_tensor_inputName = model.inputs[0].id
        model_tensor_outputName = model.outputs[0].id


    shapev = model.inputs[0].axes
    #Check if not a string:
    if type(shapev) != str:
        shapevNew = ''
        for v in range(len(shapev)):
            if shapev[v].id == 'batch':
                shapevNew += 'b'
            if shapev[v].id == 'x':
                shapevNew += 'x'
            if shapev[v].id == 'y':
                shapevNew += 'y'
            if shapev[v].id == 'channel':
                shapevNew += 'c'
        shapev = shapevNew

    #I'm going to assume always a single color channel, tough luck otherwise.
    #My image is x,y - it needs to go to x y b c, where b and c are always 1. Thus, I need to expand with np.newaxis. However, where I need to expand is...  based on the axes
    bcindexsort = sorted((shapev.index('b'), shapev.index('c')),reverse=True)
    for bc in bcindexsort:
        if bc > 2:
            input_image = input_image[:, :,np.newaxis]
        elif bc < 2:
            input_image = input_image[np.newaxis,:, :]
    print(f"array shape: {input_image.shape}")

    #Check if it requires 3d == color input, if so, simply repeat the grayscale for now.
    if model.inputs[0].shape[1] == 3:
        input_image = np.repeat(input_image, 3, axis=1)
        print(f"Expanded input_image to shape: {input_image.shape}")

    shapev = model.inputs[0].axes
    if type(shapev) != str:
        test_input_tensor = Tensor.from_numpy(input_image, dims=[shapev[0].id,shapev[1].id,shapev[2].id,shapev[3].id])
    else:
        test_input_tensor = Tensor.from_numpy(input_image, dims=[shapev[0],shapev[1],shapev[2],shapev[3]])

    sample=create_sample_for_model(
        model=model, inputs={model_tensor_inputName:test_input_tensor}, sample_id="my_demo_sample"
    )
    
    df={}
    df['sample'] = sample
    df['model_tensor_inputName'] = model_tensor_inputName
    df['model_tensor_outputName'] = model_tensor_outputName
    
    return df

# BMZ_MODEL_ID = affable-shark# "discreet-rooster"#"hiding-tiger"#
# BMZ_MODEL_DOI = ""#"10.5281/zenodo.6287342"
# BMZ_MODEL_URL = ""#"https://uk1s3.embassy.ebi.ac.uk/public-datasets/bioimage.io/affable-shark/draft/files/rdf.yaml"

# input_image = imageio.imread('C:\\Users\\kjamartens\\Documents\\Github\\ScopeGUI\\glados-pycromanager\\glados_pycromanager\\testIm_bioimageModel.png')



#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
class BioImageModelZoo():
    def __init__(self,core,**kwargs):
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        #Initialise it all
        self.outputImage = []
        self.modelId = kwargs['model_id']
        self.imageLayerId = int(kwargs['imageLayerId'])
        self.model = getModel(model_id=self.modelId)
        self.modelSample = setupSample(model=self.model,input_image=np.zeros((64,64)))
        self.prediction_pipeline = create_prediction_pipeline(
            self.model, devices=None, weight_format=None
        )

        return None

    def run(self,image,metadata,shared_data,core,**kwargs):
        logging.info('Attempting bioimagemodelzoo Run')
        
        self.lastImage = image
        self.modelSample = setupSample(model=self.model,input_image=image)
        #Finally, predict
        prediction: Sample = self.prediction_pipeline.predict_sample_without_blocking(self.modelSample['sample'])

        #Get the output images
        self.outputImage = getOutputImages(prediction,self.modelSample)

    def end(self,core,**kwargs):
        return
    
    def visualise_init(self): 
        print('Visualise_init')
        layerName = 'BioImageModelZoo'
        layerType = 'image' #layerType has to be from image|labels|points|shapes|surface|tracks|vectors
        self.firstLayerInit = True
        return layerName,layerType
    
    def visualise(self,image,metadata,core,napariLayer,**kwargs):
        try:
            napariLayer.data = self.outputImage[0,self.imageLayerId,:,:]
        except:
            logging.info(f"Issue with bioimagemodelzoo layer update")
        return napariLayer