# Glados-pycromanager

Glados-pycromanager is (1) a usable, user-friendly napari interface for Micro-Manager, through
Pycro-Manager and pymmcore-plus, and (2) easy, user-friendly autonomous microscopy on top of it.

**Documentation: <https://kjamartens.github.io/Gladoscopy/>**

Created by:
Dr. Koen J.A. Martens, koenjamartens{at}gmail.com, 2023-2026
[CC BY-NC-SA 4.0](LICENCE) licence

Please contact me if you want to use/extend/etc.

![Glados-pycromanager overview image](docs/img/Overview2.png)

![Example of user-friendly autonomous microscopy](docs/img/Autonomous_simple_1.png)

## Installation

Windows, with [Git](https://git-scm.com/download/win) installed:

```batch
git clone https://github.com/kjamartens/Gladoscopy.git
cd Gladoscopy
install_windows.bat
```

The script installs [uv](https://docs.astral.sh/uv/) if needed, which then sets up Python 3.13 and
all dependencies in a `.venv` folder, and offers Start Menu shortcuts. Re-run it after a `git pull`
to update. Developers: `make dev` (see [CONTRIBUTING.md](CONTRIBUTING.md)).

The [installation page](https://kjamartens.github.io/Gladoscopy/installation/) covers the
Micro-Manager setup and the ways to start Glados.

## Documentation

- [User guide](https://kjamartens.github.io/Gladoscopy/user-guide/controls/): controls, Multi-D
  acquisition, autonomous microscopy.
- [Writing nodes](https://kjamartens.github.io/Gladoscopy/developer/writing-nodes/): add your own
  analysis, real-time analysis or custom function.
- [API reference](https://kjamartens.github.io/Gladoscopy/developer/api/).

The site is built from [`docs/`](docs/) with MkDocs (`make docs`, or `make docs-serve` for a live
preview).

### Glados-pycromanager is a work-in-progress!
