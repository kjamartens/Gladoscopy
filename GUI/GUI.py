
from PyQt5.QtWidgets import QLayout, QLineEdit, QFrame, QGridLayout, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpacerItem, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QResizeEvent, QIcon, QPixmap
from PyQt5 import uic
import sys
import os
# import PyQt5.QtWidgets
import json
from pycromanager import *
import numpy as np
import time
import asyncio
import pyqtgraph as pg
import matplotlib.pyplot as plt
from matplotlib import colormaps # type: ignore
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
        
        #Load the UI
        self.load_ui()
        #Set Icon
        #For some reason, this needs abs path rather than rel, so os.path
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.setWindowIcon(QIcon(os.path.join(dir_path,"Icons/GladosIcon.png")))
        
        
        # Create a QVBoxLayout for the tab_autonomous widget
        # Get the tab_autonomous widget
        tab_widget = self.findChild(QWidget, "tab_autonomous")
        main_layout = QVBoxLayout(tab_widget)
        main_layout.setAlignment(Qt.AlignTop)
        
        self.layouts_dict = {}
        
        self.create_main_layout_class(main_layout,"CellSegmentScripts")
        self.create_main_layout_class(main_layout,"CellScoringScripts")
        
        tab_widget.setLayout(main_layout)
        
        #Add a button below for testing atm
        Test_run_button = QPushButton('Test')
        # Add buttons to the segments layout
        main_layout.addWidget(Test_run_button, 1) #,1 is weight=1

        # Connect button signals to slots
        Test_run_button.clicked.connect(lambda: self.test_run())
        # Add an additional widget below the layouts
        # additional_widget = QLabel("Additional Widget")
        # self.addWidget(additional_widget)

    def load_ui(self):
        uic.loadUi(os.path.join(sys.path[0], 'GUI.ui'), self)  # Load the UI file

    def create_main_layout_class(self,main_layout,className):
        layout_main_segment = QVBoxLayout()
        layout_main_segment.setObjectName("layout_main_"+className)
        main_layout.addLayout(layout_main_segment)
        # Initialize a list to keep track of added layouts
        self.layouts_dict[className] = []
        # #Setup the dynamic interface
        self.setup_dynamic_interface(main_layout,className)

    def setup_dynamic_interface(self,main_layout,className):
        # Create buttons
        # Get the segments_layout
        tab_widget = self.findChild(QWidget, "tab_autonomous")
        main_layout = tab_widget.layout()
        class_layout = tab_widget.findChild(QVBoxLayout, f"layout_main_{className}")
        
        #Create add/remove buttons
        add_button = QPushButton(f"Add {className} Layout", self)
        
        #Add a Horizontal box
        button_Hbox = QHBoxLayout()
        class_layout.addLayout(button_Hbox)
        
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
        layout_new.setObjectName(f"mainLayout_{className}_{UNIQUE_ID}");UNIQUE_ID+=1
        
        #Add the remove-button
        remove_button = QPushButton(f"Remove", self)
        layout_new.addWidget(remove_button,1,5)
        remove_button.setObjectName(f"{className}_remove_KEEP")
        remove_button.clicked.connect(lambda: self.remove_this(layout_new,className))
        
        # Create a QComboBox and add options - this is the METHOD dropdown
        methodDropdown = QComboBox(self)
        options = HelperFunctions.functionNamesFromDir(className)
        methodDropdown.setObjectName(f"{className}_methodDropdown")
        methodDropdown.addItems(options)
        #Add the methodDropdown to the layout
        layout_new.addWidget(methodDropdown,1,0,1,2)
        #Activation for methodDropdown.activated
        methodDropdown.activated.connect(lambda: self.changeLayout_choice(layout_new,className))
        
        if className != 'CellSegmentScripts':
            # Create a QComboBox and add options - this is the SCORING dropdown
            scoringDropdown = QComboBox(self)
            options = HelperFunctions.functionNamesFromDir("ScoringMetrics")
            scoringDropdown.setObjectName(f"{className}_scoringDropdown")
            scoringDropdown.addItems(options)
            #Add the methodDropdown to the layout
            layout_new.addWidget(scoringDropdown,1,2,1,2)
            #Activation for methodDropdown.activated
            scoringDropdown.activated.connect(lambda: self.changeLayout_choice(layout_new,className))

        #Most entries are filled in changeLayout_choice!

        #On startup/initiatlisation: also do changeLayout_choice
        self.changeLayout_choice(layout_new,className)
        
        # Add the layout to the father layout
        father_layout.addLayout(layout_new)
        # Append the new layout to the list so it can be easily found/removed.
        self.layouts_dict[className].append(layout_new)

    #Main def that interacts with a new layout based on whatever entries we have!
    #We assume a X-by-4 (4 columns) size, where 1/2 are used for Operation, and 3/4 are used for Value-->Score conversion
    def changeLayout_choice(self,curr_layout,className):
        global UNIQUE_ID
        
        #This removes everything except the first entry (i.e. the drop-down menu)
        self.resetLayout(curr_layout,className)
        #Get the dropdown info
        curr_dropdown = self.getMethodDropdownInfo(curr_layout,className)
        
        #Get the kw-arguments from the current dropdown.
        reqKwargs = HelperFunctions.reqKwargsFromFunction(curr_dropdown.currentText())
        #Add a widget-pair for every kwarg
        for k in range(len(reqKwargs)):
            label = QLabel(f"<b>{reqKwargs[k]}</b>")
            curr_layout.addWidget(label,2+(k),0)
            line_edit = QLineEdit()
            line_edit.setObjectName(f"LineEdit_{UNIQUE_ID}#{curr_dropdown.currentText()}#{reqKwargs[k]}")
            UNIQUE_ID+=1
            curr_layout.addWidget(line_edit,2+k,1)
            
            
        labelTitle = QLabel(f"Current selected: {curr_dropdown.currentText()}")
            
        #Get the optional kw-arguments from the current dropdown.
        optKwargs = HelperFunctions.optKwargsFromFunction(curr_dropdown.currentText())
        #Add a widget-pair for every kwarg
        for k in range(len(optKwargs)):
            label = QLabel(f"<i>{optKwargs[k]}</i>")
            curr_layout.addWidget(label,2+(k)+len(reqKwargs),0)
            line_edit = QLineEdit()
            line_edit.setObjectName(f"LineEdit_{UNIQUE_ID}#{curr_dropdown.currentText()}#{optKwargs[k]}")
            UNIQUE_ID+=1
            curr_layout.addWidget(line_edit,2+(k)+len(reqKwargs),1)
        
        try:
            #Get the dropdown info
            curr_dropdown = self.getScoringDropdownInfo(curr_layout,className)
            
            #Get the kw-arguments from the current dropdown.
            reqKwargs = HelperFunctions.reqKwargsFromFunction(curr_dropdown.currentText())
            #Add a widget-pair for every kwarg
            for k in range(len(reqKwargs)):
                label = QLabel(f"<b>{reqKwargs[k]}</b>")
                curr_layout.addWidget(label,2+(k),2)
                line_edit = QLineEdit()
                line_edit.setObjectName(f"LineEdit_{UNIQUE_ID}_{curr_dropdown.currentText()}_{reqKwargs[k]}")
                UNIQUE_ID+=1
                curr_layout.addWidget(line_edit,2+k,3)
                
            #Get the optional kw-arguments from the current dropdown.
            optKwargs = HelperFunctions.optKwargsFromFunction(curr_dropdown.currentText())
            #Add a widget-pair for every kwarg
            for k in range(len(optKwargs)):
                label = QLabel(f"<i>{optKwargs[k]}</i>")
                curr_layout.addWidget(label,2+(k)+len(reqKwargs),2)
                line_edit = QLineEdit()
                line_edit.setObjectName(f"LineEdit_{UNIQUE_ID}_{curr_dropdown.currentText()}_{optKwargs[k]}")
                UNIQUE_ID+=1
                curr_layout.addWidget(line_edit,2+(k)+len(reqKwargs),3)
        except:
            print('Scoring Dropdown not found!')
        
        
        #Add a horizontal line
        horizontal_line = QFrame()
        horizontal_line.setFrameShape(QFrame.HLine)
        horizontal_line.setFrameShadow(QFrame.Sunken)
        horizontal_line.setObjectName("HorLine")
        
        #Set the final line widget
        curr_layout.addWidget(horizontal_line,99,0,2,0)

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
                if not ("methodDropdown" in widget.objectName()) and not ("scoringDropdown" in widget.objectName()) and widget.objectName() != f"titleLabel_{className}" and not ("KEEP" in widget.objectName()):
                    widget.deleteLater()
        
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
            
                # Remove the layout from the segments layout
                curr_layout.removeItem(i)
                i.deleteLater()
                
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
                
                # Remove the layout from the segments layout
                curr_layout.removeItem(layout)
                layout.deleteLater()

    def test_run(self):
        testImageLoc = "./AutonomousMicroscopy/ExampleData/BF_test_avg.tiff"
        # Open the TIFF file
        with tifffile.TiffFile(testImageLoc) as tiff:
            # Read the image data
            ImageData = tiff.asarray()
            
            
        #Let's try to print all info of all CellSegmentScripts layouts
        #First, we find all widgets on tab_autonomous:
        all_layouts = self.findChild(QWidget, "tab_autonomous").findChildren(QLayout)
        for layout in all_layouts:
            #Select only the correct layout
            if ("mainLayout" in layout.objectName()) and ("CellSegmentScripts" in layout.objectName()):
                print(f'Widgets in {layout.objectName()}:')
                #Prepare the method kwarg arrays (and an empty name)
                methodKwargNames = []
                methodKwargValues = []
                methodName = ''
                for index in range(layout.count()):
                    item = layout.itemAt(index)
                    widget = item.widget()
                    
                    if ("LineEdit" in widget.objectName()):
                        # The objectName willb e along the lines of foo#bar#str
                        split_list = widget.objectName().split('#')
                        methodName = split_list[1]
                        methodKwargNames.append(split_list[2])
                        methodKwargValues.append(widget.text())
                
                #Now we should have the method name and all its kwargs, so:
                if len(methodName)>0:
                    #Check if all req. kwargs have some value
                    reqKwargs = HelperFunctions.reqKwargsFromFunction(methodName)
                    
                    allreqKwargsHaveValue = True
                    for id in range(0,len(reqKwargs)):
                        kwargvalue = methodKwargValues[id]
                        if kwargvalue == '':
                            allreqKwargsHaveValue = False
                            print('EMPTY VALUE, NOT CONTINUING')
                    if allreqKwargsHaveValue:
                        #If we're at this point, all req kwargs have a value, so we can run!
                        #Get the string for the required kwargs
                        partialString = ''
                        for id in range(0,len(reqKwargs)):
                            kwargvalue = methodKwargValues[id]
                            if partialString != '':
                                partialString+=","
                            if reqKwargs[id] == 'image_data':
                                partialString+=reqKwargs[id]+"="+kwargvalue+""
                            else:
                                partialString+=reqKwargs[id]+"=\""+kwargvalue+"\""
                        #Add the optional kwargs if they have a value
                        optKwargs = HelperFunctions.optKwargsFromFunction(methodName)
                        for id in range(0,len(optKwargs)):
                            if methodKwargValues[id+len(reqKwargs)] != '':
                                if partialString != '':
                                    partialString+=","
                                partialString+=optKwargs[id]+"=\""+methodKwargValues[id+len(reqKwargs)]+"\""
                        
                        print(partialString)
                        
                        
                        # coords = eval(HelperFunctions.createFunctionWithKwargs("StarDist.StarDistSegment",image_data="ImageData",modelStorageLoc="\"./AutonomousMicroscopy/ExampleData/StarDistModel\"",prob_thresh="0.35",nms_thresh="0.2"))


                        #And RUN
                        print(methodName+"("+partialString+")")
                        coords = eval(methodName+"("+partialString+")")
                        
                        
                        # coords = eval(HelperFunctions.createFunctionWithKwargs(
                        #     methodName,image_data="ImageData",modelStorageLoc="\"./AutonomousMicroscopy/ExampleData/StarDistModel\"",prob_thresh="0.35",nms_thresh="0.2"))
    
        
                        # 


                        #Non-preloaded stardistsegmentation
                        # coords = eval(HelperFunctions.createFunctionWithKwargs("StarDist.StarDistSegment",image_data="ImageData",modelStorageLoc="\"./AutonomousMicroscopy/ExampleData/StarDistModel\"",prob_thresh="0.35",nms_thresh="0.2"))

                        #Get cell image
                        cellIm = ImageData
                        # #start creating celloverlayimage
                        # cellOverlayIm = np.zeros(l.shape)
                        # for i in range(1,np.amax(l)):
                        #     cellOverlayIm[l==i] = scoreVisual[i-1]

                        # Create a figure with two subplots
                        fig, axs = plt.subplots(2, 2)

                        # Plot the first image in the left subplot
                        axs[0,0].imshow(cellIm, cmap='gray')
                        axs[0,0].axis('off')

                        cmap = colormaps.get_cmap('bwr')
                        # Plot the second image in the right subplot
                        im = axs[0,1].imshow(cellIm, cmap='gray')
                        # Plot colorful outlines on the image
                        for i in range(0,len(coords)):
                            contour = coords[i]
                            axs[0,1].plot(contour[1], contour[0]) #color=cmap(cellCrowdedness_gauss[i])
                        axs[0,1].set_xlim(0, cellIm.shape[1])
                        axs[0,1].set_ylim(cellIm.shape[0], 0)
                        axs[0,1].axis('off')
                        axs[0,1].set_title('cellCrowdedness_gauss')
                        plt.show()
        print('RUN SCRIPTS HERE')
        
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


