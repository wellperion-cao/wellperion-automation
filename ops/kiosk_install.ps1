<#
  ops/kiosk_install.ps1 — 키오스크 PC 전원 자동 개폐 설치 (GM 지시 2026-08-13)

  ★관리자 권한으로 1회만 실행한다. 키오스크 PC 에서 돌린다.
     powershell -ExecutionPolicy Bypass -File kiosk_install.ps1

  같은 폴더에 kiosk_power.ps1 · kiosk_calendar.json 이 함께 있어야 한다.

  만드는 것
    Wellperion-Kiosk-Boot  부팅 직후 — 휴관일이면 끄고, 여는 시각 전이면 다시 잰다
    Wellperion-Kiosk-Off   19:30 · 22:00 — 오늘 닫는 시각이 지났으면 끈다
    Wellperion-Kiosk-Wake  07:50 — 잠든 PC를 깨우는 용도(하는 일 없음)

  ★이것만으로는 아침에 안 켜진다. 꺼진 PC 는 윈도우가 못 켠다 —
    메인보드 BIOS 에서 "시각 지정 전원 켜기"(Resume by Alarm / RTC Alarm Power On)를
    매일 05:50 으로 잡아야 완성된다. 현장에서 1회.
#>
$ErrorActionPreference = 'Stop'
$Here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Power = Join-Path $Here 'kiosk_power.ps1'

if (-not (Test-Path $Power)) { throw "kiosk_power.ps1 이 같은 폴더에 없습니다: $Here" }
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw '관리자 권한으로 다시 실행하세요(마우스 오른쪽 → 관리자 권한으로 실행).' }

# 1) 최대절전과 깨우기 타이머를 켠다 — 주말 아침 05:50~07:50 을 재우는 데 쓴다.
& powercfg.exe /hibernate on
& powercfg.exe /setacvalueindex SCHEME_CURRENT SUB_SLEEP bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d 1
& powercfg.exe /setactive SCHEME_CURRENT
Write-Output '전원 설정 — 최대절전·깨우기 타이머 켬'

$run     = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$common  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                                        -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
function Register-Kiosk([string]$name, $triggers, $action, $settings) {
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  Register-ScheduledTask -TaskName $name -Trigger $triggers -Action $action `
                         -Principal $run -Settings $settings | Out-Null
  Write-Output "등록 — $name"
}
function New-PowerAction([string]$mode) {
  New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -Mode {1}' -f $Power, $mode)
}

Register-Kiosk 'Wellperion-Kiosk-Boot' (New-ScheduledTaskTrigger -AtStartup) (New-PowerAction 'Boot') $common
Register-Kiosk 'Wellperion-Kiosk-Off' `
  @((New-ScheduledTaskTrigger -Daily -At '19:30'), (New-ScheduledTaskTrigger -Daily -At '22:00')) `
  (New-PowerAction 'Off') $common

# 깨우기 전용 — 하는 일은 없다. "이 작업을 실행하려면 절전 모드 해제" 때문에 존재한다.
$wakeSet = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                                        -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-Kiosk 'Wellperion-Kiosk-Wake' (New-ScheduledTaskTrigger -Daily -At '07:50') `
  (New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c exit') $wakeSet

Write-Output ''
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Power -Mode Show
Write-Output ''
Write-Output '남은 것 1개 — BIOS 에서 "시각 지정 전원 켜기"를 매일 05:50 으로 설정하세요.'
Write-Output '없으면 아침에 저절로 켜지지 않습니다(윈도우는 꺼진 PC를 못 켭니다).'
