' Wellperion Weekly Page Hygiene - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\weekly_page_hygiene.log
' Created by AI CTO (2026-07-14): CTO-2026-07-14-WEEKLY-PAGE-HYGIENE (GM ask).
' PAGE_HYGIENE_APPLY stays OFF inside scripts\weekly_page_hygiene.bat unless GM explicitly
' activates it (proposal-mode default for the first weeks - see script module docstring).
' Registered trigger: weekly, Sunday 09:00 via Task Scheduler (schtasks) - see
' ops\register_weekly_page_hygiene.bat (NOT auto-run).
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\weekly_page_hygiene.bat", 0, False
