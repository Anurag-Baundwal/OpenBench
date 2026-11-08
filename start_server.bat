@echo off
rem Private OpenBench for the 4PC FFA engine: http://127.0.0.1:8000 (login anurag2801).
rem Only this machine can reach it. For the tablet on home Wi-Fi, use 0.0.0.0:8000 instead.
cd /d "%~dp0"
set /p OPENBENCH_SECRET_KEY=<.local_secret_key.txt
python manage.py runserver 127.0.0.1:8000 --noreload
