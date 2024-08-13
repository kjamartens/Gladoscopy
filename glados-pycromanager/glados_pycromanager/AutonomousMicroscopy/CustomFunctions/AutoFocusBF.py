from MainScripts import FunctionHandling
from shapely import Polygon, affinity
import math
import numpy as np
import inspect
import dask.array as da
import ndtiff
import os
import cv2
import time

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "auto_focus_iter_rel_bf": {
            "input":[
            ],
            "output":[
            ],
            "required_kwargs": [
                
                {"name": "Method", "description": "Name of the method [Choice of: Redondo, Volath, Tenengrad, Laplacian]",  "default": 'Laplacian', "type": str},
                {"name": "frame_time_ms", "description": "Frametime [ms]",  "default": 200, "type": float},
                {"name": "n_images", "description": "Number of images to average over",  "default": 5, "type": int},
                {"name": "StageName", "description": "Name of the stage",  "default": 'TIPFSOffset', "type": str},
                {"name": "startPosition", "description": "Starting position, relative from current", "default": -75, "type": float},
                {"name": "endPosition", "description": "Ending position, relative from current", "default": 75, "type": float},
                {"name": "n_positions", "description": "Number of z steps per iteration", "default": 6, "type": int},
                {"name":"aggressiveness", "description": "Higher = more aggressive jumping. 1 would mean no jumping, 10 means zoom in to center 1/10th, etc.", "default": 5, "type": int},
                {"name":"wantedResolution", "description": "Final resolution - i.e. stopping criteria", "default": 0.5, "type": float},
                {"name":"waitTimeMs", "description": "Wait time in ms after each move", "default": 100, "type": float}
            ],
            "optional_kwargs": [
            ],
            "help_string": "",
            "display_name": "Iterative Auto-focus BF [Relative Position]"
        },
        "auto_focus_iter_abs_bf": {
            "input":[
            ],
            "output":[
            ],
            "required_kwargs": [
                {"name": "Method", "description": "Name of the method [Choice of: Redondo, Volath,Tenengrad, Laplacian]",  "default": 'Laplacian', "type": str},
                {"name": "frame_time_ms", "description": "Frametime [ms]",  "default": 200, "type": float},
                {"name": "n_images", "description": "Number of images to average over",  "default": 5, "type": int},
                {"name": "StageName", "description": "Name of the stage",  "default": 'TIPFSOffset', "type": str},
                {"name": "startPosition", "description": "Starting position, absolute", "default": 0, "type": float},
                {"name": "endPosition", "description": "Ending position, absolute", "default": 400, "type": float},
                {"name": "n_positions", "description": "Number of z steps per iteration", "default": 6, "type": int},
                {"name":"aggressiveness", "description": "Higher = more aggressive jumping. 1 would mean no jumping, 10 means zoom in to center 1/10th, etc.", "default": 5, "type": int},
                {"name":"wantedResolution", "description": "Final resolution - i.e. stopping criteria", "default": 0.5, "type": float},
                {"name":"waitTimeMs", "description": "Wait time in ms after each move", "default": 100, "type": float}
            ],
            "optional_kwargs": [
            ],
            "help_string": "",
            "display_name": "Iterative Auto-focus BF [Absolute Position]"
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------

from scipy import signal
import logging
def redondo_score(image):
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
    # logging.info(image)
    filtered_image = signal.convolve2d(image/np.max(image), kernel)
    score = (np.mean(filtered_image**2))
    return 1/score

def blur_laplace_score(image):
    import cv2
    blurrad = 3
    blurim = cv2.GaussianBlur(image, (blurrad,blurrad), 1)
    edgemap = cv2.Laplacian(blurim,  cv2.CV_64F)
    score = (np.mean(edgemap**2))
    return score

def volath_score(image):
    #From https://github.com/micro-manager/micro-manager/blob/8c618f091e271f9b7f73e4331bdf977e910afcf1/libraries/ImageProcessing/src/main/java/org/micromanager/imageprocessing/ImgSharpnessAnalysis.java
    #computeVolath function
    image = image/np.max(image)
    h, w = image.shape
    # Compute sum1 using vectorized operations
    sum1 = np.sum(image[:, 1:w-1] * image[:, 2:w])
    # Compute sum2 using vectorized operations
    sum2 = np.sum(image[:, :w-2] * image[:, 2:w])
    return 1/(sum1 - sum2)

from scipy.ndimage import convolve

def tenengrad_score(image):
    image = image/np.max(image)
    ken1 = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])
    ken2 = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]])

    image1 = image.copy()
    image2 = image.copy()

    filtered_image1 = signal.convolve2d(image/np.max(image), ken1)
    filtered_image2 = signal.convolve2d(image/np.max(image), ken2)
    # Perform the convolution using scipy's convolve function
    # proc1 = convolve(image1, ken1, mode='constant', cval=0.0)
    # proc2 = convolve(image2, ken2, mode='constant', cval=0.0)

    # Compute the inverse of sum of the squared values
    sum_val = 1/(np.sum(np.square(filtered_image1) + np.square(filtered_image2)))

    return sum_val

