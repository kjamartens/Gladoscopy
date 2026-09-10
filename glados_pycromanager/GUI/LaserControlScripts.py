# Custom UI for Endefelder lab - deprecated, last used in 2022 or so

import asyncio
import json
import os
import sys
import time

#For drawing
import matplotlib

#from pycromanager import Core
import numpy as np
import pyqtgraph as pg
from pycromanager import *

matplotlib.use('Qt5Agg')
import logging
import time

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QDateTime, QTimer


#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# General switching functions - MM hooks
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#: T-B4: every hardware touch in this file goes through the MicroscopeService
#: owner thread when one is running, so a button click returns immediately
#: instead of driving a TriggerScope serial conversation on the GUI thread.
#: With no service (tests, the napari-plugin path, a shutdown in progress) the
#: call runs inline exactly as it used to -- T-B1's lock still makes that safe.


def _hardware_service():
    """The running `MicroscopeService`, or None."""
    sd = globals().get('shared_data', None)
    service = getattr(sd, 'microscope_service', None)
    if service is not None and getattr(service, 'running', False):
        return service
    return None


def submitHardware(fn, *args, label=None, **kwargs):
    """Queue `fn` on the hardware owner thread; run it inline if there is none.

    Fire-and-forget on purpose: these are user intents, and the service queue
    is FIFO within a priority, so the order the user pressed things in is the
    order the TriggerScope sees them.
    """
    service = _hardware_service()
    if service is None:
        return fn(*args, **kwargs)
    service.submit(fn, *args, label=label or getattr(fn, '__name__', 'laser'),
                   **kwargs)
    return None


def _onGuiThread(fn):
    """Run `fn()` on the GUI thread (inline when already there).

    Invariant 3's mechanism, reused: a hardware job runs on the owner thread and
    must not touch a widget from there. `NapariBridge.submit` calls back with
    the viewer as its first argument, which none of these need.
    """
    sd = globals().get('shared_data', None)
    try:
        from glados_pycromanager.GUI.napari_bridge import get_bridge
        bridge = get_bridge(sd)
    except Exception:
        bridge = None
    if bridge is None:
        fn()
        return
    bridge.submit(lambda _viewer: fn())


def timerloop(frameduration):
    getFrameTimeInfo(frameduration);

def updateColorArming(Boolean):
    #logging.debug('Updating Warning'+str(Boolean))
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
    except (AttributeError, RuntimeError, ValueError, TypeError) as exc:
        logging.warning('No plot drawn: %s', exc)
    return frameduration_new

def SwitchOffLaser(laserID):
    submitHardware(_switchOffLaser_hw, laserID, label='lasers.SwitchOffLaser')


def _switchOffLaser_hw(laserID):
    MM_Property_OnOff_Name = MM_JSON["lasers"]["MM_Property_OnOff_Name"]
    MM_Property_Name = MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"]
    core.set_property(MM_Property_Name, MM_Property_OnOff_Name, 0)
    #Update button labels
    _refreshLaserButtonLabels()


def SwitchOnOffLaser(laserID):
    submitHardware(_switchOnOffLaser_hw, laserID, label='lasers.SwitchOnOffLaser')


def _switchOnOffLaser_hw(laserID, refresh=True):
    """Toggle one laser. Runs on the hardware owner thread (T-B4)."""
    MM_Property_OnOff_Name = MM_JSON["lasers"]["MM_Property_OnOff_Name"]
    MM_Property_Name = MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"]
    #Find current onoff State
    CurrOnOffState = core.get_property(MM_Property_Name, MM_Property_OnOff_Name)
    #Switch the on off state
    if CurrOnOffState == MM_JSON["lasers"]["MM_Property_OnOff_OnValue"]:
        core.set_property(MM_Property_Name, MM_Property_OnOff_Name,
                          MM_JSON["lasers"]["MM_Property_OnOff_OffValue"])
    else:
        core.set_property(MM_Property_Name, MM_Property_OnOff_Name,
                          MM_JSON["lasers"]["MM_Property_OnOff_OnValue"])
    #Update button labels
    if refresh:
        _refreshLaserButtonLabels()

