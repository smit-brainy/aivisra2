@echo off
cd /d "%~dp0"
echo ===================================================
echo   Building AIVISRA_Virtual_CCTV.exe for Windows
echo ===================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found. Please install Python 3.10+ from python.org
        pause
        exit /b 1
    )
    set PY=py
) else (
    set PY=python
)

echo Checking PyInstaller...
%PY% -m pip install --upgrade pyinstaller

echo.
echo Compiling executable...
%PY% -m PyInstaller AIVISRA_Virtual_CCTV.spec --clean --noconfirm

if exist "dist\AIVISRA_Virtual_CCTV.exe" (
    echo.
    echo Copying AIVISRA_Virtual_CCTV.exe to server folder...
    copy /y "dist\AIVISRA_Virtual_CCTV.exe" .
    echo.
    echo ===================================================
    echo SUCCESS: AIVISRA_Virtual_CCTV.exe built successfully!
    echo ===================================================
) else (
    echo [ERROR] Build failed. Check the error log above.
)
pause
