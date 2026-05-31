# 경로 표준화 기록 — 웰페리온 자동화 시스템

## 발생일
2026-04-17

## 오표기 원인
기획서(Notion Stage 3 승인본) 내 폴더 경로가 `Desktop\welperion-automation`으로 기재되었으나,
실제 설치 위치는 `C:\Users\jjky0\welperion-automation` (Desktop 아님).

## 표준 경로 (SSOT 확정)

| 구분 | 경로 |
|------|------|
| 프로젝트 루트 | `C:\Users\jjky0\welperion-automation` |
| 텔레그램 봇 | `C:\Users\jjky0\welperion-automation\telegram_bot\` |
| 스케줄러 | `C:\Users\jjky0\welperion-automation\telegram_bot\daily_scheduler.py` |
| 봇 본체 | `C:\Users\jjky0\welperion-automation\telegram_bot\bot.py` |
| 감시 프로세스 | `C:\Users\jjky0\welperion-automation\telegram_bot\watchdog.py` |
| 스케줄러 기동 | `C:\Users\jjky0\welperion-automation\telegram_bot\start_scheduler.bat` |
| 작업 스케줄러 등록 | `C:\Users\jjky0\welperion-automation\telegram_bot\register_task_scheduler.bat` |
| 로그 | `C:\Users\jjky0\welperion-automation\telegram_bot\scheduler.log` |
| 상태 파일 | `C:\Users\jjky0\welperion-automation\telegram_bot\state.json` |
| 환경변수 | `C:\Users\jjky0\welperion-automation\telegram_bot\.env` |

## 기획서 수정 요청 사항
- 가이드허브(https://wellperion-cao.github.io/welperion-automation/) 내
  `Desktop\welperion-automation` 표기를 `C:\Users\jjky0\welperion-automation`으로 정정 필요.
- 해당 수정은 AI CEO 경유 대표님 확인 후 반영.

## 조치 완료
- daily_scheduler.py 생성 시 절대 경로(`Path(__file__).parent`) 기준으로 작성 완료.
- Desktop 경로 참조 없음 — 오표기 영향 없음 확인.
