from PyQt5 import uic
from PyQt5.QtWidgets import QApplication
import PyQt5.QtWidgets
import json
from pycromanager import *
#from pycromanager import Core
import numpy as np
import sys
import os
import time
import asyncio
import pyqtgraph as pg

#For drawing
import matplotlib
matplotlib.use('Qt5Agg')
from PyQt5 import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# General switching functions - MM hooks
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------


def SwitchOnOffLaser(laserID):
    MM_Property_OnOff_Name = MM_JSON["lasers"]["MM_Property_OnOff_Name"]
    MM_Property_Name = MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"]
    #Find current onoff State
    CurrOnOffState = core.get_property(MM_Property_Name, MM_Property_OnOff_Name)
    #Switch the on off state
    if CurrOnOffState == MM_JSON["lasers"]["MM_Property_OnOff_OnValue"]:
        core.set_property(MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"], MM_Property_OnOff_Name, MM_JSON["lasers"]["MM_Property_OnOff_OffValue"])
    else:
        core.set_property(MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"], MM_Property_OnOff_Name, MM_JSON["lasers"]["MM_Property_OnOff_OnValue"])
    #Update button labels
    InitLaserButtonLabels(MM_JSON)

def InitLaserButtonLabels(MM_JSON):
    #Get last part of property name in MM
    MMprop_onoff = MM_JSON["lasers"]["MM_Property_OnOff_Name"]
    for i in [0,1,3,4]:
        #Get first part of property name in MM
        propertyname = MM_JSON["lasers"]["Laser"+str(i)]["MM_Property_Name"]
        #Set the label of the button depending on onoff state
        if core.get_property(propertyname, MMprop_onoff) == MM_JSON["lasers"]["MM_Property_OnOff_OnValue"]:
            exec("form.PushLaser_"+str(i)+".setText(\"Now On\")")
        else:
            exec("form.PushLaser_"+str(i)+".setText(\"Now Off\")")
        #Set the label of the laser at get_property
        exec("form.NameLaser_"+str(i)+".setText(\""+str(MM_JSON["lasers"]["Laser"+str(i)]["Wavelength"])+" nm\")")
        exec("form.NameLaser_"+str(i)+"_2.setText(\""+str(MM_JSON["lasers"]["Laser"+str(i)]["Wavelength"])+" nm\")")

        #Set colours
        wvlngth = MM_JSON["lasers"]["Laser"+str(i)]["Wavelength"]
        rgbval = GetRGBFromLambda(wvlngth);
        exec("form.PushLaser_"+str(i)+".setStyleSheet(\"color:white; background-color: rgb(\"+str(rgbval[0])+\",\"+str(rgbval[1])+\",\"+str(rgbval[2])+\")\")")

def InitLaserSliders(MM_JSON):
    #Get property name for the intensity
    MMprop_intensity_name = MM_JSON["lasers"]["MM_Property_Intensity_Name"]
    for i in [0,1,3,4]:
        #Get first part of property name in MM
        propertyname = MM_JSON["lasers"]["Laser"+str(i)]["MM_Property_Name"]
        #Get the value 0-5 from MM
        ValIntMM = float(core.get_property(propertyname, MMprop_intensity_name))
        #Translate the value to 0-100 in here
        ValIntPerc = ValIntMM/float(MM_JSON["lasers"]["Laser"+str(i)]["Intensity_slope"])+float(MM_JSON["lasers"]["Laser"+str(i)]["Intensity_offset"])
        exec("form.SliderLaser_"+str(i)+".setValue(" + str(int(ValIntPerc)) + ")")
        #Get the intensity as a value from the slider
        exec("form.EditIntensity_Laser_"+str(i)+".setText(\"" +str(int(ValIntPerc))+"\")")

def ChangeIntensityLaser(laserID):
    #Get relevant names from JSON
    propertyname = MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"]
    MMprop_intensity_name = MM_JSON["lasers"]["MM_Property_Intensity_Name"]
    #Create ValIntPerc variable and extract
    exec("global ValInt; ValInt = form.SliderLaser_"+str(laserID)+".value()");
    #I don't want 99 percentages...
    ValIntPerc = ValInt
    if ValInt == 99:
        ValIntPerc = ValInt+1
    #Translate the value to 0-5
    ValIntMM = ValIntPerc*float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_slope"])-float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_offset"])
    #Set value in Micromanager
    (core.set_property(propertyname, MMprop_intensity_name, str(ValIntMM)))
    #Update labels
    InitLaserSliders(MM_JSON)

