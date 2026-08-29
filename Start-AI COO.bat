@echo off
chcp 65001 >nul
set "WORK=%USERPROFILE%\welperion-automation"

cd /d "%WORK%"
REM -- 0-a. Clear inherited child-session marker (GM 2026-08-04) --
REM    If this window is launched from inside another Claude session it inherits
REM    CLAUDE_CODE_CHILD_SESSION=1 and the transcript is never saved. Two things break:
REM    (1) the whole conversation is lost (942 bytes instead of ~12MB),
REM    (2) the status line reads the role FROM the transcript, so it drops to a grey
REM        "role unknown" line and looks like every colour vanished (GM 2026-08-04).
REM    Clearing it costs nothing when it was not set.
set "CLAUDE_CODE_CHILD_SESSION="
REM -- git 부팅 관문 자가복구 (GM 2026-07-30, 7개 부팅 배치 멈춤 사고) --
REM    왜: 자동화가 detached HEAD 로 커밋을 쌓아왔고, 그 상태의 pull --rebase 가
REM    미커밋 대용량 바이너리까지 autostash 로 삼키다 부팅이 멈췄다(stash 35개·287MB).
REM    1) detached 면 master 로 되돌린다 2) autostash 를 끈다 3) 실패해도 부팅은 계속한다.
git symbolic-ref -q HEAD >nul 2>&1
if errorlevel 1 (
  echo   [self-heal] detached HEAD 감지 - master 로 복귀합니다
  git checkout -B master HEAD
)
set DIRTY=0
for /f %%c in ('git status --porcelain ^| find /c /v ""') do set DIRTY=%%c
if %DIRTY% GTR 200 (
  echo   [warn] 미커밋 %DIRTY%개 - pull 건너뜀 ^(대용량 autostash 사고 방지^)
) else (
  REM ★--autostash 제거 (GM 지적 2026-08-29 · 시토). 이 저장소는 여러 세션이 작업트리
  REM    하나를 공유한다. --autostash 는 pull 직전 남의 미커밋 변경을 통째로 스태시했다가
  REM    rebase 뒤 도로 풀어놓는다 — 그 결과 몇 주 묵은 옛 내용이 매일 아침 새 커밋 위에
  REM    덮여 되살아났다(실측: 채용 페이지 2장이 8/25 커밋 내용으로 되돌아가 있었다).
  REM    autostash 없이 두면 트리가 더러울 때 git 이 pull 을 그냥 거부한다 — 정직한 스킵.
  git pull --rebase origin master
  if errorlevel 1 echo   [warn] git pull 실패 - 부팅은 계속합니다
)
REM statusline self-heal (bae10026 / GM 2026-07-24): keep statusLine pointing at
REM scripts\wellperion_hud.mjs. Idempotent, never blocks boot.
C:\Python314\python.exe scripts\ensure_statusline.py
REM -- 상태줄에 역할을 알려준다 (GM 2026-08-04 회색 한 줄) --
REM    상태줄은 대화기록에서 역할을 캐낸다. 부팅 직후엔 기록이 비어 있어 역할 미상
REM    회색 줄로 뜬다. 창을 띄운 이 배치가 미리 알려주면 첫 렌더부터 산다.
REM    (대화기록이 읽히면 그쪽이 이긴다 - wellperion_hud.mjs resolveRole)
set "WELLPERION_ROLE=coo"


wt new-tab --title "COO" --suppressApplicationTitle -d "%WORK%" powershell -NoExit -Command "claude --remote-control 'COO' 'C-Level 부팅: (0) caveman 스킬을 ultra 로 로드한다(말투 정본=CLAUDE.md §4 거버넌스 1-1) — 군더더기·인사말·과정 중계만 없애고 한국어·조사·기술용어·숫자·부정어와 GM 보고 표준 표(약속 L18)는 그대로 두며, 보안 경고·되돌릴 수 없는 작업 확인·헷갈리는 다단계 설명은 caveman 을 풀고 또렷이 쓰고, 저장소에 남는 글과 실무진·외부로 나가는 글은 평문으로 쓴다. (0-1) wellperion-gm-report 스킬을 로드한다(보고 형식 정본). (1) wellperion-agents\.claude\agents\ai-coo.md 읽고 페르소나·R/R 동적 조회·운영 원칙 숙지 (2) CLAUDE.md(인덱스) 로드 - 운영 원칙·R/R 상세는 S2 공통탭+본인탭에서 흡수 (3) 웰페리온 ERP S2 공통 탭 + 본인 탭(data-panel=coo)에서 최신 R/R·KPI 흡수 (SSOT=웰페리온 ERP. 약속·재발방지·공식값은 ssot/약속.json·ssot/incidents.json·ssot/canon_values.json 직독) (4) C:\Python314\python.exe scripts/hangro_board.py --dry-run --role coo 실행 → 본인 항로만 받아 표 형식 표시 (★status/_queue.json 통째 read 금지 — 22만 자·배10369. 배를 착수할 때 그 배 하나의 note 만 큐에서 찾아 끝까지 읽는다) (4-1) C:\Python314\python.exe scripts/kungjjak_board.py --role coo --carry 실행 → 어제 못 끝낸 것·오늘 접수분을 쿵짝표로 표시. 소요시간·저장업로드 칸까지 그대로 GM 께 보인다. (5) ★아침 자가점검(약속 L20 · wellperion-boot 스킬 §2-1 그대로 실행) — status/module_registry.json owner_role=coo 모듈 + 본인 소관 파이프라인을 스스로 훑어 죽은 경로·중복발신·가동끊김·게이트OFF방치·문서불일치·조용한실패를 찾아 발견 즉시 본인 배로 큐에 올린다(수리는 그 다음 — 먼저 표면화) (6) 페르소나·KPI·권한 선언 = wellperion-boot 스킬 §6 부팅 선언 표 표준 그대로(2열 구분/내용·8행 고정·구분칸 이모지 금지·없는 값은 미정 표기) (7) 타 C-Level 침범 금지 선언 (8) ★모든 GM 응답·보고는 약속 L12·L17·L18 엄수 — 결론 먼저. 작업·이슈 보고는 wellperion-gm-report 스킬 §4 표준 표 그대로(맨 위 상태 1줄 + 5요소 표 + 맨끝 기록위치 · 양식 하드카피 금지, 스킬이 정본). 까보기·위임·검증 등 과정 서술 금지·결과만(L17). 긴 줄글 금지. (9) ★부팅 직후 자율 진행(GM go 2026-07-23) — 여기서 대기하지 말고 wellperion-boot 스킬 §7 그대로 실행: python scripts/welly_auto_runner.py --boot-candidate --clevel coo 로 후보 판정 → 판정이 착수면 되묻지 말고 즉시 그 배 진행, 모호면 질문 카드만, 후보 0건이면 대기.'"
