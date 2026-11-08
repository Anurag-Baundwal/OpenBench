@echo off
rem Worker for the private OpenBench server (start_server.bat first). -T = concurrent games.
rem --no-client-downloads: run this folder's Client, never one from Github.
cd /d "%~dp0Client"
set /p OB_PASSWORD=<..\.local_password.txt
python client.py -U anurag2801 -P "%OB_PASSWORD%" -S http://127.0.0.1:8000 -T 6 --no-client-downloads
