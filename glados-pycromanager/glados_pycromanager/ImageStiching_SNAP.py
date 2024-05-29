from pycromanager import *
import numpy as np
import time
import json
import os, glob
# get object representing MMCore, used throughout
core = Core()
print(core)
bridge = Bridge()
mmc = bridge.get_core()

print('Starting')


startsz = 4;

fusing_buffer = 0;

x_dir = 1;
y_dir = 1;

sztrue_x = 3;
sztrue_y = 3;
overlap = 15;
sztrue_x += fusing_buffer;
sz_x = startsz+sztrue_x;
sz_y = startsz+sztrue_y;
#mov = 0.107*512*0.9;
magncorrection = 60/60;
#mov = 0.0978*512*0.9*magncorrection;
mov = 0.107*1024*(1-overlap/100)*magncorrection;
xy = np.empty([sz_x*sz_y+3,2]);
startx = mmc.get_x_position()
starty = mmc.get_y_position()
startx -= startsz*mov*x_dir+fusing_buffer*mov*x_dir;
starty -= startsz*mov*y_dir;
xy[0] = [startx, starty];
xy[1] = [startx, starty];
xy[2] = [startx, starty];
counter = 3;

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
        counter = counter+1;

print(xy)
mmc.set_exposure(1000);
mmc.snap_image();

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
}
print(JSONdata)

filename = 'acquisition_name';
foldername = "E:/Data/Scope/Test_neverImportant/Tiling/";
'''
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
            time.sleep(0.1)
        with Acquisition(foldername, filename) as acq:
            #create one event for the image at each z-slice
            events = []
            events = multi_d_acquisition_events(xy_positions=xy,keep_shutter_open_between_channels=True)
            acq.acquire(events)

        mmc.set_xy_position(startx+(startsz*mov+fusing_buffer*mov)*x_dir,starty+startsz*mov*y_dir)
'''
mmc.snap_image()
time.sleep(0.3)
'''
lastCreatedFolder = max(glob.glob(os.path.join(foldername, '*/')), key=os.path.getmtime)
with open(lastCreatedFolder+'/acqTilingData.json', 'w', encoding='utf-8') as f:
    json.dump(JSONdata, f, ensure_ascii=False, indent=4)
    '''
        #with XYTiledAcquisition(directory='E:/Data/Scope/Test_neverImportant/Tiling', name='acquisition_name', tile_overlap=100) as acq:
        #    #10 pixel overlap between adjacent tiles
#
#            #acquire a 2 x 1 grid
#            acq.acquire({'row': 0, 'col': 0})
#            acq.acquire({'row': sz, 'col': sz})
#            #for rep in range(0,1):
#            for rr in range(0,sz):
#                for cc in range(0,sz):
#                    print(str(rr)+'-'+str(cc)+'-'+str(1))
#                    acq.acquire({'row': rr, 'col': cc})

print('Done')
#pycromanager.multi_d_acquisition_events(num_time_points: int = 1, time_interval_s: float = 0, z_start: float = None, z_end: float = None, z_step: float = None, channel_group: str = None, channels: list = None, channel_exposures_ms: list = None, xy_positions=None, xyz_positions=None, order: str = 'tpcz', keep_shutter_open_between_channels: bool = False, keep_shutter_open_between_z_steps: bool = False)
#pycromanager.multi_d_acquisition_events(1, 0.05, None, None, None, None, None, None, xy_positions=None, xyz_positions=None, order: str = 'tpcz', keep_shutter_open_between_channels: bool = False, keep_shutter_open_between_z_steps: bool = False)

#pycromanager.XYTiledAcquisition(tile_overlap: int, directory: str = None, name: str = None, max_multi_res_index: int = None, image_process_fn: callable = None, pre_hardware_hook_fn: callable = None, post_hardware_hook_fn: callable = None, post_camera_hook_fn: callable = None, show_display: bool = True, image_saved_fn: callable = None, process: bool = False, saving_queue_size: int = 20, bridge_timeout: int = 500, port: int = 4827, debug: bool = False, core_log_debug: bool = False)


#

#Acquisition("E:\Data\Scope\Test_neverImportant\Tiling", "TileTest", None, None, None,  None,  None,  True,  None,  False,  20,  500,  4827,  False,  False)
