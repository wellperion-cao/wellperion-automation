# AI CEO 운영 체계 — status 디렉토리

CEO와 6 C-Level 간 비동기 통신 큐·상태 관리 SSOT.

## 파일 구조
- `_queue.json` — FIFO 큐 (배열). C-Level이 작업 완료 후 [DONE] commit + 큐 push
- `_ceo_log.jsonl` — JSON Lines 영구 로그. CEO 처리 1건씩 append
- `ceo.json` — CEO 메타 상태 (마지막 trigger·미처리 큐 수 등)
- `<role>.json` (cto·cfo·cmo·coo·chro·cpo) — 각 C-Level 현재 상태

## 상태 머신
DONE → VERIFYING → (VERIFIED | REJECTED) → ARCHIVED

## 큐 항목 스키마
```json
{
  "task_id": "string",
  "clevel": "cto|cfo|cmo|coo|chro|cpo",
  "title": "string",
  "status": "PENDING|DONE",
  "depends_on": "string|null",
  "origin": "bridge|null",
  "enqueued_at": "ISO8601",
  "processed_at": "YYYY-MM-DD",
  "artifact": "증거 URL(스크린샷/로그/라이브확인) — 완료 단일 정의 ④요건. DONE 항목에 기록",
  "next": "다음 한 줄(브릿지)",
  "terminal": true,
  "next_missing": true
}
```

> **완료의 단일 정의(4요건)** — DONE 등록 시 `clevel_post_action.py`는 `--artifact-url`(④증거)이
> 없으면 **거부(exit 2)**한다. 큐 DONE 항목의 `artifact` 필드는 그 증거 URL을 보존한다.
> (정의 단일 출처 = 가이드허브 S2 공통탭 "✅ 완료의 단일 정의(4요건)".)

## 로그 항목 스키마 (JSONL)
```json
{"task_id": "...", "clevel": "...", "result": "VERIFIED|REJECTED", "layer": 1|2, "reason": "...", "commit_sha": "...", "logged_at": "ISO8601"}
```

## 가동 명령
```powershell
# 등록
.\scripts\register_ceo_watcher.ps1

# 1회 수동 가동 (테스트용)
python scripts\ceo_watcher.py
```
