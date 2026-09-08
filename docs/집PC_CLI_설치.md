# 집 PC — 회사와 같은 Claude Code CLI 환경 설치

> 정본 = 이 문서 + `ops/home_pc_setup.ps1`. 회사 PC 표준(경로·모델·훅·상태줄)은 `Start-AI *.bat`·`scripts/ensure_statusline.py` 가 기대하는 모양 그대로다. (GM 지시 2026-09-08)

## 1. 회사 환경이란 무엇인가 (집에 그대로 옮기는 항목)

| 구분 | 회사 PC 표준 | 집 PC 에서 |
|---|---|---|
| 저장소 | `%USERPROFILE%\welperion-automation` (master) | 같은 위치에 clone · `rebase.autoStash=false` · `core.autocrlf=true` · git hooks 3종 |
| Python | `C:\Python314\python.exe` (절대경로를 배치·훅이 부른다) | winget 으로 같은 경로에 설치, 없으면 정션 |
| Node · CLI | Node LTS · `@anthropic-ai/claude-code` · OMC(`oh-my-claude-sisyphus` + 플러그인 `oh-my-claudecode@omc`) | npm -g 동일 |
| 터미널 | Windows Terminal(`wt` — Resume-AI.bat 이 쓴다) | winget |
| 세션 모델 | 8석 전부 Fable 5.1 (`--model claude-fable-5-1`, 배치 안에 있음) · 전역 기본도 Fable 5.1 | 배치가 저장소에 있으니 자동. 전역 `~/.claude/settings.json` 은 zip 복원 또는 기본 생성 |
| 말투·스킬 | `~/.claude/skills/caveman` (JuliusBrussee/caveman) · 저장소 `.claude/skills` 5종·`commands` 5종 | zip 복원 또는 GitHub 에서 자동 설치 / 저장소 것은 clone 에 포함 |
| 외부 도구 3종 | ponytail · graphify · headroom (`~/.claude/plugins` 등, 설치 출처는 저장소에 기록 없음) | **회사 zip 으로만** 그대로 복원된다 |
| 저장소 로컬 훅 | `.claude/settings.local.json` — PreToolUse 셸 첫줄 가드 · UserPromptSubmit 지시 접수(`--recall`) · Stop 다음 배 | git 무시 파일이라 `ops/settings.local.template.json` 에서 생성 |
| 상태줄 | `scripts/wellperion_hud.mjs` (OMC HUD 래핑) | `ensure_statusline.py` 가 부팅마다 자가복구 |
| venv | `wellperion-agents\venv` (clevel.bat 이 쓴다) | `ops/requirements_home_pc.txt` 로 생성 |

집 PC 에 **만들지 않는 것**: 텔레그램 봇·`daily_scheduler`·예약작업(`ops/register_*.bat`)·Startup 폴더 아침 부팅 바로가기·`telegram_bot/.env`. 회사 PC 가 상시 가동 중이라 집에서 또 띄우면 봇이 409(중복)로 죽는다. 집 PC 는 **CLI 세션 전용**이다.

## 2. 순서 (3단계)

### ① 회사 PC — 설정 zip 만들기 (1분)
`ops\export_claude_config.bat` 더블클릭 → 바탕화면 `wellperion_claude_config.zip`.
담는 것: `~/.claude` 의 settings·keybindings·CLAUDE.md·skills·commands·agents·hud·plugins, `~/.claude.json` 사본(mcpServers 만 쓴다), `company_inventory.txt`(버전·npm·pip·플러그인 목록).
**안 담는 것: `.credentials.json`(로그인 토큰)·세션 기록·캐시.** 토큰은 절대 옮기지 않는다.

### ② 집 PC — 설치 (10~20분, 인터넷 필요)
zip 을 집 PC 바탕화면(또는 다운로드)에 둔다. 그리고 **ERP 모듈홈**(`https://erp.wellperion.com/erp/`) → **「다운로드」 탭** → **「관리자 AI」** 를 받아 더블클릭한다. 파일 배포는 **회사 서버(AWS)에서만** 한다 — 외부 저장소 주소로 받지 않는다.

명령으로 하려면 PowerShell 에서:
```powershell
Invoke-WebRequest https://erp.wellperion.com/erp/launchers/home_pc_setup.ps1 -OutFile "$env:TEMP\home_pc_setup.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\home_pc_setup.ps1"
```
(저장소가 이미 있으면 `ops\home_pc_setup.bat` 더블클릭이면 된다. zip 위치를 직접 주려면 `-ConfigZip "경로"`.)

