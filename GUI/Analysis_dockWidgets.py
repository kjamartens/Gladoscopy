from PyQt5.QtWidgets import QGridLayout, QPushButton
from AnalysisClass import *
import napariGlados

class analysisDockWidget:
    def __init__(self,napariViewer):
        self.napariViewer = napariViewer
        #Create a Vertical+horizontal layout:
        self.mainLayout = QGridLayout()
        #Create a layout for the configs:
        self.analysisLayout = QGridLayout()
        #Add this to the mainLayout:
        self.mainLayout.addLayout(self.analysisLayout,0,0)
        #Add a button
        self.Button1 = QPushButton('Mean grayscale value')
        self.analysisLayout.addWidget(self.Button1,1,0)
        #add a connection to the button:
        self.Button1.clicked.connect(lambda index: self.startThread('AvgGrayValueText'))
        
        
        self.Button2 = QPushButton('Random')
        self.analysisLayout.addWidget(self.Button2,2,0)
        #add a connection to the button:
        self.Button2.clicked.connect(lambda index: self.startThread('Random'))
        
        self.Button2 = QPushButton('GrayValOverlay')
        self.analysisLayout.addWidget(self.Button2,3,0)
        #add a connection to the button:
        self.Button2.clicked.connect(lambda index: self.startThread('GrayValueOverlay'))
        
        self.Button2 = QPushButton('Cell Segment Overlay')
        self.analysisLayout.addWidget(self.Button2,4,0)
        #add a connection to the button:
        self.Button2.clicked.connect(lambda index: self.startThread('CellSegmentOverlay'))
    
    def startThread(self,analysisInfo):
        print('Starting analysis ' + analysisInfo)
        # create_analysis_thread(napariGlados.obtain_imageQueueAnalysis(),shared_data,analysisInfo=analysisInfo)
        create_analysis_thread(shared_data,analysisInfo=analysisInfo)
        
        #Append it to the list of analysisThreads
        # shared_data.analysisThreads.append(analysis_thread)
    


def analysis_dockWidget(MM_JSON,main_layout,sshared_data):
    global shared_data, napariViewer
    shared_data = sshared_data
    napariViewer = shared_data.napariViewer
    
    #Create the MM config via all config groups
    MMconfig = analysisDockWidget(napariViewer)
    main_layout.addLayout(MMconfig.mainLayout)
    
    return MMconfig