def ChangeIntensityLaserEditField(laserID):
    try:
        #Get relevant names from JSON
        propertyname = MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"]
        MMprop_intensity_name = MM_JSON["lasers"]["MM_Property_Intensity_Name"]
        #Create ValIntPerc variable and extract
        exec("global ValIntPerc; ValIntPerc = int(form.EditIntensity_Laser_"+str(laserID)+".text())");
        #Translate the value to 0-5
        ValIntMM = ValIntPerc*float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_slope"])-float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_offset"])
        #Set value in Micromanager
        (core.set_property(propertyname, MMprop_intensity_name, str(ValIntMM)))
        #Update labels
        InitLaserSliders(MM_JSON)
    except:
        #Do nothing
        pass

def InitFilterWheelRadioCheckbox():
    #Get the current names from the JSON for the filterwheel positions
    for i in range(0,6):
        exec("form.FW_radioButton_"+str(i)+".setText(\"" + MM_JSON["filter_wheel"]["Label"+str(i)] + "\")")
        #Reset colours - not needed for now, but still keeping
        #exec("form.FW_radioButton_"+str(i)+".setStyleSheet(\"color:black;\")")
    #Get the current filterwheel from MM
    curSelectedState = core.get_property(MM_JSON["filter_wheel"]["MM_Property_Name"], MM_JSON["filter_wheel"]["MM_Property_State_Name"])
    #Set the correct checkbox
    exec("form.FW_radioButton_" + str(curSelectedState) + ".setChecked(1)")

def ChangeFilterWheelFromRadioCheckBox(FW_id):
    #Give the command to MM
    core.set_property(MM_JSON["filter_wheel"]["MM_Property_Name"], MM_JSON["filter_wheel"]["MM_Property_State_Name"],FW_id)
    #Refresh everything
    InitFilterWheelRadioCheckbox()

def GetRGBFromLambda(w):
    r=0.0; g=0.0; b=0.0;
    if w >= 380 and w < 440:
        R = -(w - 440.) / (440. - 380.);    G = 0.0;    B = 1.0;
    elif w >= 440 and w < 490:
        R = 0.0;    G = (w - 440.) / (490. - 440.);    B = 1.0;
    elif w >= 490 and w < 510:
        R = 0.0;    G = 1.0;    B = -(w - 510.) / (510. - 490.);
    elif w >= 510 and w < 580:
        R = (w - 510.) / (580. - 510.); G = 1.0;    B = 0.0;
    elif w >= 580 and w < 660:
        R = 1.0;    G = -(w - 660.) / (660. - 580.);    B = 0.0;
    elif w >= 660 and w <= 780:
        R = 1.0;    G = 0.0;    B = 0.0;
    else:
        R = 0.0;    G = 0.0;    B = 0.0;
    multoffset = 0.7;
    return [R*255*multoffset,G*255*multoffset,B*255*multoffset]

#Function that adds text to the verbose text output box
def addToVerboseBoxText(text):
    form.VerboseBox.setPlainText(text+'\r\n'+form.VerboseBox.toPlainText());

#Specifically get TriggerScope response to verboxe text box
def TS_Response_verbose():
    addToVerboseBoxText(core.get_property('TriggerScopeMM-Hub', 'Serial Receive'));
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Laser trigger drawing functions
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def drawplot():
    #Initialise graph widget
    form.graphWidget.clear()
    form.graphWidget.setBackground('k')
    form.graphWidget.setTitle("Laser trigger scheme", color="w")
    form.graphWidget.setLabel('left', '<span style=\"color:white;font-size:10px\">Relative power</span>')
    form.graphWidget.setLabel('bottom', '<span style=\"color:white;font-size:10px\">Time (ms)</span>')
    form.graphWidget.showGrid(x=False, y=False)

    frameduration = 100 #ms
    drawnrframes = 10
    nrlasersdrawn = 5;

    form.graphWidget.setXRange(0, frameduration*drawnrframes, padding=0.01)
    form.graphWidget.setYRange(0,1*nrlasersdrawn, padding=0.005)

    #Draw frame lines
    penFrameLine = pg.mkPen(color=(200,200,200), width=1, style=QtCore.Qt.DashLine)
    for i in range(0,drawnrframes+1):
        form.graphWidget.plot([i*frameduration,i*frameduration], [-1, nrlasersdrawn+1], pen=penFrameLine)

    #Draw individual laser lines
    for i in range(0,5):
        #Get the info from the boxes above
        exec("global delay; delay = int(form.Delay_Edit_Laser_"+str(i)+".text())");
        exec("global duration; duration = int(form.Length_Edit_Laser_"+str(i)+".text())");
        if duration == 0:
            drawduration = frameduration-delay/1000;
        else:
            drawduration = duration/1000;
        exec("global everyxframes; everyxframes = int(form.BlinkFrames_Edit_Laser_"+str(i)+".text())");
        #Get wavelength to enable correct colours
        wvlngth = MM_JSON["lasers"]["Laser"+str(i)]["Wavelength"]

        drawsinglelaserint(delay/1000,drawduration,1,i+1,everyxframes,GetRGBFromLambda(wvlngth),frameduration,drawnrframes)


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
            if delay > 0.0001:
                form.graphWidget.plot([i*frameduration,delay+i*frameduration],[LowPoint, LowPoint], pen=penLaserLine)
            #Rising edge
            if delay > 0.0001:
                form.graphWidget.plot([delay+i*frameduration,delay+i*frameduration],[LowPoint, HighPoint], pen=penLaserLine)
            #Flat part
            if duration > 0.0001:
                form.graphWidget.plot([delay+i*frameduration, delay+duration+i*frameduration],[HighPoint, HighPoint], pen=penLaserLine)
            #Falling edge
            if delay+duration > frameduration:
                duration = frameduration-delay
            if duration > 0.0001 and duration < frameduration:
                form.graphWidget.plot([delay+duration+i*frameduration, delay+duration+i*frameduration],[HighPoint, LowPoint], pen=penLaserLine)
            #Flat part
            if (delay+duration) < (frameduration-0.0001):
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


