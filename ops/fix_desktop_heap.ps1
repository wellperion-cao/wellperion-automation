# Wellperion Desktop Heap Fix (2026-07-09, 웰리/AI CEO)
# 반복되는 "python.exe/git.exe 0xc0000142" 하드에러 대화상자의 근본수리.
# Windows 세션 데스크톱 힙(SharedSection 상호작용 힙)을 20480 -> 40960 으로 증대.
# 부팅 임계 키라 SharedSection 값 1군데만 정밀 교체(나머지 완전 보존) + 무결성 가드 + 원본 백업.
# 발효 = 재부팅 1회. 가역 = logs\desktop_heap_SharedSection_backup.txt 로 복구.
$ErrorActionPreference = 'Stop'
$key = 'HKLM:\System\CurrentControlSet\Control\Session Manager\SubSystems'
$bak = 'C:\Users\jjky0\welperion-automation\logs\desktop_heap_SharedSection_backup.txt'

try {
  $old = (Get-ItemProperty -Path $key -Name Windows).Windows
} catch {
  Write-Host "[ERROR] 레지스트리 읽기 실패 — 관리자 권한으로 실행했는지 확인하세요." -ForegroundColor Red
  Read-Host "Enter를 눌러 닫기"; exit 1
}

Write-Host "현재 값:" -ForegroundColor Cyan
Write-Host "  $old"

if ($old -match 'SharedSection=1024,40960') {
  Write-Host "[SKIP] 이미 40960으로 적용되어 있습니다. 재부팅만 하면 발효됩니다." -ForegroundColor Yellow
  Read-Host "Enter를 눌러 닫기"; exit 0
}

$new = $old -replace 'SharedSection=1024,20480,768', 'SharedSection=1024,40960,768'
$roundtrip = (($new -replace 'SharedSection=1024,40960,768','SharedSection=1024,20480,768') -eq $old)
$ok = ($new -ne $old) -and $roundtrip -and ($new -match 'Windows=On') -and ($new -match 'ServerDll=basesrv,1') -and ($new -match 'csrss\.exe')

if (-not $ok) {
  Write-Host "[ABORT] 무결성 가드 실패 — 레지스트리 미변경(안전). 값 형식이 예상과 다릅니다." -ForegroundColor Red
  Read-Host "Enter를 눌러 닫기"; exit 1
}

# 원본 백업(가역성)
Set-Content -Path $bak -Value $old -Encoding UTF8
Write-Host "원본 백업 저장: $bak" -ForegroundColor DarkGray

# REG_EXPAND_SZ 타입 반드시 보존
try {
  Set-ItemProperty -Path $key -Name Windows -Value $new -Type ExpandString
} catch {
  Write-Host "[ERROR] 쓰기 실패 ($($_.Exception.Message)). 관리자 권한이 아닙니다." -ForegroundColor Red
  Read-Host "Enter를 눌러 닫기"; exit 1
}

$after = (Get-ItemProperty -Path $key -Name Windows).Windows
$kind  = (Get-Item $key).GetValueKind('Windows')
if ($after -eq $new -and $kind -eq 'ExpandString') {
  Write-Host ""
  Write-Host "[SUCCESS] 데스크톱 힙 20480 -> 40960 적용 완료." -ForegroundColor Green
  Write-Host "적용 값:" -ForegroundColor Cyan
  Write-Host "  $after"
  Write-Host ""
  Write-Host ">>> 이제 PC를 재부팅하면 발효됩니다. 재부팅 후 python/git 오류 대화상자가 사라집니다." -ForegroundColor Green
} else {
  Write-Host "[MISMATCH] 적용값 확인 필요. 백업으로 복구 가능: $bak" -ForegroundColor Red
}
Read-Host "Enter를 눌러 닫기"
