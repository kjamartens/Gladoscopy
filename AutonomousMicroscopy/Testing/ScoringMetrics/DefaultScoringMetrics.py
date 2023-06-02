from MainScripts import FunctionHandling
from shapely import Polygon, affinity
import math
import numpy as np
import inspect

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "lowerUpperBound": {
            "required_kwargs": [
                {"name": "value", "description": "Value(s) to be converted to score"},
                {"name": "lower_bound", "description": "lower bound"},
                {"name": "upper_bound", "description": "upper bound"}
            ],
            "optional_kwargs": [
                {"name": "outside_bounds_score", "description": "Score the object will be given if it's outside the bounds, default 0"}
            ],
            "help_string": "Score value(s) as 1 or outside_bounds_score (default 0) depending on whether they're within a bound or not."
        },
        "gaussScore": {
            "required_kwargs": [
                {"name": "value", "description": "Value(s) to be converted to score"},
                {"name": "meanVal", "description": "Mean of Gaussian to which the value will be scored"},
                {"name": "sigmaVal", "description": "Sigma of Gaussian to which the value will be scored"}
            ],
            "optional_kwargs": [
            ],
            "help_string": "Score value(s) based on a gaussian profile with given mean, sigma - maximum score of 1 is possible."
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
def lowerUpperBound(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs)
    if "outside_bounds_score" in provided_optional_args:
        outsideboundsscore = kwargs["outside_bounds_score"]
    else:
        outsideboundsscore = 0
    #check if it's within bounds
    bounding = np.logical_and(np.array(kwargs["value"]) >= kwargs["lower_bound"], np.array(kwargs["value"]) <= kwargs["upper_bound"]).astype(int)
    #change 0s to outsideboundsscore, leave 1s as 1
    bounding = np.where(bounding == 0, outsideboundsscore, bounding)
    return bounding

def gaussScore(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs)
    #Calculate the gaussian score of the value(s)
    score = np.exp((-1*(np.array(kwargs["value"])-kwargs["meanVal"])**2)/(2*kwargs["sigmaVal"]**2))
    return score