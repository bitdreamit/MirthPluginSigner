@echo off
:: ============================================================
::  MirthPluginSigner — Windows build script
::  Run this on a Windows machine to produce MirthPluginSigner.exe
:: ============================================================
title Build MirthPluginSigner.exe

echo.
echo  ============================================================
echo    Building MirthPluginSigner.exe
echo  ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo  [ERROR] Python not found. Install from https://python.org
    echo          Tick "Add Python to PATH" during install.
    pause & exit /b 1
)

:: Check / install PyInstaller
python -m pip show pyinstaller >nul 2>&1
if %errorLevel% neq 0 (
    echo  [INFO] Installing PyInstaller...
    python -m pip install pyinstaller
    if !errorLevel! neq 0 ( echo [ERROR] pip failed. & pause & exit /b 1 )
)

:: Build
echo  [INFO] Building — this takes about 30-60 seconds...
python -m PyInstaller MirthPluginSigner.spec --clean

if %errorLevel% equ 0 (
    echo.
    echo  ============================================================
    echo    SUCCESS
    echo    Executable: dist\MirthPluginSigner.exe
    echo  ============================================================
    explorer dist
) else (
    echo  [ERROR] Build failed. Check output above.
)
echo.
pause
