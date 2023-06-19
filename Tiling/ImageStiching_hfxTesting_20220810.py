'''
Package list (pip install)
imagej
'''
#from pycromanager import *
from PycroManagerFunctions import *
import numpy as np
import time
import json
import os, glob
from PIL import Image
from datetime import datetime
from pathlib import Path
import pyperclip

# get object representing MMCore, used throughout
print("Testing outside")
mmc = InitiatePycroManager();
print(mmc)
print('Starting')

#Enter information about size of FoV to obtain
for overlaparr = 10:
    ImageSize = 1024; #In pixels
    PixelSize = 105; #nm/pixel
    Size_Stitch_X = 50; #micrometer of stitching size in x
    Size_Stitch_Y = 50; #micrometer of stitching size in y

    waittime_SmallMovement = 0.3;
    waittime_LargeMovement = 2.5;

    FoVs_initial = 3; #number of FoVs to fix unsteady screws etc
    Overlap = overlaparr; #Overlap in percent (i.e. 10 = 10%)

    #Create folder with current datetime stamp
    filename = 'acquisition_name';
    mainFolder = "E:/Data/Scope/Test_neverImportant/Tiling/ImSize"+str(ImageSize)+"_Overlap"+str(Overlap)+"/";
    newFolder = datetime.now().strftime("%y%m%d_%H%M")+"/";

    startsz = 3;
    sztrue_x = int(np.ceil((((Size_Stitch_X*1000)/PixelSize)-ImageSize)/(ImageSize*(1-Overlap/100))+1));
    sztrue_y = int(np.ceil((((Size_Stitch_Y*1000)/PixelSize)-ImageSize)/(ImageSize*(1-Overlap/100))+1));
    mmc.set_exposure(100)

    fusing_buffer = 0;

    x_dir = 1;
    y_dir = 1;

    overlap = Overlap;
    sztrue_x += fusing_buffer;
    sz_x = startsz+sztrue_x;
    sz_y = startsz+sztrue_y;
    #mov = 0.107*512*0.9;
    magncorrection = 60/60;
    #mov = 0.0978*512*0.9*magncorrection;
    mov = PixelSize/1000*ImageSize*(1-overlap/100)*magncorrection;
    startx = mmc.get_x_position()
    starty = mmc.get_y_position()
    startx -= startsz*mov*x_dir+fusing_buffer*mov*x_dir;
    starty -= startsz*mov*y_dir;
    counter = 0;
    xy = np.empty([sz_x*sz_y+counter,2]);
    snap = np.empty([sz_x*sz_y+counter,1]);
    for i in range(0,counter):
        xy[i] = [startx, starty];

    snake = 0;
    #Add reversal to get 'snake'-like
    for yy in range(0,sz_y):
        for xx in range(0,sz_x):
            if snake:
                if (yy%2):
                    #
                    xy[counter] = [startx+mov*x_dir*(sz_x-1)+mov*xx*x_dir*-1,starty+mov*yy*y_dir];
                else:
                    xy[counter] = [startx+mov*xx*x_dir*1,starty+mov*yy*y_dir];
            else:
                xy[counter] = [startx+mov*xx*x_dir*1,starty+mov*yy*y_dir];

            snap[counter] = 1;
            if yy < startsz:
                snap[counter] = 0;
            #if yy >= sz_y-startsz:
            #    snap[counter] = 0;
            if xx < startsz:
                snap[counter] = 0;
            #if xx >= sz_x-startsz:
            #    snap[counter] = 0;

            counter = counter+1;

    print(xy)
    print(snap)


    def snap_image():
        # acquire an image and display it
        for i in range(0,3): #Try three times, something it screws up
            try:
                mmc.snap_image()
                tagged_image = mmc.get_tagged_image()
                # get the pixels in numpy array and reshape it according to its height and width
                image_array = np.reshape(
                    tagged_image.pix,
                    newshape=[-1, tagged_image.tags["Height"], tagged_image.tags["Width"]],
                )
                break
            except ErrorException:
                try:
                    print("Error in snap_image() "+ErrorException);
                except:
                    print("Error in snap_image() ");

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

    JSONdata = {
        "startsz": startsz,
        "fusing_buffer": fusing_buffer,
        "x_dir" : x_dir,
        "y_dir" : y_dir,
        "sztrue_x" : sztrue_x,
        "sztrue_y" : sztrue_y,
        "mov" : mov,
        #"xy" : xy,
        "overlap": overlap,
        "counter": counter,
        "StartPosXYStage_X": startx,
        "StartPosXYStage_Y": starty,
    }
    print(JSONdata)


    Path(mainFolder+newFolder).mkdir(parents=True, exist_ok=True)

    if mov < 1e4:
        if max((max(xy[:,0])-min(xy[:,0])),(max(xy[:,1])-min(xy[:,1]))) < 2e4:
            for it in range(0,2):
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
                #create one event for the image at each z-slice
                events = []
                events = multi_d_acquisition_events(xy_positions=xy,keep_shutter_open_between_channels=True)
                acq.acquire(events)
                '''
            Path(mainFolder+newFolder+"Tiling/").mkdir(parents=True, exist_ok=True)
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
                    im = Image.fromarray(snap_image())
                    im.save(mainFolder+newFolder+"Tiling/"+"im_"+lz+str(snapCounter)+".tif")
                    #Repeat the first image to get good lighting
                    if i>0:
                        if snap[i-1]==0:
                            im = Image.fromarray(snap_image())
                            im.save(mainFolder+newFolder+"Tiling/"+"im_"+lz+str(snapCounter)+".tif")
                    snapCounter+=1;

            #At the end, move back to orig position
            mmc.set_xy_position(startx-mov*m,starty-mov*m)
            time.sleep(0.2)
            mmc.set_xy_position(startx+(startsz*mov+fusing_buffer*mov)*x_dir,starty+startsz*mov*y_dir)

    #Store some JSON info
    with open(mainFolder+newFolder+"Tiling/"+'acqTilingData.json', 'w', encoding='utf-8') as f:
        json.dump(JSONdata, f, ensure_ascii=False, indent=4)

    # DeepBacs in ImageJ from macro:
    #run("Command From Macro", "command=[de.csbdresden.stardist.StarDist2D], args=['input':'9tr.tif', 'modelChoice':'Model (.zip) from File', 'normalizeInput':'true', 'percentileBottom':'1.0', 'percentileTop':'99.8', 'probThresh':'0.5', 'nmsThresh':'0.4', 'outputType':'Both', 'modelFile':'\\\\\\\\IFMB-NAS\\\\AG Endesfelder\\\\Data\\\\Koen\\\\Scientific\\\\Segmentation\\\\DeepBac\\\\Test_standalone\\\\model\\\\hfx_20220722\\\\TF_SavedModel.zip', 'nTiles':'1', 'excludeBoundary':'2', 'roiPosition':'Automatic', 'verbose':'false', 'showCsbdeepProgress':'false', 'showProbAndDist':'false'], process=[false]");
    #run("Set Measurements...", "area mean standard modal min centroid center perimeter bounding fit shape feret's integrated median skewness kurtosis area_fraction stack redirect=None decimal=3");
    #roiManager("multi-measure measure_all");


    if x_dir == 1:
        directionName = "Right & ";
    else:
        directionName = "Left & ";
    if y_dir == 1:
        directionName = directionName+"Down"
    else:
        directionName = directionName+"Up"
    if x_dir == 1 and y_dir == 1:
        directionName = directionName+"                ";



    macroTextForStitching = "run(\"Grid/Collection stitching\", \"type=[Grid: row-by-row] order=["+directionName+"] grid_size_x="+str(sztrue_x)+" grid_size_y="+str(sztrue_y)+" tile_overlap="+str(overlap)+" first_file_index_i="+str(0)+" directory="+mainFolder+newFolder+"Tiling file_names=im_{iii}.tif output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] add_tiles_as_rois regression_threshold=0.3 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 add_tiles_as_rois compute_overlap display_fusion computation_parameters=[Save computation time (but use more RAM)] image_output=[Write to disk] output_directory="+mainFolder+newFolder+"Tiling/\");";
    print(macroTextForStitching)
    with open(mainFolder+newFolder+'Tiling\Macro.ijm', 'w') as f:
        f.write(macroTextForStitching)
    with open(mainFolder+newFolder+'Tiling\IJMBatMacro.bat', 'w') as f:
        f.write("c:\n");
        f.write("cd \"C:\\Users\\SMIPC2\\Documents\\Microscope Software\\Fiji.app\" \n");
        f.write("ImageJ-win64 --ij2 --headless --console --run "+mainFolder+newFolder+"Tiling\Macro.ijm");

    #Run the just-created bat file
    os.system(mainFolder+newFolder+"Tiling\IJMBatMacro.bat");


print('Done')
#pycromanager.multi_d_acquisition_events(num_time_points: int = 1, time_interval_s: float = 0, z_start: float = None, z_end: float = None, z_step: float = None, channel_group: str = None, channels: list = None, channel_exposures_ms: list = None, xy_positions=None, xyz_positions=None, order: str = 'tpcz', keep_shutter_open_between_channels: bool = False, keep_shutter_open_between_z_steps: bool = False)
#pycromanager.multi_d_acquisition_events(1, 0.05, None, None, None, None, None, None, xy_positions=None, xyz_positions=None, order: str = 'tpcz', keep_shutter_open_between_channels: bool = False, keep_shutter_open_between_z_steps: bool = False)

#pycromanager.XYTiledAcquisition(tile_overlap: int, directory: str = None, name: str = None, max_multi_res_index: int = None, image_process_fn: callable = None, pre_hardware_hook_fn: callable = None, post_hardware_hook_fn: callable = None, post_camera_hook_fn: callable = None, show_display: bool = True, image_saved_fn: callable = None, process: bool = False, saving_queue_size: int = 20, bridge_timeout: int = 500, port: int = 4827, debug: bool = False, core_log_debug: bool = False)


#

#Acquisition("E:\Data\Scope\Test_neverImportant\Tiling", "TileTest", None, None, None,  None,  None,  True,  None,  False,  20,  500,  4827,  False,  False)
