@echo off
setlocal
cd /d "%~dp0"
set "CHK=import sys, tkinter; raise SystemExit(sys.version_info[:2] < (3, 8))"

call :find
if defined PYW goto run

echo.
echo Python 3.8 or newer was not found on this PC. The Creality Hi tool needs it.
choice /c YN /m "Install Python 3.12 now (about a minute, no admin rights needed)"
if errorlevel 2 goto nopy

where winget >nul 2>&1
if not errorlevel 1 (
  echo Installing Python with winget ...
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
)
call :find
if defined PYW goto run

echo Downloading the Python installer from python.org ...
set "INST=%TEMP%\python-3.12.8-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile '%INST%'"
if exist "%INST%" (
  echo Installing Python ...
  start /wait "" "%INST%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_tcltk=1
)
call :find
if defined PYW goto run

echo.
echo Could not install Python automatically. Install it from https://www.python.org/downloads/
echo (tick "Add python.exe to PATH"), then double-click this file again.
pause
exit /b 1

:nopy
echo.
echo OK. Install Python 3.8+ from https://www.python.org/downloads/ (tick "Add python.exe to PATH"),
echo then double-click this file again.
pause
exit /b 1

:run
start "" %PYW% "%~dp0hi_gui.py"
exit /b 0

:find
set "PYW="
py -3 -c "%CHK%" >nul 2>&1
if not errorlevel 1 set "PYW=pyw -3" & goto :eof
python -c "%CHK%" >nul 2>&1
if not errorlevel 1 set "PYW=pythonw" & goto :eof
for %%V in (313 312 311 310 39 38) do (
  if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" -c "%CHK%" >nul 2>&1
    if not errorlevel 1 (
      set PYW="%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe"
      goto :eof
    )
  )
)
goto :eof
