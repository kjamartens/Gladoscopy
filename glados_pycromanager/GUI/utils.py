#region imports
import ast
import collections
import datetime
import importlib
import importlib.machinery
import importlib.util
import inspect
import json
import logging
import os
import re
import shutil
import sys
import textwrap
import time
import warnings
import webbrowser
from dataclasses import dataclass, fields
from typing import Any

import appdirs
import markdown
import numpy as np
from pycromanager import Core
from PyQt5.QtCore import QSize, Qt

#Imports for PyQt5 (GUI)
from PyQt5.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPen
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

#TODO: Maybe sharedFunctions need to be in the pip-installed list?
# from sharedFunctions import Shared_data

#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import glados_pycromanager.AutonomousMicroscopy.MainScripts.HelperFunctions
import glados_pycromanager.Core.microscopeInterfaceLayer as MIL
from glados_pycromanager.autonomous import registry as _node_registry
from glados_pycromanager.errors import NodeDispatchError

#endregion

# Phase 7.1/7.2: body moved to `glados_pycromanager.io.appdata`; shim
# kept here for back-compat with one-time DeprecationWarning per call.
import warnings as _shim_warnings_cleanup  # noqa: E402

from glados_pycromanager.io import appdata as _appdata_cleanup  # noqa: E402


def cleanUpTemporaryFiles(mainFolder="./", shared_data=None):
    _shim_warnings_cleanup.warn(
        "cleanUpTemporaryFiles() has moved to glados_pycromanager.io.appdata."
        "cleanUpTemporaryFiles; the GUI.utils re-export is scheduled for "
        "removal in Phase 18.1 of claude_project.md.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _appdata_cleanup.cleanUpTemporaryFiles(mainFolder, shared_data)


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
            # Reuse an already-loaded module to avoid re-executing module-level
            # @register decorators. __file__ may point to a .pyc in __pycache__,
            # so normalise both sides to the source path before comparing.
            abs_path = os.path.abspath(module_name)
            module = None
            for m in sys.modules.values():
                mfile = getattr(m, '__file__', None)
                if not mfile:
                    continue
                if mfile.endswith('.pyc'):
                    try:
                        mfile = importlib.util.source_from_cache(mfile)
                    except (NotImplementedError, ValueError):
                        continue
                if os.path.abspath(mfile) == abs_path:
                    module = m
                    break
            if module is None:
                loader = importlib.machinery.SourceFileLoader('', module_name)  # type:ignore
                module = loader.load_module()
        else:
            module = importlib.import_module(module_name)
        return hasattr(module, subfunction_name) and callable(getattr(module, subfunction_name))
    except (ImportError, AttributeError):
        return False
    

# Plugin node modules (e.g. FFT_im) are registered in sys.modules under their
# full dotted path (glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.FFT_im),
# never under their bare stem -- so the sys.modules.get(stem) fast path below
# always misses for them, and every call falls through to the linear scan.
# That scan is called once per RT-analysis run() invocation (see
# realTimeAnalysis_run -> kwargsFromFunction -> _resolve_node_obj), so with a
# few thousand modules loaded (napari/torch/tensorflow et al. easily import
# that many), one real-time-analysis frame could cost 5000+ rsplit() calls --
# directly observed via Performance Mode as a major CPU cost inside an
# RT-analysis subprocess. Caching the stem->module resolution avoids re-scanning
# sys.modules on every call; reload_all_node_modules() (dev hot-reload) clears
# this cache since it deletes/re-adds the exact sys.modules entries this looks up.
_resolve_node_obj_module_cache: dict[str, object] = {}


def clear_resolve_node_obj_cache() -> None:
    """Invalidate the stem->module cache used by _resolve_node_obj().

    Call this whenever sys.modules entries for node packages are added,
    removed, or replaced (see plugins/discovery.py's reload_all_node_modules).
    """
    _resolve_node_obj_module_cache.clear()
    _NODE_LIVE_CONTEXT_CACHE.clear()


def _resolve_node_obj(name_str):
    """Resolve a dotted node name (e.g. 'BioImageModelZoo' or 'BioImageModelZoo.BioImageModelZoo')
    to the named object without using eval. Looks up the stem in sys.modules."""
    import sys as _sys
    parts = str(name_str).split('.')
    stem = parts[0]
    mod = _sys.modules.get(stem)
    if mod is None:
        mod = _resolve_node_obj_module_cache.get(stem)
    if mod is None:
        for key, m in list(_sys.modules.items()):
            if m is not None and key.rsplit('.', 1)[-1] == stem:
                mod = m
                _resolve_node_obj_module_cache[stem] = m
                break
    if mod is None:
        raise NameError(f"No loaded module with stem '{stem}' (name_str={name_str!r})")
    obj = mod
    for part in parts[1:]:
        obj = getattr(obj, part)
    return obj


def _node_metadata(name_str):
    """Cached ``__function_metadata__()`` dict for a node module (T-G1).

    Thin wrapper over :func:`registry.get_metadata` so every metadata read in
    this module goes through one cache. The returned dict is *shared* — never
    mutate it.
    """
    return _node_registry.get_metadata(name_str)


def _nodeFunctionEntry(functionname):
    """Return the metadata sub-dict of a single node function.

    ``functionname`` is either ``"Module.Function"`` or a bare module stem; a
    bare stem resolves to the module's *first* declared function, which is what
    the blob-and-regex helpers this replaced did (they always regexed entry 0).

    Returns None when the module has no usable metadata for that name, so
    callers degrade to an empty kwarg list exactly as the regex path did.
    """
    try:
        metadata = _node_metadata(functionname)
        parts = str(functionname).split('.')
        if len(parts) > 1:
            return metadata[parts[1]]
        return next(iter(metadata.values()))
    except (AttributeError, TypeError, KeyError, NameError, StopIteration):
        return None


# Return all functions that are found in a specific directory
def functionNamesFromDir(dirname):
    #initialise empty array
    functionnamearr = []
    def _load_module(functionName, file_path):
        """Return the already-loaded module or load it fresh from its file path."""
        import sys
        abs_file = os.path.abspath(file_path)
        for mod in sys.modules.values():
            mfile = getattr(mod, '__file__', None)
            if mfile and os.path.abspath(mfile) == abs_file:
                return mod
        #For files that live inside the glados_pycromanager package tree, prefer
        #importing via their real dotted package path so this shares the same
        #sys.modules entry (and node registration) as glados_pycromanager.plugins.discovery,
        #regardless of which mechanism happens to run first.
        if not os.path.isabs(dirname):
            qualified_name = 'glados_pycromanager.' + dirname.replace('\\', '.').replace('/', '.') + '.' + functionName
            try:
                return importlib.import_module(qualified_name)
            except ImportError:
                pass
        spec = importlib.util.spec_from_file_location(functionName, file_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[functionName] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def addFilesToAbsolutePath(functionnamearr,absolute_path):
        #Loop over all files
        for file in os.listdir(absolute_path):
            #Check if they're .py files
            if file.endswith(".py"):
                #Check that they're not init files or similar
                if not file.startswith("_") and not file == "utils.py" and not file == "utilsHelper.py":
                    #Get the function name
                    functionName = file[:-3]
                    file_path = os.path.join(absolute_path, file)
                    mod = _load_module(functionName, file_path)
                    if mod is None:
                        continue
                    #Get the metadata from this function and from there obtain
                    try:
                        functionMetadata = mod.__function_metadata__()
                        for singlefunctiondata in functionMetadata:
                            #Also check this against the actual sub-routines and raise an error (this should also be present in the __init__ of the folders)
                            subroutineName = f"{functionName}.{singlefunctiondata}"
                            if subfunction_exists(f'{absolute_path}{os.sep}{functionName}.py',singlefunctiondata): #type:ignore
                                functionnamearr.append(subroutineName)
                            else:
                                warnings.warn(f"Warning: {subroutineName} is present in __function_metadata__ but not in the actual file!")
                    #Error handling if __function_metadata__ doesn't exist
                    except AttributeError:
                        #Get all callable subroutines and store those
                        subroutines = []
                        for subroutineName, obj in inspect.getmembers(mod):
                            if function_exists(obj):
                                subroutines.append(subroutineName)
                                functionnamearr.append(subroutineName)
                        #Give the user the warning and the solution
                        warnings.warn(f"Warning: {str(functionName)} does not have the required __function_metadata__ ! All functions that are found in this module are added! They are {subroutines}")
        return functionnamearr
    
    #Get the absolute path, assuming that this file will stay in the sister-folder
    absolute_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),dirname)
    functionnamearr = addFilesToAbsolutePath(functionnamearr,absolute_path)
    
    #Also do this on the app-data folder
    #Try-except clause just if the folder isn't in appdata it shouldn't be an issue
    try:
        additional_folder_name = os.path.join("C:\\Users\\Koen Martens\\AppData\\Local\\UniBonn\\Glados",dirname)
        functionnamearr = addFilesToAbsolutePath(functionnamearr,additional_folder_name)
    except OSError as exc:
        logging.debug('Optional hard-coded AppData path %s unavailable: %s', additional_folder_name, exc)
    
    #return all functions
    return functionnamearr

#Returns the 'names' of the required kwargs of a function
def reqKwargsFromFunction(functionname):
    #Read the (cached) metadata directly - this used to serialise the kwarg
    #dicts into a "key: value" text blob and regex the names back out (T-G1).
    entry = _nodeFunctionEntry(functionname)
    if entry is None:
        return []
    return [kwarg['name'] for kwarg in entry.get('required_kwargs', [])]

#Returns a display name (if available) of an individual kwarg name, from a specific function:
def displayNameFromKwarg(functionname,name):
    #Look through optional args first, then req. kwargs (so that req. kwargs
    #have priority in case something weird is happening).
    entry = _nodeFunctionEntry(functionname)
    if entry is None:
        return name
    displayName = name
    for kwargListName in ('optional_kwargs', 'required_kwargs'):
        for kwarg in entry.get(kwargListName, []):
            if kwarg.get('name') == name:
                displayName = kwarg.get('display_text', name)
    return displayName

#Returns the 'names' of the optional kwargs of a function
def optKwargsFromFunction(functionname):
    #Read the (cached) metadata directly rather than regexing a text blob (T-G1).
    entry = _nodeFunctionEntry(functionname)
    if entry is None:
        return []
    return [kwarg['name'] for kwarg in entry.get('optional_kwargs', [])]

def classKwargValuesFromFittingFunction(functionname, class_type):
    #Get all kwarg info
    allkwarginfo = kwargsFromFunction(functionname)
    derivedClasses = []
    return derivedClasses

#Obtain the kwargs from a function. Results in an array with entries
def kwargsFromFunction(functionname):
    try:
        #Check if parent function
        if not '.' in functionname:
            functionMetadata = _node_metadata(functionname)
            #Loop over all entries
            looprange = range(0,len(functionMetadata))
        else: #or specific sub-function
            #get the parent info
            functionparent = functionname.split('.')[0]
            functionMetadata = _node_metadata(functionparent)
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
            if "optional_kwargs" in functionMetadata[list(functionMetadata.keys())[i]]:
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
    except TypeError:
        #Likely due to trying to run this on an empty folder
        rkwarr_arr = []
        okwarr_arr = []
        return f"Empty __function_metadata__ in {functionname}"
            
    return [rkwarr_arr, okwarr_arr]

def inputFromFunction(functionname):
    try:
        #Check if parent function
        if not '.' in functionname:
            functionMetadata = _node_metadata(functionname)
            #Loop over all entries
            looprange = range(0,len(functionMetadata))
        else: #or specific sub-function
            #get the parent info
            functionparent = functionname.split('.')[0]
            functionMetadata = _node_metadata(functionparent)
            #sub-select the looprange
            loopv = next((index for index in range(0,len(functionMetadata)) if list(functionMetadata.keys())[index] == functionname.split('.')[1]), None)
            looprange = range(loopv,loopv+1) #type:ignore
        
        input_arr = []
        for i in looprange:
            #Not every node declares "input" (e.g. LaserAdjustment) - that used
            #to be a KeyError here, which crashed anything binding a node's
            #visualise kwargs (the only path that does not skipInput).
            input_arr.append(functionMetadata[list(functionMetadata.keys())[i]].get("input", []))
    except AttributeError:
        input_arr = []
        return f"No __function_metadata__ in {functionname}"
    
    return input_arr

def outputFromFunction(functionname):
    try:
        #Check if parent function
        if not '.' in functionname:
            functionMetadata = _node_metadata(functionname)
            #Loop over all entries
            looprange = range(0,len(functionMetadata))
        else: #or specific sub-function
            #get the parent info
            functionparent = functionname.split('.')[0]
            functionMetadata = _node_metadata(functionparent)
            #sub-select the looprange
            loopv = next((index for index in range(0,len(functionMetadata)) if list(functionMetadata.keys())[index] == functionname.split('.')[1]), None)
            looprange = range(loopv,loopv+1) #type:ignore
        
        output_arr = []
        for i in looprange:
            output_arr.append(functionMetadata[list(functionMetadata.keys())[i]].get("output", []))
    except AttributeError:
        output_arr = []
        return f"No __function_metadata__ in {functionname}"
    
    return output_arr
#Obtain the help-file and info on kwargs on a specific function
#Optional: Boolean kwarg showKwargs & Boolean kwarg showHelp
def infoFromMetadata(functionname,**kwargs):
    showKwargs = kwargs.get('showKwargs', True)
    showHelp = kwargs.get('showHelp', True)
    specificKwarg = kwargs.get('specificKwarg', False)
    try:
        skipfinalline = False
        #Check if parent function
        if not '.' in functionname:
            functionMetadata = _node_metadata(functionname)
            finaltext = f"""\
            --------------------------------------------------------------------------------------
            {functionname} contains {len(functionMetadata)} callable functions: {", ".join(str(singlefunctiondata) for singlefunctiondata in functionMetadata)}
            --------------------------------------------------------------------------------------
            """
            #Loop over all entries
            looprange = range(0,len(functionMetadata))
        else: #or specific sub-function
            if specificKwarg == False:
                #get the parent info
                functionparent = functionname.split('.')[0]
                functionMetadata = _node_metadata(functionparent)
                #sub-select the looprange
                loopv = next((index for index in range(0,len(functionMetadata)) if list(functionMetadata.keys())[index] == functionname.split('.')[1]), None)
                looprange = range(loopv,loopv+1) #type:ignore
                finaltext = ""
            else:
                #Get information on a single kwarg
                #get the parent info
                functionparent = functionname.split('.')[0]
                #Get the full function metadata
                functionMetadata = _node_metadata(functionparent)
                #Get the help string of a single kwarg
                
                #Find the help text of a single kwarg
                helptext = 'No help text set'
                #Look over optional kwargs
                if "optional_kwargs" in functionMetadata[functionname.split('.')[1]]:
                    for k in range(0,len(functionMetadata[functionname.split('.')[1]]["optional_kwargs"])):
                        if functionMetadata[functionname.split('.')[1]]["optional_kwargs"][k]['name'] == specificKwarg:
                            helptext = functionMetadata[functionname.split('.')[1]]["optional_kwargs"][k]['description']
                #look over required kwargs
                for k in range(0,len(functionMetadata[functionname.split('.')[1]]["required_kwargs"])):
                    if functionMetadata[functionname.split('.')[1]]["required_kwargs"][k]['name'] == specificKwarg:
                        helptext = functionMetadata[functionname.split('.')[1]]["required_kwargs"][k]['description']
                # for distribution kwarg
                if specificKwarg == 'dist_kwarg':
                    helptext = functionMetadata[functionname.split('.')[1]]["dist_kwarg"]['description']
                # for time fitting kwarg
                if specificKwarg == 'time_kwarg':
                    helptext = functionMetadata[functionname.split('.')[1]]["time_kwarg"]['description']
                finaltext = helptext
                skipfinalline = True
                looprange = range(0,0)
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
        
        if not skipfinalline:
            finaltext += "--------------------------------------------------------------------------------------\n"
        #Remove left-leading spaces
        finaltext = "\n".join(line.lstrip() for line in finaltext.splitlines())

        return finaltext
    #Error handling if __function_metadata__ doesn't exist
    except AttributeError:
        return f"No __function_metadata__ in {functionname}"

#Build a display-only string for "Module.Function(arg1, arg2, ...)".
#Phase 9.6: renamed from createFunctionWithArgs. The production call
#path no longer eval's these strings — use
#registry.dispatch_from_eval_text instead. Old name preserved as a
#deprecated alias until the next major release.
def createFunctionWithArgs_str_for_display(functionname,*args):
    fullstring = functionname+"."+functionname+"("
    idloop = 0
    for arg in args:
        if idloop>0:
            fullstring = fullstring+","
        fullstring = fullstring+str(arg)
        idloop+=1
    fullstring = fullstring+")"
    return fullstring


def createFunctionWithArgs(functionname,*args):
    """Deprecated. Use ``createFunctionWithArgs_str_for_display``."""
    import warnings
    warnings.warn(
        "utils.createFunctionWithArgs is a display-only helper now; "
        "eval'ing its result is unsafe — use "
        "glados_pycromanager.autonomous.registry.dispatch_from_eval_text instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return createFunctionWithArgs_str_for_display(functionname, *args)


#Build a display-only string for "Module.Function(kw1=v1, kw2=v2, ...)".
#Phase 9.6: renamed from createFunctionWithKwargs. Same notes as above.
def createFunctionWithKwargs_str_for_display(functionname,**kwargs):
    fullstring = functionname+"("
    idloop = 0
    for key, value in kwargs.items():
        if idloop>0:
            fullstring = fullstring+","
        fullstring = fullstring+str(key)+"="+str(value)
        idloop+=1
    fullstring = fullstring+")"
    return fullstring


def createFunctionWithKwargs(functionname,**kwargs):
    """Deprecated. Use ``createFunctionWithKwargs_str_for_display``."""
    import warnings
    warnings.warn(
        "utils.createFunctionWithKwargs is a display-only helper now; "
        "eval'ing its result is unsafe — use "
        "glados_pycromanager.autonomous.registry.dispatch_from_eval_text instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return createFunctionWithKwargs_str_for_display(functionname, **kwargs)


def defaultValueFromKwarg(functionname,kwargname):
    #Check if the function has a 'default' entry for the specific kwarg. If not, return None. Otherwise, return the default value.
    
    defaultEntry=None
    functionparent = functionname.split('.')[0]
    #Get the full function metadata
    functionMetadata = _node_metadata(functionparent)
    if 'optional_kwargs'  in functionMetadata[functionname.split('.')[1]]:
        for k in range(0,len(functionMetadata[functionname.split('.')[1]]["optional_kwargs"])):
            if functionMetadata[functionname.split('.')[1]]["optional_kwargs"][k]['name'] == kwargname:
                #check if this has a default value:
                if 'default' in functionMetadata[functionname.split('.')[1]]["optional_kwargs"][k]:
                    defaultEntry = functionMetadata[functionname.split('.')[1]]["optional_kwargs"][k]['default']
    #look over required kwargs
    for k in range(0,len(functionMetadata[functionname.split('.')[1]]["required_kwargs"])):
        if functionMetadata[functionname.split('.')[1]]["required_kwargs"][k]['name'] == kwargname:
            #check if this has a default value:
            if 'default' in functionMetadata[functionname.split('.')[1]]["required_kwargs"][k]:
                defaultEntry = functionMetadata[functionname.split('.')[1]]["required_kwargs"][k]['default']
    
    logging.debug(f"Default value for {functionname} - {kwargname} is {defaultEntry}")
    return defaultEntry

def motherFunctionFromFunctionName(functionname):
    return functionname.split('.')[0]

def daughterFunctionsFromFunctionName(functionname):
    return functionname.split('.')[1]

def createGridFromFunction(functionname):
    #Idea: get all arg and kwarg info, and create a QGridLayout that contains these info, and line-edits, or dropdowns, or checkboxes, etc.
    
    #Create a gridLayout with labels and line-edits, dropdowns or checkboxes based on the function's metadata:
    motherFunctionMetadata = _node_metadata(motherFunctionFromFunctionName(functionname))
    functionMetadata = motherFunctionMetadata[daughterFunctionsFromFunctionName(functionname)]
    gridLayout = QGridLayout()
    current_row = 0
    for k in range(0,len(functionMetadata["required_kwargs"])):
        gridLayout.addWidget(QLabel(functionMetadata["required_kwargs"][k]["name"]),current_row,0)
        #First check if there is a type key in this req kwargs metadata:
        if "type" in functionMetadata["required_kwargs"][k]:
            if functionMetadata["required_kwargs"][k]["type"] == "bool":
                checkbox = QCheckBox()
                defaultValue = defaultValueFromKwarg(functionname,functionMetadata["required_kwargs"][k])
                if defaultValue != None:
                    checkbox.setChecked(defaultValue)
                gridLayout.addWidget(checkbox,current_row,1)
            if functionMetadata["required_kwargs"][k]["type"] == "int" or functionMetadata["required_kwargs"][k]["type"] == "float":
                lineEdit = QLineEdit()
                gridLayout.addWidget(lineEdit,current_row,1)
            if functionMetadata["required_kwargs"][k]["type"] == "str":
                lineEdit = QLineEdit()
                gridLayout.addWidget(lineEdit,current_row,1)
        else: #if there is no type key, assume it is a string
            lineEdit = QLineEdit()
            gridLayout.addWidget(lineEdit,current_row,1)
        current_row+=1
    for k in range(0,len(functionMetadata["optional_kwargs"])):
        gridLayout.addWidget(QLabel(functionMetadata["optional_kwargs"][k]["name"]),current_row,0)
        if "type" in functionMetadata["optional_kwargs"][k]:
            if functionMetadata["optional_kwargs"][k]["type"] == "bool":
                checkbox = QCheckBox()
                defaultValue = defaultValueFromKwarg(functionname,functionMetadata["optional_kwargs"][k])
                if defaultValue != None:
                    checkbox.setChecked(defaultValue)
                gridLayout.addWidget(checkbox,current_row,1)
            if functionMetadata["optional_kwargs"][k]["type"] == "int" or functionMetadata["optional_kwargs"][k]["type"] == "float":
                lineEdit = QLineEdit()
                defaultValue = defaultValueFromKwarg(functionname,functionMetadata["optional_kwargs"][k])
                if defaultValue != None:
                    lineEdit.setText(str(defaultValue))
                gridLayout.addWidget(lineEdit,current_row,1)
            else: #if there is no type key, assume it is a string
                lineEdit = QLineEdit()
                gridLayout.addWidget(lineEdit,current_row,1)
            current_row+=1
    return gridLayout





def displayNamesFromFunctionNames(functionName, polval):
    displaynames = []
    functionName_to_displayName_map = []
    for function in functionName:
        #Extract the mother function name - before the period:
        subroutineName = function.split('.')[0]
        singlefunctiondata = function.split('.')[1]
        #Check if the subroutine has a display name - if so, use that, otherwise use the subroutineName
        functionMetadata = _node_metadata(subroutineName)
        if 'display_name' in functionMetadata[singlefunctiondata]:
            displayName = functionMetadata[singlefunctiondata]['display_name']
            #Add the polarity info between brackets if required
            if polval != '':
                displayName += " ("+polval+")"
        else:
            displayName = subroutineName+': '+singlefunctiondata
            #Add the polarity info between brackets if required
            if polval != '':
                displayName += " ("+polval+")"
        displaynames.append(displayName)
        functionName_to_displayName_map.append((displayName,function))
        
    #Check for ambiguity in both columns:
    # if not len(np.unique(list(set(functionName_to_displayName_map)))) == len(list(itertools.chain.from_iterable(functionName_to_displayName_map))):
    #     raise Exception('Ambiguous display names in functions!! Please check all function names and display names for uniqueness!')
        
    return displaynames, functionName_to_displayName_map

def functionNameFromDisplayName(displayname,map):
    for pair in map:
        if pair[0] == displayname:
            return pair[1]
        
def typeFromKwarg(functionname,kwargname):
    #Check if the function has a 'type' entry for the specific kwarg. If not, return None. Otherwise, return the type value.
    typing=None
    try:
        functionparent = functionname.split('.')[0]
        #Get the full function metadata
        functionMetadata = _node_metadata(functionparent)
        for k in range(0,len(functionMetadata[functionname.split('.')[1]]["optional_kwargs"])):
            if functionMetadata[functionname.split('.')[1]]["optional_kwargs"][k]['name'] == kwargname:
                #check if this has a default value:
                if 'type' in functionMetadata[functionname.split('.')[1]]["optional_kwargs"][k]:
                    typing = functionMetadata[functionname.split('.')[1]]["optional_kwargs"][k]['type']
        #look over required kwargs
        for k in range(0,len(functionMetadata[functionname.split('.')[1]]["required_kwargs"])):
            if functionMetadata[functionname.split('.')[1]]["required_kwargs"][k]['name'] == kwargname:
                #check if this has a default value:
                if 'type' in functionMetadata[functionname.split('.')[1]]["required_kwargs"][k]:
                    typing = functionMetadata[functionname.split('.')[1]]["required_kwargs"][k]['type']

    except (KeyError, IndexError, TypeError, AttributeError):
        typing=None
    return typing

def createValueEditWidget(functionname,kwargname):
    """
    Build the 'Value'-mode widget for a kwarg. Bool-typed kwargs (declared as "type": bool
    in __function_metadata__) get a QCheckBox instead of a free-text QLineEdit; everything
    else is unchanged. The object name (LineEdit#function#kwarg) is kept identical for both
    widget kinds, since hideAdvVariables()/getFunctionEvalTextFromCurrentData_* only ever key
    off that name, not the widget class - see docs/rt_analysis_parameters.md.
    """
    if typeFromKwarg(functionname,kwargname) == bool:
        widget = QCheckBox()
    else:
        widget = QLineEdit()
    widget.setObjectName(f"LineEdit#{functionname}#{kwargname}")
    return widget

def wireValueEditWidget(line_edit,defaultValue):
    """
    Apply the default value and hook up the change-signal for a widget built by
    createValueEditWidget(), branching on whether it's a QCheckBox (bool) or QLineEdit (everything else).
    """
    if isinstance(line_edit,QCheckBox):
        if defaultValue is not None:
            if isinstance(defaultValue,str):
                line_edit.setChecked(defaultValue.strip().lower() in ('true','1'))
            else:
                line_edit.setChecked(bool(defaultValue))
        line_edit.stateChanged.connect(lambda state,line_edit=line_edit: changeDataVarUponKwargChange(line_edit))
    else:
        if defaultValue is not None:
            line_edit.setText(str(defaultValue))
        line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))

