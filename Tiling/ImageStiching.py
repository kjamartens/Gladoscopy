'''
Package list (pip install)
imagej
'''
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

#Initiate the pycromanager
mmc = InitiatePycroManager();

#Enter information about size of FoV to obtain
ImageSize = 512; #In pixels
PixelSize = 105; #nm/pixel
Size_Stitch_X = 150; #micrometer of stitching size in x
Size_Stitch_Y = 150; #micrometer of stitching size in y
FoVs_initial = 3; #number of FoVs to fix unsteady screws etc
Overlap = 30; #Overlap in percent (i.e. 10 = 10%)
x_dir = 1; #Direction in X: 1 = right-moveing, -1 = left-moving
y_dir = 1; #Direction in Y: 1 = down-moveing, -1 = up-moving
#Set waittime after small or large movements to ensure full stop of (slow-moving) xy stages
waittime_SmallMovement = 0.3;
waittime_LargeMovement = 2;
#Create folder with current datetime stamp
filename = 'acquisition_name';
mainFolder = "E:/Data/Scope/Tiling/Test";
daughterFolder = "/"+datetime.now().strftime("%y%m%d_%H%M")+"/";
Path(mainFolder+daughterFolder).mkdir(parents=True, exist_ok=True)

# Start non-user-definable code here
startsz = FoVs_initial;
sztrue_x = int(np.ceil((((Size_Stitch_X*1000)/PixelSize)-ImageSize)/(ImageSize*(1-Overlap/100))+1));
sztrue_y = int(np.ceil((((Size_Stitch_Y*1000)/PixelSize)-ImageSize)/(ImageSize*(1-Overlap/100))+1));
overlap = Overlap;
sz_x = startsz+sztrue_x;
sz_y = startsz+sztrue_y;
magncorrection = 60/60;
#Calculate the actual movement between FoVs here
mov = PixelSize/1000*ImageSize*(1-overlap/100)*magncorrection;
#Get the current start position as initial point
startx = mmc.get_x_position()
starty = mmc.get_y_position()
#Calculate the real start position - moving a little outside the FoV to ensure correct movement of the XY stage
startx -= startsz*mov*x_dir;
starty -= startsz*mov*y_dir;
startSnaps = 0;#>0 if you want to have initial snapshots before starting imaging.

#Get the list of xy positions, and corresponding boolean values whether or not a snap will take place.
[xy,snap] = InitialiseXYPositions(sz_x,sz_y,startx,starty,mov,x_dir,y_dir,startsz,startSnaps)

#Determine JSONdata to store
JSONdata = {
    "startsz": startsz,
    "x_dir" : x_dir,
    "y_dir" : y_dir,
    "sztrue_x" : sztrue_x,
    "sztrue_y" : sztrue_y,
    "mov" : mov,
    "overlap": overlap,
    "startSnaps": startSnaps,
    "StartPosXYStage_X": startx,
    "StartPosXYStage_Y": starty,
}

#Ensure that we only move within safety constraints
if mov < 1e4:
    if max((max(xy[:,0])-min(xy[:,0])),(max(xy[:,1])-min(xy[:,1]))) < 2e4:
        #Move a little around to ensure that screws are active and such
        for it in range(0,1):
            m = 5;
            mmc.set_xy_position(startx-mov*m,starty-mov*m)
            time.sleep(0.1)
            mmc.set_xy_position(startx-mov*m,starty+mov*m)
            time.sleep(0.1)
            mmc.set_xy_position(startx+mov*m,starty+mov*m)
            time.sleep(0.1)
            mmc.set_xy_position(startx+mov*m,starty-mov*m)
            time.sleep(0.1)
            mmc.set_xy_position(startx,starty)
            time.sleep(3)
        '''
        with Acquisition(foldername, filename) as acq:
            events = []
            events = multi_d_acquisition_events(xy_positions=xy,keep_shutter_open_between_channels=True)
            acq.acquire(events)
        '''
        #Create the Tiling folder if it doesn't exist
        Path(mainFolder+daughterFolder+"Tiling/").mkdir(parents=True, exist_ok=True)
        #Loop over all positions
        snapCounter = 0;
        for i in range(0,len(xy)):
            print("Tiling! " +str(Size_Stitch_X) +"x"+str(Size_Stitch_Y)+" um ("+str(sztrue_x)+"x"+str(sztrue_y) +" FoVs) " + str(round(i/len(xy)*100))+" % done ("+str(i)+"|"+str(len(xy))+")")
            #Check if the xy stage moved a lot - let it rest a while if it did
            totalMoved = 0;
            if i > 0:
                totalMoved = np.sqrt((xy[i,0]-xy[i-1,0])**2+(xy[i,1]-xy[i-1,1])**2);
            if totalMoved < 100:
                waittime = waittime_SmallMovement;
            else:
                waittime = waittime_LargeMovement;
            mmc.set_xy_position(xy[i,0],xy[i,1]);
            time.sleep(waittime);
            #Snap the image if needed
            lz = getLeadingZeros(snapCounter);
            if snap[i]:
                im = Image.fromarray(snap_image(mmc))
                im.save(mainFolder+daughterFolder+"Tiling/"+"im_"+lz+str(snapCounter)+".tif")
                #Repeat the first image to get good lighting
                if snapCounter == 0:
                    im = Image.fromarray(snap_image(mmc))
                    im.save(mainFolder+daughterFolder+"Tiling/"+"im_"+lz+str(snapCounter)+".tif")
                snapCounter+=1;

        #At the end, move back to orig position
        mmc.set_xy_position(startx-mov*m,starty-mov*m)
        time.sleep(0.2)
        mmc.set_xy_position(startx+(startsz*mov)*x_dir,starty+startsz*mov*y_dir)

#Store some JSON info
with open(mainFolder+daughterFolder+"Tiling/"+'/acqTilingData.json', 'w', encoding='utf-8') as f:
    json.dump(JSONdata, f, ensure_ascii=False, indent=4)

SegmentAllBFImages(mainFolder,daughterFolder,sztrue_x,sztrue_y)

print('Done')
