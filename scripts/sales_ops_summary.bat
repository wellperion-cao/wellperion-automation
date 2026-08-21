@echo off
REM 매출보고 시트 09:00 자동 채움 — P20(시설·지원·주차 운영 현황) + I16(예상 컨택·예약·LOSS)
REM 2026-08-21 시토: 런처가 cmd 한 줄에 따옴표를 겹쳐 넣다가 실패해 3일간(8/19~8/21) 조용히 안 돌았다.
REM   예약작업은 매일 Ready 로 떴고 종료코드만 1 이었으며 로그 파일조차 안 생겼다.
REM   이 저장소에서 이미 검증된 방식(ops_morning_digest.bat)과 같게 .bat 으로 옮긴다.
cd /d "C:\Users\jjky0\welperion-automation"
echo [%date% %time%] start >> "logs\sales_ops_summary.log"
C:\Python314\python.exe scripts\sales_report_ops_summary.py --contact >> "logs\sales_ops_summary.log" 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> "logs\sales_ops_summary.log"
exit /b %ERRORLEVEL%
