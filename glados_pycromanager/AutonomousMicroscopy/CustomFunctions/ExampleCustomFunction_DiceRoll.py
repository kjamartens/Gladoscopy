import sys,os
#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling

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
        "DiceRoll": {
            "input":[
            ],
            "output":[
                {"name": "DiceResult", "type": [int], "importance": "Default"}
            ],
            "required_kwargs": [
                {"name": "MaxDiceValue", "description": "The largest value for a random value", "type": int, "default": 6}
            ],
            "help_string": "Example custom function",
            "display_name": "Example custom function - Roll a dice"
        }
    }


def DiceRoll(core,**kwargs):
    import logging
    diceRoll = np.random.randint(1,int(kwargs['MaxDiceValue']))

    logging.info(f"The dice rolled a {diceRoll}!")

    #Return the output
    output = {}
    output["DiceResult"] = diceRoll
    return output

