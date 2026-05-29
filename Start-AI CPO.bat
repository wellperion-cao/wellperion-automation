@echo off
chcp 65001 >nul
set "WORK=%USERPROFILE%\welperion-automation"

wt new-tab --title "CPO" --suppressApplicationTitle -d "%WORK%" powershell -NoExit -Command "git pull --rebase origin master 2>$null; claude 'C-Level 부팅: (1) wellperion-agents\.claude\agents\ai-cpo.md 읽고 페르소나·R/R 동적 조회·운영 원칙 숙지 (2) 메인 CLAUDE.md 헌법 로드 (3) 가이드허브 g10 공통 탭 + 본인 탭(data-panel=cpo)에서 최신 R/R·KPI 흡수 (SSOT는 가이드허브, Notion 사용 안 함) (4) status/cpo.json + status/_queue.json read → 본인 task 표 형식 표시 (5) 페르소나·KPI·권한 마크다운 표 선언 (6) 타 C-Level 침범 금지 선언 후 대기.'"