> ⚠️ **저장소 본체는 아직 GitHub 에 있다.** 설치 3단계 중 「저장소 내려받기」만 그렇다(`-RepoUrl` 인자로 옮길 수 있게 빼 두었다). 저장소를 비공개로 돌리면 이 단계에서 로그인을 한 번 묻는다 — 막힌 게 아니라 정상이다.
스크립트는 관리자 권한을 스스로 올리고(UAC '예'), 6단계를 돌고, 끝에 점검표를 찍는다. 각 단계는 실패해도 다음으로 간다. 로그 = `logs\home_pc_setup.log`.

### ③ 집 PC — 사람이 1회
1. 새 PowerShell 창 → `claude` → `/login` (회사와 같은 계정).
2. `%USERPROFILE%\welperion-automation\Start-AI CEO.bat` 더블클릭 → 부팅 선언 표·상태줄이 뜨면 끝.
3. `logs\company_inventory.txt` 와 집 PC 의 `claude plugin list`·`pip list` 를 대조해 빠진 것이 있으면 그것만 추가.

## 3. 다시 실행·부분 실행
- 멱등이다. 몇 번 돌려도 이미 있는 것은 건너뛴다.
- `-SkipWinget` 기반 도구 건너뜀 · `-SkipVenv` venv 건너뜀.
- zip 없이 먼저 깔았다가 나중에 zip 이 생기면 `-ConfigZip` 으로 한 번 더 돌리면 `~/.claude` 만 덮어쓴다.

## 4. 자주 걸리는 것
| 증상 | 원인 · 조치 |
|---|---|
| `winget` 없음 | Microsoft Store 에서 "앱 설치 관리자" 설치 후 재실행 |
| `C:\Python314\python.exe` 없음 | 설치가 다른 경로로 갔을 때 스크립트가 정션을 만든다. 그래도 없으면 python.org 3.14 설치 시 "Customize" → 경로 `C:\Python314` |
| 배치 창이 뜨자마자 닫힘 | `.bat` 이 LF 로 저장됨 — `core.autocrlf=true` 가 꺼져 있다. `git config --local core.autocrlf true` 후 `git checkout -- "*.bat"` |
| 상태줄이 회색 한 줄 | OMC HUD(`~/.claude/hud/omc-hud-cost.mjs`) 가 아직 없음 — OMC 플러그인 첫 실행 뒤 생긴다. 다음 부팅에 `ensure_statusline.py` 가 맞춘다 |
| `Resume-AI.bat` 이 세션을 못 찾음 | 집 PC 엔 회사 세션 기록이 없다(정상). 새로 부팅하려면 `Start-AI <역할>.bat` |
| 커밋이 push 안 됨 | git hooks 미설치 — Git Bash 에서 `sh scripts/install_hooks.sh` |

## 4-1. 배포 사본 (ERP 다운로드 탭)
ERP 가 내주는 폴더는 `3. 웰페리온 가이드/erp/launchers/` 다. 그래서 설치 스크립트 사본이 그곳에도 있다 — **정본은 `ops/home_pc_setup.ps1`**. 스크립트를 고치면 두 곳을 같이 고친다. 목록은 `erp/downloads.json` 한 곳만 고치면 되고 화면(`erp/index.html`)은 손대지 않는다.
**이 폴더는 로그인 없이 열리는 공개 통로다 — 회사 자료가 든 파일은 절대 두지 않는다.**

모듈홈 탭은 셋이다 — **화면 / 다운로드 / 권한관리**. 「권한관리」 탭은 **관리자로 로그인했을 때만 뜨고**, 누르면 서버가 내주는 관리자 화면(`/auth/admin`)이 **그 자리에 그대로 뜬다**(끼워넣기 · 페이지 이동 없음). 화면이 안 뜨면 안내문의 「새 창으로 열기」로 연다. 탭을 감추는 것은 보기 편하라는 것이지 잠금이 아니다 — 실제 차단은 서버가 한다(관리자가 아니면 거부, 관리자여도 비밀번호 한 번 더).

설치가 끝나면 그 PC 의 `%USERPROFILE%\welperion-automation\` 안에 **`Start-AI CEO.bat` ~ `Start-AI CBO.bat` 8개**와 **`Resume-AI.bat`**(최근 세션 이어서 열기)이 생긴다. 회사 PC 와 같은 파일이고, 더블클릭이 곧 부팅이다.

## 5. 이번에 같이 고친 것 (사용자명 하드코딩 제거)
회사 사용자명 `jjky0` 절대경로가 박혀 있어 집 PC 에서 깨지던 4곳을 저장소·홈 기준으로 바꿨다: `scripts/worklog.py`(ROOT) · `scripts/session_resume.py`(PROJECT_DIR) · `scripts/skill_inventory.py`(BASE_DIR) · `scripts/wellperion_hud.mjs`(OMC_HUD). 회사 PC 에서는 값이 같아 동작 변화 없다.
