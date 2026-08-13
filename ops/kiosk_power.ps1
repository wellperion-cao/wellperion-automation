<#
  ops/kiosk_power.ps1 — 키오스크 PC 전원 자동 개폐 (GM 지시 2026-08-13)

  GM 확정 시각
    켜짐  평일 05:50 · 주말/공휴일 07:50
    꺼짐  평일 22:00 · 주말/공휴일 19:30
    휴관일(매월 2·4째 일요일 + 신정·설·추석 당일) = 그날은 켜지 않는다

  아침 켜짐은 윈도우가 못 만든다(꺼진 PC는 스스로 못 켠다). 메인보드 BIOS 의
  "시각 지정 전원 켜기"를 매일 05:50 으로 잡아 두고, 주말·공휴일에는 05:50 에
  깨어난 뒤 이 스크립트가 07:50 까지 다시 재우는 방식이다.

  달력 정본 = scripts/close_days.py → status/kiosk_calendar.json (여기서 판정을
  다시 구현하지 않는다). 달력 파일이 없으면 요일 규칙만으로 안전하게 돈다.

  실행
    powershell -ExecutionPolicy Bypass -File kiosk_power.ps1 -Mode Boot
    powershell -ExecutionPolicy Bypass -File kiosk_power.ps1 -Mode Off
    powershell -ExecutionPolicy Bypass -File kiosk_power.ps1 -Mode Show      # 오늘 판정만 출력
    powershell -ExecutionPolicy Bypass -File kiosk_power.ps1 -Mode SelfTest  # 검사
#>
param(
  [ValidateSet('Boot', 'Off', 'Show', 'SelfTest')]
  [string]$Mode = 'Show',
  [switch]$WhatIfOnly
)

$ErrorActionPreference = 'Stop'
$Root       = Split-Path -Parent $MyInvocation.MyCommand.Path
$CalPath    = Join-Path $Root 'kiosk_calendar.json'
$LogPath    = Join-Path $Root 'kiosk_power.log'

function Write-Log([string]$msg) {
  $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
  Add-Content -Path $LogPath -Value $line -Encoding UTF8
  Write-Output $line
}

function Get-Calendar {
  if (-not (Test-Path $CalPath)) { return @{ closed = @(); holidays = @() } }
  try { return Get-Content $CalPath -Raw -Encoding UTF8 | ConvertFrom-Json }
  catch { return @{ closed = @(); holidays = @() } }
}

# 그날의 판정 한 곳 — 켜는 시각·끄는 시각·휴관 여부를 함께 돌려준다.
function Get-DayPlan([datetime]$when, $cal) {
  $key      = $when.ToString('yyyy-MM-dd')
  $isClosed = @($cal.closed)   -contains $key
  $isHoli   = @($cal.holidays) -contains $key
  $isWeekend = ($when.DayOfWeek -eq 'Saturday') -or ($when.DayOfWeek -eq 'Sunday')
  $isRest   = $isWeekend -or $isHoli -or $isClosed
  # PowerShell 5.1 은 if 를 값으로 못 쓴다(7 부터 된다) — 키오스크 PC 는 5.1 이라 미리 계산한다.
  if ($isRest) {
    $onT  = $when.Date.AddHours(7).AddMinutes(50)
    $offT = $when.Date.AddHours(19).AddMinutes(30)
  } else {
    $onT  = $when.Date.AddHours(5).AddMinutes(50)
    $offT = $when.Date.AddHours(22)
  }
  [pscustomobject]@{
    Date    = $key
    Closed  = $isClosed
    Rest    = $isRest
    OnTime  = $onT
    OffTime = $offT
  }
}

function Invoke-Shutdown([string]$why) {
  Write-Log "종료 — $why"
  if ($WhatIfOnly) { return }
  & shutdown.exe /s /f /t 30 /c "웰페리온 키오스크 자동 종료"
}

function Invoke-Hibernate([string]$why) {
  Write-Log "최대절전 — $why (07:50 깨우기 작업이 다시 켠다)"
  if ($WhatIfOnly) { return }
  & shutdown.exe /h
}

if ($Mode -eq 'SelfTest') {
  $cal = @{ closed = @('2026-08-23'); holidays = @('2026-08-15') }
  $wd  = Get-DayPlan ([datetime]'2026-08-13 06:00') $cal   # 목요일 평일
  $sat = Get-DayPlan ([datetime]'2026-08-15 06:00') $cal   # 토요일 + 광복절
  $sun = Get-DayPlan ([datetime]'2026-08-23 06:00') $cal   # 4째 일요일 = 휴관
  if ($wd.Rest)   { throw '평일을 쉬는 날로 판정했다' }
  if (-not $sat.Rest)    { throw '토요일을 평일로 판정했다' }
  if ($sat.Closed)       { throw '광복절을 휴관으로 판정했다 — 광복절은 운영한다' }
  if (-not $sun.Closed)  { throw '2·4째 일요일 휴관을 놓쳤다' }
  if ($wd.OnTime.ToString('HH:mm')  -ne '05:50') { throw "평일 켜짐 시각 오류: $($wd.OnTime)" }
  if ($sat.OnTime.ToString('HH:mm') -ne '07:50') { throw "주말 켜짐 시각 오류: $($sat.OnTime)" }
  if ($wd.OffTime.ToString('HH:mm')  -ne '22:00') { throw "평일 꺼짐 시각 오류: $($wd.OffTime)" }
  if ($sat.OffTime.ToString('HH:mm') -ne '19:30') { throw "주말 꺼짐 시각 오류: $($sat.OffTime)" }
  Write-Output 'OK — kiosk_power 판정 8개 검사 통과'
  return
}

$now  = Get-Date
$plan = Get-DayPlan $now (Get-Calendar)
if ($plan.Closed)   { $label = '휴관일' }
elseif ($plan.Rest) { $label = '주말·공휴일' }
else                { $label = '평일' }

switch ($Mode) {
  'Show' {
    Write-Output ("{0} — {1} · 켜짐 {2} · 꺼짐 {3}" -f $plan.Date, $label,
                  $plan.OnTime.ToString('HH:mm'), $plan.OffTime.ToString('HH:mm'))
  }
  'Boot' {
    if ($plan.Closed) { Invoke-Shutdown "$label — 오늘은 열지 않는다"; break }
    if ($now -lt $plan.OnTime) {
      Invoke-Hibernate ("$label — 여는 시각 {0} 전에 깨어났다" -f $plan.OnTime.ToString('HH:mm'))
      break
    }
    Write-Log ("가동 유지 — $label · 오늘 꺼짐 {0}" -f $plan.OffTime.ToString('HH:mm'))
  }
  'Off' {
    # 19:30·22:00 두 번 다 이 작업이 뜬다. 오늘 꺼질 시각이 지났을 때만 끈다.
    if ($now -ge $plan.OffTime) { Invoke-Shutdown "$label — 닫는 시각" }
    else { Write-Log ("아직 안 끈다 — $label · 꺼짐 {0}" -f $plan.OffTime.ToString('HH:mm')) }
  }
}
