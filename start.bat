@echo off
cd /d "%~dp0"
py -3.12 app.py
if errorlevel 1 (
    echo.
    echo The program stopped with an error. Please send a screenshot of this window.
    pause
)
