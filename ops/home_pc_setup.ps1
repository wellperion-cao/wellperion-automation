<#
  ops/home_pc_setup.ps1 — 집 PC 에 회사 PC 와 같은 Claude Code CLI 환경을 만든다.
  (GM 지시 2026-09-08 "집 PC 에 회사환경과 똑같이 CLI 설치")

  실행 (PowerShell · 관리자 권한은 스크립트가 스스로 올린다):
    powershell -NoProfile -ExecutionPolicy Bypass -File home_pc_setup.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File home_pc_setup.ps1 -ConfigZip "C:\...\wellperion_claude_config.zip"

  인자
    -ConfigZip   회사 PC 에서 ops\export_claude_config.bat 로 만든 zip. 생략하면 바탕화면·다운로드에서 찾는다.
    -SkipWinget  Git·Node·Python·Windows Terminal 설치 단계를 건너뛴다(이미 있을 때).
    -SkipVenv    wellperion-agents\venv 생성·pip 설치를 건너뛴다.

  만드는 것 (회사 PC 표준 = Start-AI *.bat · scripts\ensure_statusline.py 가 기대하는 모양)
    1. Git · Node.js LTS · Python 3.14 (C:\Python314 고정 경로) · Windows Terminal   ← winget
    2. Claude Code CLI(@anthropic-ai/claude-code) · OMC(oh-my-claude-sisyphus)         ← npm -g
    3. 저장소 %USERPROFILE%\welperion-automation  clone + git 설정(autoStash off · autocrlf) + git hooks
    4. Python 의존성(전역 최소) + wellperion-agents\venv (clevel.bat 이 쓴다)
    5. ~\.claude  — 회사 zip 이 있으면 그대로 복원(설정·스킬·플러그인·HUD), 없으면 기본값 + caveman 스킬 + OMC 플러그인
    6. .claude\settings.local.json 훅 3종(PreToolUse·UserPromptSubmit·Stop) + statusline 자가복구
  하지 않는 것 (집 PC 에서 돌리면 안 된다)
    - 텔레그램 봇·daily_scheduler·예약작업 등록 · Startup 폴더 아침 부팅 바로가기 · telegram_bot\.env 복사
      → 회사 PC 가 상시 가동 중이라 집에서 또 띄우면 getUpdates 409(중복 봇) 가 난다.
  안전: 각 단계는 실패해도 다음 단계로 간다. 끝에 점검표를 찍는다. 로그 = logs\home_pc_setup.log
#>
param(
  [string]$ConfigZip = "",
  [string]$RepoUrl   = "https://github.com/wellperion-cao/wellperion-automation.git",
  [switch]$SkipWinget,
  [switch]$SkipVenv
)
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