def layout_changedDropdown(curr_layout,current_dropdown,displayNameToFunctionNameMap,parent=None):
    #Called whenever the dropdown is changed, hides everything and shows selectively only the chosen dropdown
    if current_dropdown == None:
        return
    item_text = current_dropdown.currentText()
    if item_text is not None and item_text != '':
        #Get the kw-arguments from the current dropdown.
        current_selected_function = functionNameFromDisplayName(item_text,displayNameToFunctionNameMap)
        #Hides everything except current dropdown selected
        resetLayout(curr_layout,current_selected_function)
        #Update the layout
        curr_layout.update()
        
        #Force-set the current selected function
        
        currentSelectedFunctionReadable = None
        try:
            for entry in curr_layout.parent().parent().currentData['__displayNameFunctionNameMap__']:
                if entry[1] == current_selected_function:
                    currentSelectedFunctionReadable = entry[0]
            curr_layout.parent().parent().currentData['__selectedDropdownEntryAnalysis__'] = currentSelectedFunctionReadable
        except (AttributeError, KeyError):
            # raised when called directly from the GUI rather than nodz
            pass
        
        #Show/hide varialbes/advanced lineedits and such
        for i in range(curr_layout.count()):
            item = curr_layout.itemAt(i)
            if not isinstance(item,QSpacerItem):
                if item.widget() is not None:
                    child = item.widget()
                    if 'ComboBoxSwitch#'+current_selected_function in child.objectName():
                        # logging.debug(f"1Going to run hideAdvVariables with {child.objectName()}")
                        curr_layout.update()
                        hideAdvVariables(child,current_selected_function=current_selected_function)
                else:
                    for index2 in range(item.count()):
                        widget_sub_item = item.itemAt(index2)
                        child = widget_sub_item.widget()
                        if 'ComboBoxSwitch#'+current_selected_function in child.objectName():
                            # logging.debug(f"2Going to run hideAdvVariables with {child.objectName()}")
                            curr_layout.update()
                            hideAdvVariables(child,current_selected_function=current_selected_function)
                        
        
        
        # parentObject = curr_layout.parent().parent()
        # currentSelectedFunction = None
        # for entry in parentObject.currentData['__displayNameFunctionNameMap__']:
        #     if entry[0] == parentObject.currentData['__selectedDropdownEntryAnalysis__']:
        #         currentSelectedFunction = entry[1]
        #                 if 'ComboBoxSwitch#'+currentSelectedFunction in child.objectName():
        #                     hideAdvVariables(child)

def attemptToEvaluateVariables(value,nodzInfo):
    """
    Idea: check if 'value' can be assessed as a variable (abc@def) or as an advanced thing ({abc@def}+'t'+{abc2#def2}). If so, return the assessed value, else, return the initial value.
    """
    try:
        #Check for exactly a single variable abc@def, no spaces etc before/after
        checkExactlySingleVariable = bool(re.match("[a-zA-Z0-9._%+-]+@[a-zA-Z0-9._%+-]+",value))
        checkAdvanced = bool(re.match("{[a-zA-Z0-9._%+-]+@[a-zA-Z0-9._%+-]+}",value))
        if checkExactlySingleVariable:
            try:
                finalVal = nodz_evaluateVar(value,nodzInfo)
            except (KeyError, AttributeError, TypeError, ValueError):
                finalVal = value
        elif checkAdvanced:
            try:
                finalVal = nodz_evaluateAdv(value,nodzInfo)
            except (KeyError, AttributeError, TypeError, ValueError, SyntaxError, NameError):
                finalVal = value
        else:
            finalVal = value
    except TypeError: #if value is not a string at all, return the initial value
        finalVal = value
    
    return finalVal

def nodz_setVariableToValue(variable,value,nodzInfo):
    """
    The nodz_setVariableToValue function is used to set a global variable to a value.
    
    Args:
        variable: Specify the variable you want to set
        value: Set the value of the variable
        nodzInfo: Pass information between functions
    """
    originNodeName = variable.split('@')[1]
    variableName = variable.split('@')[0]
    
    if originNodeName != 'Global':
        logging.error('Attempting to set non-Global var. This is not allowed')
    else:
        #Add typing to an array if not yet.
        if type(nodzInfo.globalVariables[variableName]['type']) == type:
            nodzInfo.globalVariables[variableName]['type'] = [nodzInfo.globalVariables[variableName]['type']]
        
        if type(value) in nodzInfo.globalVariables[variableName]['type']:
            nodzInfo.globalVariables[variableName]['data'] = value
            logging.debug(f"Set global variable {variableName} to {value}")
        else:
            try:
                if type(eval(value)) in nodzInfo.globalVariables[variableName]['type']:
                    nodzInfo.globalVariables[variableName]['data'] = eval(value)
                    logging.debug(f"Set global variable {variableName} to {eval(value)}")
            except (SyntaxError, NameError, ValueError, TypeError, KeyError, AttributeError) as exc:
                logging.error('Type mismatch in variable setting! %s and %s (%s)', variableName, value, exc)
    return

def nodz_evaluateVar(varName,nodzInfo):
    varData = None
    if '@' in varName:
        originNodeName = varName.split('@')[1]
        variableName = varName.split('@')[0]
        
        #Find the correct node
        if originNodeName == 'Global':
            varData = nodzInfo.globalVariables[variableName]['data']
        elif originNodeName == 'Core':
            varData = nodzInfo.coreVariables[variableName]['data']
        else:
            #Done it like this to have access to kwargvalue if needed (not retported right now)
            nodeDict = createNodeDictFromNodes(nodzInfo.nodes)
            kwargvalue = "nodeDict['"+originNodeName+"'].variablesNodz['"+variableName+"']['data']"
        
            varData = eval(kwargvalue)
        
    return varData

def nodz_evaluateAdv(varName,nodzInfo,skipEval=False):
    if '@' in varName and '{' in varName and '}' in varName:
        nodeDict = createNodeDictFromNodes(nodzInfo.nodes)
        #Find a regex like this:
        import re
        matches = re.finditer("{[a-zA-Z0-9._%+-]+@[a-zA-Z0-9._%+-]+}",varName)
        #Find all the matches
        calculatable = True
        #First check the typing (i.e. calculatable or not)
        for match in matches:
            startpos = match.regs[0][0]
            endpos = match.regs[0][1]
            foundstring = varName[startpos:endpos]
            #Remove the curly braces
            foundstring_data = foundstring[1:-1]
            #run getting the data of this match
            try:
                #Assuming string
                if foundstring_data.split('@')[1] == 'Global':
                    if isinstance(nodzInfo.globalVariables[foundstring_data.split('@')[0]]['type'],type):
                        nodzInfo.globalVariables[foundstring_data.split('@')[0]]['type'] = [nodzInfo.globalVariables[foundstring_data.split('@')[0]]['type']]
                    typev = nodzInfo.globalVariables[foundstring_data.split('@')[0]]['type'][0]
                elif foundstring_data.split('@')[1] == 'Core':
                    if isinstance(nodzInfo.coreVariables[foundstring_data.split('@')[0]]['type'],type):
                        nodzInfo.coreVariables[foundstring_data.split('@')[0]]['type'] = [nodzInfo.coreVariables[foundstring_data.split('@')[0]]['type']]
                    typev = nodzInfo.coreVariables[foundstring_data.split('@')[0]]['type'][0]
                else:
                    typev = nodeDict[foundstring_data.split('@')[1]].variablesNodz[foundstring_data.split('@')[0]]['type'][0]
                #Check if it's calculatable
                if typev not in [int, float, np.ndarray]:
                    calculatable = False
            except KeyError:
                typev = None
                calculatable = False
                
        updating_string = varName
        try:
            matches = re.finditer("{[a-zA-Z0-9._%+-]+@[a-zA-Z0-9._%+-]+}",varName)
            #Now check the data
            for match in matches:
                startpos = match.regs[0][0]
                endpos = match.regs[0][1]
                foundstring = varName[startpos:endpos]
                #Remove the curly braces
                foundstring_data = foundstring[1:-1]
                #run getting the data of this match
                #Assuming string
                if foundstring_data.split('@')[1] == 'Global':
                    data = nodzInfo.globalVariables[foundstring_data.split('@')[0]]['data']
                    typev = nodzInfo.globalVariables[foundstring_data.split('@')[0]]['type'][0]
                elif foundstring_data.split('@')[1] == 'Core':
                    data = nodzInfo.coreVariables[foundstring_data.split('@')[0]]['data']
                    typev = nodzInfo.coreVariables[foundstring_data.split('@')[0]]['type'][0]
                else:
                    data = str(nodeDict[foundstring_data.split('@')[1]].variablesNodz[foundstring_data.split('@')[0]]['data'])
                    typev = nodeDict[foundstring_data.split('@')[1]].variablesNodz[foundstring_data.split('@')[0]]['type'][0]
                
                #Replace this in the updating_string
                if calculatable: #if calculatable
                    try:
                        updating_string = updating_string.replace(foundstring,""+data+"")
                    except TypeError:
                        updating_string = updating_string.replace(foundstring,""+str(data)+"")
                else: #uncalculatable, add as string
                    try:
                        updating_string = updating_string.replace(foundstring,""+data+"")
                    except TypeError:
                        updating_string = updating_string.replace(foundstring,""+str(data)+"")
        except KeyError:
            pass
        #Replace backslashes since they're escapechars
        updating_string_backslash = updating_string.replace('\\','\\\\')
        
        if skipEval:
            finalData = updating_string_backslash
            return finalData
        else:
            try:
                finalData = eval(updating_string_backslash)
            except (SyntaxError, NameError, ValueError, TypeError, AttributeError) as exc:
                logging.error('Error when assessing adv variable %s: %s (%s)', varName, updating_string_backslash, exc)
                finalData = None
            return finalData
    else:
        #If not a true advanced, try, in turn, if it's int, if it's float, and if it can be evaluated as a var.
        try:
            varNameN = int(varName)
        except (ValueError, TypeError):
            try:
                varNameN = float(varName)
            except (ValueError, TypeError):
                try:
                    varNameN = nodz_evaluateVar(varName,nodzInfo)
                    logging.warning(f"Wrong syntax for advanced variable [but seems to be a variable instead]! Details: {varName} - interpreting as variable")
                except (KeyError, AttributeError, TypeError, ValueError, NameError):
                    logging.error('Wrong syntax for advanced variable! Details: %s - interpreting as value', varName)
                    varNameN = varName
        return varNameN

def nodz_dataFromGeneralAdvancedLineEditDialog(relevantData,nodzInfo,dontEvaluate=False):
    allData = {}
    
    uniqueVars = []
    for entry in relevantData:
        if len(entry.split('#')) == 3:
            newEntry = entry.split('#')[2]
            if newEntry not in uniqueVars:
                uniqueVars.append(entry.split('#')[2])
    
    
    for var in uniqueVars:
        # if 'ComboBoxSwitch#' in entry:
        # print(entry)
        #See if we have any of the ComboBox# objectnames:
        lineEditName = 'LineEdit'
        valueVarOrAdv = 'Value'
        for entry in relevantData:
            if 'ComboBoxSwitch#' in entry and '#'+var in entry:
                valueVarOrAdv = relevantData[entry]
                kwargName = entry.split('#')[2]
                if valueVarOrAdv == 'Value':
                    lineEditName = 'LineEdit'
                elif valueVarOrAdv == 'Variable':   
                    lineEditName = 'LineEditVariable'
                elif valueVarOrAdv == 'Advanced':
                    lineEditName = 'LineEditAdv'
        
        finalValue = None
        for entry in relevantData:
            if lineEditName+'#' in entry and '#'+var in entry:
                finalValue = relevantData[entry]

        if valueVarOrAdv == 'Variable':
            evaluatedVar = nodz_evaluateVar(finalValue,nodzInfo)
        elif valueVarOrAdv == 'Advanced':
            evaluatedVar = nodz_evaluateAdv(finalValue,nodzInfo,skipEval = dontEvaluate)
        else:
            evaluatedVar = finalValue
        allData[var] = [evaluatedVar,finalValue,valueVarOrAdv]

    return allData


# Phase 7.3: bodies moved to `glados_pycromanager.ui.widgets.builders`.
# Re-exported here so existing `utils.findIconFolder(...)` calls keep
# working unchanged. Phase 18.1 deletes this shim.
from glados_pycromanager.ui.widgets.builders import (  # noqa: F401
    findIconFolder,
    setWarningErrorInfoIcon,
)

def get_xy_position(core = None,shared_data=None):
    """
    Get the stage XY position, which needs to be handled differently if it's JAVA or Python backend
    """
    position = shared_data.MILcore.get_xy_position()
    
    return position

