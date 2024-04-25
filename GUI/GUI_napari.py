from pycromanager import Core
from pycromanager import start_headless
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

from PyQt5.QtCore import QThread, QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow
import sys
# Add the folder 2 folders up to the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#Import all scripts in the custom script folders
from Analysis_Images import * #type: ignore
from Analysis_Measurements import * #type: ignore
from Analysis_Shapes import * #type: ignore
from Scoring_Images import * #type: ignore
from Scoring_Measurements import * #type: ignore
from Scoring_Shapes import * #type: ignore
from Scoring_Images_Measurements import * #type: ignore
from Scoring_Measurements_Shapes import * #type: ignore
from Scoring_Images_Measurements_Shapes import * #type: ignore
from Visualisation_Images import * #type: ignore
from Visualisation_Measurements import * #type: ignore
from Visualisation_Shapes import * #type: ignore
#Obtain the helperfunctions
import HelperFunctions #type: ignore


def perform_post_closing_actions(shared_data):
    """Performing closing actions

    Args:
        shared_data: shared_data class (Shared_data())
    """
    #Clean up temporary files
    cleanUpTemporaryFiles()
    
    # if shared_data._headless:
    #     stop_headless()

class Worker(QObject):
    finished = pyqtSignal()

    def runNapariPycroManagerWrap(self, core, MM_JSON, shared_data):
        # Your code for running the NapariPycroManager function goes here
        runNapariPycroManager(core, MM_JSON, shared_data)
        self.finished.emit()

def main():
    #Create parser
    parser = argparse.ArgumentParser(description='Glados-PycroManager-Napari: an interface for autonomous microscopy via PycroManager')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug')
    args=parser.parse_args()
    
    cleanUpTemporaryFiles()
    
    #Set up logging at correct level
    log_file_path = 'logpath.txt'
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if args.debug else logging.INFO)

    # Create the file handler to log to the file
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.INFO)

    # Create the stream handler to log to the debug terminal
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.DEBUG if args.debug else logging.INFO)

    # Add the handlers to the logger
    logging.basicConfig(handlers=[file_handler, stream_handler], level=logging.DEBUG if args.debug else logging.INFO,format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s")
    
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
        start_headless(mm_app_path= "C:\\Program Files\\Micro-Manager-2.0gamma\\", config_file="C:\\Users\\SMIPC2\\Desktop\\MM-config\\MMconfig_20240103c.cfg", python_backend=False, buffer_size_mb=2048, max_memory_mb=10000)
        shared_data._headless = True
        print('headless MM started')
        core = Core()
        shared_data.core = core

    #Open JSON file with MM settings
    with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
        MM_JSON = json.load(f)

    #Run the UI on a second thread (hopefully robustly)
    app = QApplication(sys.argv)

    worker = Worker()
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(lambda: worker.runNapariPycroManagerWrap(core, MM_JSON, shared_data))
    thread.start()
    
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    sys.exit(app.exec_())

    #Run the UI
    # import threading
    # thread = threading.Thread(target=runNapariPycroManager, args=(core, MM_JSON, shared_data))
    # thread.start()
    # # nPM = runNapariPycroManager(core,MM_JSON,shared_data)

    # #Periodically update the MM info of the MMcontrolsWidget
    # global MM_update_instance
    # # MM_update_instance = periodicallyUpdate(updateFunction=nPM['MMcontrolWidget'].updateAllMMinfo)

    # #Ensure it stays open
    # app = QApplication([])
    # app.aboutToQuit.connect(lambda: perform_post_closing_actions(shared_data))
    # sys.exit(app.exec_())

if __name__ == "__main__":
    try:
        main()
    except:
        print('Error!')

