@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title ZCode Mod Kit - patcher console

rem ---- python guard ----
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found on PATH - install Python 3.10+ with "Add to PATH" checked.
    echo.
    pause
    exit /b 1
)

rem ---- ANSI escape helper (pure-ASCII source) ----
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"

rem ---- banner (note: ^| escapes the pipe char for cmd) ----
echo(
echo  %ESC%[35m  +--------------------------------------------------------------+%ESC%[0m
echo  %ESC%[35m  ^|%ESC%[0m  %ESC%[96mZ C O D E   M O D   K I T%ESC%[0m                                      %ESC%[35m^|%ESC%[0m
echo  %ESC%[35m  ^|%ESC%[0m  %ESC%[37msix-module patcher for the ZCode desktop client%ESC%[0m              %ESC%[35m^|%ESC%[0m
echo  %ESC%[35m  ^|%ESC%[0m                                                              %ESC%[35m^|%ESC%[0m
echo  %ESC%[35m  ^|%ESC%[0m  %ESC%[37mAuthor : Adam1290-0%ESC%[0m                                        %ESC%[35m^|%ESC%[0m
echo  %ESC%[35m  ^|%ESC%[0m  %ESC%[96mGitHub : https://github.com/Adam1290-0/zcode-mod-kit%ESC%[0m        %ESC%[35m^|%ESC%[0m
echo  %ESC%[35m  ^|%ESC%[0m  %ESC%[90mLicense: MIT - educational only, see DISCLAIMER.md%ESC%[0m           %ESC%[35m^|%ESC%[0m
echo  %ESC%[35m  +--------------------------------------------------------------+%ESC%[0m
echo(

rem ---- bouncing ball intro (~2s) ----
set "lane=                    "
set /a p=0, d=1
for /l %%n in (1,1,40) do (
    call set "head=%%lane:~0,!p!%%"
    call set "tail=%%lane:~!p!%%"
    set "tail=!tail:~1!"
    <nul set /p "=%ESC%[1G  %ESC%[90m[%ESC%[0m!head!%ESC%[96mO%ESC%[0m!tail!%ESC%[90m]  loading%ESC%[0m"
    ping -n 1 -w 50 127.0.0.1 >nul
    set /a p+=d
    if !p! geq 19 set /a d=-1
    if !p! leq 0 set /a d=1
)
echo(
echo  %ESC%[90mstarting the patcher console...%ESC%[0m
echo(

python modkit.py %*
if errorlevel 1 (
    echo.
    echo  %ESC%[91m[ERROR] failed - see output above.%ESC%[0m
)
echo.
pause
endlocal
