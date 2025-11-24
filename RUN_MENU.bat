@echo off
setlocal EnableDelayedExpansion

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not found in your PATH. Please ensure Python is installed and in your PATH.
    pause
    exit /b 1
)

REM Check if materials.db exists and create it if it doesn't
if not exist materials.db (
    echo Creating materials database...
    python create_materials_db.py
)

REM Run the menu with full path specification
python "%~dp0materials_menu.py"

REM The menu will call one of the batch files, which will then return here