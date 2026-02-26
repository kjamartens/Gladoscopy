@echo off
echo --- Creating Environment ---
call conda env create -f environment.yaml
call conda activate GladosEnv

echo --- Installing Gladoscopy ---
uv pip install -e .

echo.
echo Done! Run with 'glados'
pause