#Example:
#2912, 816 should be in image im_009

import numpy as np
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

print((mmc.get_x_position(),mmc.get_y_position()))
#startpos = [84910.72,-90846.28];
startpos = [mmc.get_x_position(),mmc.get_y_position()]

point_of_interest = [2516, 448]; #IN PIXELS
#point_of_interest = [2, 2]; #IN PIXELS

#Read the TileConfiguration.registered.txt file
filename = 'E:/Data/Scope/Test_neverImportant/Tiling/220809_1119/Tiling/TileConfiguration.registered.txt';
with open(filename) as f:
    lines = f.readlines()

#We start reading the line after "# Define the image coordinates"
for l in range (0,len(lines)):
    if lines[l].find('Define the image coordinates') > 0:
        startline = l+1;
        break;

TileConfigXYpos = np.zeros((len(lines)-startline,2))
for l in range(startline,len(lines)):
    startp1 = lines[l].find('; (');
    endp1 = lines[l].find(', ');
    TileConfigXYpos[l-startline,0] = lines[l][startp1+3:endp1];
    startp2 = lines[l].find(', ');
    endp2 = lines[l].find(')');
    TileConfigXYpos[l-startline,1] = lines[l][startp2+2:endp2];

distance_to_POI = np.zeros((len(TileConfigXYpos),1));
#Calculate distance from point of interest to corner of every image and find the minimal distance
for l in range(0,len(TileConfigXYpos)):
    if (point_of_interest[0] > TileConfigXYpos[l,0]) and (point_of_interest[1] > TileConfigXYpos[l,1]):
        distance_to_POI[l] = np.sqrt((point_of_interest[0]-TileConfigXYpos[l,0])**2+(point_of_interest[1]-TileConfigXYpos[l,1])**2);
    else:
        distance_to_POI[l] = 2048;


print(np.argmin(distance_to_POI))
print(distance_to_POI[np.argmin(distance_to_POI)])

corner_of_closest_image = TileConfigXYpos[np.argmin(distance_to_POI)]+[0,0];
print(corner_of_closest_image)

dist_POI_to_center = point_of_interest-(corner_of_closest_image+[512,512])
print(point_of_interest)
print(dist_POI_to_center)

XYpos_to_go_to = startpos+(corner_of_closest_image+dist_POI_to_center)*0.105
print(XYpos_to_go_to)

mmc.set_xy_position(startpos[0]-1024*0.105*5,startpos[1]-1024*0.105*5)
time.sleep(0.2)
mmc.set_xy_position(XYpos_to_go_to[0],XYpos_to_go_to[1])
time.sleep(5)
mmc.set_xy_position(startpos[0]-1024*0.105*5,startpos[1]-1024*0.105*5)
time.sleep(0.2)
mmc.set_xy_position(startpos[0],startpos[1])
