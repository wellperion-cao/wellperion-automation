# daily_scheduler(넛지·정기보고 스케줄러) 재기동 — 관리자 권한(restart_daily_scheduler.bat가 승격 호출)
# 알림 문구 변경(①점검넛지 링크제거 ②미체크항목) 적용을 위해 스케줄러 프로세스만 재기동.
# 봇(WellperionTelegramBot)은 건드리지 않음.
$ErrorActionPreference = 'SilentlyContinue'
$root    = Split-Path -Parent $PSScriptRoot          # ops -> 저장소 루트
$pidFile = Join-Path $root 'telegram_bot\daily_scheduler.pid'

Write-Host "=== 웰페리온 스케줄러 재기동 ===" -ForegroundColor Cyan
$oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
Write-Host ("현재 daily_scheduler.pid = " + $oldPid)

if ($oldPid) {
    Write-Host ("멈춘 스케줄러 " + $oldPid + " 종료 중...")
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

Write-Host "예약작업 WellperionDailyScheduler 재실행..."
Start-ScheduledTask -TaskName 'WellperionDailyScheduler'
Start-Sleep -Seconds 8

$newPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
Write-Host ("새 daily_scheduler.pid = " + $newPid)
if ($newPid -and ($newPid -ne $oldPid)) {
    Write-Host "OK 재기동 성공 (PID 바뀜). 새 넛지 문구가 다음 발송부터 적용됩니다." -ForegroundColor Green
} else {
    Write-Host "주의: PID 그대로. 시토에게 알려주세요." -ForegroundColor Yellow
}
Write-Host "이 창은 8초 뒤 닫힙니다."
Start-Sleep -Seconds 8
