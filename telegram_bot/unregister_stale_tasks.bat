@echo off
REM Wellperion - remove stale/duplicate scheduled tasks (Notion-era leftovers).
REM RUN AS ADMINISTRATOR. Safe: these point to deleted files / are duplicates of -Live tasks.
schtasks /Delete /TN "Wellperion-AutoTask-Watcher-Start" /F
schtasks /Delete /TN "Wellperion-AutoTask-Watcher-Stop" /F
schtasks /Delete /TN "Wellperion-CEO-Morning-Brief-0800" /F
schtasks /Delete /TN "Wellperion-PC-Shutdown-Greeting" /F
echo.
echo Done. Removed 4 stale tasks. Surviving: -Live versions + WellperionDailyScheduler/TelegramBot.
pause
