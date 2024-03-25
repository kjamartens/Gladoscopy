
import shutil
import os
import logging

def cleanUpTemporaryFiles(mainFolder='./'):
    logging.info('Cleaning up temporary files')
    for folder in os.listdir(os.path.join(mainFolder,'temp')):
        if 'LiveAcqShouldBeRemoved' in folder:
            try:
                shutil.rmtree(os.path.join(os.path.join(folder,'temp'), folder))
            except:
                pass