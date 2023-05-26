import os
import tifffile
import warnings
import inspect
import importlib
from csbdeep.io import save_tiff_imagej_compatible
from stardist import _draw_polygons, export_imagej_rois


from stardist.models import StarDist2D

#Import all scripts in the custom script folders
from CellSegmentScripts import *
from ROICalcScripts import *

#Required PIPs:
# pip install stardist
# pip install tensorflow
# pip install matplotlib
# pip install tifffile
# pip install csbdeep
# pip install numpy

# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# Function declarations
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------

#Returns whether a function exists and is callable
def function_exists(obj):
    return callable(obj) and inspect.isfunction(obj)

#Returns whether a subfunction exists specifically in module_name and is callable
def subfunction_exists(module_name, subfunction_name):
    try:
        module = importlib.import_module(module_name)
        a = hasattr(module, subfunction_name)
        b = callable(getattr(module, subfunction_name))
        return hasattr(module, subfunction_name) and callable(getattr(module, subfunction_name))
    except (ImportError, AttributeError):
        return False
    
# Return all functions that are found in a specific directory
def functionNamesFromDir(dirname):
    #initialise empty array
    functionnamearr = []
    #Loop over all files
    for file in os.listdir("./"+dirname):
        #Check if they're .py files
        if file.endswith(".py"):
            #Check that they're not init files or similar
            if not file.startswith("_"):
                #Get the function name
                functionName = file[:-3]
                #Get the metadata from this function and from there obtain
                try:
                    functionMetadata = eval(f'{str(functionName)}.__function_metadata__()')
                    for singlefunctiondata in functionMetadata:
                        #Also check this against the actual sub-routines and raise an error (this should also be present in the __init__ of the folders)
                        subroutineName = f"{functionName}.{singlefunctiondata}"
                        if subfunction_exists(f'{dirname}.{functionName}',singlefunctiondata):
                            functionnamearr.append(subroutineName)
                        else:
                            warnings.warn(f"Warning: {subroutineName} is present in __function_metadata__ but not in the actual file!")
                #Error handling if __function_metadata__ doesn't exist
                except AttributeError:
                    #Get all callable subroutines and store those
                    subroutines = []
                    for subroutineName, obj in inspect.getmembers(eval(f'{functionName}')):
                        if function_exists(obj):
                            subroutines.append(subroutineName)
                            functionnamearr.append(subroutineName)
                    #Give the user the warning and the solution
                    warnings.warn(f"Warning: {str(functionName)} does not have the required __function_metadata__ ! All functions that are found in this module are added! They are {subroutines}")
    #return all functions
    return functionnamearr

#Obtain the help-file and info on kwargs on a specific function
#TODO: the same, but for a specific sub-function (i.e. StarDistSegment rather than StarDist parent)
#Optional: Boolean kwarg showKwargs & Boolean kwarg showHelp
def infoFromMetadata(functionname,**kwargs):
    showKwargs = kwargs.get('showKwargs', True)
    showHelp = kwargs.get('showHelp', True)
    try:
        functionMetadata = eval(f'{str(functionname)}.__function_metadata__()')
        finaltext = f"""\
        --------------------------------------------------------------------------------------
        {functionname} contains {len(functionMetadata)} callable functions: {", ".join(str(singlefunctiondata) for singlefunctiondata in functionMetadata)}
        --------------------------------------------------------------------------------------
        """
        name_arr = []
        help_arr = []
        rkwarr_arr = []
        okwarr_arr = []
        for i in range(0,len(functionMetadata)):
            #Get name text for all entries
            name_arr.append([list(functionMetadata.keys())[i]])
            #Get help text for all entries
            help_arr.append(functionMetadata[list(functionMetadata.keys())[i]]["help_string"])
            #Get text for all the required kwarrs
            txt = ""
            #Loop over the number or rkwarrs
            for k in range(0,len(functionMetadata[list(functionMetadata.keys())[i]]["required_kwargs"])):
                zz = functionMetadata[list(functionMetadata.keys())[i]]["required_kwargs"][k]
                for key, value in functionMetadata[list(functionMetadata.keys())[i]]["required_kwargs"][k].items():
                    txt += f"{key}: {value}\n"
            rkwarr_arr.append(txt)
            #Get text for all the optional kwarrs
            txt = ""
            #Loop over the number of okwarrs
            for k in range(0,len(functionMetadata[list(functionMetadata.keys())[i]]["optional_kwargs"])):
                zz = functionMetadata[list(functionMetadata.keys())[i]]["optional_kwargs"][k]
                for key, value in functionMetadata[list(functionMetadata.keys())[i]]["optional_kwargs"][k].items():
                    txt += f"{key}: {value}\n"
            okwarr_arr.append(txt)
        
            #Fuse all the texts together
            if showHelp or showKwargs:
                finaltext += f"""
                -------------------------------------------
                {name_arr[i][0]} information:
                -------------------------------------------"""
            if showHelp:
                finaltext += f"""
                {help_arr[i]}"""
            if showKwargs:
                finaltext += f"""
                ----------
                Required keyword arguments (kwargs):
                {rkwarr_arr[i]}----------
                Optional keyword arguments (kwargs):
                {okwarr_arr[i]}"""
            finaltext += "\n"
        
        finaltext += "--------------------------------------------------------------------------------------\n"
        #Remove left-leading spaces
        finaltext = "\n".join(line.lstrip() for line in finaltext.splitlines())

        return finaltext
    #Error handling if __function_metadata__ doesn't exist
    except AttributeError:
        return f"No __function_metadata__ in {functionname}"

