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
import time
from PyQt5.QtCore import QTimer,QDateTime


#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# General switching functions - MM hooks
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def timerloop(frameduration):
    getFrameTimeInfo(frameduration);

def updateColorArming(Boolean):
    #print('Updating Warning'+str(Boolean))
    if Boolean == True:
        form.ARMlaserTriggerPushButton.setStyleSheet("color:red;")
    else:
        form.ARMlaserTriggerPushButton.setStyleSheet("color:black;")


def getFrameTimeInfo(frameduration):
    ft = core.get_exposure();
    form.frameTime_editBox.setText(str(ft));
    frameduration_new = ft;
    try:
        if frameduration_new != frameduration:
            drawplot(frameduration_new)
    except:
        print('No plot drawn')
    return frameduration_new

def SwitchOffLaser(laserID):
    MM_Property_OnOff_Name = MM_JSON["lasers"]["MM_Property_OnOff_Name"]
    MM_Property_Name = MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"]
    core.set_property(MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"], MM_Property_OnOff_Name, 0)
    #Update button labels
    InitLaserButtonLabels(MM_JSON)

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
    for i in [0,1,2,3,4]:
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
    for i in [0,1,2,3,4]:
        ValIntPerc = MMJSON_to_ValIntPerc(MM_JSON,i);
        exec("form.SliderLaser_"+str(i)+".setValue(" + str(int(ValIntPerc)) + ")")
        #Get the intensity as a value from the slider
        exec("form.EditIntensity_Laser_"+str(i)+".setText(\"" +str(int(ValIntPerc))+"\")")

def MMJSON_to_ValIntPerc(MM_JSON,i):
    #Get property name for the intensity
    MMprop_intensity_name = MM_JSON["lasers"]["MM_Property_Intensity_Name"]
    #Get first part of property name in MM
    propertyname = MM_JSON["lasers"]["Laser"+str(i)]["MM_Property_Name"]
    #Get the value 0-5 from MM
    ValIntMM = float(core.get_property(propertyname, MMprop_intensity_name))
    #Translate the value to 0-100 in here
    ValIntPerc = ValIntMM/float(MM_JSON["lasers"]["Laser"+str(i)]["Intensity_slope"])+float(MM_JSON["lasers"]["Laser"+str(i)]["Intensity_offset"])
    return ValIntPerc;

def GetIntensityLaser(MM_JSON,laserID):
    return MMJSON_to_ValIntPerc(MM_JSON,laserID);


def ChangeIntensityLaser(laserID, ValIntPerc):
    #Get relevant names from JSON
    propertyname = MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"]
    MMprop_intensity_name = MM_JSON["lasers"]["MM_Property_Intensity_Name"]

    #Translate the value to 0-5
    ValIntMM = ValIntPerc*float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_slope"])-float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_offset"])
    #Set value in Micromanager
    (core.set_property(propertyname, MMprop_intensity_name, str(ValIntMM)))

    #Change the PAC of the laser if it's triggering and such
    if form.advancedLasers_RadioButton.isChecked():
        drawplot(frameduration);
        armLaser(laserID);
        updateColorArming(0);

#Change intensityslider only when simple laser is checked
def ChangeIntensityLaser_Slider_onlySimple(laserID):
    if form.simpleLasers_RadioButton.isChecked():
        ChangeIntensityLaser_Slider(laserID)

def ChangeIntensityLaser_Slider(laserID):
    #Create ValIntPerc variable and extract
    exec("global ValInt; ValInt = form.SliderLaser_"+str(laserID)+".value()");
    #I don't want 99 percentages...
    ValIntPerc = ValInt
    if ValInt == 99:
        ValIntPerc = ValInt+1
    #Change the intensity
    ChangeIntensityLaser(laserID, ValIntPerc);
    #Update labels
    InitLaserSliders(MM_JSON)


def ChangeIntensityLaserEditField(laserID):
    try:
        #Create ValIntPerc variable and extract
        exec("global ValIntPerc; ValIntPerc = int(form.EditIntensity_Laser_"+str(laserID)+".text())");
        #Change the intensity
        ChangeIntensityLaser(laserID, ValIntPerc);
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

def InitBFRadioCheckbox():
    #Get the current names from the JSON for the filterwheel positions
    for i in range(0,3):
        exec("form.FW_radioButton_"+str(i)+".setText(\"" + MM_JSON["BF_radioLabels"]["Label"+str(i)] + "\")")
    #Get the current BF state from MM
    try:
        curBFstate = core.get_property('TIDiaLamp','Intensity')
    except:
        curBFstate = 0
        print('errored BF')
    print(curBFstate)
    if curBFstate == 0:
        curSelectedState = 0 #off
    elif curBFstate < 7:
        curSelectedState = 1 #on
    else:
        curSelectedState = 2 #high
    #Set the correct checkbox
    exec("form.BF_radioButton_" + str(curSelectedState) + ".setChecked(1)")

