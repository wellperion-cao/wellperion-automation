@echo off
title Wellperion Token-Cache Live
echo Starting Wellperion ccusage live dashboard...
echo.

where ccusage >nul 2>&1
if %ERRORLEVEL% == 0 (
    ccusage blocks --live
) else (
    echo ccusage not found globally, falling back to npx...
    npx -y ccusage@latest blocks --live
)
