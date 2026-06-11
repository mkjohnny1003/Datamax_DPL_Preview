@echo off
setlocal
cd /d "%~dp0"

set "INPUT_PATH=%~1"
if not defined INPUT_PATH set /p "INPUT_PATH=Enter a DPL file or folder path (blank = samples): "
if not defined INPUT_PATH set "INPUT_PATH=%~dp0samples"
set "INPUT_PATH=%INPUT_PATH:"=%"

if not exist "%INPUT_PATH%" (
    echo Input path not found:
    echo %INPUT_PATH%
    pause
    exit /b 1
)

where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0datamax_dpl_preview.py" "%INPUT_PATH%"
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python 3 was not found.
        pause
        exit /b 1
    )
    py -3 "%~dp0datamax_dpl_preview.py" "%INPUT_PATH%"
)

if errorlevel 1 (
    echo Preview generation failed.
    pause
    exit /b 1
)

if exist "%INPUT_PATH%\DPL_Preview\index.html" (
    start "" "%INPUT_PATH%\DPL_Preview\index.html"
) else (
    for %%I in ("%INPUT_PATH%") do set "INPUT_DIR=%%~dpI"
    if exist "%INPUT_DIR%DPL_Preview\index.html" start "" "%INPUT_DIR%DPL_Preview\index.html"
)

endlocal