def ChangeBFFromRadioCheckBox(FW_id):
    #Give the command to MM
    if FW_id == 0: #off
        core.set_config('BF_Mode', 'BF_Off')
    elif FW_id == 1:
        core.set_config('BF_Mode', 'BF_On')
    elif FW_id == 2:
        core.set_config('BF_Mode', 'BF_High')
    #Refresh everything
    InitBFRadioCheckbox()

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
    core.get_property('TriggerScopeMM-Hub', 'Serial Receive');
    addToVerboseBoxText(core.get_property('TriggerScopeMM-Hub', 'Serial Receive'));
    print(core.get_property('TriggerScopeMM-Hub', 'Serial Receive'));
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Laser trigger drawing functions
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def drawplot(frameduration):
    #print('CallingDrawPlot')
    #We're changing something, so warning user that it's not yet armed
    updateColorArming(1);
    #print(frameduration)
    #Initialise graph widget
    form.graphWidget.clear()
    form.graphWidget.setBackground('k')
    form.graphWidget.setTitle("Laser trigger scheme", color="w")
    form.graphWidget.setLabel('left', '<span style=\"color:white;font-size:10px\">Relative power</span>')
    form.graphWidget.setLabel('bottom', '<span style=\"color:white;font-size:10px\">Time (ms)</span>')
    form.graphWidget.showGrid(x=False, y=False)

    #frameduration = 100 #ms
    drawnrframes = 5
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
            drawduration = 0;#frameduration-delay/1000;
        else:
            drawduration = duration/1000;
        exec("global everyxframes; everyxframes = int(form.BlinkFrames_Edit_Laser_"+str(i)+".text())");
        #Get wavelength to enable correct colours
        wvlngth = MM_JSON["lasers"]["Laser"+str(i)]["Wavelength"]
        #Get intensity from slider
        intensity = GetIntensityLaser(MM_JSON,i);

        drawsinglelaserint(delay/1000,drawduration,intensity/100,i+1,everyxframes,GetRGBFromLambda(wvlngth),frameduration,drawnrframes)


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
                if duration > 0.0001:
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
def ResetLasersTriggerButtonPress(frameduration):
    ResetLasersTrigger();
    initLaserTrigEditBoxes();
    #Draw the laser trigger plot
    #Also see https://www.pythonguis.com/tutorials/plotting-pyqtgraph/
    drawplot(frameduration)

def ResetLasersTrigger():
    for i in [0,1,2,3,4]:
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAC'+str(i+1))
        TS_Response_verbose();
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAD'+str(i+1)+'-0')
        TS_Response_verbose();
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAL'+str(i+1)+'-0')
        TS_Response_verbose();
        #if (i != 2):
        SwitchOnOffLaser(i)
        SwitchOnOffLaser(i)
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', '*')
    TS_Response_verbose();

#Set all boxes to zeros and such
def initLaserTrigEditBoxes():
    for i in range(0,5):
        exec("form.Length_Edit_Laser_"+str(i)+".setText(\"" +str(0)+"\")");
        exec("form.Delay_Edit_Laser_"+str(i)+".setText(\"" +str(1)+"\")");
        exec("form.BlinkFrames_Edit_Laser_"+str(i)+".setText(\"" +str(1)+"\")");

#Arm the laser triggering based on boxes input
def armLaserTriggering():
    print('NEWARM')
    for i in [0,1,2,3,4]:
        armLaser(i);
    #remove arming warning
    updateColorArming(0);

#Arm a single laser
def armLaser(i):
    #Loop over number of frames after which it repeats
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAC'+str(i+1))
    TS_Response_verbose();

    exec("global nrframesrepeat; nrframesrepeat = int(form.BlinkFrames_Edit_Laser_"+str(i)+".text())")
    for k in range(0,nrframesrepeat):
        exec("global delay; delay = int(form.Delay_Edit_Laser_"+str(i)+".text())");
        exec("global length; length = int(form.Length_Edit_Laser_"+str(i)+".text())");
        if k == 0:
            if length>0:
                print('PAO'+str(i+1)+'-0-' + str(round(65535*0.01*GetIntensityLaser(MM_JSON,i))))
                core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(i+1)+'-0-' + str(round(65535*0.01*GetIntensityLaser(MM_JSON,i))))
                TS_Response_verbose();
            else:
                print('PAO'+str(i+1)+'-0' + str(round(0)))
                core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(i+1)+'-0-' + str(round(0)))
                TS_Response_verbose();
        else:
            time.sleep(0.1)
            #print('PAO'+str(i+1)+'-'+str(k)+'-0')
            core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(i+1)+'-'+str(k)+'-0')
            TS_Response_verbose();

        #print('PAS'+str(i+1)+'-1-1');
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAS'+str(i+1)+'-1-1')
        TS_Response_verbose();


            #if k == nrframesrepeat:
            #    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAS'+str(i+1)+'-1-1')
            #    TS_Response_verbose();
            #print(writetgs('PAS2-1-1\r\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)
            #print(writetgs('BAO2-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received

    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAD'+str(i+1)+'-'+str(delay))
    TS_Response_verbose();
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAL'+str(i+1)+'-'+str(length))
    TS_Response_verbose();

    # #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Other functions
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------

