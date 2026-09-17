@echo off
REM counsel questions collect + learning loop (GM 2026-09-11 / 2026-09-17). log: logs\counsel_questions.log
setlocal
cd /d "%USERPROFILE%\welperion-automation"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo [%date% %time%] --- run --- >> logs\counsel_questions.log
C:\Python314\python.exe scripts\counsel_questions.py >> logs\counsel_questions.log 2>&1
REM learning loop: types -> 3 tenants -> blanks -> numbered questions -> metrics (2026-09-17)
C:\Python314\python.exe scripts\counsel_learning_loop.py >> logs\counsel_questions.log 2>&1
REM waiting-list board (labs_waiting.json) refresh (2026-09-17)
C:\Python314\python.exe scripts\labs_waiting.py >> logs\labs_waiting.log 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> logs\counsel_questions.log
exit /b %ERRORLEVEL%
