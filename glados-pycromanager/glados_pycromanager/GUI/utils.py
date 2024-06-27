
import shutil
import os
import logging

def cleanUpTemporaryFiles(mainFolder='./'):
    logging.debug('Cleaning up temporary files')
    if os.path.exists(os.path.join(mainFolder,'temp')):
        for folder in os.listdir(os.path.join(mainFolder,'temp')):
            if 'LiveAcqShouldBeRemoved' in folder or 'MdaAcqShouldBeRemoved' in folder:
                try:
                    shutil.rmtree(os.path.join(mainFolder,os.path.join('temp',folder)))
                except:
                    pass

#Below here, copy from Eve's util functions:
import os
import warnings
import inspect
import importlib
import re
import warnings, logging
import numpy as np
import itertools
import time
import h5py

#Imports for PyQt5 (GUI)
from PyQt5 import QtWidgets, QtGui
from PyQt5.QtGui import QCursor, QTextCursor, QIntValidator
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem, QLayout, QMainWindow, QLabel, QPushButton, QSizePolicy, QGroupBox, QTabWidget, QGridLayout, QWidget, QComboBox, QLineEdit, QFileDialog, QToolBar, QCheckBox,QDesktopWidget, QMessageBox, QTextEdit, QSlider, QSpacerItem
from PyQt5.QtCore import Qt, QPoint, QProcess, QCoreApplication, QTimer, QFileSystemWatcher, QFile, QThread, pyqtSignal, QObject
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep + 'AutonomousMicroscopy')
#Import all scripts in the custom script folders
from Analysis_Images import * #type: ignore
from Analysis_Measurements import * #type: ignore
from Analysis_Shapes import * #type: ignore
from CustomFunctions import * #type: ignore
from Scoring_Images import * #type: ignore
from Scoring_Measurements import * #type: ignore
from Scoring_Shapes import * #type: ignore
from Scoring_Images_Measurements import * #type: ignore
from Scoring_Measurements_Shapes import * #type: ignore
from Scoring_Images_Measurements_Shapes import * #type: ignore
from Visualisation_Images import * #type: ignore
from Visualisation_Measurements import * #type: ignore
from Visualisation_Shapes import * #type: ignore
from Real_Time_Analysis import * #type: ignore

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
    #initialise empty array
    functionnamearr = []
    def addFilesToAbsolutePath(functionnamearr,absolute_path):
        #Loop over all files
        for file in os.listdir(absolute_path):
            #Check if they're .py files
            if file.endswith(".py"):
                #Check that they're not init files or similar
                if not file.startswith("_") and not file == "utils.py" and not file == "utilsHelper.py":
                    #Get the function name
                    functionName = file[:-3]
                    #Get the metadata from this function and from there obtain
                    try:
                        functionMetadata = eval(f'{str(functionName)}.__function_metadata__()')
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
                        for subroutineName, obj in inspect.getmembers(eval(f'{functionName}')):
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
    except:
        pass
    
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

#Returns a display name (if available) of an individual kwarg name, from a specific function:
def displayNameFromKwarg(functionname,name):
    #Get all kwarg info
    allkwarginfo = kwargsFromFunction(functionname)
    
    #Look through optional args first, then req. kwargs (so that req. kwargs have priority in case something weirdi s happening):
    for optOrReq in range(1,-1,-1):
    
        #Perform a regex match on 'name'
        name_pattern = r"name:\s*(\S+)"
        
        names = re.findall(name_pattern, allkwarginfo[optOrReq][0])
        instances = re.split(r'(?=name: )', allkwarginfo[optOrReq][0])[1:]

        #Find which instance this name belongs to:
        name_id = -1
        for i,namef in enumerate(names):
            if namef == name:
                name_id = i
        
        if name_id > -1:
            curr_instance = instances[name_id]
            displayText_pattern = r"display_text: (.*?)\n"
            displaytext = re.findall(displayText_pattern, curr_instance)
            if len(displaytext) > 0:
                displayName = displaytext[0]
            else:
                displayName = name
    
    return displayName