# ── 관리자 권한으로 자기 자신을 다시 연다 (Python 을 C:\Python314 에 전체 사용자용으로 깔려면 필요) ──
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
  $fwd = @()
  if ($ConfigZip)  { $fwd += "-ConfigZip `"$ConfigZip`"" }
  if ($RepoUrl -ne "https://github.com/wellperion-cao/wellperion-automation.git") { $fwd += "-RepoUrl `"$RepoUrl`"" }
  if ($SkipWinget) { $fwd += "-SkipWinget" }
  if ($SkipVenv)   { $fwd += "-SkipVenv" }
  Write-Host "관리자 권한으로 다시 엽니다(UAC 창에서 '예')..."
  Start-Process powershell -Verb RunAs -ArgumentList ("-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$PSCommandPath`" " + ($fwd -join ' '))
  exit
}

$Work      = Join-Path $env:USERPROFILE 'welperion-automation'
# 저장소 주소는 -RepoUrl 로 바꾼다(위 param). 저장소를 비공개로 돌리거나 다른 곳으로 옮기면
# 그 인자만 주면 된다 — 비공개면 첫 clone 때 로그인을 한 번 묻는다(막힌 게 아니라 정상이다).
$Py        = 'C:\Python314\python.exe'
$ClaudeDir = Join-Path $env:USERPROFILE '.claude'
$Report    = New-Object System.Collections.ArrayList
$LogDir    = if (Test-Path $Work) { Join-Path $Work 'logs' } else { $env:TEMP }
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Log       = Join-Path $LogDir 'home_pc_setup.log'

function Log([string]$m) { $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m; Write-Host $line; Add-Content -Path $Log -Value $line -Encoding UTF8 }
function Step([string]$m) { Write-Host ""; Log ("== " + $m) }
function Note([string]$k, [string]$v) { [void]$Report.Add(@{k=$k; v=$v}) }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
  # npm 전역 bin 은 사용자 PATH 에 나중에 붙는다 — 이 세션에서 바로 쓰려면 직접 얹는다.
  $npmBin = Join-Path $env:APPDATA 'npm'
  if ((Test-Path $npmBin) -and ($env:Path -notlike "*$npmBin*")) { $env:Path += ";$npmBin" }
  if ((Test-Path 'C:\Python314') -and ($env:Path -notlike '*C:\Python314*')) { $env:Path = 'C:\Python314;C:\Python314\Scripts;' + $env:Path }
}
function Has([string]$exe) { return [bool](Get-Command $exe -ErrorAction SilentlyContinue) }
function Winget-Install([string]$id, [string]$override = "") {
  $wa = @('install','-e','--id',$id,'--accept-source-agreements','--accept-package-agreements','--silent')
  if ($override) { $wa += @('--override', $override) }
  Log ("winget " + ($wa -join ' '))
  & winget @wa 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
  return $LASTEXITCODE
}

# ═══ 1. 기반 도구 ═══════════════════════════════════════════════════════════
Step "1/6 기반 도구 (Git · Node LTS · Python 3.14 · Windows Terminal)"
if ($SkipWinget) {
  Log "-SkipWinget: 건너뜀"
} elseif (-not (Has 'winget')) {
  Log "[경고] winget 이 없다. Microsoft Store 에서 '앱 설치 관리자'를 설치한 뒤 다시 실행. 이 단계는 건너뛴다."
  Note '기반 도구' 'winget 없음 - 수동 설치 필요'
} else {
  if (-not (Has 'git'))  { Winget-Install 'Git.Git' | Out-Null }           else { Log "git 있음: $(git --version)" }
  if (-not (Has 'node')) { Winget-Install 'OpenJS.NodeJS.LTS' | Out-Null } else { Log "node 있음: $(node -v)" }
  if (-not (Test-Path $Py)) {
    # 회사 PC 표준 경로 = C:\Python314 (Start-AI *.bat · auto_next_ship_hook.cmd 가 이 절대경로를 부른다)
    Winget-Install 'Python.Python.3.14' '/quiet InstallAllUsers=1 TargetDir=C:\Python314 PrependPath=1 Include_launcher=1 Include_test=0' | Out-Null
    Refresh-Path
    if (-not (Test-Path $Py)) {
      # 이미 다른 위치에 3.14 가 있으면 C:\Python314 를 그쪽으로 잇는다(정션). 배치들이 절대경로만 알기 때문.
      $found = Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python\Python314", "C:\Program Files\Python314" -Filter python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($found) { cmd /c mklink /J C:\Python314 "$($found.DirectoryName)" | Out-Null; Log "정션 C:\Python314 -> $($found.DirectoryName)" }
    }
  } else { Log "python 있음: $(& $Py --version)" }
  if (-not (Has 'wt')) { Winget-Install 'Microsoft.WindowsTerminal' | Out-Null } else { Log "Windows Terminal 있음" }
}
Refresh-Path
Note 'git'    $(if (Has 'git')  { git --version } else { '없음' })
Note 'node'   $(if (Has 'node') { node -v }       else { '없음' })
Note 'python' $(if (Test-Path $Py) { & $Py --version } else { "없음 ($Py)" })
Note 'wt'     $(if (Has 'wt') { '있음' } else { '없음(Resume-AI.bat 만 영향)' })

