@echo off
chcp 65001 >nul

REM ============================================================
REM  Wellperion Morning Update — pre-session npm + claude update
REM  Runs at 05:40 BEFORE any Claude session launches.
REM  Does NOT launch claude or any AI session.
REM ============================================================

set LOGDIR=C:\Users\jjky0\welperion-automation\logs
set LOGFILE=%LOGDIR%\morning_update.log

REM Create log directory if absent
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

REM Timestamp header
echo. >> "%LOGFILE%"
echo ======================================================== >> "%LOGFILE%"
for /f "tokens=*" %%T in ('powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd HH:mm:ss\""') do echo [%%T] Wellperion Morning Update START >> "%LOGFILE%"
echo ======================================================== >> "%LOGFILE%"

REM --- Step 1: npm global update of @anthropic-ai/claude-code ---
echo [Step 1] npm install -g @anthropic-ai/claude-code@latest >> "%LOGFILE%"
npm install -g @anthropic-ai/claude-code@latest >> "%LOGFILE%" 2>&1
set NPM_EXIT=%ERRORLEVEL%
echo [Step 1] npm exit code: %NPM_EXIT% >> "%LOGFILE%"

REM --- Step 2: claude self-update (only if npm step did not produce EBUSY) ---
echo [Step 2] claude update (self-update check) >> "%LOGFILE%"
claude update >> "%LOGFILE%" 2>&1
set CLAUDE_EXIT=%ERRORLEVEL%
echo [Step 2] claude update exit code: %CLAUDE_EXIT% >> "%LOGFILE%"

REM --- Summary ---
echo -------------------------------------------------------- >> "%LOGFILE%"
for /f "tokens=*" %%T in ('powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd HH:mm:ss\""') do echo [%%T] Wellperion Morning Update END >> "%LOGFILE%"
echo npm exit=%NPM_EXIT%  claude-update exit=%CLAUDE_EXIT% >> "%LOGFILE%"
echo ======================================================== >> "%LOGFILE%"

REM Exit 0 regardless — a no-op update is success; EBUSY during active session is expected.
exit /b 0