def _refreshLaserButtonLabels():
    """Read the five on/off states here, apply the labels on the GUI thread.

    T-B4: the split matters because this is called from inside hardware jobs.
    The read is five `get_property` calls; doing them on the GUI thread (which
    is what `InitLaserButtonLabels` does, and still does when the GUI calls it
    directly) is five serial round trips in front of the next repaint.
    """
    MMprop_onoff = MM_JSON["lasers"]["MM_Property_OnOff_Name"]
    on_value = MM_JSON["lasers"]["MM_Property_OnOff_OnValue"]
    states = []
    for i in [0, 1, 2, 3, 4]:
        propertyname = MM_JSON["lasers"]["Laser"+str(i)]["MM_Property_Name"]
        states.append(core.get_property(propertyname, MMprop_onoff) == on_value)
    _onGuiThread(lambda: _applyLaserButtonLabels(states))


def _applyLaserButtonLabels(states):
    """GUI-thread half of `_refreshLaserButtonLabels`."""
    for i, is_on in enumerate(states):
        getattr(form, "PushLaser_"+str(i)).setText("Now On" if is_on else "Now Off")
        wavelength = MM_JSON["lasers"]["Laser"+str(i)]["Wavelength"]
        getattr(form, "NameLaser_"+str(i)).setText(str(wavelength)+" nm")
        getattr(form, "NameLaser_"+str(i)+"_2").setText(str(wavelength)+" nm")
        rgbval = GetRGBFromLambda(wavelength)
        getattr(form, "PushLaser_"+str(i)).setStyleSheet(
            "color:white; background-color: rgb({},{},{})".format(*rgbval[:3]))


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
        ValIntPerc = min(100,MMJSON_to_ValIntPerc(MM_JSON,i));
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


#: Last intensity actually sent per laser, recorded here because this is the one
#: choke point every path goes through (slider and edit field alike). Used by
#: ChangeIntensityLaserEditField to skip a focus-out that changed nothing (T-F8).
_lastWrittenLaserIntensity = {}


def ChangeIntensityLaser(laserID, ValIntPerc):
    #Get relevant names from JSON
    propertyname = MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"]
    MMprop_intensity_name = MM_JSON["lasers"]["MM_Property_Intensity_Name"]

    #Translate the value to 0-5
    ValIntMM = ValIntPerc*float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_slope"])-float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_offset"])
    #Set value in Micromanager -- queued on the owner thread (T-B4). Recorded as
    #written straight away: the queue is FIFO, so this *is* the value the laser
    #will hold once the queue drains, and the T-F8 duplicate-write skip below
    #must not be defeated by the write being asynchronous.
    submitHardware(core.set_property, propertyname, MMprop_intensity_name,
                   str(ValIntMM), label='lasers.ChangeIntensity')
    _lastWrittenLaserIntensity[laserID] = ValIntPerc

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
    ValIntPerc = ValInt #type:ignore
    if ValInt == 99: #type:ignore
        ValIntPerc = ValInt+1 #type:ignore
    #Change the intensity
    ChangeIntensityLaser(laserID, ValIntPerc);
    #Update labels
    InitLaserSliders(MM_JSON)


def ChangeIntensityLaserEditField(laserID):
    """Apply a typed laser intensity.

    T-F8: wired to `editingFinished`, not `textChanged`. On `textChanged` this
    issued a **serial write per keystroke**, so typing "150" briefly drove the
    laser to 1 and then 15 on the way to 150 -- the bare `except: pass` below
    was there precisely to swallow the half-typed values. `editingFinished`
    fires once, on Enter or focus-out, and (unlike `textChanged`) is not emitted
    by a programmatic `setText`, so the slider updating this field no longer
    loops back into a write.
    """
    try:
        #Create ValIntPerc variable and extract
        exec("global ValIntPerc; ValIntPerc = int(form.EditIntensity_Laser_"+str(laserID)+".text())");
        newIntensity = ValIntPerc #type:ignore # noqa: F821 -- defined by the exec above
        #A focus-out that changed nothing must not repeat the serial write.
        if _lastWrittenLaserIntensity.get(laserID) == newIntensity:
            return
        #Change the intensity (which records it in _lastWrittenLaserIntensity)
        ChangeIntensityLaser(laserID, newIntensity); #type:ignore
        #Update labels
        InitLaserSliders(MM_JSON)
    except (RuntimeError, OSError, AttributeError, ValueError):
        #Do nothing - an empty or non-numeric field is not a value to send
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
        exec("form.BF_radioButton_"+str(i)+".setText(\"" + MM_JSON["BF_radioLabels"]["Label"+str(i)] + "\")")
    #Get the current BF state from MM
    try:
        curBFstate = float(core.get_property('TIDiaLamp','Intensity')) #Get the intensity of the BF lamp
    except (RuntimeError, OSError, AttributeError, ValueError, TypeError):
        curBFstate = 0
    
    #Set a certain BF state
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
    """Prepend a line to the verbose box, from any thread (T-B4)."""
    _onGuiThread(
        lambda: form.VerboseBox.setPlainText(text + '\r\n' + form.VerboseBox.toPlainText()))

