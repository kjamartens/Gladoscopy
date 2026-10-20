@echo off
setlocal EnableExtensions
rem Install or update Glados-PycroManager into .venv next to this file.
rem Needs Git and uv; uv downloads Python 3.13 itself. Re-run it after a `git pull`.
rem   install_windows.bat      interactive
rem   install_windows.bat /y   unattended: yes to every question, no pause at the end

set "UNATTENDED="
if /I "%~1"=="/y" set "UNATTENDED=1"
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
    echo Git was not found. Install it from https://git-scm.com/download/win
    echo ^(or: winget install Git.Git^), open a new window and run this again.
    goto :fail
)

where uv >nul 2>&1
if not errorlevel 1 goto :have_uv
echo uv ^(the Python installer Glados uses^) was not found.
if defined UNATTENDED goto :install_uv
choice /C YN /M "Install uv now from astral.sh (no admin rights needed)"
if errorlevel 2 (
    echo Install uv yourself: https://docs.astral.sh/uv/getting-started/installation/
    goto :fail
)
:install_uv
powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
rem The installer puts uv in %USERPROFILE%\.local\bin, which only new windows see on PATH.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>&1
if errorlevel 1 (
    echo uv could not be installed. See https://docs.astral.sh/uv/getting-started/installation/
    goto :fail
)
:have_uv

echo --- Python environment (.venv) ---
if exist ".venv\pyvenv.cfg" (
    echo Using the existing .venv
) else (
    uv venv --python 3.13 --seed .venv
    if errorlevel 1 goto :fail
)

echo --- Installing Glados-PycroManager and its dependencies ---
rem Editable install: a `git pull` updates the code; re-running this updates dependencies.
uv pip install --python .venv\Scripts\python.exe --compile-bytecode -e .
if errorlevel 1 goto :fail
rem Fingerprint pyproject.toml, so Glados warns when its dependencies change.
.venv\Scripts\python.exe -m glados_pycromanager.install_check stamp
if errorlevel 1 goto :fail

if defined UNATTENDED goto :shortcuts
choice /C YN /M "Add Glados to the Start Menu"
if errorlevel 2 goto :done
:shortcuts
.venv\Scripts\python.exe -m glados_pycromanager.shortcuts install
if errorlevel 1 goto :fail

:done
echo.
echo Done. Start Glados from the Start Menu, or run:  .venv\Scripts\glados.exe
if not defined UNATTENDED pause
exit /b 0

:fail
echo.
echo Installation did not complete.
if not defined UNATTENDED pause
exit /b 1
