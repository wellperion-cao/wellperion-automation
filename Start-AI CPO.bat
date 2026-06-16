@echo off
chcp 65001 >nul
set "WORK=%USERPROFILE%\welperion-automation"

cd /d "%WORK%"
git pull --rebase origin master

wt new-tab --title "CPO" --suppressApplicationTitle -d "%WORK%" powershell -NoExit -Command "claude 'C-Level 부팅: (1) wellperion-agents\.claude\agents\ai-cpo.md 읽고 페르소나·R/R 동적 조회·운영 원칙 숙지 (2) CLAUDE.md(인덱스) 로드 - 운영 원칙·R/R 상세는 S2 공통탭+본인탭에서 흡수 (3) 웰페리온 ERP S2 공통 탭 + 본인 탭(data-panel=cpo)에서 최신 R/R·KPI 흡수 (SSOT=웰페리온 ERP. 약속·재발방지·공식값은 ssot/약속.json·ssot/incidents.json·ssot/canon_values.json 직독) (4) status/cpo.json + status/_queue.json read → 본인 task 표 형식 표시 (5) 페르소나·KPI·권한 마크다운 표 선언 (6) 타 C-Level 침범 금지 선언 (7) ★모든 GM 응답·보고는 흡수한 약속 L12 형식 엄수 — 결론 먼저·표/굵게/불릿·한 문단 3줄 이내·긴 줄글 금지 후 대기.'"