#Returns the 'names' of the optional kwargs of a function
def optKwargsFromFunction(functionname):
    #Get all kwarg info
    allkwarginfo = kwargsFromFunction(functionname)
    #Perform a regex match on 'name'
    name_pattern = r"name:\s*(\S+)"
    #Get the names of the optional kwargs (allkwarginfo[1])
    names = re.findall(name_pattern, allkwarginfo[1][0])
    return names

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

def inputFromFunction(functionname):
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
        
        input_arr = []
        for i in looprange:
            input_arr.append(functionMetadata[list(functionMetadata.keys())[i]]["input"])
    except AttributeError:
        input_arr = []
        return f"No __function_metadata__ in {functionname}"
    
    return input_arr

def outputFromFunction(functionname):
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
        
        output_arr = []
        for i in looprange:
            output_arr.append(functionMetadata[list(functionMetadata.keys())[i]]["output"])
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
            functionMetadata = eval(f'{str(functionname)}.__function_metadata__()')
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
                functionMetadata = eval(f'{str(functionparent)}.__function_metadata__()')
                #sub-select the looprange
                loopv = next((index for index in range(0,len(functionMetadata)) if list(functionMetadata.keys())[index] == functionname.split('.')[1]), None)
                looprange = range(loopv,loopv+1) #type:ignore
                finaltext = ""
            else:
                #Get information on a single kwarg
                #get the parent info
                functionparent = functionname.split('.')[0]
                #Get the full function metadata
                functionMetadata = eval(f'{str(functionparent)}.__function_metadata__()')
                #Get the help string of a single kwarg
                
                #Find the help text of a single kwarg
                helptext = 'No help text set'
                #Look over optional kwargs
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


