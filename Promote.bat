@echo off
setlocal
cd /d "%~dp0"
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
if "%~1"=="" (
  set /p YTURL=Paste YouTube URL or video ID: 
) else (
  set "YTURL=%~1"
)
if "%YTURL%"=="" (
  echo No URL provided.
  exit /b 1
)
py promote.py "%YTURL%"
pause
endlocal
