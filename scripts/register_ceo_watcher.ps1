# Wellperion AI CEO Watcher 등록
# Windows Task Scheduler At log on + delay 60초

$taskName = "Wellperion-CEO-Watcher"
$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonCmd) {
    $pythonCmd = "C:\Python314\python.exe"
}
$projectRoot = "$env:USERPROFILE\welperion-automation"
$scriptPath = "$projectRoot\scripts\ceo_watcher.py"
$logPath = "$projectRoot\status\register_log.txt"

if (-not (Test-Path $scriptPath)) {
    Write-Host "ceo_watcher.py 미존재: $scriptPath" -ForegroundColor Red
    exit 1
}

# 기존 작업 삭제 (있으면)
try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
    Write-Host "기존 작업 제거: $taskName"
} catch { }

# 새 작업 등록
$action = New-ScheduledTaskAction -Execute $pythonCmd -Argument "`"$scriptPath`"" -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = "PT60S"
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "AI CEO 깨어남 watcher (15초 polling, At log on + 60s delay)"

Write-Host "등록 완료: $taskName" -ForegroundColor Green
Get-ScheduledTask -TaskName $taskName | Format-List TaskName,State,LastRunTime
