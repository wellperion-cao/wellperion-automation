@echo off
REM Wellperion - Kakao External Room Listen (once a day 06:30): detect new counterpart lines in
REM externally-facing kakao rooms (kakao_rooms.json external_rooms) and append to the owner
REM C-Level's most recent open ship. GM decision 2026-09-08 (ship 1137) - moved from hourly
REM to a single 06:30 run on 2026-09-11 (GM: saving every hour was too noisy).
REM ASCII only (CP949 safety) - room names are Korean but stay inside kakao_room_listen.py's
REM own JSON read and Python subprocess list args, never passed as .bat command-line args
REM (that is what breaks Korean args in other .bat files - see kakao_rooms.json room_aliases doc).
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=%USERPROFILE%\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
echo ===== %DATE% %TIME% kakao-external-listen start ===== >> "%ROOT%\logs\kakao_room_listen_external.log"
"%PY%" "%ROOT%\scripts\kakao_room_listen.py" --external >> "%ROOT%\logs\kakao_room_listen_external.log" 2>&1
set RC=%ERRORLEVEL%
echo ===== %DATE% %TIME% kakao-external-listen end rc=%RC% ===== >> "%ROOT%\logs\kakao_room_listen_external.log"
exit /b %RC%
