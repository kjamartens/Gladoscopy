import os
import pytest
from pycromanager import Acquisition, Core, multi_d_acquisition_events
import napari
import time
import numpy as np
import asyncio
import threading
import time
import os
import sys
import time
from skimage.io.collection import alphanumeric_key
from dask import delayed
import dask.array as da
from tifffile import imread
import napari
from napari.qt import thread_worker

#Pycromanager
core = Core()
#Napari start
viewer = napari.Viewer()

def append(delayed_image):
    print('Update')
    if delayed_image is None:
        return

    if viewer.layers:
        # layer is present, replace its data
        layer = viewer.layers[0]
        # image_shape = layer.data.shape[1:]
        # image_dtype = layer.data.dtype
        layer.data = delayed_image#da.concatenate((layer.data, delayed_image), axis=2)
    else:
        layer = viewer.add_image(delayed_image, rendering='attenuated_mip')

    # we want to show the last file added in the viewer to do so we want to
    # put the slider at the very end. But, sometimes when user is scrolling
    # through the previous slide then it is annoying to jump to last
    # stack as it gets added. To avoid that jump we 1st check where
    # the scroll is and if its not at the last slide then don't move the slider.
    if viewer.dims.point[0] >= layer.data.shape[0] - 2:
        viewer.dims.set_point(0, layer.data.shape[0] - 1)


# Create a function to generate random images
def generate_random_image():
    print('GRI')
    time.sleep(1)
    return np.random.rand(256, 256)  # Generating a random 256x256 pixel image

@thread_worker(connect={'yielded': append})
def watch_path():
    while True:
        core.snap_image()
        tagged_image = core.get_tagged_image()
        # get the pixels in numpy array and reshape it according to its height and width
        image_array = np.reshape(
            tagged_image.pix,
            newshape=[-1, tagged_image.tags["Height"], tagged_image.tags["Width"]],
        )
        # for display, we can scale the image into the range of 0~255
        image_array = (image_array / image_array.max() * 255).astype("uint8")
        yield image_array[0,:,:]


worker = watch_path()
napari.run()

# #Start napari
# viewer = napari.Viewer()

# for i in range(10):
#     print(i)
#     core.snap_image()
#     tagged_image = core.get_tagged_image()
#     # get the pixels in numpy array and reshape it according to its height and width
#     image_array = np.reshape(
#         tagged_image.pix,
#         newshape=[-1, tagged_image.tags["Height"], tagged_image.tags["Width"]],
#     )
#     # for display, we can scale the image into the range of 0~255
#     image_array = (image_array / image_array.max() * 255).astype("uint8")
#     im = image_array[0,:,:]
#     new_layer = viewer.add_image(im)
#     viewer.show()
#     time.sleep(1)

# napari.run()