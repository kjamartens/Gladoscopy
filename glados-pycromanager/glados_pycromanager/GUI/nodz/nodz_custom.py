import os
import re
import json

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtWidgets import QLineEdit, QInputDialog, QDialog, QLineEdit, QComboBox, QVBoxLayout, QDialogButtonBox, QMenu, QAction
from PyQt5.QtGui import QFont, QColor, QTextDocument, QAbstractTextDocumentLayout
from PyQt5.QtCore import QRectF


def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    import glados_pycromanager.GUI.nodz.nodz_utils as utils
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI, ConfigInfo
    from glados_pycromanager.GUI.MDAGlados import MDAGlados
else:
    import nodz.nodz_utils as utils
    from MMcontrols import MMConfigUI, ConfigInfo
    from MDAGlados import MDAGlados

""" 
Custom nodz attachments
"""
