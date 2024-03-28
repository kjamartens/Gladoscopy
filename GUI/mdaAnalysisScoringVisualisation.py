import numpy as np
from PyQt5.QtWidgets import QGridLayout, QPushButton
import sys
# Add the folder 2 folders up to the system path
import os
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
#Obtain the helperfunctions
import HelperFunctions #type: ignore

from napariHelperFunctions import getLayerIdFromName, InitateNapariUI
from utils import cleanUpTemporaryFiles
import numpy as np
from PyQt5.QtCore import pyqtSignal
import napari
import math
from napari.qt import thread_worker
import time
import queue
from PyQt5.QtWidgets import QMainWindow
from pycromanager import Core
from magicgui import magicgui
from qtpy.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QScrollArea
import sys
from custom_widget_ui import Ui_CustomDockWidget  # Import the generated UI module
import logging
import os

from AutonomousMicroscopyScripts import *

class CustomMDA():
    def __init__(self):
        self.ROI = None
    
    def getMDA(self):
        #Do the MDA
        with JavaBackendAcquisition(directory='', name='Test', show_display=False) as acq: #type:ignore
            events = self.mdaparams
            acq.acquire(events)
        
        data = acq.get_dataset()        
        
        return data

    def setmdaparams(self,params):
        self.mdaparams = params
        print(self.mdaparams)

class mdaASTDockWidget():
    def __init__(self,napariViewer):
        self.napariViewer = napariViewer
        #Create a Vertical+horizontal layout:
        self.mainLayout = QGridLayout()
        #Create a layout for the configs:
        self.analysisLayout = QGridLayout()
        #Add this to the mainLayout:
        self.mainLayout.addLayout(self.analysisLayout,0,0)
        #Add a button
        self.Button1 = QPushButton('Testing small MDA and grayvalue determination')
        self.analysisLayout.addWidget(self.Button1,1,0)
        #add a connection to the button:
        self.Button1.clicked.connect(lambda index: self.testMDAGrayscale())

    def testMDAGrayscale(self):
        scoringMDA = CustomMDA()
        scoringMDA.setmdaparams([{'axes': {'time': 0}, 'min_start_time': 0.0}, {'axes': {'time': 1}, 'min_start_time': 0.001}])
        ImageData = scoringMDA.getMDA()
        #Throw this into the analysis:
        print('MDA done!')
        avgGrayVal = eval(HelperFunctions.createFunctionWithKwargs("AverageIntensity.AvgGrayValue",NDTIFFStack="ImageData"))
        
        print(f"found avg gray val: {avgGrayVal}")

def mdaAnalysisScoringTest_dockWidget(core,MM_JSON,main_layout,sshared_data):
    global shared_data, napariViewer
    shared_data = sshared_data
    napariViewer = shared_data.napariViewer
    
    #Create the MM config via all config groups
    mdaAST = mdaASTDockWidget(napariViewer)
    main_layout.addLayout(mdaAST.mainLayout,0,0)