#UV blinking function
def blinkUV(duration):
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAC9')
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'SAO9-65535')
    TS_Response_verbose()
    addToVerboseBoxText('UV LED on for '+str(duration)+' microseconds');
    print('UV LED on for '+str(duration)+' microseconds');
    time.sleep(duration/1000)
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'SAO9-0')
    TS_Response_verbose()


#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#End of functions
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def runlaserControllerUI(score,sMM_JSON,sform,sapp):
    #Go from self to global variables
    global core, MM_JSON, form, app
    core = score
    MM_JSON = sMM_JSON
    form = sform
    app = sapp

    #Get onoff and intensity from MM
    InitLaserButtonLabels(MM_JSON)
    InitLaserSliders(MM_JSON)
    InitFilterWheelRadioCheckbox()
    InitBFRadioCheckbox()

    #Get frametimeinfo
    global frameduration;
    frameduration = getFrameTimeInfo(0);

    timer = QTimer(app)
    timer.timeout.connect(lambda: timerloop(frameduration))

    #Update the timer every 500 ms
    timer.start(500)

    #Set FilterWheel Clickable commands
    for i in range(0,6):
        #Change on-off state when button is pressed
        exec("form.FW_radioButton_" + str(i) + ".clicked.connect(lambda: ChangeFilterWheelFromRadioCheckBox(" + str(i) + "));")

    #Set Brightfield Clickable commands
    for i in range(0,3):
        #Change on-off state when button is pressed
        exec("form.BF_radioButton_" + str(i) + ".clicked.connect(lambda: ChangeBFFromRadioCheckBox(" + str(i) + "));")

    #Laser control integration
    #For all lasers
    for i in [0,1,2,3,4]:
        #Change on-off state when button is pressed
        exec("form.PushLaser_" + str(i) + ".clicked.connect(lambda: SwitchOnOffLaser(" + str(i) + "));")
        #Change intensity when slider is changed
        exec("form.SliderLaser_" + str(i) + ".sliderReleased.connect(lambda: ChangeIntensityLaser_Slider(" + str(i) + "));")
        exec("form.SliderLaser_" + str(i) + ".valueChanged.connect(lambda: ChangeIntensityLaser_Slider_onlySimple(" + str(i) + "));")
        #Change intensity when intensity edit field is changed
        exec("form.EditIntensity_Laser_" + str(i) + ".textChanged.connect(lambda: ChangeIntensityLaserEditField(" + str(i) + "));")

    #Initialise the laser triggering boxes
    initLaserTrigEditBoxes();
    #Draw the laser trigger plot
    #Also see https://www.pythonguis.com/tutorials/plotting-pyqtgraph/
    drawplot(frameduration)

    #Change laser trigger scheme when values in boxes are changed
    for i in range(0,5):
        exec("form.Delay_Edit_Laser_" + str(i) + ".textChanged.connect(lambda: drawplot(frameduration));")
        exec("form.Length_Edit_Laser_" + str(i) + ".textChanged.connect(lambda: drawplot(frameduration));")
        exec("form.BlinkFrames_Edit_Laser_" + str(i) + ".textChanged.connect(lambda: drawplot(frameduration));")

    #Arm lasers button
    form.ARMlaserTriggerPushButton.clicked.connect(lambda: armLaserTriggering());

    #Button that resets laser triggering
    form.resetLasersTriggerButton.clicked.connect(lambda: ResetLasersTrigger());

    #Button that resets laser triggering
    form.resetLasersTriggerButton.clicked.connect(lambda: ResetLasersTriggerButtonPress(frameduration));

    #UV LED Button run
    form.PushUVLED.clicked.connect(lambda: blinkUV(float(form.UVLED_duration_EditField.text())));

    #--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #UI-based things
    #--------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    #Activate/deactivate either the advanced lasers or simple laser scheme based on radio Button
    def SimpleLasers():
        form.LaserTriggerSchemeBox.setEnabled(0);
        for i in range(0,5):
            exec("form.PushLaser_" + str(i) + ".setEnabled(1);");
        ResetLasersTrigger();

    def AdvancedLasers():
        form.LaserTriggerSchemeBox.setEnabled(1);
        for i in range(0,5):
            exec("form.PushLaser_" + str(i) + ".setEnabled(0);");
            SwitchOffLaser(i);
        armLaserTriggering();

    form.simpleLasers_RadioButton.clicked.connect(lambda: SimpleLasers());
    form.advancedLasers_RadioButton.clicked.connect(lambda: AdvancedLasers());

    #Don't display warning
    updateColorArming(0)

    #Reset laser triggers when startup for properly expected behaviour
    ResetLasersTrigger();
    #Initialise laser trigger edit buttons
    initLaserTrigEditBoxes();
