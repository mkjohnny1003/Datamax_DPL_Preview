@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0dist\Datamax_DPL_Preview_Viewer.exe" (
    start "" "%~dp0dist\Datamax_DPL_Preview_Viewer.exe"
    endlocal
    exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0datamax_dpl_preview_gui.py"
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python 3 was not found.
        pause
        exit /b 1
    )
    py -3 "%~dp0datamax_dpl_preview_gui.py"
)

endlocal
