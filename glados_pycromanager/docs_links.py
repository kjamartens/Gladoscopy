"""Where the documentation lives: the MkDocs site built from `docs/` (see `mkdocs.yml`).

The in-app Help buttons and the napari "User Manual" widget point here instead of
rendering bundled copies, so there is one copy of the docs to keep current.
"""
from __future__ import annotations

import logging
import webbrowser

DOCS_URL = "https://kjamartens.github.io/Gladoscopy/"

#: Pages the GUI links to, relative to DOCS_URL (MkDocs' directory URLs).
USER_GUIDE_PAGE = ""
WRITING_NODES_PAGE = "developer/writing-nodes/"
API_REFERENCE_PAGE = "developer/api/"


def docs_url(page: str = "") -> str:
    """Full URL of a docs page, e.g. `docs_url(WRITING_NODES_PAGE)`."""
    return DOCS_URL + page.lstrip("/")


def open_docs(page: str = "") -> None:
    """Open a docs page in the system browser. Never raises: a help button must not
    take the GUI down."""
    url = docs_url(page)
    try:
        webbrowser.open(url)
    except Exception as exc:
        logging.error("Could not open %s: %s", url, exc)
