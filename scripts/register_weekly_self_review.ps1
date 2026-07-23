# 주간 AI 자기정리 파이프라인 예약작업 정리·등록 (AI CTO, 2026-07-10)
# 설계: docs/superpowers/specs/2026-07-10-weekly-ai-self-review-before-after-design.md
#
# 변경 내용(net-zero):
#   1) Wellperion-AI-Education-Weekly   : 인자에 --no-send 추가 (개별 발송 OFF, 트리거·시각 무변경)
#   2) Wellperion-AI-Learning-Proposer-Weekly : 트리거 월 09:45 -> 일 10:00 이동 + --no-send 는
#      hidden vbs 런처 자체에 이미 반영됨(launchers/ai_learning_proposer_hidden.vbs)
#   3) Wellperion-Weekly-Self-Review-Sunday (신규) : 일 10:30, 숨김 vbs 런처
#
# 안전: 기존 작업 삭제 후 재등록(Unregister -> Register) — 액션/트리거만 교체, 다른 예약작업 무영향.
#   실제 텔레그램 발송은 weekly_self_review.py 내부 게이트(WEEKLY_REVIEW_LIVE_SEND) 로 별도 통제.

$projectRoot = "$env:USERPROFILE\welperion-automation"
$python = "C:\Python314\python.exe"
$wscript = "$env:WINDIR\System32\wscript.exe"

function Write-Step($msg) { Write-Host $msg -ForegroundColor Cyan }

# ── 1) Education-Archive-Weekly(파일정리)는 무변경 — 손대지 않음 ──

# ── 2) AI-Education-Weekly: 인자에 --no-send 추가 (트리거 일 09:30 유지) ──
Write-Step "[1/3] Wellperion-AI-Education-Weekly — --no-send 추가"
try {
    $existing = Get-ScheduledTask -TaskName "Wellperion-AI-Education-Weekly" -ErrorAction Stop
    $trig = $existing.Triggers[0]
    $action = New-ScheduledTaskAction -Execute $python `
        -Argument "$projectRoot\scripts\ai_education_auto_learner.py --no-send" `
        -WorkingDirectory $projectRoot
    Set-ScheduledTask -TaskName "Wellperion-AI-Education-Weekly" -Action $action | Out-Null
    Write-Host "  갱신 완료" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] 작업 없음/갱신 실패 — 수동 확인 필요: $_" -ForegroundColor Yellow
}

# ── 3) AI-Learning-Proposer-Weekly: 트리거 월 09:45 -> 일 10:00 이동 ──
Write-Step "[2/3] Wellperion-AI-Learning-Proposer-Weekly — 트리거 월->일 10:00 이동"
try {
    Unregister-ScheduledTask -TaskName "Wellperion-AI-Learning-Proposer-Weekly" -Confirm:$false -ErrorAction Stop
    Write-Host "  기존 작업 제거"
} catch { }
$vbsPath = "$projectRoot\launchers\ai_learning_proposer_hidden.vbs"
$action = New-ScheduledTaskAction -Execute $wscript -Argument "`"$vbsPath`"" -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 10:00am
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName "Wellperion-AI-Learning-Proposer-Weekly" -Action $action `
    -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "AI 자기학습 개선제안 생성 — 일요일 10:00(주간 통합 카드 앞단), --no-send 개별발송 OFF (CTO 2026-07-10 이동)" | Out-Null
Write-Host "  등록 완료 (일 10:00)" -ForegroundColor Green

# ── 4) Weekly-Self-Review (신규): 일 10:30 ──
Write-Step "[3/3] Wellperion-Weekly-Self-Review-Sunday — 신규 등록(일 10:30)"
try {
    Unregister-ScheduledTask -TaskName "Wellperion-Weekly-Self-Review-Sunday" -Confirm:$false -ErrorAction Stop
    Write-Host "  기존 작업 제거"
} catch { }
$vbsPath2 = "$projectRoot\launchers\weekly_self_review_hidden.vbs"
$action2 = New-ScheduledTaskAction -Execute $wscript -Argument "`"$vbsPath2`"" -WorkingDirectory $projectRoot
$trigger2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 10:30am
$settings2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "Wellperion-Weekly-Self-Review-Sunday" -Action $action2 `
    -Trigger $trigger2 -Settings $settings2 -Principal $principal `
    -Description "주간 AI 자기정리 — 메모리+AI트렌드+C레벨컨텍스트 Before/After 카드 (CTO 2026-07-10). 실발송 게이트 WEEKLY_REVIEW_LIVE_SEND 기본 OFF." | Out-Null
Write-Host "  등록 완료 (일 10:30)" -ForegroundColor Green

Write-Host "`n=== 최종 상태 ===" -ForegroundColor Cyan
Get-ScheduledTask -TaskName "Wellperion-Education-Archive-Weekly","Wellperion-AI-Education-Weekly","Wellperion-AI-Learning-Proposer-Weekly","Wellperion-Weekly-Self-Review-Sunday" |
    Select-Object TaskName, State | Format-Table -AutoSize