#Run a function with unknown number of parameters via the eval() method
#Please note that the arg values need to be the string variants of the variable, not the variable itself!
def evalFunctionWithArgs(functionname,*args):
    #Start string with functionname.functionname - probably changing later for safety/proper usages
    fullstring = functionname+"."+functionname+"("
    #Add all arguments to the function
    idloop = 0
    for arg in args:
        if idloop>0:
            fullstring = fullstring+","
        fullstring = fullstring+str(arg)
        idloop+=1
    #Finish the function string
    fullstring = fullstring+")"
    #run the function
    return eval(fullstring)

#Run a function with unknown number of kwargs via the eval() method
#Please note that the kwarg values need to be the string variants of the variable, not the variable itself!
def evalFunctionWithKwargs(functionname,**kwargs):
    #Start string with functionname.functionname - probably changing later for safety/proper usages
    fullstring = functionname+"("
    #Add all arguments to the function
    idloop = 0
    for key, value in kwargs.items():
        if idloop>0:
            fullstring = fullstring+","
        fullstring = fullstring+str(key)+"="+str(value)
        idloop+=1
    #Finish the function string
    fullstring = fullstring+")"
    #run the function
    return eval(fullstring)

# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# Main script
# -----------------------------------------------------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------------------------------------------------

print(infoFromMetadata("StarDist",showKwargs=True,showHelp=True))

fn = functionNamesFromDir("CellSegmentScripts")
print(fn)

testImageLoc = "./ExampleData/BF_test_avg.tiff"

# Open the TIFF file
with tifffile.TiffFile(testImageLoc) as tiff:
    # Read the image data
    ImageData = tiff.asarray()


#Example of non-preloaded stardistsegmentation
l,d = evalFunctionWithKwargs("StarDist.StarDistSegment",image_data="ImageData",modelStorageLoc="\"./ExampleData/StarDistModel\"",prob_thresh="0.35",nms_thresh="0.2")

#Load the model outside the function - heavy speed increase for gridding specifically
stardistModel = StarDist2D(None,name='StarDistModel',basedir="./ExampleData")
#Run the stardistsegment with a preloaded model
l,d = evalFunctionWithKwargs("StarDist.StarDistSegment_preloadedModel",image_data="ImageData",model="stardistModel",prob_thresh="0.35",nms_thresh="0.2")

#Export the ROIs for ImageJ
export_imagej_rois("./ExampleData/example_rois.zip",d)

#Export the labeled image
save_tiff_imagej_compatible('./ExampleData/example_labels.tif', l, axes='YX')





# #For now, test run all of them
# # print(fn)
# for i in range(0,len(fn)):
#     print(fn[i])

    
fn = functionNamesFromDir("ROICalcScripts")
# #For now, test run all of them
# # print(fn)
# for i in range(0,len(fn)):
#     print(fn[i])