#Specifically get TriggerScope response to verboxe text box
def TS_Response_verbose():
    """Read one TriggerScope response and show it.

    Called after *every* serial write, so it is the per-command cost of every
    loop in this file. It used to make three identical `get_property` reads --
    one discarded, one displayed, one logged -- i.e. three serial round trips
    to show one answer. One read now serves all three uses.
    """
    response = core.get_property('TriggerScopeMM-Hub', 'Serial Receive')
    addToVerboseBoxText(response)
    logging.debug(response)
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Laser trigger drawing functions
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#: Idle window before a laser-trigger edit redraws the plot (T-F8).
DRAWPLOT_DEBOUNCE_MS = 200

_drawplotTimer = None


def scheduleDrawplot(frameduration):
    """Coalesce laser-trigger edits into one plot rebuild (T-F8).

    `drawplot` clears the graph widget and rebuilds roughly a hundred pyqtgraph
    items. It was wired to `textChanged` on fifteen line edits, so every
    keystroke in any of them paid for a full rebuild on the GUI thread.

    The trigger stays `textChanged` rather than moving to `editingFinished`:
    the plot is a live preview of what the user is typing, and leaving it stale
    until focus-out would change what the control does. Debouncing changes only
    when it fires.
    """
    global _drawplotTimer
    if _drawplotTimer is None:
        _drawplotTimer = QTimer()
        _drawplotTimer.setSingleShot(True)
    try:
        _drawplotTimer.timeout.disconnect()
    except TypeError:  # nothing connected yet
        pass
    _drawplotTimer.timeout.connect(lambda: drawplot(frameduration))
    _drawplotTimer.start(DRAWPLOT_DEBOUNCE_MS)


def drawplot(frameduration):
    #logging.debug('CallingDrawPlot')
    #We're changing something, so warning user that it's not yet armed
    updateColorArming(1);
    #logging.debug(frameduration)
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
    penFrameLine = pg.mkPen(color=(200,200,200), width=1, style=QtCore.Qt.DashLine) #type:ignore
    for i in range(0,drawnrframes+1):
        form.graphWidget.plot([i*frameduration,i*frameduration], [-1, nrlasersdrawn+1], pen=penFrameLine)

    #Draw individual laser lines
    for i in range(0,5):
        #Get the info from the boxes above
        exec("global delay; delay = int(form.Delay_Edit_Laser_"+str(i)+".text())");
        exec("global duration; duration = int(form.Length_Edit_Laser_"+str(i)+".text())");
        if duration == 0: #type:ignore
            drawduration = 0;#frameduration-delay/1000;
        else:
            drawduration = duration/1000; #type:ignore
        exec("global everyxframes; everyxframes = int(form.BlinkFrames_Edit_Laser_"+str(i)+".text())");
        #Get wavelength to enable correct colours
        wvlngth = MM_JSON["lasers"]["Laser"+str(i)]["Wavelength"]
        #Get intensity from slider
        intensity = GetIntensityLaser(MM_JSON,i);

        drawsinglelaserint(delay/1000,drawduration,intensity/100,i+1,everyxframes,GetRGBFromLambda(wvlngth),frameduration,drawnrframes) #type:ignore


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
    """Queue the whole reset onto the hardware owner thread (T-B4).

    This is ~100 serial round trips in one button press. On the GUI thread that
    froze the UI (and starved the frame path) for its whole duration; the click
    now returns immediately and the TriggerScope conversation happens on the
    owner thread.
    """
    submitHardware(_resetLasersTrigger_hw, label='lasers.ResetLasersTrigger')


