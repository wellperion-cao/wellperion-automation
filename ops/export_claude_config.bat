@echo off
REM ops\export_claude_config.bat - office PC: pack ~\.claude (settings, skills, plugins, HUD) into one zip for the home PC.
REM Double-click. Output = Desktop\wellperion_claude_config.zip. Never includes .credentials.json.
REM ASCII only on purpose (CP949 batch safety).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0export_claude_config.ps1"
pause
