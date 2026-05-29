@echo off
chcp 65001 >nul
set "WORK=%USERPROFILE%\welperion-automation"

wt new-tab --title "CHRO" --suppressApplicationTitle -d "%WORK%" powershell -NoExit -Command "claude 'C-Level 부팅: (1) notion-c-level-agents\.claude\agents\ai-chro.md 읽고 페르소나·R/R 동적 조회·운영 원칙 숙지 (2) 메인 CLAUDE.md 헌법 로드 (3) Notion AI 조직 DB(Data Source 33f0407d-a948-80d2-ad27-000b132ef146)에서 AI CHRO 최신 R/R 흡수 (4) 페르소나·KPI·권한 마크다운 표 선언 (5) 타 C-Level 침범 금지 선언 후 대기.'"
