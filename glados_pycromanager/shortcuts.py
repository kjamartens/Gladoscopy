"""Start Menu (and optionally Desktop) shortcuts for one-click launching on Windows.

    python -m glados_pycromanager.shortcuts install [--desktop]
    python -m glados_pycromanager.shortcuts uninstall
    python -m glados_pycromanager.shortcuts show          # print what would be written

The shortcuts run the scripts of *this* environment. With an editable install
(``make dev``) that is the source tree, so a code edit is live on the next click and
there is no build step. Windows 11 offers no supported way to pin to the taskbar
programmatically: right-click the Start Menu entry once and choose "Pin to taskbar".

The "Glados" shortcut carries the AppUserModelID that ``GUI/startup.py`` sets on the
running process. That is what makes the running window group under the pinned icon
instead of under "Python". The other two need IDs of their own: the Start Menu lists
apps by AppUserModelID, so shortcuts sharing one collapse into a single entry.
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from glados_pycromanager.GUI.startup import APP_USER_MODEL_ID

FOLDER_NAME = 'Glados'
ICON = Path(__file__).resolve().parent / 'GUI' / 'Icons' / 'GladosIcon.ico'
UNLINK_ATTEMPTS = 20
UNLINK_RETRY_S = 0.1


@dataclass(frozen=True)
class ShortcutSpec:
    name: str            # file name without .lnk
    target: Path
    arguments: str
    working_dir: Path
    icon: Path
    description: str
    app_id: str = APP_USER_MODEL_ID
    launcher: Path | None = None  # the venv script run, when `target` is a wrapper (cmd.exe)

    @property
    def required(self) -> Path:
        return self.launcher or self.target


def scripts_dir() -> Path:
    """Where this environment's console/GUI launchers live (``.venv\\Scripts``)."""
    return Path(sys.prefix) / ('Scripts' if sys.platform == 'win32' else 'bin')


def cmd_exe() -> Path:
    return Path(os.environ.get('ComSpec', r'C:\Windows\System32\cmd.exe'))


def build_specs(scripts: Path, working_dir: Path, icon: Path = ICON) -> list[ShortcutSpec]:
    """The three shortcuts. Pure, so it can be tested without touching the Start Menu."""
    windowed, console = scripts / 'gladosw.exe', scripts / 'glados.exe'
    return [
        ShortcutSpec('Glados', windowed, '', working_dir, icon,
                     'Start Glados-PycroManager (choose the microscope backend)'),
        ShortcutSpec('Glados (last setup)', windowed, '--last', working_dir, icon,
                     'Start Glados-PycroManager with the backend and config used last time',
                     app_id=f'{APP_USER_MODEL_ID}.LastSetup'),
        # Run inside `cmd /k`: the console window belongs to cmd, so it stays open
        # with the traceback / last log lines after Glados exits or crashes.
        ShortcutSpec('Glados (debug console)', cmd_exe(), f'/k "{console}"', working_dir, icon,
                     'Start Glados-PycroManager with a console window showing its output '
                     '(stays open after Glados exits)',
                     app_id=f'{APP_USER_MODEL_ID}.DebugConsole', launcher=console),
    ]


def start_menu_dir() -> Path:
    import os
    return (Path(os.environ['APPDATA']) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs'
            / FOLDER_NAME)


def desktop_dir() -> Path:
    from win32com.shell import shell, shellcon
    return Path(shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0))


def write_shortcut(spec: ShortcutSpec, path: Path) -> None:
    """Write ``spec`` as a .lnk at ``path``, including its AppUserModelID."""
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
                                      pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    link.SetPath(str(spec.target))
    link.SetArguments(spec.arguments)
    link.SetWorkingDirectory(str(spec.working_dir))
    link.SetIconLocation(str(spec.icon), 0)
    link.SetDescription(spec.description)
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID,
                   propsys.PROPVARIANTType(spec.app_id, pythoncom.VT_LPWSTR))
    store.Commit()
    path.parent.mkdir(parents=True, exist_ok=True)
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(path), 0)


def read_shortcut(path: Path) -> dict:
    """Target, arguments, working dir and AppUserModelID of a .lnk (tests, ``show``)."""
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
                                      pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(path))
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    return {
        'target': link.GetPath(shell.SLGP_RAWPATH)[0],
        'arguments': link.GetArguments(),
        'working_dir': link.GetWorkingDirectory(),
        'app_id': store.GetValue(pscon.PKEY_AppUserModel_ID).GetValue(),
    }


def install(folders: list[Path], specs: list[ShortcutSpec]) -> list[Path]:
    missing = sorted({str(s.required) for s in specs if not s.required.exists()})
    if missing:
        raise FileNotFoundError('Launcher(s) not found, run `make dev` or install_windows.bat first: ' + ', '.join(missing))
    written = []
    for folder in folders:
        for spec in specs:
            path = folder / f'{spec.name}.lnk'
            write_shortcut(spec, path)
            written.append(path)
    return written


def _unlink_retrying(path: Path, attempts: int = UNLINK_ATTEMPTS) -> None:
    # A just-written .lnk is briefly opened by the virus scanner / search indexer.
    for attempt in range(attempts):
        try:
            path.unlink()
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(UNLINK_RETRY_S)


def uninstall(folders: list[Path], specs: list[ShortcutSpec]) -> list[Path]:
    removed = []
    for folder in folders:
        for spec in specs:
            path = folder / f'{spec.name}.lnk'
            if path.exists():
                _unlink_retrying(path)
                removed.append(path)
        if folder.name == FOLDER_NAME and folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
    return removed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('action', choices=['install', 'uninstall', 'show'])
    parser.add_argument('--desktop', action='store_true', help='Also put the shortcuts on the Desktop.')
    args = parser.parse_args(argv)
    if sys.platform != 'win32':
        parser.error('shortcuts are Windows-only')

    repo_root = Path(__file__).resolve().parents[1]
    specs = build_specs(scripts_dir(), repo_root)
    folders = [start_menu_dir()] + ([desktop_dir()] if args.desktop else [])
    if args.action == 'show':
        for spec in specs:
            print(f'{spec.name}: {spec.target} {spec.arguments}'.rstrip())
        print(f'-> {", ".join(str(f) for f in folders)}  (AppUserModelID {APP_USER_MODEL_ID})')
    elif args.action == 'install':
        for path in install(folders, specs):
            print(f'wrote {path}')
        print('\nTo pin: open Start, find "Glados", right-click it -> Pin to taskbar.')
    else:
        removed = uninstall(folders + [desktop_dir()], specs)
        print('\n'.join(f'removed {p}' for p in removed) or 'nothing to remove')
    return 0


if __name__ == '__main__':
    sys.exit(main())
