#Warning suppression
# pyright: reportGeneralTypeIssues=false
# pyright: reportMissingImports=false


from PyQt5.QtWidgets import QScrollArea, QLayout, QLineEdit, QFrame, QGridLayout, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpacerItem, QSizePolicy, qApp
from PyQt5.QtCore import QFileInfo, Qt, QSettings
from PyQt5.QtGui import QResizeEvent, QIcon, QPixmap
from PyQt5 import uic, QtGui
import sys
import os
# import PyQt5.QtWidgets
import json
import shutil
from pycromanager import * #type:ignore
import numpy as np
import time
import asyncio
import pyqtgraph as pg
import matplotlib.pyplot as plt
import pickle
from matplotlib import colormaps
#For drawing
import matplotlib
matplotlib.use('Qt5Agg')
# from PyQt5 import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import tifffile
import time
from PyQt5.QtCore import QTimer,QDateTime

import sys, os
# Add the folder 2 folders up to the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))+os.path.sep+'AutonomousMicroscopy')
#Import all scripts in the custom script folders
from CellSegmentScripts import *
from CellScoringScripts import *
from ROICalcScripts import *
from ScoringMetrics import *
#Obtain the helperfunctions
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))+os.path.sep+'AutonomousMicroscopy'+os.path.sep+'MainScripts')
import HelperFunctions

from LaserControlScripts import *



#Create a global UNIQUE value that is needed here and there
UNIQUE_ID = 1

