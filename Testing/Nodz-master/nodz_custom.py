import os
import re
import json

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtWidgets import QLineEdit, QInputDialog, QDialog, QLineEdit, QComboBox, QVBoxLayout, QDialogButtonBox, QMenu, QAction
from PyQt5.QtGui import QFont, QColor, QTextDocument, QAbstractTextDocumentLayout
from PyQt5.QtCore import QRectF
import nodz_utils as utils

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
