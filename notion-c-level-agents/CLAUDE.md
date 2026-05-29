# wellperion-agents — C-Level R/R sub-project

본 폴더는 메인 프로젝트 `welperion-automation/` 의 sub-project다.

## 메인 헌법 참조
운영 헌법·R/R·SSOT 등 모든 규칙은 메인 CLAUDE.md를 우선 따른다:
`C:\Users\jjky0\welperion-automation\CLAUDE.md`

## 본 sub-project 한정 역할
1. AI C-Level 7명 에이전트 정의: `.claude/agents/ai-{ceo|cfo|chro|cmo|coo|cpo|cto}.md`
2. Notion 동기화 도구: `notion_wrapper.py` · `analyze_page.py` · `telegram_notifier.py`
3. 정기 가동 스크립트: `agent_tasks_watcher.py` · `scripts/ceo_morning_brief_08.py` · `pc_boot_greeting.py` · `pc_shutdown_greeting.py`
4. C-Level .bat post-action 훅: `scripts/clevel_post_action.py`

## sub-project 자체 환경
- venv: `wellperion-agents/venv/` (메인 `.venv/` 와 별개)
- .env: HardLink → 메인 `telegram_bot/.env`

## 변경 사항
2026-05-23: 메인 CLAUDE.md 신설 + 본 헌법 흡수. 본 파일은 sub-project 식별·메인 참조 안내만 유지.