class XYGridManager:
    """  
    #Idea of XY grid: have methods to create a pop-up dialog, where users can set up the grid (top), setting up top/bottom/left/right/center and specifiy overlap. This then also includes a grid-flow (bottom) with options betwen e.g. normal grid, diagonal grid, spiral grid, etc
    #The class both includes the settings, the positions, and the GUI
    """
    def __init__(self, core = None, parent=None):
        """ 
        Initialisation of the grid manager
        """
        #Initialise with empty positions.
        self.parent=parent
        self.core = core
        self.pos_top_left = [np.nan,np.nan]
        self.pos_top_right = [np.nan,np.nan]
        self.pos_bottom_left = [np.nan,np.nan]
        self.pos_bottom_right = [np.nan,np.nan]
        self.pos_center = [np.nan,np.nan]
        self.pos_overlap_um = 0
        self.pos_overlap_px = 0
        self.pos_overlap_pct = 0
        self.pos_overlap_choice = 'um' #'um' or 'px' or 'pct'
        
        self.pos_overlap = [0,0]
        self.pos_choice = 'center' #'center' or 'corners', depends if grid is created from the center or from the corners
        
        self.grid_flow_type = 'hor_normal' #atm, 'hor_normal', 'hor_snake', 'ver_normal', 'ver_snake'
        self.grid_n_rows = 1
        self.grid_n_cols = 1
        
        self.gridEntries = np.array([[self.core.get_xy_position()[0],self.core.get_xy_position()[1]]])
    
    def openGUI(self):
        """ 
        Create a GUI that allows for setting of the grid and flow
        """
        
        #Create a QDialog with OK/Cancel button:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QDialog, QDialogButtonBox
        
        self.dialog = QDialog()
        self.dialog.setWindowTitle("XY Grid Setup")
        
        #Create a QGridLayout:
        layout = QGridLayout()
        
        self.groupBoxGridSetup = QGroupBox("Grid Setup")
        #Initialise the GridSetup
        self.gridlayoutGridSetup = QGridLayout()
        self.groupBoxGridSetup.setLayout(self.gridlayoutGridSetup)
        
        #Add a bunch of buttons:
        self.buttonTopLeft = QPushButton("Set Top Left")
        self.buttonTopRight = QPushButton("Set Top Right")
        self.buttonBottomLeft = QPushButton("Set Bottom Left")
        self.buttonBottomRight = QPushButton("Set Bottom Right")
        self.buttonCenter = QPushButton("Grid from Center")
        
        self.overlapLabel = QLabel("Overlap: ")
        self.overlapEditField = QLineEdit("0")
        self.overlapEditField.textChanged.connect(self.overlapTextChanged)
        #Only accept numbers in this lineedit:
        from PyQt5.QtGui import QDoubleValidator
        self.overlapEditField.setValidator(QDoubleValidator())
        self.overlapDropDown = QComboBox()
        #Add choice of um, px, and %:
        self.overlapDropDown.addItems(["um", "px", "%"])
        self.overlapDropDown.currentIndexChanged.connect(self.overlapDropDownChanged)
        self.overlapDropDown.setCurrentIndex(0)
        
        #Add these overlapLabel/EditField/Dropdown in a QHBox:
        self.overlapHBox = QHBoxLayout()
        self.overlapHBox.addWidget(self.overlapLabel)
        self.overlapHBox.addWidget(self.overlapEditField)
        self.overlapHBox.addWidget(self.overlapDropDown)
        
        #Add a label which will hold info on the selected grid (i.e. number of FoVs, total size):
        self.gridInfoLabel = QLabel("Total Grid: NaN")
        
        #Add a bunch of uneditable text entries
        self.setPosTopLeft = QLabel("NaN")
        self.setPosTopLeft.setAlignment(Qt.AlignCenter)
        self.setPosTopRight = QLabel("NaN")
        self.setPosTopRight.setAlignment(Qt.AlignCenter)
        self.setPosBottomLeft = QLabel("NaN")
        self.setPosBottomLeft.setAlignment(Qt.AlignCenter)
        self.setPosBottomRight = QLabel("NaN")
        self.setPosBottomRight.setAlignment(Qt.AlignCenter)
        self.setPosCenter = QLabel("NaN")
        self.setPosCenter.setAlignment(Qt.AlignCenter)
        
        #Add callbacks:
        
        self.buttonCenter.clicked.connect(lambda: self.createGridFromCenterRun())
        self.buttonTopLeft.clicked.connect(lambda: self.setPositionText("pos_top_left"))
        self.buttonTopRight.clicked.connect(lambda: self.setPositionText("pos_top_right"))
        self.buttonBottomLeft.clicked.connect(lambda: self.setPositionText("pos_bot_left"))
        self.buttonBottomRight.clicked.connect(lambda: self.setPositionText("pos_bot_right"))
        
        #Add them:
        self.gridlayoutGridSetup.addWidget(self.buttonTopLeft,0,0)
        self.gridlayoutGridSetup.addWidget(self.buttonTopRight,0,2)
        self.gridlayoutGridSetup.addWidget(self.buttonBottomLeft,3*2,0)
        self.gridlayoutGridSetup.addWidget(self.buttonBottomRight,3*2,2)
        self.gridlayoutGridSetup.addWidget(self.buttonCenter,3*1,1)
        
        self.gridlayoutGridSetup.addWidget(self.setPosTopLeft,0*3+1,0)
        self.gridlayoutGridSetup.addWidget(self.setPosTopRight,0*3+1,2)
        self.gridlayoutGridSetup.addWidget(self.setPosBottomLeft,3*2+1,0)
        self.gridlayoutGridSetup.addWidget(self.setPosBottomRight,3*2+1,2)
        self.gridlayoutGridSetup.addWidget(self.setPosCenter,3*1+1,1)
        
        #Add the self.overlapHBox stretched below:
        self.gridlayoutGridSetup.addLayout(self.overlapHBox,3*3+1,0,1,3)
        #Add self.gridInfoLabel stretched below:
        self.gridlayoutGridSetup.addWidget(self.gridInfoLabel,3*3+2,0,1,3)
        
        
        self.groupBoxGridFlow = QGroupBox("Grid Flow")
        #Add a gridLayout to this groupbox:
        self.gridlayoutGridFlow = QGridLayout()
        self.groupBoxGridFlow.setLayout(self.gridlayoutGridFlow)
        
        self.iconFolder = findIconFolder()
        if not os.path.exists(self.iconFolder):
            #Find the iconPath folder
            if os.path.exists('./glados_pycromanager/GUI/Icons/General_Start.png'):
                self.iconFolder = './glados_pycromanager/GUI/Icons/'
            elif os.path.exists('./glados-pycromanager/glados_pycromanager/GUI/Icons/General_Start.png'):
                self.iconFolder = './glados-pycromanager/glados_pycromanager/GUI/Icons/'
            else:
                self.iconFolder = ''
                
        iconSize = 64
        self.rb_horNorm = QRadioButton("")
        self.rb_horNorm.setIcon(QIcon(self.iconFolder+os.sep+"gridHorNorm.png"))
        self.rb_horNorm.setIconSize(QSize(iconSize,iconSize))
        self.rb_horNorm.setChecked(True)
        self.rb_horNorm.toggled.connect(self.gridFlowChanged)

        self.rb_horSnake = QRadioButton("")
        self.rb_horSnake.setIcon(QIcon(self.iconFolder+os.sep+"gridHorSnake.png"))
        self.rb_horSnake.setIconSize(QSize(iconSize,iconSize))
        self.rb_horSnake.toggled.connect(self.gridFlowChanged)
        
        self.rb_verNorm = QRadioButton("")
        self.rb_verNorm.setIcon(QIcon(self.iconFolder+os.sep+"gridVerNorm.png"))
        self.rb_verNorm.setIconSize(QSize(iconSize,iconSize))
        self.rb_verNorm.toggled.connect(self.gridFlowChanged)

        self.rb_verSnake = QRadioButton("")
        self.rb_verSnake.setIcon(QIcon(self.iconFolder+os.sep+"gridVerSnake.png"))
        self.rb_verSnake.setIconSize(QSize(iconSize,iconSize))
        self.rb_verSnake.toggled.connect(self.gridFlowChanged)

        # Add these to your layout
        self.gridlayoutGridFlow.addWidget(self.rb_horNorm,0,0)
        self.gridlayoutGridFlow.addWidget(self.rb_horSnake,0,1)
        self.gridlayoutGridFlow.addWidget(self.rb_verNorm,1,0)
        self.gridlayoutGridFlow.addWidget(self.rb_verSnake,1,1)
        
        
        #Add a group box to the layout:
        layout.addWidget(self.groupBoxGridSetup,0,0)
        layout.addWidget(self.groupBoxGridFlow,1,0)
        #Add a button box
        
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        
        layout.addWidget(self.buttonBox,3,0)
        self.dialog.setLayout(layout)
        
        self.dialog.exec_()
        
        pass

    def gridFlowChanged(self):
        """
        Callback if the radio button of grid flow is changed
        """
        if self.rb_horNorm.isChecked():
            self.grid_flow_type = "hor_normal"
        elif self.rb_horSnake.isChecked():
            self.grid_flow_type = "hor_snake"
        elif self.rb_verNorm.isChecked():
            self.grid_flow_type = "ver_normal"
        elif self.rb_verSnake.isChecked():
            self.grid_flow_type = "ver_snake"
        else:
            #Default back to this
            self.grid_flow_type = "horNorm"
        self.updateGridInfo()

    def overlapTextChanged(self):
        """
        Function which runs if the overlap text is changed. Basically sets the correct pos_overlap_um, pos_overlap_px, pos_overlap_pct
        """
        #Get the text of the overlapEditField:
        text = self.overlapEditField.text()
        if self.overlapDropDown.currentText() == "um":
            self.pos_overlap_um = float(text)
        elif self.overlapDropDown.currentText() == "px":
            self.pos_overlap_px = float(text)
        elif self.overlapDropDown.currentText() == "%":
            self.pos_overlap_pct = float(text)
        
        self.updateGridInfo()

    def overlapDropDownChanged(self):
        """
        Function which runs if the overlap dropdown is changed. Sets the correct pos_overlap_um, pos_overlap_px, pos_overlap_pct
        """
        #Get the current text of the dropdown:
        text = self.overlapDropDown.currentText()
        #Set text back down to the edit field:
        if text == "um":
            self.overlapEditField.setText(str(self.pos_overlap_um))
        elif text == "px":
            self.overlapEditField.setText(str(self.pos_overlap_px))
        elif text == "%":
            self.overlapEditField.setText(str(self.pos_overlap_pct))
            
        self.updateGridInfo()

    def createGridFromCenterRun(self):
        """
        Calldown to make a create-grid-from-center popup box.
        """
        popupbox = createGridFromCenterPopUpBox(parent=self)
        popupbox.getPopup().exec_()
        self.setPositionText("pos_center")

    def updateGridInfo(self):
        """
        General function to update grid info - determines from the current class what the grid info should be, and stores this as self.gridEntries
        """
        if self.core.get_pixel_size_um() != 0:
            corePxSize = self.core.get_pixel_size_um()
        else:
            logging.error('Pixel size in MM set to 1, probably not set properly in MicroManager, please set this!')
            corePxSize = 1
        # Width/height are each a get_roi() round trip to the microscope core (a
        # real Java-bridge cost on the PYCROMANAGER_JAVA backend). The loops below
        # previously called get_image_width()/get_image_height() up to 4x per grid
        # tile; cache them once here since the ROI doesn't change during grid layout.
        imgWidthUm = self.core.get_image_width() * corePxSize
        imgHeightUm = self.core.get_image_height() * corePxSize

        #Update self.pos_overlap to contain the current value in um:
        text = self.overlapEditField.text()
        if self.overlapDropDown.currentText() == "um":
            self.pos_overlap = [float(text),float(text)]
        elif self.overlapDropDown.currentText() == "px":
            self.pos_overlap = [float(text)*corePxSize,float(text)*corePxSize]
        elif self.overlapDropDown.currentText() == "%":
            self.pos_overlap = [float(text)/100 * imgWidthUm,float(text)/100 * imgHeightUm]

        #Get the grid info:
        self.gridEntries = []
        if self.pos_choice == 'center':
            #If it's from center, we need to create a grid of self.grid_n_rows by self.grid_n_cols, centered around self.pos_center, taking self.pos_overlap (in um units) into account:
            totXsize = (self.grid_n_cols)* imgWidthUm + (self.grid_n_cols - 1) * -self.pos_overlap[0]
            totYsize = (self.grid_n_rows)* imgHeightUm + (self.grid_n_rows - 1) * -self.pos_overlap[1]
            centerPos = self.pos_center
        elif self.pos_choice == 'corner':
            #Check if any NaNs in the corner entries:
            if not np.isnan(any([any(self.pos_top_left),any(self.pos_top_right),any(self.pos_bottom_left),any(self.pos_bottom_right)])):
            #     Use the corner positions to determine the center position and the total size:
                centerPos = [(self.pos_top_left[0]+self.pos_bottom_right[0])/2,(self.pos_top_left[1]+self.pos_bottom_right[1])/2]
                totXsize = abs(self.pos_bottom_right[0]-self.pos_top_left[0])
                totYsize = abs(self.pos_bottom_right[1]-self.pos_top_left[1])
                #Using this and the overlap, determine the grid n rows/cols:
                self.grid_n_rows = int(totYsize / (imgHeightUm + self.pos_overlap[1]))+1
                self.grid_n_cols = int(totXsize / (imgWidthUm + self.pos_overlap[0]))+1


        if self.grid_flow_type == 'hor_normal': #row-by-row
            for yy in range(self.grid_n_rows):
                for xx in range(self.grid_n_cols):
                    xpoint = centerPos[0]-(totXsize/2)+xx*imgWidthUm + xx * -self.pos_overlap[0]+ 0.5*imgWidthUm #type:ignore
                    ypoint = centerPos[1]-(totYsize/2)+ yy*imgHeightUm + yy * -self.pos_overlap[1]+ 0.5*imgHeightUm #type:ignore
                    self.gridEntries.append([xpoint,ypoint])
        elif self.grid_flow_type == 'ver_normal': #row-by-row
            for xx in range(self.grid_n_cols):
                for yy in range(self.grid_n_rows):
                    xpoint = centerPos[0]-(totXsize/2)+xx*imgWidthUm + xx * -self.pos_overlap[0]+ 0.5*imgWidthUm #type:ignore
                    ypoint = centerPos[1]-(totYsize/2)+ yy*imgHeightUm + yy * -self.pos_overlap[1]+ 0.5*imgHeightUm #type:ignore
                    self.gridEntries.append([xpoint,ypoint])
        elif self.grid_flow_type == 'hor_snake':
            for yy in range(self.grid_n_rows):
                rangev = range(self.grid_n_cols)
                if yy % 2 == 1:
                    #reverse the range
                    rangev = range(self.grid_n_cols-1,-1,-1)
                for xx in rangev:
                    xpoint = centerPos[0]-(totXsize/2)+xx*imgWidthUm + xx * -self.pos_overlap[0]+ 0.5*imgWidthUm #type:ignore
                    ypoint = centerPos[1]-(totYsize/2)+ yy*imgHeightUm + yy * -self.pos_overlap[1]+ 0.5*imgHeightUm #type:ignore
                    self.gridEntries.append([xpoint,ypoint])
        elif self.grid_flow_type == 'ver_snake':
            for xx in range(self.grid_n_cols):

                rangev = range(self.grid_n_rows)
                if xx % 2 == 1:
                    #reverse the range
                    rangev = range(self.grid_n_rows-1,-1,-1)
                for yy in rangev:
                    xpoint = centerPos[0]-(totXsize/2)+xx*imgWidthUm + xx * -self.pos_overlap[0]+ 0.5*imgWidthUm #type:ignore
                    ypoint = centerPos[1]-(totYsize/2)+ yy*imgHeightUm + yy * -self.pos_overlap[1]+ 0.5*imgHeightUm #type:ignore
                    self.gridEntries.append([xpoint,ypoint])
            
        #Set the grid text
        gridText = ""
        if self.pos_choice == 'corner':
            gridText += "Grid determined from corners - hover for info\n"
        elif self.pos_choice == 'center':
            gridText += "Grid determined from center - hover for info\n"
        
        gridHoverText = str(self.gridEntries)
        self.gridInfoLabel.setText(gridText)
        self.gridInfoLabel.setToolTip(gridHoverText)

    def setPositionText(self,positionAttr,recursiveUpdate = True,updateFromStage = True):
        """
        Sets the text of the position text boxes to the current xy stage position.
        """
        #Create text of these positions with 2 dec places:
        if updateFromStage:
            xx = f"{self.core.get_xy_position()[0]:.2f}"
            yy = f"{self.core.get_xy_position()[1]:.2f}"
            text = f"{xx}, {yy}"
            
            if positionAttr == "pos_center":
                self.setPosCenter.setText(text)
                self.pos_choice = 'center'
                #set corners to nans:
                self.pos_top_right = [np.nan,np.nan]
                self.pos_bottom_left = [np.nan,np.nan]
                self.pos_bottom_right = [np.nan,np.nan]
                self.pos_top_left = [np.nan,np.nan]
            elif positionAttr == "pos_top_left":
                self.pos_choice = 'corner'
                self.setPosTopLeft.setText(text)
                self.pos_top_left = [float(xx),float(yy)]
                #Also update the top and left pos of the pos_top_right and pos_bot_left:
                self.pos_top_right[1] = self.pos_top_left[1]
                self.pos_bottom_left[0] = self.pos_top_left[0]
            elif positionAttr == "pos_top_right":
                self.pos_choice = 'corner'
                self.setPosTopRight.setText(text)
                self.pos_top_right = [float(xx),float(yy)]
                self.pos_top_left[1] = self.pos_top_right[1]
                self.pos_bottom_right[0] = self.pos_top_right[0]
            elif positionAttr == "pos_bot_left":
                self.pos_choice = 'corner'
                self.setPosBottomLeft.setText(text)
                self.pos_bottom_left = [float(xx),float(yy)]
                self.pos_bottom_right[1] = self.pos_bottom_left[1]
                self.pos_top_left[0] = self.pos_bottom_left[0]
            elif positionAttr == "pos_bot_right":
                self.pos_choice = 'corner'
                self.setPosBottomRight.setText(text)
                self.pos_bottom_right = [float(xx),float(yy)]
                self.pos_bottom_left[1] = self.pos_bottom_right[1]
                self.pos_top_right[0] = self.pos_bottom_right[0]
                
        else: #Not from stage pos, but from memory
            if positionAttr == "pos_top_left":
                self.setPosTopLeft.setText(f"{self.pos_top_left[0]}, {self.pos_top_left[1]}")
            elif positionAttr == "pos_top_right":
                self.setPosTopRight.setText(f"{self.pos_top_right[0]}, {self.pos_top_right[1]}")
            elif positionAttr == "pos_bot_left":
                self.setPosBottomLeft.setText(f"{self.pos_bottom_left[0]}, {self.pos_bottom_left[1]}")
            elif positionAttr == "pos_bot_right":
                self.setPosBottomRight.setText(f"{self.pos_bottom_right[0]}, {self.pos_bottom_right[1]}")
        
        #And update the others/all w/o recursiveness
        if recursiveUpdate == True:
            self.setPositionText("pos_top_left",recursiveUpdate = False,updateFromStage = False)
            self.setPositionText("pos_top_right",recursiveUpdate = False,updateFromStage = False)
            self.setPositionText("pos_bot_left",recursiveUpdate = False,updateFromStage = False)
            self.setPositionText("pos_bot_right",recursiveUpdate = False,updateFromStage = False)
        
        self.updateGridInfo()
        
        pass

    def accept(self):
        if self.gridEntries != []:
            #For speedup, right now un-link the update GUI function:
            self.parent.xypositionListWidget.disconnectFunGUIConnection()
            for entry in self.gridEntries:
                self.parent.xypositionListWidget.addNewEntry(textEntry="Grid",setxy = entry)
            
            #And relink the update GUI function
            self.parent.xypositionListWidget.reconnectFunGUIConnection(runOnce=True)
            self.dialog.close()
        else:
            logging.error('No grid entries!')
        
    def reject(self):
        self.dialog.close()

class createGridFromCenterPopUpBox:
    
    def __init__(self,parent):
        #Idea: Create a quick pop-up box which asks the user for nr of rows, columns. Then use this to find the top/bottom left/right positions (given the overlap). Also flag the self.setFromCenter to True, and self.setFromCorners to False for good interactibility later.
        self.parent=parent
        #The pop-up box should contain inputs for both rows and columns
        from PyQt5.QtWidgets import QDialog
        self.popupbox = QDialog()
        self.popupbox.setWindowTitle("Grid from Center")
        layout = QVBoxLayout()
        #Add two of those rolling integer things to the layout:
        # Create a QSpinBox
        from PyQt5.QtWidgets import QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QSpinBox
        self.SpinBoxRows = QSpinBox()
        self.SpinBoxRows.setRange(1,1000)
        self.SpinBoxRows.setValue(parent.grid_n_rows)
        self.SpinBoxRows.setSingleStep(1)
        self.SpinBoxCols = QSpinBox()
        self.SpinBoxCols.setRange(1,1000)
        self.SpinBoxCols.setValue(parent.grid_n_cols)
        self.SpinBoxCols.setSingleStep(1)
        
        #Create a Hbox and add these in, together with labesl:
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Rows:"))
        hbox.addWidget(self.SpinBoxRows)
        hbox.addWidget(QLabel("Cols:"))
        hbox.addWidget(self.SpinBoxCols)
        
        layout.addLayout(hbox)
        
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.acceptPopup)
        self.buttonBox.rejected.connect(self.rejectPopup)
        
        #Add the buttonbox:
        layout.addWidget(self.buttonBox)
        self.popupbox.setLayout(layout)
        
    def getPopup(self):
        return self.popupbox

    def acceptPopup(self):
        #Get the values from the line edits:
        rows = int(self.SpinBoxRows.value())
        self.parent.grid_n_rows = rows
        cols = int(self.SpinBoxCols.value())
        self.parent.grid_n_cols = cols
        # #Get the overlap:
        # overlap = float(self.overlapEditField.text())
        # #Get the overlap unit:
        # overlapUnit = self.overlapDropDown.currentText()
        #Get the current position:
        position = get_xy_position(self.parent.core,self.parent.parent.shared_data)
        self.parent.pos_center = position
        
        self.parent.pos_choice = 'center'
        self.parent.updateGridInfo()
        #Close the popup box
        self.popupbox.close()
        logging.debug(f"Rows: {rows}, Cols: {cols}, Position: {position}")
    
    def rejectPopup(self):
        #Just close:
        self.popupbox.close()
            
class multiLineEdit_valueVarAdv(QHBoxLayout):
    
    def __init__(self,current_selected_function,inputData,curr_layout,nodzInfo,ShowVariablesOptions=True,textChangeCallback=None,valueVarAdv='Value'):
        super().__init__()
        
        self.line_edit = None
        self.line_edit_variable = None
        self.line_edit_adv = None
        self.comboBox_switch = None
        
        if valueVarAdv not in ['Value','Variable','Advanced']:
            valueVarAdv = 'Value'
            logging.error('Wrong entry!')
        
        #Create a random string of 10 characters:
        import random
        import string
        randomName2 = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
        
        #Create a new HBox:
        
        k=0
        #Creating a line-edit...
        self.line_edit = QLineEdit()
        
        #Method for variables in Glados
        if ShowVariablesOptions:
            #Advanced - flow + var via maths
            self.line_edit_adv = CustomLineEdit()
            self.line_edit_Button_adv = QPushButton("Add Var")
            #Add a click-callback:
            self.line_edit_Button_adv.clicked.connect(lambda text,line_edit=self.line_edit_adv: PushButtonAddVariableCallBack(line_edit, nodzInfo=nodzInfo))
            #Only var
            self.line_edit_variable = CustomLineEdit()
            self.line_edit_variable.setEnabled(False)
            self.push_button_variable_adv = QPushButton("Choose Var")
            #Add a click-callback:
            self.push_button_variable_adv.clicked.connect(lambda text,line_edit=self.line_edit_variable: PushButtonChooseVariableCallBack(line_edit, nodzInfo=nodzInfo))
            #Switch to switch between
            self.comboBox_switch = QComboBox()
            self.comboBox_switch.addItem("Value")
            self.comboBox_switch.addItem("Variable")
            self.comboBox_switch.addItem("Advanced")
            
            #Check if it's the standard list of list of dicts for analysis
            if type(inputData) == list and type(inputData[0]) == list and type(inputData[0][0]) == dict:
                self.line_edit.setObjectName(f"LineEdit#{current_selected_function}#{inputData[0][k]['name']}")
                self.line_edit_adv.setObjectName(f"LineEditAdv#{current_selected_function}#{inputData[0][k]['name']}")
                self.line_edit_Button_adv.setObjectName(f"PushButtonAdv#{current_selected_function}#{inputData[0][k]['name']}")
                self.line_edit_variable.setObjectName(f"LineEditVariable#{current_selected_function}#{inputData[0][k]['name']}")
                self.push_button_variable_adv.setObjectName(f"PushButtonVariable#{current_selected_function}#{inputData[0][k]['name']}")
                self.comboBox_switch.setObjectName(f"ComboBoxSwitch#{current_selected_function}#{inputData[0][k]['name']}")
            else: #Otherwise is a non-user-settable function.
                self.line_edit.setObjectName(f"LineEdit#{current_selected_function}#{inputData}")
                self.line_edit_adv.setObjectName(f"LineEditAdv#{current_selected_function}#{inputData}")
                self.line_edit_Button_adv.setObjectName(f"PushButtonAdv#{current_selected_function}#{inputData}")
                self.line_edit_variable.setObjectName(f"LineEditVariable#{current_selected_function}#{inputData}")
                self.push_button_variable_adv.setObjectName(f"PushButtonVariable#{current_selected_function}#{inputData}")
                self.comboBox_switch.setObjectName(f"ComboBoxSwitch#{current_selected_function}#{inputData}")
        
        #Actually placing it in the layout
        if checkAndShowWidget(curr_layout,self.line_edit.objectName()) == False or (current_selected_function is None and inputData is None):
            self.addWidget(self.line_edit)
            if ShowVariablesOptions:
                self.addWidget(self.line_edit_variable)
                #TODO: Figure out if this can stay callback kwargValueInputChanged
                
                #Init the parent currentData storage:
                self.addWidget(self.push_button_variable_adv)
                
                self.addWidget(self.line_edit_adv)
                #TODO: Figure out if this can stay callback kwargValueInputChanged
                #Init the parent currentData storage:
                self.addWidget(self.line_edit_Button_adv)
                
                self.addWidget(self.comboBox_switch)
                #Change the switch-combobox to variable and update as required:
                self.comboBox_switch.setCurrentText(valueVarAdv)
                # hideAdvVariables(comboBox_switch)
                
                # if textChangeCallback == None:
                self.line_edit_variable.textChanged.connect(lambda text,line_edit=self.line_edit_variable: kwargValueInputChanged(line_edit))
                self.line_edit_adv.textChanged.connect(lambda text,line_edit=self.line_edit_adv: kwargValueInputChanged(line_edit))
                self.comboBox_switch.currentIndexChanged.connect(lambda index, comboBox=self.comboBox_switch: changeDataVarUponKwargChange(comboBox))
                self.comboBox_switch.currentIndexChanged.connect(lambda index, comboBox=self.comboBox_switch: hideAdvVariables(comboBox))
                if textChangeCallback is not None:
                    self.line_edit.textChanged.connect(textChangeCallback)
                    self.line_edit_variable.textChanged.connect(textChangeCallback)
                    self.line_edit_adv.textChanged.connect(textChangeCallback)
                    self.comboBox_switch.currentIndexChanged.connect(textChangeCallback)
                    # self.comboBox_switch.currentIndexChanged.connect(lambda index, comboBox=self.comboBox_switch: hideAdvVariables(comboBox))
            
