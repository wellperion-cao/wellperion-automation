' Wellperion CMO Content Intake to Review Queue plus GM Card - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\cmo_intake_to_review.log
' Created by AI CMO (2026-07-24, ship 9888): instructor content intake reaches GM as a
' telegram card without a separate screen. Idempotent - already-sent rows never resend.
' Card-only - never approves or publishes (intake status is outside both publish gates).
' Trigger: every 15 minutes via Task Scheduler (schtasks)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\cmo_intake_to_review.bat", 0, False
