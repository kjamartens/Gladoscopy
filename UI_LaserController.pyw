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
    for i in range(0,5):
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
#--------------------------------------------------------------------------------------
#End of functions
#--------------------------------------------------------------------------------------

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
for i in range(0,5):
    #Change on-off state when button is pressed
    exec("form.FW_radioButton_" + str(i) + ".clicked.connect(lambda: ChangeFilterWheelFromRadioCheckBox(" + str(i) + "));")

#Show window and start app
window.show()
app.exec()
