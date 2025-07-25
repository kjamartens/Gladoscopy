
def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
else:
    from MainScripts import FunctionHandling
# from shapely import Polygon, affinity
import math
import numpy as np
import inspect
import dask.array as da
import ndtiff

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "set_strobo_lasers": {
            "input":[
            ],
            "output":[
            ],
            "required_kwargs": [
                {"name": "pulse_len_405", "description": "Pulse length (us) of 405 nm laser",  "default": 0, "type": int, "display_text": "405 nm - Pulse length (μs)"},
                {"name": "pulse_delay_405", "description": "Pulse delay (us) of 405 nm laser",  "default": 1, "type": int, "display_text": "405 nm - Pulse delay (μs)"},
                {"name": "pulse_frames_405", "description": "Pulse frames of 405 nm laser",  "default": 1, "type": int, "display_text": "405 nm - Which frames on?"},
                {"name": "power_pct_405", "description": "Power of 405 nm laser (%)",  "default": 100, "type": float, "display_text": "405 nm - Laser power (%)"},
                {"name": "pulse_len_488", "description": "Pulse length (us) of 488 nm laser",  "default": 0, "type": int, "display_text": "488 nm - Pulse length (μs)"},
                {"name": "pulse_delay_488", "description": "Pulse delay (us) of 488 nm laser",  "default": 1, "type": int, "display_text": "488 nm - Pulse delay (μs)"},
                {"name": "pulse_frames_488", "description": "Pulse frames of 488 nm laser",  "default": 1, "type": int, "display_text": "488 nm - Which frames on?"},
                {"name": "power_pct_488", "description": "Power of 488 nm laser (%)",  "default": 100, "type": float, "display_text": "488 nm - Laser power (%)"},
                {"name": "pulse_len_561", "description": "Pulse length (us) of 561 nm laser",  "default": 0, "type": int, "display_text": "561 nm - Pulse length (μs)"},
                {"name": "pulse_delay_561", "description": "Pulse delay (us) of 561 nm laser",  "default": 1, "type": int, "display_text": "561 nm - Pulse delay (μs)"},
                {"name": "pulse_frames_561", "description": "Pulse frames of 561 nm laser",  "default": 1, "type": int, "display_text": "561 nm - Which frames on?"},
                {"name": "power_pct_561", "description": "Power of 561 nm laser (%)",  "default": 100, "type": float, "display_text": "561 nm - Laser power (%)"},
                {"name": "pulse_len_638", "description": "Pulse length (us) of 638 nm laser",  "default": 0, "type": int, "display_text": "638 nm - Pulse length (μs)"},
                {"name": "pulse_delay_638", "description": "Pulse delay (us) of 638 nm laser",  "default": 1, "type": int, "display_text": "638 nm - Pulse delay (μs)"},
                {"name": "pulse_frames_638", "description": "Pulse frames of 638 nm laser",  "default": 1, "type": int, "display_text": "638 nm - Which frames on?"},
                {"name": "power_pct_638", "description": "Power of 638 nm laser (%)",  "default": 100, "type": float, "display_text": "638 nm - Laser power (%)"},
                {"name": "pulse_len_750", "description": "Pulse length (us) of 750 nm laser",  "default": 0, "type": int, "display_text": "750 nm - Pulse length (μs)"},
                {"name": "pulse_delay_750", "description": "Pulse delay (us) of 750 nm laser",  "default": 1, "type": int, "display_text": "750 nm - Pulse delay (μs)"},
                {"name": "pulse_frames_750", "description": "Pulse frames of 750 nm laser",  "default": 1, "type": int, "display_text": "750 nm - Which frames on?"},
                {"name": "power_pct_750", "description": "Power of 750 nm laser (%)",  "default": 100, "type": float, "display_text": "750 nm - Laser power (%)"},
            ],
            "optional_kwargs": [
            ],
            "help_string": "",
            "display_name": "Set stroboscopic lasers"
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------

def set_strobo_lasers(core,**kwargs):
    import time
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    printStatements = True

    #Transform kwargs to integers/floats
    pulse_len_405 = int(kwargs['pulse_len_405'])
    pulse_len_488 = int(kwargs['pulse_len_488'])
    pulse_len_561 = int(kwargs['pulse_len_561'])
    pulse_len_638 = int(kwargs['pulse_len_638'])
    pulse_len_750 = int(kwargs['pulse_len_750'])
    pulse_delay_405 = int(kwargs['pulse_delay_405'])
    pulse_delay_488 = int(kwargs['pulse_delay_488'])
    pulse_delay_561 = int(kwargs['pulse_delay_561'])
    pulse_delay_638 = int(kwargs['pulse_delay_638'])
    pulse_delay_750 = int(kwargs['pulse_delay_750'])
    pulse_frames_405 = int(kwargs['pulse_frames_405'])
    pulse_frames_488 = int(kwargs['pulse_frames_488'])
    pulse_frames_561 = int(kwargs['pulse_frames_561'])
    pulse_frames_638 = int(kwargs['pulse_frames_638'])
    pulse_frames_750 = int(kwargs['pulse_frames_750'])
    power_pct_405 = float(kwargs['power_pct_405'])
    power_pct_488 = float(kwargs['power_pct_488'])
    power_pct_561 = float(kwargs['power_pct_561'])
    power_pct_638 = float(kwargs['power_pct_638'])
    power_pct_750 = float(kwargs['power_pct_750'])
    
    def TS_Response_verbose():
        core.get_property('TriggerScopeMM-Hub', 'Serial Receive');
        print(core.get_property('TriggerScopeMM-Hub', 'Serial Receive'));
    
    wavelength_arr = [405,488,561,638,750]
    #Loop over each of the laser IDs:
    for laser_id in range(0,5):
        wavelength = wavelength_arr[laser_id]
        pulse_len = eval('pulse_len_'+str(wavelength))
        pulse_delay = eval('pulse_delay_'+str(wavelength))
        pulse_frames = eval('pulse_frames_'+str(wavelength))
        power_pct = eval('power_pct_'+str(wavelength))
        
        
        #Loop over number of frames after which it repeats
        if printStatements: print('PAC'+str(laser_id+1))
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAC'+str(laser_id+1))
        TS_Response_verbose();

        for k in range(0,pulse_frames): #type:ignore
            if k == 0:
                if pulse_len>0: #type:ignore
                    power_level = 65535*0.01*power_pct
                    if laser_id == 2: #Exception for the 561 laser:
                        if printStatements: print('Power level exception for 561 laser succes')
                        power_level = 65535*0.01*power_pct*(12/100)
                    if printStatements: print('PAO'+str(laser_id+1)+'-0-' + str(round(power_level)))
                    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(laser_id+1)+'-0-' + str(round(power_level)))
                    TS_Response_verbose();
                else:
                    if printStatements: print('PAO'+str(laser_id+1)+'-0-' + str(round(0)))
                    core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(laser_id+1)+'-0-' + str(round(0)))
                    TS_Response_verbose();
            else:
                time.sleep(0.1)
                if printStatements: print('PAO'+str(laser_id+1)+'-0-' + str(round(0)))
                core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAO'+str(laser_id+1)+'-'+str(k)+'-0')
                TS_Response_verbose();

            if printStatements: print('PAS'+str(laser_id+1)+'-1-1')
            core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'PAS'+str(laser_id+1)+'-1-1')
            TS_Response_verbose();

        if printStatements: print('BAD'+str(laser_id+1)+'-'+str(pulse_delay))
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAD'+str(laser_id+1)+'-'+str(pulse_delay)) 
        TS_Response_verbose();
        if printStatements: print('BAL'+str(laser_id+1)+'-'+str(pulse_len))
        core.set_property('TriggerScopeMM-Hub', 'Serial Send', 'BAL'+str(laser_id+1)+'-'+str(pulse_len)) 
        TS_Response_verbose();
    
    
    
    #Output nothing.
    output = {}
    
    return output