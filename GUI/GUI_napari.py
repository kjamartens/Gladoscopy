from pycromanager import Core
from pycromanager import start_headless, stop_headless
import os
import json
import sys
from PyQt5.QtWidgets import QApplication
import shutil
import logging
import argparse

from napariGlados import runNapariPycroManager
from sharedFunctions import Shared_data, periodicallyUpdate
from utils import *

def perform_post_closing_actions(shared_data):
    """Performing closing actions

    Args:
        shared_data: shared_data class (Shared_data())
    """
    #Clean up temporary files
    cleanUpTemporaryFiles()
    
    if shared_data._headless:
        stop_headless()
        
    
    # #If it's closed, delete the folder for temp live images
    # folder_path = "TempAcq_removeFolder"
    # shutil.rmtree(folder_path)

def main():
    #Create parser
    parser = argparse.ArgumentParser(description='Glados-PycroManager-Napari: an interface for autonomous microscopy via PycroManager')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug')
    args=parser.parse_args()
    
    cleanUpTemporaryFiles()
    
    if args.debug:
        log_format = "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
        logging.basicConfig(format=log_format, level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Create an instance of the shared_data class
    shared_data = Shared_data()
        
    # get object representing MMCore, used throughout
    #try to open a running instance:
    try:
        core = Core()
        shared_data.core = core
        shared_data._headless = False
    except:
        #else, create a new headless instance:
        print('Starting headless MM')
        start_headless(mm_app_path= "C:\\Program Files\\Micro-Manager-2.0gamma\\", config_file="C:\\Users\\SMIPC2\\Desktop\s\MM-config\\MMconfig_20240103c.cfg", python_backend=False, buffer_size_mb=2048, max_memory_mb=10000)
        shared_data._headless = True
        print('headless MM started')
        core = Core()
        shared_data.core = core

    #Open JSON file with MM settings
    with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
        MM_JSON = json.load(f)

    #Run the live mode UI
    nPM = runNapariPycroManager(core,MM_JSON,shared_data)

    #Periodically update the MM info of the MMcontrolsWidget
    global MM_update_instance
    # MM_update_instance = periodicallyUpdate(updateFunction=nPM['MMcontrolWidget'].updateAllMMinfo)

    #Ensure it stays open
    app = QApplication([])
    app.aboutToQuit.connect(lambda: perform_post_closing_actions(shared_data))
    sys.exit(app.exec_())

if __name__ == "__main__":
    try:
        main()
    except:
        print('Error!')