# ═══ 2. Claude Code CLI + OMC ══════════════════════════════════════════════
Step "2/6 Claude Code CLI · OMC (npm 전역)"
if (Has 'npm') {
  Log "npm install -g @anthropic-ai/claude-code@latest"
  npm install -g @anthropic-ai/claude-code@latest 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
  Log "npm install -g oh-my-claude-sisyphus@latest  (OMC · ops\morning_update.bat Step 3 과 동일)"
  npm install -g oh-my-claude-sisyphus@latest 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
  Refresh-Path
} else { Log "[경고] npm 없음 - Node 설치 뒤 다시 실행" }
Note 'claude' $(if (Has 'claude') { (claude --version 2>$null | Select-Object -First 1) } else { '없음' })

# ═══ 3. 저장소 ═════════════════════════════════════════════════════════════
Step "3/6 저장소 $Work"
if (Has 'git') {
  if (-not (Test-Path (Join-Path $Work '.git'))) {
    Log "git clone $RepoUrl"
    Log "  (저장소가 비공개면 여기서 로그인을 한 번 묻는다 - 정상)"
    git clone $RepoUrl $Work 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
  } else {
    Log "이미 있음 - git pull --rebase origin master"
    git -C $Work pull --rebase origin master 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
  }
  if (Test-Path (Join-Path $Work '.git')) {
    # Start-AI *.bat 이 매 부팅 끄는 값 — 처음부터 꺼 둔다(2026-09-02 자체 표류 사고 뿌리).
    git -C $Work config --local rebase.autoStash false
    git -C $Work config --local core.autocrlf true
    if (-not (git config --global user.name))  { $n = Read-Host 'git user.name (회사 PC 와 같게)';  if ($n) { git config --global user.name  $n } }
    if (-not (git config --global user.email)) { $e = Read-Host 'git user.email (회사 PC 와 같게)'; if ($e) { git config --global user.email $e } }
    # git hooks (pre-commit 가드 · post-commit 자동 push · pre-push 자물쇠 · _queue.json 머지 드라이버)
    $bash = @("$env:ProgramFiles\Git\bin\bash.exe", "${env:ProgramFiles(x86)}\Git\bin\bash.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($bash) {
      $wposix = $Work -replace '\\','/'
      & $bash -c "cd '$wposix' && sh scripts/install_hooks.sh" 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
      Note 'git hooks' $(if (Test-Path (Join-Path $Work '.git\hooks\post-commit')) { '설치됨' } else { '실패 - sh scripts/install_hooks.sh 수동' })
    } else { Note 'git hooks' 'Git Bash 못 찾음 - sh scripts/install_hooks.sh 수동' }
    if ($LogDir -eq $env:TEMP) { $LogDir = Join-Path $Work 'logs'; New-Item -ItemType Directory -Path $LogDir -Force | Out-Null; Copy-Item $Log (Join-Path $LogDir 'home_pc_setup.log') -Force; $Log = Join-Path $LogDir 'home_pc_setup.log' }
  }
}
Note '저장소' $(if (Test-Path (Join-Path $Work '.git')) { $Work } else { 'clone 실패' })

