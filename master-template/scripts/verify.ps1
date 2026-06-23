# verify.ps1 - Quality gate check (Windows PowerShell 5.1)
# Checks: required files, JSON validity, placeholders
#Requires -Version 5.1

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

$PassCount = 0
$FailCount = 0

function Check-Gate {
    param([string]$Label, [bool]$Passed, [string]$Reason = "")
    if ($Passed) {
        Write-Host "  PASS  $Label" -ForegroundColor Green
        $script:PassCount++
    } else {
        Write-Host "  FAIL  $Label -- $Reason" -ForegroundColor Red
        $script:FailCount++
    }
}

Write-Host "=== Quality Gate Check ===" -ForegroundColor Cyan
Write-Host ""

# Gate 1: Required files
Write-Host "[Gate 1] Required files" -ForegroundColor Yellow
$RequiredFiles = @(
    "README.md", "AGENTS.md", "CLAUDE.md",
    "ssot/incidents.json", "ssot/canon.json",
    "state/_queue.json", "state/README.md",
    "loop/swarm-loop.md", "loop/quality-gates.md",
    "agents/orchestrator.md", "agents/planner.md",
    "agents/executor.md", "agents/reviewer.md", "agents/researcher.md",
    "skills/index.md",
    "skills/intake/SKILL.md", "skills/decompose/SKILL.md",
    "skills/implement/SKILL.md", "skills/verify/SKILL.md",
    "skills/memory-update/SKILL.md", "skills/retrospective/SKILL.md",
    "docs/upstreams.md"
)
foreach ($f in $RequiredFiles) {
    $FullPath = Join-Path $RootDir $f
    Check-Gate -Label $f -Passed (Test-Path $FullPath) -Reason "file missing"
}
# Korean filename: count matching files to avoid PS5.1 string encoding issues
$YaksokCount = @(Get-ChildItem (Join-Path $RootDir "ssot") -File | Where-Object { $_.Name -match "^.{2}\.json$" -and $_.Length -gt 0 -and $_.Name -notmatch "^(canon|incidents)\.json$" }).Count
Check-Gate -Label "ssot/약속.json" -Passed ($YaksokCount -gt 0) -Reason "file missing"

# Gate 2: JSON validity
Write-Host ""
Write-Host "[Gate 2] JSON validity" -ForegroundColor Yellow
$JsonFiles = @("ssot/incidents.json", "ssot/canon.json", "state/_queue.json")
foreach ($f in $JsonFiles) {
    $FullPath = Join-Path $RootDir $f
    if (Test-Path $FullPath) {
        try {
            Get-Content $FullPath -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null
            Check-Gate -Label $f -Passed $true
        } catch {
            Check-Gate -Label $f -Passed $false -Reason "JSON parse error"
        }
    }
}
# Korean filename JSON: read via Get-ChildItem path
$YaksokPath = Get-ChildItem (Join-Path $RootDir "ssot") | Where-Object { $_.Name -eq "약속.json" } | Select-Object -ExpandProperty FullName
if ($YaksokPath) {
    try {
        Get-Content $YaksokPath -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null
        Check-Gate -Label "ssot/약속.json" -Passed $true
    } catch {
        Check-Gate -Label "ssot/약속.json" -Passed $false -Reason "JSON parse error"
    }
}

# Gate 3: Placeholder check
Write-Host ""
Write-Host "[Gate 3] Placeholder check (canon.json)" -ForegroundColor Yellow
try {
    $CanonPath = Join-Path $RootDir "ssot/canon.json"
    $CanonContent = Get-Content $CanonPath -Raw -Encoding UTF8
    $PlaceholderCount = ([regex]::Matches($CanonContent, '\[\[REPLACE_ME\]\]')).Count
    if ($PlaceholderCount -eq 0) {
        Check-Gate -Label "canon.json placeholders" -Passed $true
    } else {
        Write-Host ("  WARN  canon.json placeholders: $PlaceholderCount remaining - replace [[REPLACE_ME]] before production use") -ForegroundColor Yellow
    }
} catch {
    Check-Gate -Label "canon.json placeholders" -Passed $false -Reason "read failed"
}

# Summary
Write-Host ""
Write-Host "=== Result ===" -ForegroundColor Cyan
Write-Host "  PASS: $PassCount" -ForegroundColor Green
if ($FailCount -eq 0) {
    Write-Host "  FAIL: $FailCount" -ForegroundColor Green
    Write-Host "  Verdict: ALL GATES PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host "  FAIL: $FailCount" -ForegroundColor Red
    Write-Host ("  Verdict: " + $FailCount + " gate(s) failed - rework needed") -ForegroundColor Red
    exit 1
}
