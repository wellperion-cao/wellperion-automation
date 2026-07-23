# retime_auto_shutdown_2330.ps1
# 목적: Windows 예약작업 'Auto-Shutdown-2230'(22:30 PC 종료)을 23:30으로 변경하고
#       작업명을 'Auto-Shutdown-2330'으로 동기화한다. (GM 2026-06-08 지시)
#
# 배경: PC 종료 시각을 22:30 → 23:30으로 늦춰 23:00 텔레그램 슬롯(마감 점검) 발송 환경을 확보.
#       해당 예약작업은 \Welperion\ 경로 + RunLevel Highest 라 일반 세션에서 변경 불가(Access Denied).
#       → 본 스크립트를 '관리자 권한 PowerShell'에서 1회 실행하면 끝.
#
# 실행법 (관리자 PowerShell):
#   powershell -ExecutionPolicy Bypass -File "C:\Users\jjky0\welperion-automation\scripts\retime_auto_shutdown_2330.ps1"
#   또는 파일 우클릭 → 'PowerShell로 실행'(관리자) 후 권한 상승.

$ErrorActionPreference = 'Stop'

# 관리자 권한 확인
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
          ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[!] 관리자 권한이 필요합니다. 관리자 PowerShell에서 다시 실행하세요." -ForegroundColor Red
    exit 1
}

$oldName = 'Auto-Shutdown-2230'
$newName = 'Auto-Shutdown-2330'
$path    = '\Welperion\'

$old = Get-ScheduledTask -TaskName $oldName -TaskPath $path -ErrorAction SilentlyContinue
if ($null -eq $old) {
    # 이미 새 이름으로 변경된 경우: 트리거만 23:30 보정
    $cur = Get-ScheduledTask -TaskName $newName -TaskPath $path -ErrorAction SilentlyContinue
    if ($cur) {
        Set-ScheduledTask -TaskName $newName -TaskPath $path -Trigger (New-ScheduledTaskTrigger -Daily -At 23:30) | Out-Null
        Write-Host "[OK] $newName 이미 존재 → 트리거 23:30 보정 완료." -ForegroundColor Green
        exit 0
    }
    Write-Host "[!] '$oldName' / '$newName' 모두 없음. 작업명 확인 필요." -ForegroundColor Red
    exit 2
}

# 기존 action / principal / settings 보존하여 23:30 으로 재등록
$action    = $old.Actions[0]   # shutdown.exe /s /f /t 0
$principal = New-ScheduledTaskPrincipal -UserId $old.Principal.UserId -LogonType Interactive -RunLevel Highest
$settings  = $old.Settings
$trigger   = New-ScheduledTaskTrigger -Daily -At 23:30

Register-ScheduledTask -TaskName $newName -TaskPath $path -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
Unregister-ScheduledTask -TaskName $oldName -TaskPath $path -Confirm:$false

$check = Get-ScheduledTask -TaskName $newName -TaskPath $path
Write-Host "[OK] $newName 등록 완료. 트리거 = $($check.Triggers.StartBoundary)" -ForegroundColor Green
Write-Host "[OK] 구 $oldName 제거 완료. PC는 이제 23:30에 종료됩니다." -ForegroundColor Green
