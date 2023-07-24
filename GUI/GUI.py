
from PyQt5.QtWidgets import QGridLayout, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpacerItem, QSizePolicy
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
#For drawing
import matplotlib
matplotlib.use('Qt5Agg')
# from PyQt5 import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
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
        remove_button = QPushButton(f"Remove {className} Layout", self)
        
        #Add a Horizontal box
        button_Hbox = QHBoxLayout()
        class_layout.addLayout(button_Hbox)
        
        # Add buttons to the segments layout
        # button_Hbox.addWidget(dropdown, 2) #,1 is weight=1
        button_Hbox.addWidget(add_button, 1) #,1 is weight=1
        button_Hbox.addWidget(remove_button, 1) #,1 is weight=1

        # Connect button signals to slots
        add_button.clicked.connect(lambda: self.add_layout(className))
        remove_button.clicked.connect(lambda: self.remove_layout(className))

    def add_layout(self,className):
        # Create a new layout (QHBoxLayout) with a unique name
        layout_new = QGridLayout()
        
        # Get the segments layout
        tab_widget = self.findChild(QWidget, "tab_autonomous")
        main_layout = tab_widget.layout()
        father_layout = tab_widget.findChild(QVBoxLayout, f"layout_main_{className}")
        
        # Create a QComboBox and add options
        dropdown = QComboBox(self)
        options = HelperFunctions.functionNamesFromDir(className)
        dropdown.setObjectName(f"{className}_dropdown")
        dropdown.addItems(options)
        
        #Add the dropdown to the layout and go
        layout_new.addWidget(dropdown)
        
        #What to do if something is chosen?
        dropdown.activated.connect(lambda: self.changeLayout_choice(layout_new,className))
        #Also do this for the default choice
        self.changeLayout_choice(layout_new,className)

        # Add the layout to the father layout
        father_layout.addLayout(layout_new)
        
        # Append the new layout to the list
        self.layouts_dict[className].append(layout_new)

    def changeLayout_choice(self,curr_layout,className):
        #This removes everything except the first entry (i.e. the drop-down menu)
        self.resetLayout(curr_layout,className)
        #Get the dropdown info
        #Look through all widgets in the current layout
        for index in range(curr_layout.count()):
            widget_item = curr_layout.itemAt(index)
            #Check if it's fair to check
            if widget_item.widget() is not None:
                widget = widget_item.widget()
                #If it's the dropdown segment, label it as such
                if widget.objectName() == f"{className}_dropdown":
                    curr_dropdown = widget
        
        #Get the arguments
        
        
        #To test, add a widget:
        label1 = QLabel(f"Current selected: {curr_dropdown.currentText()}")
        label2 = QLabel(f"ReqKwargs: {HelperFunctions.reqKwargsFromFunction(curr_dropdown.currentText())}" )
        label3 = QLabel(f"OptKwargs: {HelperFunctions.optKwargsFromFunction(curr_dropdown.currentText())}" )
        curr_layout.addWidget(label1)
        curr_layout.addWidget(label2)
        curr_layout.addWidget(label3)

    #Remove everythign in this layout except className_dropdown
    def resetLayout(self,curr_layout,className):
        for index in range(curr_layout.count()):
            widget_item = curr_layout.itemAt(index)
            # Check if the item is a widget (as opposed to a layout)
            if widget_item.widget() is not None:
                widget = widget_item.widget()
                #If it's the dropdown segment, label it as such
                if widget.objectName() != f"{className}_dropdown":
                    widget.deleteLater()
        
    def add_layout_OLD(self,className):
        # Create a new layout (QHBoxLayout) with a unique name
        layout_new = QVBoxLayout()
        
        # Get the segments layout
        tab_widget = self.findChild(QWidget, "tab_autonomous")
        main_layout = tab_widget.layout()
        father_layout = tab_widget.findChild(QVBoxLayout, f"layout_main_{className}")
        
        #Figure out which drop-down is used
        # Loop through the child widgets and print information about each widget
        segments_dropdown=[]
        #itemAt(0) points towards a HBox inside father_layout
        for index in range(father_layout.itemAt(0).count()):
            widget_item = father_layout.itemAt(0).itemAt(index)
            # Check if the item is a widget (as opposed to a layout)
            # print(f"WidgetItem at index {index}: {type(widget_item).__name__}")
            if widget_item.widget() is not None:
                widget = widget_item.widget()
                #If it's the dropdown segment, label it as such
                if widget.objectName() == f"{className}_dropdown":
                    father_dropdown = widget

        
        # Create labels for the layout
        label1 = QLabel(f"Current selected: {father_dropdown.currentText()}")
        label2 = QLabel(f"Label 2 - Segment layout {HelperFunctions.kwargsFromFunction(father_dropdown.currentText())}")
        label3 = QLabel(f"All Segment options: {HelperFunctions.functionNamesFromDir(className)}")
        
        # Add the labels to the layout
        layout_new.addWidget(label1)
        layout_new.addWidget(label2)
        layout_new.addWidget(label3)
        
        # Add the layout to the layouts layout
        father_layout.addLayout(layout_new)
        
        # Append the new layout to the list
        self.layouts_dict[className].append(layout_new)
        
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


