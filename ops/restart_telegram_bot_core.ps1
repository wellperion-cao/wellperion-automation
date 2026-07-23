# 보고봇(@namuki_report_bot) 재기동 — 관리자 권한으로 실행됨 (restart_telegram_bot.bat가 승격 호출)
# 멈춘 bot.py 프로세스만 종료하고 예약작업으로 재기동. daily_scheduler(스케줄러)는 건드리지 않음.
$ErrorActionPreference = 'SilentlyContinue'
$root    = Split-Path -Parent $PSScriptRoot          # ops -> 저장소 루트
$pidFile = Join-Path $root 'telegram_bot\bot.pid'

Write-Host "=== 웰페리온 보고봇 재기동 ===" -ForegroundColor Cyan
$oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
Write-Host ("현재 bot.pid = " + $oldPid)

if ($oldPid) {
    Write-Host ("멈춘 봇 프로세스 " + $oldPid + " 종료 중...")
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

Write-Host "예약작업 WellperionTelegramBot 재실행..."
Start-ScheduledTask -TaskName 'WellperionTelegramBot'
Start-Sleep -Seconds 8

$newPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
Write-Host ("새 bot.pid = " + $newPid)
if ($newPid -and ($newPid -ne $oldPid)) {
    Write-Host "✅ 재기동 성공 (PID가 바뀜). CLI에서 시토가 폴링 재개를 확인합니다." -ForegroundColor Green
} else {
    Write-Host "⚠️ PID가 그대로입니다. 시토에게 알려주세요 — 추가 진단하겠습니다." -ForegroundColor Yellow
}
Write-Host "이 창은 8초 뒤 닫힙니다."
Start-Sleep -Seconds 8
