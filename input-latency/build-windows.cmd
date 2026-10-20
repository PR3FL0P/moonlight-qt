@echo off
setlocal
cd /d "%~dp0"
if not exist "C:\msys64\msys2_shell.cmd" (
  echo Install MSYS2 into C:\msys64 and update it with pacman -Syu first.
  pause
  exit /b 1
)
call "C:\msys64\msys2_shell.cmd" -defterm -here -no-start -full-path -ucrt64 -c "bash ./build-windows.sh"
set "LATENCY_BUILD_RESULT=%ERRORLEVEL%"
pause
exit /b %LATENCY_BUILD_RESULT%
