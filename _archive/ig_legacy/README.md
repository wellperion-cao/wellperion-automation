# IG 레거시 배치 (아카이브 2026-06-13 · 시토)

구식 IG 발행 워크플로 `.bat`. **현재 미사용** — Windows 예약작업 미등록·활성 참조 0건 (이관 전 schtasks 실측 확인).

| 파일 | 폐기 사유 |
|---|---|
| `start_ig_publish_watcher.bat` · `register_ig_publish_watcher.bat` | 120초 폴링 watcher → 텔레그램 승인 즉시 발행으로 대체(2026-06-03) |
| `start_ig_publish_dispatcher.bat` · `register_ig_publish_dispatcher_0730.bat` | 07:30 배치 발행 → 승인 즉시 발행으로 대체 |
| `register_ig_series_produce_2100.bat` | 21:00 제작 → 07:30 통합(루트 `register_ig_series_produce_0730` 활성)으로 대체 |
| `_kill_ig_watcher_permanent.bat` | 위 watcher 중지용 수동 도구 |

**복구 시:** 경로·예약작업 재등록 필요. 관련 죽은 런처 `launchers/ig_watcher_hidden.vbs`(비활성)도 함께 정리 대상.
