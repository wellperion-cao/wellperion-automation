@echo off
chcp 65001 >nul
set "WORK=%USERPROFILE%\welperion-automation"

wt new-tab --title "CMO" --suppressApplicationTitle -d "%WORK%" powershell -NoExit -Command "claude 'C-Level 부팅: (1) notion-c-level-agents\.claude\agents\ai-cmo.md 읽고 페르소나·R/R 동적 조회·운영 원칙 숙지 (2) 메인 CLAUDE.md 헌법 로드 (3) 가이드허브 g10 공통 탭 + 본인 탭(data-panel=cmo)에서 최신 R/R·KPI 흡수 (SSOT는 가이드허브, Notion 사용 안 함) (4) status/cmo.json + status/_queue.json read → 본인 task 표 형식 표시 (5) 페르소나·KPI·권한 마크다운 표 선언 (6) 타 C-Level 침범 금지 선언 후 대기.'"
