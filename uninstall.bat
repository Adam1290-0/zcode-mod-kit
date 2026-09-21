@echo off
cd /d "%~dp0"
title ZCode Mod Kit - remove all modules
python modkit.py --uninstall-all
if errorlevel 1 (
    echo.
    echo [ERROR] failed - see output above.
)
pause
