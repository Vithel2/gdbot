@echo off
cd /d "%~dp0"
py -3.12 -m pip install -r simulator\requirements.txt
if errorlevel 1 goto error
py -3.12 simulator\sim.py
if errorlevel 1 goto error
pause
exit /b 0
:error
echo The program stopped with an error. Please send a screenshot of this window.
pause
