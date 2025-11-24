@echo off
setlocal EnableDelayedExpansion

REM Check if order_flow.xlsx is open
set "excel_file=Order_Flow\output\order_flow.xlsx"

REM Try to rename the file to itself - if it fails, the file is likely open
if exist "%excel_file%" (
    ren "%excel_file%" "order_flow.xlsx" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo WARNING: The file order_flow.xlsx appears to be open.
        echo Please close it before proceeding.
        echo.
        choice /C YN /M "Do you want to continue anyway"
        if errorlevel 2 (
            echo Operation cancelled by user.
            exit /b
        )
    )
)

REM Run the Order Flow process
python .\Order_Flow\main.py
explorer .\Order_Flow\output\order_flow.xlsx