def defaultValueFromKwarg(functionname,kwargname):
    #Check if the function has a 'default' entry for the specific kwarg. If not, return None. Otherwise, return the default value.
    
    defaultEntry=None
    functionparent = functionname.split('.')[0]
    #Get the full function metadata
    functionMetadata = eval(f'{str(functionparent)}.__function_metadata__()')
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
    motherFunctionMetadata = eval(f'{str(motherFunctionFromFunctionName(functionname))}.__function_metadata__()')
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
        functionMetadata = eval(f'{str(subroutineName)}.__function_metadata__()')
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
        functionMetadata = eval(f'{str(functionparent)}.__function_metadata__()')
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
        
    except:
        typing=None
    return typing

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
        for entry in curr_layout.parent().parent().currentData['__displayNameFunctionNameMap__']:
            if entry[1] == current_selected_function:
                currentSelectedFunctionReadable = entry[0]
            
        curr_layout.parent().parent().currentData['__selectedDropdownEntryAnalysis__'] = currentSelectedFunctionReadable
        
        #Show/hide varialbes/advanced lineedits and such
        for i in range(curr_layout.count()):
            item = curr_layout.itemAt(i)
            if not isinstance(item,QSpacerItem):
                if item.widget() is not None:
                    child = item.widget()
                    if 'ComboBoxSwitch#'+current_selected_function in child.objectName():
                        logging.debug(f"1Going to run hideAdvVariables with {child.objectName()}")
                        curr_layout.update()
                        hideAdvVariables(child,current_selected_function=current_selected_function)
                else:
                    for index2 in range(item.count()):
                        widget_sub_item = item.itemAt(index2)
                        child = widget_sub_item.widget()
                        if 'ComboBoxSwitch#'+current_selected_function in child.objectName():
                            logging.debug(f"2Going to run hideAdvVariables with {child.objectName()}")
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
            except:
                finalVal = value
        elif checkAdvanced:
            try:
                finalVal = nodz_evaluateAdv(value,nodzInfo)
            except:
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
            except:
                logging.error(f'Type mismatch in variable setting! {variableName} and {value}')
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
                    except:
                        updating_string = updating_string.replace(foundstring,""+str(data)+"")
                else: #uncalculatable, add as string
                    try:
                        updating_string = updating_string.replace(foundstring,""+data+"")
                    except:
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
            except:
                logging.error(f"Error when assessing adv variable {varName}: {updating_string_backslash}")
                finalData = None
            return finalData
    else:
        try:
            varName = nodz_evaluateVar(varName,nodzInfo)
            logging.warning(f"Wrong syntax for advanced variable [but seems to be a variable instead]! Details: {varName} - interpreting as variable")
        except:
            logging.error(f'Wrong syntax for advanced variable! Details: {varName} - interpreting as value')
        return varName

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
        import string
        import random
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
    logging.debug('Changing layout '+curr_layout.parent().objectName())
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
                        curr_layout.addWidget(label,2+((k+labelposoffset))%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+0)
                        
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
                    curr_layout.addLayout(SingleVar_Variables_boxLayout,2+((k+labelposoffset))%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+1)
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
                curr_layout.addWidget(label, 3+((k+labelposoffset))%maxNrRows, 0, 1, 10)  # Span one row and one column

            reqKwargs = reqKwargsFromFunction(current_selected_function)
            
            #Add a widget-pair for every kw-arg
            for k in range(len(reqKwargs)):
                #Value is used for scoring, and takes the output of the method
                if reqKwargs[k] != 'methodValue':
                    label = QLabel(f"<b>{displayNameFromKwarg(current_selected_function,reqKwargs[k])}</b>")
                    label.setObjectName(f"Label#{current_selected_function}#{reqKwargs[k]}")
                    if checkAndShowWidget(curr_layout,label.objectName()) == False:
                        label.setToolTip(infoFromMetadata(current_selected_function,specificKwarg=reqKwargs[k]))
                        curr_layout.addWidget(label,4+((k+labelposoffset))%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+0)
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
                            curr_layout.addLayout(hor_boxLayout,4+((k+labelposoffset))%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+1)
                            #Add a on-change listener:
                            line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))
                            
                            #Add an listener when the pushButton is pressed
                            line_edit_lookup.clicked.connect(lambda text2,line_edit_change_objName = line_edit,text="Select file",filter="*.*": lineEditFileLookup(line_edit_change_objName, text, filter,parent=parent))
                            #Init the parent currentData storage:
                            changeDataVarUponKwargChange(line_edit)
                    else: #'normal' type - int, float, string, whatever
                        #Create a new HBox:
                        SingleVar_Variables_boxLayout = QHBoxLayout()
                        
                        #Creating a line-edit...
                        line_edit = QLineEdit()
                        
                        line_edit.setObjectName(f"LineEdit#{current_selected_function}#{reqKwargs[k]}")
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
                            if defaultValue is not None:
                                line_edit.setText(str(defaultValue))
                            curr_layout.addLayout(SingleVar_Variables_boxLayout,4+((k+labelposoffset))%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+1)
                            #Add a on-change listener:
                            line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))
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
                    curr_layout.addWidget(label,4+((k+labelposoffset+len(reqKwargs)))%maxNrRows,(((k+labelposoffset+len(reqKwargs)))//maxNrRows)*2+0)
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
                        curr_layout.addLayout(hor_boxLayout,4+((k+labelposoffset))%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+1)
                        #Add a on-change listener:
                        line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))
                        #Init the parent currentData storage:
                        changeDataVarUponKwargChange(line_edit)
                        
                        #Add an listener when the pushButton is pressed
                        line_edit_lookup.clicked.connect(lambda text2,line_edit_change_objName = line_edit,text="Select file",filter="*.*": lineEditFileLookup(line_edit_change_objName, text, filter,parent=parent))
                            
                else:
                    #Create a new HBox:
                    SingleVar_Variables_boxLayout = QHBoxLayout()
                        
                    line_edit = QLineEdit()
                    line_edit.setObjectName(f"LineEdit#{current_selected_function}#{optKwargs[k]}")
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
                        if defaultValue is not None:
                            line_edit.setText(str(defaultValue))
                        curr_layout.addLayout(SingleVar_Variables_boxLayout,4+((k+labelposoffset+len(reqKwargs)))%maxNrRows,(((k+labelposoffset+len(reqKwargs)))//maxNrRows)*2+1)
                        #Add a on-change listener:
                        line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))
                        #Init the parent currentData storage:
                        changeDataVarUponKwargChange(line_edit)
                        if ShowVariablesOptions:
                            #Init the parent currentData storage:
                            changeDataVarUponKwargChange(line_edit_variable)
                            changeDataVarUponKwargChange(line_edit_adv)
                        
    #Hides everything except the current layout
    layout_changedDropdown(curr_layout,current_dropdown,displayNameToFunctionNameMap)
    # resetLayout(curr_layout)

