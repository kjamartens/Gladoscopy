"""Small Qt widget helpers extracted from `GUI/utils.py` (Phase 7.3).

These are dependency-light utilities — icon-folder discovery, the
warning/error/info icon painter, a 3-level `QLayout` widget walker, a
line-edit style setter, and the file-dialog launchers used across the
dock widgets. They are imported eagerly from `glados_pycromanager.GUI.utils`
via a thin re-export so existing call sites continue to work; new
modules should import from `glados_pycromanager.ui.widgets.builders`
directly.
"""
from __future__ import annotations

import functools
import logging
import os

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QFileDialog

logger = logging.getLogger(__name__)


# T-F1: rendered-pixmap cache, keyed by (iconFolder, type, alteration, iconSize).
# Populated lazily on first use — never at import, because constructing a QPixmap
# before a QApplication exists is invalid.
_ICON_PIXMAP_CACHE: dict[tuple[str, str, str, int], QPixmap] = {}


@functools.lru_cache(maxsize=1)
def findIconFolder() -> str:
    """Locate the `GUI/Icons/` folder regardless of install / repo layout.

    Memoized (T-F1): this is a pure lookup of a path that cannot change during a
    session, but it was called several times per warning-icon update — each call
    running an `importlib.util.find_spec` plus up to three `os.path.exists` probes.
    """
    import importlib.util

    if importlib.util.find_spec("glados_pycromanager") is not None:
        import glados_pycromanager  # noqa: PLC0415 — lazy on purpose

        package_path = os.path.dirname(glados_pycromanager.__file__)
        iconFolder = os.path.join(package_path, "GUI", "Icons")

        if not os.path.exists(iconFolder):
            if os.path.exists("./glados_pycromanager/GUI/Icons/General_Start.png"):
                iconFolder = "./glados_pycromanager/GUI/Icons/"
            elif os.path.exists("./glados-pycromanager/glados_pycromanager/GUI/Icons/General_Start.png"):
                iconFolder = "./glados-pycromanager/glados_pycromanager/GUI/Icons/"
            else:
                iconFolder = ""
    else:
        if os.path.exists("./glados_pycromanager/GUI/Icons/General_Start.png"):
            iconFolder = "./glados_pycromanager/GUI/Icons/"
        elif os.path.exists("./glados-pycromanager/glados_pycromanager/GUI/Icons/General_Start.png"):
            iconFolder = "./glados-pycromanager/glados_pycromanager/GUI/Icons/"
        else:
            iconFolder = ""
    return iconFolder


def setWarningErrorInfoIcon(widget, type, iconFolder, alteration="grayscale", iconSize=16):
    """Paint the warning / error / info icon onto `widget`, optionally grayed."""
    try:
        if type == "warning":
            iconLoc = iconFolder + os.sep + "WarningIcon.png"
        elif type == "error":
            iconLoc = iconFolder + os.sep + "ErrorIcon.png"
        else:
            iconLoc = iconFolder + os.sep + "InfoIcon.png"

        cache_key = (iconFolder, type, alteration, iconSize)
        cached = _ICON_PIXMAP_CACHE.get(cache_key)
        if cached is not None:
            widget.setPixmap(cached)
            return widget

        pixmap = QPixmap(iconLoc)

        if alteration == "grayscale":
            image = pixmap.toImage()

            ptr = image.bits()
            ptr.setsize(image.byteCount())
            image_array = np.array(ptr).reshape((image.height(), image.width(), 4))
            gray_array = np.dot(image_array[:, :, :3], [0.299, 0.587, 0.114])
            image_array[:, :, :3] = gray_array[:, :, np.newaxis]
            grayscale_image = QImage(
                image_array.data, image.width(), image.height(), QImage.Format_RGBA8888
            )
            pixmap = QPixmap.fromImage(grayscale_image)

        scaled_pixmap = pixmap.scaled(
            iconSize, iconSize, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        # Only cache a pixmap that actually rendered; a missing/unreadable PNG
        # yields a null QPixmap that we should keep retrying rather than pin.
        if not scaled_pixmap.isNull():
            _ICON_PIXMAP_CACHE[cache_key] = scaled_pixmap
        widget.setPixmap(scaled_pixmap)
        return widget
    except Exception:  # noqa: BLE001 — preserve historical "swallow on icon fail"
        return None


def setLineEditStyle(line_edit, type="Normal") -> None:
    """Apply the "normal" or "warning" border styling to a `QLineEdit`."""
    if type == "Normal":
        line_edit.setStyleSheet("border: 1px  solid #D5D5E5;")
    elif type == "Warning":
        line_edit.setStyleSheet("border: 1px solid red;")


def checkAndShowWidget(layout, widgetName):
    """Find `widgetName` (object-name match) within `layout`; `.show()` it.

    Walks up to two levels of nested layouts (the same depth the original
    helper supported). Returns implicitly `None` on hit, `False` when no
    widget with that name was found.
    """
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is not None:
            widget = item.widget()
            if widget.objectName() == widgetName:
                widget.show()
                return
        else:
            for index2 in range(item.count()):
                item_sub = item.itemAt(index2)
                if item_sub.widget() is not None:
                    widget = item_sub.widget()
                    if widget.objectName() == widgetName:
                        widget.show()
                        logger.debug("909 showing widget: %s", widget.objectName())
                        return
    return False


def lineEditFileLookup(line_edit_objName, text, filter, parent=None) -> None:
    """Open a file dialog seeded with `line_edit_objName`'s current dir."""
    parentFolder = line_edit_objName.text()
    if parentFolder != "":
        parentFolder = os.path.dirname(parentFolder)
    file_path = generalFileSearchButtonAction(
        parent=parent, text=text, filter=filter, parentFolder=parentFolder
    )
    line_edit_objName.setText(file_path)


def generalFileSearchButtonAction(
    parent=None, text="Select File", filter="*.txt", parentFolder=""
) -> str:
    """Wrap `QFileDialog.getOpenFileName` and return only the path."""
    file_path, _ = QFileDialog.getOpenFileName(parent, text, parentFolder, filter=filter)
    return file_path
