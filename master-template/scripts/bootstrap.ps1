# bootstrap.ps1 — 마스터 템플릿 초기화 스크립트 (Windows PowerShell)
# 용도: 새 프로젝트에 복붙 후 state 폴더 초기화, 필수 파일 존재 확인, 체크리스트 출력
#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

Write-Host "=== 마스터 템플릿 부트스트랩 ===" -ForegroundColor Cyan
Write-Host "루트: $RootDir"
Write-Host ""

# 1. 필수 파일 존재 확인
$RequiredFiles = @(
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "ssot/약속.json",
    "ssot/incidents.json",
    "ssot/canon.json",
    "state/_queue.json",
    "loop/swarm-loop.md",
    "loop/quality-gates.md"
)

$Missing = 0
Write-Host "[1/4] 필수 파일 확인..." -ForegroundColor Yellow
foreach ($f in $RequiredFiles) {
    $FullPath = Join-Path $RootDir $f
    if (Test-Path $FullPath) {
        Write-Host "  OK  $f" -ForegroundColor Green
    } else {
        Write-Host "  MISSING  $f" -ForegroundColor Red
        $Missing++
    }
}

if ($Missing -gt 0) {
    Write-Host ""
    Write-Host "ERROR: 필수 파일 ${Missing}개 누락. 템플릿이 완전히 복사되었는지 확인하세요." -ForegroundColor Red
    exit 1
}

# 2. [[REPLACE_ME]] 플레이스홀더 확인
Write-Host ""
Write-Host "[2/4] 플레이스홀더 확인 (canon.json)..." -ForegroundColor Yellow
$CanonPath = Join-Path $RootDir "ssot/canon.json"
$CanonContent = Get-Content $CanonPath -Raw -Encoding UTF8
$PlaceholderCount = ([regex]::Matches($CanonContent, '\[\[REPLACE_ME\]\]')).Count
if ($PlaceholderCount -gt 0) {
    Write-Host "  WARNING: canon.json에 [[REPLACE_ME]] 플레이스홀더 ${PlaceholderCount}개 남음" -ForegroundColor Yellow
    Write-Host "  -> ssot/canon.json을 열어 실제 프로젝트 값으로 교체하세요"
} else {
    Write-Host "  OK  플레이스홀더 없음" -ForegroundColor Green
}

# 3. state/memory 폴더 초기화
Write-Host ""
Write-Host "[3/4] state/memory 폴더 초기화..." -ForegroundColor Yellow
$MemoryDir = Join-Path $RootDir "state/memory"
New-Item -ItemType Directory -Force $MemoryDir | Out-Null
$MemoryIndex = Join-Path $MemoryDir "MEMORY.md"
if (-not (Test-Path $MemoryIndex)) {
    @"
# 영구 메모리 인덱스

형식: - [제목](파일명.md) — 한 줄 요약
"@ | Out-File -FilePath $MemoryIndex -Encoding utf8
    Write-Host "  생성됨: state/memory/MEMORY.md" -ForegroundColor Green
} else {
    Write-Host "  OK  MEMORY.md 이미 존재" -ForegroundColor Green
}

# 4. 다음 체크리스트 출력
Write-Host ""
Write-Host "[4/4] 시작 체크리스트" -ForegroundColor Yellow
Write-Host "  [ ] ssot/canon.json -- [[REPLACE_ME]] 플레이스홀더를 실제 값으로 교체"
Write-Host "  [ ] AGENTS.md -- 미션 한 문장 교체"
Write-Host "  [ ] README.md -- 프로젝트 목적·컨텍스트 수정"
Write-Host "  [ ] state/_queue.json -- 첫 번째 태스크 추가"
Write-Host "  [ ] Claude Code에서 AGENTS.md를 시작점으로 오케스트레이터 호출"
Write-Host ""
Write-Host "=== 부트스트랩 완료 ===" -ForegroundColor Cyan