def layout_init(curr_layout,className,displayNameToFunctionNameMap,current_dropdown=None,parent=None,ignorePolarity=False,maxNrRows=10,showVisualisationBox=False,nodzInfo=None,skipInput=False):
    try:
        logging.debug('Changing layout '+curr_layout.parent().objectName())
    except (AttributeError, RuntimeError):
        pass
    #This removes everything except the first entry (i.e. the drop-down menu)
    # resetLayout(curr_layout,className)
    #Get the dropdown info
    
    if current_dropdown == None:
        return
    for index in range(current_dropdown.count()):
        item_text = current_dropdown.itemText(index)
        if item_text is not None and item_text != '':
            #Get the kw-arguments from the current dropdown.
            current_selected_function = functionNameFromDisplayName(item_text,displayNameToFunctionNameMap)
            logging.debug('current selected function: '+current_selected_function) #type:ignore

            #Unhide everything
            model = current_dropdown.model()
            totalNrRows = model.rowCount()
            for rowId in range(totalNrRows):
                #First show all rows:
                current_dropdown.view().setRowHidden(rowId, False)
                item = model.item(rowId)
                item.setFlags(item.flags() | Qt.ItemIsEnabled) #type:ignore
        
            #Visual max number of rows before a 2nd column is started.
            labelposoffset = 0
            
            #Want to show variables in advanced mode?
            ShowVariablesOptions = True 

            k=0
            if not skipInput:
                inputData = inputFromFunction(current_selected_function)
                
                for k in range(len(inputData)):
                    #TODO: display name if wanted
                    if 'display_name' in inputData[0][k]:
                        label = QLabel(f"<b><i>{inputData[0][k]['display_name']}</i></b>")
                    else:
                        label = QLabel(f"<b><i>{inputData[0][k]['name']}</i></b>")
                    label.setObjectName(f"Label#{current_selected_function}#{inputData[0][k]['name']}")
                    if checkAndShowWidget(curr_layout,label.objectName()) == False:
                        #TODO: actual tooltip
                        label.setToolTip("INPUT DATA")
                        curr_layout.addWidget(label,2+(k+labelposoffset)%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+0)
                        
                    #This defaultValue is actually important later, leave it at DefaultInput.
                    defaultValue = 'DefaultInput'
                    
                    SingleVar_Variables_boxLayout = multiLineEdit_valueVarAdv(current_selected_function,inputData,curr_layout,nodzInfo,ShowVariablesOptions=True)
                    
                    line_edit = SingleVar_Variables_boxLayout.line_edit
                    line_edit_variable = SingleVar_Variables_boxLayout.line_edit_variable
                    line_edit_adv = SingleVar_Variables_boxLayout.line_edit_adv
                    comboBox_switch = SingleVar_Variables_boxLayout.comboBox_switch
                    
                    #TODO: get tooltip
                    line_edit.setToolTip('TOOLTIP')
                    if defaultValue is not None:
                        line_edit.setText(str(defaultValue))
                    curr_layout.addLayout(SingleVar_Variables_boxLayout,2+(k+labelposoffset)%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+1)
                    #Add a on-change listener:
                    line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))
                    #Init the parent currentData storage:
                    changeDataVarUponKwargChange(line_edit)
                    if ShowVariablesOptions:
                        #Init the parent currentData storage:
                        #TODO: Figure out if this can stay kwargvalueinputchanged
                        changeDataVarUponKwargChange(line_edit_variable)
                        changeDataVarUponKwargChange(line_edit_adv)
                        changeDataVarUponKwargChange(comboBox_switch)
                    
            #Add a visual thick line:
            # Create a widget for the line
            label = QLabel(f"")
            label.setObjectName(f"KEEP")
            if checkAndShowWidget(curr_layout,label.objectName()) == False:
                # line_widget = QLabel('LINE')
                label.setStyleSheet("background-color: black;")  # Set the line color
                label.setFixedHeight(2)  # Set the line thickness
                curr_layout.addWidget(label, 3+(k+labelposoffset)%maxNrRows, 0, 1, 10)  # Span one row and one column

            reqKwargs = reqKwargsFromFunction(current_selected_function)
            
            #Add a widget-pair for every kw-arg
            for k in range(len(reqKwargs)):
                #Value is used for scoring, and takes the output of the method
                if reqKwargs[k] != 'methodValue':
                    label = QLabel(f"<b>{displayNameFromKwarg(current_selected_function,reqKwargs[k])}</b>")
                    label.setObjectName(f"Label#{current_selected_function}#{reqKwargs[k]}")
                    if checkAndShowWidget(curr_layout,label.objectName()) == False:
                        label.setToolTip(infoFromMetadata(current_selected_function,specificKwarg=reqKwargs[k]))
                        curr_layout.addWidget(label,4+(k+labelposoffset)%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+0)
                    #Check if we want to add a fileLoc-input:
                    if typeFromKwarg(current_selected_function,reqKwargs[k]) == 'fileLoc':
                        #Create a new qhboxlayout:
                        hor_boxLayout = QHBoxLayout()
                        #Add a line_edit to this:
                        line_edit = QLineEdit()
                        line_edit.setObjectName(f"LineEdit#{current_selected_function}#{reqKwargs[k]}")
                        defaultValue = defaultValueFromKwarg(current_selected_function,reqKwargs[k])
                        hor_boxLayout.addWidget(line_edit)
                        #Also add a QButton with ...:
                        line_edit_lookup = QPushButton()
                        line_edit_lookup.setText('...')
                        line_edit_lookup.setObjectName(f"PushButton#{current_selected_function}#{reqKwargs[k]}")
                        hor_boxLayout.addWidget(line_edit_lookup)
                        
                        #Actually placing it in the layout
                        checkAndShowWidget(curr_layout,line_edit.objectName())
                        checkAndShowWidget(curr_layout,line_edit_lookup.objectName())
                        if checkAndShowWidget(curr_layout,line_edit.objectName()) == False:
                            line_edit.setToolTip(infoFromMetadata(current_selected_function,specificKwarg=reqKwargs[k]))
                            if defaultValue is not None:
                                line_edit.setText(str(defaultValue))
                            curr_layout.addLayout(hor_boxLayout,4+(k+labelposoffset)%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+1)
                            #Add a on-change listener:
                            line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))
                            
                            #Add an listener when the pushButton is pressed
                            line_edit_lookup.clicked.connect(lambda text2,line_edit_change_objName = line_edit,text="Select file",filter="*.*": lineEditFileLookup(line_edit_change_objName, text, filter,parent=parent))
                            #Init the parent currentData storage:
                            changeDataVarUponKwargChange(line_edit)
                    else: #'normal' type - int, float, string, whatever
                        #Create a new HBox:
                        SingleVar_Variables_boxLayout = QHBoxLayout()
                        
                        #Creating a line-edit (or, for bool-typed kwargs, a checkbox)...
                        line_edit = createValueEditWidget(current_selected_function,reqKwargs[k])
                        defaultValue = defaultValueFromKwarg(current_selected_function,reqKwargs[k])

                        #Method for variables in Glados
                        if ShowVariablesOptions:
                            #Advanced - flow + var via maths
                            line_edit_adv = CustomLineEdit()
                            line_edit_adv.setObjectName(f"LineEditAdv#{current_selected_function}#{reqKwargs[k]}")
                            line_edit_Button_adv = QPushButton("Add Var")
                            #Add a click-callback:
                            line_edit_Button_adv.clicked.connect(lambda text,line_edit=line_edit_adv: PushButtonAddVariableCallBack(line_edit, nodzInfo=nodzInfo))
                            line_edit_Button_adv.setObjectName(f"PushButtonAdv#{current_selected_function}#{reqKwargs[k]}")
                            #Only var
                            line_edit_variable = CustomLineEdit()
                            line_edit_variable.setEnabled(False)
                            line_edit_variable.setObjectName(f"LineEditVariable#{current_selected_function}#{reqKwargs[k]}")
                            push_button_variable_adv = QPushButton("Choose Var")
                            push_button_variable_adv.setObjectName(f"PushButtonVariable#{current_selected_function}#{reqKwargs[k]}")
                            #Add a click-callback:
                            push_button_variable_adv.clicked.connect(lambda text,line_edit=line_edit_variable: PushButtonChooseVariableCallBack(line_edit, nodzInfo=nodzInfo))
                            #Switch to switch between
                            comboBox_switch = QComboBox()
                            comboBox_switch.setObjectName(f"ComboBoxSwitch#{current_selected_function}#{reqKwargs[k]}")
                            comboBox_switch.addItem("Value")
                            comboBox_switch.addItem("Variable")
                            comboBox_switch.addItem("Advanced")
                        
                        #Actually placing it in the layout
                        if checkAndShowWidget(curr_layout,line_edit.objectName()) == False:
                            SingleVar_Variables_boxLayout.addWidget(line_edit)
                            if ShowVariablesOptions:
                                SingleVar_Variables_boxLayout.addWidget(line_edit_variable)
                                line_edit_variable.textChanged.connect(lambda text,line_edit=line_edit_variable: kwargValueInputChanged(line_edit))
                                #Init the parent currentData storage:
                                SingleVar_Variables_boxLayout.addWidget(push_button_variable_adv)
                                
                                SingleVar_Variables_boxLayout.addWidget(line_edit_adv)
                                line_edit_adv.textChanged.connect(lambda text,line_edit=line_edit_adv: kwargValueInputChanged(line_edit))
                                #Init the parent currentData storage:
                                SingleVar_Variables_boxLayout.addWidget(line_edit_Button_adv)
                                
                                SingleVar_Variables_boxLayout.addWidget(comboBox_switch)
                                comboBox_switch.currentIndexChanged.connect(lambda index, comboBox=comboBox_switch: changeDataVarUponKwargChange(comboBox))
                                comboBox_switch.currentIndexChanged.connect(lambda index, comboBox=comboBox_switch: hideAdvVariables(comboBox))
                            
                            line_edit.setToolTip(infoFromMetadata(current_selected_function,specificKwarg=reqKwargs[k]))
                            curr_layout.addLayout(SingleVar_Variables_boxLayout,4+(k+labelposoffset)%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+1)
                            #Set the default value and add a on-change listener (branches on QCheckBox vs QLineEdit):
                            wireValueEditWidget(line_edit,defaultValue)
                            #Init the parent currentData storage:
                            changeDataVarUponKwargChange(line_edit)
                            if ShowVariablesOptions:
                                #Init the parent currentData storage:
                                changeDataVarUponKwargChange(line_edit_variable)
                                changeDataVarUponKwargChange(line_edit_adv)
                            
                else:
                    labelposoffset -= 1
                
            #Get the optional kw-arguments from the current dropdown.
            optKwargs = optKwargsFromFunction(current_selected_function)
            #Add a widget-pair for every kwarg
            for k in range(len(optKwargs)):
                label = QLabel(f"<i>{displayNameFromKwarg(current_selected_function,optKwargs[k])}</i>")
                label.setObjectName(f"Label#{current_selected_function}#{optKwargs[k]}")
                if checkAndShowWidget(curr_layout,label.objectName()) == False:
                    label.setToolTip(infoFromMetadata(current_selected_function,specificKwarg=optKwargs[k]))
                    curr_layout.addWidget(label,4+(k+labelposoffset+len(reqKwargs))%maxNrRows,(((k+labelposoffset+len(reqKwargs)))//maxNrRows)*2+0)
                #Check if we want to add a fileLoc-input:
                if typeFromKwarg(current_selected_function,optKwargs[k]) == 'fileLoc':
                    #Create a new qhboxlayout:
                    hor_boxLayout = QHBoxLayout()
                    #Add a line_edit to this:
                    line_edit = QLineEdit()
                    line_edit.setObjectName(f"LineEdit#{current_selected_function}#{optKwargs[k]}")
                    defaultValue = defaultValueFromKwarg(current_selected_function,optKwargs[k])
                    hor_boxLayout.addWidget(line_edit)
                    #Also add a QButton with ...:
                    line_edit_lookup = QPushButton()
                    line_edit_lookup.setText('...')
                    line_edit_lookup.setObjectName(f"PushButton#{current_selected_function}#{optKwargs[k]}")
                    hor_boxLayout.addWidget(line_edit_lookup)
                    
                    #Actually placing it in the layout
                    checkAndShowWidget(curr_layout,line_edit.objectName())
                    checkAndShowWidget(curr_layout,line_edit_lookup.objectName())
                    if checkAndShowWidget(curr_layout,line_edit.objectName()) == False:
                        line_edit.setToolTip(infoFromMetadata(current_selected_function,specificKwarg=optKwargs[k]))
                        if defaultValue is not None:
                            line_edit.setText(str(defaultValue))
                        curr_layout.addLayout(hor_boxLayout,4+(k+labelposoffset)%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+1)
                        #Add a on-change listener:
                        line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))
                        #Init the parent currentData storage:
                        changeDataVarUponKwargChange(line_edit)
                        
                        #Add an listener when the pushButton is pressed
                        line_edit_lookup.clicked.connect(lambda text2,line_edit_change_objName = line_edit,text="Select file",filter="*.*": lineEditFileLookup(line_edit_change_objName, text, filter,parent=parent))
                            
                else:
                    #Create a new HBox:
                    SingleVar_Variables_boxLayout = QHBoxLayout()
                        
                    line_edit = createValueEditWidget(current_selected_function,optKwargs[k])
                    defaultValue = defaultValueFromKwarg(current_selected_function,optKwargs[k])

                    #Method for variables in Glados
                    if ShowVariablesOptions:
                        #Advanced - flow + var via maths
                        line_edit_adv = QLineEdit()
                        line_edit_adv.setObjectName(f"LineEditAdv#{current_selected_function}#{optKwargs[k]}")
                        line_edit_Button_adv = QPushButton("Add Var")
                        line_edit_Button_adv.setObjectName(f"PushButtonAdv#{current_selected_function}#{optKwargs[k]}")
                        #Add a click-callback:
                        line_edit_Button_adv.clicked.connect(lambda text,line_edit=line_edit_adv: PushButtonAddVariableCallBack(line_edit, nodzInfo=nodzInfo))
                        #Only var
                        line_edit_variable = QLineEdit()
                        line_edit_variable.setObjectName(f"LineEditVariable#{current_selected_function}#{optKwargs[k]}")
                        push_button_variable_adv = QPushButton("Choose Var")
                        push_button_variable_adv.setObjectName(f"PushButtonVariable#{current_selected_function}#{optKwargs[k]}")
                        #Add a click-callback:
                        push_button_variable_adv.clicked.connect(lambda text,line_edit=line_edit_variable: PushButtonChooseVariableCallBack(line_edit, nodzInfo=nodzInfo))
                        #Switch to switch between
                        comboBox_switch = QComboBox()
                        comboBox_switch.setObjectName(f"ComboBoxSwitch#{current_selected_function}#{optKwargs[k]}")
                        comboBox_switch.addItem("Value")
                        comboBox_switch.addItem("Variable")
                        comboBox_switch.addItem("Advanced")
                    
                    if checkAndShowWidget(curr_layout,line_edit.objectName()) == False:
                        SingleVar_Variables_boxLayout.addWidget(line_edit)
                        
                        if ShowVariablesOptions:
                            SingleVar_Variables_boxLayout.addWidget(line_edit_variable)
                            line_edit_variable.textChanged.connect(lambda text,line_edit=line_edit_variable: kwargValueInputChanged(line_edit))
                            #Init the parent currentData storage:
                            SingleVar_Variables_boxLayout.addWidget(push_button_variable_adv)
                            
                            SingleVar_Variables_boxLayout.addWidget(line_edit_adv)
                            line_edit_adv.textChanged.connect(lambda text,line_edit=line_edit_adv: kwargValueInputChanged(line_edit))
                            #Init the parent currentData storage:
                            SingleVar_Variables_boxLayout.addWidget(line_edit_Button_adv)
                            
                            SingleVar_Variables_boxLayout.addWidget(comboBox_switch)
                            comboBox_switch.currentIndexChanged.connect(lambda index, comboBox=comboBox_switch: changeDataVarUponKwargChange(comboBox))
                            comboBox_switch.currentIndexChanged.connect(lambda index, comboBox=comboBox_switch: hideAdvVariables(comboBox))
                        
                        line_edit.setToolTip(infoFromMetadata(current_selected_function,specificKwarg=optKwargs[k]))
                        curr_layout.addLayout(SingleVar_Variables_boxLayout,4+(k+labelposoffset+len(reqKwargs))%maxNrRows,(((k+labelposoffset+len(reqKwargs)))//maxNrRows)*2+1)
                        #Set the default value and add a on-change listener (branches on QCheckBox vs QLineEdit):
                        wireValueEditWidget(line_edit,defaultValue)
                        #Init the parent currentData storage:
                        changeDataVarUponKwargChange(line_edit)
                        if ShowVariablesOptions:
                            #Init the parent currentData storage:
                            changeDataVarUponKwargChange(line_edit_variable)
                            changeDataVarUponKwargChange(line_edit_adv)
                        
    #Hides everything except the current layout
    layout_changedDropdown(curr_layout,current_dropdown,displayNameToFunctionNameMap)
    # resetLayout(curr_layout)


#Start of a customLineEdit class to format a variable in a kwarg.
class CustomLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.search_icon = QIcon("search_icon.png")  # Change this to your icon path
        self.search_text = "Search"  # Change this to your desired text
        self.highlight_search = False
        self.setStyleSheet("color: white;")

    def paintEvent(self, event):
        super().paintEvent(event)

        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.Antialiasing)

            # Draw the custom icon
            # icon_rect = self.rect().adjusted(self.width() - self.icon_size - self.icon_padding,
            #                                 (self.height() - self.icon_size) / 2,
            #                                 -(self.width() - self.icon_padding),
            #                                 (self.height() - self.icon_size) / 2 + self.icon_size)
            # self.search_icon.paint(painter, icon_rect)

            # Draw the text
            painter.save()
            fm = QFontMetrics(self.font())
            text_rect = self.rect().adjusted(3, 3, 0, 0)
            if self.highlight_search:
                search_index = self.text().find(self.search_text)
                if search_index != -1:
                    prefix = self.text()[:search_index]
                    match = self.text()[search_index:search_index+len(self.search_text)]
                    suffix = self.text()[search_index+len(self.search_text):]
                    prefix_width = fm.width(prefix)
                    match_width = fm.width(match)

                    # Draw the match text
                    painter.setPen(QColor(0, 255, 0))  # Set pen color for text
                    painter.drawText(text_rect.left() + prefix_width, text_rect.top() + fm.ascent(), match)
                    
                    # Draw underline
                    underline_start = text_rect.left() + prefix_width
                    underline_end = underline_start + match_width
                    underline_y = text_rect.bottom() - 2  # Position the underline 2 pixels above the bottom
                    underline_pen = QPen(QColor(0, 0, 255))
                    underline_pen.setWidth(1)
                    painter.setPen(underline_pen)
                    painter.drawLine(underline_start, underline_y, underline_end, underline_y)
                    

            painter.restore()

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if self.text().find(self.search_text) != -1:
            self.highlight_search = True
        else:
            self.highlight_search = False
        self.update()

def preLoadOptions_analysis(curr_layout,currentData,functionName='comboBox_analysisFunctions',analysisName='__selectedDropdownEntryAnalysis__'):
    """
    Preloads the kwarg values from the currentData dict into their respective widgets
    """
    
    parentObject = curr_layout.parent().parent()
    currentSelectedFunction = None
    for entry in parentObject.currentData['__displayNameFunctionNameMap__']:
        if entry[0] == parentObject.currentData[analysisName]:
            currentSelectedFunction = entry[1]
            
    for i in range(curr_layout.count()):
        item = curr_layout.itemAt(i)
        if not isinstance(item,QSpacerItem):
            if item.widget() is not None:
                child = item.widget()
                if child.objectName() in currentData:
                    logging.debug(f"Preloading {child.objectName()} with {currentData[child.objectName()]}")
                    if isinstance(child,QComboBox):
                        child.setCurrentText(currentData[child.objectName()])
                        # if 'ComboBoxSwitch#'+currentSelectedFunction in child.objectName():
                        #     hideAdvVariables(child)
                    else:
                        child.setText(str(currentData[child.objectName()]))
                    
                #Also set the dropdown to the correct value:
                if functionName in child.objectName() and analysisName in currentData:
                    child.setCurrentText(currentData[analysisName])
            else:
                for index2 in range(item.count()):
                    widget_sub_item = item.itemAt(index2)
                    child = widget_sub_item.widget()
                    if child.objectName() in currentData:
                        # logging.debug(f"2Preloading {child.objectName()} with {currentData[child.objectName()]}")
                        if isinstance(child,QComboBox):
                            child.setCurrentText(currentData[child.objectName()])
                            # if 'ComboBoxSwitch#'+currentSelectedFunction in child.objectName():
                            #     hideAdvVariables(child)
                        else:
                            child.setText(str(currentData[child.objectName()]))
                        
                    #Also set the dropdown to the correct value:
                    if functionName in child.objectName() and analysisName in currentData:
                        child.setCurrentText(currentData[analysisName])
    
def preLoadOptions_realtime(curr_layout,currentData):
    """
    Preloads the kwarg values from the currentData dict into their respective widgets
    """
    
    preLoadOptions_analysis(curr_layout,currentData,functionName='comboBox_RTanalysisFunctions',analysisName='__selectedDropdownEntryAnalysis__')
    # for i in range(curr_layout.count()):
    #     item = curr_layout.itemAt(i)
    #     if item.widget() is not None:
            # child = item.widget()
            # if child.objectName() in currentData:
            #     child.setText(str(currentData[child.objectName()]))
                
            # #Also set the dropdown to the correct value:
            # if 'comboBox_RTanalysisFunctions' in child.objectName() and '__selectedDropdownEntryRTAnalysis__' in currentData:
            #     child.setCurrentText(currentData['__selectedDropdownEntryRTAnalysis__'])

def hideAdvVariables(comboBox,current_selected_function=None,customParentChildren=None):
    """ 
    Hide/show the lineEdits/comboboxes of NodzVariables/Advanced/Normal input based on the comboBox variable
    """
    comboboxvalue = comboBox.currentText()
    functionName = comboBox.objectName().split('#')[1]
    kwargName = comboBox.objectName().split('#')[2]
    if customParentChildren == None:
        parentObject = comboBox.parent()
        parentChildren = parentObject.children()
        
        #Go out if wrong function
        currentSelectedFunction = None
        if hasattr(parentObject, 'currentData'):
            for entry in parentObject.currentData['__displayNameFunctionNameMap__']:
                if entry[0] == parentObject.currentData['__selectedDropdownEntryAnalysis__']:
                    currentSelectedFunction = entry[1]
        
            if functionName != currentSelectedFunction:
                return
    else:
        parentChildren = customParentChildren
    
    
    #Loop over all widgets in parent:
    for child in parentChildren:
        # logging.debug(child.objectName())
        if len(child.objectName().split('#')) > 2:
            #Check if it's the same function and variable:
            if child.objectName().split('#')[1] == functionName and child.objectName().split('#')[2] == kwargName:
                # logging.debug('Looking at ' + functionName + ' ' + kwargName)
                normalVarAdvValue = child.objectName().split('#')[0]
                if normalVarAdvValue != 'Label' and normalVarAdvValue != 'ComboBoxSwitch':
                    #Hide/show simple/advanced/onlyVar based on the comboBox value:
                    if comboboxvalue == 'Variable':
                        if normalVarAdvValue == 'LineEditVariable' or normalVarAdvValue == 'PushButtonVariable':
                            child.show()
                            # logging.debug(f'1Showing {child.objectName()}')
                        else:
                            child.hide()
                            logging.debug(f'1Hiding {child.objectName()}')
                    elif comboboxvalue == 'Advanced':
                        if normalVarAdvValue == 'LineEditAdv' or normalVarAdvValue == 'PushButtonAdv':
                            child.show()
                            # logging.debug(f'2Showing {child.objectName()}')
                        else:
                            child.hide()
                            logging.debug(f'2Hiding {child.objectName()}')
                    else:
                        if normalVarAdvValue == 'LineEdit':
                            child.show()
                            # logging.debug(f'3Showing {child.objectName()}')
                        else:
                            child.hide()
                            # logging.debug(f'3Hiding {child.objectName()}')
    
    # resetLayout(parentObject.mainLayout,currentSelectedFunction)
                    
def changeDataVarUponKwargChange(line_edit):
    #Idea: update the parent.currentData{} structure whenever a kwarg is changed, and this can be (re-)loaded when needed
    if isinstance(line_edit,QCheckBox):
        #Bool-typed kwarg widget (see createValueEditWidget). Stored as the same "True"/"False"
        #string a QLineEdit would hold, so every downstream consumer of currentData[...] is unaffected.
        parentObject = line_edit.parent()
        newValue = str(line_edit.isChecked())
        if hasattr(parentObject, 'currentData'):
            parentObject.currentData[line_edit.objectName()] = newValue
            #To be sure, also do this routine:
            updateCurrentDataUponDropdownChange(parentObject)
    elif isinstance(line_edit,QLineEdit):
        parentObject = line_edit.parent()
        newValue = line_edit.text()
        if hasattr(parentObject, 'currentData'):
            parentObject.currentData[line_edit.objectName()] = newValue
            #To be sure, also do this routine:
            updateCurrentDataUponDropdownChange(parentObject)
    elif isinstance(line_edit,QComboBox):
        parentObject = line_edit.parent()
        newValue = line_edit.currentText()
        if hasattr(parentObject, 'currentData'):
            parentObject.currentData[line_edit.objectName()] = newValue
            #To be sure, also do this routine:
            updateCurrentDataUponDropdownChange(parentObject)


def updateCurrentDataUponDropdownChange(parentObject):
    #Figure out the current selected dropdown entry:
    #loop over all children:
    for child in parentObject.children():
        if 'comboBox_analysisFunctions' in child.objectName() or 'comboBox_customFunctions' in child.objectName():
            parentObject.currentData['__selectedDropdownEntryAnalysis__'] = child.currentText()

def kwargValueInputChanged(line_edit):
    #Change the storage structure
    changeDataVarUponKwargChange(line_edit)
    #Get the function name
    function = line_edit.objectName().split("#")[1]
    #Get the kwarg
    kwarg = line_edit.objectName().split("#")[2]
    #Get the value
    value = line_edit.text()
    expectedType = typeFromKwarg(function,kwarg)
    if expectedType == 'fileLoc':
        expectedType=str
    if expectedType is not None:
        if expectedType is str:
            try:
                value = str(line_edit.text())
                setLineEditStyle(line_edit,type='Normal')
            except (AttributeError, RuntimeError, TypeError):
                #Show as warning
                setLineEditStyle(line_edit,type='Warning')
        elif expectedType is not str:
            try:
                value = eval(line_edit.text())
                if expectedType == float:
                    if isinstance(value,int) or isinstance(value,float):
                        setLineEditStyle(line_edit,type='Normal')
                    else:
                        setLineEditStyle(line_edit,type='Warning')
                else:
                    if isinstance(value,expectedType):
                        setLineEditStyle(line_edit,type='Normal')
                    else:
                        setLineEditStyle(line_edit,type='Warning')
            except (AttributeError, RuntimeError, TypeError, ValueError):
                #Show as warning
                setLineEditStyle(line_edit,type='Warning')
    else:
        setLineEditStyle(line_edit,type='Normal')
    pass

# Phase 7.3: setLineEditStyle + checkAndShowWidget moved to
# ui.widgets.builders. Re-exported below.
from glados_pycromanager.ui.widgets.builders import (  # noqa: F401
    checkAndShowWidget,
    setLineEditStyle,
)

#Remove everythign in this layout except className_dropdown
def resetLayout(curr_layout,className):
    for index in range(curr_layout.count()):
        widget_item = curr_layout.itemAt(index)
        if not isinstance(widget_item,QSpacerItem):
            # Check if the item is a widget (as opposed to a layout)
            if widget_item.widget() is not None:
                widget = widget_item.widget()
                #If it's the dropdown segment, label it as such
                if not ("KEEP" in widget.objectName()) and not ('#'+className+'#' in widget.objectName()):
                    # logging.debug(f"1Hiding {widget.objectName()}")
                    widget.hide()
                else:
                    # logging.debug(f"1Showing {widget.objectName()}")
                    widget.show()
            else:
                for index2 in range(widget_item.count()):
                    widget_sub_item = widget_item.itemAt(index2)
                    # Check if the item is a widget (as opposed to a layout)
                    if widget_sub_item.widget() is not None:
                        widget = widget_sub_item.widget()
                        #If it's the dropdown segment, label it as such
                        if not ("KEEP" in widget.objectName()) and not ('#'+className+'#' in widget.objectName()):
                            # logging.debug(f"2Hiding {widget.objectName()}")
                            widget.hide()
                        else:
                            # logging.debug(f"2Showing {widget.objectName()}")
                            widget.show()
                    else:
                        for index3 in range(widget_sub_item.count()):
                            widget_sub_sub_item = widget_sub_item.itemAt(index3)
                            # Check if the item is a widget (as opposed to a layout)
                            if widget_sub_sub_item.widget() is not None:
                                widget = widget_sub_sub_item.widget()
                                #If it's the dropdown segment, label it as such
                                if not ("KEEP" in widget.objectName()) and not ('#'+className+'#' in widget.objectName()):
                                    logging.debug(f"3Hiding {widget.objectName()}")
                                    widget.hide()
                            else:
                                logging.debug(f"3Showing {widget.objectName()}")
                                widget.show()
    

def getMethodDropdownInfo(curr_layout,className):
    curr_dropdown = []
    #Look through all widgets in the current layout
    for index in range(curr_layout.count()):
        widget_item = curr_layout.itemAt(index)
        #Check if it's fair to check
        if widget_item.widget() is not None:
            widget = widget_item.widget()
            #If it's the dropdown segment, label it as such
            if (className in widget.objectName()) and ("Dropdown" in widget.objectName()):
                curr_dropdown = widget
    #Return the dropdown
    return curr_dropdown


# Phase 7.3: file-dialog helpers moved to ui.widgets.builders. Shim.
from glados_pycromanager.ui.widgets.builders import (  # noqa: F401
    generalFileSearchButtonAction,
    lineEditFileLookup,
)


def getFunctionEvalTextFromCurrentData(function,currentData,p1,p2,nodzInfo=None,skipp2=False):
    
    methodKwargNames_method=[]
    methodKwargValues_method=[]
    methodKwargTypes_method=[]
    methodName_method = ''
    
    #First we determine if we run this with a normal value, with a variable only, or adv (mix of the two):
    variableValueOrAdvanced = {}
    for key,value in currentData.items():
        if "#"+function+"#" in key:
            if ("ComboBoxSwitch#" in key):
                kwargName = key.split('#')[2]
                variableValueOrAdvanced[kwargName] = value
    
    #Loop over all entries of currentData:
    for key,value in currentData.items():
        if "#"+function+"#" in key:
            split_list = key.split('#')
            kwargName = split_list[2]
            #Find variable/advance/normal (value) lineEdit
            
            #If not found, it's a Value:
            if kwargName not in variableValueOrAdvanced:
                variableValueOrAdvanced[kwargName] = 'Value'
            if variableValueOrAdvanced[kwargName] == 'Variable':
                lineEditNameVarAdv = "LineEditVariable#"
            elif variableValueOrAdvanced[kwargName] == 'Advanced':
                lineEditNameVarAdv = "LineEditAdv#"
            else:
                lineEditNameVarAdv = "LineEdit#"
            
            if (lineEditNameVarAdv in key):
                # The objectName will be along the lines of foo#bar#str
                #Check if the objectname is part of a method or part of a scoring
                methodName_method = split_list[1]
                methodKwargNames_method.append(split_list[2])

                #value could contain a file location. Thus, we need to swap out all \ for /:
                methodKwargValues_method.append(value.replace('\\','/'))
                
    
    #Get the Value/Variable/Adv:
    for entry in methodKwargNames_method:
        if variableValueOrAdvanced[entry]  == 'Variable':
            methodKwargTypes_method.append('Variable')
        elif variableValueOrAdvanced[entry]  == 'Advanced':
            methodKwargTypes_method.append('Advanced')
        else:
            methodKwargTypes_method.append('Value')
        
    
    #Now we create evaluation-texts:
    moduleMethodEvalTexts = []
    if methodName_method != '':
        if not skipp2:
            EvalTextMethod = getEvalTextFromGUIFunction(methodName_method, methodKwargNames_method, methodKwargValues_method,partialStringStart=str(p1)+','+str(p2),methodKwargTypes=methodKwargTypes_method,nodzInfo=nodzInfo)
        elif skipp2:
            EvalTextMethod = getEvalTextFromGUIFunction(methodName_method, methodKwargNames_method, methodKwargValues_method,partialStringStart=str(p1),methodKwargTypes=methodKwargTypes_method,nodzInfo=nodzInfo)
    else:
        if not skipp2:
            EvalTextMethod = function+'('+str(p1)+','+str(p2)+')'
        elif skipp2:
            EvalTextMethod = function+'('+str(p1)+')'
    #append this to moduleEvalTexts
    moduleMethodEvalTexts.append(EvalTextMethod)


    if moduleMethodEvalTexts is not None and len(moduleMethodEvalTexts) > 0:
        return moduleMethodEvalTexts[0]


#region T-G2: bind-time kwarg coercion
# __function_metadata__ declares a real Python type for every kwarg, but that
# type used to pick a *widget class* and nothing else: the value travelled as a
# string, was re-quoted into a Python string literal on every frame, and was
# re-parsed inside the node body (float(kwargs.get(...)),
# str(...).lower() in ('true','1')). These helpers coerce once, at bind time.
_KWARG_TRUE_STRINGS = ('true', '1', 'yes', 'on')
_KWARG_FALSE_STRINGS = ('false', '0', 'no', 'off', '')


def coerceKwargValue(value, declaredType, kwargName='', methodName=''):
    """Coerce one GUI-sourced kwarg string to its declared metadata type.

    Permissive by design: anything that does not convert cleanly is handed back
    as the original string with a warning, so an existing recipe carrying an
    unparseable value keeps behaving exactly as it did before (the node's own
    defensive parsing, or its failure, is unchanged).

    Non-strings pass through untouched - a Variable-mode kwarg resolves to a
    live object, not text.
    """
    if not isinstance(value, str):
        return value
    if declaredType is None or declaredType is str or declaredType == 'fileLoc':
        return value
    text = value.strip()
    try:
        if declaredType is bool:
            lowered = text.lower()
            if lowered in _KWARG_TRUE_STRINGS:
                return True
            if lowered in _KWARG_FALSE_STRINGS:
                return False
            raise ValueError(f'{value!r} is neither true nor false')
        if declaredType is int:
            return int(text)
        if declaredType is float:
            return float(text)
    except (ValueError, TypeError) as exc:
        logging.warning("Keeping kwarg %s.%s as text: %r is not a valid %s (%s)",
                        methodName, kwargName, value,
                        getattr(declaredType, '__name__', declaredType), exc)
        return value
    #An unrecognised declared type is not an error - leave the text alone.
    return value


def kwargTypesFromFunction(functionname):
    """Return {kwargName: declared type} for one node function, from the cached
    metadata. Kwargs that declare no "type" are absent from the map (their
    values stay strings)."""
    entry = _nodeFunctionEntry(functionname)
    if entry is None:
        return {}
    declaredTypes = {}
    for kwargListName in ('required_kwargs', 'optional_kwargs'):
        for kwarg in entry.get(kwargListName, []):
            if 'type' in kwarg:
                declaredTypes[kwarg['name']] = kwarg['type']
    return declaredTypes


def makeNodzVariableGetter(reference, nodzInfo, nodeDict=None):
    """Return a zero-arg callable reading the **current** value of `name@Origin`.

    Origin is `Global`, `Core`, or another node's name. This replaces the source
    text `getEvalTextFromGUIFunction` used to emit
    (`nodeDict['X'].variablesNodz['y']['data']`) — which is the only reason
    `eval()` needed a live local frame holding `nodeDict`, and therefore the only
    reason `createNodeDictFromNodes` was rebuilt on every frame (T-G3).

    What is captured is the *container mapping* (`nodzInfo.globalVariables`, or
    the origin node's `variablesNodz`), never the value and never the per-variable
    dict: writers replace the per-variable dict wholesale
    (`globalVariables[name] = {}` then `['data'] = value`, see
    `autonomous/executor.py`), so capturing one level deeper would silently go
    stale. The containers themselves are built once, per graph and per node.
    """
    variableName, _, originNodeName = str(reference).partition('@')
    if originNodeName == 'Global':
        container = nodzInfo.globalVariables
    elif originNodeName == 'Core':
        container = nodzInfo.coreVariables
    else:
        if nodeDict is None:
            nodeDict = createNodeDictFromNodes(nodzInfo.nodes)
        container = nodeDict[originNodeName].variablesNodz
    return lambda: container[variableName]['data']


def resolveNodzVariable(reference, nodzInfo, nodeDict=None):
    """Read the current value of a `name@Origin` Glados-variable reference once."""
    return makeNodzVariableGetter(reference, nodzInfo, nodeDict)()


@dataclass(frozen=True)
class BoundKwargs:
    """A node's kwargs, resolved once at bind time (T-G2/T-G3).

    `values` holds the constants, already coerced to their declared metadata
    types. `variableGetters` holds one zero-arg callable per Variable-mode kwarg,
    called on each `resolve()` so a Glados variable changed mid-run is seen.
    """
    values: dict
    variableGetters: dict

    def resolve(self) -> dict:
        """Return the kwargs dict to call the node with."""
        if not self.variableGetters:
            #Overwhelmingly the common case; no per-call copy needed since the
            #caller splats this into **kwargs anyway.
            return self.values
        resolved = dict(self.values)
        for kwargName, getter in self.variableGetters.items():
            resolved[kwargName] = getter()
        return resolved


def bindKwargsFromGUIFunction(methodName, methodKwargNames, methodKwargValues,
                              methodKwargTypes=None, removeKwargs=None,
                              skipInput=False, nodzInfo=None, nodeDict=None):
    """Build a **typed kwargs dict** for one node function from GUI values.

    The dict-returning sibling of :func:`getEvalTextFromGUIFunction`: same kwarg
    selection rules (declared required kwargs, plus the function's `input`
    entries unless ``skipInput``, plus any optional kwarg that has a value, plus
    `dist_kwarg`/`time_kwarg`), but the values are coerced to the types declared
    in ``__function_metadata__`` instead of being re-quoted as string literals.

    ``methodKwargTypes`` is the per-kwarg Value/Variable/Advanced *mode* list
    (the same argument `getEvalTextFromGUIFunction` takes), not a list of Python
    types. Variable-mode kwargs are resolved through :func:`resolveNodzVariable`;
    Advanced mode is still unimplemented and falls back to the raw text, exactly
    as the eval-text path does.

    Returns a :class:`BoundKwargs` (call ``.resolve()`` for the dict to splat into
    the node), or None when a required kwarg has no value — logging the same error
    the eval-text path logs, so callers can keep their existing failure handling.
    """
    if methodKwargTypes is None:
        methodKwargTypes = ['Value'] * len(methodKwargNames)
    if not methodName:
        return None

    inputKwargs = []
    if not skipInput:
        for inputEntry in inputFromFunction(methodName)[0]:
            inputKwargs.append(inputEntry['name'])
    reqKwargs = inputKwargs + reqKwargsFromFunction(methodName)
    if removeKwargs is not None:
        for removeKwarg in removeKwargs:
            if removeKwarg in reqKwargs:
                reqKwargs.remove(removeKwarg)

    if not all(elem in set(methodKwargNames) for elem in reqKwargs):
        logging.error('SOMETHING VERY STUPID HAPPENED')
        return None

    declaredTypes = kwargTypesFromFunction(methodName)
    boundValues = {}
    variableGetters = {}

    def _bind(kwargName, rawValue, mode):
        if mode == 'Variable':
            #Live reference, not a literal - never coerced, never quoted, and
            #re-read on every resolve() so a variable changed mid-run is seen.
            try:
                variableGetters[kwargName] = makeNodzVariableGetter(rawValue, nodzInfo, nodeDict)
            except (AttributeError, KeyError, TypeError) as exc:
                #No graph to resolve against (e.g. an RT node started from the
                #live view, nodzInfo=None), or a stale reference. Hand the raw
                #reference text through, which is what the eval-text path does
                #for optional kwargs anyway.
                logging.warning("Could not resolve Variable kwarg %s.%s = %r (%s); "
                                "passing the reference through as text",
                                methodName, kwargName, rawValue, exc)
                boundValues[kwargName] = rawValue
        elif mode == 'Advanced':
            logging.error('To implement!')
            boundValues[kwargName] = rawValue
        else:
            boundValues[kwargName] = coerceKwargValue(
                rawValue, declaredTypes.get(kwargName), kwargName, methodName)

    for reqKwarg in reqKwargs:
        GUIbasedIndex = methodKwargNames.index(reqKwarg)
        if methodKwargValues[GUIbasedIndex] == '':
            logging.error(f'Missing required keyword argument in {methodName}: {reqKwarg}, NOT CONTINUING')
            logging.error('NOT ALL KWARGS PROVIDED!')
            return None
        _bind(reqKwarg, methodKwargValues[GUIbasedIndex], methodKwargTypes[GUIbasedIndex])

    #Optional kwargs are looked up by name rather than by position. The eval-text
    #path indexes methodKwargValues positionally here, which turns a kwarg the
    #GUI did not supply into an IndexError instead of a default-value fallback.
    for optKwarg in optKwargsFromFunction(methodName):
        if optKwarg not in methodKwargNames:
            continue
        GUIbasedIndex = methodKwargNames.index(optKwarg)
        if methodKwargValues[GUIbasedIndex] == '':
            continue
        _bind(optKwarg, methodKwargValues[GUIbasedIndex], methodKwargTypes[GUIbasedIndex])

    #Distribution/time-fit choices come from combo boxes and stay text.
    for extraKwarg in ('dist_kwarg', 'time_kwarg'):
        if extraKwarg in methodKwargNames:
            boundValues[extraKwarg] = methodKwargValues[methodKwargNames.index(extraKwarg)]

    return BoundKwargs(boundValues, variableGetters)
#endregion

def _rtAnalysisKwargsFromCurrentData(function, currentData, modeAware=True):
    """Scan a node parameter panel's `currentData` dict for one function's kwargs.

    `currentData` is keyed by widget object name (`LineEdit#<function>#<kwarg>`,
    `LineEditVariable#...`, `LineEditAdv#...`, `ComboBoxSwitch#...`) - see
    Documentation/rt_analysis_parameters.md. Which of the three parallel input
    widgets is authoritative for a kwarg is decided by that kwarg's
    `ComboBoxSwitch` value (Value / Variable / Advanced).

    Args:
        function: the dotted node-function name the keys are scoped to.
        currentData: the panel's object-name -> value dict.
        modeAware: False reproduces the visualisation path's looser matching,
            which accepts *any* `LineEdit*` key and ignores the mode switch.

    Returns:
        ``(methodName, kwargNames, kwargValues, kwargModes)``; ``methodName`` is
        '' when nothing matched.
    """
    variableValueOrAdvanced = {}
    if modeAware:
        for key, value in currentData.items():
            if "#" + function + "#" in key and "ComboBoxSwitch#" in key:
                variableValueOrAdvanced[key.split('#')[2]] = value

    methodName = ''
    kwargNames = []
    kwargValues = []
    kwargModes = []
    for key, value in currentData.items():
        if "#" + function + "#" not in key:
            continue
        split_list = key.split('#')
        kwargName = split_list[2]
        #If no switch was found, it's a Value:
        mode = variableValueOrAdvanced.setdefault(kwargName, 'Value')
        if modeAware:
            lineEditNameVarAdv = {'Variable': 'LineEditVariable#',
                                  'Advanced': 'LineEditAdv#'}.get(mode, 'LineEdit#')
            matched = lineEditNameVarAdv in key
        else:
            mode = 'Value'
            matched = 'LineEdit' in key
        if matched:
            methodName = split_list[1]
            kwargNames.append(kwargName)
            #value could contain a file location. Thus, we need to swap out all \ for /:
            kwargValues.append(value.replace('\\', '/'))
            kwargModes.append(mode)

    return methodName, kwargNames, kwargValues, kwargModes


def getFunctionEvalTextFromCurrentData_RTAnalysis_init(function,currentData):
    methodName_method, names, values, modes = _rtAnalysisKwargsFromCurrentData(function, currentData)
    if methodName_method == '':
        return None
    #note that RT analysis methods do not have an input, thus we skipInput.
    return getEvalTextFromGUIFunction(methodName_method, names, values,
                                      partialStringStart='core=core',
                                      methodKwargTypes=modes, skipInput=True)


def getFunctionEvalTextFromCurrentData_RTAnalysis_run(function,currentData,p1,p2,pshared_data,p3):
    methodName_method, names, values, modes = _rtAnalysisKwargsFromCurrentData(function, currentData)
    if methodName_method == '':
        return None
    evalText = getEvalTextFromGUIFunction(
        methodName_method, names, values,
        partialStringStart=str(p1) + ',' + str(p2) + ',' + str(pshared_data) + ',' + str(p3),
        methodKwargTypes=modes, skipInput=True)
    return evalText.replace(methodName_method, '.run') if evalText is not None else None


def getFunctionEvalTextFromCurrentData_RTAnalysis_end(function,currentData,p1):
    methodName_method, names, values, modes = _rtAnalysisKwargsFromCurrentData(function, currentData)
    if methodName_method == '':
        return None
    evalText = getEvalTextFromGUIFunction(methodName_method, names, values,
                                          partialStringStart=str(p1),
                                          methodKwargTypes=modes, skipInput=True)
    return evalText.replace(methodName_method, '.end') if evalText is not None else None


def getFunctionEvalTextFromCurrentData_RTAnalysis_visualisation(function,currentData,p1,p2,p3,p4):
    methodName_method, names, values, _modes = _rtAnalysisKwargsFromCurrentData(
        function, currentData, modeAware=False)
    if methodName_method == '':
        return None
    evalText = getEvalTextFromGUIFunction(
        methodName_method, names, values,
        partialStringStart=str(p1) + ',' + str(p2) + ',' + str(p3) + ',' + str(p4))
    return evalText.replace(methodName_method, '.visualise') if evalText is not None else None


def getFunctionEvalText(layout,p1,p2):
    #Get the dropdown info
    moduleMethodEvalTexts = []

    methodKwargNames_method = []
    methodKwargValues_method = []
    methodName_method = ''
    # Iterate over the items in the layout
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        if widget is not None:#Catching layouts rather than widgets....
            if ("LineEdit" in widget.objectName()) and widget.isVisibleTo(layout):
                # The objectName will be along the lines of foo#bar#str
                #Check if the objectname is part of a method or part of a scoring
                split_list = widget.objectName().split('#')
                methodName_method = split_list[1]
                methodKwargNames_method.append(split_list[2])

                #Widget.text() could contain a file location. Thus, we need to swap out all \ for /:
                methodKwargValues_method.append(widget.text().replace('\\','/'))
        else:
            #If the item is a layout instead...
            if isinstance(item, QLayout):
                for index2 in range(item.count()):
                    item_sub = item.itemAt(index2)
                    widget_sub = item_sub.widget()
                    if ("LineEdit" in widget_sub.objectName()) and widget_sub.isVisibleTo(layout):
                        # The objectName will be along the lines of foo#bar#str
                        #Check if the objectname is part of a method or part of a scoring
                        split_list = widget_sub.objectName().split('#')
                        methodName_method = split_list[1]
                        methodKwargNames_method.append(split_list[2])

                        #Widget.text() could contain a file location. Thus, we need to swap out all \ for /:
                        methodKwargValues_method.append(widget_sub.text().replace('\\','/'))

                    # add distKwarg choice to Kwargs if given
                    if ("ComboBox" in widget_sub.objectName()) and widget_sub.isVisibleTo(layout) and 'dist_kwarg' in widget_sub.objectName():
                        methodKwargNames_method.append('dist_kwarg')
                        methodKwargValues_method.append(widget_sub.currentText())
                    # add timeKwarg choice to Kwargs if given
                    if ("ComboBox" in widget_sub.objectName()) and widget_sub.isVisibleTo(layout) and 'time_kwarg' in widget_sub.objectName():
                        methodKwargNames_method.append('time_kwarg')
                        methodKwargValues_method.append(widget_sub.currentText())

    # #If at this point there is no methodName_method, it means that the method has exactly 0 req or opt kwargs. Thus, we simply find the value of the QComboBox which should be the methodName:
    # if methodName_method == '':
    #     for index in range(all_layouts.count()):
    #         item = all_layouts.itemAt(index)
    #         widget = item.widget()
    #         if isinstance(widget,QComboBox) and widget.isVisibleTo(self.tab_processing) and className in widget.objectName():
    #             if className == 'Finding':
    #                 methodName_method = functionNameFromDisplayName(widget.currentText(),getattr(self,f"Finding_functionNameToDisplayNameMapping{polarity}"))
    #             elif className == 'Fitting':
    #                 methodName_method = functionNameFromDisplayName(widget.currentText(),getattr(self,f"Fitting_functionNameToDisplayNameMapping{polarity}"))

    #Function call: get the to-be-evaluated text out, giving the methodName, method KwargNames, methodKwargValues, and 'function Type (i.e. cellSegmentScripts, etc)' - do the same with scoring as with method
    if methodName_method != '':
        EvalTextMethod = getEvalTextFromGUIFunction(methodName_method, methodKwargNames_method, methodKwargValues_method,partialStringStart=str(p1)+','+str(p2))
        #append this to moduleEvalTexts
        moduleMethodEvalTexts.append(EvalTextMethod)

    if moduleMethodEvalTexts is not None and len(moduleMethodEvalTexts) > 0:
        return moduleMethodEvalTexts[0]
    else:
        return None
    
def getEvalTextFromGUIFunction(methodName, methodKwargNames, methodKwargValues, partialStringStart=None, removeKwargs=None, methodKwargTypes = None, nodzInfo = None,skipInput=False):
    #--------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #methodName: the physical name of the method, i.e. StarDist.StarDistSegment
    #methodKwargNames: found kwarg NAMES from the GUI
    #methodKwargValues: found kwarg VALUES from the GUI
    #methodTypeString: type of method, i.e. 'function Type' (e.g. CellSegmentScripts, CellScoringScripts etc)'
    #Optionals: partialStringStart: gives a different start to the partial eval-string
    #Optionals: removeKwargs: removes kwargs from assessment (i.e. for scoring script, where this should always be changed by partialStringStart)
    #--------------------------------------------------------------------------------------------------------------------------------------------------------------------
    specialcaseKwarg = [] #Kwarg where the special case is used
    specialcaseKwargPartialStringAddition = [] #text to be eval-ed in case this kwarg is found
    
    #Addition of Value/Variable/Advanced:
    #Assumption is normally all value, so:
    if methodKwargTypes == None:
        methodKwargTypes = ['Value']*len(methodKwargNames)
    
    #We have the method name and all its kwargs, so:
    if len(methodName)>0: #if the method exists
        #Check if all req. kwargs have some value
        inputKwargs = []
        if not skipInput:
            for k in range(len(inputFromFunction(methodName)[0])):
                inputKwargs.append(inputFromFunction(methodName)[0][k]['name'])
        
        reqKwargs = reqKwargsFromFunction(methodName)
        
        #Simply append the input to the req
        reqKwargs = inputKwargs+reqKwargs
        #Remove values from this array if wanted
        if removeKwargs is not None:
            for removeKwarg in removeKwargs:
                if removeKwarg in reqKwargs:
                    reqKwargs.remove(removeKwarg)
                else:
                    #nothing, but want to make a note of this (log message)
                    reqKwargs = reqKwargs
        #Stupid dummy-check whether we have the reqKwargs in the methodKwargNames, which we should (basically by definition)

        ignoreQuotes = False
        if all(elem in set(methodKwargNames) for elem in reqKwargs):
            allreqKwargsHaveValue = True
            for id in range(0,len(reqKwargs)):
                #First find the index of the function-based reqKwargs in the GUI-based methodKwargNames. 
                GUIbasedIndex = methodKwargNames.index(reqKwargs[id])
                #Get the value of the kwarg - we know the name already now due to reqKwargs.
                kwargvalue = methodKwargValues[GUIbasedIndex]
                if kwargvalue == '':
                    allreqKwargsHaveValue = False
                    logging.error(f'Missing required keyword argument in {methodName}: {reqKwargs[id]}, NOT CONTINUING')
            if allreqKwargsHaveValue:
                #If we're at this point, all req kwargs have a value, so we can run!
                #Get the string for the required kwargs
                if partialStringStart is not None:
                    partialString = partialStringStart
                else:
                    partialString = ''
                for id in range(0,len(reqKwargs)):
                    #First find the index of the function-based reqKwargs in the GUI-based methodKwargNames. 
                    GUIbasedIndex = methodKwargNames.index(reqKwargs[id])
                    #Get the value of the kwarg - we know the name already now due to reqKwargs.
                    kwargvalue = methodKwargValues[GUIbasedIndex]
                    #Change this value if it's a variable or advanced:
                    if methodKwargTypes[GUIbasedIndex] == 'Variable':
                        #name@origin.
                        # kwargvalue = nodz_evaluateVar(kwargvalue, nodzInfo)
                        originNodeName = kwargvalue.split('@')[1]
                        variableName = kwargvalue.split('@')[0]
                        # #Find the correct node
                        # for node in nodzInfo.nodes:
                        #     if node.name == originNodeName:
                        #         #Find the correct variable data
                        #         varData = node.variablesNodz[variableName]['data']
                        #         #Set it to this kwarg value - str allways
                        
                        if originNodeName == 'Global':
                            kwargvalue = "nodzInfo.globalVariables['"+variableName+"']['data']"
                        elif originNodeName == 'Core':
                            kwargvalue = "nodzInfo.coreVariables['"+variableName+"']['data']"
                        else:
                            kwargvalue = "nodeDict['"+originNodeName+"'].variablesNodz['"+variableName+"']['data']"
                        ignoreQuotes = True #ignore quotes - use it as a variable, not a string
                                # break
                    elif methodKwargTypes[GUIbasedIndex] == 'Advanced':
                        logging.error('To implement!')
                    
                    #Add a comma if there is some info in the partialString already
                    if partialString != '':
                        partialString+=","
                    #Check for special requests of kwargs, this is normally used when pointing to the output of a different value
                    if reqKwargs[id] in specialcaseKwarg:
                        #Get the index
                        ps_index = specialcaseKwarg.index(reqKwargs[id])
                        #Change the partialString with the special case
                        partialString+=eval(specialcaseKwargPartialStringAddition[ps_index])
                    else:
                        if ignoreQuotes:
                            partialString+=reqKwargs[id]+"="+kwargvalue
                            ignoreQuotes = False #default back to not ignoring
                        else:
                            partialString+=reqKwargs[id]+"=\""+kwargvalue+"\""
                #Add the optional kwargs if they have a value
                optKwargs = optKwargsFromFunction(methodName)
                for id in range(0,len(optKwargs)):
                    if methodKwargValues[id+len(reqKwargs)] != '':
                        if partialString != '':
                            partialString+=","
                        partialString+=optKwargs[id]+"=\""+methodKwargValues[methodKwargNames.index(optKwargs[id])]+"\""
                #Add the distribution kwarg if it exists
                if 'dist_kwarg' in methodKwargNames:
                    partialString += ",dist_kwarg=\""+methodKwargValues[methodKwargNames.index('dist_kwarg')]+"\""
                #Add the time fit if it exists
                if 'time_kwarg' in methodKwargNames:
                    partialString += ",time_kwarg=\""+methodKwargValues[methodKwargNames.index('time_kwarg')]+"\""
                segmentEval = methodName+"("+partialString+")"
                return segmentEval
            else:
                logging.error('NOT ALL KWARGS PROVIDED!')
                return None
        else:
            logging.error('SOMETHING VERY STUPID HAPPENED')
            return None
        

def _rtAnalysisClassName(rt_analysis_info):
    """Map an RT-analysis panel's selected dropdown entry to its dotted node name."""
    functionDispName = rt_analysis_info['__selectedDropdownEntryRTAnalysis__']
    for function in rt_analysis_info['__displayNameFunctionNameMap__']:
        if function[0] == functionDispName:
            return function[1]
    return None


#region T-G4: bound node dispatch
# `realTimeAnalysis_run` used to rebuild a Python call expression from the kwarg
# dict and eval() it on *every analysed frame* (~13us to compile() alone, plus
# metadata re-derivation, plus a currentData rescan with per-key split('#')), and
# `realTimeAnalysis_visualisation` did the same thing on the GUI thread. None of
# it can change unless the user edits the node's parameter panel -- which is what
# `BoundNode.signature` detects, cheaply, instead of re-deriving unconditionally.
_BOUND_NODE_ATTR = '_glados_bound_node'

# Escape hatch: GLADOS_RT_EVAL_DISPATCH=1 restores the pre-T-G4 eval() dispatch
# for run/end/visualise. Read once, at import.
RT_ANALYSIS_USE_EVAL_DISPATCH = os.environ.get('GLADOS_RT_EVAL_DISPATCH', '') == '1'


@dataclass(frozen=True)
class BoundNode:
    """Everything needed to call one RT-analysis node, resolved once.

    Deliberately a dataclass and not a dict/list/tuple: it is stashed on the node
    instance, and `AnalysisClass._subprocess_analysis_worker` pickles every
    plain-data attribute of that instance back to the parent after each frame
    (`_SUBPROCESS_SNAPSHOT_TYPES`). A dataclass is not in that tuple, so this
    never crosses the process boundary.
    """
    className: str
    metadata: dict
    kwargs: 'BoundKwargs'                 # run() and end() take the same set
    visualisationKwargs: 'BoundKwargs'
    signature: tuple


def _rtAnalysisBindingSignature(rt_analysis_info):
    """Cheap fingerprint of the panel values a binding was built from.

    A user editing a kwarg while the analysis runs mutates `currentData` in
    place, and that used to take effect on the next frame because every frame
    re-derived everything. Comparing this tuple keeps that behaviour at a
    fraction of the cost.
    """
    return tuple(rt_analysis_info.items())


def buildBoundNode(rt_analysis_info, nodzInfo=None, signature=None):
    """Resolve a node's kwargs (run/end and visualise) once, from `currentData`."""
    className = _rtAnalysisClassName(rt_analysis_info)
    nodeDict = createNodeDictFromNodes(nodzInfo.nodes) if nodzInfo is not None else None

    methodName, names, values, modes = _rtAnalysisKwargsFromCurrentData(className, rt_analysis_info)
    kwargs = bindKwargsFromGUIFunction(methodName or className, names, values,
                                       methodKwargTypes=modes, skipInput=True,
                                       nodzInfo=nodzInfo, nodeDict=nodeDict)

    #The visualisation path deliberately keeps its looser matching and its
    #skipInput=False - see Documentation/rt_analysis_parameters.md section 4.
    visMethodName, visNames, visValues, visModes = _rtAnalysisKwargsFromCurrentData(
        className, rt_analysis_info, modeAware=False)
    try:
        visualisationKwargs = bindKwargsFromGUIFunction(
            visMethodName or className, visNames, visValues, methodKwargTypes=visModes,
            nodzInfo=nodzInfo, nodeDict=nodeDict)
    except Exception:  # noqa: BLE001
        #A node that never visualises must not fail to *run* because of a quirk
        #in the metadata its visualise binding reads. The error surfaces from
        #realTimeAnalysis_visualisation instead, where it is actionable.
        logging.debug('Could not bind visualisation kwargs for %s', className, exc_info=True)
        visualisationKwargs = None

    #kwargs is None when a required kwarg has no value; the error is raised at
    #the call site, which knows whether it is run/end or visualise that failed.
    return BoundNode(
        className=className,
        metadata=_nodeFunctionEntry(className) or {},
        kwargs=kwargs,
        visualisationKwargs=visualisationKwargs,
        signature=_rtAnalysisBindingSignature(rt_analysis_info) if signature is None else signature,
    )


def _boundNodeFor(RT_analysis_object, rt_analysis_info, nodzInfo=None):
    """Return the node's BoundNode, rebuilding it only if the panel changed."""
    signature = _rtAnalysisBindingSignature(rt_analysis_info)
    bound = getattr(RT_analysis_object, _BOUND_NODE_ATTR, None)
    if bound is not None:
        try:
            if bound.signature == signature:
                return bound
        except Exception:  # noqa: BLE001 - an exotic unequal-comparable value just rebinds
            logging.debug('RT-analysis binding signature could not be compared, rebinding', exc_info=True)
        logging.debug('RT-analysis parameters changed, rebinding %s', getattr(bound, 'className', '?'))
    bound = buildBoundNode(rt_analysis_info, nodzInfo=nodzInfo, signature=signature)
    try:
        setattr(RT_analysis_object, _BOUND_NODE_ATTR, bound)
    except (AttributeError, TypeError):
        #A node using __slots__ cannot carry the binding; it just rebinds per call.
        logging.debug('Could not cache the binding on %r', type(RT_analysis_object))
    return bound
#endregion


def realTimeAnalysis_init(rt_analysis_info,core=None, nodzInfo=None):
    #Get the classname from rt_analysis_info
    className = _rtAnalysisClassName(rt_analysis_info)

    #Bind the node's kwargs once, here, with each value coerced to the type its
    #__function_metadata__ declares (T-G2). This used to build a Python call
    #expression ("LaserAdjustment.laser_adjustment(core=core, Laser_id='X',
    #maxFrame='100')") that dispatch_from_eval_text then re-parsed with ast and
    #eval'ed argument-by-argument, which is also why every value reached the node
    #as a string regardless of its declared type.
    bound = buildBoundNode(rt_analysis_info, nodzInfo=nodzInfo)
    if bound.kwargs is None:
        raise NodeDispatchError(
            f"Cannot start RT-analysis node {className!r}: its required kwargs are incomplete"
        )

    from glados_pycromanager.autonomous import registry as _registry
    RT_analysis_object = _registry.dispatch(className, core=core, **bound.kwargs.resolve())
    try:
        setattr(RT_analysis_object, _BOUND_NODE_ATTR, bound)
    except (AttributeError, TypeError):
        logging.debug('Could not cache the binding on %r', type(RT_analysis_object))
    return RT_analysis_object


def realTimeAnalysis_run(RT_analysis_object,rt_analysis_info,v1,v2,vshared_data,v3, nodzInfo=None):
    if RT_ANALYSIS_USE_EVAL_DISPATCH:
        return _realTimeAnalysis_run_viaEval(RT_analysis_object, rt_analysis_info, v1, v2, vshared_data, v3, nodzInfo)
    bound = _boundNodeFor(RT_analysis_object, rt_analysis_info, nodzInfo)
    if bound.kwargs is None:
        raise NodeDispatchError(f"RT-analysis node {bound.className!r}: required kwargs are incomplete")
    return RT_analysis_object.run(v1, v2, vshared_data, v3, **bound.kwargs.resolve())


def realTimeAnalysis_end(RT_analysis_object,rt_analysis_info,v1,nodzInfo = None):
    if RT_ANALYSIS_USE_EVAL_DISPATCH:
        return _realTimeAnalysis_end_viaEval(RT_analysis_object, rt_analysis_info, v1, nodzInfo)
    bound = _boundNodeFor(RT_analysis_object, rt_analysis_info, nodzInfo)
    if bound.kwargs is None:
        raise NodeDispatchError(f"RT-analysis node {bound.className!r}: required kwargs are incomplete")
    return RT_analysis_object.end(v1, **bound.kwargs.resolve())


def realTimeAnalysis_visualisation(RT_analysis_object,rt_analysis_info,v1,v2,v3,v4):
    if RT_ANALYSIS_USE_EVAL_DISPATCH:
        return _realTimeAnalysis_visualisation_viaEval(RT_analysis_object, rt_analysis_info, v1, v2, v3, v4)
    logging.debug('Attempting to visualise RT Analysis')
    bound = _boundNodeFor(RT_analysis_object, rt_analysis_info)
    if bound.visualisationKwargs is None:
        raise NodeDispatchError(f"RT-analysis node {bound.className!r}: required kwargs are incomplete")
    result = RT_analysis_object.visualise(v1, v2, v3, v4, **bound.visualisationKwargs.resolve())
    logging.debug(result)
    return result


#region T-G4 fallback: the pre-bind eval() dispatch, kept behind
#GLADOS_RT_EVAL_DISPATCH=1 for one release so a node that misbehaves under bound
#dispatch has an escape hatch that does not need a code change.
def _realTimeAnalysis_run_viaEval(RT_analysis_object,rt_analysis_info,v1,v2,vshared_data,v3, nodzInfo=None):
    className = _rtAnalysisClassName(rt_analysis_info)
    evalText = getFunctionEvalTextFromCurrentData_RTAnalysis_run(className,rt_analysis_info,'v1','v2','vshared_data','v3')
    nodeDict = createNodeDictFromNodes(nodzInfo.nodes) if nodzInfo is not None else None  # noqa: F841 - read by eval
    return eval("RT_analysis_object" + evalText)  #type:ignore


def _realTimeAnalysis_end_viaEval(RT_analysis_object,rt_analysis_info,v1,nodzInfo = None):
    className = _rtAnalysisClassName(rt_analysis_info)
    evalText = getFunctionEvalTextFromCurrentData_RTAnalysis_end(className,rt_analysis_info,'v1')
    nodeDict = createNodeDictFromNodes(nodzInfo.nodes) if nodzInfo is not None else None  # noqa: F841 - read by eval
    return eval("RT_analysis_object" + evalText)  #type:ignore


def _realTimeAnalysis_visualisation_viaEval(RT_analysis_object,rt_analysis_info,v1,v2,v3,v4):
    className = _rtAnalysisClassName(rt_analysis_info)
    evalText = getFunctionEvalTextFromCurrentData_RTAnalysis_visualisation(className,rt_analysis_info,'v1','v2','v3','v4')
    logging.debug('Attempting to visualise RT Analysis')
    result = eval("RT_analysis_object" + evalText)  #type:ignore
    logging.debug(result)
    return result
#endregion


def realTimeAnalysis_getDelay(rt_analysis_info,runOrVis='run'):
    indexv = next(i for i, sublist in enumerate(rt_analysis_info['__displayNameFunctionNameMap__']) if sublist[0] == rt_analysis_info['__selectedDropdownEntryRTAnalysis__'])
    
    wrapperName = rt_analysis_info['__displayNameFunctionNameMap__'][indexv][1].split(".")[0]
    functionMetadata = _node_metadata(wrapperName)
    functionMetadata2 = functionMetadata[rt_analysis_info['__displayNameFunctionNameMap__'][indexv][1].split(".")[1]]
    if runOrVis == 'run':
        if 'run_delay' not in functionMetadata2:
            delay = 10 #Default value for run
        else:
            delay = functionMetadata2['run_delay']
    elif runOrVis == 'visualise':
        if 'visualise_delay' not in functionMetadata2:
            delay = 200 #Default value for vis
        else:
            delay = functionMetadata2['visualise_delay']

    return delay

def realTimeAnalysis_snapshotAttrs(rt_analysis_info):
    """Return the attribute names a subprocess-isolated node wants mirrored back.

    See `AnalysisProcess_customFunction`: `.visualise()` needs a live napari
    layer, so it runs against a shadow instance in *this* process whose
    plain-data attributes are refreshed from the child after each frame. That
    mirror used to be every picklable attribute on the node, pickled and shipped
    per frame — for `RealTimeFFT` that meant the full-size FFT array *and* the
    cached Tukey window, every frame (T-G5).

    A node opts in by listing the attributes its `visualise()` actually reads, in
    a `"__snapshot_attrs__"` key of its `__function_metadata__` entry. Declaring
    nothing means nothing is mirrored. A node needing something more dynamic can
    instead define a `snapshot()` method returning a dict, which takes precedence.

    Returns an empty list for anything that is not a resolvable node (the
    plain-string sentinels used elsewhere, test doubles, ...).
    """
    try:
        entry = _nodeFunctionEntry(_rtAnalysisClassName(rt_analysis_info))
    except (KeyError, TypeError, AttributeError):
        return []
    if not entry:
        return []
    return list(entry.get('__snapshot_attrs__', []))


#: Cache for :func:`nodeRunNeedsLiveContext`, keyed by dotted node name.
#: Cleared with the stem->module cache, since it is derived from the class the
#: stem resolves to.
_NODE_LIVE_CONTEXT_CACHE: dict[str, bool] = {}

#: Names that are None inside a subprocess-isolated node's run() (see
#: AnalysisClass._subprocess_analysis_worker).
_LIVE_CONTEXT_NAMES = ('core', 'shared_data', 'nodzInfo')


def nodeRunNeedsLiveContext(functionname) -> bool:
    """True when a node's ``run()`` dereferences the live in-process context.

    Reads the node's own source and looks for attribute access on ``core``,
    ``shared_data`` or ``nodzInfo`` — all three of which are ``None`` inside a
    subprocess-isolated worker, so such a node would raise on its first frame.

    This is the safety net under the inverted default (T-G10): a node that
    declares neither ``__runInSubprocess__`` nor ``__needsLiveCore__`` is
    third-party code dropped into the AppData plugin folder, and isolating it
    blindly would break it with an ``AttributeError`` in another process.
    Conservative on doubt: anything that cannot be resolved or parsed counts as
    needing the live context. It cannot see indirection (a helper that
    dereferences a passed-in ``shared_data``), which is why an explicit
    ``__needsLiveCore__`` is still the supported way to say so.
    """
    dottedName = str(functionname)
    cached = _NODE_LIVE_CONTEXT_CACHE.get(dottedName)
    if cached is not None:
        return cached
    needsLiveContext = True
    try:
        runMethod = getattr(_resolve_node_obj(dottedName), 'run')
        tree = ast.parse(textwrap.dedent(inspect.getsource(runMethod)))
        needsLiveContext = any(
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in _LIVE_CONTEXT_NAMES
            for node in ast.walk(tree)
        )
    except Exception as exc:  # noqa: BLE001 - unreadable source must not isolate blindly
        logging.debug('Could not inspect %s.run() for live-context use (%s); '
                      'assuming it needs the live context', dottedName, exc)
    _NODE_LIVE_CONTEXT_CACHE[dottedName] = needsLiveContext
    return needsLiveContext


#: What a node gets when its `__function_metadata__` says nothing about
#: subprocess isolation. Inverted by T-G10: a node that cannot be isolated
#: declares `"__needsLiveCore__": True` rather than relying on the default.
#: Every shipped node declares one or the other explicitly, so this decides
#: only what a node dropped into the AppData plugin folder gets - and the
#: safe answer for unknown third-party code holding the GIL is "its own
#: process". The Adv.-settings kill switch turns it off globally.
RT_SUBPROCESS_ISOLATION_DEFAULT = True


def realTimeAnalysis_runInSubprocess(rt_analysis_info, shared_data=None) -> bool:
    """Return whether the selected RT-analysis node should run in a subprocess.

    See https://github.com/kjamartens/Gladoscopy/issues/16 — a node run in a
    separate OS process (AnalysisProcess_customFunction) instead of a QThread
    cannot starve the Qt main thread with a GIL-heavy compute, whatever the
    underlying library does.

    Three metadata-level answers, in order of precedence:

    1. ``"__needsLiveCore__": True`` — the node reads something that does not
       cross a process boundary: the live ``core``, ``shared_data``, or
       ``nodzInfo``. Never isolated, whatever else is declared. In the child,
       ``run()`` receives ``None`` for all three (see
       ``_subprocess_analysis_worker``), so such a node would silently degrade
       or raise.
    2. ``"__runInSubprocess__"`` — the explicit per-node answer.
    3. :data:`RT_SUBPROCESS_ISOLATION_DEFAULT` — what a node that says neither
       gets.

    ``shared_data.config.rt_analysis_config.subprocess_isolation`` (Adv.
    settings, "RT-analysis: use a separate CPU core (subprocess)") is a
    global kill switch on top of all three: when set to "False" it forces every
    node back onto the same-process QThread path. ``shared_data`` is optional so
    existing/test call sites that don't have it keep the pure per-node behaviour.
    """
    if shared_data is not None:
        global_setting = getattr(shared_data.config.rt_analysis_config, 'subprocess_isolation', 'True')
        if str(global_setting) == 'False':
            return False

    indexv = next(i for i, sublist in enumerate(rt_analysis_info['__displayNameFunctionNameMap__']) if sublist[0] == rt_analysis_info['__selectedDropdownEntryRTAnalysis__'])

    wrapperName = rt_analysis_info['__displayNameFunctionNameMap__'][indexv][1].split(".")[0]
    functionMetadata = _node_metadata(wrapperName)
    functionMetadata2 = functionMetadata[rt_analysis_info['__displayNameFunctionNameMap__'][indexv][1].split(".")[1]]
    if functionMetadata2.get('__needsLiveCore__', False):
        return False
    explicit = functionMetadata2.get('__runInSubprocess__')
    if explicit is not None:
        return bool(explicit)
    if not RT_SUBPROCESS_ISOLATION_DEFAULT:
        return False
    #An undeclared node is third-party code (dropped into the AppData plugin
    #folder). Before isolating it, check the one thing isolation actually
    #breaks: a run() that dereferences core/shared_data/nodzInfo, all of which
    #are None in the child.
    dottedName = rt_analysis_info['__displayNameFunctionNameMap__'][indexv][1]
    if nodeRunNeedsLiveContext(dottedName):
        logging.info("Not isolating %s: its run() reads the live core/shared_data/nodzInfo. "
                     "Declare \"__needsLiveCore__\": True to make that explicit.", dottedName)
        return False
    return True

class SmallWindow(QMainWindow):
    """ 
    General class that creates a small popup window to have some data. Mostly used for utility functions.
    """
    
    #Create a small window that pops up
    def __init__(self, parent=None, windowTitle="Small Window"):
        super().__init__(parent)
        self.setWindowTitle(windowTitle)
        self.resize(300, 200)

        try:
            # Set the window icon to the parent's icon
            self.setWindowIcon(QIcon(findIconFolder()+os.sep+'GladosIcon.ico'))
        except Exception as e:
            logging.error(f'Cannot find icon folder with exception: {e}')
        
        #Add a layout
        layout = QVBoxLayout()
        self.central_widget = QWidget()  # Create a central widget for the window
        self.setCentralWidget(self.central_widget) # Set it
        self.central_widget.setLayout(layout) # Set the layout on the widget
        
    #Function to find/select a file and add it to the lineedit
    def openFileDialog(self,fileArgs = "All Files (*)"):
        options = QFileDialog.Options()
        #Try to get current folder from self.fileLocationLineEdit:
        try:
            #Split the filelocationtext on slash:
            filefolder = self.fileLocationLineEdit.text().split('/')
            #Get all but the last element of this:
            filefolder = '/'.join(filefolder[:-1])
            folderName = filefolder
        except (AttributeError, IndexError, TypeError):
            folderName = ""
        
        file_name, _ = QFileDialog.getOpenFileName(None, "Open File", folderName, fileArgs, options=options)
        if file_name:
            self.fileLocationLineEdit.setText(file_name)
        
        return file_name
    
    #Add extra text before the period
    def addTextPrePriod(self,lineedit,LineEditText,textAddPrePeriod = ""):
        #Add the textAddPrePriod directly before the last found period in the LineEditText:
        if textAddPrePeriod != "":
            try:
                LineEditText = LineEditText.split('.')
                LineEditText[-2] = LineEditText[-2]+textAddPrePeriod
                LineEditText = '.'.join(LineEditText)
            except (IndexError, AttributeError):
                pass
        lineedit.setText(LineEditText)
    
    def addDescription(self,description):
        #Create a horizontal box layout:
        layout = QHBoxLayout()
        #add the description as text, allowing for multi-line text:
        self.descriptionLabel = QLabel(description)
        self.descriptionLabel.setWordWrap(True)
        #Add the label to the layout:
        layout.addWidget(self.descriptionLabel)
        #Add the layout to the central widget:
        self.centralWidget().layout().addLayout(layout) #type:ignore
        return self.descriptionLabel
    
    def addButton(self,buttonText="Button"):
        #Create a horizontal box layout:
        layout = QHBoxLayout()
        #add a button:
        self.button = QPushButton(buttonText)
        #Add the button to the layout:
        layout.addWidget(self.button)
        #Add the layout to the central widget:
        self.centralWidget().layout().addLayout(layout) #type:ignore
        return self.button
    
    def addTextEdit(self,labelText = "Text edit:", preFilledText = ""):
        #Create a horizontal box layout:
        layout = QHBoxLayout()
        #add a label and text edit:
        self.textEdit = QLineEdit()
        self.textEdit.setText(preFilledText)
        #Add the label and text edit to the layout:
        layout.addWidget(QLabel(labelText))
        layout.addWidget(self.textEdit)
        #Add the layout to the central widget:
        self.centralWidget().layout().addLayout(layout) #type:ignore
        return self.textEdit
    
    #Add a file information label/text/button:
    def addFileLocation(self, labelText="File location:", textAddPrePeriod = ""):
        #Create a horizontal box layout:
        layout = QHBoxLayout()
        #add a label, line edit and button:
        self.fileLocationLabel = QLabel(labelText)
        self.fileLocationLineEdit = QLineEdit()
        LineEditText = self.parent.dataLocationInput.text()
        
        self.addTextPrePriod(self.fileLocationLineEdit,LineEditText,textAddPrePeriod)
        
        self.fileLocationButton = QPushButton("...")
        self.fileLocationButton.clicked.connect(lambda: self.openFileDialog(fileArgs = "All Files (*)")) #type:ignore
        
        #Add the label, line edit and button to the layout:
        layout.addWidget(self.fileLocationLabel)
        layout.addWidget(self.fileLocationLineEdit)
        layout.addWidget(self.fileLocationButton)
        #Add the layout to the central widget:
        self.centralWidget().layout().addLayout(layout) #type:ignore
        return self.fileLocationLineEdit

    def addHtml(self, htmlfile, width=700, height=800):
        # Body moved to glados_pycromanager.ui.markdown_view (Phase 7.4).
        from glados_pycromanager.ui.markdown_view import add_html_to_window

        add_html_to_window(self, htmlfile, width=width, height=height)

    def addMarkdown(self, mdfile, width=700, height=800):
        # Body moved to glados_pycromanager.ui.markdown_view (Phase 7.4).
        from glados_pycromanager.ui.markdown_view import add_markdown_to_window

        add_markdown_to_window(self, mdfile, width=width, height=height)
    
class HelpGroupBox:
    def __init__(self,parent):
        self.parent = parent
        self.helpGroupBox = QGroupBox("Help")
        newgridlayout = QGridLayout()
        self.helpGroupBox.setLayout(newgridlayout)
        #Add a User Manual Button:
        newgridlayout.addWidget(QLabel('Glados-Pycromanager\n\nCreated by Dr. Koen J.A. Martens\nkoenjamartens{at}gmail.com\n\nAutonomous microscopy is very much a work in progress!'))
        button1 = QPushButton('User Manual')
        button1.clicked.connect(lambda index: self.quickStartMenu())
        newgridlayout.addWidget(button1)
        button2 = QPushButton('Developer Manual')
        button2.clicked.connect(lambda index: self.developerMenu())
        newgridlayout.addWidget(button2)
        button3 = QPushButton('Complete software info')
        button3.clicked.connect(lambda index: self.DeveloperAdvMenu())
        newgridlayout.addWidget(button3)
        
        # I need to store references to the windows so they aren't garbage-collected
        self.quick_start_window = None
        self.devMenuWindow = None
        
    def quickStartMenu(self):
        """
        Shows the UserManual.md file
        """
        try:
            self.quick_start_window = SmallWindow()
            QApplication.processEvents()
            self.quick_start_window.setWindowTitle('Quick start / User Manual')
            QApplication.processEvents()
            
            #TODO: check that .MD help file still works
            # if is_pip_installed():
            package_path = os.path.dirname(glados_pycromanager.__file__)
            self.quick_start_window.addMarkdown(os.path.join(package_path, 'Documentation', 'UserManual.md'))
            # else:
            #     try:
            #         self.quick_start_window.addMarkdown(os.path.join('glados-pycromanager', 'glados_pycromanager', 'Documentation', 'UserManual.md'))
            #     except Exception as e:
            #         logging.info(f'TryException: {e}')
            #         self.quick_start_window.addMarkdown(os.path.join('glados_pycromanager', 'Documentation', 'UserManual.md'))
            QApplication.processEvents()
            self.quick_start_window.show() #Show
            self.quick_start_window.raise_() # Bring to the front
            self.quick_start_window.activateWindow() # Give focus
        except Exception as e:
            logging.error(f'Could not open quick start window. {e}')
    
    def developerMenu(self):
        """
        Shows the DeveloperManual.md file
        """
        try:
            self.devMenuWindow = SmallWindow(self.parent)
            QApplication.processEvents()
            self.devMenuWindow.setWindowTitle('Developer manual')
            QApplication.processEvents()
            
            #TODO check if .md help still works
            # if is_pip_installed():
            package_path = os.path.dirname(glados_pycromanager.__file__)
            self.devMenuWindow.addMarkdown(os.path.join(package_path, 'Documentation', 'DeveloperManual.md'))
            # else:
            #     try:
            #         self.devMenuWindow.addMarkdown(os.path.join('glados-pycromanager', 'glados_pycromanager', 'Documentation', 'DeveloperManual.md'))
            #     except Exception as e:
            #         logging.info(f'TryException: {e}')
            #         self.devMenuWindow.addMarkdown(os.path.join('glados_pycromanager', 'Documentation', 'DeveloperManual.md'))
            QApplication.processEvents()
            self.devMenuWindow.show() #Show
            self.devMenuWindow.raise_() # Bring to the front
            self.devMenuWindow.activateWindow() # Give focus
        except Exception as e:
            logging.error(f'Could not open developer menu. {e}')
    
    def DeveloperAdvMenu(self):
        """
        Shows the Documentation .html files file in a proper external webbrowser
        """
        try:
            #TODO check if .md help still works
            # if is_pip_installed():
            package_path = os.path.dirname(glados_pycromanager.__file__)
            htmlPath = os.path.join(package_path, 'Documentation', 'index.html')
            # else:
            #     htmlPath = (os.path.join('glados-pycromanager', 'glados_pycromanager', 'Documentation', 'index.html'))
            
            webbrowser.open('file://' + os.path.realpath(htmlPath))
        except Exception as e:
            logging.error(f'Could not open the developer advanced info. {e}')
    

def PushButtonChooseVariableCallBack(line_edit,nodzInfo):
    from FlowChart_dockWidgets import VariablesDialog
    
    #Find the associated kwarg/function:
    associatedFunction = line_edit.objectName().split('#')[1]
    associatedKwarg = line_edit.objectName().split('#')[2]
    associatedType = typeFromKwarg(associatedFunction,associatedKwarg)
    
    #open a variablesDialog:
    variablesDialog = VariablesDialog(nodzinstance=nodzInfo,typeInfo=associatedType)
    result = variablesDialog.exec()
    if result == variablesDialog.Accepted:
        lineEditText = variablesDialog.selected_entry[2]+'@'+variablesDialog.selected_entry[1]
        line_edit.setText(lineEditText)
    else:
        logging.warning("Dialog rejected (Cancel pressed or closed)")


def PushButtonAddVariableCallBack(line_edit,nodzInfo):
    from FlowChart_dockWidgets import VariablesDialog
    
    #Find the associated kwarg/function:
    associatedFunction = line_edit.objectName().split('#')[1]
    associatedKwarg = line_edit.objectName().split('#')[2]
    associatedType = typeFromKwarg(associatedFunction,associatedKwarg)
    
    #open a variablesDialog:
    variablesDialog = VariablesDialog(nodzinstance=nodzInfo,typeInfo=associatedType)
    result = variablesDialog.exec()
    if result == variablesDialog.Accepted:
        if line_edit.text() != '':
            lineEditText = line_edit.text()+' {'+variablesDialog.selected_entry[2]+'@'+variablesDialog.selected_entry[1]+'}'
        else:
            lineEditText = '{'+variablesDialog.selected_entry[2]+'@'+variablesDialog.selected_entry[1]+'}'
        line_edit.setText(lineEditText)
    else:
        logging.warning("Dialog rejected (Cancel pressed or closed)")

def _is_json_serializable(value):
    """True when `value` can go into the state JSON as-is.

    `save_state_MDA` iterates `vars(self)` and writes anything that is not a bare
    QWidget straight into the state dict. A *container* of widgets -- a list, a
    dict -- passes that check and then blows up inside `json.dump`, which by then
    has already truncated the file, so the user loses every other setting too.
    """
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


class CustomMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        # Attributes never written to the state JSON. Note the QWidget branch in
        # save_state_MDA only catches a *bare* QWidget attribute -- a container of
        # widgets (list, dict) falls through to the generic branch and would be
        # dumped verbatim, so anything holding widgets belongs here.
        # `_guiWrappers` is MDAGlados' list of the current rebuild's wrapper
        # widgets (T-F7); it crashed the whole save until it was listed.
        # The two `_mda*Timer`s are MDAGlados' T-H1 debounce QTimers.
        self.storingExceptions = ['core','layout','shared_data','gui','mda','mda_useq','data','config_groups','mainLayout','xypositionListWidget_XYGridManager','_guiWrappers','_mdaEventsUpdateTimer','_mdaStateSaveTimer']

    def save_state_globalData(self,filename):
        if os.path.exists(filename):
            #Load the mda state
            with open(filename) as file:
                state = json.load(file)
        else:
            state = {}
            state['MDA'] = {}
            state['MMControls'] = {}
            state['GlobalData'] = {}
        
        if 'MMControls' not in state:
            state['MMControls'] = {}
        if 'MDA' not in state:
            state['MDA'] = {}
        if 'GlobalData' not in state:
            state['GlobalData'] = {}
            
        #Loop over everything in self.shared_data.globalData dict and store the ['value']s:
        # for key, value in self.shared_data.globalData.items():
        #     if key not in self.storingExceptions:
        #         state['GlobalData'][key] = value['value']
                
        from dataclasses import dataclass, fields
        cfg = self.shared_data.config
        for group_field in fields(cfg):
            group = getattr(cfg, group_field.name)
            for f in fields(group):
                state['GlobalData'][f"{group_field.name}.{f.name}"] = getattr(group, f.name)
        
        with open(filename, 'w') as file:
            json.dump(state, file, indent=4)

    def save_state_MMControls(self,filename):
        if os.path.exists(filename):
            #Load the mda state
            with open(filename) as file:
                state = json.load(file)
        else:
            state = {}
            state['MDA'] = {}
            state['MMControls'] = {}
            state['GlobalData'] = {}
        
        if 'MMControls' not in state:
            state['MMControls'] = {}
        if 'MDA' not in state:
            state['MDA'] = {}
        if 'GlobalData' not in state:
            state['GlobalData'] = {}
        
        import glados_pycromanager.GUI.napariGlados as napariGlados
        
        iterable = []
        
        for key, value in vars(self).items():
            iterable.append((key,value))
            if key == 'XYMoveEditField':
                for keyC in vars(self)[key]:
                    valueC = vars(self)[key][keyC]
                    iterable.append((keyC,valueC))
            if key == 'oneDStackedWidget':
                for widget_id in range(0,vars(self)[key].count()):
                    widget = vars(self)[key].widget(widget_id)
                    for m in range(1,3):
                        lineEdit = self.oneDMoveEditField[widget.objectName()][f'oneDStackedWidget_{widget.objectName()}_{m}']
                        iterable.append(("oneDStackedWidget_"+widget.objectName()+"_"+str(m),lineEdit))
            if key == 'oneDstageDropdown':
                iterable.append((key,value.currentText()))
        
        for key, value in iterable:
            saveState = None
            if isinstance(value, QWidget):
                maxParentInst = 10
                currentParent = value
                for _ in range(maxParentInst):
                    if currentParent == None:
                        break
                    currentParent = currentParent.parent()
                    #Try to figure out if it's a MMControls instance or not:
            
                    if isinstance(currentParent, napariGlados.dockWidget_MMcontrol):
                        saveState = 'MMControls'
                        break
                    else:
                        try:
                            if isinstance(currentParent.dockwidget, napariGlados.dockWidget_MMcontrol):
                                saveState = 'MMControls'
                                break
                        except AttributeError:
                            try:
                                if currentParent.type == 'MMConfig':
                                    saveState = 'MMControls'
                                    break
                            except AttributeError:
                                pass
                    
                if saveState is not None:
                    try:
                        if hasattr(value,'text') and callable(value.text):
                            textv = value.text()
                        elif hasattr(value,'currentText') and callable(value.currentText):
                            textv = value.currentText()
                        else:
                            textv = None
                    except (AttributeError, RuntimeError, TypeError):
                        textv = None
                    state[saveState][key] = {
                        'text': textv,
                        'checked': value.isChecked() if hasattr(value, 'isChecked') else None,
                        # Add more properties as needed
                    }

        with open(filename, 'w') as file:
            json.dump(state, file, indent=4)
        
        #Also save global data:
        self.save_state_globalData(filename)
            
    def save_state_MDA(self, filename):
        import glados_pycromanager.Core.MDAGlados as MDAGlados
        import glados_pycromanager.GUI.napariGlados as napariGlados
        logging.debug('SAVING STATE')
        if os.path.exists(filename):
            #Load the mda state
            with open(filename) as file:
                state = json.load(file)
        else:
            state = {}
            state['MDA'] = {}
            state['MMControls'] = {}
            state['GlobalData'] = {}
            
        if 'MMControls' not in state:
            state['MMControls'] = {}
        if 'MDA' not in state:
            state['MDA'] = {}
        if 'GlobalData' not in state:
            state['GlobalData'] = {}
            
        for key, value in vars(self).items():
            saveState = None
            if isinstance(value, QWidget):
                try:
                    maxParentInst = 10
                    currentParent = value
                    for _ in range(maxParentInst):
                        if currentParent == None:
                            break
                        if currentParent.parent == None:
                            break
                        #Rather difficult method to figure out if we're in MDA or MMControls savestate
                        if callable(currentParent.parent):
                            currentParent = currentParent.parent()
                            if isinstance(currentParent, napariGlados.dockWidget_MDA):
                                saveState = 'MDA'
                                break
                        else:
                            try:
                                currentParent = currentParent.parent
                                if isinstance(currentParent, napariGlados.dockWidget_MDA):
                                    saveState = 'MDA'
                                    break
                            except AttributeError:
                                break

                    if saveState is not None:
                        state[saveState][key] = {
                            'text': value.text() if hasattr(value, 'text') else None,
                            'checked': value.isChecked() if hasattr(value, 'isChecked') else None,
                            # Add more properties as needed
                        }
                except RuntimeError as exc:
                    #Widget was deleted (e.g. mid-rebuild teardown) - skip it.
                    logging.debug('Skipping deleted widget %s while saving state: %s', key, exc)
            else:
                if isinstance(self, MDAGlados.MDAGlados):
                    saveState = 'MDA'
                if saveState is not None:
                    if key not in self.storingExceptions:
                        # One un-encodable attribute must not cost the user every
                        # other setting in the file: json.dump writes nothing at
                        # all when it raises partway through. Check each value as
                        # it goes in, and skip (loudly) what cannot be stored.
                        if _is_json_serializable(value):
                            state[saveState][key] = value
                        else:
                            logging.warning(
                                'Not saving MDA state key %r: %s is not JSON '
                                'serializable. Add it to storingExceptions.',
                                key, type(value).__name__)

        # Encode before opening the file: `open(..., 'w')` truncates immediately,
        # so a json.dump that raises partway through would leave the user with a
        # half-written or empty state file and no settings at all.
        encoded = json.dumps(state, indent=4)
        with open(filename, 'w') as file:
            file.write(encoded)

        #Also save global data:
        self.save_state_globalData(filename)

def createNodeDictFromNodes(nodes):
    #Idea: create a dictionary where dict[nodeName] = Node.
    nodeDict = {}
    for node in nodes:
        nodeDict[node.name] = node
    
    #Add global variables
    return nodeDict

def closeAllLayers(shared_data):
    """
    Closes all the layers in napari
    """
    for layer in reversed(shared_data.napariViewer.layers):
        shared_data.napariViewer.layers.remove(layer)


def forceReset_actual(shared_data):
    """
    attempt to do whatever is necessary to reset pycromanager to a clean/functioning slate
    """
    logging.debug('Attempting force-reset!')
    import time

    from glados_pycromanager.GUI.napari_bridge import get_bridge
    core=shared_data.core

    # T-F9: this function runs on a ThreadPoolExecutor thread. Assigning
    # liveMode/mdaMode re-enters acqModeChanged, which reaches moveLayerToTop --
    # i.e. it mutates viewer.layers from a non-GUI thread. Route the two flips
    # through the bridge so that whole chain runs where it belongs. The waits
    # are bounded; forceReset's own 5 s future timeout is the outer bound.
    bridge = get_bridge(shared_data)

    def _set_mode(attribute):
        def _apply(_viewer):
            setattr(shared_data, attribute, False)
        if bridge is None:
            _apply(None)
        else:
            bridge.submit(_apply, wait=True, timeout=2.0)

    #Trying a bunch of different things:
    try:
        _set_mode('liveMode')
        logging.debug("Attempted: shared_data.liveMode=False")
    except (AttributeError, RuntimeError, TimeoutError):
        logging.debug("Attempted but failed: shared_data.liveMode=False")
    try:
        _set_mode('mdaMode')
        logging.debug("Attempted: shared_data.mdaMode=False")
    except (AttributeError, RuntimeError, TimeoutError):
        logging.debug("Attempted but failed: shared_data.mdaMode=False")
    time.sleep(0.1)
    try:
        core.stop_sequence_acquisition()
        logging.debug("Attempted: core.stop_sequence_acquisition()")
    except (AttributeError, RuntimeError, OSError):
        logging.debug("Attempted but failed: core.stop_sequence_acquisition()")
    try:
        core.stop_exposure_sequence(core.get_camera_device())
        logging.debug("Attempted: core.stop_sequence_acquisition()")
    except (AttributeError, RuntimeError, OSError):
        logging.debug("Attempted but failed: core.stop_exposure_sequence()")
    time.sleep(0.1)
    try:
        core.clear_circular_buffer()
        logging.debug("Attempted: core.clear_circular_buffer()")
    except (AttributeError, RuntimeError, OSError):
        logging.debug("Attempted but failed: core.clear_circular_buffer()")

def forceReset(shared_data):
    """
    attempt to do whatever is necessary to reset pycromanager to a clean/functioning slate
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(forceReset_actual,shared_data)
        try:
            result = future.result(timeout=5)  # Attempt for 5 seconds
        except concurrent.futures.TimeoutError:
            logging.warning("Function did not complete within 5 seconds and thus quitted")

# Phase 7.1/7.2: body moved to `glados_pycromanager.io.appdata`; shim
# kept here for back-compat with one-time DeprecationWarning per call.
import warnings as _shim_warnings_store  # noqa: E402

from glados_pycromanager.io import appdata as _appdata_store  # noqa: E402


def storeSharedData_GlobalData(shared_data):
    _shim_warnings_store.warn(
        "storeSharedData_GlobalData() has moved to glados_pycromanager.io."
        "appdata.storeSharedData_GlobalData; the GUI.utils re-export is "
        "scheduled for removal in Phase 18.1 of claude_project.md.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _appdata_store.storeSharedData_GlobalData(shared_data)

def openAdvancedSettings(shared_data):
    """
    Allow the user to change the global/advanced settings via some GUI
    """
    def acceptS(dialog,shared_data):
        #Set the current values in shared_data.config:
        #Loop over all config entries:
        for group_field in fields(shared_data.config):
            group = getattr(shared_data.config, group_field.name)
            for f in fields(group):
                if not f.metadata.get("hidden", True):
                    try:
                        if f.metadata['input_type'] == 'lineEdit':
                            setattr(group, f.name, dialog.findChild(QLineEdit, f.name).text())
                        elif f.metadata['input_type'] == 'dropdown':
                            setattr(group, f.name, dialog.findChild(QComboBox, f.name).currentText())
                        #Try to make integer/float:
                        try:
                            setattr(group, f.name,float(getattr(group, f.name)))
                        except (ValueError, TypeError):
                            pass
                        try:
                            setattr(group, f.name,int(getattr(group, f.name)))
                        except (ValueError, TypeError):
                            pass
                    except (AttributeError, KeyError, TypeError) as exc:
                        logging.warning("Couldn't save global data of entry %s: %s", f, exc)
        
        
        # for entry in shared_data.globalData:
        #     if not 'hidden' in shared_data.globalData[entry] or shared_data.globalData[entry]['hidden'] == False:
        #         try:
        #             if shared_data.globalData[entry]['inputType'] == 'lineEdit':
        #                 shared_data.globalData[entry]['value'] = dialog.findChild(QLineEdit, entry).text()
        #             elif shared_data.globalData[entry]['inputType'] == 'dropdown':
        #                 shared_data.globalData[entry]['value'] = dialog.findChild(QComboBox, entry).currentText()
        #             #Try to make integer/float:
        #             try:
        #                 shared_data.globalData[entry]['value'] = float(shared_data.globalData[entry]['value'])
        #             except:
        #                 pass
        #             try:
        #                 shared_data.globalData[entry]['value'] = int(shared_data.globalData[entry]['value'])
        #             except:
        #                 pass
        #         except:
        #             logging.warning(f"Couldn't save global data of entry {entry}")
        
        #Store in appdata
        storeSharedData_GlobalData(shared_data)

        # Apply log-level change immediately (no restart needed)
        try:
            from glados_pycromanager.observability.logger import set_log_level
            set_log_level(shared_data.config.logging_config.log_level)
        except Exception as exc:
            logging.warning("Could not apply log level: %s", exc)

        # RT-analysis nodes running in a subprocess (see AnalysisClass.
        # AnalysisProcess_customFunction) have their own, separately-spawned
        # root logger, which set_log_level() above cannot reach -- push the
        # new level to each running one explicitly.
        for entry in shared_data.RTAnalysisQueuesThreads:
            update_log_level = getattr(entry.get('Thread'), 'update_log_level', None)
            if update_log_level is not None:
                update_log_level(shared_data.config.logging_config.log_level)

        # The live-display path caches the parsed contrast-refresh interval;
        # drop it so a changed value takes effect on the next frame.
        try:
            from glados_pycromanager.GUI.napariGlados import invalidate_contrast_refresh_interval
            invalidate_contrast_refresh_interval(shared_data)
        except Exception as exc:
            logging.warning("Could not invalidate contrast-refresh cache: %s", exc)

        logging.info('advanced settings stored!')
        dialog.close()
        pass
    
    def rejectS(dialog):
        dialog.close()
    
    from PyQt5.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit
    #Create a QDialog with OK/Cancel button:
    dialog = QDialog()
    dialog.setWindowTitle("Advanced settings")

    layout = QGridLayout()
    layout.addWidget(QLabel("Please restart glados-pycromanager after changing any of these settings!"),0,0,1,2)
    currentRow = 1
    #Loop over all globalData entries:
    for group_field in fields(shared_data.config):
        group = getattr(shared_data.config, group_field.name)
        for f in fields(group):
            if not f.metadata.get("hidden", True):
                currentValue = getattr(group, f.name)
                currentRow+=1
                try:
                    label = QLabel(f.metadata['display_name'])
                    hoverInfo = f.metadata['description']
                    layout.addWidget(label,currentRow,0)
                    label.setToolTip(hoverInfo)
                    
                    typeV = f.metadata['input_type']
                    if typeV == 'lineEdit':
                        editField = QLineEdit()
                        editField.setText(str(currentValue))
                        editField.setObjectName(f.name)
                        layout.addWidget(editField,currentRow,1)
                    elif typeV == 'dropdown':
                        editField = QComboBox()
                        editField.addItems(f.metadata['options'])
                        editField.setObjectName(f.name)
                        editField.setCurrentText(str(currentValue))
                        layout.addWidget(editField,currentRow,1)
                except (AttributeError, RuntimeError):
                    pass


    button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    button_box.accepted.connect(lambda: acceptS(dialog,shared_data))
    button_box.rejected.connect(lambda: rejectS(dialog))
    layout.addWidget(button_box,99,0,1,2)

    dialog.setLayout(layout)
    
    dialog.exec_()
    pass

def getAcquisitionDimensions(shared_data):
    """Cached `getDimensionsFromAcqData` for the current acquisition (T-G8).

    Node code (`pSMLM`, `RT_counter`) used to call `getDimensionsFromAcqData`
    uncached inside `run()`, which walks every event of the acquisition in pure
    Python — all 999 of a live-mode plan — on every frame, holding the GIL.
    Reading `_mdaModeParams` at all also triggers its lazy
    `useq.MDASequence -> pycromanager event list` conversion on first access.

    Keyed on `shared_data._mdaModeParamsGeneration`, the counter the
    `_mdaModeParams` setter bumps on every assignment; the generation is read
    first, so a cache hit never touches the property. Returns None when there is
    no shared_data (a subprocess-isolated node is handed None) or no plan.
    """
    if shared_data is None:
        return None
    generation = getattr(shared_data, '_mdaModeParamsGeneration', None)
    if generation is None:
        #Not a Shared_data (a test double, say) - correct, just uncached.
        return getDimensionsFromAcqData(getattr(shared_data, '_mdaModeParams', None))
    cached = getattr(shared_data, '_dims_cache', None)
    #Compare rather than test for absence: getDimensionsFromAcqData legitimately
    #returns None, so a cached None must not read as "nothing cached yet".
    if cached is None or cached[0] != generation:
        result = getDimensionsFromAcqData(shared_data._mdaModeParams)
        shared_data._dims_cache = (generation, result)
        return result
    return cached[1]


def getDimensionsFromAcqData(acqData):
    if not acqData:
        return None
    try:
        # Single pass: accumulate unique values per dimension using sets.
        # Previous implementation made one full pass per dimension (O(n_dims × n_events)).
        seen: dict = {}
        for event in acqData:
            for dim, val in event['axes'].items():
                seen.setdefault(dim, set()).add(val)

        # Preserve dimension order from the first event (matches np.unique contract).
        dimOrder = list(acqData[0]['axes'].keys())
        uniqueEntriesAllDims = {d: np.array(sorted(seen[d])) for d in dimOrder}
        n_entries_in_dims = [len(uniqueEntriesAllDims[d]) for d in dimOrder]

        logging.debug(f"dimOrder: {dimOrder} with n_entries_in_dims: {n_entries_in_dims}")
        return dimOrder, n_entries_in_dims, uniqueEntriesAllDims
    except Exception as e:
        logging.warning("Problem with get Dimensions: %s", e)

def updateNodzVariablesTime(node):
    
    #self.nodeInfo.variablesNodz['data']['data']
    for vars in node.variablesNodz:
        node.variablesNodz[vars]['lastUpdateTime'] = time.time()
        
    logging.debug('updating nodz variables time')

def analysis_outputs_store_as_variableNodz(currentNode):
    """
    Stores the analysis output as variables - ran just before the next node is ran.
    """ 
    output = currentNode.scoring_analysis_currentData['__output__']
    for outputtype in output:
        if outputtype in currentNode.variablesNodz:
            currentNode.variablesNodz[outputtype]['data'] = output[outputtype]
        else:
            logging.error(f'Critical! Error with outputs of function {currentNode.scoring_analysis_currentData["__selectedDropdownEntryAnalysis__"]} and variable {outputtype}')
    #update the timing
    updateNodzVariablesTime(currentNode)
    
    
def customFunction_outputs_store_as_variableNodz(currentNode):
    """
    Stores the analysis output as variables - ran just before the next node is ran.
    """ 
    output = currentNode.customFunction_currentData['__output__']
    for outputtype in output:
        if outputtype in currentNode.variablesNodz:
            currentNode.variablesNodz[outputtype]['data'] = output[outputtype]
        else:
            logging.error(f'Critical! Error with outputs of function {currentNode.customFunction_currentData["__selectedDropdownEntryAnalysis__"]} and variable {outputtype}')
    #update the timing
    updateNodzVariablesTime(currentNode)


def analysis_outputs_to_variableNodz(currentNode):
    """ 
    Get the expected outputs from an analysis function, and store them as a node variableNodz. Called when a variableNode is updated or loaded. NOT when it's finished - look at analysis_outputs_store_as_variableNodz(currentNode) instead
    """
    
    if 'scoring_analysis_currentData' in vars(currentNode) and len(currentNode.scoring_analysis_currentData) > 0:
        selectedFunction = currentNode.scoring_analysis_currentData['__selectedDropdownEntryAnalysis__'] #type:ignore
        for dn in currentNode.scoring_analysis_currentData['__displayNameFunctionNameMap__']: #type:ignore
            if dn[0] == selectedFunction:
                selectedFunctionName = dn[1]
                
        #Get the outputs to put in nodz-variables
        expectedoutputs = outputFromFunction(selectedFunctionName)
        for output in expectedoutputs[0]:
            currentNode.variablesNodz[output['name']] = {} #type:ignore
            if 'type' in output:
                currentNode.variablesNodz[output['name']]['type'] = output['type'] #type:ignore
            else:
                currentNode.variablesNodz[output['name']]['type'] = None #type:ignore
            currentNode.variablesNodz[output['name']]['data'] = None #type:ignore
            if 'importance' in output:
                currentNode.variablesNodz[output['name']]['importance'] = output['importance'] #type:ignore
            else:
                currentNode.variablesNodz[output['name']]['importance'] = 'Informative' #type:ignore
            currentNode.variablesNodz[output['name']]['lastUpdateTime'] = None
            
def customFunction_outputs_to_variableNodz(currentNode):
    """ 
    Get the expected outputs from an customFunction function, and store them as a node variableNodz. Called when a variableNode is updated or loaded. NOT when it's finished - look at customFunction_outputs_store_as_variableNodz(currentNode) instead
    """
    
    if 'customFunction_currentData' in vars(currentNode) and len(currentNode.customFunction_currentData) > 0:
        selectedFunction = currentNode.customFunction_currentData['__selectedDropdownEntryAnalysis__'] #type:ignore
        for dn in currentNode.customFunction_currentData['__displayNameFunctionNameMap__']: #type:ignore
            if dn[0] == selectedFunction:
                selectedFunctionName = dn[1]
                
        #Get the outputs to put in nodz-variables
        expectedoutputs = outputFromFunction(selectedFunctionName)
        for output in expectedoutputs[0]:
            currentNode.variablesNodz[output['name']] = {} #type:ignore
            if 'type' in output:
                currentNode.variablesNodz[output['name']]['type'] = output['type'] #type:ignore
            else:
                currentNode.variablesNodz[output['name']]['type'] = None #type:ignore
            currentNode.variablesNodz[output['name']]['data'] = None #type:ignore
            if 'importance' in output:
                currentNode.variablesNodz[output['name']]['importance'] = output['importance'] #type:ignore
            else:
                currentNode.variablesNodz[output['name']]['importance'] = 'Informative' #type:ignore
            currentNode.variablesNodz[output['name']]['lastUpdateTime'] = None
            


def getCoreDevicesOfDeviceType(core,devicetype):
    """
    #Find all devices that have a specific devicetype
    #Look at https://javadoc.scijava.org/Micro-Manager-Core/mmcorej/DeviceType.html 
    #for all devicetypes
    """
    #Get devices
    devices = core.get_loaded_devices() #type:ignore
    try:
        #Java-proxy StrVector (has .size()/.get()) vs a plain list/tuple of names
        #(e.g. PYCROMANAGER_PYTHON backend) - normalize to a plain list either way.
        if hasattr(devices, 'size') and hasattr(devices, 'get'):
            devices = [devices.get(i) for i in range(devices.size())]
        else:
            devices = list(devices)
        devicesOfType = []
        #Loop over devices
        for device in devices:
            if core.get_device_type(device).to_string() == devicetype: #type:ignore
                logging.debug("found " + device + " of type " + devicetype)
                devicesOfType.append(device)
        return devicesOfType
    except (RuntimeError, OSError, AttributeError, KeyError, IndexError) as exc:
        logging.warning('Enumerating devices of type %s failed: %s', devicetype, exc)
        return []
def updateAutonousErrorWarningInfo(shared_data,updateInfo='All'):
    """
    Update the autonomous error, warning, and info icons and tooltips in the GUI based on the shared data.

    This function is responsible for updating the appearance and tooltips of the error, warning, and info icons in the GUI based on the information stored in the `shared_data` object. It sets the icons to grayscale if there are no errors, warnings, or info messages to display, and activates the icons and sets the tooltips accordingly if there are messages to display.

    Args:
        shared_data (Shared_data): The shared data object containing the information about errors, warnings, and info messages.
        updateInfo (str, optional): Specifies which information to update. Defaults to 'All', which updates all error, warning, and info messages.
    """
    if updateInfo == 'All': #Willa lways be the case, deprecated is ['Error','Warning','Info']
        
        from glados_pycromanager.GUI.sharedFunctions import Shared_data
        
        if isinstance(shared_data,Shared_data):
            sharedData = shared_data
        elif isinstance(shared_data.parent, Shared_data):
            sharedData = shared_data.parent
        
        if sharedData == None or sharedData.nodzInstance == None: 
            return
        errorIcon = sharedData.nodzInstance.errorIcon
        warningIcon = sharedData.nodzInstance.warningIcon
        infoIcon = sharedData.nodzInstance.infoIcon
        
        #Set all to inactive icons/grayscale:
        setWarningErrorInfoIcon(warningIcon,'warning',findIconFolder(),alteration='grayscale')

        infoToolTip = ''
        #Showcase on how to activate/set infoToolTip:
        if sharedData.warningErrorInfoInfo['Info']['LastNodeRan'] != None:
            infoToolTip+= "Last Node Ran: " + sharedData.warningErrorInfoInfo['Info']['LastNodeRan']+"\n"
        if sharedData.warningErrorInfoInfo['Info']['Other'] != None:
            infoToolTip += sharedData.warningErrorInfoInfo['Info']['Other'][0]
        
        if infoToolTip != '':
            setWarningErrorInfoIcon(infoIcon,'info',findIconFolder(),alteration='none')
            infoIcon.setToolTip(infoToolTip)
        else:
            infoIcon.setToolTip(infoToolTip)
            setWarningErrorInfoIcon(infoIcon,'info',findIconFolder(),alteration='grayscale')
        
        
        #For warning/error, all nodes have a .warning or .error, which contain the info.
        #We find this info and display it if necessary
        errorToolTip = ''
        if not hasattr(sharedData.nodzInstance, 'nodes'):
            return
        for node in sharedData.nodzInstance.nodes:
            if node.errorInfo != None:
                if node.errorInfo != '':
                    errorToolTip += f"Error in node {node.name}: {node.errorInfo}\n"
        
        errorIcon.setToolTip(errorToolTip)
        if errorToolTip == '':
            setWarningErrorInfoIcon(errorIcon,'error',findIconFolder(),alteration='grayscale')
        else:
            setWarningErrorInfoIcon(errorIcon,'error',findIconFolder(),alteration='none')
        
        #Set the warningToolTip
        warningToolTip = ''
        for entry in sharedData.warningErrorInfoInfo['Warnings']:
            warningToolTip+=entry+'\n'
        warningIcon.setToolTip(warningToolTip)
        if warningToolTip == '':
            setWarningErrorInfoIcon(warningIcon,'warning',findIconFolder(),alteration='grayscale')
        else:
            setWarningErrorInfoIcon(warningIcon,'warning',findIconFolder(),alteration='none')
        # errorToolTip = ''
        # errorToolTip = sharedData.warningErrorInfoInfo['Errors']
        # if errorToolTip != '':
        #     setWarningErrorInfoIcon(errorIcon,'error',findIconFolder(),alteration='none')
        #     errorIcon.setToolTip(errorToolTip)
        # else:
        #     errorIcon.setToolTip(errorToolTip)
        #     setWarningErrorInfoIcon(errorIcon,'error',findIconFolder(),alteration='grayscale')

import warnings

# Logger classes/functions moved to glados_pycromanager.observability.logger (Phase 11.1).
# These shims keep existing callers working without modification.
from glados_pycromanager.observability.logger import ColoredFormatter as ColoredFormatter
from glados_pycromanager.observability.logger import set_up_logger as _set_up_logger


def set_up_logger():  # type: ignore[override]
    warnings.warn(
        "utils.set_up_logger() is deprecated; use "
        "glados_pycromanager.observability.logger.set_up_logger() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    _set_up_logger()


def metadata_refactor(metadata, shared_data=None):
    """
    Refactor the metadata to be more consistent and easier to use.
    """
    #Metadata is a dict. This might be received from pycromanager, or from pymmc, or something else. We create a new, somewhat consistent metadata dict.
    # new_metadata = dict()
    # if shared_data.MILcore.MI() == MIL.MicroscopeInstance.PYCROMANAGER_JAVA or shared_data.MILcore.MI() == MIL.MicroscopeInstance.PYCROMANAGER_PYTHON:
    #     new_metadata = metadata
    # elif shared_data.MILcore.MI() == MIL.MicroscopeInstance.MMCORE_PLUS:
    #     new_metadata['Time'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f")
    #     new_metadata['Exposure'] = shared_data.MILcore.core.getExposure()
    #     new_metadata['ROI'] = shared_data.MILcore.core.getROI()
    #     new_metadata['PixelSize_um'] = shared_data.MILcore.core.getPixelSizeUm()
    #     new_metadata['Axes'] = metadata['Axes']
    #     if 't' in metadata['Axes']:
    #         new_metadata['Axes']['time'] = metadata['Axes']['t']
    #         del new_metadata['Axes']['t']
    # metadata_orig = metadata.copy()  # Keep original metadata for reference
    # if 'mda_event' in metadata:
    #     metadata['Axes'] = dict(metadata['mda_event'].index)
    #     if 't' in metadata['Axes']:
    #         metadata['Axes']['time'] = metadata['Axes']['t']
    #         del metadata['Axes']['t']
    #     if 'c' in metadata['Axes']:
    #         metadata['Axes']['channel'] = metadata['Axes']['c']
    #         del metadata['Axes']['c']
    #     if 'Z' in metadata['Axes']:
    #         metadata['Axes']['z'] = metadata['Axes']['Z']
    #         del metadata['Axes']['Z']
    #     if 'p' in metadata['Axes']:
    #         metadata['Axes']['position'] = metadata['Axes']['p']
    #         del metadata['Axes']['p']
    
    key_remapping = {
        't': 'time',
        'c': 'channel',
        'Z': 'z',
        'p': 'position'
    }

    if 'mda_event' in metadata:
        original_axes = metadata['mda_event'].index
        ordered_axes_data = collections.OrderedDict() # Use OrderedDict to guarantee order

        # Iterate through the keys of the original index to preserve order
        for original_key in original_axes:
            # Get the new key name, defaulting to the original key if not in remapping
            new_key = key_remapping.get(original_key, original_key)
            ordered_axes_data[new_key] = original_axes[original_key]

        metadata['Axes'] = ordered_axes_data
    
    return metadata
