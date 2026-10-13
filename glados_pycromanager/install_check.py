"""Warn when the environment is older than ``pyproject.toml`` (editable installs).

With an editable install a code edit is live on the next launch. A changed dependency
or entry point is not: it needs ``make dev`` again. ``make dev`` / ``make install``
stamp a fingerprint of those parts of ``pyproject.toml`` into the environment
(``python -m glados_pycromanager.install_check stamp``). At startup ``stale_install_message()``
compares it with the current file, and Glados shows a warning when they differ.

Deliberately quiet: no stamp (an environment set up before this existed) or no
``pyproject.toml`` next to the package (a regular, non-editable install) means "nothing
to say", never an error.
"""

import hashlib
import json
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / 'pyproject.toml'
STAMP_NAME = 'glados_install_stamp.txt'


def stamp_path() -> Path:
    return Path(sys.prefix) / STAMP_NAME


def install_fingerprint(pyproject: Path = PYPROJECT) -> str:
    """Hash of everything in pyproject.toml that a reinstall would pick up."""
    project = tomllib.loads(pyproject.read_text(encoding='utf-8')).get('project', {})
    relevant = {key: project.get(key) for key in
                ('dependencies', 'optional-dependencies', 'scripts', 'gui-scripts',
                 'entry-points', 'requires-python')}
    blob = json.dumps(relevant, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def write_stamp(pyproject: Path = PYPROJECT, stamp: Path | None = None) -> Path:
    stamp = stamp or stamp_path()
    stamp.write_text(install_fingerprint(pyproject) + '\n', encoding='utf-8')
    return stamp


def stale_install_message(pyproject: Path = PYPROJECT, stamp: Path | None = None) -> str | None:
    """A user-facing warning if the install is out of date, else None."""
    stamp = stamp or stamp_path()
    try:
        if not (pyproject.is_file() and stamp.is_file()):
            return None
        if stamp.read_text(encoding='utf-8').strip() == install_fingerprint(pyproject):
            return None
    except Exception:
        return None
    return ('pyproject.toml has changed since this environment was installed '
            '(dependencies or entry points). Run `make dev` to update it.')


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ['stamp']:
        print(f'stamped {write_stamp()}')
        return 0
    message = stale_install_message()
    print(message or 'install is up to date (or not stamped)')
    return 1 if message else 0


if __name__ == '__main__':
    sys.exit(main())
