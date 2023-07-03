
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QResizeEvent
from PyQt5 import uic
# import PyQt5.QtWidgets
import json
from pycromanager import *
import numpy as np
import sys
import os
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

from LaserControlScripts import *


class MainWindow(QMainWindow):
    #Intialisation
    def __init__(self):
        super().__init__()
        #Load the UI
        self.load_ui()
        #Setup the dynamic interface
        self.setup_dynamic_interface()

    def load_ui(self):
        uic.loadUi(os.path.join(sys.path[0], 'GUI.ui'), self)  # Load the UI file
        # uic.loadUi("C:\\Users\\Koen Martens\\Documents\\GitHub\\ScopeGUI\\AutonomousMicroscopy\\UI\\GUI_temp.ui",self)
        # uic.loadUi("C:\\Users\\Koen Martens\\Documents\\GitHub\\ScopeGUI\\GUI\\GUI_temp.ui",self)

    def setup_dynamic_interface(self):
        # Get the tab_autonomous widget
        tab_widget = self.findChild(QWidget, "tab_autonomous")
        
        # Create a QVBoxLayout for the tab_autonomous widget
        main_layout = QVBoxLayout(tab_widget)
        main_layout.setAlignment(Qt.AlignTop)
        tab_widget.setLayout(main_layout)
        
        # Create a QVBoxLayout for the layouts
        layouts_layout = QVBoxLayout()
        
        # Initialize the layout count
        self.layout_count = 0
        
        # Create buttons
        add_button = QPushButton("Add Layout", self)
        remove_button = QPushButton("Remove Layout", self)
        
        # Connect button signals to slots
        add_button.clicked.connect(self.add_layout)
        remove_button.clicked.connect(self.remove_layout)
        
        # Add buttons to the layouts layout
        layouts_layout.addWidget(add_button)
        layouts_layout.addWidget(remove_button)
        
        # Add the layouts layout to the main layout
        main_layout.addLayout(layouts_layout)
        
        # Add an additional widget below the layouts
        additional_widget = QLabel("Additional Widget")
        main_layout.addWidget(additional_widget)
        
    def add_layout(self):
        # Increase the layout count
        self.layout_count += 1
        
        # Create a new layout (QHBoxLayout) with a unique name
        layout = QVBoxLayout()
        
        # Create labels for the layout
        label1 = QLabel(f"Label 1 - Layout {self.layout_count}")
        label2 = QLabel(f"Label 2 - Layout {self.layout_count}")
        label3 = QLabel(f"Label 3 - Layout {self.layout_count}")
        
        # Add the labels to the layout
        layout.addWidget(label1)
        layout.addWidget(label2)
        layout.addWidget(label3)
        
        # Get the layouts layout
        tab_widget = self.findChild(QWidget, "tab_autonomous")
        main_layout = tab_widget.layout()
        layouts_layout = main_layout.itemAt(0)
        
        # Add the layout to the layouts layout
        layouts_layout.addLayout(layout)
        
    def remove_layout(self):
        if self.layout_count > 0:
            # Get the tab_autonomous widget and its layout
            tab_widget = self.findChild(QWidget, "tab_autonomous")
            main_layout = tab_widget.layout()
            layouts_layout = main_layout.itemAt(0)
            
            # Remove the last layout from the layouts layout
            layout = layouts_layout.itemAt(self.layout_count - 1 + 2).layout()
            
            # Remove labels from the layout
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            
            layouts_layout.removeItem(layout)
            layout.deleteLater()
            
            # Decrease the layout count
            self.layout_count -= 1


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
        # app.exec()
        sys.exit(app.exec_())

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


