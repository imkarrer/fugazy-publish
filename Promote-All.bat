@echo off
setlocal
cd /d "%~dp0"
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
echo Promoting all videos in channel-videos.txt ...
py promote.py --file channel-videos.txt
pause
endlocal