import sys
from PyQt5.QtWidgets import QApplication, QLineEdit
from PyQt5.QtGui import QPainter, QIcon, QPixmap, QColor, QFontMetrics, QPalette, QPen
from PyQt5.QtCore import Qt

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
                        logging.debug(f"2Preloading {child.objectName()} with {currentData[child.objectName()]}")
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
        logging.debug(child.objectName())
        if len(child.objectName().split('#')) > 2:
            #Check if it's the same function and variable:
            if child.objectName().split('#')[1] == functionName and child.objectName().split('#')[2] == kwargName:
                logging.debug('Looking at ' + functionName + ' ' + kwargName)
                normalVarAdvValue = child.objectName().split('#')[0]
                if normalVarAdvValue != 'Label' and normalVarAdvValue != 'ComboBoxSwitch':
                    #Hide/show simple/advanced/onlyVar based on the comboBox value:
                    if comboboxvalue == 'Variable':
                        if normalVarAdvValue == 'LineEditVariable' or normalVarAdvValue == 'PushButtonVariable':
                            child.show()
                            logging.debug(f'1Showing {child.objectName()}')
                        else:
                            child.hide()
                            logging.debug(f'1Hiding {child.objectName()}')
                    elif comboboxvalue == 'Advanced':
                        if normalVarAdvValue == 'LineEditAdv' or normalVarAdvValue == 'PushButtonAdv':
                            child.show()
                            logging.debug(f'2Showing {child.objectName()}')
                        else:
                            child.hide()
                            logging.debug(f'2Hiding {child.objectName()}')
                    else:
                        if normalVarAdvValue == 'LineEdit':
                            child.show()
                            logging.debug(f'3Showing {child.objectName()}')
                        else:
                            child.hide()
                            logging.debug(f'3Hiding {child.objectName()}')
    
    # resetLayout(parentObject.mainLayout,currentSelectedFunction)
                    
def changeDataVarUponKwargChange(line_edit):
    #Idea: update the parent.currentData{} structure whenever a kwarg is changed, and this can be (re-)loaded when needed
    if isinstance(line_edit,QLineEdit):
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
            except:
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
            except:
                #Show as warning
                setLineEditStyle(line_edit,type='Warning')
    else:
        setLineEditStyle(line_edit,type='Normal')
    pass

def setLineEditStyle(line_edit,type='Normal'):
    if type == 'Normal':
        line_edit.setStyleSheet("border: 1px  solid #D5D5E5;")
    elif type == 'Warning':
        line_edit.setStyleSheet("border: 1px solid red;")

