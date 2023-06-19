from PycroManagerFunctions import *
from TilingFunctions import *
import numpy as np
import time
import json
import glob
from PIL import Image
from datetime import datetime
from pathlib import Path
import pyperclip
from pycromanager import *

#Initiate the pycromanager
mmc = InitiatePycroManager();


def img_process_fn(image, metadata):
    ### create a new acquisition event in response to something in the image ###
    #Only do this every 10th frame to prevent delay between acq and doing things
    if np.mod(int(metadata['PVCAM-FrameNr']),1)==0:
        #We calc the wanted Intensity value (range 0-5)
        wantedIntValue = min(5,int(metadata['PVCAM-FrameNr'])/500*5)
        if int(metadata['PVCAM-FrameNr'])>=900:
            wantedIntValue = 0;
        # and set this as property to the 488 laser!
        mmc.set_property("TS_DAC02_488Laser", "Volts", str(wantedIntValue))

    #Then just return input image/metadata
    return image, metadata

#Initiase that 488 is on, but no volts
mmc.set_property("TS_DAC02_488Laser", "State", str(1))
mmc.set_property("TS_DAC02_488Laser", "Volts", str(0))

#Do acquisition
with Acquisition(directory='E:\Data\Scope\Test_neverImportant', name='acquisition_name',image_process_fn=img_process_fn) as acq:
    events = multi_d_acquisition_events(num_time_points=1000,time_interval_s=0.0)
    acq.acquire(events)
