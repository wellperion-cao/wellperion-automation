@echo off
REM  Wait until the Claude executable is ready (CTO, 2026-09-11).
REM
REM  Why: the first morning window (Start-AI CEO.bat) runs `claude update`, which swaps
REM  the global npm install. For about a minute the npm shims (claude.cmd / claude.ps1)
REM  already point at the new path while the 220MB bin\claude.exe has not been unpacked
REM  yet. Any other window launching in that gap dies with the PowerShell error
REM  "is not recognized as a cmdlet ...". Measured 2026-09-11 05:55:46 (2.1.267 -> 2.1.268);
REM  the GM had that error on screen.
REM
REM  What it does: 1) wait while the update marker exists, 2) wait until `claude` answers.
REM  Caps at 180s and then proceeds anyway - this must never block the boot.
REM
REM  ASCII only on purpose: cmd re-reads a .bat by byte offset, so Korean text plus a
REM  mid-file chcp shifts the parser and mangles the labels (measured while writing this).
REM  ping is the sleep, by full path: timeout.exe quits with "input redirection is not
REM  supported" whenever stdin is redirected, which is how a launcher often runs it.
setlocal
set "MARK=%USERPROFILE%\welperion-automation\logs\.claude_updating"
set "SLEEP=%SystemRoot%\System32\ping.exe"
set "N=0"

:wait_mark
if not exist "%MARK%" goto wait_exe
set /a N+=1
if %N% GEQ 90 goto give_up
"%SLEEP%" -n 3 127.0.0.1 >nul
goto wait_mark

:wait_exe
where claude >nul 2>&1
if not errorlevel 1 goto ready
set /a N+=1
if %N% GEQ 90 goto give_up
"%SLEEP%" -n 3 127.0.0.1 >nul
goto wait_exe

:give_up
echo   [wait] Claude not ready after 180s - starting anyway
endlocal
exit /b 0

:ready
if %N% GTR 0 echo   [wait] Claude update finished - starting now
endlocal
exit /b 0
