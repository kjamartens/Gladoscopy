# Troubleshooting

Problems that often come up on a first run:

1. **The Python backend cannot find a device adapter** (e.g. `andor_mmgr_dal.dll`): add the
   Micro-Manager installation folder to the system's `PATH`, restart the PC, and try again.
2. **`install_windows.bat` stops with an error mentioning git**: install Git, open a *new* terminal
   or Explorer window (so it sees the updated `PATH`), and run it again.
3. **Glados warns that `pyproject.toml` has changed since the environment was installed**: run
   `install_windows.bat` (or `make dev`) again after a `git pull`.
4. **"Glados could not start"**: the message box shows Micro-Manager's own error. *Show Details…*
   holds the end of the console log and *Open log file* opens the whole log
   (`%LOCALAPPDATA%\Glados-PycroManager\Glados_console.log`).
5. **Glados seems stuck** (an acquisition that does not stop, a frozen live view): press
   **Force-reset** in the Controls tab. It tries to stop every running acquisition and usually
   restores normal operation.

For anything else, start Glados with the "Glados (debug console)" shortcut so error messages stay
visible, and open an issue on [GitHub](https://github.com/kjamartens/Gladoscopy/issues).
