@echo off
REM Wellperion - Kakao External Room Listen (hourly, 08-21h): detect new counterpart lines in
REM externally-facing kakao rooms (kakao_rooms.json external_rooms) and append to the owner
REM C-Level's most recent open ship. GM decision 2026-09-08 20:2x (ship 1137, CBO->CTO).
REM ASCII only (CP949 safety) - room names are Korean but stay inside kakao_room_listen.py's
REM own JSON read and Python subprocess list args, never passed as .bat command-line args
REM (that is what breaks Korean args in other .bat files - see kakao_rooms.json room_aliases doc).
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
echo ===== %DATE% %TIME% kakao-external-listen start ===== >> "%ROOT%\logs\kakao_room_listen_external.log"
"%PY%" "%ROOT%\scripts\kakao_room_listen.py" --external >> "%ROOT%\logs\kakao_room_listen_external.log" 2>&1
set RC=%ERRORLEVEL%
echo ===== %DATE% %TIME% kakao-external-listen end rc=%RC% ===== >> "%ROOT%\logs\kakao_room_listen_external.log"
exit /b %RC%
