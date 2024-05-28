'''
Functions for pycromanager-related things
I.e. loading pycromanager, taking images, etc etc
'''
import numpy as np

# Get the core (mmc = micromanagercore) from pycromanager
def InitiatePycroManager():
    from pycromanager import Core;
    mmc = Core()
    print("Pycromanager initialised!")
    return mmc

#Custom image snapping
def snap_image(mmc):
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

#Set FoV to size specified by imSize
def Pycro_set_ImageSize(mmc,imSize):
    print(imSize)
    maxImSize = 2048;
    curROI = (mmc.get_roi().width, mmc.get_roi().height);
    if ((curROI[0] != maxImSize) and (curROI[1] != maxImSize)):
        mmc.set_roi(0,0,maxImSize,maxImSize);

    mmc.set_roi(int((maxImSize-imSize[0])/2),int((maxImSize-imSize[1])/2),int(imSize[0]),int(imSize[1]))

def Pycro_TurnOnBF(mmc):
    #Open shutter
    mmc.set_property('Core', 'AutoShutter', 0)
    mmc.set_property("TIDiaLamp","Intensity","12")
    mmc.set_property("TIDiaLamp","State","1")

def Pycro_TurnOffBF(mmc):
    mmc.set_property('Core', 'AutoShutter', 1)
    mmc.set_property("TIDiaLamp","Intensity","0")
    mmc.set_property("TIDiaLamp","State","0")

def Pycro_stopLiveMode(mmc):
    mmc.stop_sequence_acquisition()

def Pycro_startLiveMode(mmc):
    mmc.start_sequence_acquisition()

def Pycro_Setup_sptSettings(mmc,strobo_time_561,power_561,frametime):
    #Commands to setup 2 ms delay, 1 ms strobo 561
    #561 nm laser is at 3rd position
    for laser_id in range(3,4):
        mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', '*')
        #TS_Response_verbose_pr(mmc);
        mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAC'+str(laser_id));
        #TS_Response_verbose_pr(mmc);
        mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(laser_id)+'-0-' + str(65535));
        #TS_Response_verbose_pr(mmc);
        mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAS'+str(laser_id)+'-1-1')
        #TS_Response_verbose_pr(mmc);
        #print(str(1+1000*(frametime-(strobo_time_561))/2));
        mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAD'+str(laser_id)+'-'+str(1+1000*(frametime-(strobo_time_561))/2))
        #TS_Response_verbose_pr(mmc);
        #print(str(1000*strobo_time_561))
        mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAL'+str(laser_id)+'-'+str(1000*strobo_time_561))
        #TS_Response_verbose_pr(mmc);
        mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAO'+str(laser_id)+'-'+str(1)+'-1')
        #TS_Response_verbose_pr(mmc);
    #Commands to setup 0 ms delay, 1 ms strobo 405 every 10th frame at low power (25% should be slightly above minimum value)
    #405 nm laser is at 1st position
    laser_id = 1;
    mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAC'+str(laser_id));
    #TS_Response_verbose_pr(mmc);
    mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(laser_id)+'-0-' + str(round(65535*0.5)));
    #TS_Response_verbose_pr(mmc);
    for i in range(1,9):
        mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(laser_id)+'-'+str(i)+'-' + str(0));
        #TS_Response_verbose_pr(mmc);
    mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAS'+str(laser_id)+'-1-1')
    #TS_Response_verbose_pr(mmc);
    mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAD'+str(laser_id)+'-'+str(1))
    #TS_Response_verbose_pr(mmc);
    mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAL'+str(laser_id)+'-'+str(500))
    #TS_Response_verbose_pr(mmc);
    mmc.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAO'+str(laser_id)+'-'+str(0)+'-1')
    #TS_Response_verbose_pr(mmc);
    #Property setting for 200 (?) mW 561 and turning it on
    mmc.set_property('561Laser_LQGem','Power (mW)',str(power_561));
    mmc.set_property('561Laser_LQGem','Laser Operation','On');


def TS_Response_verbose_pr(mmc):
    mmc.get_property('TriggerScopeMM-Hub', 'Serial Receive');
    print(mmc.get_property('TriggerScopeMM-Hub', 'Serial Receive'));

def Pycro_Setup_stop_561_laser(mmc):
    mmc.set_property('561Laser_LQGem','Power (mW)',str(2));
    mmc.set_property('561Laser_LQGem','Laser Operation','Off');

import time
def moveDistanceWaitingForPFS(mmc,xposMoveTo,yposMoveTo,xySteps):
    mainCounter = 0;
    finishedMoving = 0;
    while finishedMoving == 0:
        curxpos = mmc.get_x_position();
        curypos = mmc.get_y_position();
        #Move to right?
        if xposMoveTo > curxpos:
            movetoPosNow_x = curxpos+min(xySteps,(xposMoveTo-curxpos));
        else:
            movetoPosNow_x = curxpos-min(xySteps,(curxpos-xposMoveTo));
        if yposMoveTo > curypos:
            movetoPosNow_y = curypos+min(xySteps,(yposMoveTo-curypos));
        else:
            movetoPosNow_y = curypos-min(xySteps,(curypos-yposMoveTo));
        '''
        print('--------')
        print(curxpos)
        print(curypos)
        print(movetoPosNow_x)
        print(movetoPosNow_y)
        print(xposMoveTo);
        print(yposMoveTo)
        '''
        mmc.set_xy_position(movetoPosNow_x,movetoPosNow_y);
        time.sleep(0.1);
        #Wait for PFS
        waitforPFSDone = 0;
        counter = 0;
        while waitforPFSDone == 0:
            if mmc.get_property("TIPFSStatus","Status") != "Locked in focus":
                counter += 1;
                time.sleep(0.05);
            else:
                waitforPFSDone = 1;

            if counter > 50:
                print('Focus error!!! Aborting')
                waitforPFSDone = 1;

        if (abs(xposMoveTo-curxpos)<1) & (abs(yposMoveTo-curypos)<1):
            print('FinishedMoving')
            finishedMoving = 1;
        else:
            mainCounter+=1;

        if mainCounter > 50:
            print('MainLoopError!')
            finishedMoving = 1;
