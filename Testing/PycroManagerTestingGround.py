from pycromanager import *
from imjoy import api
from matplotlib import pyplot as plt
import numpy as np

# get object representing MMCore, used throughout
core = Core()

print(core)

def snap_image():
    print('Snapping image')
    # acquire an image and display it
    core.snap_image()
    tagged_image = core.get_tagged_image()
    # get the pixels in numpy array and reshape it according to its height and width
    image_array = np.reshape(
        tagged_image.pix,
        newshape=[-1, tagged_image.tags["Height"], tagged_image.tags["Width"]],
    )
    # for display, we can scale the image into the range of 0~255
    image_array = (image_array / image_array.max() * 255).astype("uint8")
    # return the first channel if multiple exists
    return image_array[0, :, :]

class ImJoyPlugin:
    """Defines an ImJoy plugin"""
    async def setup(self):
        """for initialization"""
        pass
    async def run(self, ctx):
        """called when the user run this plugin"""
        # show a popup message
        await api.alert("hello world")

# register the plugin to the imjoy core
api.export(ImJoyPlugin())

# plt.imshow(snap_image())
# plt.show()