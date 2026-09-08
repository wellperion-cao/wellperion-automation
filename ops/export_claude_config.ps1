<#
  ops/export_claude_config.ps1 — 회사 PC 의 Claude 설정을 zip 하나로 내보낸다 (집 PC 복원용).
  실행: ops\export_claude_config.bat 더블클릭  (또는 powershell -ExecutionPolicy Bypass -File 이 파일)
  결과: 바탕화면\wellperion_claude_config.zip  → 집 PC 로 옮겨 ops\home_pc_setup.ps1 -ConfigZip 으로 복원

  담는 것  ~\.claude\ settings.json · keybindings.json · CLAUDE.md · skills\ · commands\ · agents\ · hud\ · plugins\
           ~\.claude.json 사본(claude.json.company — 복원 때 mcpServers 만 가져간다)
           company_inventory.txt (버전·npm 전역·pip·플러그인 목록 — 집에서 대조용)
  안 담는 것  .credentials.json(로그인 토큰) · projects\ · sessions\ · shell-snapshots\ · todos\ · history · 캐시
              → 토큰은 절대 옮기지 않는다. 집 PC 는 claude /login 으로 따로 로그인.
#>
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$src = Join-Path $env:USERPROFILE '.claude'
$tmp = Join-Path $env:TEMP 'wp_claude_export'
$out = Join-Path ([Environment]::GetFolderPath('Desktop')) 'wellperion_claude_config.zip'
if (-not (Test-Path $src)) { Write-Host "~\.claude 가 없습니다: $src"; exit 1 }
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Path $tmp -Force | Out-Null

foreach ($item in 'settings.json','keybindings.json','CLAUDE.md','skills','commands','agents','hud','plugins') {
  $p = Join-Path $src $item
  if (Test-Path $p) { Copy-Item $p (Join-Path $tmp $item) -Recurse -Force; Write-Host "담음: $item" }
}
# 플러그인 폴더 안의 대용량 캐시·저장소 메타는 뺀다(플러그인 코드 자체는 남긴다).
Get-ChildItem (Join-Path $tmp 'plugins') -Recurse -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -in @('.git','node_modules','__pycache__') } |
  ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

$cj = Join-Path $env:USERPROFILE '.claude.json'
if (Test-Path $cj) { Copy-Item $cj (Join-Path $tmp 'claude.json.company') -Force; Write-Host "담음: .claude.json (mcpServers 용)" }

# 대조용 인벤토리
$inv = Join-Path $tmp 'company_inventory.txt'
$lines = @("# 회사 PC 인벤토리 $(Get-Date -Format 'yyyy-MM-dd HH:mm')  ($env:COMPUTERNAME / $env:USERNAME)")
foreach ($c in @('claude --version','node -v','npm -v','git --version','C:\Python314\python.exe --version','wt -v')) {
  try { $lines += "`n## $c"; $lines += (cmd /c "$c 2>&1") } catch { $lines += "(실패)" }
}
$lines += "`n## npm ls -g --depth=0";        $lines += (cmd /c "npm ls -g --depth=0 2>&1")
$lines += "`n## claude plugin list";         $lines += (cmd /c "claude plugin list 2>&1")
$lines += "`n## claude plugin marketplace list"; $lines += (cmd /c "claude plugin marketplace list 2>&1")
$lines += "`n## pip list (C:\Python314)";    $lines += (cmd /c "C:\Python314\python.exe -m pip list 2>&1")
$venvPy = Join-Path $env:USERPROFILE 'welperion-automation\wellperion-agents\venv\Scripts\python.exe'
if (Test-Path $venvPy) { $lines += "`n## pip list (wellperion-agents\venv)"; $lines += (cmd /c "`"$venvPy`" -m pip list 2>&1") }
foreach ($t in 'graphify','headroom','ponytail','omc','uv','pipx') { $lines += "`n## where $t"; $lines += (cmd /c "where $t 2>&1") }
$lines += "`n## ~\.claude 1단계 목록"; $lines += (Get-ChildItem $src -Force | ForEach-Object { $_.Name })
$lines | Set-Content -Path $inv -Encoding UTF8

if (Test-Path $out) { Remove-Item $out -Force }
Compress-Archive -Path (Join-Path $tmp '*') -DestinationPath $out -CompressionLevel Optimal
Remove-Item $tmp -Recurse -Force
Write-Host ""
Write-Host "완료: $out  ($([math]::Round((Get-Item $out).Length/1MB,1)) MB)"
Write-Host "→ 이 zip 을 집 PC 바탕화면에 두고 ops\home_pc_setup.bat 을 실행하면 자동으로 복원됩니다."
Write-Host "   (.credentials.json 은 넣지 않았습니다 — 집에서 claude /login)"
