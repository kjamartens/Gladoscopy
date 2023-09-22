from pycromanager import *
import time

global core
core = Core()
   
for i in range(10):
    start = time.time()
    core.snap_image()
    mid = time.time()
    tagIm = core.get_tagged_image()
    end = time.time()
    print('{}\t\t{}'.format(end - mid, mid - start))