
import shutil
import os
import logging

def cleanUpTemporaryFiles(mainFolder='./'):
    logging.info('Cleaning up temporary files')
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
#Import all scripts in the custom script folders
from Analysis_Images import * #type: ignore
from Analysis_Measurements import * #type: ignore
from Analysis_Shapes import * #type: ignore
from Scoring_Images import * #type: ignore
from Scoring_Measurements import * #type: ignore
from Scoring_Shapes import * #type: ignore
from Scoring_Images_Measurements import * #type: ignore
from Scoring_Measurements_Shapes import * #type: ignore
from Scoring_Images_Measurements_Shapes import * #type: ignore
from Visualisation_Images import * #type: ignore
from Visualisation_Measurements import * #type: ignore
from Visualisation_Shapes import * #type: ignore

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

def layout_init(curr_layout,className,displayNameToFunctionNameMap,current_dropdown=None,parent=None,ignorePolarity=False,maxNrRows=4):
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
            logging.debug('current selected function: '+current_selected_function)

            #Unhide everything
            model = current_dropdown.model()
            totalNrRows = model.rowCount()
            for rowId in range(totalNrRows):
                #First show all rows:
                current_dropdown.view().setRowHidden(rowId, False)
                item = model.item(rowId)
                item.setFlags(item.flags() | Qt.ItemIsEnabled)
        
            #Visual max number of rows before a 2nd column is started.
            labelposoffset = 0

            reqKwargs = reqKwargsFromFunction(current_selected_function)
            
            #Add a widget-pair for every kw-arg
            
            for k in range(len(reqKwargs)):
                #Value is used for scoring, and takes the output of the method
                if reqKwargs[k] != 'methodValue':
                    label = QLabel(f"<b>{displayNameFromKwarg(current_selected_function,reqKwargs[k])}</b>")
                    label.setObjectName(f"Label#{current_selected_function}#{reqKwargs[k]}")
                    if checkAndShowWidget(curr_layout,label.objectName()) == False:
                        label.setToolTip(infoFromMetadata(current_selected_function,specificKwarg=reqKwargs[k]))
                        curr_layout.addWidget(label,2+((k+labelposoffset))%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+0)
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
                            curr_layout.addLayout(hor_boxLayout,2+((k+labelposoffset))%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+1)
                            #Add a on-change listener:
                            line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))
                            
                            #Add an listener when the pushButton is pressed
                            line_edit_lookup.clicked.connect(lambda text2,line_edit_change_objName = line_edit,text="Select file",filter="*.*": lineEditFileLookup(line_edit_change_objName, text, filter,parent=parent))
                            #Init the parent currentData storage:
                            changeDataVarUponKwargChange(line_edit)
                            
                    else: #'normal' type - int, float, string, whatever
                        #Creating a line-edit...
                        line_edit = QLineEdit()
                        line_edit.setObjectName(f"LineEdit#{current_selected_function}#{reqKwargs[k]}")
                        defaultValue = defaultValueFromKwarg(current_selected_function,reqKwargs[k])
                        #Actually placing it in the layout
                        if checkAndShowWidget(curr_layout,line_edit.objectName()) == False:
                            line_edit.setToolTip(infoFromMetadata(current_selected_function,specificKwarg=reqKwargs[k]))
                            if defaultValue is not None:
                                line_edit.setText(str(defaultValue))
                            curr_layout.addWidget(line_edit,2+((k+labelposoffset))%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+1)
                            #Add a on-change listener:
                            line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))
                            #Init the parent currentData storage:
                            changeDataVarUponKwargChange(line_edit)
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
                    curr_layout.addWidget(label,2+((k+labelposoffset+len(reqKwargs)))%maxNrRows,(((k+labelposoffset+len(reqKwargs)))//maxNrRows)*2+0)
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
                        curr_layout.addLayout(hor_boxLayout,2+((k+labelposoffset))%maxNrRows,(((k+labelposoffset))//maxNrRows)*2+1)
                        #Add a on-change listener:
                        line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))
                        #Init the parent currentData storage:
                        changeDataVarUponKwargChange(line_edit)
                        
                        #Add an listener when the pushButton is pressed
                        line_edit_lookup.clicked.connect(lambda text2,line_edit_change_objName = line_edit,text="Select file",filter="*.*": lineEditFileLookup(line_edit_change_objName, text, filter,parent=parent))
                            
                else:
                    line_edit = QLineEdit()
                    line_edit.setObjectName(f"LineEdit#{current_selected_function}#{optKwargs[k]}")
                    defaultValue = defaultValueFromKwarg(current_selected_function,optKwargs[k])
                    if checkAndShowWidget(curr_layout,line_edit.objectName()) == False:
                        line_edit.setToolTip(infoFromMetadata(current_selected_function,specificKwarg=optKwargs[k]))
                        if defaultValue is not None:
                            line_edit.setText(str(defaultValue))
                        curr_layout.addWidget(line_edit,2+((k+labelposoffset+len(reqKwargs)))%maxNrRows,(((k+labelposoffset+len(reqKwargs)))//maxNrRows)*2+1)
                        #Add a on-change listener:
                        line_edit.textChanged.connect(lambda text,line_edit=line_edit: kwargValueInputChanged(line_edit))
                        #Init the parent currentData storage:
                        changeDataVarUponKwargChange(line_edit)
                        
    #Hides everything except the current layout
    layout_changedDropdown(curr_layout,current_dropdown,displayNameToFunctionNameMap)

def preLoadOptions(curr_layout,currentData):
    """
    Preloads the kwarg values from the currentData dict into their respective widgets
    """
    for i in range(curr_layout.count()):
        item = curr_layout.itemAt(i)
        if item.widget() is not None:
            child = item.widget()
            if child.objectName() in currentData:
                child.setText(str(currentData[child.objectName()]))
                
            #Also set the dropdown to the correct value:
            if 'comboBox_analysisFunctions' in child.objectName() and '__selectedDropdownEntryAnalysis__' in currentData:
                child.setCurrentText(currentData['__selectedDropdownEntryAnalysis__'])
    

def changeDataVarUponKwargChange(line_edit):
    #Idea: update the parent.currentData{} structure whenever a kwarg is changed, and this can be (re-)loaded when needed
    parentObject = line_edit.parent()
    newValue = line_edit.text()
    parentObject.currentData[line_edit.objectName()] = newValue
    #To be sure, also do this routine:
    updateCurrentDataUponDropdownChange(parentObject)


def updateCurrentDataUponDropdownChange(parentObject):
    #Figure out the current selected dropdown entry:
    #loop over all children:
    for child in parentObject.children():
        if 'comboBox_analysisFunctions' in child.objectName():
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
                        return
    return False

#Remove everythign in this layout except className_dropdown
def resetLayout(curr_layout,className):
    for index in range(curr_layout.count()):
        widget_item = curr_layout.itemAt(index)
        # Check if the item is a widget (as opposed to a layout)
        if widget_item.widget() is not None:
            widget = widget_item.widget()
            #If it's the dropdown segment, label it as such
            if not ("KEEP" in widget.objectName()) and not ('#'+className+'#' in widget.objectName()):
                logging.debug(f"Hiding {widget.objectName()}")
                widget.hide()
            else:
                widget.show()
        else:
            for index2 in range(widget_item.count()):
                widget_sub_item = widget_item.itemAt(index2)
                # Check if the item is a widget (as opposed to a layout)
                if widget_sub_item.widget() is not None:
                    widget = widget_sub_item.widget()
                    #If it's the dropdown segment, label it as such
                    if not ("KEEP" in widget.objectName()) and not ('#'+className+'#' in widget.objectName()):
                        logging.debug(f"Hiding {widget.objectName()}")
                        widget.hide()
                else:
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


def getFunctionEvalTextFromCurrentData(function,currentData,p1,p2):
    
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
        EvalTextMethod = getEvalTextFromGUIFunction(methodName_method, methodKwargNames_method, methodKwargValues_method,partialStringStart=str(p1)+','+str(p2))
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
    
def getEvalTextFromGUIFunction(methodName, methodKwargNames, methodKwargValues, partialStringStart=None, removeKwargs=None):
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
    #We have the method name and all its kwargs, so:
    if len(methodName)>0: #if the method exists
        #Check if all req. kwargs have some value
        reqKwargs = reqKwargsFromFunction(methodName)
        #Remove values from this array if wanted
        if removeKwargs is not None:
            for removeKwarg in removeKwargs:
                if removeKwarg in reqKwargs:
                    reqKwargs.remove(removeKwarg)
                else:
                    #nothing, but want to make a note of this (log message)
                    reqKwargs = reqKwargs
        #Stupid dummy-check whether we have the reqKwargs in the methodKwargNames, which we should (basically by definition)

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
        self.centralWidget().layout().addLayout(layout)
        return self.descriptionLabel
    
    def addButton(self,buttonText="Button"):
        #Create a horizontal box layout:
        layout = QHBoxLayout()
        #add a button:
        self.button = QPushButton(buttonText)
        #Add the button to the layout:
        layout.addWidget(self.button)
        #Add the layout to the central widget:
        self.centralWidget().layout().addLayout(layout)
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
        self.centralWidget().layout().addLayout(layout)
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
        self.fileLocationButton.clicked.connect(lambda: self.openFileDialog(fileArgs = "All Files (*)"))
        
        #Add the label, line edit and button to the layout:
        layout.addWidget(self.fileLocationLabel)
        layout.addWidget(self.fileLocationLineEdit)
        layout.addWidget(self.fileLocationButton)
        #Add the layout to the central widget:
        self.centralWidget().layout().addLayout(layout)
        return self.fileLocationLineEdit