def testArray_report_sharpNess(core,position_array_test,zmovestage,waitTimeMs,method='Redondo',n_images=5):
    res_arr = []
    import time
    for n in range(len(position_array_test)):
        print(f"n: {n}, abs_pos_arr[n]: {position_array_test[n]}")
        core.set_position(zmovestage,position_array_test[n]) #type:ignore
        core.wait_for_system()
        time.sleep(waitTimeMs/1000)
        im = {}
        for i in range(n_images):
            core.snap_image()
            imraw = core.get_tagged_image()
            im[i] = imraw.pix.reshape((imraw.tags["Height"],imraw.tags["Width"]))
            time.sleep(waitTimeMs/1000)
        finalim = np.mean(list(im.values()), axis=0)
        #Store this im_ndarr as a .png:
        current_datetime = time.strftime("%Y%m%d_%H%M%S")
        # cv2.imwrite("C:/TEMP/test_im_"+current_datetime+".png",im_ndarr)
        res_arr.append(sharpnessScore_from_image(finalim,method = method))
        
    return res_arr

def single_sharpnessTest(core,position,zmovestage,waitTimeMs,method='Redondo',n_images=5):
    import time
    core.set_position(zmovestage,position) #type:ignore
    core.wait_for_system()
    time.sleep(waitTimeMs/1000)
    im = {}
    for i in range(n_images):
        core.snap_image()
        imraw = core.get_tagged_image()
        im[i] = imraw.pix.reshape((imraw.tags["Height"],imraw.tags["Width"]))
    finalim = np.mean(list(im.values()), axis=0)
    res = sharpnessScore_from_image(finalim,method = method)
    return res

def sharpnessScore_from_image(image,method='Redondo'):
    if method == 'Redondo':
        finalScore = redondo_score(image)
    elif method == 'Volath':
        finalScore =  volath_score(image)
    elif method == 'Tenengrad':
        finalScore = tenengrad_score(image)
    elif method == 'Laplacian':
        finalScore = blur_laplace_score(image)
    print(f"Sharpness score: {finalScore}")
    return finalScore

