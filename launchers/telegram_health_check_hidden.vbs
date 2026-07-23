' Wellperion Telegram Health Check - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\telegram_health_check.log
' Created by AI CTO (2026-06-30): daily 13:00 Telegram bot health check via Task Scheduler.
' Recommended trigger: every day 13:00 via Task Scheduler (Wellperion-Telegram-HealthCheck-1300)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\telegram_health_check.bat", 0, False