def _resetLasersTrigger_hw():
    for i in [0,1,2,3,4]:
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAC'+str(i+1))
        TS_Response_verbose();
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAD'+str(i+1)+'-0')
        TS_Response_verbose();
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAL'+str(i+1)+'-0')
        TS_Response_verbose();
        #if (i != 2):
        # Already on the owner thread, so toggle directly rather than queueing
        # two more jobs -- and refresh the button labels once at the end rather
        # than ten times mid-loop.
        _switchOnOffLaser_hw(i, refresh=False)
        _switchOnOffLaser_hw(i, refresh=False)
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', '*')
    TS_Response_verbose();
    _refreshLaserButtonLabels()

#Set all boxes to zeros and such
def initLaserTrigEditBoxes():
    for i in range(0,5):
        exec("form.Length_Edit_Laser_"+str(i)+".setText(\"" +str(0)+"\")");
        exec("form.Delay_Edit_Laser_"+str(i)+".setText(\"" +str(1)+"\")");
        exec("form.BlinkFrames_Edit_Laser_"+str(i)+".setText(\"" +str(1)+"\")");

#Arm the laser triggering based on boxes input
def armLaserTriggering():
    logging.debug('NEWARM')
    for i in [0,1,2,3,4]:
        armLaser(i);
    #remove arming warning
    updateColorArming(0);

#Arm a single laser
def armLaser(i):
    """Arm one laser.

    T-B4: the widget reads (and `GetIntensityLaser`, which reads the laser's
    intensity property) happen on the calling thread, then the serial
    conversation -- including its `time.sleep(0.1)` per repeat frame -- is
    queued onto the hardware owner thread. `armLaserTriggering` arms all five,
    so on the GUI thread that was five conversations plus up to 0.1 s of sleep
    per repeat frame, per laser.
    """
    nrframesrepeat = int(getattr(form, "BlinkFrames_Edit_Laser_"+str(i)).text())
    delay = int(getattr(form, "Delay_Edit_Laser_"+str(i)).text())
    length = int(getattr(form, "Length_Edit_Laser_"+str(i)).text())
    submitHardware(_armLaser_hw, i, nrframesrepeat, delay, length,
                   label='lasers.armLaser')


def _armLaser_hw(i, nrframesrepeat, delay, length):
    #Loop over number of frames after which it repeats
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAC'+str(i+1))
    TS_Response_verbose();

    for k in range(0,nrframesrepeat): #type:ignore
        if k == 0:
            if length>0: #type:ignore
                power_level = 65535*0.01*GetIntensityLaser(MM_JSON,i)
                if i == 2: #Exception for the 561 laser:
                    logging.debug('Power level exception for 561 laser succes')
                    power_level = 65535*0.01*GetIntensityLaser(MM_JSON,i)*(8/100)
                logging.debug('PAO'+str(i+1)+'-0-' + str(round(power_level)))
                core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(i+1)+'-0-' + str(round(power_level)))
                TS_Response_verbose();
            else:
                logging.debug('PAO'+str(i+1)+'-0' + str(round(0)))
                core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(i+1)+'-0-' + str(round(0)))
                TS_Response_verbose();
        else:
            time.sleep(0.1)
            #logging.debug('PAO'+str(i+1)+'-'+str(k)+'-0')
            core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(i+1)+'-'+str(k)+'-0')
            TS_Response_verbose();

        #logging.debug('PAS'+str(i+1)+'-1-1');
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAS'+str(i+1)+'-1-1')
        TS_Response_verbose();


            #if k == nrframesrepeat:
            #    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAS'+str(i+1)+'-1-1')
            #    TS_Response_verbose();
            #logging.debug(writetgs('PAS2-1-1\r\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)
            #logging.debug(writetgs('BAO2-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received

    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAD'+str(i+1)+'-'+str(delay)) #type:ignore
    TS_Response_verbose();
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAL'+str(i+1)+'-'+str(length)) #type:ignore
    TS_Response_verbose();

    # #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Other functions
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------