def auto_focus_iter_rel_bf(core,**kwargs):
    
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    
    #General idea: take images throughout z-stack of BF images, compuate the value/deriv, find the best, set position to that
    import time
    zmovestage = kwargs['StageName']#"TIPFSOffset"
    startp = float(kwargs['startPosition'])#-75 #relative wrt current position
    endp = float(kwargs['endPosition'])#75 #relative wrt current position
    waitTimeMs = float(kwargs['waitTimeMs'])#100
    final_offset = 0
    n_per_zoom = int(kwargs['n_positions']) #6
    aggressiveness = int(kwargs['aggressiveness']) # 5 - #higher = more aggressive jumping. 1 would mean no jumping, 10 means zoom in to center 1/10th, etc.
    aggressiveness = 1/aggressiveness
    wantedResolution = float(kwargs['wantedResolution']) #0.5
    
    core.set_exposure(float(kwargs['frame_time_ms']))
    #These two are hardcoded now.
    maxmaxiter = 10
    max_n_appending = 3
    
    #Get the current absolute position
    start_abs_pos = core.get_position(zmovestage)
    
    #Initialise some variables
    totalIter = 0
    resolutionTest = np.inf
    
    #Get the array of positions to test the resolution
    position_array_test = start_abs_pos+np.linspace(startp,endp,num=n_per_zoom)
    
    currentBestFoundPos = start_abs_pos
    
    #Continue doing all of this untill we're done or maxiter is hit
    import logging
    while resolutionTest > wantedResolution and totalIter < maxmaxiter:
        logging.debug(f"New full sharpness test with {(position_array_test)} positions, iter {totalIter}")
        #We test all of these positions
        sharpnessVal_arr = testArray_report_sharpNess(core,position_array_test,zmovestage,waitTimeMs,method=kwargs['Method'],n_images=int(kwargs['n_images']))
        
        #see if the argmax is at 0 or end and do up to 3 more:
        max_index = np.argmax(sharpnessVal_arr)
        while max_index == 0 or max_index == len(sharpnessVal_arr)-1:
            logging.debug(f"max index found at {max_index} for array {sharpnessVal_arr} with position array {position_array_test}")
            n_appending = 0
            if n_appending < max_n_appending:
                #If we are at the start, we measure another position at the start
                if max_index == 0 and position_array_test[0] > startp:
                    additional_position = position_array_test[0]-(position_array_test[1]-position_array_test[0])
                    logging.debug('Doing new position at start at '+str(additional_position))
                    newEntry = single_sharpnessTest(core,additional_position,zmovestage,waitTimeMs,method=kwargs['Method'],n_images=int(kwargs['n_images']))
                    sharpnessVal_arr = np.insert(sharpnessVal_arr,0,newEntry)
                    position_array_test = np.insert(position_array_test,0,additional_position)
                    max_index = np.argmax(sharpnessVal_arr)
                #If we are at the end, we measure another position at the end
                elif max_index == len(sharpnessVal_arr)-1 and position_array_test[-1] < endp:
                    additional_position = position_array_test[-1]+(position_array_test[-1]-position_array_test[-2])
                    logging.debug('Doing new position at end at '+str(additional_position))
                    newEntry = single_sharpnessTest(core,additional_position,zmovestage,waitTimeMs,method=kwargs['Method'],n_images=int(kwargs['n_images']))
                    sharpnessVal_arr = np.insert(sharpnessVal_arr,len(sharpnessVal_arr),newEntry)
                    position_array_test = np.insert(position_array_test,len(position_array_test),additional_position)
                    max_index = np.argmax(sharpnessVal_arr)
                n_appending += 1
            else:
                break
        
        #So now we have a good array
        #normalize
        sharpnessVal_arr_nrom = sharpnessVal_arr/np.max(sharpnessVal_arr)
        max_index = np.argmax(sharpnessVal_arr_nrom)
        logging.debug(f"final sharpnessVal_arr_nrom: {sharpnessVal_arr_nrom} at pos {position_array_test}")
        
        #determine the current resolution
        resolutionTest = position_array_test[1]-position_array_test[0]
        
        currentFinalPosArr = position_array_test
        currentFinalSharpnessArr = sharpnessVal_arr_nrom
        currentBestFoundPos = currentFinalPosArr[np.argmax(currentFinalSharpnessArr)]
        
        #Choose the new array:
        splitdiff = aggressiveness*(position_array_test[-1]-position_array_test[0])
        
        new_sharpnessVal_arr = np.linspace(position_array_test[max_index]-splitdiff,position_array_test[max_index]+splitdiff,num=n_per_zoom)
        
        position_array_test = new_sharpnessVal_arr
        
        totalIter += 1
    
    #Move to the final best position
    core.set_position(zmovestage,currentBestFoundPos)
    
    #Output nothing.
    output = {}
    
    return output

