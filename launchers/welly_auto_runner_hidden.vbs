' Wellperion Auto Runner - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\welly_auto_runner.log
' Created by AI CTO (2026-07-13): bae237 phase3 scheduled headless claude runner MVP.
' RUNNER_LIVE stays OFF inside welly_auto_runner.bat unless GM explicitly activates it
' (see docs\superpowers\specs\2026-07-13-welly-auto-runner-design.md SS9).
' Recommended trigger: daily (proposed 07:30, does not overlap gm_aide_scan at 06:30)
' via Task Scheduler (schtasks) - see ops\register_welly_auto_runner.bat (NOT auto-run).
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\welly_auto_runner.bat", 0, False
