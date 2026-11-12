@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title ZCode Mod Kit - patcher console
mode con: cols=104 lines=48 >nul 2>&1
chcp 65001 >nul 2>&1

rem =====================================================================
rem  python guard: a bundled copy wins over PATH, so a broken global
rem  install cannot take the installer down with it
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

rem =====================================================================
rem  The banner, kit version and every module version are printed by
rem  modkit.py --splash: one source of truth, so this script never has to
rem  be edited when a module bumps. Only a raw ANSI escape is needed here.
rem =====================================================================
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"

rem ---- winter intro: drifting snow, then the frozen roster ----
rem ---- (banner, version and every module version come from modkit.py, so
rem ----  this file never has to be edited when a module bumps)
%PY% modkit.py --splash %*
if errorlevel 2 goto pyfail

echo  %ESC%[38;5;153m  Every module is optional and reversible. Nothing is written outside%ESC%[0m
echo  %ESC%[38;5;153m  your ZCode install and %%USERPROFILE%%\.zcode\plugins\.%ESC%[0m
echo(
%PY% modkit.py --from-splash %*
if errorlevel 1 goto pyfail

echo.
pause
endlocal
exit /b 0

:pyfail
echo.
echo  %ESC%[91m[ERROR] the patcher failed - see the messages above.%ESC%[0m
echo.
pause
endlocal
exit /b 1
