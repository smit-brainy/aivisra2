@echo off
cd /d "%~dp0"
echo ===================================================
echo   AIVISRA Virtual CCTV RTSP Generator (Windows)
echo ===================================================
echo.

where python >nul 2>nul
if %errorlevel% equ 0 (
    python app.py %*
    goto end
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    py app.py %*
    goto end
)

echo [INFO] Python is not detected in your system PATH.
echo Trying to install Python 3.12 automatically via Windows winget...
winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
if %errorlevel% equ 0 (
    echo Python installed! Starting app...
    python app.py %*
    goto end
)

echo.
echo [ERROR] Python is required to run the script version.
echo Please download and install Python from: https://www.python.org/downloads/
echo IMPORTANT: During installation, check "Add python.exe to PATH".
echo.
pause

:end