class MainWindow(QMainWindow):
    #Intialisation
    def __init__(self):
        super().__init__()
        
        settings_file_path = "./temp/autonomous_settings.ini"
        # Remove the settings file if it exists
        if os.path.exists(settings_file_path):
            try:
                os.remove(settings_file_path)
                print("Settings file removed successfully.")
            except OSError as e:
                print(f"Error while removing the settings file: {e}")

        #Create settings? 
        self.autonomous_settings = QSettings(settings_file_path, QSettings.IniFormat)
        self.autonomous_settings.sync()
        
        #Load the UI
        self.load_ui()
        #Set Icon
        #For some reason, this needs abs path rather than rel, so os.path
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.setWindowIcon(QIcon(os.path.join(dir_path,"Icons/GladosIcon.png")))
        
        
        # Create the main_layout in which the autonomous GUI will be placed
        main_layout = QVBoxLayout(self.findChild(QWidget, "tab_autonomous"))
        main_layout.setAlignment(Qt.AlignTop) #type: ignore
        
        self.layouts_dict = {}
        
        #Create the main layout classes
        self.create_main_layout_class(main_layout,"CellSegmentScripts")
        self.create_main_layout_class(main_layout,"CellScoringScripts")
        
        #Add a button below for testing atm
        Test_run_button = QPushButton('Test')
        main_layout.addWidget(Test_run_button, 1) #,1 is weight=1
        # Connect button signals to slots
        Test_run_button.clicked.connect(lambda: self.test_run())
        
        #Add a button below for testing atm
        Save_layout_button = QPushButton('Save layout')
        main_layout.addWidget(Save_layout_button, 1) #,1 is weight=1
        # Connect button signals to slots
        Save_layout_button.clicked.connect(lambda: self.save()) #,parent=self.findChild(QWidget, "tab_autonomous"))
        # #Add a button below for testing atm
        # Load_layout_button = QPushButton('Load layout')
        # main_layout.addWidget(Load_layout_button, 1) #,1 is weight=1
        # # Connect button signals to slots
        # Load_layout_button.clicked.connect(lambda: self.restore(self.autonomous_settings))#parent=self.findChild(QWidget, "tab_autonomous"))
        
        #Add a stretch at the bottom so everything is pushed to the top
        main_layout.addStretch()
        
        #Create a scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)  # Allows the scroll area to resize its widget
        scroll_area.setVerticalScrollBarPolicy(0x0002)  # Always show the vertical scrollbar  #type: ignore
        #Add a content_widget who's only job it is to contain the main_layout
        content_widget = QWidget()
        content_widget.setLayout(main_layout)
        #Add this content_widget to the scroll_area
        scroll_area.setWidget(content_widget)
        #Add a new tab_layout to the tab_autonomous tab in the main GUI
        tab_layout = QVBoxLayout(self.findChild(QWidget, "tab_autonomous")) #type: ignore
        #And give this the scroll_area widget
        tab_layout.addWidget(scroll_area)
        
    def value_is_valid(self,val):
        if isinstance(val, QtGui.QPixmap):
            return not val.isNull()
        return True
    
    # def find_widgets_with_objectname(self, widget, object_name):
    #     layouts = []
    #     if object_name in widget.objectName():
    #         layouts.append(widget.layout())

    #     if isinstance(widget, QWidget):
    #         for child in widget.children():
    #             layouts.extend(self.find_widgets_with_objectname(child, object_name))

    #     return layouts
    
    
    # def find_widgets_method_scoring_from_objectName(self, parent, object_name):
    #     layouts = []
    #     if parent != None:
    #         if object_name in parent.objectName():
    #             layouts.extend(self.find_widgets_in_grid_layout(parent))
    #     return layouts
    
    def find_widgets_in_grid_layout(self,layout):
        widgetsMain = []
        if isinstance(layout, QGridLayout):
            #We look in the first grid layout - this has all the cellSegmentScript possibilities
            for row in range(layout.rowCount()):
                for column in range(layout.columnCount()):
                    item = layout.itemAtPosition(row, column)
                    if item is not None:
                        layout2 = item.layout()
                        if layout2 is not None:
                            #If we find a layout in there, we know that it's the entry of a new cellSegmentScript variables
                            widgets = []
                            #We loop over all row/columns and add
                            for row2 in range(layout2.rowCount()):
                                for column2 in range(layout2.columnCount()):
                                    item = layout2.itemAtPosition(row2, column2)
                                    if item is not None:
                                        widget = item.widget()
                                        if widget is not None:
                                            widgets.append(widget)
                            #and we add the widgets to the widgetsMain
                            widgetsMain.append(widgets)
        return widgetsMain
    
    #Function to find layouts with a certain objectname.
    #Need to input the parent layoutOrWidget, and the name to search for
    def find_layoutsOrWidgets_with_objectname(self, layoutOrWidget, object_name):
        layouts = []
        if layoutOrWidget != None:
            if object_name in layoutOrWidget.objectName():
                # layouts.append(layoutOrWidget)
                layouts.extend(self.find_widgets_in_grid_layout(layoutOrWidget))
                # print(layoutOrWidget.objectName())

            if isinstance(layoutOrWidget, QWidget):
                for child in layoutOrWidget.children():
                    layouts.extend(self.find_layoutsOrWidgets_with_objectname(child, object_name))
            if isinstance(layoutOrWidget,QLayout):
                for i in range(layoutOrWidget.count()):
                    item = layoutOrWidget.itemAt(i)
                    layouts.extend(self.find_layoutsOrWidgets_with_objectname(item.layout(), object_name))

        return layouts
    
    #Function to find layouts with a certain type
    #Need to input the parent layoutOrWidget, and the type to search for
    def find_layoutsOrWidgets_with_type(self, layoutOrWidget, type_name):
        layouts = []
        if layoutOrWidget != None:
            print(layoutOrWidget.objectName())
            if isinstance(layoutOrWidget,type_name):
                layouts.append(layoutOrWidget)
                print(f"Found: {layoutOrWidget.objectName()}")

            if isinstance(layoutOrWidget, QWidget):
                for child in layoutOrWidget.children():
                    layouts.extend(self.find_layoutsOrWidgets_with_type(child, type_name))
            if isinstance(layoutOrWidget,QLayout):
                for i in range(layoutOrWidget.count()):
                    item = layoutOrWidget.itemAt(i)
                    layouts.extend(self.find_layoutsOrWidgets_with_type(item.layout(), type_name))

        return layouts
    
    #Find all children of a layout with a certain type (i.e. QComboBox, QLineEdit)
    def find_children_by_type(self,layout_search,type):
        childrenArr = []
        for children in self.list_layout_children(layout_search):
            if isinstance(children,type):
                childrenArr.append(children)
        return childrenArr
    
    def save(self):
        #Looks for all layouts (or widgets, but shouldn't find any) that have the name 'mainClassLayout' in them
        # layoutsToLookInto = self.find_layoutsOrWidgets_with_objectname(self.findChild(QWidget, "tab_autonomous"),"mainClassLayout")
        layoutsToLookInto = self.find_layoutsOrWidgets_with_objectname(self.findChild(QWidget, "tab_autonomous"),"mainClassLayout")
        #Next, in these layouts look for children of specific types
        #Now, each of these layouts should contain 1 or 2 gridLayouts - method and (maybe) scoring.
        for ms in range(len(layoutsToLookInto)):
            #And then we loop over all layouts in this array
            for layout in layoutsToLookInto[ms]:
                #and for now print if they're doing something interesting
                if isinstance(layout,QComboBox):
                    print(layout.currentText())
                if isinstance(layout,QLineEdit):
                    print(layout.text())
            
            
            #Also look for LineEdits and remember their info
            # self.find_layoutsOrWidgets_with_type(layout.parentWidget(), QComboBox)
            # self.find_layoutsOrWidgets_with_objectname(self.findChild(QWidget, "tab_autonomous"),"LineEdit")
            #And store this as a variable.

    def list_layout_children(self,layout):
        num_children = layout.count()
        children = []

        for i in range(num_children):
            item = layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    children.append(widget)

        return children

    def load_ui(self):
        uic.loadUi(os.path.join(sys.path[0], 'GUI.ui'), self)  # Load the UI file

    def create_main_layout_class(self,main_layout,className):
        layout_main_segment = QVBoxLayout()
        layout_main_segment.setObjectName("layout_main_"+className)
        layout_main_segment.setAlignment(Qt.AlignTop) #type: ignore
        main_layout.addLayout(layout_main_segment)
        # Initialize a list to keep track of added layouts
        self.layouts_dict[className] = []
        # #Setup the dynamic interface
        self.setup_dynamic_interface(main_layout,className)

    def setup_dynamic_interface(self,main_layout,className):
        # Create buttons
        # Get the segments_layout
        tab_widget = self.findChild(QWidget, "tab_autonomous")
        main_layout = tab_widget.layout() #type: ignore
        class_layout = tab_widget.findChild(QVBoxLayout, f"layout_main_{className}")
        
        #Create add/remove buttons
        add_button = QPushButton(f"Add {className} Layout", self)
        
        #Add a Horizontal box
        button_Hbox = QHBoxLayout()
        class_layout.addLayout(button_Hbox) #type: ignore
        
        # Add buttons to the segments layout
        button_Hbox.addWidget(add_button, 1) #,1 is weight=1

        # Connect button signals to slots
        add_button.clicked.connect(lambda: self.add_layout(className))
        
    def add_layout(self,className):
        global UNIQUE_ID
        # Create a new layout
        layout_new = QGridLayout()
        
        # Find the father layout
        tab_widget = self.findChild(QWidget, "tab_autonomous")
        father_layout = tab_widget.findChild(QVBoxLayout, f"layout_main_{className}")
        
        #Add a QLabel TitleWidget for identification
        #Add a title to this label
        # labelTitle = QLabel(f"<b>{className}{UNIQUE_ID}</b>")
        # labelTitle.setObjectName(f"titleLabel_{className}{UNIQUE_ID}");UNIQUE_ID+=1
        # layout_new.addWidget(labelTitle,0,0,1,3)
        
        #Add info to layout_new via the setObjectName:
        layout_new.setObjectName(f"mainClassLayout_{className}_{UNIQUE_ID}");UNIQUE_ID+=1
        
        #Add the remove-button
        remove_button = QPushButton(f"Remove", self)
        layout_new.addWidget(remove_button,1,3)
        remove_button.setObjectName(f"{className}_remove_KEEP")
        remove_button.clicked.connect(lambda: self.remove_this(layout_new,className))
        
        #Create a method-only gridbox
        method_Grid = QGridLayout()
        layout_new.addLayout(method_Grid,1,1)
        # Create a QComboBox and add options - this is the METHOD dropdown
        methodDropdown = QComboBox(self)
        options = HelperFunctions.functionNamesFromDir(className)
        methodDropdown.setObjectName(f"{className}_methodDropdown")
        methodDropdown.addItems(options)
        #Add the methodDropdown to the layout
        method_Grid.addWidget(methodDropdown,1,0,1,2)
        #Activation for methodDropdown.activated
        methodDropdown.activated.connect(lambda: self.changeLayout_choice(method_Grid,className,'method'))
        #On startup/initiatlisation: also do changeLayout_choice
        self.changeLayout_choice(method_Grid,className,'method')
        
        #Create a scoring-only gridbox
        scoring_Grid = QGridLayout()
        layout_new.addLayout(scoring_Grid,1,2)
        #Fill it if it's not segmention
        if className != 'CellSegmentScripts':
            # Create a QComboBox and add options - this is the SCORING dropdown
            scoringDropdown = QComboBox(self)
            options = HelperFunctions.functionNamesFromDir("ScoringMetrics")
            scoringDropdown.setObjectName(f"{className}_scoringDropdown")
            scoringDropdown.addItems(options)
            #Add the methodDropdown to the layout
            scoring_Grid.addWidget(scoringDropdown,1,0,1,2)
            #Activation for methodDropdown.activated
            scoringDropdown.activated.connect(lambda: self.changeLayout_choice(scoring_Grid,className,'scoring'))
            #On startup/initiatlisation: also do changeLayout_choice
            self.changeLayout_choice(scoring_Grid,className,'scoring')

        
        #Add a horizontal line
        horizontal_line = QFrame()
        horizontal_line.setFrameShape(QFrame.HLine)
        horizontal_line.setFrameShadow(QFrame.Sunken)
        horizontal_line.setObjectName("HorLine")
        
        #Set the final line widget
        layout_new.addWidget(horizontal_line,99,0,2,0)

        # Add the layout to the father layout
        father_layout.addLayout(layout_new) #type: ignore
        # Append the new layout to the list so it can be easily found/removed.
        self.layouts_dict[className].append(layout_new)

    #Main def that interacts with a new layout based on whatever entries we have!
    #We assume a X-by-4 (4 columns) size, where 1/2 are used for Operation, and 3/4 are used for Value-->Score conversion
    def changeLayout_choice(self,curr_layout,className,methodorscoring):
        global UNIQUE_ID
        
        #This removes everything except the first entry (i.e. the drop-down menu)
        self.resetLayout(curr_layout,className)
        
        if methodorscoring == 'method':
            #Get the dropdown info
            curr_dropdown = self.getMethodDropdownInfo(curr_layout,className)
            #Get the kw-arguments from the current dropdown.
            reqKwargs = HelperFunctions.reqKwargsFromFunction(curr_dropdown.currentText())
            #Add a widget-pair for every kwarg
            labelposoffset = 0
            for k in range(len(reqKwargs)):
                #Value is used for scoring, and takes the output of the method
                if reqKwargs[k] != 'methodValue':
                    label = QLabel(f"<b>{reqKwargs[k]}</b>")
                    label.setObjectName(f"Label_{UNIQUE_ID}#{curr_dropdown.currentText()}#{reqKwargs[k]}")
                    curr_layout.addWidget(label,2+(k)+labelposoffset,0)
                    line_edit = QLineEdit()
                    line_edit.setObjectName(f"LineEdit_{UNIQUE_ID}#{curr_dropdown.currentText()}#{reqKwargs[k]}")
                    UNIQUE_ID+=1
                    curr_layout.addWidget(line_edit,2+k+labelposoffset,1)
                else:
                    labelposoffset -= 1
                
                
            labelTitle = QLabel(f"Current selected: {curr_dropdown.currentText()}")


            #Get the optional kw-arguments from the current dropdown.
            optKwargs = HelperFunctions.optKwargsFromFunction(curr_dropdown.currentText())
            #Add a widget-pair for every kwarg
            for k in range(len(optKwargs)):
                label = QLabel(f"<i>{optKwargs[k]}</i>")
                label.setObjectName(f"Label_{UNIQUE_ID}#{curr_dropdown.currentText()}#{optKwargs[k]}")
                curr_layout.addWidget(label,2+(k)+len(reqKwargs)+labelposoffset,0)
                line_edit = QLineEdit()
                line_edit.setObjectName(f"LineEdit_{UNIQUE_ID}#{curr_dropdown.currentText()}#{optKwargs[k]}")
                UNIQUE_ID+=1
                curr_layout.addWidget(line_edit,2+(k)+len(reqKwargs)+labelposoffset,1)
        
        elif methodorscoring == 'scoring':
            #Get the dropdown info
            curr_dropdown = self.getScoringDropdownInfo(curr_layout,className)
            
            #Get the kw-arguments from the current dropdown.
            reqKwargs = HelperFunctions.reqKwargsFromFunction(curr_dropdown.currentText())
            #Add a widget-pair for every kwarg
            labelposoffset = 0
            for k in range(len(reqKwargs)):
                if reqKwargs[k] != 'methodValue':
                    label = QLabel(f"<b>{reqKwargs[k]}</b>")
                    label.setObjectName(f"Label_{UNIQUE_ID}#{curr_dropdown.currentText()}#{reqKwargs[k]}")
                    curr_layout.addWidget(label,2+(k)+labelposoffset,0)
                    line_edit = QLineEdit()
                    line_edit.setObjectName(f"LineEdit_{UNIQUE_ID}#{curr_dropdown.currentText()}#{reqKwargs[k]}")
                    UNIQUE_ID+=1
                    curr_layout.addWidget(line_edit,2+k+labelposoffset,1)
                else:
                    labelposoffset -= 1
                
            #Get the optional kw-arguments from the current dropdown.
            optKwargs = HelperFunctions.optKwargsFromFunction(curr_dropdown.currentText())
            #Add a widget-pair for every kwarg
            for k in range(len(optKwargs)):
                label = QLabel(f"<i>{optKwargs[k]}</i>")
                label.setObjectName(f"Label_{UNIQUE_ID}#{curr_dropdown.currentText()}#{optKwargs[k]}")
                curr_layout.addWidget(label,2+(k)+labelposoffset+len(reqKwargs),0)
                line_edit = QLineEdit()
                line_edit.setObjectName(f"LineEdit_{UNIQUE_ID}#{curr_dropdown.currentText()}#{optKwargs[k]}")
                UNIQUE_ID+=1
                curr_layout.addWidget(line_edit,2+(k)+labelposoffset+len(reqKwargs),1)
        

    def getMethodDropdownInfo(self,curr_layout,className):
        curr_dropdown = []
        #Look through all widgets in the current layout
        for index in range(curr_layout.count()):
            widget_item = curr_layout.itemAt(index)
            #Check if it's fair to check
            if widget_item.widget() is not None:
                widget = widget_item.widget()
                #If it's the dropdown segment, label it as such
                if (className in widget.objectName()) and ("methodDropdown" in widget.objectName()):
                    curr_dropdown = widget
        #Return the dropdown
        return curr_dropdown
    
    def getScoringDropdownInfo(self,curr_layout,className):
        curr_dropdown = []
        #Look through all widgets in the current layout
        for index in range(curr_layout.count()):
            widget_item = curr_layout.itemAt(index)
            #Check if it's fair to check
            if widget_item.widget() is not None:
                widget = widget_item.widget()
                #If it's the dropdown segment, label it as such
                if (className in widget.objectName()) and ("scoringDropdown" in widget.objectName()):
                    curr_dropdown = widget
        #Return the dropdown
        return curr_dropdown
                    
    #Remove everythign in this layout except className_dropdown
    def resetLayout(self,curr_layout,className):
        for index in range(curr_layout.count()):
            widget_item = curr_layout.itemAt(index)
            # Check if the item is a widget (as opposed to a layout)
            if widget_item.widget() is not None:
                widget = widget_item.widget()
                #If it's the dropdown segment, label it as such
                if not ("methodDropdown" in widget.objectName()) and not ("scoringDropdown" in widget.objectName())and widget.objectName() != f"Label_{className}" and widget.objectName() != f"titleLabel_{className}" and not ("KEEP" in widget.objectName()):
                    widget.deleteLater()
                    # widget.setParent(None)
        
    def remove_this(self,layout_name,className):
        # Get the segments_layout
        tab_widget = self.findChild(QWidget, "tab_autonomous")
        curr_layout = tab_widget.findChild(QVBoxLayout, f"layout_main_{className}")
        # Get the last added layout from the list
        for i in self.layouts_dict[className]:
            if layout_name == i:
                #remove from the array
                self.layouts_dict[className].remove(i)
                
                # Remove labels from the layout
                while i.count():
                    item = i.takeAt(0)
                    widget = item.widget()
                    if widget is not None:
                        widget.deleteLater()
                        # widget.setParent(None)
            
                # Remove the layout from the segments layout
                curr_layout.removeItem(i)
                i.deleteLater()
                # i.setParent(None)
                
        # print(self.layouts_dict[className])
        # print(layout_name)
        # layout_name.deleteLater()
        
    def remove_layout(self,className):
        if len(self.layouts_dict[className]) > 0:
            # Get the segments_layout
            tab_widget = self.findChild(QWidget, "tab_autonomous")
            main_layout = tab_widget.layout()
            curr_layout = tab_widget.findChild(QVBoxLayout, f"layout_main_{className}")
            
            # Get the last added layout from the list
            if self.layouts_dict[className]:
                layout = self.layouts_dict[className].pop()
                
                # Remove labels from the layout
                while layout.count():
                    item = layout.takeAt(0)
                    widget = item.widget()
                    if widget is not None:
                        widget.deleteLater()
                        # widget.setParent(None)
                
                # Remove the layout from the segments layout
                curr_layout.removeItem(layout)
                layout.deleteLater()
                # layout.setParent(None)

    def getAllEvalsFromModule(self, moduleName):
        #Create an empty array in which we store all the Eval-texts belonging to this module
        moduleMethodEvalTexts = []
        moduleScoringEvalTexts = []
        #First, we find all widgets on tab_autonomous:
        # all_layouts = self.findChild(QWidget, "tab_autonomous").findChildren(QLayout)
        evalModules = self.find_layoutsOrWidgets_with_objectname(self.findChild(QWidget, "tab_autonomous"),f"mainClassLayout_{moduleName}")
        if evalModules != []:
            #Prepare the method kwarg arrays (and an empty name)
            methodKwargNames_scoring = []
            methodKwargValues_scoring = []
            methodName_scoring = ''
            methodKwargNames_method = []
            methodKwargValues_method = []
            methodName_method = ''
            #First scoring modules
            for widget in evalModules[0]:
                if ("LineEdit" in widget.objectName()):
                    # The objectName will be along the lines of foo#bar#str
                    #Check if the objectname is part of a method or part of a scoring
                    split_list = widget.objectName().split('#')
                    methodName_method = split_list[1]
                    methodKwargNames_method.append(split_list[2])
                    methodKwargValues_method.append(widget.text())
            for widget in evalModules[1]:
                if ("LineEdit" in widget.objectName()):
                    # The objectName will be along the lines of foo#bar#str
                    #Check if the objectname is part of a method or part of a scoring
                    split_list = widget.objectName().split('#')
                    methodName_scoring = split_list[1]
                    methodKwargNames_scoring.append(split_list[2])
                    methodKwargValues_scoring.append(widget.text())
        
            #Function call: get the to-be-evaluated text out, giving the methodName, method KwargNames, methodKwargValues, and 'function Type (i.e. cellSegmentScripts, etc)' - do the same with scoring as with method
            if methodName_method != '':
                EvalTextMethod = self.getEvalTextFromGUIFunction(methodName_method, methodKwargNames_method, methodKwargValues_method, moduleName)
                #append this to moduleEvalTexts
                moduleMethodEvalTexts.append(EvalTextMethod)
            if methodName_scoring != '':
                EvalTextScoring = self.getEvalTextFromGUIFunction(methodName_scoring, methodKwargNames_scoring, methodKwargValues_scoring, 'ScoringMetrics', partialStringStart='methodValue=methodOutput',removeKwargs=['methodValue'])
                #append this to moduleEvalTexts
                moduleScoringEvalTexts.append(EvalTextScoring)
        else:
            print(f'NO MODULES FOUND WITH {moduleName}')
        
        #Return all eval text arrays
        return moduleMethodEvalTexts, moduleScoringEvalTexts
    
    def getEvalTextFromGUIFunction(self, methodName, methodKwargNames, methodKwargValues, methodTypeString, partialStringStart=None, removeKwargs=None):
    #--------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #methodName: the physical name of the method, i.e. StarDist.StarDistSegment
    #methodKwargNames: found kwarg NAMES from the GUI
    #methodKwargValues: found kwarg VALUES from the GUI
    #methodTypeString: type of method, i.e. 'function Type' (e.g. CellSegmentScripts, CellScoringScripts etc)'
    #Optionals: partialStringStart: gives a different start to the partial eval-string
    #Optionals: removeKwargs: removes kwargs from assessment (i.e. for scoring script, where this should always be changed by partialStringStart)
    #--------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #We define special cases as function of methodTypeString:
        if methodTypeString == 'CellSegmentScripts':
            specialcaseKwarg = ['image_data'] #Kwarg where the special case is used
            specialcaseKwargPartialStringAddition = ["reqKwargs[id]+\"=\"+kwargvalue"] #text to be eval-ed in case this kwarg is found
        elif methodTypeString == 'CellScoringScripts':
            specialcaseKwarg = ['outline_coords'] #Kwarg where the special case is used
            specialcaseKwargPartialStringAddition = ["reqKwargs[id]+\"=\"+kwargvalue"] #text to be eval-ed in case this kwarg is found
        else:
            specialcaseKwarg = [] #Kwarg where the special case is used
            specialcaseKwargPartialStringAddition = [] #text to be eval-ed in case this kwarg is found
        #We have the method name and all its kwargs, so:
        if len(methodName)>0: #if the method exists
            #Check if all req. kwargs have some value
            reqKwargs = HelperFunctions.reqKwargsFromFunction(methodName)
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
                    #First find the index of the function-based reqKwargs in the GUI-based methodKwargNames. They should be the same, but you never know
                    GUIbasedIndex = methodKwargNames.index(reqKwargs[id])
                    #Get the value of the kwarg - we know the name already now due to reqKwargs.
                    kwargvalue = methodKwargValues[GUIbasedIndex]
                    if kwargvalue == '':
                        allreqKwargsHaveValue = False
                        print(f'EMPTY VALUE of {kwargvalue}, NOT CONTINUING')
                #Get started with empty string for the eval-function
                partialString = ''
                if allreqKwargsHaveValue:
                    #If we're at this point, all req kwargs have a value, so we can run!
                    #Get the string for the required kwargs
                    if partialStringStart is not None:
                        partialString = partialStringStart
                    for id in range(0,len(reqKwargs)):
                        #First find the index of the function-based reqKwargs in the GUI-based methodKwargNames. They should be the same, but you never know
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
                    optKwargs = HelperFunctions.optKwargsFromFunction(methodName)
                    for id in range(0,len(optKwargs)):
                        if methodKwargValues[id+len(reqKwargs)] != '':
                            if partialString != '':
                                partialString+=","
                            partialString+=optKwargs[id]+"=\""+methodKwargValues[id+len(reqKwargs)]+"\""
                segmentEval = methodName+"("+partialString+")"
                return segmentEval
            else:
                print('SOMETHING VERY STUPID HAPPENED')
                return None

    def test_run(self):
        testImageLoc = "./AutonomousMicroscopy/ExampleData/BF_test_avg.tiff"
        # Open the TIFF file
        with tifffile.TiffFile(testImageLoc) as tiff:
            # Read the image data
            ImageData = tiff.asarray()
        
        #First, we find all widgets on tab_autonomous:
        all_layouts = self.findChild(QWidget, "tab_autonomous").findChildren(QLayout)
        # Function to get all segmentEvals from all CellSegmentScripts in the GUI
        segmentMethodEvalArr, segmentScoreEvalArr = self.getAllEvalsFromModule("CellSegmentScripts")

        # Function to get all segmentEvals from all CellScoringScripts in the GUI
        cellScoreMethodEvalArr, cellScoreScoreArr = self.getAllEvalsFromModule("CellScoringScripts")
                
        #Now we can do the calculation!
        #Segmenting
        segmentResult = eval(segmentMethodEvalArr[0])
        #Scoring - method
        methodOutput = eval(cellScoreMethodEvalArr[0])
        #Scoring - score - requires atm 'methodOutput', but should be changed.
        scoreOutput = eval(cellScoreScoreArr[0])
        print('Segmenting performed')
        cellIm = ImageData
        coords = segmentResult
                        
        # Create a figure with two subplots
        fig, axs = plt.subplots(1,2)

        # Plot the first image in the left subplot
        axs[0].imshow(cellIm, cmap='gray')
        axs[0].axis('off')

        cmap = colormaps.get_cmap('bwr')
        # Plot the second image in the right subplot
        im = axs[1].imshow(cellIm, cmap='gray')
        # Plot colorful outlines on the image
        for i in range(0,len(coords)):
            contour = coords[i]
            axs[1].plot(contour[1], contour[0], color=cmap(scoreOutput[i]))
        axs[1].set_xlim(0, cellIm.shape[1])
        axs[1].set_ylim(cellIm.shape[0], 0)
        axs[1].axis('off')
        axs[1].set_title(cellScoreMethodEvalArr[0])
        plt.show()
        
        print('All run correctly!')


if __name__ == "__main__":
    try:
        # get object representing MMCore, used throughout
        core = Core()

        #Open JSON file with MM settings
        with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
            MM_JSON = json.load(f)

        #Load UI settings
        # Form, Window = uic.loadUiType(os.path.join(sys.path[0], 'GUI.ui'))

        #Setup UI
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        # app = QApplication(sys.argv)
        # window = Window()
        # form = Form()
        # form.setupUi(window)
        z=2
        #Run the laserController UI
        runlaserControllerUI(core,MM_JSON,window,app)

        #Show window and start app
        window.show()
        app.exec()
        # sys.exit(app.exec_())

    except:
        print('No micromanager, test mode!')

        #Open JSON file with MM settings
        with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
            MM_JSON = json.load(f)

        #Load UI settings
        # Form, Window = uic.loadUiType(os.path.join(sys.path[0], 'GUI.ui'))

        #Setup UI
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()

        #Show window and start app
        window.show()
        # app.exec()
        sys.exit(app.exec_())


