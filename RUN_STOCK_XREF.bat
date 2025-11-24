@echo off
setlocal EnableDelayedExpansion

REM List of files to check
set "file1=Shopify_Odoo_Stock_Cross_Ref\output\stock_cross_reference.xlsx"
set "file2=Shopify_Odoo_Stock_Cross_Ref\output\odoostock.xlsx"

set "files_open=0"
set "open_files="

REM Check each file to see if it's open
for %%f in ("%file1%" "%file2%") do (
    if exist "%%~f" (
        ren "%%~f" "%%~nxf" >nul 2>&1
        if errorlevel 1 (
            set /a files_open+=1
            if "!open_files!" == "" (
                set "open_files=%%~nxf"
            ) else (
                set "open_files=!open_files!, %%~nxf"
            )
        )
    )
)

REM If any files are open, warn the user
if %files_open% gtr 0 (
    echo.
    echo WARNING: The following Excel files appear to be open:
    echo !open_files!
    echo Please close them before proceeding.
    echo.
    choice /C YN /M "Do you want to continue anyway"
    if errorlevel 2 (
        echo Operation cancelled by user.
        exit /b
    )
)

REM Run the Stock Cross Reference process
python .\Shopify_Odoo_Stock_Cross_Ref\main.py
explorer .\Shopify_Odoo_Stock_Cross_Ref\output\
