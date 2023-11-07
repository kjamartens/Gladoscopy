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
                {"name": "methodValue", "description": "Value(s) to be converted to score"},
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
                {"name": "methodValue", "description": "Value(s) to be converted to score"},
                {"name": "meanVal", "description": "Mean of Gaussian to which the value will be scored"},
                {"name": "sigmaVal", "description": "Sigma of Gaussian to which the value will be scored"}
            ],
            "optional_kwargs": [
            ],
            "help_string": "Score value(s) based on a gaussian profile with given mean, sigma - maximum score of 1 is possible."
        },
        "relativeToMaxScore": {
            "required_kwargs": [
                {"name": "methodValue", "description": "Value(s) to be converted to score"}
            ],
            "optional_kwargs": [
                {"name": "max_value", "description": "Maximum value. If left empty, the maximum value is taken from the value input"}
            ],
            "help_string": "Score value(s) based on the proportion to the max score. If no optional kwarg is given, max score is based on the input values."
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
def lowerUpperBound(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore
    if "outside_bounds_score" in provided_optional_args:
        outsideboundsscore = float(kwargs["outside_bounds_score"])
    else:
        outsideboundsscore = 0.
    #check if it's within bounds
    bounding = np.logical_and(np.array(kwargs["methodValue"]) >= float(kwargs["lower_bound"]), np.array(kwargs["methodValue"]) <= float(kwargs["upper_bound"])).astype(int)
    #change 0s to outsideboundsscore, leave 1s as 1
    bounding = np.where(bounding == 0, outsideboundsscore, bounding)
    return bounding

def gaussScore(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore
    #Calculate the gaussian score of the value(s)
    score = np.exp((-1*(np.array(kwargs["methodValue"])-float(kwargs["meanVal"]))**2)/(2*float(kwargs["sigmaVal"])**2))
    return score

def relativeToMaxScore(**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore
    if "max_value" in provided_optional_args:
        max_value = float(kwargs["max_value"])
    else:
        max_value = max(kwargs["methodValue"])
    #Calculate the proportional value(s) compared to max_value
    score = kwargs["methodValue"]/max_value
    return score