'''

PERFORMED THIS EXPERIMENT EXACTLY LIKE THIS IN NIGHT OF 08-08 TO 09-08 2022. Results in
E:\Data\Scope\XYStability

'''
from pycromanager import *
import numpy as np
import time
import json
import os, glob
from PIL import Image
from datetime import datetime
from pathlib import Path
import pyperclip

# get object representing MMCore, used throughout
core = Core()
print(core)
bridge = Bridge()
mmc = bridge.get_core()

print('Starting')

# Long duration stability test of XY stage

startx = mmc.get_x_position()
starty = mmc.get_y_position()
print(startx)
print(starty)

xposes = [85020,86069,85020,86069];
yposes = [-90701,-90701,-90143,-90143];


def snap_image():
    mmc.set_exposure(100)
    # acquire an image and display it
    mmc.snap_image()
    tagged_image = mmc.get_tagged_image()
    # get the pixels in numpy array and reshape it according to its height and width
    image_array = np.reshape(
        tagged_image.pix,
        newshape=[-1, tagged_image.tags["Height"], tagged_image.tags["Width"]],
    )
    # return the first channel if multiple exists
    return image_array[0, :, :]


def getLeadingZeros(counter):
	if (counter < 10):
		lz = "00";
	else:
		if (counter < 100):
			lz = "0";
		else:
			lz = "";
	return lz;

waittime = 60*5/4;

#Create folder with current datetime stamp
filename = 'acquisition_name';
mainFolder = "E:/Data/Scope/Test_neverImportant/Tiling/";
newFolder = datetime.now().strftime("%y%m%d_%H%M")+"/";

Path(mainFolder+newFolder).mkdir(parents=True, exist_ok=True)

Path(mainFolder+newFolder+"Tiling/").mkdir(parents=True, exist_ok=True)
snapCounter = 0;
nrit = 220;
for it in range(0,nrit):
    for i in range(0,len(xposes)):
        print(str(snapCounter+1)+"/"+str(4*nrit))
        mmc.set_xy_position(xposes[i],yposes[i]);
        time.sleep(waittime);
        #Snap the image if needed
        lz = getLeadingZeros(snapCounter);
        im = Image.fromarray(snap_image())
        im.save(mainFolder+newFolder+"Tiling/"+"im_"+lz+str(snapCounter)+".tif")
        snapCounter+=1;

print('Finished!')
