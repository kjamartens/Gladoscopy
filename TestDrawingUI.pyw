
from PyQt5 import uic
from PyQt5.QtWidgets import QApplication
import PyQt5.QtWidgets
import json
#from pycromanager import Core
import numpy as np
import sys
import os
import time
import asyncio
import pyqtgraph as pg

import sys
import matplotlib
matplotlib.use('Qt5Agg')

from PyQt5 import QtCore, QtWidgets

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

def drawplot(xdatalist,ydatalist,collist):
    nrlines = len(xdatalist)
    if len(ydatalist) != nrlines:
        print("ERROR! Not correct nr of x and y data lists")

    print("Plotting " + str(nrlines) + " lines")
    #Initialise graph widget
    form.graphWidget.setBackground('w')
    form.graphWidget.setTitle("New title", color="k")
    labelstyle = {'color':'k', 'font-size':'10px'}
    form.graphWidget.setLabel('left', 'Temperature (°C)', **labelstyle)
    form.graphWidget.setLabel('bottom', 'Hour (H)', **labelstyle)
    form.graphWidget.showGrid(x=True, y=True)

    #Draw individual lines
    for i in range(0,nrlines):
        #pen = pg.mkPen(color=(255, 0, 0), width=5)
        #my_line_ref = form.graphWidget.plot([1,2,3,4,5,6,7,8,9,10], [30,32,34,32,33,31,29,32,35,45], pen=pen)
        drawsingleline(xdatalist[i],ydatalist[i],collist[i])

def drawsingleline(xdata,ydata,col):
    pen = pg.mkPen(color=col, width=2)
    form.graphWidget.plot(xdata, ydata, pen=pen)
#--------------------------------------------------------------------------------------
#End of functions
#--------------------------------------------------------------------------------------

#Following guide on https://www.pythonguis.com/tutorials/embed-pyqtgraph-custom-widgets-qt-app/

#Load UI settings
Form, Window = uic.loadUiType(os.path.join(sys.path[0], 'TestPlots.ui'))
#Form, Window = uic.loadUiType(os.path.join(sys.path[0], 'UILaserController.ui'))

app = QApplication([])
window = Window()
form = Form()
form.setupUi(window)

#Also see https://www.pythonguis.com/tutorials/plotting-pyqtgraph/
drawplot([[1,2,3],[1,2,3]],[[1,2,3],[3,2,1]],['k','b'])

#Show window and start app
window.show()
app.exec()
