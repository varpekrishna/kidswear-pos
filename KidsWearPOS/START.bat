@echo off
title KidsWear Pro POS - Setup & Launch
cls
echo ============================================================
echo    KidsWear Pro - POS System Setup
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b
)

echo [OK] Python found.
echo.

:: Install requirements
echo Installing required packages...
pip install flask flask-cors python-barcode Pillow >nul 2>&1
if errorlevel 1 (
    echo Trying with --user flag...
    pip install --user flask flask-cors python-barcode Pillow >nul 2>&1
)
echo [OK] Packages installed.
echo.

:: Launch
echo ============================================================
echo    Starting KidsWear Pro POS Server...
echo    Open your browser to: http://localhost:5000
echo
echo    Login: admin / admin123
echo ============================================================
echo.
start http://localhost:5000
python app.py
pause
