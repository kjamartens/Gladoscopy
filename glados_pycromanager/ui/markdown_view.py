"""Render a Markdown file inside a `QWebEngineView` panel.

Lifted from `SmallWindow.addMarkdown` / `addHtml` in `GUI/utils.py`
(Phase 7.4). The split lets the markdown-to-HTML conversion be tested
in isolation and keeps `SmallWindow` light. The original methods on
`SmallWindow` are kept as 1-line wrappers around these helpers via a
re-export shim so existing call sites stay green.
"""
from __future__ import annotations

import os

import markdown
from PyQt5.QtCore import QUrl
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QVBoxLayout

# Markdown → HTML extension set kept identical to the original to avoid
# rendering differences for existing User-Manual pages.
_MARKDOWN_EXTENSIONS = [
    "markdown_captions",
    "fenced_code",
    "codehilite",
    "toc",
    "attr_list",
    "meta",
]


def _wrap_html(body_html: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script type="text/javascript" async
            src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.7/MathJax.js?config=TeX-MML-AM_CHTML">
        </script>
        <script type="text/x-mathjax-config">
            MathJax.Hub.Config({{
                tex2jax: {{
                    inlineMath: [['$','$']],
                    processEscapes: true
                }}
            }});
        </script>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; padding: 20px; }}
            img {{ max-width: 100%; height: auto; }}
        </style>
    </head>
    <body>
        {body_html}
    </body>
    </html>
    """


def markdown_to_html(md_path: str) -> str:
    """Read `md_path` and return MathJax-equipped HTML (string-only, no Qt)."""
    with open(md_path, encoding="utf-8") as fh:
        md_content = fh.read()
    body = markdown.markdown(md_content, extensions=_MARKDOWN_EXTENSIONS)
    return _wrap_html(body)


def add_markdown_to_window(window, md_path: str, width: int = 700, height: int = 800) -> None:
    """Attach a Markdown-rendered `QWebEngineView` to `window`'s central layout."""
    newlayout = QVBoxLayout()
    viewer = QWebEngineView()
    viewer.setFixedHeight(height)
    viewer.setFixedWidth(width)
    base_dir = os.path.dirname(os.path.abspath(md_path))
    viewer.setHtml(markdown_to_html(md_path), QUrl.fromLocalFile(base_dir + "/"))
    newlayout.addWidget(viewer)
    window.centralWidget().layout().addLayout(newlayout)


def add_html_to_window(window, html_path: str, width: int = 700, height: int = 800) -> None:
    """Attach a raw-HTML `QWebEngineView` to `window`'s central layout."""
    viewer = QWebEngineView()
    viewer.setFixedHeight(height)
    viewer.setFixedWidth(width)
    with open(html_path, encoding="utf-8") as fh:
        html_content = fh.read()
    viewer.setHtml(html_content)
    window.centralWidget().layout().addWidget(viewer)
