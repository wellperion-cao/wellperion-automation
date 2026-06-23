# run_cycle.ps1 — 1 사이클 실행 스캐폴드 (Windows PowerShell)
# 용도: 큐에서 PENDING 태스크 읽기 → 실행 envelope → 검증 체크리스트 출력
# 주의: LLM 직접 호출 없음 — 구조와 체크리스트만 제공
#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$QueueFile = Join-Path $RootDir "state\_queue.json"

Write-Host "=== 스웜 사이클 실행 스캐폴드 ===" -ForegroundColor Cyan
Write-Host "사이클 시작: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

# 1. ssot 부팅 확인
Write-Host "[BOOT] ssot 3종 확인..." -ForegroundColor Yellow
$SsotFiles = @("ssot/약속.json", "ssot/incidents.json", "ssot/canon.json")
foreach ($f in $SsotFiles) {
    $FullPath = Join-Path $RootDir $f
    if (Test-Path $FullPath) {
        Write-Host "  OK  $f" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: $f 없음 -- 부팅 중단" -ForegroundColor Red
        exit 1
    }
}

# 2. 큐에서 PENDING 태스크 확인
Write-Host ""
Write-Host "[QUEUE] PENDING 태스크 확인..." -ForegroundColor Yellow
try {
    $Queue = Get-Content $QueueFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $PendingTasks = $Queue.tasks | Where-Object { $_.status -eq "PENDING" }
    Write-Host "  PENDING: $($PendingTasks.Count)개"
    foreach ($t in $PendingTasks) {
        Write-Host "  - [$($t.id)] $($t.title)"
    }
} catch {
    Write-Host "  (큐 파싱 실패 -- state/_queue.json 수동 확인)" -ForegroundColor Yellow
}

# 3. 실행 체크리스트
Write-Host ""
Write-Host "[CYCLE] 실행 전 체크리스트:" -ForegroundColor Yellow
Write-Host "  [ ] 1. intake 스킬 실행 (목표.범위.성공조건 명확화)"
Write-Host "  [ ] 2. decompose 스킬 실행 (태스크 분해.병렬 식별)"
Write-Host "  [ ] 3. 라우팅 결정 (토큰 라우팅 원칙 준수)"
Write-Host "  [ ] 4. executor -> implement 스킬 (병렬 가능 항목 병렬 실행)"
Write-Host "  [ ] 5. reviewer -> verify 스킬 (완료 4요건 확인)"
Write-Host "  [ ] 6. 큐 상태 업데이트"
Write-Host "  [ ] 7. retrospective 스킬 실행"
Write-Host "  [ ] 8. memory-update 스킬 실행"

# 4. 경계 확인
Write-Host ""
Write-Host "[LIMITS] 루프 경계 (canon.json 기준):" -ForegroundColor Yellow
try {
    $Canon = Get-Content (Join-Path $RootDir "ssot/canon.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $Lim = $Canon.loop_limits
    Write-Host "  태스크당 최대 재시도: $($Lim.max_retries_per_task)회"
    Write-Host "  최대 사이클: $($Lim.max_cycles)"
    Write-Host "  수렴 판단 기준: $($Lim.stall_threshold_cycles)사이클 연속 진전 없음"
} catch {
    Write-Host "  (canon.json 파싱 실패 -- 수동 확인)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== 사이클 스캐폴드 출력 완료 ===" -ForegroundColor Cyan
Write-Host "이제 Claude Code에서 AGENTS.md를 시작점으로 오케스트레이터를 호출하세요."
