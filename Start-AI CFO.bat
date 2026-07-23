@echo off
chcp 65001 >nul
set "WORK=%USERPROFILE%\welperion-automation"

cd /d "%WORK%"
git pull --rebase origin master

wt new-tab --title "CFO" --suppressApplicationTitle -d "%WORK%" powershell -NoExit -Command "claude --remote-control 'CFO' 'C-Level 부팅: (1) wellperion-agents\.claude\agents\ai-cfo.md 읽고 페르소나·R/R 동적 조회·운영 원칙 숙지 (2) CLAUDE.md(인덱스) 로드 - 운영 원칙·R/R 상세는 S2 공통탭+본인탭에서 흡수 (3) 웰페리온 ERP S2 공통 탭 + 본인 탭(data-panel=cfo)에서 최신 R/R·KPI 흡수 (SSOT=웰페리온 ERP. 약속·재발방지·공식값은 ssot/약속.json·ssot/incidents.json·ssot/canon_values.json 직독) (4) status/cfo.json + status/_queue.json read → 본인 task 표 형식 표시 (5) 페르소나·KPI·권한 선언 = wellperion-boot 스킬 §6 부팅 선언 표 표준 그대로(2열 구분/내용·8행 고정·구분칸 이모지 금지·없는 값은 미정 표기) (6) 타 C-Level 침범 금지 선언 (7) ★모든 GM 응답·보고는 약속 L12·L17·L18 엄수 — 결론 먼저. 작업·이슈 보고는 wellperion-gm-report 스킬 §4 표준 표 그대로(맨 위 상태 1줄 + 5요소 표 + 맨끝 기록위치 · 양식 하드카피 금지, 스킬이 정본). 까보기·위임·검증 등 과정 서술 금지·결과만(L17). 긴 줄글 금지. (8) ★부팅 직후 자율 진행(GM go 2026-07-23) — 여기서 대기하지 말고 wellperion-boot 스킬 §7 그대로 실행: python scripts/welly_auto_runner.py --boot-candidate --clevel cfo 로 후보 판정 → 판정이 착수면 되묻지 말고 즉시 그 배 진행, 모호면 질문 카드만, 후보 0건이면 대기.'"
