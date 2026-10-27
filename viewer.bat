@echo off
cd /d "%~dp0"
py -3.12 -c "import PIL, cv2" 2>nul
if errorlevel 1 (
    echo Installing Pillow and OpenCV for preview and recording...
    py -3.12 -m pip install pillow opencv-python
    if errorlevel 1 goto error
)
py -3.12 viewer.py
if errorlevel 1 goto error
exit /b 0
:error
echo.
echo The program stopped with an error. Please send a screenshot of this window.
pause
