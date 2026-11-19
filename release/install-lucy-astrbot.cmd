@echo off
chcp 65001 >nul
setlocal enableextensions
cd /d "%~dp0"

echo ============================================================
echo   Lucy x AstrBot  -  installer
echo ============================================================
echo.

set "PY="
for %%C in (py.exe) do if not defined PY if exist "%%~$PATH:C" set "PY=py -3"
if not defined PY for %%C in (python.exe) do if not defined PY if exist "%%~$PATH:C" set "PY=python"

if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if not defined PY if exist "%USERPROFILE%\.astrbot\..\python\python.exe" set "PY=%USERPROFILE%\python\python.exe"

if not defined PY (
  echo [ERROR] Python 3.10+ not found.
  echo         Install Python or run:  python install.py
  echo.
  pause
  exit /b 1
)

%PY% install.py %*
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo [FAILED] exit code %RC%
pause
exit /b %RC%