def checkAndShowWidget(layout, widgetName):
    # Iterate over the layout's items
    for index in range(layout.count()):
        item = layout.itemAt(index)
        # Check if the item is a widget
        if item.widget() is not None:
            widget = item.widget()
            # Check if the widget has the desired name
            if widget.objectName() == widgetName:
                # Widget already exists, unhide it
                widget.show()
                logging.debug('898 showing widget: '+widget.objectName())
                return
        else:
            for index2 in range(item.count()):
                item_sub = item.itemAt(index2)
                # Check if the item is a widget
                if item_sub.widget() is not None:
                    widget = item_sub.widget()
                    # Check if the widget has the desired name
                    if widget.objectName() == widgetName:
                        # Widget already exists, unhide it
                        widget.show()
                        logging.debug('909 showing widget: '+widget.objectName())
                        return
    return False

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
                    logging.debug(f"1Hiding {widget.objectName()}")
                    widget.hide()
                else:
                    logging.debug(f"1Showing {widget.objectName()}")
                    widget.show()
            else:
                for index2 in range(widget_item.count()):
                    widget_sub_item = widget_item.itemAt(index2)
                    # Check if the item is a widget (as opposed to a layout)
                    if widget_sub_item.widget() is not None:
                        widget = widget_sub_item.widget()
                        #If it's the dropdown segment, label it as such
                        if not ("KEEP" in widget.objectName()) and not ('#'+className+'#' in widget.objectName()):
                            logging.debug(f"2Hiding {widget.objectName()}")
                            widget.hide()
                        else:
                            logging.debug(f"2Showing {widget.objectName()}")
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


def lineEditFileLookup(line_edit_objName, text, filter,parent=None):
    parentFolder = line_edit_objName.text()
    if parentFolder != "":
        parentFolder = os.path.dirname(parentFolder)
    
    file_path = generalFileSearchButtonAction(parent=parent,text=text,filter=filter,parentFolder=parentFolder)
    line_edit_objName.setText(file_path)
        
def generalFileSearchButtonAction(parent=None,text='Select File',filter='*.txt',parentFolder=""):
    file_path, _ = QFileDialog.getOpenFileName(parent,text,parentFolder,filter=filter)
    return file_path


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


def getFunctionEvalTextFromCurrentData_RTAnalysis_init(function,currentData):
    
    methodKwargNames_method=[]
    methodKwargValues_method=[]
    variableValueOrAdvanced={}
    
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
                split_list = key.split('#')
                methodName_method = split_list[1]
                methodKwargNames_method.append(split_list[2])

                #value could contain a file location. Thus, we need to swap out all \ for /:
                methodKwargValues_method.append(value.replace('\\','/'))
    
    methodKwargTypes_method = []
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
        #note that RT analysis methods do not have an input, thus we skipInput.
        EvalTextMethod = getEvalTextFromGUIFunction(methodName_method, methodKwargNames_method, methodKwargValues_method,partialStringStart='core=core',methodKwargTypes=methodKwargTypes_method,skipInput=True)
        #append this to moduleEvalTexts
        moduleMethodEvalTexts.append(EvalTextMethod)

    if moduleMethodEvalTexts is not None and len(moduleMethodEvalTexts) > 0:
        return moduleMethodEvalTexts[0]


def getFunctionEvalTextFromCurrentData_RTAnalysis_run(function,currentData,p1,p2,p3):
    
    methodKwargNames_method=[]
    methodKwargValues_method=[]
    variableValueOrAdvanced={}
    
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
                split_list = key.split('#')
                methodName_method = split_list[1]
                methodKwargNames_method.append(split_list[2])

                #value could contain a file location. Thus, we need to swap out all \ for /:
                methodKwargValues_method.append(value.replace('\\','/'))
    
    methodKwargTypes_method = []
    #Get the Value/Variable/Adv:
    for entry in methodKwargNames_method:
        if variableValueOrAdvanced[entry]  == 'Variable':
            methodKwargTypes_method.append('Variable')
        elif variableValueOrAdvanced[entry]  == 'Advanced':
            methodKwargTypes_method.append('Advanced')
        else:
            methodKwargTypes_method.append('Value')
    
    logging.debug(f'RTeval: {methodKwargTypes_method}')
    #Now we create evaluation-texts:
    moduleMethodEvalTexts = []
    if methodName_method != '':
        #note that RT analysis methods do not have an input, thus we skipInput.
        EvalTextMethod = getEvalTextFromGUIFunction(methodName_method, methodKwargNames_method, methodKwargValues_method,partialStringStart=str(p1)+','+str(p2)+','+str(p3),methodKwargTypes=methodKwargTypes_method,skipInput=True)
        EvalTextMethod = EvalTextMethod.replace(methodName_method,'.run') #type:ignore
        #append this to moduleEvalTexts
        moduleMethodEvalTexts.append(EvalTextMethod)

    if moduleMethodEvalTexts is not None and len(moduleMethodEvalTexts) > 0:
        return moduleMethodEvalTexts[0]

