# Wellperion 일일 북극성 추천기 06:30 예약 등록
# Windows Task Scheduler — 매일 06:30, 숨김 VBS 런처 실행(검은창 없음).
# 메모리 준수: 트리거=Task Scheduler / 숨김런처=launchers/*.vbs / .bat=ASCII.

$taskName = "Wellperion-NorthStar-0630"
$projectRoot = "$env:USERPROFILE\welperion-automation"
$vbsPath = "$projectRoot\launchers\northstar_recommender_hidden.vbs"

if (-not (Test-Path $vbsPath)) {
    Write-Host "런처 미존재: $vbsPath" -ForegroundColor Red
    exit 1
}

# 기존 작업 삭제 (있으면)
try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
    Write-Host "기존 작업 제거: $taskName"
} catch { }

# wscript.exe 로 숨김 VBS 실행 (검은창 숨김 정책 준수)
$wscript = "$env:WINDIR\System32\wscript.exe"
$action = New-ScheduledTaskAction -Execute $wscript -Argument "`"$vbsPath`"" -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At 6:30am
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "일일 북극성 추천기 — 매일 06:30 전사 top3 카드 텔레그램 발송 (CTO 2026-06-29)"

Write-Host "등록 완료: $taskName" -ForegroundColor Green
Get-ScheduledTask -TaskName $taskName | Format-List TaskName,State
