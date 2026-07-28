@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag and drop a video file onto Publish.bat
  exit /b 1
)
set "DEFAULT_TITLE=%~n1"
set /p TITLE=Enter video title [%DEFAULT_TITLE%]: 
if "%TITLE%"=="" set "TITLE=%DEFAULT_TITLE%"
py publish.py "%~1" --title "%TITLE%"
pause
endlocal