def auto_focus_iter_abs_bf(core,**kwargs):
    
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    
    #General idea: take images throughout z-stack of BF images, compuate the value/deriv, find the best, set position to that
    import time
    zmovestage = kwargs['StageName']#"TIPFSOffset"
    startp = float(kwargs['startPosition'])#-75 #ABSOLUTE
    endp = float(kwargs['endPosition'])#75 #ABSOLUTE
    waitTimeMs = float(kwargs['waitTimeMs'])#100
    final_offset = 0
    n_per_zoom = int(kwargs['n_positions']) #6
    aggressiveness = int(kwargs['aggressiveness']) # 5 - #higher = more aggressive jumping. 1 would mean no jumping, 10 means zoom in to center 1/10th, etc.
    aggressiveness = 1/aggressiveness
    wantedResolution = float(kwargs['wantedResolution']) #0.5
    
    core.set_exposure(float(kwargs['frame_time_ms']))
    #These two are hardcoded now.
    maxmaxiter = 10
    max_n_appending = 3
    
    #Get the current absolute position
    start_abs_pos = core.get_position(zmovestage)
    
    #Initialise some variables
    totalIter = 0
    resolutionTest = np.inf
    
    #Get the array of positions to test the resolution
    position_array_test = np.linspace(startp,endp,num=n_per_zoom)
    
    currentBestFoundPos = (endp-startp)/2
    
    #Continue doing all of this untill we're done or maxiter is hit
    import logging
    while resolutionTest > wantedResolution and totalIter < maxmaxiter:
        logging.debug(f"New full redondo test with {(position_array_test)} positions, iter {totalIter}")
        #We test all of these positions
        sharpnessVal_arr = testArray_report_sharpNess(core,position_array_test,zmovestage,waitTimeMs,method=kwargs['Method'],n_images=int(kwargs['n_images']))
        
        #see if the argmax is at 0 or end and do up to 3 more:
        max_index = np.argmax(sharpnessVal_arr)
        while max_index == 0 or max_index == len(sharpnessVal_arr)-1:
            logging.debug(f"max index found at {max_index} for array {sharpnessVal_arr} with position array {position_array_test}")
            n_appending = 0
            if n_appending < max_n_appending:
                #If we are at the start, we measure another position at the start
                if max_index == 0:
                    additional_position = position_array_test[0]-(position_array_test[1]-position_array_test[0])
                    logging.debug('Doing new position at start at '+str(additional_position))
                    newEntry = single_sharpnessTest(core,additional_position,zmovestage,waitTimeMs,method=kwargs['Method'],n_images=int(kwargs['n_images']))
                    sharpnessVal_arr = np.insert(sharpnessVal_arr,0,newEntry)
                    position_array_test = np.insert(position_array_test,0,additional_position)
                    max_index = np.argmax(sharpnessVal_arr)
                #If we are at the end, we measure another position at the end
                elif max_index == len(sharpnessVal_arr)-1:
                    additional_position = position_array_test[-1]+(position_array_test[-1]-position_array_test[-2])
                    logging.debug('Doing new position at end at '+str(additional_position))
                    newEntry = single_sharpnessTest(core,additional_position,zmovestage,waitTimeMs,method=kwargs['Method'],n_images=int(kwargs['n_images']))
                    sharpnessVal_arr = np.insert(sharpnessVal_arr,len(sharpnessVal_arr),newEntry)
                    position_array_test = np.insert(position_array_test,len(position_array_test),additional_position)
                    max_index = np.argmax(sharpnessVal_arr)
                n_appending += 1
            else:
                break
        
        #So now we have a good array
        #normalize
        sharpnessVal_arr_nrom = sharpnessVal_arr/np.max(sharpnessVal_arr)
        max_index = np.argmax(sharpnessVal_arr_nrom)
        logging.debug(f"final sharpnessVal_arr_nrom: {sharpnessVal_arr_nrom} at pos {position_array_test}")
        
        #determine the current resolution
        resolutionTest = position_array_test[1]-position_array_test[0]
        
        currentFinalPosArr = position_array_test
        currentFinalSharpnessArr = sharpnessVal_arr_nrom
        currentBestFoundPos = currentFinalPosArr[np.argmax(currentFinalSharpnessArr)]
        
        #Choose the new array:
        splitdiff = aggressiveness*(position_array_test[-1]-position_array_test[0])
        
        new_sharpnessVal_arr = np.linspace(position_array_test[max_index]-splitdiff,position_array_test[max_index]+splitdiff,num=n_per_zoom)
        
        if new_sharpnessVal_arr[0] < startp:
            addval = startp-new_sharpnessVal_arr[0]
            new_sharpnessVal_arr += addval
        elif new_sharpnessVal_arr[-1] > endp:
            addval = new_sharpnessVal_arr[-1]-endp
            new_sharpnessVal_arr += addval
        
        position_array_test = new_sharpnessVal_arr
        
        totalIter += 1
    
    #Move to the final best position
    core.set_position(zmovestage,currentBestFoundPos)
    
    #Output nothing.
    output = {}
    
    return output
