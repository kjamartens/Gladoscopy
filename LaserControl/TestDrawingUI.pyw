
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
    form.graphWidget.setBackground('k')
    form.graphWidget.setTitle("Laser trigger scheme", color="w")
    form.graphWidget.setLabel('left', '<span style=\"color:white;font-size:10px\">Relative power</span>')
    form.graphWidget.setLabel('bottom', '<span style=\"color:white;font-size:10px\">Time (ms)</span>')
    form.graphWidget.showGrid(x=False, y=False)

    frameduration = 10 #ms
    drawnrframes = 10
    nrlasersdrawn = 5;

    form.graphWidget.setXRange(0, frameduration*drawnrframes, padding=0.01)
    form.graphWidget.setYRange(0,1*nrlasersdrawn, padding=0.005)

    #Draw frame lines
    penFrameLine = pg.mkPen(color=(200,200,200), width=1, style=QtCore.Qt.DashLine)
    for i in range(0,drawnrframes+1):
        form.graphWidget.plot([i*frameduration,i*frameduration], [-1, nrlasersdrawn+1], pen=penFrameLine)

    #Draw individual laser lines
    drawsinglelaserint(4,2,1,1,1,'c',frameduration,drawnrframes)
    drawsinglelaserint(4,2,1,2,2,[255,255,0],frameduration,drawnrframes)
    drawsinglelaserint(0,frameduration,1,3,3,'r',frameduration,drawnrframes)
    drawsinglelaserint(5,5,1,4,2,[90,255,48],frameduration,drawnrframes)
    drawsinglelaserint(0,frameduration,1,5,1,[0,84,120],frameduration,drawnrframes)

def drawsingleline(xdata,ydata,col):
    pen = pg.mkPen(color=col, width=2)
    form.graphWidget.plot(xdata, ydata, pen=pen)

def drawsinglelaserint(delay,duration,intensity,laserID,everyxframes,col,frameduration,nrdrawframes):
    intensity *= 0.9; #Lower slightly
    LowPoint = (laserID-1)*1;
    HighPoint = LowPoint+intensity;
    #Set colour
    penLaserLine = pg.mkPen(color=col, width=2)
    #Draw every frame individually
    for i in range(0,nrdrawframes):
        #Check if this frame should be included in 'on' state
        if i % everyxframes == 0:
            #Draw the line
            #Flat part
            if delay > 0.1:
                form.graphWidget.plot([i*frameduration,delay+i*frameduration],[LowPoint, LowPoint], pen=penLaserLine)
            #Rising edge
            if delay > 0.1:
                form.graphWidget.plot([delay+i*frameduration,delay+i*frameduration],[LowPoint, HighPoint], pen=penLaserLine)
            #Flat part
            if duration > 0.1:
                form.graphWidget.plot([delay+i*frameduration, delay+duration+i*frameduration],[HighPoint, HighPoint], pen=penLaserLine)
            #Falling edge
            if delay+duration > frameduration:
                duration = frameduration-delay
            if duration > 0.1 and duration < frameduration:
                form.graphWidget.plot([delay+duration+i*frameduration, delay+duration+i*frameduration],[HighPoint, LowPoint], pen=penLaserLine)
            #Flat part
            if (delay+duration) < (frameduration-0.1):
                form.graphWidget.plot([delay+duration+i*frameduration, (i+1)*frameduration],[LowPoint, LowPoint], pen=penLaserLine)

        else:
            #Draw a flat line for this frame
            form.graphWidget.plot([i*frameduration,(i+1)*frameduration],[LowPoint, LowPoint], pen=penLaserLine)

            #Extra lines if trigger is switching on frame start or frame end
            #if the laser didn't trigger on the previous frame
            if (i-1) % everyxframes == 0:
                if delay == 0:
                    form.graphWidget.plot([i*frameduration, i*frameduration],[LowPoint, HighPoint], pen=penLaserLine)
            if (i+1) % everyxframes == 0:
                if duration == frameduration:
                    form.graphWidget.plot([(i+1)*frameduration, (i+1)*frameduration],[LowPoint, HighPoint], pen=penLaserLine)
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
