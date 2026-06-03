# ============================================================
# Wellperion - hide all scheduled-task console windows (A-plan)
# Root-cause fix: tasks ran with visible console (python.exe / cmd .bat)
# in the interactive session. Re-point each to a hidden VBS launcher
# (wscript window style 0). Boot line + IG publish stay alive; only the
# black windows disappear. Created by AI CTO (2026-06-03).
# RUN AS ADMINISTRATOR (tasks are RunLevel=Highest).
# ============================================================
$ErrorActionPreference = 'Stop'
$wscript = "$env:WINDIR\System32\wscript.exe"
$L = "C:\Users\jjky0\welperion-automation\launchers"

function Set-Hidden($task, $vbs) {
  $vbsPath = Join-Path $L $vbs
  if (-not (Test-Path $vbsPath)) { Write-Host "[SKIP] launcher missing: $vbsPath" -ForegroundColor Yellow; return }
  $action = New-ScheduledTaskAction -Execute $wscript -Argument ('"{0}"' -f $vbsPath)
  Set-ScheduledTask -TaskName $task -Action $action | Out-Null
  Write-Host "[OK] $task  ->  $vbs (hidden)" -ForegroundColor Green
}

Write-Host "`n=== Wellperion: hiding task windows ===`n"

Set-Hidden "WellperionTelegramBot"          "bot_hidden.vbs"
Set-Hidden "WellperionDailyScheduler"       "scheduler_hidden.vbs"
Set-Hidden "Wellperion-IG-Publish-Watcher"  "ig_watcher_hidden.vbs"
Set-Hidden "Wellperion-Morning-Update"      "morning_update_hidden.vbs"

# Morning-Update: was failing with 0x800710E0 ("operator refused") because the
# task is blocked on battery power (DisallowStartIfOnBatteries / StopIfGoingOnBatteries).
# Clear battery conditions + wake the PC so the daily 05:40 update actually runs.
try {
  $mu = Get-ScheduledTask -TaskName "Wellperion-Morning-Update"
  $mu.Settings.DisallowStartIfOnBatteries = $false
  $mu.Settings.StopIfGoingOnBatteries     = $false
  $mu.Settings.WakeToRun                   = $true
  Set-ScheduledTask -TaskName "Wellperion-Morning-Update" -Settings $mu.Settings | Out-Null
  Write-Host "[OK] Wellperion-Morning-Update  ->  battery conditions cleared + WakeToRun" -ForegroundColor Green
} catch { Write-Host "[WARN] Morning-Update settings: $($_.Exception.Message)" -ForegroundColor Yellow }

# CEO-Verify-Watcher: orphan (target script ceo_verify_watcher.py never in git,
# absent on disk) -> only fails (result=2) and flashes a window each logon. Disable.
try {
  Disable-ScheduledTask -TaskName "Wellperion-CEO-Verify-Watcher" | Out-Null
  Write-Host "[OK] Wellperion-CEO-Verify-Watcher  ->  DISABLED (orphan, script missing)" -ForegroundColor Green
} catch { Write-Host "[WARN] CEO-Verify disable: $($_.Exception.Message)" -ForegroundColor Yellow }

# Restart the always-on daemons now so the visible windows vanish immediately
# (no reboot needed). Their morning 08:00 report already ran today.
Write-Host "`n--- restarting always-on tasks (windows will close) ---"
foreach ($t in "WellperionTelegramBot","WellperionDailyScheduler","Wellperion-IG-Publish-Watcher") {
  try {
    Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
    Start-ScheduledTask -TaskName $t
    Write-Host "[OK] restarted $t (now hidden)" -ForegroundColor Green
  } catch { Write-Host "[WARN] restart $t : $($_.Exception.Message)" -ForegroundColor Yellow }
}

Write-Host "`n=== DONE. Verifying no console windows remain... ===`n"
Start-Sleep -Seconds 2
$cmds = @(Get-Process cmd -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -ne "" })
$pys  = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*bot.py*" -or $_.CommandLine -like "*daily_scheduler*" })
Write-Host ("Visible cmd windows : {0}" -f $cmds.Count)
Write-Host ("Bot/Scheduler alive : {0}" -f $pys.Count)
Write-Host "`nIf both windows are gone and the bot still replies on Telegram, the fix worked.`n"
Read-Host "Press Enter to close"
