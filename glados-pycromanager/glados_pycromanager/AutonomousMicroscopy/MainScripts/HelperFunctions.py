import os
import sys
import warnings
import inspect
import importlib
# from stardist import _draw_polygons, export_imagej_rois
import re

# from stardist.models import StarDist2D
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
        if module_name.endswith('.py'):
            # Module path is provided
            loader = importlib.machinery.SourceFileLoader('', module_name) #type:ignore
            module = loader.load_module()
        else:
            module = importlib.import_module(module_name)
        a = hasattr(module, subfunction_name)
        b = callable(getattr(module, subfunction_name))
        return hasattr(module, subfunction_name) and callable(getattr(module, subfunction_name))
    except (ImportError, AttributeError):
        return False
    
# Return all functions that are found in a specific directory
def functionNamesFromDir(dirname):
    #Get the absolute path, assuming that this file will stay in the sister-folder
    absolute_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),dirname)
    #initialise empty array
    functionnamearr = []
    #Loop over all files
    for file in os.listdir(absolute_path):
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
                        if subfunction_exists(f'{absolute_path}\{functionName}.py',singlefunctiondata): #type:ignore
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

#Returns the 'names' of the required kwargs of a function
def reqKwargsFromFunction(functionname):
    #Get all kwarg info
    allkwarginfo = kwargsFromFunction(functionname)
    #Perform a regex match on 'name'
    name_pattern = r"name:\s*(\S+)"
    #Get the names of the req_kwargs (allkwarginfo[0])
    names = re.findall(name_pattern, allkwarginfo[0][0])
    return names

#Returns the 'names' of the optional kwargs of a function
def optKwargsFromFunction(functionname):
    #Get all kwarg info
    allkwarginfo = kwargsFromFunction(functionname)
    #Perform a regex match on 'name'
    name_pattern = r"name:\s*(\S+)"
    #Get the names of the optional kwargs (allkwarginfo[1])
    names = re.findall(name_pattern, allkwarginfo[1][0])
    return names

#Obtain the kwargs from a function. Results in an array with entries
def kwargsFromFunction(functionname):
    try:
        #Check if parent function
        if not '.' in functionname:
            functionMetadata = eval(f'{str(functionname)}.__function_metadata__()')
            #Loop over all entries
            looprange = range(0,len(functionMetadata))
        else: #or specific sub-function
            #get the parent info
            functionparent = functionname.split('.')[0]
            functionMetadata = eval(f'{str(functionparent)}.__function_metadata__()')
            #sub-select the looprange
            loopv = next((index for index in range(0,len(functionMetadata)) if list(functionMetadata.keys())[index] == functionname.split('.')[1]), None)
            looprange = range(loopv,loopv+1) #type:ignore
        name_arr = []
        help_arr = []
        rkwarr_arr = []
        okwarr_arr = []
        loopindex = 0
        for i in looprange:
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
    #Error handling if __function_metadata__ doesn't exist
    except AttributeError:
        rkwarr_arr = []
        okwarr_arr = []
        return f"No __function_metadata__ in {functionname}"
            
    return [rkwarr_arr, okwarr_arr]

#Obtain the help-file and info on kwargs on a specific function
#Optional: Boolean kwarg showKwargs & Boolean kwarg showHelp
def infoFromMetadata(functionname,**kwargs):
    showKwargs = kwargs.get('showKwargs', True)
    showHelp = kwargs.get('showHelp', True)
    try:
        #Check if parent function
        if not '.' in functionname:
            functionMetadata = eval(f'{str(functionname)}.__function_metadata__()')
            finaltext = f"""\
            --------------------------------------------------------------------------------------
            {functionname} contains {len(functionMetadata)} callable functions: {", ".join(str(singlefunctiondata) for singlefunctiondata in functionMetadata)}
            --------------------------------------------------------------------------------------
            """
            #Loop over all entries
            looprange = range(0,len(functionMetadata))
        else: #or specific sub-function
            #get the parent info
            functionparent = functionname.split('.')[0]
            functionMetadata = eval(f'{str(functionparent)}.__function_metadata__()')
            #sub-select the looprange
            loopv = next((index for index in range(0,len(functionMetadata)) if list(functionMetadata.keys())[index] == functionname.split('.')[1]), None)
            looprange = range(loopv,loopv+1) #type:ignore
            finaltext = ""
        name_arr = []
        help_arr = []
        rkwarr_arr = []
        okwarr_arr = []
        loopindex = 0
        for i in looprange:
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
                {name_arr[loopindex][0]} information:
                -------------------------------------------"""
            if showHelp:
                finaltext += f"""
                {help_arr[loopindex]}"""
            if showKwargs:
                finaltext += f"""
                ----------
                Required keyword arguments (kwargs):
                {rkwarr_arr[loopindex]}----------
                Optional keyword arguments (kwargs):
                {okwarr_arr[loopindex]}"""
            finaltext += "\n"
            loopindex+=1
        
        finaltext += "--------------------------------------------------------------------------------------\n"
        #Remove left-leading spaces
        finaltext = "\n".join(line.lstrip() for line in finaltext.splitlines())

        return finaltext
    #Error handling if __function_metadata__ doesn't exist
    except AttributeError:
        return f"No __function_metadata__ in {functionname}"

#Run a function with unknown number of parameters via the eval() method
#Please note that the arg values need to be the string variants of the variable, not the variable itself!
def createFunctionWithArgs(functionname,*args):
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
    return fullstring

#Run a function with unknown number of kwargs via the eval() method
#Please note that the kwarg values need to be the string variants of the variable, not the variable itself!
def createFunctionWithKwargs(functionname,**kwargs):
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
    return fullstring
