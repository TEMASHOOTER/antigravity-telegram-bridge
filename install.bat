@echo off
title Install Dependencies - Antigravity Remote Bridge

if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" goto :install_local_python

py -3 --version >nul 2>&1
if %ERRORLEVEL% equ 0 goto :install_py

python --version >nul 2>&1
if %ERRORLEVEL% equ 0 goto :install_python

echo [ERROR] Python was not found on this system!
echo Please install Python from https://www.python.org/
pause
exit /b 1

:install_local_python
echo Installing packages using Python 3.14...
"%LOCALAPPDATA%\Programs\Python\Python314\python.exe" -m pip install -r requirements.txt
goto :done

:install_py
echo Installing packages using py -3...
py -3 -m pip install -r requirements.txt
goto :done

:install_python
echo Installing packages using python...
python -m pip install -r requirements.txt
goto :done

:done
echo.
echo [DONE] Setup finished.
pause
