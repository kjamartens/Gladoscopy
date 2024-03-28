import os
import re
import json

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtWidgets import QLineEdit, QInputDialog, QDialog, QLineEdit, QComboBox, QVBoxLayout, QDialogButtonBox, QMenu, QAction
from PyQt5.QtGui import QFont, QColor, QTextDocument, QAbstractTextDocumentLayout
from PyQt5.QtCore import QRectF
import nodz_utils as utils

from MMcontrols import MMConfigUI, ConfigInfo, MDAGlados

""" 
Custom nodz attachments
"""

class AdvancedInputDialog(QDialog):
    def __init__(self, parent=None, parentData=None):
        super().__init__(parent)
        
        self.setWindowTitle("Advanced Input Dialog")
        
        # Create line edit
        self.line_edit = QLineEdit()
        
        # Create combobox
        self.combo_box = QComboBox()
        self.combo_box.addItems(["Option 1", "Option 2", "Option 3"])
        
        # Create button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        # Create layout
        layout = QVBoxLayout()
        layout.addWidget(self.line_edit)
        layout.addWidget(self.combo_box)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        
    def getInputs(self):
        return self.line_edit.text(), self.combo_box.currentText()


class nodz_openMDADialog(QDialog):
    def __init__(self, parent=None, parentData=None):
        super().__init__(parent)
        
        self.setWindowTitle("MDA Dialog")
        if parentData is not None:
            from PyQt5.QtWidgets import QApplication, QVBoxLayout, QMainWindow, QWidget
            testQWidget = QWidget()
            
            self.mdaconfig = MDAGlados(parentData.core,None,None,parentData.shared_data,hasGUI=True)
            
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
            

            # Create the QVBoxLayout
            layout = QVBoxLayout()

            # Create a QWidget to contain the QGridLayout
            grid_widget = QWidget()
            grid_widget.setLayout(self.mdaconfig.gui)
            # Add the QMainWindow to the QVBoxLayout
            layout.addWidget(grid_widget)

            layout.addWidget(button_box)
            
            self.setLayout(layout)
        
    def getInputs(self):
        return self.mdaconfig.mda


class FoVFindImaging_singleCh_configs(QDialog):
    def __init__(self, parent=None, parentData=None):
        super().__init__(parent)
        
        self.setWindowTitle("Advanced Input Dialog")
        if parentData is not None:
            core = parentData.core
            
            
            # Get all config groups
            allConfigGroups={}
            nrconfiggroups = core.get_available_config_groups().size()
            for config_group_id in range(nrconfiggroups):
                allConfigGroups[config_group_id] = ConfigInfo(core,config_group_id)
            
            #Create the MM config via all config groups
            self.MMconfig = MMConfigUI(allConfigGroups, showConfigs = True,showStages=False,showROIoptions=False,showLiveMode=False,number_config_columns=5,changes_update_MM = False, showCheckboxes=True)
            
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
                
            #Set the layout
            layout = QVBoxLayout()
            layout.addLayout(self.MMconfig.mainLayout)
            layout.addWidget(button_box)
            
            self.setLayout(layout)
        
    def getInputs(self):
        return self.MMconfig.getUIConfigInfo(onlyChecked=True)