def getFunctionEvalTextFromCurrentData_RTAnalysis_end(function,currentData,p1):
    
    methodKwargNames_method=[]
    methodKwargValues_method=[]
    variableValueOrAdvanced={}
    
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
                split_list = key.split('#')
                methodName_method = split_list[1]
                methodKwargNames_method.append(split_list[2])

                #value could contain a file location. Thus, we need to swap out all \ for /:
                methodKwargValues_method.append(value.replace('\\','/'))
    
    methodKwargTypes_method = []
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
        #note that RT analysis methods do not have an input, thus we skipInput.
        EvalTextMethod = getEvalTextFromGUIFunction(methodName_method, methodKwargNames_method, methodKwargValues_method,partialStringStart=str(p1),methodKwargTypes=methodKwargTypes_method,skipInput=True)
        EvalTextMethod = EvalTextMethod.replace(methodName_method,'.end') #type:ignore
        #append this to moduleEvalTexts
        moduleMethodEvalTexts.append(EvalTextMethod)

    if moduleMethodEvalTexts is not None and len(moduleMethodEvalTexts) > 0:
        return moduleMethodEvalTexts[0]

def getFunctionEvalTextFromCurrentData_RTAnalysis_visualisation(function,currentData,p1,p2,p3,p4):
    
    methodKwargNames_method=[]
    methodKwargValues_method=[]
    #Loop over all entries of currentData:
    for key,value in currentData.items():
        if "#"+function+"#" in key:
            if ("LineEdit" in key):
                # The objectName will be along the lines of foo#bar#str
                #Check if the objectname is part of a method or part of a scoring
                split_list = key.split('#')
                methodName_method = split_list[1]
                methodKwargNames_method.append(split_list[2])

                #value could contain a file location. Thus, we need to swap out all \ for /:
                methodKwargValues_method.append(value.replace('\\','/'))
    
    #Now we create evaluation-texts:
    moduleMethodEvalTexts = []
    if methodName_method != '':
        EvalTextMethod = getEvalTextFromGUIFunction(methodName_method, methodKwargNames_method, methodKwargValues_method,partialStringStart=str(p1)+','+str(p2)+','+str(p3)+','+str(p4))
        EvalTextMethod = EvalTextMethod.replace(methodName_method,'.visualise') #type:ignore
        #append this to moduleEvalTexts
        moduleMethodEvalTexts.append(EvalTextMethod)

    if moduleMethodEvalTexts is not None and len(moduleMethodEvalTexts) > 0:
        return moduleMethodEvalTexts[0]

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
        

def realTimeAnalysis_init(rt_analysis_info,core=None, nodzInfo=None):
    #Get the classname from rt_analysis_info
    functionDispName = rt_analysis_info['__selectedDropdownEntryRTAnalysis__']
    for function in rt_analysis_info['__displayNameFunctionNameMap__']:
        if function[0] == functionDispName:
            className = function[1]
    
    if nodzInfo is not None:
        nodeDict = createNodeDictFromNodes(nodzInfo.nodes) 
    else:
        nodeDict = None

    #Get the object
    RT_analysis_object = eval(getFunctionEvalTextFromCurrentData_RTAnalysis_init(className,rt_analysis_info)) #type:ignore
    
    return RT_analysis_object

