import os
import sys

#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import inspect
import logging

# from shapely import Polygon, affinity
# from shapely import Polygon, affinity
import math
import time
from pprint import pprint

import dask.array as da
import imageio
import numpy as np
# Load general dependencies
from imageio.v2 import imread
from scipy import signal
from scipy.ndimage import gaussian_filter
from skimage.feature.peak import peak_local_max

import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
from glados_pycromanager.autonomous.registry import register

def _patch_bioimageio_pydantic_compat():
    # bioimageio.spec 0.5.4.1 calls inspect_validator(func, mode) positionally,
    # but pydantic 2.12+ made `mode` keyword-only. Patch the module-local reference
    # so model loading works without forking the library.
    try:
        import bioimageio.spec._internal.field_warning as _fw
        from pydantic._internal._decorators import inspect_validator as _real_iv
        _sig = inspect.signature(_real_iv)
        if _sig.parameters.get('mode') and \
                _sig.parameters['mode'].kind == inspect.Parameter.KEYWORD_ONLY:
            def _compat_iv(func, mode=None, **kw):
                return _real_iv(func, mode=mode or 'after', type='field')
            _fw.inspect_validator = _compat_iv
    except Exception:
        pass

_patch_bioimageio_pydantic_compat()


def _patch_bioimageio_scale_linear_v04():
    # bioimageio.core 0.8 raises NotImplementedError for v0.4 ScaleLinear with axes.
    # For a single-char axis (e.g. 'c') we can map directly to an xarray dim.
    # For multi-char axes (e.g. 'xy') the gain is applied jointly (same scalar for all),
    # so we fold it to a scalar and drop the axis.
    try:
        import xarray as xr
        import numpy as np
        from bioimageio.core import proc_ops
        from bioimageio.spec.model import v0_4, v0_5
        from typing_extensions import assert_never

        original_from_proc_descr = proc_ops.ScaleLinear.from_proc_descr.__func__

        @classmethod  # type: ignore[misc]
        def _patched(cls, descr, member_id):
            kwargs = descr.kwargs
            if isinstance(kwargs, v0_5.ScaleLinearKwargs):
                axis = None
            elif isinstance(kwargs, v0_5.ScaleLinearAlongAxisKwargs):
                axis = kwargs.axis
            elif isinstance(kwargs, v0_4.ScaleLinearKwargs):
                axes = kwargs.axes  # e.g. 'c', 'xy', None
                if axes is None or len(axes) != 1:
                    axis = None  # multi-char means jointly scaled → treat as scalar
                else:
                    axis = axes   # single axis letter → per-element along that dim
            else:
                assert_never(kwargs)

            def _to_scalar(v):
                if isinstance(v, (float, int)):
                    return v
                arr = np.atleast_1d(v)
                return float(arr[0])  # jointly-applied: all values should be equal

            if axis:
                gain = xr.DataArray(np.atleast_1d(kwargs.gain), dims=axis)
                offset = xr.DataArray(np.atleast_1d(kwargs.offset), dims=axis)
            else:
                gain = _to_scalar(kwargs.gain)
                offset = _to_scalar(kwargs.offset)

            return cls(input=member_id, output=member_id, gain=gain, offset=offset)

        proc_ops.ScaleLinear.from_proc_descr = _patched
    except Exception:
        pass

_patch_bioimageio_scale_linear_v04()


def _patch_bioimageio_load_state_dict():
    # Some model architecture files (e.g. PredictorAdaptor in affable-shark) define
    # load_state_dict() without a `strict` keyword argument, which bioimageio.core
    # now passes explicitly.  We pre-shim the model's load_state_dict before the
    # single weights-file read so we never have to re-open the file on retry.
    try:
        from bioimageio.core.backends import pytorch_backend

        original = pytorch_backend.load_torch_state_dict

        def _patched(model, path, devices, strict=True):
            _orig_lsd = model.load_state_dict
            needs_shim = False
            try:
                sig = inspect.signature(_orig_lsd)
                needs_shim = 'strict' not in sig.parameters
            except (ValueError, TypeError):
                pass
            if needs_shim:
                model.load_state_dict = lambda state, strict=True, **_kw: _orig_lsd(state)
            try:
                return original(model, path, devices, strict=strict)
            finally:
                if needs_shim:
                    model.load_state_dict = _orig_lsd

        pytorch_backend.load_torch_state_dict = _patched
    except Exception:
        pass

_patch_bioimageio_load_state_dict()


# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "BioImageModelZoo": {
            "required_kwargs": [
                {"name": "model_id", "description": "ID of the Model", "default": "affable-shark", "type": str}
            ],
            "optional_kwargs": [
                {"name": "imageLayerId", "description": "model layer id", "default": 0, "type": int}
            ],
            "help_string": "phasor-based SMLM.",
            "display_name": "BioImage Model Zoo",
            "run_delay": 200,
            "visualise_delay": 200,
            "visualisation_type": "image", #'image', 'points', 'value', or 'shapes'
            "input":[
            ],
            "output":[
            ],
        }
    }




