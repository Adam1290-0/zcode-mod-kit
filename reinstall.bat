@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title ZCode Mod Kit - reinstall last selection
chcp 65001 >nul 2>&1

rem =====================================================================
rem  Same python resolution as install.bat: a bundled copy wins, then the
rem  PATH entry, then the py launcher. reinstall.bat is the MOST used entry
rem  point (every ZCode update), so it must not be more fragile than the
rem  first install - a machine with only the py launcher used to fail here
rem  with "'python' is not recognized" right after a successful install.
rem =====================================================================
if exist "%~dp0python\python.exe" (
    set "PY=%~dp0python\python.exe"
    goto havePy
)
where python >nul 2>&1
if not errorlevel 1 (
    set "PY=python"
    goto havePy
)
where py >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
    goto havePy
)
echo.
echo  [ERROR] Python 3.10+ not found.
echo.
echo  Get it from https://www.python.org/downloads/
echo  and tick "Add python.exe to PATH" during setup.
echo.
pause
exit /b 1

:havePy
if not exist "modkit.py" (
    echo  [ERROR] modkit.py is missing next to this script.
    pause
    exit /b 1
)

%PY% modkit.py --reinstall
if errorlevel 1 (
    echo.
    echo  [ERROR] failed - see output above.
)
pause
endlocal
exit /b 0
