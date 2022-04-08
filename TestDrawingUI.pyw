
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

def drawplot():
    #Initialise graph widget
    form.graphWidget.setBackground('w')
    form.graphWidget.setTitle("Laser trigger scheme", color="k")
    labelstyle = {'color':'k', 'font-size':'10px'}
    form.graphWidget.setLabel('left', 'Relative power', **labelstyle)
    form.graphWidget.setLabel('bottom', 'Time (ms)', **labelstyle)
    form.graphWidget.showGrid(x=False, y=False)

    frameduration = 10 #ms
    drawnrframes = 10

    form.graphWidget.setXRange(0, frameduration*drawnrframes, padding=0.01)
    form.graphWidget.setYRange(0,1, padding=0.005)
    #Draw individual laser line
    drawsinglelaserint(4,2,1,2,'c',frameduration,drawnrframes)
    drawsinglelaserint(4,2,1,1,'r',frameduration,drawnrframes)
    #Draw frame lines
    penFrameLine = pg.mkPen(color=(200,200,200), width=1, style=QtCore.Qt.DashLine)
    for i in range(0,drawnrframes+1):
        form.graphWidget.plot([i*frameduration,i*frameduration], [-1, 2], pen=penFrameLine)

def drawsingleline(xdata,ydata,col):
    pen = pg.mkPen(color=col, width=2)
    form.graphWidget.plot(xdata, ydata, pen=pen)

def drawsinglelaserint(delay,duration,intensity,everyxframes,col,frameduration,nrdrawframes):
    #Set colour
    penLaserLine = pg.mkPen(color=col, width=2)
    #Draw every frame individually
    for i in range(0,nrdrawframes):
        #Check if this frame should be included in 'on' state
        if i % everyxframes == 0:
            #Draw the line
            #Flat part
            if delay > 0.001:
                form.graphWidget.plot([i*frameduration,delay+i*frameduration],[0, 0], pen=penLaserLine)
            #Rising edge
            if delay > 0.001:
                form.graphWidget.plot([delay+i*frameduration,delay+i*frameduration],[0, intensity], pen=penLaserLine)
            #Flat part
            form.graphWidget.plot([delay+i*frameduration, delay+duration+i*frameduration],[intensity, intensity], pen=penLaserLine)
            #Falling edge
            if delay+duration > frameduration:
                duration = frameduration-delay
            form.graphWidget.plot([delay+duration+i*frameduration, delay+duration+i*frameduration],[intensity, 0], pen=penLaserLine)
            #Flat part
            if (delay+duration) < (frameduration-0.001):
                form.graphWidget.plot([delay+duration+i*frameduration, (i+1)*frameduration],[0, 0], pen=penLaserLine)
        else:
            #Draw a flat line for this frame
            form.graphWidget.plot([i*frameduration,(i+1)*frameduration],[0, 0], pen=penLaserLine)
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
drawplot()

#Show window and start app
window.show()
app.exec()
