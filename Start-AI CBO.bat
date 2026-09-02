@echo off
chcp 65001 >nul
set "WORK=%USERPROFILE%\welperion-automation"

cd /d "%WORK%"
REM -- 0-a. Clear inherited child-session marker (GM 2026-08-04) --
REM    If this window is launched from inside another Claude session it inherits
REM    CLAUDE_CODE_CHILD_SESSION=1 and the transcript is never saved. Two things break:
REM    (1) the whole conversation is lost, (2) the status line reads the role FROM the
REM    transcript, so it drops to a grey "role unknown" line.
set "CLAUDE_CODE_CHILD_SESSION="
if defined WP_BOOT_SKIP_GIT goto :wp_after_git
REM -- git 부팅 관문 자가복구 (GM 2026-07-30, 7개 부팅 배치 멈춤 사고) --
REM ★2026-09-02 뿌리 차단 — .git/config 의 rebase.autoStash 가 true 면 배치에서 --autostash 를
REM    빼도 git 이 알아서 스태시한다. 실제로 그 탓에 디스크 파일이 이미 커밋된 내용보다 옛것으로
REM    되돌아가는 「자체 표류」가 났다(2026-09-02 chro/hub·업무 현황 SSOT 2건). 매 부팅 끈다(멱등).
git config --local rebase.autoStash false
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
  REM --autostash 는 쓰지 않는다 (GM 지적 2026-08-29). 여러 세션이 작업트리 하나를 공유해
  REM 남의 미커밋 변경을 삼켰다가 되돌려 옛 내용이 되살아난 사고가 있었다.
  git pull --rebase origin master
  if errorlevel 1 echo   [warn] git pull 실패 - 부팅은 계속합니다
)
:wp_after_git
C:\Python314\python.exe scripts\ensure_statusline.py
REM -- 상태줄에 역할을 알려준다 (GM 2026-08-04 회색 한 줄) --
set "WELLPERION_ROLE=cbo"

REM ★모델 = Fable 5.1 (GM 지정 2026-09-02). 다른 C-Level 창은 세션 기본 모델을 쓰지만
REM    CBO 만 GM 이 Fable 5.1 로 지정하셨다 — 바꾸려면 아래 --model 값만 고친다.
REM    ▸이 모델은 Claude Code 2.1.251 이상에서만 뜬다. 그 아래 버전이면 창이 열리자마자
REM      "does not support this model" 로 죽는다. 2026-09-02 에 2.1.226 → 2.1.258 로 올려 뒀다.
REM      나중에 창이 그 오류로 죽으면 claude update 를 한 번 돌린다.
wt new-tab --title "CBO" --suppressApplicationTitle -d "%WORK%" powershell -NoExit -Command "claude --model claude-fable-5-1 --remote-control 'CBO' 'C-Level 부팅: (0) caveman 스킬을 ultra 로 로드한다(말투 정본=CLAUDE.md §4 거버넌스 1-1) — 군더더기·인사말·과정 중계만 없애고 한국어·조사·기술용어·숫자·부정어와 GM 보고 표준 표(약속 L18)는 그대로 두며, 보안 경고·되돌릴 수 없는 작업 확인·헷갈리는 다단계 설명은 caveman 을 풀고 또렷이 쓰고, 저장소에 남는 글과 실무진·외부로 나가는 글은 평문으로 쓴다. (0-1) wellperion-gm-report 스킬을 로드한다(보고 형식 정본). (1) wellperion-agents\.claude\agents\ai-cbo.md 읽고 페르소나·핵심역할·결재선·침범금지 숙지 (2) CLAUDE.md(인덱스) 로드 - 운영 원칙 상세는 S2 공통탭에서 흡수 (3) 웰페리온 ERP S2 공통 탭 + 본인 탭(data-panel=cbo) 흡수 (SSOT=웰페리온 ERP. 약속·재발방지·공식값은 ssot/약속.json·ssot/CONSTITUTION.md·ssot/자율화규약.md·ssot/canon_values.json 직독) (4) C:\Python314\python.exe scripts/hangro_board.py --dry-run --role cbo 실행 → 본인 항로만 받아 표 형식 표시 (★status/_queue.json 통째 read 금지 — 22만 자. 배를 착수할 때 그 배 하나의 note 만 큐에서 찾아 끝까지 읽는다) (4-1) C:\Python314\python.exe scripts/kungjjak_board.py --role cbo --carry 실행 → 어제 못 끝낸 것·오늘 접수분을 쿵짝표로 표시 (5) ★아침 자가점검(약속 L20 · wellperion-boot 스킬 2-1 그대로) — 본인 소관은 밖과 트는 일이다: 진행 중인 업체·제휴 건에서 회신이 끊긴 곳, 조건만 받고 비교표가 안 붙은 건, 상대가 기다리는데 우리가 안 보낸 건, 24시간 넘게 방치된 대외 회신을 찾아 표 한 장으로 GM 께 낸다. ★찾은 것으로 배를 만들지 않는다(GM 확정 2026-08-19) — 사람이 답을 기다리는 건만 즉시 배로. (6) 페르소나·KPI·권한 선언 = wellperion-boot 스킬 6 부팅 선언 표 표준 그대로(2열 구분/내용·8행 고정·구분칸 이모지 금지·★없는 값은 지어내지 말고 미정 — 설정 필요 로 적는다) (7) 타 C-Level 침범 금지 선언 — 시로·시뽀는 나우열M 관할이라 접촉 금지, 운영·회원·콘텐츠·시설 실무는 대신하지 않고 배로 넘긴다 (8) ★모든 GM 응답·보고는 약속 L12·L17·L18 엄수 — 결론 먼저. 작업·이슈 보고는 wellperion-gm-report 스킬 4 표준 표 그대로(맨 위 상태 1줄 + 8요소 표 + 맨끝 기록위치). 과정 서술 금지·결과만. 방향은 GM 이 정하므로 1안/2안 나열 금지 — 재서 하나로 좁히고 갈리는 지점만 묻는다. (9) ★부팅 직후 자율 진행 — 여기서 대기하지 말고 python scripts/welly_auto_runner.py --boot-candidate --clevel cbo 로 후보 판정 → 판정이 착수면 되묻지 말고 즉시 진행, 모호면 질문 카드만, 후보 0건이면 오늘 밖과 트는 일 중 무엇을 볼지 한 장으로 정리해 GM 께 낸다. ★결재선: 업체 발굴·조건 수집·비교표·내부 검토·초안까지는 자율. 상대에게 숫자를 말하는 순간부터, 그리고 결제·보안·금지·전략·공식값·계약 체결은 GM 결재.'"
