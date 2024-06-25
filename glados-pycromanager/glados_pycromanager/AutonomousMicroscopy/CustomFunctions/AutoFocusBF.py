from MainScripts import FunctionHandling
from shapely import Polygon, affinity
import math
import numpy as np
import inspect
import dask.array as da
import ndtiff

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "auto_focus_bf": {
            "input":[
            ],
            "output":[
            ],
            "required_kwargs": [
                {"name": "StageName", "description": "Name of the stage",  "default": 'TIPFSOffset', "type": str},
                {"name": "startPosition", "description": "Starting position, relative from current", "default": -75, "type": float},
                {"name": "endPosition", "description": "Ending position, relative from current", "default": 75, "type": float},
                {"name": "numsteps", "description": "Number of z steps", "default": 50, "type": int}
            ],
            "optional_kwargs": [
                {"name": "final_offset", "description": "Final offset from 'perfect' position", "default": 12, "type": float}
            ],
            "help_string": "",
            "display_name": "Auto-focus BF"
        },
        "auto_focus_iter_bf": {
            "input":[
            ],
            "output":[
            ],
            "required_kwargs": [
                {"name": "StageName", "description": "Name of the stage",  "default": 'TIPFSOffset', "type": str},
                {"name": "startPosition", "description": "Starting position, relative from current", "default": -75, "type": float},
                {"name": "endPosition", "description": "Ending position, relative from current", "default": 75, "type": float},
                {"name": "numsteps", "description": "Number of z steps", "default": 50, "type": int}
            ],
            "optional_kwargs": [
                {"name": "final_offset", "description": "Final offset from 'perfect' position", "default": 12, "type": float}
            ],
            "help_string": "",
            "display_name": "Iterative Auto-focus BF"
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
def auto_focus_bf(core,**kwargs):
    
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    print(kwargs)
    
    #General idea: take images throughout z-stack of BF images, compuate the value/deriv, find the best, set position to that
    import time
    zmovestage = kwargs['StageName']#"TIPFSOffset"
    startp = float(kwargs['startPosition'])#-75
    endp = float(kwargs['endPosition'])#75
    numsteps = int(kwargs['numsteps'])#50
    final_offset = float(kwargs['final_offset'])#6
    
    minval = startp
    valstep = (endp-startp)/numsteps
    
    from scipy import signal
    def laplace_filter(image):
        """Applies a sort-of Laplace filter to an image.

        Args:
        image: A NumPy array representing the image.

        Returns:
        A NumPy array representing the filtered image.
        """
        
        #Note that this kernel is not a typo - this is how it should be.
        kernel = np.array([[0, 1, 0],
                        [1, 0, 1],
                        [0, -3, 0]])
        filtered_image = signal.convolve2d(image, kernel)
        return filtered_image
    
    redondo_arr = []

    core.set_relative_position(zmovestage,minval) #type:ignore
    core.wait_for_system()
    for n in range(numsteps):
        print(n)
        core.set_relative_position(zmovestage,valstep) #type:ignore
        core.wait_for_system()
        core.snap_image()
        # core.wait_for_system()
        im = core.get_tagged_image()
        im_ndarr = im.pix.reshape((im.tags["Height"],im.tags["Width"]))
        
        redondo_arr.append(np.mean(laplace_filter(im_ndarr)**2))
    
    from scipy.signal import savgol_filter
    derivRedondo = np.gradient(savgol_filter(redondo_arr, window_length=int(numsteps/20)+1, polyorder=1))
    #make the top and bottom 5% of points 0:
    derivRedondo[:int(len(derivRedondo)*0.05)] = np.mean(derivRedondo)
    derivRedondo[int(len(derivRedondo)*0.95):] = np.mean(derivRedondo)
    #check if the peak is negative or positive:
    if sum(derivRedondo) < 0:
        derivRedondo *= -1
    derivRedondo_smoothed = savgol_filter(derivRedondo, window_length=int(numsteps/20)+1, polyorder=1)
    #Find the max of the deriv:
    derivRedondo_max_index = np.argmax(derivRedondo_smoothed)
    print(f"derivRedondo_max_index max: {derivRedondo_max_index}")
    
    #Currently, we're at the max pos, so we move to the final position:
    #Factually, we're moving to the start (endp*-1 + startp), then move the derivRedondo offset, then add a final_offset
    core.set_relative_position(zmovestage,endp*-1+startp+valstep*derivRedondo_max_index+final_offset) #type:ignore
    
    
    output = {}
    
    return output


def auto_focus_bf_visualise(datastruct,core,**kwargs):
    #This is how datastruct is organised...
    output,pointsLayer,mdaDataobject = datastruct
    
    
    # create features for each point
    features = {
        'outputval': output
    }
    # textv = {'string': 'Hi!','size':20,'color':'green','translation':np.array([-30,0])}
    textv = {
        'string': 'GrayValue {outputval:.2f}',
        'size': 15,
        'color': 'red',
        'translation': np.array([0, 0]),
        'anchor': 'upper_left',
    }
    pointsLayer.data = [0,0]
    pointsLayer.features = features
    pointsLayer.text = textv
    pointsLayer.size = 0
    
def auto_focus_iter_bf(core,**kwargs):
    
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    print(kwargs)
    
    #General idea: take images throughout z-stack of BF images, compuate the value/deriv, find the best, set position to that
    import time
    zmovestage = kwargs['StageName']#"TIPFSOffset"
    startp = float(kwargs['startPosition'])#-75
    endp = float(kwargs['endPosition'])#75
    numsteps = int(kwargs['numsteps'])#50
    final_offset = float(kwargs['final_offset'])#6
    
    minval = startp
    valstep = (endp-startp)/numsteps
    
    from scipy import signal
    def laplace_filter(image):
        """Applies a sort-of Laplace filter to an image.

        Args:
        image: A NumPy array representing the image.

        Returns:
        A NumPy array representing the filtered image.
        """
        
        #Note that this kernel is not a typo - this is how it should be.
        kernel = np.array([[0, 1, 0],
                        [1, 0, 1],
                        [0, -3, 0]])
        filtered_image = signal.convolve2d(image, kernel)
        return filtered_image
    
    
    
    # kwargs['startPosition'] = -100
    # kwargs['endPosition'] = 100
    
    
    n_per_zoom = 6
    n_zooms = 6
    
    redondo_arr = []
    #First, we move to start, take n_per_zoom images over the full range, and see which is best:
    totalMove = 0
    
    start_abs_pos = core.get_position(zmovestage)
    
    wantedResolution = 3
    maxmaxiter = 10
    
    totalIter = 0
    resolutionTest = np.inf
    
    def testArray_report_redondo(core,position_array_test):
        res_arr = []
        for n in range(len(position_array_test)):
            print(f"n: {n}, abs_pos_arr[n]: {position_array_test[n]}")
            core.set_position(zmovestage,position_array_test[n]) #type:ignore
            core.wait_for_system()
            core.snap_image()
            im = core.get_tagged_image()
            im_ndarr = im.pix.reshape((im.tags["Height"],im.tags["Width"]))
            res_arr.append(np.mean(laplace_filter(im_ndarr)**2))
        return res_arr
    
    def single_redondo(core,position):
        core.set_position(zmovestage,position) #type:ignore
        core.wait_for_system()
        core.snap_image()
        im = core.get_tagged_image()
        im_ndarr = im.pix.reshape((im.tags["Height"],im.tags["Width"]))
        return (np.mean(laplace_filter(im_ndarr)**2))
    
    position_array_test = start_abs_pos+np.linspace(float(kwargs['startPosition']),float(kwargs['endPosition']),num=n_per_zoom)
    
    while resolutionTest > wantedResolution and totalIter < maxmaxiter:
        print(f"New full redondo test with {(position_array_test)} positions, iter {totalIter}")
        redondo_arr = testArray_report_redondo(core,position_array_test)
        
        #see if the argmax is at 0 or end and do up to 3 more:
        max_index = np.argmax(redondo_arr)
        while max_index == 0 or max_index == len(redondo_arr)-1:
            print(f"max index found at {max_index} for array {redondo_arr}")
            n_appending = 0
            max_n_appending = 3
            if n_appending < max_n_appending:
                if max_index == 0:
                    additional_position = position_array_test[0]-(position_array_test[1]-position_array_test[0])
                    print('Doing new position at start at '+str(additional_position))
                    newEntry = single_redondo(core,additional_position)
                    redondo_arr = [newEntry]+redondo_arr
                    position_array_test = [additional_position]+position_array_test
                    max_index = np.argmax(redondo_arr)
                elif max_index == len(redondo_arr)-1:
                    print('Doing new position at end at '+str(additional_position))
                    additional_position = position_array_test[-1]+(position_array_test[-1]-position_array_test[-2])
                    newEntry = single_redondo(core,additional_position)
                    redondo_arr = redondo_arr+[newEntry]
                    position_array_test = position_array_test+[additional_position]
                    max_index = np.argmax(redondo_arr)
                n_appending += 1
            else:
                break
        
        #So now we have a good array
        #normalize
        redondo_arr_nrom = redondo_arr/np.max(redondo_arr)
        max_index = np.argmax(redondo_arr_nrom)
        print(f"final redondo_arr_nrom: {redondo_arr_nrom} at pos {position_array_test}")
        
        #Choose the new array:
        new_redondo_arr = np.linspace(position_array_test[max_index-1],position_array_test[max_index+1],num=n_per_zoom)
        redondo_arr = new_redondo_arr
        
        resolutionTest = position_array_test[1]-position_array_test[0]
        totalIter += 1
    
    print(f"final redondo_arr: {redondo_arr]
    
    # for z in range(n_zooms):
    #     if z == 0:
    #         abs_pos_arr = start_abs_pos+np.linspace(float(kwargs['startPosition']),float(kwargs['endPosition']),num=n_per_zoom)
    #     else: #else, we have a redondo_arr already.
    #         #First, find the max index of the redondo_arr:
    #         max_index = np.argmax(redondo_arr)
    #         abs_pos_arr_old = abs_pos_arr
    #         new_start_pos = abs_pos_arr[max_index-1]
    #         new_end_pos = abs_pos_arr[max_index+1]
    #         abs_pos_arr = np.linspace(new_start_pos,new_end_pos,num=n_per_zoom)
    #     redondo_arr = []
            
    #     for n in range(len(abs_pos_arr)):
    #         print(f"n: {n}, abs_pos_arr[n]: {abs_pos_arr[n]}")
    #         core.set_position(zmovestage,abs_pos_arr[n]) #type:ignore
    #         core.wait_for_system()
    #         core.snap_image()
    #         im = core.get_tagged_image()
    #         im_ndarr = im.pix.reshape((im.tags["Height"],im.tags["Width"]))
    #         redondo_arr.append(np.mean(laplace_filter(im_ndarr)**2))
    #     redondo_arr /= np.max(redondo_arr)
    #     print(f"{z} zoom completed, redondo arr: {redondo_arr}, abs_pos_arr: {abs_pos_arr}")
        
    #     #find the max index:
    #     max_index = np.argmax(redondo_arr)
    #     #check if it's 0 or last index:
    #     if max_index == 0:
    #         z-=1
    #         if z < 0:
    #             kwargs['startPosition'] = str(float(kwargs['startPosition'])-abs_pos_arr[2]-abs_pos_arr[1])
    #             print("MOVED START POS FORWARD Z = 0")
    #         else:
    #             abs_pos_arr = abs_pos_arr_old
    #             abs_pos_arr -= (abs_pos_arr_old[1]-abs_pos_arr_old[0])
    #             print("MOVED START POS FORWARD Z > 0")
    #     if max_index == len(redondo_arr)-1:
    #         z-=1
    #         if z < 0:
    #             kwargs['endPosition'] = str(float(kwargs['endPosition'])+abs_pos_arr[2]-abs_pos_arr[1])
    #             print("MOVED END POS BACKWARD Z = 0")
    #         else:
    #             abs_pos_arr = abs_pos_arr_old
    #             abs_pos_arr += (abs_pos_arr_old[1]-abs_pos_arr_old[0])
    #             print("MOVED END POS BACKWARD Z > 0")
            
    # final_pos = abs_pos_arr[np.argmax(redondo_arr)]
    # core.set_position(zmovestage,final_pos+final_offset) #type:ignore
    
    
    # for i in range(-10.5, 11, 2):
    #     print(i)
    
    # core.set_relative_position(zmovestage,float(kwargs['startPosition'])) 
    # #type:ignore
    # totalMove += float(kwargs['startPosition'])
    # core.wait_for_system()
    # valstep = (float(kwargs['endPosition'])-float(kwargs['startPosition']))/n_per_zoom
    # for n in range(n_per_zoom):
    #     print(n)
    #     core.set_relative_position(zmovestage,valstep) #type:ignore
    #     totalMove += valstep
    #     core.wait_for_system()
    #     core.snap_image()
    #     im = core.get_tagged_image()
    #     im_ndarr = im.pix.reshape((im.tags["Height"],im.tags["Width"]))
        
    #     redondo_arr.append(np.mean(laplace_filter(im_ndarr)**2))
    # core.set_relative_position(zmovestage,totalMove*-1) #type:ignore
    
    
    # redondo_arr = []

    # core.set_relative_position(zmovestage,minval) #type:ignore
    # core.wait_for_system()
    # for n in range(numsteps):
    #     print(n)
    #     core.set_relative_position(zmovestage,valstep) #type:ignore
    #     core.wait_for_system()
    #     core.snap_image()
    #     # core.wait_for_system()
    #     im = core.get_tagged_image()
    #     im_ndarr = im.pix.reshape((im.tags["Height"],im.tags["Width"]))
        
    #     redondo_arr.append(np.mean(laplace_filter(im_ndarr)**2))
    
    # from scipy.signal import savgol_filter
    # derivRedondo = np.gradient(savgol_filter(redondo_arr, window_length=int(numsteps/20)+1, polyorder=1))
    # #make the top and bottom 5% of points 0:
    # derivRedondo[:int(len(derivRedondo)*0.05)] = np.mean(derivRedondo)
    # derivRedondo[int(len(derivRedondo)*0.95):] = np.mean(derivRedondo)
    # #check if the peak is negative or positive:
    # if sum(derivRedondo) < 0:
    #     derivRedondo *= -1
    # derivRedondo_smoothed = savgol_filter(derivRedondo, window_length=int(numsteps/20)+1, polyorder=1)
    # #Find the max of the deriv:
    # derivRedondo_max_index = np.argmax(derivRedondo_smoothed)
    # print(f"derivRedondo_max_index max: {derivRedondo_max_index}")
    
    # #Currently, we're at the max pos, so we move to the final position:
    # #Factually, we're moving to the start (endp*-1 + startp), then move the derivRedondo offset, then add a final_offset
    # core.set_relative_position(zmovestage,endp*-1+startp+valstep*derivRedondo_max_index+final_offset) #type:ignore
    
    
    output = {}
    
    return output
