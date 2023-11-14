from pycromanager import Core
import os
import json
import sys
from PyQt5.QtWidgets import QApplication
import shutil
import logging
import argparse

from napariGlados import runNapariPycroManager
from sharedFunctions import Shared_data, periodicallyUpdate

def perform_post_closing_actions():
    #If it's closed, delete the folder for temp live images
    folder_path = "TempAcq_removeFolder"
    shutil.rmtree(folder_path)

def main():
    #Create parser
    parser = argparse.ArgumentParser(description='Glados-PycroManager-Napari: an interface for autonomous microscopy via PycroManager')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug')
    args=parser.parse_args()
    
    if args.debug:
        log_format = "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
        logging.basicConfig(format=log_format, level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Create an instance of the shared_data class
    shared_data = Shared_data()
        
    # get object representing MMCore, used throughout
    core = Core()
    shared_data.core = core

    #Open JSON file with MM settings
    with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
        MM_JSON = json.load(f)

    #Run the live mode UI
    nPM = runNapariPycroManager(core,MM_JSON,shared_data)

    #Periodically update the MM info of the MMcontrolsWidget
    global MM_update_instance
    MM_update_instance = periodicallyUpdate(updateFunction=nPM['MMcontrolWidget'].updateAllMMinfo)

    #Ensure it stays open
    app = QApplication([])
    # app.aboutToQuit.connect(perform_post_closing_actions)
    sys.exit(app.exec_())

if __name__ == "__main__":
    try:
        main()
    except:
        print('Error!')

