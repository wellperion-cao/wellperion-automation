# daily_scheduler(넛지·정기보고 스케줄러) 재기동 — 관리자 권한(restart_daily_scheduler.bat가 승격 호출)
# 알림 문구 변경(①점검넛지 링크제거 ②미체크항목) 적용을 위해 스케줄러 프로세스만 재기동.
# 봇(WellperionTelegramBot)은 건드리지 않음.
$root    = Split-Path -Parent $PSScriptRoot          # ops -> 저장소 루트
$pidFile = Join-Path $root 'telegram_bot\daily_scheduler.pid'

function Test-ProcessAlive($procId) {
    if (-not $procId) { return $false }
    return [bool](Get-Process -Id $procId -ErrorAction SilentlyContinue)
}

Write-Host "=== 웰페리온 스케줄러 재기동 ===" -ForegroundColor Cyan
$oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
Write-Host ("현재 daily_scheduler.pid = " + $oldPid)

if ($oldPid -and (Test-ProcessAlive $oldPid)) {
    Write-Host ("멈춘 스케줄러 " + $oldPid + " 종료 중...")
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue

    $dead = $false
    for ($i = 0; $i -lt 5; $i++) {
        Start-Sleep -Seconds 1
        if (-not (Test-ProcessAlive $oldPid)) { $dead = $true; break }
    }

    if (-not $dead) {
        Write-Host ("Stop-Process 로 안 죽음 — taskkill /F /T 재시도: " + $oldPid) -ForegroundColor Yellow
        taskkill /PID $oldPid /F /T | Out-Null
        for ($i = 0; $i -lt 5; $i++) {
            Start-Sleep -Seconds 1
            if (-not (Test-ProcessAlive $oldPid)) { $dead = $true; break }
        }
    }

    if (-not $dead) {
        Write-Host ("실패: 옛 스케줄러(PID " + $oldPid + ") 종료 안 됨. 관리자 권한 확인 후 수동 종료 필요.") -ForegroundColor Red
        exit 1
    }
    Write-Host ("PID " + $oldPid + " 종료 확인됨.") -ForegroundColor Green
}

Write-Host "예약작업 WellperionDailyScheduler 재실행..."
Start-ScheduledTask -TaskName 'WellperionDailyScheduler'

$newPid = $null
for ($i = 0; $i -lt 8; $i++) {
    Start-Sleep -Seconds 1
    $candidate = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($candidate -and ($candidate -ne $oldPid) -and (Test-ProcessAlive $candidate)) {
        $newPid = $candidate
        break
    }
}

if ($newPid) {
    Write-Host ("새 daily_scheduler.pid = " + $newPid)
    Write-Host "OK 재기동 성공 (PID 바뀜). 새 넛지 문구가 다음 발송부터 적용됩니다." -ForegroundColor Green
} else {
    Write-Host "실패: 새 PID 확인 안 됨 (pid 파일 갱신 안 됨 또는 프로세스 미기동). 시토에게 알려주세요." -ForegroundColor Red
    exit 1
}
Write-Host "이 창은 8초 뒤 닫힙니다."
Start-Sleep -Seconds 8