#UV blinking function
def blinkUV(duration):
    """Blink the UV LED for `duration`.

    T-B4: queued whole onto the hardware owner thread -- the `time.sleep` in
    the middle used to freeze the GUI (and every napari repaint) for the entire
    blink, since the on and off writes have to bracket it.
    """
    submitHardware(_blinkUV_hw, duration, label='lasers.blinkUV')


def _blinkUV_hw(duration):
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAC9')
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'SAO9-65535')
    TS_Response_verbose()
    addToVerboseBoxText('UV LED on for '+str(duration)+' microseconds');
    logging.info('UV LED on for '+str(duration)+' microseconds');
    time.sleep(duration/1000)
    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'SAO9-0')
    TS_Response_verbose()


def buttonPressliveStateToggle():
    logging.debug('buttonPressliveStateToggle run')
    global shared_data
    if shared_data.liveMode == False:
        shared_data.liveMode = True
    else:
        shared_data.liveMode = False
    logging.debug('livestate now LaserControlScripts ', shared_data.liveMode)
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#End of functions
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def runlaserControllerUI(score,sMM_JSON,sform,sshared_data):
    #Go from self to global variables
    global core, MM_JSON, form, app, shared_data
    core = score
    MM_JSON = sMM_JSON
    form = sform
    # app = sapp
    shared_data = sshared_data
    criticalErrors=False

    #Get onoff and intensity from MM
    try:
        InitLaserButtonLabels(MM_JSON)
        InitLaserSliders(MM_JSON)
        InitFilterWheelRadioCheckbox()
    except (RuntimeError, OSError, AttributeError, KeyError) as exc:
        logging.debug('Error in InitLaserButtonLabels or InitLaserSliders: %s', exc)
        criticalErrors=True
    #Get frametimeinfo
    InitBFRadioCheckbox()
    global frameduration;
    frameduration = getFrameTimeInfo(0);

    # timer = QTimer(app)
    # timer.timeout.connect(lambda: timerloop(frameduration))

    # #Update the timer every 500 ms
    # timer.start(500)

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
        #T-F8: editingFinished, not textChanged -- one serial write per commit
        #instead of one per keystroke.
        exec("form.EditIntensity_Laser_" + str(i) + ".editingFinished.connect(lambda: ChangeIntensityLaserEditField(" + str(i) + "));")

    #Initialise the laser triggering boxes
    initLaserTrigEditBoxes();
    try:
        #Draw the laser trigger plot
        #Also see https://www.pythonguis.com/tutorials/plotting-pyqtgraph/
        drawplot(frameduration)

        #Change laser trigger scheme when values in boxes are changed
        for i in range(0,5):
            #T-F8: still textChanged (the plot is a live preview), but debounced
            #so a burst of keystrokes costs one rebuild instead of one each.
            exec("form.Delay_Edit_Laser_" + str(i) + ".textChanged.connect(lambda: scheduleDrawplot(frameduration));")
            exec("form.Length_Edit_Laser_" + str(i) + ".textChanged.connect(lambda: scheduleDrawplot(frameduration));")
            exec("form.BlinkFrames_Edit_Laser_" + str(i) + ".textChanged.connect(lambda: scheduleDrawplot(frameduration));")
    except (AttributeError, NameError, SyntaxError, RuntimeError) as exc:
        logging.error('error in execing forms: %s', exc)
        criticalErrors=True
    #Arm lasers button
    form.ARMlaserTriggerPushButton.clicked.connect(lambda: armLaserTriggering());

    #Button that resets laser triggering
    form.resetLasersTriggerButton.clicked.connect(lambda: ResetLasersTrigger());

    #Button that resets laser triggering
    form.resetLasersTriggerButton.clicked.connect(lambda: ResetLasersTriggerButtonPress(frameduration));

    #UV LED Button run
    form.PushUVLED.clicked.connect(lambda: blinkUV(float(form.UVLED_duration_EditField.text())));

    #Live button testing
    form.liveview_PushButton.clicked.connect(lambda: buttonPressliveStateToggle())
    
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

    try:
        #Reset laser triggers when startup for properly expected behaviour
        ResetLasersTrigger();
        #Initialise laser trigger edit buttons
        initLaserTrigEditBoxes();
    except (RuntimeError, OSError, AttributeError) as exc:
        logging.error('error in resetting laser boxes: %s', exc)
        criticalErrors=True
    
    return form, criticalErrors
