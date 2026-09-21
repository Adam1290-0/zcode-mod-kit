@echo off
cd /d "%~dp0"
title ZCode Mod Kit - reinstall last selection
python modkit.py --reinstall
if errorlevel 1 (
    echo.
    echo [ERROR] failed - see output above.
)
pause
