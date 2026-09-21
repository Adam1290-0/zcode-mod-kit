@echo off
cd /d "%~dp0"
title ZCode Mod Kit - modular patcher console
python modkit.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] failed - see output above.
)
pause
