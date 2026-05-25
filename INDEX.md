# 웰페리온 자산 마스터 INDEX

최종 audit 2026-05-23. SSOT = 본 파일 + Notion 마스터 프레임워크.

## 1. 메인 repo (welperion-automation)

| 폴더/파일 | 용도 |
|---|---|
| telegram_bot | 봇 + 스케줄러 (PID 가동) |
| profiles | Playwright 세션 3 프로필 (IG·카페·블로그) |
| scripts | 자동화 파이썬 (Notion·블로그·CMO·COO·CTO) |
| notion-c-level-agents | C-Level 에이전트 정의 + R/R SSOT |
| instagram | CMO 4채널 콘텐츠 작업 ({YYMMDD_콘텐츠명}/) |
| brand | 로고·컬러·가이드 (변경 시 GM 결재) |
| .omc / .claude | 상태·메모리·hooks (자동 갱신) |
| wellperion.bat | 단일 디스패처 (menu/health/inbox) |
| Start-AI {역할}.bat | C-Level별 런처 (cao@wellperion.com SSO) |

## 2. Home (절대 이동 금지)

| 자원 | 용도 |
|---|---|
| .welperion-*-profile (3개) | Playwright 자동발행 세션 (경로 하드코딩) |
| .omc / .claude.json | Claude Code 레지스트리·로그인 |

## 3. Desktop (_정리완료/)

| 폴더 | 용도 |
|---|---|
| 01_업무문서 | 정책·HR·기획 역사 (보존) |
| 02_영상 | 운영 영상 137MB (보존) |
| 03_교육 | AI 교육자료 (매주 월 09:00 자동 이관) |
| 04_기타 | 옵션 자료 (보존) |

## 4. 운영 진입점

| 채널 | 경로 |
|---|---|
| 텔레그램 | @namuki_report_bot (Chat ID 8254867551) |
| Notion 마스터 | https://www.notion.so/AI-CEO-34a0407da94881c59c54dd7cc43b6072 |
| CEO 인박스 DB | https://www.notion.so/fed0015b23cc4faf8acbd3310edf4f72 |

## 5. 갱신 규칙
신규 자산 등록·이동·폐기 시 본 파일 우선 patch → 메모리 동기화.
