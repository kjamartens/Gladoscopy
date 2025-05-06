import numpy as np
import inspect
import utils
import logging
import time

def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
else:
    from MainScripts import FunctionHandling
# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return { 
        "RealTimeCounter": {
            "required_kwargs": [
                {"name": "Color", "description": "Color of the text", "default": 'red', "type": str}
            ],
            "optional_kwargs": [
            ],
            "help_string": "RT counter.",
            "display_name": "RT counter",
            "run_delay": 0,
            "visualise_delay": 10,
            "visualisation_type": "points", #'image', 'points', 'value', or 'shapes'
            "input":[
            ],
            "output":[
            ],
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
class RealTimeCounter():
    def __init__(self,core,**kwargs):
        logging.info('INITIALISING COUNTER REAL-TIME ANALYSIS')
        # print(core)
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore
        self.currentValue = 0
        self.initVal = 25
        logging.info('in RT_counter at time '+str(time.time()))
        return None

    def run(self,image,metadata,shared_data,core,**kwargs):
        run_time = time.time()
        if 'ImageNumber' in metadata:
            self.currentValue = float(metadata['ImageNumber'])
            logging.info("At frame: "+metadata['ImageNumber'])
        else:
            #Append to full list with frame info
            self.dimensionOrder, self.n_entries_in_dims, self.uniqueEntriesAllDims = utils.getDimensionsFromAcqData(shared_data._mdaModeParams)
            mda_values = []
            for v in list(self.uniqueEntriesAllDims.keys()):
                mda_values = np.hstack((mda_values,metadata['Axes'][v]))
                
            self.currentValue = metadata['Axes'][v]
        logging.info(f"Running time counter rta: {time.time()-run_time}")
    
    def end(self,core,**kwargs):
        logging.info('ENDING COUNTER REAL-TIME ANALYSIS')
        return
    
    def visualise_init(self): 
        logging.info('INITIALISING VISUALISATION COUNTER REAL-TIME ANALYSIS')
        layerName = 'RT counter'
        layerType = 'points' #layerType has to be from image|labels|points|shapes|surface|tracks|vectors
        self.firstLayerInit = True
        return layerName,layerType
    
    def visualise(self,image,metadata,core,napariLayer,**kwargs):
        vis_time = time.time()
        napariLayer.data = np.array([[0, 0]])
        properties = {
            'outputval': [self.currentValue],
        }
        #Only the properties need to be changed
        napariLayer.properties = properties
        if self.firstLayerInit:
            #The text data of the napariLayer need to be changed only on init.
            textv = {
                'string': 'Current frame: {outputval:0.0f}',
                'size': 10,  # Set a default value
                'color': 'cyan',  # Set a default value 
                'anchor': 'upper_left',
                'translation': [0, 0]
            }
            
            # Then optionally override with kwargs if they exist:
            if 'Color' in kwargs:
                textv['color'] = kwargs['Color']
            if 'Size' in kwargs:
                textv['size'] = int(kwargs['Size'])
            napariLayer.text = textv
            #Only change if really needed:
            napariLayer.symbol = 'disc'
            napariLayer.size = 0
            napariLayer.selected_data = []
            self.firstLayerInit = False
        logging.info(f"Visualising time counter rta: {time.time()-vis_time}")