def realTimeAnalysis_run(RT_analysis_object,rt_analysis_info,v1,v2,v3, nodzInfo=None):
    #Get the classname from rt_analysis_info
    functionDispName = rt_analysis_info['__selectedDropdownEntryRTAnalysis__']
    for function in rt_analysis_info['__displayNameFunctionNameMap__']:
        if function[0] == functionDispName:
            className = function[1]
    evalText = getFunctionEvalTextFromCurrentData_RTAnalysis_run(className,rt_analysis_info,'v1','v2','v3')
    logging.debug(f'RTanalysistext:{evalText}')
    
    if nodzInfo is not None:
        nodeDict = createNodeDictFromNodes(nodzInfo.nodes) 
    else:
        nodeDict = None
        
    #And run the .run function:
    result = eval("RT_analysis_object" + evalText) #type:ignore

    return result

def realTimeAnalysis_end(RT_analysis_object,rt_analysis_info,v1,nodzInfo = None):
    #Get the classname from rt_analysis_info
    functionDispName = rt_analysis_info['__selectedDropdownEntryRTAnalysis__']
    for function in rt_analysis_info['__displayNameFunctionNameMap__']:
        if function[0] == functionDispName:
            className = function[1]
    evalText = getFunctionEvalTextFromCurrentData_RTAnalysis_end(className,rt_analysis_info,'v1')
    
    if nodzInfo is not None:
        nodeDict = createNodeDictFromNodes(nodzInfo.nodes) 
    else:
        nodeDict = None
        
    #And run the .run function:
    result = eval("RT_analysis_object" + evalText) #type:ignore

    return result

def realTimeAnalysis_visualisation(RT_analysis_object,rt_analysis_info,v1,v2,v3,v4):
    #Get the classname from rt_analysis_info
    functionDispName = rt_analysis_info['__selectedDropdownEntryRTAnalysis__']
    for function in rt_analysis_info['__displayNameFunctionNameMap__']:
        if function[0] == functionDispName:
            className = function[1]
    evalText = getFunctionEvalTextFromCurrentData_RTAnalysis_visualisation(className,rt_analysis_info,'v1','v2','v3','v4')
    #And run the .run function:
    result = eval("RT_analysis_object" + evalText) #type:ignore

    return result

def realTimeAnalysis_getDelay(rt_analysis_info,runOrVis='run'):
    wrapperName = rt_analysis_info['__displayNameFunctionNameMap__'][0][1].split(".")[0]
    functionMetadata = eval(wrapperName+".__function_metadata__()")
    functionMetadata2 = functionMetadata[rt_analysis_info['__displayNameFunctionNameMap__'][0][1].split(".")[1]]
    if runOrVis == 'run':
        if 'run_delay' not in functionMetadata2:
            delay = 100 #Default value for run
        else:
            delay = functionMetadata2['run_delay']
    elif runOrVis == 'visualise':
        if 'visualise_delay' not in functionMetadata2:
            delay = 500 #Default value for vis
        else:
            delay = functionMetadata2['visualise_delay']
    
    return delay

class SmallWindow(QMainWindow):
    """ 
    General class that creates a small popup window to have some data. Mostly used for utility functions.
    """
    
    #Create a small window that pops up
    def __init__(self, parent, windowTitle="Small Window"):
        super().__init__(parent)
        self.setWindowTitle(windowTitle)
        self.resize(300, 200)

        self.parent = parent
        # Set the window icon to the parent's icon
        self.setWindowIcon(self.parent.windowIcon())
        
        #Add a layout
        layout = QVBoxLayout()
        self.setCentralWidget(QWidget())  # Create a central widget for the window
        self.centralWidget().setLayout(layout)  # Set the layout for the central widget

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
        except:
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
            except:
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


import json

class CustomMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.storingExceptions = ['core','layout','shared_data','gui','mda','data','config_groups','mainLayout']

    def save_state_MMControls(self,filename):
        if os.path.exists(filename):
            #Load the mda state
            with open(filename, 'r') as file:
                state = json.load(file)
        else:
            state = {}
            state['MDA'] = {}
            state['MMControls'] = {}
        
        if 'MMControls' not in state:
            state['MMControls'] = {}
        if 'MDA' not in state:
            state['MDA'] = {}
        
        import MMcontrols
        import napariGlados
        
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
                        except:
                            try:
                                if currentParent.type == 'MMConfig':
                                    saveState = 'MMControls'
                                    break
                            except:
                                pass
                            pass
                    
                if saveState is not None:
                    state[saveState][key] = {
                        'text': value.text() if hasattr(value, 'text') else None,
                        'checked': value.isChecked() if hasattr(value, 'isChecked') else None,
                        # Add more properties as needed
                    }

        with open(filename, 'w') as file:
            json.dump(state, file, indent=4)
            
    def save_state_MDA(self, filename):
        import napariGlados
        import MDAGlados
        logging.debug('SAVING STATE')
        if os.path.exists(filename):
            #Load the mda state
            with open(filename, 'r') as file:
                state = json.load(file)
        else:
            state = {}
            state['MDA'] = {}
            state['MMControls'] = {}
            
        if 'MMControls' not in state:
            state['MMControls'] = {}
        if 'MDA' not in state:
            state['MDA'] = {}
            
        for key, value in vars(self).items():
            saveState = None
            if isinstance(value, QWidget):
                maxParentInst = 10
                currentParent = value
                for _ in range(maxParentInst):
                    if currentParent == None:
                        break
                    currentParent = currentParent.parent()
                    if isinstance(currentParent, napariGlados.dockWidget_MDA):
                        saveState = 'MDA'
                        break
                    
                if saveState is not None:
                    state[saveState][key] = {
                        'text': value.text() if hasattr(value, 'text') else None,
                        'checked': value.isChecked() if hasattr(value, 'isChecked') else None,
                        # Add more properties as needed
                    }
            else:
                if isinstance(self, MDAGlados.MDAGlados):
                    saveState = 'MDA'
                if saveState is not None:
                    if key not in self.storingExceptions:
                        state[saveState][key] = value

        with open(filename, 'w') as file:
            json.dump(state, file, indent=4)


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


def getDimensionsFromAcqData(acqData):
    alldims = acqData[0]['axes']
    n_dims = len(alldims)
    dimOrder = []
    n_entries_in_dims = []
    uniqueEntriesAllDims = {}
    for dim in alldims:
        uniqueEntries = []
        for i in range(0,len(acqData)):
            uniqueEntries.append(acqData[i]['axes'][dim])
        uniqueEntries = np.unique(uniqueEntries)
        nEntries = len(uniqueEntries)
        n_entries_in_dims.append(nEntries)
        dimOrder.append(dim)
        uniqueEntriesAllDims.update({dim:uniqueEntries})
    logging.debug(f"dimOrder: {dimOrder} with n_entries_in_dims: {n_entries_in_dims}")
    logging.debug(f"uniqueEntriesAllDims: {uniqueEntriesAllDims}")
    return dimOrder, n_entries_in_dims, uniqueEntriesAllDims

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
            


def getCoreDevicesOfDeviceType(core,devicetype):
    """
    #Find all devices that have a specific devicetype
    #Look at https://javadoc.scijava.org/Micro-Manager-Core/mmcorej/DeviceType.html 
    #for all devicetypes
    """
    #Get devices
    devices = core.get_loaded_devices() #type:ignore
    devices = [devices.get(i) for i in range(devices.size())]
    devicesOfType = []
    #Loop over devices
    for device in devices:
        if core.get_device_type(device).to_string() == devicetype: #type:ignore
            logging.debug("found " + device + " of type " + devicetype)
            devicesOfType.append(device)
    return devicesOfType