def _model_spatial_constraints(model, min_fallback=64, step_fallback=256):
    """Return (min_h, min_w, step) from the model's input axis size constraints."""
    min_hw = min_fallback
    step = step_fallback
    try:
        inp = model.inputs[0]
        axes = _bmz_field(inp, 'axes') or []
        for ax in axes:
            ax_type = _bmz_field(ax, 'type') or _bmz_field(ax, 'id') or ''
            if ax_type not in ('space', 'x', 'y'):
                continue
            size = _bmz_field(ax, 'size') or {}
            if isinstance(size, dict):
                ax_min = _bmz_field(size, 'min')
                ax_step = _bmz_field(size, 'step')
                if ax_min is not None:
                    min_hw = max(min_hw, int(ax_min))
                if ax_step is not None and int(ax_step) > 1:
                    step = max(step, int(ax_step))
    except Exception:
        pass
    return min_hw, min_hw, step


def _model_min_spatial_size(model, fallback=64):
    """Return the minimum (height, width) that satisfies the model's input size constraints."""
    try:
        inp = model.inputs[0]
        axes = _bmz_field(inp, 'axes') or []
        min_h = min_w = fallback
        for ax in axes:
            ax_type = _bmz_field(ax, 'type') or _bmz_field(ax, 'id') or ''
            if ax_type not in ('space', 'x', 'y'):
                continue
            size = _bmz_field(ax, 'size') or {}
            ax_min = _bmz_field(size, 'min') if isinstance(size, dict) else None
            if ax_min is not None:
                min_h = min_w = max(min_h, int(ax_min))
        return min_h, min_w
    except Exception:
        return fallback, fallback


def getModel(model_id="",model_doi="",model_url=""):
    from bioimageio.core import load_description
    if model_id != "":
        model = load_description(model_id)
    elif model_doi != "":
        model = load_description(model_doi)
    elif model_url != "":
        model = load_description(model_url)
    else:
        logging.warning("Please specify a model ID, DOI or URL")
    return model

def getOutputImages(prediction,modelSample):
    
    if tuple(sorted(prediction.members[modelSample['model_tensor_outputName']].data.dims)) == tuple(sorted(('batch','channel','y','x'))):
        outputImages = prediction.members[modelSample['model_tensor_outputName']].data.transpose('batch','channel','x','y').data
    elif tuple(sorted(prediction.members[modelSample['model_tensor_outputName']].data.dims)) == tuple(sorted(('batch','y','x','channel'))):
        outputImages = prediction.members[modelSample['model_tensor_outputName']].data.transpose('b','c','x','y').data
    elif tuple(sorted(prediction.members[modelSample['model_tensor_outputName']].data.dims)) == tuple(sorted(('batch','y','x','channel','object'))):
        outputImages = prediction.members[modelSample['model_tensor_outputName']].data.transpose('batch','channel','x','y','object').data
        #delete final axis:
        outputImages = np.squeeze(outputImages,axis=4)
    return outputImages