#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Functions that instruct strobo + blanking of lasers
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def ResetLasersTrigger():
    #Testing for now
    for i in range(0,5):
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAC'+str(i+1))
        TS_Response_verbose();
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAD'+str(i+1)+'-0')
        TS_Response_verbose();
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAL'+str(i+1)+'-0')
        TS_Response_verbose();
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', '*')
    initLaserTrigEditBoxes()
    TS_Response_verbose();

#Set all boxes to zeros and such
def initLaserTrigEditBoxes():
    for i in range(0,5):
        exec("form.Length_Edit_Laser_"+str(i)+".setText(\"" +str(0)+"\")");
        exec("form.Delay_Edit_Laser_"+str(i)+".setText(\"" +str(0)+"\")");
        exec("form.BlinkFrames_Edit_Laser_"+str(i)+".setText(\"" +str(1)+"\")");

#Arm the laser triggering based on boxes input
def armLaserTriggering():
    for i in [1,3]:
        exec("global delay; delay = int(form.Delay_Edit_Laser_"+str(i)+".text())");
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAD'+str(i+1)+'-'+str(delay))
        TS_Response_verbose();
        exec("global length; length = int(form.Length_Edit_Laser_"+str(i)+".text())");
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAL'+str(i+1)+'-'+str(length))
        TS_Response_verbose();
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#End of functions
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# get object representing MMCore, used throughout
core = Core()

#Open JSON file with MM settings
with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
  MM_JSON = json.load(f)

#Load UI settings
Form, Window = uic.loadUiType(os.path.join(sys.path[0], 'UILaserController.ui'))

#Setup UI
app = QApplication([])
window = Window()
form = Form()
form.setupUi(window)

#Get onoff and intensity from MM
InitLaserButtonLabels(MM_JSON)
InitLaserSliders(MM_JSON)
InitFilterWheelRadioCheckbox()
#Laser control integration
#For all non-AOTF lasers
for i in [0,1,3,4]:
    #Change on-off state when button is pressed
    exec("form.PushLaser_" + str(i) + ".clicked.connect(lambda: SwitchOnOffLaser(" + str(i) + "));")
    #Change intensity when slider is changed
    exec("form.SliderLaser_" + str(i) + ".valueChanged.connect(lambda: ChangeIntensityLaser(" + str(i) + "));")
    #Change intensity when intensity edit field is changed
    exec("form.EditIntensity_Laser_" + str(i) + ".textChanged.connect(lambda: ChangeIntensityLaserEditField(" + str(i) + "));")

#Set FilterWheel Clickable commands
for i in range(0,6):
    #Change on-off state when button is pressed
    exec("form.FW_radioButton_" + str(i) + ".clicked.connect(lambda: ChangeFilterWheelFromRadioCheckBox(" + str(i) + "));")

#Initialise the laser triggering boxes
initLaserTrigEditBoxes();
#Draw the laser trigger plot
#Also see https://www.pythonguis.com/tutorials/plotting-pyqtgraph/
drawplot()

#Change laser trigger scheme when values in boxes are changed
for i in range(0,5):
    exec("form.Delay_Edit_Laser_" + str(i) + ".textChanged.connect(lambda: drawplot());")
    exec("form.Length_Edit_Laser_" + str(i) + ".textChanged.connect(lambda: drawplot());")
    exec("form.BlinkFrames_Edit_Laser_" + str(i) + ".textChanged.connect(lambda: drawplot());")

#Arm lasers button
form.ARMlaserTriggerPushButton.clicked.connect(lambda: armLaserTriggering());

#Button that resets laser triggering
form.resetLasersTriggerButton.clicked.connect(lambda: ResetLasersTrigger());

#Show window and start app
window.show()


#Reset laser triggers when startup for properly expected behaviour
ResetLasersTrigger();
app.exec()
