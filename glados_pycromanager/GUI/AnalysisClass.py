"""
Handles the GUI display of Glados-pycromanager, as well as the structure for analysis (normal and real-time) to run on secondary threads.
"""

import cProfile
import io
import json
import logging
import multiprocessing as mp
import os
import pickle
import pstats
import queue as std_queue
import sys
import time
from collections import deque
from threading import Event, get_native_id
from typing import List, Tuple, Union

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import glados_pycromanager.Core.microscopeInterfaceLayer as MIL
import glados_pycromanager.GUI.utils as utils


#Class for overlays and their update and such
class napariOverlay:
    def __init__(self,napariViewer,layer_name:str | None='new Layer',colormap='gray',opacity=1,visible=True,blending='translucent',layerType = None,RT_analysisObject=None):
        """
        Initializes an instance of the class with the specified `napariViewer` and `layer_name`.

        Args:
            napariViewer (napari.Viewer): The napari viewer object.
            layer_name (Union[str, None], optional): The name of the layer. Defaults to 'new Layer'.
            colormap (str, optional): The colormap to use. Defaults to 'gray'.
            opacity (float, optional): The opacity of the layer. Defaults to 1.
            visible (bool, optional): Whether the layer is visible. Defaults to True.
            blending (str, optional): The blending mode. Defaults to 'opaque', options are {'opaque', 'translucent', and 'additive'}

        Returns:
            None
        """
        self.napariViewer = napariViewer
        self.layer_name = layer_name
        self.colormap = colormap
        self.opacity = opacity
        self.visible = visible
        self.blending = blending
        self.RT_analysisObject = RT_analysisObject
        self.layerType = layerType
        try:
            self.layer_scale = napariViewer.layers[0].scale
        except (AttributeError, IndexError, TypeError):
            self.layer_scale = [1,1]
        
        #Get info from a RT analysis object (i.e. outside-based-analysis)
        if self.RT_analysisObject is not None:
            self.layer_name, self.layerType = self.RT_analysisObject.visualise_init()
            logging.debug(f"#nO - Initialised napariOverlay with layer_name: {self.layer_name}, layerType: {self.layerType}")
            
        #Create the layer if layer_name is not none
        #layer_name is None if we only want to instantialise the napariOverlay but not get any shape
        if self.layer_name is not None:
            if self.layerType is not None:
                
                #check if a layer with this name already exists:
                if self.layer_name in napariViewer.layers:
                    self.layer = napariViewer.layers[self.layer_name]
                        
                else: #else create the layer
                    if self.layerType == 'image':
                        self.layer = napariViewer.add_image(np.zeros((32,32)),name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'labels':
                        self.layer = napariViewer.add_labels([],name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'points':
                        self.layer = napariViewer.add_points(name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'shapes':
                        self.layer = napariViewer.add_shapes(name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'surface':
                        self.layer = napariViewer.add_surface([],name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'tracks':
                        self.layer = napariViewer.add_tracks([],name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'vectors':
                        self.layer = napariViewer.add_vectors(name=self.layer_name,scale=self.layer_scale)
            else: #Fallback if no layer type is specified at all
                self.layer = napariViewer.add_shapes(name=self.layer_name,scale=self.layer_scale)
        
            logging.debug(f"Using layer {self.layer}")
        
    #Update the name of the overlay
    def changeName(self,new_name):
        """
        Change the name of the napariOverlay

        Args:
            new_name (str): The new name for the napariOverlay.

        Returns:
            None
        """
        self.layer_name = new_name
        self.layer.name = self.layer_name
        #Return the layer
        
    def getLayer(self):
        """
        Returns the layer attribute of the object.

        Args:
            None

        Returns:
            layer (object or None): The layer attribute of the object if it exists, None otherwise.
        """
        if hasattr(self, 'layer'):
            return self.layer
        else:
            return None
        
    #Initialise drawing a text overly (single string of text)
    def drawTextOverlay_init(self):
        """
        Initializes the text overlay for drawing text on the napari viewer.

        Args:
            None
        
        Returns:
            None
        """
        polygons = [np.array([[0, 0], [0, 1], [1, 1], [1, 0]])]
        # create properties
        properties = {'value': [0]}
        text_properties = {'text': '{value:0.1f}','anchor': 'upper_left','translation': [-5, 0],'size': 8,'color': 'green',}
        #Remove old layer
        napariViewer.layers.remove(self.layer)
        # new layer with polygons and text
        self.layer = napariViewer.add_shapes(polygons,properties=properties,shape_type='polygon',edge_color='transparent',face_color='transparent',text=text_properties,name=self.layer_name,scale=self.layer_scale,opacity = self.opacity,visible=self.visible)
    
    #Update routine for drawing a text overly (single string of text)
    def drawTextOverlay(self,text='',pos=[0,0],textCol='red',textSize=8):
        """
        Running loop to draw/update the text overlay. Requires drawTextOverlay_init to be ran beforehand

        Args:
            text (str): The text to be displayed on the overlay. Defaults to an empty string.
            pos ([int of size (2,1)]): The position of the overlay on the image. Defaults to [0, 0].
            textCol (str): The color of the text. Defaults to 'red'.
            textSize (int): The size of the text. Defaults to 8.

        Returns:
            None
        """
        # Update the properties - this contains the text
        new_properties = {'text': np.array([text]).astype(object)}
        self.layer.properties = new_properties
        #update the polygon - this contains the position
        pseudo_size = 0.1
        polygons = [np.array([[pos[0], pos[1]], [pos[0]+pseudo_size, pos[1]], [pos[0]+pseudo_size, pos[1]+pseudo_size], [pos[0], pos[1]+pseudo_size]])]
        #Remove the old polygon
        self.layer.data = []
        # add the new polygon
        self.layer.add(polygons,shape_type='polygon',edge_color='transparent',face_color='transparent')
        #Update the text surrounding the invisible shape
        text_properties = {'text': '{text}','anchor': 'upper_left','translation': [0, 0],'size': textSize,'color': textCol}
        self.layer.text = text_properties
        
    #Initialise an overlay that only has shapes
    def shapesOverlay_init(self):
        """
        Initialise an overlay that only draws shapes.

        Args:
            None

        Returns:
            None
        """
        #Initialise an overlay that only has shapes
        #Create a single shape (polygon) and show it
        polygons = [np.array([[225, 146], [283, 146], [283, 211], [225, 211]])]
        #Remove old layer
        self.napariViewer.layers.remove(self.layer)
        # new layer with polygons and text
        self.layer = self.napariViewer.add_shapes(polygons,shape_type='polygon',edge_color='transparent',face_color='transparent',name=self.layer_name,scale=self.layer_scale,opacity = self.opacity,visible=self.visible)
    
    #Update routine for an overlay that only has shapes
    def drawSquaresOverlay(self,shapePosList = [[0,0,10,10]],shapeCol: list[str | tuple[float, float, float]] = ['black']):
        """
        Running loop to draw/update and overlay with one or multiple rectangles. Requires shapesOverlay_init to be ran beforehand

        Args:
            shapePosList (List[List[int]]): A list of shape positions in the format [[x, y, w, h], [x, y, w, h], ...].
                Default is [[0, 0, 10, 10]].
            shapeCol (List[Union[str, Tuple[float, float, float]]]): A single entry or an array with the same size as shapePosList.
                Default is ['black'].

        Returns:
            None
        """        
        #Update the shapes
        polygons = []
        for p in range(len(shapePosList)):
            polygons.append(np.array([[shapePosList[p][0], shapePosList[p][1]], [shapePosList[p][0]+shapePosList[p][2], shapePosList[p][1]], [shapePosList[p][0]+shapePosList[p][2], shapePosList[p][1]+shapePosList[p][3]], [shapePosList[p][0], shapePosList[p][1]+shapePosList[p][3]]]))
        #Remove the old polygon
        self.layer.data = []
        # add the new polygon
        if len(shapeCol) == 1:
            self.layer.add(polygons,shape_type='polygon',edge_color='transparent',face_color=shapeCol[0])
        else:
            self.layer.add(polygons,shape_type='polygon',edge_color='transparent',face_color=shapeCol)
    
    #Update routine for an overlay that only has shapes
    def drawShapesOverlay(self,shapePosList = [[0,0],[0,10],[10,10],[10,0]],shapeCol: list[str | tuple[float, float, float]] = ['black']):
        """
        Running loop to draw arbitrary-shaped polygon shapes. Requires shapesOverlay_init to be ran beforehand

        Args:
            shapePosList (List[List[float]]): A list of shape positions. A [[x1-1,y1-1],[x1-2,y1-2],...],[[x2-1,y2-1],[x2-2,y2-2],...] array of size [n,2,m], drawing m shapes with n points each. Default is [[0,0],[0,10],[10,10],[10,0]].
            shapeCol (List[Union[str, Tuple[float, float, float]]]): A list of shape colors. Default is ['black'].

        Returns:
            None
        """
        #Update the shapes
        polygons = []
        for p in range(shapePosList.shape[2]):
            polygons.append(shapePosList[:,:,p])
        #Remove the old polygon
        self.layer.data = []
        # add the new polygon
        if len(shapeCol) == 1:
            self.layer.add(polygons,shape_type='polygon',edge_color='transparent',face_color=shapeCol[0])
        else:
            self.layer.add(polygons,shape_type='polygon',edge_color='transparent',face_color=shapeCol)
    
    #Initialise an overlay that only shows an image
    def imageOverlay_init(self,opacity=None,visible=None,blending=None,colormap=None):
        """
        Initialize a napari overlay that only draws an image

        Args:
            opacity (float, optional): The opacity of the layer. If None, the value will be taken from self.opacity.
            visible (bool, optional): Whether the layer is visible. If None, the value will be taken from self.visible.
            blending (str, optional): The blending mode. If None, the value will be taken from self.blending.
            colormap (str, optional): The colormap to use. If None, the value will be taken from self.colormap.
        
        Returns:
            None
        """
        # Assign values from self if the corresponding argument is None
        self.opacity = self.opacity if opacity is None else opacity
        self.visible = self.visible if visible is None else visible
        self.blending = self.blending if blending is None else blending
        self.colormap = self.colormap if colormap is None else colormap
        #Load image
        im = np.random.random((300, 300))
        #Remove old layer
        self.napariViewer.layers.remove(self.layer)
        # new layer with polygons and text
        self.layer = self.napariViewer.add_image(im,scale=self.layer_scale,opacity = self.opacity,visible=self.visible,blending=self.blending,colormap=self.colormap)
        
    #Update an overlay that shows an image
    def drawImageOverlay(self,im=np.zeros((300,300))):
        """
        Running loop to draw an image as napari overlay. Requires imageOverlay_init to be ran beforehand

        Parameters:
            im (numpy.ndarray): The image to be overlaid. Default is np.zeros((300, 300)).

        Returns:
            None
        """
        #Remove the old image
        self.layer.data = np.ones(np.shape(self.layer.data))
        #Update the image
        self.layer.data = im
        
    def destroy(self):
        """
        Deletes the instance of the class.
        """
        del self

class AnalysisThread_customFunction_Visualisation(QThread):
    finished = pyqtSignal()
    _do_visualise = pyqtSignal(object)
    def __init__(self,analysisObject,shared_data,analysisInfo: str | None = 'Random',delay=None):
        super().__init__()
        #Initiate some variables
        if delay==None:
            #Get the delay of the function from the realTimeAnalysis module,
            #ensure that it's never faster than the visualisation rate
            min_delay_visualisation = int(1000/(float(shared_data.config.visualisation_config.fps)))
            delay = max(min_delay_visualisation,utils.realTimeAnalysis_getDelay(analysisInfo,runOrVis='visualise'))
        
        logging.debug('#aC - init analysisThread_customFunction_Visualisation')
        self.is_running = True
        self.analysis_ongoing = False
        self.shared_data = shared_data
        self.analysisInfo = analysisInfo
        self.napariViewer = shared_data.napariViewer
        self.sleepTimeMs = delay
        self.napariOverlay = napariOverlay(self.napariViewer,RT_analysisObject=analysisObject,layer_name='TestLayer_VIS')
        self.visualisation_queue = deque(maxlen=10)#queue.Queue()
        self.shared_data = shared_data
        
        self.running = True
        self._new_image = Event()
        self._do_visualise.connect(self._visualise_on_main_thread)
    
    def new_image(self):
        self._new_image.set()

    def _visualise_on_main_thread(self, data):
        """Slot executed on the main (GUI) thread via Qt queued connection."""
        RT_analysis_object, analysisInfo, image, metadata, shared_data, core = data
        self.updateVisualisation(RT_analysis_object, analysisInfo, image, metadata, core)

    def run(self):
        node_label = self.analysisInfo.get('__selectedDropdownEntryRTAnalysis__', 'RT-analysis node') if isinstance(self.analysisInfo, dict) else str(self.analysisInfo)
        self.shared_data.register_perf_thread_label(get_native_id(), f'RT-analysis visualisation: {node_label}')
        try:
            while self.running:
                self._new_image.wait()
                self._new_image.clear()
                if not self.visualisation_queue:
                    continue
                data = self.visualisation_queue.popleft()
                # Emit to main thread so napari layer ops run on GUI thread (not here).
                self._do_visualise.emit(data)
                self.msleep(max(1,self.sleepTimeMs))
        finally:
            self.shared_data.unregister_perf_thread_label(get_native_id())
            
    def updateVisualisation(self,RT_analysis_object,analysisInfo,image,metadata=None,core=None):
        # logging.info('visualisation should be updated here :)')
        # tic = time.time()
        res = utils.realTimeAnalysis_visualisation(RT_analysis_object,analysisInfo,image,metadata,core,self.napariOverlay.layer)
        # print(f'Time spend in updateVisualisation; {time.time()-tic}')


# Snapshot-safe attribute types forwarded from the analysis subprocess back to the
# main-process visualisation shadow instance (see AnalysisProcess_customFunction).
# Deliberately excludes anything that could be a live handle (core, Qt objects,
# open files, etc.) which wouldn't survive/be meaningful across a process boundary.
_SUBPROCESS_SNAPSHOT_TYPES = (int, float, bool, str, bytes, type(None), np.ndarray, list, dict, tuple)


def _subprocess_analysis_worker(rt_analysis_info, in_queue, out_queue, stop_event,
                                 init_fn=None, run_fn=None, end_fn=None,
                                 control_in_queue=None, control_out_queue=None,
                                 log_level=None):
    """Entry point for the child process spawned by AnalysisProcess_customFunction.

    Kept as a free module-level function (not a method/closure) so it's picklable
    for multiprocessing's 'spawn' start method (required on Windows). init_fn/
    run_fn/end_fn default to the real utils.realTimeAnalysis_* functions; tests
    override them with lightweight picklable stand-ins to avoid depending on the
    GUI-widget-derived rt_analysis_info dict format.

    core and nodzInfo are always passed as None here -- RT-analysis run() is
    already documented as not allowed to touch the live hardware core, and a
    node needing nodzInfo (e.g. to read another graph node's data) at init time
    is not compatible with subprocess isolation (see class docstring).

    control_in_queue/control_out_queue (Performance Mode, see
    glados_pycromanager/observability/perf_capture.py): a *separate* pair of
    queues used only for "start/stop profiling this worker" signaling. Kept
    deliberately apart from in_queue/out_queue (the per-frame pipeline) so
    Performance Mode can never be confused with a malformed frame and never
    delays/derails normal frame processing. Both default to None so existing
    callers/tests that don't pass them are unaffected.

    log_level: the Adv. settings log level (e.g. "DEBUG"/"INFO") at the time
    this process was spawned. A 'spawn'-started child gets a fresh, unconfigured
    root logger (WARNING level, no handlers) -- without this, every logging.debug/
    info call made by a node's init/run/end here would be silently dropped
    regardless of what the user picked in Adv. settings. A later change to the
    setting while this worker is already running arrives via control_in_queue
    (see the '__set_log_level__:' branch below) rather than a restart.
    """
    logging.basicConfig(level=getattr(logging, str(log_level or 'INFO').upper(), logging.INFO))
    if init_fn is None and run_fn is None and end_fn is None:
        # Node classes (e.g. FFT_im.RealTimeFFT) are resolved via a sys.modules
        # stem lookup (_resolve_node_obj), not a fresh import. The spawned child
        # process only imports what's needed to unpickle this function, so the
        # RT-analysis plugin package -- built-ins plus anything dropped into the
        # AppData plugin folder, see CLAUDE.md's plugin-discovery section --
        # must be imported explicitly here to populate sys.modules.
        import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis  # noqa: F401

    init_fn = init_fn or utils.realTimeAnalysis_init
    run_fn = run_fn or utils.realTimeAnalysis_run
    end_fn = end_fn or utils.realTimeAnalysis_end

    RT_analysis_object = init_fn(rt_analysis_info, core=None, nodzInfo=None)
    _child_profiler = cProfile.Profile()
    try:
        while not stop_event.is_set():
            if control_in_queue is not None:
                try:
                    ctrl = control_in_queue.get_nowait()
                except std_queue.Empty:
                    ctrl = None
                except Exception:
                    logging.exception('AnalysisProcess worker: failed to read control queue, ignoring')
                    ctrl = None
                if ctrl == '__perf_profile_start__':
                    _child_profiler.enable()
                elif ctrl == '__perf_profile_stop__':
                    _child_profiler.disable()
                    buf = io.StringIO()
                    pstats.Stats(_child_profiler, stream=buf).sort_stats('cumulative').print_stats(25)
                    if control_out_queue is not None:
                        try:
                            control_out_queue.put({'__perf_report__': True, 'hotspots': buf.getvalue(), 'pid': os.getpid()})
                        except Exception:
                            logging.exception('AnalysisProcess worker: failed to enqueue profile report')
                    _child_profiler = cProfile.Profile()
                elif isinstance(ctrl, str) and ctrl.startswith('__set_log_level__:'):
                    new_level = ctrl.split(':', 1)[1]
                    logging.getLogger().setLevel(getattr(logging, new_level.upper(), logging.INFO))
            try:
                item = in_queue.get(timeout=0.5)
            except std_queue.Empty:
                continue
            except Exception:
                # A malformed/partially-received item (e.g. an unpickling error
                # on this end) must not kill the whole worker process -- that
                # would silently strand every subsequent frame in a "worker
                # never responds" state indistinguishable from a hang.
                logging.exception('AnalysisProcess worker: failed to receive a queued item, skipping')
                continue
            if item is None:  # stop sentinel
                break
            image, metadata = item
            try:
                result = run_fn(RT_analysis_object, rt_analysis_info, image, metadata, None, None, nodzInfo=None)
            except Exception:
                logging.exception('AnalysisProcess worker: run_fn failed')
                continue
            state_snapshot = {
                k: v for k, v in vars(RT_analysis_object).items()
                if isinstance(v, _SUBPROCESS_SNAPSHOT_TYPES)
            }
            try:
                out_queue.put([result, metadata, state_snapshot])
            except Exception:
                logging.exception('AnalysisProcess worker: failed to enqueue result')
    finally:
        try:
            end_fn(RT_analysis_object, rt_analysis_info, None, nodzInfo=None)
        except Exception:
            logging.exception('AnalysisProcess worker: end_fn failed')


def _rt_config_key(analysisInfo) -> Union[str, None]:
    """Stable cache key for AnalysisProcess_customFunction's warm-restart
    cache (see _park_subprocess_worker below) -- dict-equal configs hash
    identically regardless of key order, so restarting a node with unchanged
    kwargs reclaims its still-alive worker instead of a fresh spawn. Returns
    None (uncacheable) for non-dict analysisInfo (e.g. the plain-string
    sentinels used elsewhere, like 'LiveModeVisualisation') or anything that
    isn't JSON-serialisable, in which case callers fall back to today's
    always-fresh-spawn behaviour.
    """
    if not isinstance(analysisInfo, dict):
        return None
    try:
        return json.dumps(analysisInfo, sort_keys=True, default=str)
    except TypeError:
        return None


_RT_SUBPROCESS_CACHE_MAX_ENTRIES = 3
_RT_SUBPROCESS_CACHE_IDLE_SECS = 600  # 10 min


def _terminate_cached_worker(worker: dict) -> None:
    try:
        worker['process'].terminate()
    except Exception:
        logging.exception('AnalysisProcess: failed to terminate a parked subprocess')


def _park_subprocess_worker(shared_data, key: str, worker: dict) -> None:
    """Stashes a still-alive, already-warmed-up subprocess (+ its queues and
    main-process visualisation shadow object) in shared_data._rt_subprocess_cache
    so a later AnalysisProcess_customFunction.__init__ with the identical
    config can reclaim it directly. Also opportunistically reaps stale/excess
    entries so the cache doesn't need a dedicated periodic QTimer."""
    cache = shared_data._rt_subprocess_cache
    worker['last_used'] = time.time()

    now = time.time()
    for stale_key in [k for k, v in cache.items() if now - v['last_used'] > _RT_SUBPROCESS_CACHE_IDLE_SECS]:
        _terminate_cached_worker(cache.pop(stale_key))
    while len(cache) >= _RT_SUBPROCESS_CACHE_MAX_ENTRIES:
        lru_key = min(cache, key=lambda k: cache[k]['last_used'])
        _terminate_cached_worker(cache.pop(lru_key))

    cache[key] = worker


def terminate_all_rt_subprocesses(shared_data) -> None:
    """Best-effort, non-blocking teardown of every parked RT-analysis
    subprocess and the warm-pool's blank process. Call this right before
    forcing app exit (see GUI_napari.py's os._exit(0)) -- idle cached workers
    now outlive a single node's stop() call (that's the point of the cache),
    so without this they'd otherwise be orphaned instead of dying with their
    daemon-process parent."""
    cache = getattr(shared_data, '_rt_subprocess_cache', None)
    if cache:
        for worker in cache.values():
            _terminate_cached_worker(worker)
        cache.clear()
    pool = getattr(shared_data, '_rt_subprocess_pool', None)
    if pool is not None:
        pool.terminate()


class AnalysisProcess_customFunction(QThread):
    """Drop-in alternative to AnalysisThread_customFunction that runs a node's
    init/run/end in a separate OS process instead of on this QThread.

    Why: CPython's GIL serialises all threads within one process. A node whose
    compute holds the GIL for most of its runtime (e.g. diplib's FourierTransform
    -- benchmarked at ~80%+ GIL-held during a single call) starves the Qt main
    thread when it runs back-to-back on a QThread, which happens whenever frames
    arrive faster than the analysis can keep up (see
    https://github.com/kjamartens/Gladoscopy/issues/16). A separate OS process has
    its own GIL, so its compute can never block this process's main thread,
    regardless of what the underlying library does internally.

    Opt-in only: a node opts in via `"__runInSubprocess__": True` in its
    __function_metadata__ (see utils.realTimeAnalysis_runInSubprocess). Every
    node not opting in keeps using AnalysisThread_customFunction unchanged.
    Users can also force every node back onto the plain QThread path
    regardless of its own opt-in via Adv. settings -> "RT-analysis: use a
    separate CPU core (subprocess)" (shared_data.config.rt_analysis_config.
    subprocess_isolation, "True"/"False") -- useful for troubleshooting.
    Read fresh on every create_real_time_analysis_thread() call, so no
    restart is needed for a changed setting to take effect.

    v1 limitations (documented, not solved here):
      * `run()` always receives core=None and nodzInfo=None in the child process
        (see _subprocess_analysis_worker) -- a node relying on nodzInfo at init
        time (to read another graph node's data) is not compatible.
      * `shared_data` is not available inside the child process either -- a node
        reading shared_data inside run() will see None there.
      * Visualisation: `.visualise()` needs a live napari layer object, which
        cannot cross a process boundary, so a second node instance is created in
        this process purely to serve visualisation. Its plain-data attributes are
        refreshed from a snapshot the child sends back after every run() call, so
        a node that stores its result on `self` (e.g. `self.fft_display`) for
        `visualise()` to read keeps working unmodified. This duplicates any
        one-time init cost (e.g. importing diplib) once per process.
      * Warm restarts (_rt_config_key / _park_subprocess_worker /
        subprocess_pool.py): stop() parks a still-alive worker (+ its
        visualisation shadow object) instead of killing it, and __init__
        reclaims it on an identical restart to skip spawn/import/model-load.
        This means the node's Python-level state (self attributes set in
        run(), e.g. a frame counter or accumulation buffer) now survives a
        stop -> start of the *same* configuration, where previously every
        start got a fresh instance. No current node is known to rely on
        per-start-fresh state, so this isn't fixed with a reset hook -- if a
        future node needs one, that's the place to add it.
    """
    analysis_done_signal = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, shared_data, analysisInfo: str | None = 'Random', analysisQueue=None, sleepTimeMs=1, nodzInfo=None):
        super().__init__()
        logging.debug('#aC - started AnalysisProcess_customFunction')
        self.is_running = True
        self.shared_data = shared_data
        self.analysisInfo = analysisInfo
        self.napariViewer = shared_data.napariViewer
        self.image_queue_analysis = analysisQueue
        self.sleepTimeMs = sleepTimeMs
        self.nodzInfo = nodzInfo
        self._new_image = Event()
        self._activity_event = Event()
        self.visualisationObject = None
        self.RT_analysis_object = None
        self._cache_key = _rt_config_key(analysisInfo)
        wants_visualisation = bool(isinstance(analysisInfo, dict) and analysisInfo.get('__realTimeVisualisation__')) #type:ignore

        cached = shared_data._rt_subprocess_cache.pop(self._cache_key, None) if self._cache_key is not None else None
        if cached is not None:
            # A previous stop() of this exact node configuration parked its
            # still-alive worker (see _park_subprocess_worker) instead of
            # killing it -- its package imports/model weights/GPU context are
            # already loaded, so this restart skips spawn + import + model-load
            # entirely rather than paying it again.
            logging.debug('AnalysisProcess: reusing warm cached subprocess for %s', self._node_label())
            self._process = cached['process']
            self._in_queue = cached['in_queue']
            self._out_queue = cached['out_queue']
            self._stop_event = cached['stop_event']
            self._control_in_queue = cached['control_in_queue']
            self._control_out_queue = cached['control_out_queue']
            self.RT_analysis_object = cached['RT_analysis_object']
            self._worker_warmed_up = True
        else:
            # The child process re-imports the *entire* glados_pycromanager package
            # tree from scratch (spawn shares nothing with the parent) plus whatever
            # heavy library the node itself needs (e.g. diplib, "may take a few
            # seconds" per FFT_im.py) before it's ready to process its first frame --
            # observed up to ~10s in practice. Give that one-time cold start a much
            # longer grace period than the steady-state per-frame timeout, and don't
            # log it as a warning (it's expected, not a stall). A pre-warmed pool
            # process (below) can shortcut most of this.
            self._worker_warmed_up = False

            mp_ctx = mp.get_context('spawn')
            self._in_queue = mp_ctx.Queue(maxsize=2)
            self._out_queue = mp_ctx.Queue(maxsize=2)
            self._stop_event = mp_ctx.Event()
            # Separate queue pair used only by Performance Mode (see
            # glados_pycromanager/observability/perf_capture.py) to start/stop
            # cProfile inside this worker and get its hotspot report back --
            # kept apart from _in_queue/_out_queue so profiling control traffic
            # can never be mistaken for a frame/result and never delays one.
            self._control_in_queue = mp_ctx.Queue(maxsize=2)
            self._control_out_queue = mp_ctx.Queue(maxsize=2)

            claimed = shared_data._rt_subprocess_pool.try_claim()
            if claimed is not None:
                # A blank process pre-spawned at app startup (subprocess_pool.py)
                # already paid the spawn + package-tree (+ diplib) import cost --
                # hand it this node's real work instead of spawning from scratch.
                self._process, assign_queue = claimed
                assign_queue.put((analysisInfo, self._in_queue, self._out_queue, self._stop_event,
                                   self._control_in_queue, self._control_out_queue,
                                   shared_data.config.logging_config.log_level))
            else:
                self._process = mp_ctx.Process(
                    target=_subprocess_analysis_worker,
                    args=(analysisInfo, self._in_queue, self._out_queue, self._stop_event),
                    kwargs={
                        'control_in_queue': self._control_in_queue,
                        'control_out_queue': self._control_out_queue,
                        'log_level': shared_data.config.logging_config.log_level,
                    },
                    daemon=True,
                )
                self._process.start()

            # Visualisation shadow instance -- see class docstring. Constructed
            # in this (main) process only when the node wants real-time
            # visualisation.
            if wants_visualisation:
                self.RT_analysis_object = utils.realTimeAnalysis_init(analysisInfo, core=shared_data.core, nodzInfo=nodzInfo)

        if wants_visualisation and self.RT_analysis_object is not None:
            self.visualisationObject = AnalysisThread_customFunction_Visualisation(self.RT_analysis_object, shared_data, analysisInfo=analysisInfo)
            self.visualisationObject.start()

    def new_image(self):
        self._new_image.set()

    def set_activity(self, is_active):
        """Matches AnalysisThread_customFunction's interface -- napariGlados.py
        calls this on every live/MDA mode toggle for every RT-analysis thread.
        Currently inert (like the QThread version it mirrors: the run() loop
        doesn't gate on this event either), kept only so callers that iterate
        shared_data.RTAnalysisQueuesThreads don't AttributeError."""
        if is_active:
            self._activity_event.set()
        else:
            self._activity_event.clear()

    def _node_label(self) -> str:
        if isinstance(self.analysisInfo, dict):
            return str(self.analysisInfo.get('__selectedDropdownEntryRTAnalysis__', 'RT-analysis node'))
        return str(self.analysisInfo)

    def update_log_level(self, level: str) -> None:
        """Push a new Adv.-settings log level to the already-running child
        process, so a change takes effect without restarting the analysis
        (mirrors the main-process behaviour in utils.py's advanced-settings
        save handler, which calls observability.logger.set_log_level directly)."""
        try:
            self._control_in_queue.put_nowait(f'__set_log_level__:{level}')
        except std_queue.Full:
            logging.warning('AnalysisProcess: could not push log level update (control queue full)')

    def start_profiling(self) -> None:
        """Performance Mode: tell the child process to start cProfile."""
        try:
            self._control_in_queue.put_nowait('__perf_profile_start__')
        except std_queue.Full:
            logging.warning('AnalysisProcess: could not signal profiling start (control queue full)')

    def stop_profiling(self, timeout: float = 3.0):
        """Performance Mode: tell the child to stop cProfile and dump its
        hotspot table, plus psutil-based CPU%%/RSS/thread-count for the child
        PID. Returns a perf_capture.SubprocessReport, never raises."""
        from glados_pycromanager.observability.perf_capture import SubprocessReport
        pid = self._process.pid
        cpu_percent = None
        rss_mb = None
        thread_count = None
        try:
            import psutil
            if pid is not None and self._process.is_alive():
                child_proc = psutil.Process(pid)
                # cpu_percent() on a freshly-constructed Process object has no
                # baseline and always returns 0.0 on its first call -- block
                # briefly here (rare, user-initiated action, not a hot path)
                # to get a real instantaneous reading instead of a bogus 0.0.
                cpu_percent = child_proc.cpu_percent(interval=0.1)
                rss_mb = child_proc.memory_info().rss / (1024 * 1024)
                thread_count = child_proc.num_threads()
        except Exception as exc:  # noqa: BLE001 - profiling must never crash
            logging.warning('AnalysisProcess: could not read subprocess psutil stats: %r', exc)

        try:
            self._control_in_queue.put_nowait('__perf_profile_stop__')
        except std_queue.Full:
            return SubprocessReport(node_label=self._node_label(), pid=pid, cpu_percent=cpu_percent,
                                     rss_mb=rss_mb, thread_count=thread_count,
                                     error='could not signal profiling stop (control queue full)')
        try:
            report = self._control_out_queue.get(timeout=timeout)
        except std_queue.Empty:
            return SubprocessReport(node_label=self._node_label(), pid=pid, cpu_percent=cpu_percent,
                                     rss_mb=rss_mb, thread_count=thread_count,
                                     error=f'child did not respond within {timeout}s')
        return SubprocessReport(
            node_label=self._node_label(),
            pid=report.get('pid', pid),
            cpu_percent=cpu_percent,
            rss_mb=rss_mb,
            thread_count=thread_count,
            hotspots=report.get('hotspots'),
        )

    def run(self):
        self.shared_data.register_perf_thread_label(get_native_id(), f'RT-analysis (subprocess proxy): {self._node_label()}')
        try:
            self._run_loop()
        finally:
            self.shared_data.unregister_perf_thread_label(get_native_id())

    def _run_loop(self):
        while self.is_running:
            self._new_image.wait()
            self._new_image.clear()
            analysis_elapsed_ms = 0
            if self.image_queue_analysis:
                analysis_start = time.time()
                image, metadata = self.image_queue_analysis.popleft() #type:ignore
                # multiprocessing.Queue.put() hands off to a background feeder
                # thread that pickles asynchronously -- an unpicklable metadata
                # object (e.g. a live Java/SWIG-backed handle from the
                # pycromanager bridge) fails silently there with no exception
                # raised here, which otherwise looks identical to "the worker
                # never responded". Validate proactively so that failure mode
                # degrades (drop metadata, keep the frame) instead of hanging.
                try:
                    pickle.dumps(metadata)
                except Exception:
                    logging.warning('AnalysisProcess: frame metadata is not picklable, forwarding without it', exc_info=True)
                    metadata = {}
                try:
                    self._in_queue.put_nowait((image, metadata))
                except std_queue.Full:
                    logging.debug('AnalysisProcess: worker still busy with a previous frame, dropping this one')
                else:
                    get_timeout = 5 if self._worker_warmed_up else 30
                    try:
                        result, out_metadata, state_snapshot = self._out_queue.get(timeout=get_timeout)
                    except std_queue.Empty:
                        if not self._process.is_alive():
                            logging.error('AnalysisProcess: worker process is no longer alive, stopping this analysis thread')
                            self.is_running = False
                        elif self._worker_warmed_up:
                            logging.warning('AnalysisProcess: worker did not respond within %ss, skipping frame', get_timeout)
                        else:
                            logging.info('AnalysisProcess: worker still starting up (importing its dependencies), skipping frame')
                    else:
                        self._worker_warmed_up = True
                        analysis_elapsed_ms = (time.time() - analysis_start) * 1000
                        self.analysis_result = [result, out_metadata]
                        self.analysis_done_signal.emit(self.analysis_result)
                        if self.visualisationObject is not None and self.RT_analysis_object is not None:
                            self.RT_analysis_object.__dict__.update(state_snapshot)
                            if len(self.visualisationObject.visualisation_queue) < 1:
                                data = (self.RT_analysis_object, self.analysisInfo, image, out_metadata, self.shared_data, self.shared_data.core)
                                self.visualisationObject.visualisation_queue.append(data)
                                self.visualisationObject.new_image()
            # Same duty-cycle cap as AnalysisThread_customFunction: never sleep less
            # than the round-trip just took, so a persistently backlogged worker
            # can't monopolise this thread's requests either.
            self.msleep(max(1, self.sleepTimeMs, int(analysis_elapsed_ms)))
        self.finished.emit()

    def stop(self):
        self.is_running = False
        self._new_image.set()  # unblock run() if it's currently waiting
        if self.visualisationObject is not None:
            self.visualisationObject.running = False

        if self._cache_key is not None and self._process.is_alive():
            # Park this still-alive, already-warmed-up worker instead of
            # tearing it down -- a later __init__() with the identical
            # configuration reclaims it directly, skipping spawn + import +
            # model-load entirely. The worker's run loop just idles on
            # in_queue.get(timeout=0.5) with nothing arriving, so this costs
            # ~0 CPU while parked (see _park_subprocess_worker).
            _park_subprocess_worker(self.shared_data, self._cache_key, {
                'process': self._process,
                'in_queue': self._in_queue,
                'out_queue': self._out_queue,
                'stop_event': self._stop_event,
                'control_in_queue': self._control_in_queue,
                'control_out_queue': self._control_out_queue,
                'RT_analysis_object': self.RT_analysis_object,
            })
            return

        self._stop_event.set()
        try:
            self._in_queue.put_nowait(None)
        except Exception:
            pass
        self._process.join(timeout=3)
        if self._process.is_alive():
            self._process.terminate()

    def destroy(self):
        logging.debug('Destroying AnalysisProcess_customFunction for %s', self.analysisInfo)
        self.stop()
        self.requestInterruption()
        self.quit()


#This code gets some image and does some analysis on this - does NOT do the visualisation - see AnalysisThread_customFunction_Visualisation specifically for a second thread which does the RT visualisation based on this output

#Has to be a QThread and not e.g. multiprocessing because we rely on pickyyable objects - mostly the pycromanager core that we send around to influence the run during RT analysis
#
#UPDATE (see https://github.com/kjamartens/Gladoscopy/issues/16 and
#AnalysisProcess_customFunction above): nodes that don't need a live core/
#nodzInfo inside run() can now opt into subprocess isolation via
#`"__runInSubprocess__": True` in their __function_metadata__, specifically to
#avoid the GIL-starvation problem multiprocessing here would otherwise solve.
class AnalysisThread_customFunction(QThread):
    # Define analysis_done_signal as a class attribute, shared among all instances of AnalysisThread class
    # Create a signal to communicate between threads
    analysis_done_signal = pyqtSignal(object)
    finished = pyqtSignal()# signal to indicate that the thread has finished
    def __init__(self,shared_data,analysisInfo: str | None = 'Random',analysisQueue=None,sleepTimeMs=1,nodzInfo=None):
        """
        Initializes the AnalysisThread object.

        Args:
            shared_data: The shared data object. See Shared_data class for more information
            analysisInfo (Union[str, None]): Optional. The analysis 'title/method'. Default is 'Random'.
            visualisationInfo (Union[str, None]): Optional. The visualisation 'title/method'. Default is 'Random'.

        Returns:
        None
        """
        logging.debug('#aC - started AnalysisThread_customFunction')
        super().__init__()
        #Initiate some variables
        self.is_running = True
        self.analysis_ongoing = False
        self.shared_data = shared_data
        self.analysisInfo = analysisInfo
        self.napariViewer = shared_data.napariViewer
        self.image_queue_analysis = analysisQueue
        self.sleepTimeMs = sleepTimeMs
        self.napariOverlay = None
        self.nodzInfo=nodzInfo
        # self.napariOverlay = napariOverlay(self.napariViewer,layer_name='TestLayer')
        self.initAnalysis()
        self.running = True
        self._activity_event = Event()
        self._new_image = Event()
    
    def run(self):
        """
        Runs the function in a loop as long as `self.is_running` is True.

        Args:
            None

        Returns:
            None
        """
        
        node_label = self.analysisInfo.get('__selectedDropdownEntryRTAnalysis__', 'RT-analysis node') if isinstance(self.analysisInfo, dict) else str(self.analysisInfo)
        self.shared_data.register_perf_thread_label(get_native_id(), f'RT-analysis (in-process): {node_label}')
        try:
            self._run_loop()
        finally:
            self.shared_data.unregister_perf_thread_label(get_native_id())
        self.finished.emit()

    def _run_loop(self):
        while self.is_running:
            # # tic = time.time()
            # # Wait until liveMode or mdaMode is active
            # self._activity_event.wait()

            # #Only check the vis queue if live or mda is ongoing
            # if self.shared_data.liveMode or self.shared_data.mdaMode:
            #     # logging.debug(f'#aC - running analysisThread_customFunction, liveMode:{self.shared_data.liveMode}, mdaMode: {self.shared_data.mdaMode}')
            #     #Run analysis on the image from the queue

            self._new_image.wait()
            self._new_image.clear()
            analysis_elapsed_ms = 0
            if self.image_queue_analysis:
                analysis_start = time.time()
                self.analysis_result = self.runAnalysis(self.image_queue_analysis.popleft()) #type:ignore
                analysis_elapsed_ms = (time.time() - analysis_start) * 1000
                self.analysis_done_signal.emit(self.analysis_result)
            # Cap this thread's GIL-holding duty cycle: give the rest of the app at
            # least as much wall-clock time as the analysis call just took, so a
            # slow/GIL-heavy analysis (e.g. a diplib-based FFT) can't starve the Qt
            # main thread continuously when frames arrive faster than analysis keeps up.
            self.msleep(max(1, self.sleepTimeMs, int(analysis_elapsed_ms)))

        # while self.running:
        #     if not self.image_queue_analysis.empty():
        #         data = self.image_queue_analysis.get_nowait()
        #         self.runAnalysis(data)
        #         self.image_queue_analysis.task_done()
        #     time.sleep(self.sleepTimeMs/1000.0)
    
    def stop(self):
        """
        Stops the execution of the function
        """
        self.endAnalysis(self.analysisInfo,core=self.shared_data.core)
        self.is_running = False
        self._activity_event.set()
        #Also remove the image queue requestion from live mode
        # if self.image_queue_analysis in self.shared_data.RTAnalysisQueues:
        #     self.shared_data.RTAnalysisQueues.remove(self.image_queue_analysis)
        # if self.image_queue_analysis in self.shared_data.mdaImageQueues:
        #     self.shared_data.mdaImageQueues.remove(self.image_queue_analysis)
    
        try:
            #check if there's a layer associated with this...
            # layer = self.getLayer()
            #and remove it
            self.shared_data.skipAnalysisThreadDeletion = True
            # self.shared_data.napariViewer.layers.remove(layer)
        except (AttributeError, RuntimeError):
            pass
        
    def destroy(self):
        """
        Destroy the object.

        Args:
            None

        Returns:
            None
        """
        self.endAnalysis(self.analysisInfo,core=self.shared_data.core)
        try:
            logging.debug('Destroying '+str(self.analysisInfo))
        except (AttributeError, TypeError):
            logging.debug('Destroying some analysis thread')
        #Wait for the thread to be finished
        self.stop()
        self.requestInterruption()
        self.quit()
        #Officially we'd need to wait here, but that seems to start an infinite loop somewhere
        # self.wait()
        # self.deleteLater()
    
    def set_activity(self, is_active):
        if is_active:
            self._activity_event.set()
            # print('setting self._activity_event')
        else:
            self._activity_event.clear()
            # print('clearing self._activity_event')
    
    def new_image(self):
        self._new_image.set()

    #Get corresponding layer of napariOverlay
    def getLayer(self):
        """
        Obtain the napari overlay layer (napariOverlay class) associated with this analysisThread
        
        Args:
            None

        Returns:
            napari.layers.Layer: The layer associated with the napari overlay.
        """
        if self.napariOverlay is not None:
            return self.napariOverlay.getLayer()
        else:
            return None
    
    #Analysis is split into two parts: obtaining the analysis result and displaying this.
    #Here, we calculate the analysis result based on the analysisInfo
    def runAnalysis(self,data): 
        """
        Runs the analysis on the given image based on the analysis information provided.

        Args:
            data, containing:
            image (Image): The image on which the analysis needs to be performed.
            metadata: corresponding metadata

        Returns:
            analysisResult (Any): The result of the analysis. The analysis result will be passed to Visualise_Analysis_results.

        Notes:
            - The layer should be open before running the analysis.
            - The analysisInfo parameter should be set before calling this function.
            - If analysisInfo is 'AvgGrayValueText', the analysisResult will be the result of calcAnalysisAvgGrayValue.
            - If analysisInfo is 'GrayValueOverlay', the analysisResult will be the result of calcGrayValueOverlay.
            - If analysisInfo is 'CellSegmentOverlay', the analysisResult will be the result of calcCellSegmentOverlay.
            - If analysisInfo is not set or is invalid, the analysisResult will be None.
        """
        if data is not None:
            image = data[0]
            metadata = data[1]
            if self.analysisInfo is not None and self.analysisInfo != 'LiveModeVisualisation' and self.analysisInfo != 'mdaVisualisation':
                # self.msleep(self.sleepTimeMs)
                # self.msleep(self.sleepTimeMs)
                #Do analysis here - the info in analysisResult will be passed to Visualise_Analysis_results
                analysisResult = self.runAnalysisThisImage(self.analysisInfo,image,metadata=metadata,shared_data=self.shared_data,core=self.shared_data.core)
                # if self.analysisInfo == 'ChangeStageAtFrame':
                #     analysisResult = self.changeStageAtFrame(image,metadata=metadata,core=self.shared_data.core,frame=500)
                    
                return [analysisResult,metadata]
            elif self.analysisInfo == 'LiveModeVisualisation' or self.analysisInfo == 'mdaVisualisation':
                self.setPriority(self.TimeCriticalPriority) #type:ignore
                return None
            else:
                return None
        else:
            return None

    def initAnalysis(self):
        self.RT_analysis_object = utils.realTimeAnalysis_init(self.analysisInfo,core=self.shared_data.core,nodzInfo=self.nodzInfo)
        logging.debug('run initAnalysis')
        #Make a rtVis thread if required
        #Make a rtVis thread if required
        if '__realTimeVisualisation__' in self.analysisInfo and self.analysisInfo['__realTimeVisualisation__']: #type:ignore
            self.queue_visualisation = deque(maxlen=10)
            self.visualisationObject=AnalysisThread_customFunction_Visualisation(self.RT_analysis_object,self.shared_data,analysisInfo=self.analysisInfo)
            self.visualisationObject.start()
    
    def runAnalysisThisImage(self,analysisInfo,image,metadata=None,shared_data=None,core=None):
        # self.msleep(self.sleepTimeMs)
        # self.msleep(self.sleepTimeMs)
        
        #We are absolutely not allowed to access the core during the real-time analysis running.
        result = utils.realTimeAnalysis_run(self.RT_analysis_object,analysisInfo,image,metadata,shared_data,None,nodzInfo=self.nodzInfo)
        
        logging.debug(f"Analysis on Image done with result: {result}")
        
        if '__realTimeVisualisation__' in self.analysisInfo and self.analysisInfo['__realTimeVisualisation__']:#type:ignore
            logging.debug('Attempting RT visualisation!')
            # self.update_napariLayer(analysisInfo,image,metadata=metadata,core=core)
            # if self.visualisationObject.visualisation_queue.empty():
            # print(f'#ac537 -- len of queue: {len(self.visualisationObject.visualisation_queue)}')
            if len(self.visualisationObject.visualisation_queue) < 1:
                # data = (self.RT_analysis_object,analysisInfo,image,metadata,shared_data,core)
                data = (self.RT_analysis_object,analysisInfo,image,metadata,shared_data,core)
                self.visualisationObject.visualisation_queue.append(data)
                self.visualisationObject.new_image() #Signal that we have a new image in the visualisation object
                logging.debug('Put data in visualisation_queue!')
        
        return result
    
    def endAnalysis(self,analysisInfo,core=None):
        self.msleep(self.sleepTimeMs)
        result = utils.realTimeAnalysis_end(self.RT_analysis_object,analysisInfo,core,nodzInfo=self.nodzInfo)
        
        if '__realTimeVisualisation__' in self.analysisInfo and self.analysisInfo['__realTimeVisualisation__']:#type:ignore
            #End the visualisation
            self.visualisationObject.running=False
        return result


def create_real_time_analysis_thread(shared_data,analysisInfo = None,createNewThread = True,throughputThread=None,delay: float|None = None,nodzInfo=None):
    """
    Function that creates separate threads for real-time analysis. 
    """    
    global image_queue_analysis, napariViewer
    napariViewer = shared_data.napariViewer
    if createNewThread == False:
        image_queue_analysis = throughputThread
    else:
        #Create a new analysis thread
        image_queue_analysis = deque(maxlen=10)#queue.Queue() #This now needs to be linked to pycromanager so that pycromanager pushes images to all image queues and not just one
            
    if delay==None:
        #Get the delay of the function from the realTimeAnalysis module
        delay = utils.realTimeAnalysis_getDelay(analysisInfo,runOrVis='run')
    
    # image_queue_analysis = image_queue_transfer
    #Instantiate an analysis thread (or, for nodes opting into subprocess
    #isolation via "__runInSubprocess__", unless overridden by the global
    #Adv. settings kill switch shared_data.config.rt_analysis_config.
    #subprocess_isolation -- see https://github.com/kjamartens/Gladoscopy/
    #issues/16 -- an analysis process) and add a signal
    if utils.realTimeAnalysis_runInSubprocess(analysisInfo, shared_data):
        analysis_thread = AnalysisProcess_customFunction(shared_data,analysisInfo=analysisInfo, analysisQueue=image_queue_analysis,sleepTimeMs = delay,nodzInfo=nodzInfo) #type:ignore
    else:
        analysis_thread = AnalysisThread_customFunction(shared_data,analysisInfo=analysisInfo, analysisQueue=image_queue_analysis,sleepTimeMs = delay,nodzInfo=nodzInfo) #type:ignore
    
    
    analysis_thread.start()
    analysis_thread.finished.connect(analysis_thread.deleteLater)
    
    #Append it to the list of analysisThreads
    shared_data.RTAnalysisQueuesThreads.append({'Queue':image_queue_analysis,'Thread':analysis_thread})
    # shared_data.RTAnalysisQueuesThreads.append({'Queue':image_queue_analysis,'Thread':analysis_thread})
    
    return analysis_thread






# #PRETTY SURE THIS IS DEPRECATED
# #Maybe done for MDA visualisation ONLY
# #This code gets some image and does some analysis on this
# class AnalysisThread(QThread):
#     """
#     Obtained streamed data, and perform rt analysis and/or rt visualisation on this.
#     """
#     # Define analysis_done_signal as a class attribute, shared among all instances of AnalysisThread class
#     # Create a signal to communicate between threads
#     analysis_done_signal = pyqtSignal(object)
#     finished = pyqtSignal()# signal to indicate that the thread has finished
#     def __init__(self,shared_data,analysisInfo: Union[str, None] = 'Random',visualisationInfo: Union[str, None] = 'Random',analysisQueue=None,sleepTimeMs=500):
#         """
#         Initializes the AnalysisThread object.

#         Args:
#             shared_data: The shared data object. See Shared_data class for more information
#             analysisInfo (Union[str, None]): Optional. The analysis 'title/method'. Default is 'Random'.
#             visualisationInfo (Union[str, None]): Optional. The visualisation 'title/method'. Default is 'Random'.

#         Returns:
#         None
#         """
#         super().__init__()	
#         logging.debug('#aC - init AnalysisThread')
#         self.is_running = True
#         self.running = self.is_running
#         self.analysis_ongoing = False
#         self.shared_data = shared_data
#         self.analysisInfo = analysisInfo
#         self.visualisationInfo = visualisationInfo
#         self.napariViewer = shared_data.napariViewer
#         self.image_queue_analysis = analysisQueue
#         self.sleepTimeMs = sleepTimeMs
#         if analysisInfo == None:
#             self.napariOverlay = napariOverlay(self.napariViewer,layer_name=None)
#         elif analysisInfo == 'LiveModeVisualisation':
#             self.napariOverlay = napariOverlay(self.napariViewer,layer_name=None)
#             self.sleepTimeMs = 1000/float(self.shared_data.globalData['VISUALISATION-FPS']['value'])
#         elif analysisInfo == 'mdaVisualisation':
#             self.napariOverlay = napariOverlay(self.napariViewer,layer_name=None)
#             self.sleepTimeMs = 1000/float(self.shared_data.globalData['VISUALISATION-FPS']['value'])
#         else:
#             self.napariOverlay = napariOverlay(self.napariViewer,layer_name=analysisInfo)
#             #Create an empty overlay
#             if visualisationInfo != None:
#                 #Activate layer
#                 self.initialise_napariLayer()
    
#     def run(self):
#         """
#         Runs the function in a loop as long as `self.is_running` is True.

#         Args:
#             None

#         Returns:
#             None
#         """
#         while not self.isInterruptionRequested():
#             #Run analysis on the image from the queue
#             # logging.debug(self.image_queue_analysis.get())
#             # if self.image_queue_analysis.qsize() > 0:
#             logging.debug('#aC - runAnalysis is running')
#             if self.image_queue_analysis:
#                 #Get_nowait is not allowed in the following line:
#                 data = self.image_queue_analysis.popleft()
#                 self.analysis_result = self.runAnalysis(data) #type:ignore
#                 self.analysis_done_signal.emit(self.analysis_result)
#                 if self.is_running == False:
#                     # self.finished.emit()
#                     return
#             #Always sleep between frames
#             self.msleep(self.sleepTimeMs)
        
#         # Thread has finished, emit the finished signal
#         self.finished.emit()
        
        
#         # while self.running:
#         #     if not self.image_queue_analysis.empty():
#         #         data = self.image_queue_analysis.get_nowait()
#         #         self.runAnalysis(data)
#         #         self.image_queue_analysis.task_done()
#         #     time.sleep(self.sleepTimeMs/1000.0)
    
#     def stop(self):
#         """
#         Stops the execution of the function
#         """
#         self.is_running = False
#         #Also remove the image queue requestion from live mode
#         # if self.image_queue_analysis in self.shared_data.RTAnalysisQueues:
#         #     self.shared_data.RTAnalysisQueues.remove(self.image_queue_analysis)
#         # if self.image_queue_analysis in self.shared_data.mdaImageQueues:
#         #     self.shared_data.mdaImageQueues.remove(self.image_queue_analysis)
    
#     def destroy(self):
#         """
#         Destroy the object.

#         Args:
#             None

#         Returns:
#             None
#         """
#         try:
#             logging.debug('Destroying '+str(self.analysisInfo))
#         except:
#             logging.debug('Destroying some analysis thread')
#         #Wait for the thread to be finished
#         self.stop()
#         self.requestInterruption()
#         self.quit()
#         #Officially we'd need to wait here, but that seems to start an infinite loop somewhere
#         # self.wait()
#         # self.deleteLater()
    
#     #Get corresponding layer of napariOverlay
#     def getLayer(self):
#         """
#         Obtain the napari overlay layer (napariOverlay class) associated with this analysisThread
        
#         Args:
#             None

#         Returns:
#             napari.layers.Layer: The layer associated with the napari overlay.
#         """
#         return self.napariOverlay.getLayer()
    
#     #Analysis is split into two parts: obtaining the analysis result and displaying this.
#     #Here, we calculate the analysis result based on the analysisInfo
#     def runAnalysis(self,data): 
#         """
#         Runs the analysis on the given image based on the analysis information provided.

#         Args:
#             data, containing:
#             image (Image): The image on which the analysis needs to be performed.
#             metadata: corresponding metadata

#         Returns:
#             analysisResult (Any): The result of the analysis. The analysis result will be passed to Visualise_Analysis_results.

#         Notes:
#             - The layer should be open before running the analysis.
#             - The analysisInfo parameter should be set before calling this function.
#             - If analysisInfo is not set or is invalid, the analysisResult will be None.
#         """
#         if data is not None:
#             if self.analysisInfo == 'LiveModeVisualisation' or self.analysisInfo == 'mdaVisualisation':
#                 self.setPriority(self.TimeCriticalPriority) #type:ignore
#                 return None
#             else:
#                 return None
#         else:
#             return None

#     #And here we perform the visualisation - can be fully separate from performing the analysis
#     #Initialisation is called upon creation
#     def initialise_napariLayer(self):
#         if self.visualisationInfo == 'AvgGrayValueText':
#             self.initAvgGrayValueText()
#         elif self.analysisInfo == 'GrayValueOverlay':
#             self.initGrayScaleImageOverlay()
#         elif self.analysisInfo == 'ChangeStageAtFrame':
#             self.initChangeStageAtFrame()
#         else:
#             self.initRandomOverlay()
            
#     #Update ir called every time the analysis is done
#     def update_napariLayer(self,analysis_data):
#         if analysis_data is not None:
#             analysis_result = analysis_data[0]
#             metadata = analysis_data[1]
#             # logging.debug(analysis_result)
#             if self.analysisInfo is not None and self.analysisInfo != 'LiveModeVisualisation' and self.analysisInfo != 'mdaVisualisation':
#                 if self.visualisationInfo == 'AvgGrayValueText':
#                     self.visualiseAvgGrayValueText(analysis_result=analysis_result,metadata=metadata)
#                 elif self.analysisInfo == 'GrayValueOverlay':
#                     self.visualiseGrayScaleImageOverlay(analysis_result=analysis_result,metadata=metadata)
#                 # else:
#                 #     self.visualiseRandomOverlay()
    
#     def outlineCoordinatesToImage(self,coords):
#     # Create a blank grayscale image with a white background
#         image = Image.new("L", (self.shared_data.core.get_roi().width,self.shared_data.core.get_roi().height), "black")
#         draw = ImageDraw.Draw(image)

#         # Iterate over each n in N
#         for n in range(coords.shape[0]):
#             # Get the x and y coordinates for the current n
#             x = coords[n, 0, :]
#             y = coords[n, 1, :]

#             # Create a list of (x, y) tuples for drawing the lines
#             points = [(x[i], y[i]) for i in range(len(x))]

#             # Draw the lines on the image
#             draw.line(points, fill="white",width=2)  # Use black for the lines

#         # Convert the image to grayscale mode (L)
#         grayscale_image = image.convert("L")
#         return np.fliplr(np.rot90(np.array(grayscale_image),k=3))
    
#     """
#     Testing updating a stage during acq
#     """
    
#     def changeStageAtFrame(self,image,metadata=None,core=None,frame=100):
#         logging.debug(float(metadata['ImageNumber'])) #type:ignore
        
#         if float(metadata['ImageNumber'])>frame and self.notyetchanged == True: #type:ignore
#             core.set_relative_position('Z',100.0) #type:ignore
#             self.notyetchanged = False
#             logging.debug('Z position changed!')
        
#     def initChangeStageAtFrame(self):
#         logging.debug('Initted changestageatframe')
#         self.notyetchanged = True
    
#     """
#     Average gray value calculation and display
#     """
#     #Calculating average gray value of an image
#     def calcAnalysisAvgGrayValue(self,image,metadata=None):
#         return np.mean(np.mean(image))
    
#     def visualiseAvgGrayValueText(self,analysis_result='Random',metadata={}):
#         self.napariOverlay.drawTextOverlay(text='Mean gray value: {:.0f}, at frame: {:.0f}'.format(analysis_result,float(metadata['ImageNumber'])),pos=[0,0],textCol='white',textSize=12)
        
#     def initAvgGrayValueText(self):
#         self.napariOverlay.changeName('Average Gray Value')
#         self.napariOverlay.drawTextOverlay_init()
    
#     """
#     Random overlay display
#     """   
#     def visualiseRandomOverlay(self,analysis_result=None,metadata={}):
#         self.napariOverlay.drawSquaresOverlay(shapePosList=[[random.random()*100,random.random()*100,50,50],[100+random.random()*100,random.random()*100,100,100]],shapeCol=[(random.random(),random.random(),random.random()),(random.random(),random.random(),random.random())])
        
#     def initRandomOverlay(self):
#         self.napariOverlay.changeName('RandomOverlay')
#         self.napariOverlay.shapesOverlay_init()    
    
#     """
#     Testing overlay of image - based on grayscale value
#     """
#     def calcGrayValueOverlay(self,image,metadata=None):
#         #Get an image that simply provides a Boolean based on percentile:
#         image2 = np.where(image<np.percentile(image,25),1,0)
#         return image2
    
#     def visualiseGrayScaleImageOverlay(self,analysis_result=None,metadata={}):
#         #Expected analysis_result is a boolean image.
#         #Create an image overlay from napari
#         self.napariOverlay.drawImageOverlay(im=analysis_result) #type:ignore
    
#     def initGrayScaleImageOverlay(self):
#         self.napariOverlay.imageOverlay_init()
#         self.napariOverlay.changeName('Grayscale Image Overlay')