def _bmz_field(obj, key, default=None):
    """Get a field from a bioimageio descriptor that may be a dict or object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

# Maps full bioimageio axis names to the single-char shorthand used internally.
_AXIS_SHORT = {'batch': 'b', 'channel': 'c', 'x': 'x', 'y': 'y', 'z': 'z', 'time': 't',
               'b': 'b', 'c': 'c', 't': 't'}

def _axis_id(axis):
    """Return the id string for an axis that may be a str, dict, or object."""
    if isinstance(axis, str):
        return axis
    if isinstance(axis, dict):
        return axis.get('id') or axis.get('type', '')
    return getattr(axis, 'id', getattr(axis, 'type', ''))

def setupSample(model=None,input_image=None):
    from bioimageio.core import Tensor
    from bioimageio.core.digest_spec import create_sample_for_model
    if model == None:
        logging.warning("Model input required!")
        return
    if type(input_image) == type(None):
        logging.warning("Input image required!")
        return
    inp0 = model.inputs[0]
    out0 = model.outputs[0]
    if _bmz_field(inp0, 'name') is not None:
        model_tensor_inputName = _bmz_field(inp0, 'name')
        model_tensor_outputName = _bmz_field(out0, 'name')
    elif _bmz_field(inp0, 'id') is not None:
        model_tensor_inputName = _bmz_field(inp0, 'id')
        model_tensor_outputName = _bmz_field(out0, 'id')

    raw_axes_objs = _bmz_field(inp0, 'axes')
    # Build shorthand string (e.g. 'bcyx') and full axis-name list for Tensor.from_numpy
    if isinstance(raw_axes_objs, str):
        shapev = raw_axes_objs
        full_axis_names = list(raw_axes_objs)
    else:
        full_axis_names = [_axis_id(a) for a in raw_axes_objs]
        shapev = ''.join(_AXIS_SHORT.get(a, '') for a in full_axis_names)

    # Expand 2D input (H, W) with singleton dims for any non-spatial axes
    # that the model expects.  Process in descending position so earlier
    # insertions don't shift later indices.
    non_spatial = [(i, c) for i, c in enumerate(shapev) if c not in ('x', 'y')]
    for idx, _ in sorted(non_spatial, key=lambda t: t[0], reverse=True):
        if idx < 2:
            input_image = input_image[np.newaxis, :, :]
        else:
            input_image = input_image[:, :, np.newaxis]
    logging.debug("array shape: %s", input_image.shape)

    # If the model expects 3 input channels and we gave 1, repeat it.
    c_idx_in_shapev = shapev.find('c')
    if c_idx_in_shapev != -1 and input_image.shape[c_idx_in_shapev] == 1:
        inp0_axes = raw_axes_objs if not isinstance(raw_axes_objs, str) else []
        for ax in (inp0_axes if not isinstance(inp0_axes, str) else []):
            ax_id = _axis_id(ax)
            if ax_id in ('c', 'channel'):
                ch_names = _bmz_field(ax, 'channel_names') or []
                if len(ch_names) == 3:
                    input_image = np.repeat(input_image, 3, axis=c_idx_in_shapev)
                    logging.debug("Expanded to 3 channels: %s", input_image.shape)
                break

    dims = full_axis_names
    test_input_tensor = Tensor.from_numpy(input_image, dims=dims)

    sample=create_sample_for_model(
        model=model, inputs={model_tensor_inputName:test_input_tensor}, sample_id="my_demo_sample"
    )
    
    df={}
    df['sample'] = sample
    df['model_tensor_inputName'] = model_tensor_inputName
    df['model_tensor_outputName'] = model_tensor_outputName
    
    return df

# BMZ_MODEL_ID = affable-shark# "discreet-rooster"#"hiding-tiger"#
# BMZ_MODEL_DOI = ""#"10.5281/zenodo.6287342"
# BMZ_MODEL_URL = ""#"https://uk1s3.embassy.ebi.ac.uk/public-datasets/bioimage.io/affable-shark/draft/files/rdf.yaml"

# input_image = imageio.imread('C:\\Users\\kjamartens\\Documents\\Github\\ScopeGUI\\glados-pycromanager\\glados_pycromanager\\testIm_bioimageModel.png')



#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
@register("BioImageModelZoo.BioImageModelZoo")
class BioImageModelZoo:
    def __init__(self,core,**kwargs):
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        #Initialise it all
        self.outputImage = []
        self.modelId = kwargs['model_id']
        self.imageLayerId = int(kwargs['imageLayerId'])
        logging.info("Loading bioimageio for BioImageModelZoo (first use — may take a few seconds)…")
        from bioimageio.core import create_prediction_pipeline
        self.model = getModel(model_id=self.modelId)
        _h, _w, self._step = _model_spatial_constraints(self.model)
        self.modelSample = setupSample(model=self.model, input_image=np.zeros((_h, _w)))
        # torchscript is self-contained (no custom architecture imports needed).
        # Try it first; if the model has no torchscript weights fall through to
        # bioimageio's auto-selection, which will surface the real error.
        try:
            self.prediction_pipeline = create_prediction_pipeline(
                self.model, devices=None, weight_format='torchscript'
            )
        except Exception:
            self.prediction_pipeline = create_prediction_pipeline(
                self.model, devices=None, weight_format=None
            )

        return None

    def run(self,image,metadata,shared_data,core,**kwargs):
        logging.info('Attempting bioimagemodelzoo Run')

        self.lastImage = image
        orig_h, orig_w = image.shape[:2]
        step = getattr(self, '_step', 256)
        new_h = ((orig_h + step - 1) // step) * step
        new_w = ((orig_w + step - 1) // step) * step
        if new_h != orig_h or new_w != orig_w:
            image = np.pad(image, ((0, new_h - orig_h), (0, new_w - orig_w)), mode='reflect')
        self.modelSample = setupSample(model=self.model,input_image=image)
        #Finally, predict
        prediction = self.prediction_pipeline.predict_sample_without_blocking(self.modelSample['sample'])

        #Get the output images
        self.outputImage = getOutputImages(prediction,self.modelSample)
        # Crop back to original spatial size if we padded
        if self.outputImage is not None and (new_h != orig_h or new_w != orig_w):
            self.outputImage = self.outputImage[..., :orig_h, :orig_w]

    def end(self,core,**kwargs):
        return
    
    def visualise_init(self): 
        logging.debug("Visualise_init")
        layerName = 'BioImageModelZoo'
        layerType = 'image' #layerType has to be from image|labels|points|shapes|surface|tracks|vectors
        self.firstLayerInit = True
        return layerName,layerType
    
    def visualise(self,image,metadata,core,napariLayer,**kwargs):
        try:
            napariLayer.data = self.outputImage[0,self.imageLayerId,:,:]
        except (AttributeError, RuntimeError, IndexError, TypeError) as exc:
            logging.info('Issue with bioimagemodelzoo layer update: %s', exc)
        return napariLayer