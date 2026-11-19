@echo off
title Antigravity Remote Bridge

if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" goto :use_local_python

py -3 --version >nul 2>&1
if %ERRORLEVEL% equ 0 goto :use_py

python --version >nul 2>&1
if %ERRORLEVEL% equ 0 goto :use_python

echo [ERROR] Python was not found on this system!
echo Please install Python from https://www.python.org/
pause
exit /b 1

:use_local_python
echo Starting Antigravity Remote Bridge (Python 3.14)...
"%LOCALAPPDATA%\Programs\Python\Python314\python.exe" bot.py
goto :check_error

:use_py
echo Starting Antigravity Remote Bridge (py -3)...
py -3 bot.py
goto :check_error

:use_python
echo Starting Antigravity Remote Bridge (python)...
python bot.py
goto :check_error

:check_error
if errorlevel 1 (
    echo.
    echo [Process terminated with an error code: %ERRORLEVEL%]
    pause
)
