' Wellperion Auto Runner - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\welly_auto_runner.log
' Created by AI CTO (2026-07-13): bae237 phase3 scheduled headless claude runner MVP.
' RUNNER_LIVE stays OFF inside welly_auto_runner.bat unless GM explicitly activates it
' (see docs\superpowers\specs\2026-07-13-welly-auto-runner-design.md SS9).
' Recommended trigger: daily (proposed 07:30, does not overlap gm_aide_scan at 06:30)
' via Task Scheduler (schtasks) - see ops\register_welly_auto_runner.bat (NOT auto-run).
' 2026-08-20 검토(보류): 종료코드 전달 수리 대상에서 뺐다. 예약작업 ExecutionTimeLimit=PT10M인데
' RUNNER_LIVE를 켜면 헤드리스 claude 러너 소요시간이 원천적으로 무제한 — wait=True로 바꾸면
' 10분에서 강제 종료돼 진행 중 작업이 끊길 수 있다. 지금은 RUNNER_LIVE OFF라 즉시 끝나 무해하지만,
' RUNNER_LIVE를 켜는 시점에 ETL도 같이 늘려야 한다(이번 회차는 schtasks 설정 변경 범위 밖).
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\welly_auto_runner.bat", 0, False
