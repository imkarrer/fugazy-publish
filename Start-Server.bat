@echo off
setlocal
cd /d "%~dp0"
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
echo Starting Fugazy Publish web UI at http://127.0.0.1:8000
py -m uvicorn server:app --host 127.0.0.1 --port 8000
endlocal