# ═══ 4. Python 의존성 ══════════════════════════════════════════════════════
Step "4/6 Python 의존성"
if (Test-Path $Py) {
  # 부팅 경로(boot_pack·hangro_board·kungjjak_board·worklog·훅)는 표준 라이브러리만 쓴다.
  # 전역에는 알림·HTTP 최소 세트만. 나머지는 venv.
  & $Py -m pip install --upgrade pip --quiet 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
  & $Py -m pip install --quiet requests python-dotenv httpx pillow 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
  Note 'pip 전역' 'requests·python-dotenv·httpx·pillow'
  $venv = Join-Path $Work 'wellperion-agents\venv'
  $req  = Join-Path $Work 'ops\requirements_home_pc.txt'
  if ($SkipVenv) { Log "-SkipVenv: 건너뜀" }
  elseif (Test-Path $req) {
    if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) { & $Py -m venv $venv 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null }
    & (Join-Path $venv 'Scripts\python.exe') -m pip install --quiet -r $req 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
    Note 'venv' $(if ($LASTEXITCODE -eq 0) { "$venv (requirements_home_pc.txt)" } else { "일부 실패 - 로그 확인" })
  }
} else { Log "[경고] $Py 없음 - 건너뜀"; Note 'pip' 'python 없음' }

# ═══ 5. ~\.claude (회사 설정 복원 또는 기본 구성) ══════════════════════════
Step "5/6 Claude 설정 ($ClaudeDir)"
New-Item -ItemType Directory -Path $ClaudeDir -Force | Out-Null
if (-not $ConfigZip) {
  $cands = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'wellperion_claude_config.zip'),
    (Join-Path $env:USERPROFILE 'Downloads\wellperion_claude_config.zip'),
    (Join-Path $env:USERPROFILE 'OneDrive\Desktop\wellperion_claude_config.zip'),
    (Join-Path $env:USERPROFILE 'OneDrive\바탕 화면\wellperion_claude_config.zip')
  )
  $ConfigZip = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if ($ConfigZip -and (Test-Path $ConfigZip)) {
  # ── 회사 PC 그대로: settings.json · keybindings · CLAUDE.md · skills · commands · agents · hud · plugins ──
  $tmp = Join-Path $env:TEMP 'wp_claude_import'
  if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
  Expand-Archive -Path $ConfigZip -DestinationPath $tmp -Force
  foreach ($item in 'settings.json','keybindings.json','CLAUDE.md','skills','commands','agents','hud','plugins') {
    $src = Join-Path $tmp $item
    if (Test-Path $src) { Copy-Item $src (Join-Path $ClaudeDir $item) -Recurse -Force; Log "복원: $item" }
  }
  # 회사 ~\.claude.json 에서 mcpServers 만 가져온다(계정·토큰은 안 옮긴다 — 집에서 claude 로그인).
  $company = Join-Path $tmp 'claude.json.company'
  if ((Test-Path $company) -and (Test-Path $Py)) {
    $merge = @"
import json, os, sys
home = os.path.join(os.path.expanduser('~'), '.claude.json')
src = json.load(open(sys.argv[1], encoding='utf-8'))
dst = json.load(open(home, encoding='utf-8')) if os.path.exists(home) else {}
if src.get('mcpServers'):
    dst.setdefault('mcpServers', {}).update(src['mcpServers'])
    json.dump(dst, open(home, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('mcpServers 병합:', ', '.join(src['mcpServers']))
else:
    print('mcpServers 없음 - 건너뜀')
"@
    $mergePy = Join-Path $tmp '_merge_mcp.py'; Set-Content -Path $mergePy -Value $merge -Encoding UTF8
    & $Py $mergePy $company 2>&1 | Tee-Object -FilePath $Log -Append
  }
  $inv = Join-Path $tmp 'company_inventory.txt'
  if (Test-Path $inv) { Copy-Item $inv (Join-Path $LogDir 'company_inventory.txt') -Force; Log "회사 인벤토리 -> logs\company_inventory.txt (pip·npm·플러그인 대조용)" }
  Note '.claude' "회사 zip 복원: $ConfigZip"
} else {
  # ── zip 없음: 회사 표준 최소 구성 ──
  $settings = Join-Path $ClaudeDir 'settings.json'
  if (-not (Test-Path $settings)) {
    # 전역 기본 모델 = Fable 5.1 (CLAUDE.md §4 · 1M 컨텍스트 미사용)
    # BOM 없는 UTF-8 로 쓴다 — Set-Content -Encoding UTF8 은 BOM 을 붙여 JSON 파서가 깨진다.
    [IO.File]::WriteAllText($settings, '{ "model": "claude-fable-5-1" }', (New-Object Text.UTF8Encoding $false))
    Log "settings.json 생성 (model=claude-fable-5-1)"
  }
  # caveman 스킬 (CLAUDE.md §4 1-1 · 회사 PC 설치 기록 2026-08-04: JuliusBrussee/caveman 의 skills/caveman 만)
  $cave = Join-Path $ClaudeDir 'skills\caveman'
  if ((-not (Test-Path $cave)) -and (Has 'git')) {
    $ct = Join-Path $env:TEMP 'wp_caveman'
    if (Test-Path $ct) { Remove-Item $ct -Recurse -Force }
    git clone --depth 1 https://github.com/JuliusBrussee/caveman $ct 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
    if (Test-Path (Join-Path $ct 'skills\caveman')) { New-Item -ItemType Directory -Path (Split-Path $cave) -Force | Out-Null; Copy-Item (Join-Path $ct 'skills\caveman') $cave -Recurse -Force; Log "caveman 스킬 설치" }
    if (Test-Path $ct) { Remove-Item $ct -Recurse -Force }
  }
  # OMC 플러그인 (Start-AI *.bat 이 매 부팅 update 하는 oh-my-claudecode@omc)
  if (Has 'claude') {
    claude plugin marketplace add Yeachan-Heo/oh-my-claudecode 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
    claude plugin install oh-my-claudecode@omc 2>&1 | Tee-Object -FilePath $Log -Append | Out-Null
  }
  Note '.claude' '기본 구성(zip 없음) - ponytail·graphify·headroom 은 회사 zip 으로만 복원됨'
}

# ═══ 6. 저장소 로컬 훅 + statusline ═══════════════════════════════════════
Step "6/6 .claude\settings.local.json 훅 · statusline"
$localDir = Join-Path $Work '.claude'
$local    = Join-Path $localDir 'settings.local.json'
$tpl      = Join-Path $Work 'ops\settings.local.template.json'
if ((-not (Test-Path $local)) -and (Test-Path $tpl)) {
  New-Item -ItemType Directory -Path $localDir -Force | Out-Null
  Copy-Item $tpl $local -Force
  Log "settings.local.json 생성 (템플릿: PreToolUse 셸가드 · UserPromptSubmit 접수 · Stop 다음배)"
}
if ((Test-Path $Py) -and (Test-Path (Join-Path $Work 'scripts\ensure_statusline.py'))) {
  Push-Location $Work
  & $Py scripts\ensure_statusline.py 2>&1 | Tee-Object -FilePath $Log -Append
  Pop-Location
}
Note 'settings.local.json' $(if (Test-Path $local) { '있음' } else { '없음' })

# ═══ 점검표 ════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "══════════════ 집 PC 설치 점검표 ══════════════"
foreach ($r in $Report) { Write-Host ("  {0,-22} {1}" -f $r.k, $r.v) }
Write-Host "  로그                   $Log"
Write-Host ""
Write-Host "다음 할 일 (사람이 1회)"
Write-Host "  1. 새 PowerShell 창을 열고  claude  → /login  (회사와 같은 계정)"
Write-Host "  2. $Work 에서 'Start-AI CEO.bat' 더블클릭 → 부팅 선언 표·상태줄 확인"
Write-Host "  3. 텔레그램 봇·스케줄러·예약작업·Startup 바로가기는 집 PC 에 만들지 않는다(회사 PC 가 상시 가동)"
Write-Host "  4. zip 없이 설치했으면 ponytail·graphify·headroom 은 회사 PC 에서 ops\export_claude_config.bat 로 zip 을 만들어 -ConfigZip 으로 한 번 더 실행"
Write-Host "  * 이 스크립트를 다시 받을 곳 = ERP 모듈홈 > 다운로드 탭 (https://erp.wellperion.com/erp/)"
