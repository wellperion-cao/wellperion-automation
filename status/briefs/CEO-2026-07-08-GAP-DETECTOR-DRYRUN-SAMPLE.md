# 자율 틈 감지기(배237(b)) 드라이런 샘플 — GM 오탐 검토용

> 실행: `python scripts/gm_aide_scan.py` · 2026-07-08 10:53 · 두 게이트 모두 OFF(`AIDE_STALL_APPLY`·`GM_AIDE_AUTO_EXEC` 미설정) → **변경 0(순수 감지·라우팅만)**.
> 활성큐 193척 스캔 → 틈 **12건**(정체 5 · 재개가능 7), 라우팅 auto 12 · propose 0.

## 1. 정체 배(5) — 무게별 임계(🛳️2일/⛴️3일/⛵5일·NORMAL 5일) 초과 무활동

| 배 | 담당 | 무게 | 며칠 정체 | 마지막 활동(근거) | 라우팅 |
|---|---|---|---|---|---|
| #300 CMO-2026-07-02-NORTHSTAR-MEASUREMENT-BIO | 시모 | ⛴️여객선(3일 임계) | 5일 | 2026-07-03 | auto |
| #102 CTO-2026-06-30-TELEGRAM-RELIABILITY-OWNERSHIP | 시토 | ⛴️여객선(3일 임계) | 8일 | 2026-06-30 | auto |
| #185 CMO-2026-06-26-M5-SSOT-UNIFY | 시모 | 🛳️크루즈(2일 임계) | 12일 | 2026-06-26 | auto |
| #237 CEO-2026-07-02-GM-AIDE-AUTONOMY | 웰리 | 🛳️크루즈(2일 임계) | 4일 | 2026-07-04 | auto |
| #426 CMO-2026-07-04-AI-SERIES-MEASUREMENT-CH-33-37 | 시모 | ⛴️여객선(3일 임계) | 4일 | 2026-07-04 | auto |

## 2. 재개가능 배(7) — 선행 참조배(`depends_on`) 완료(DONE)로 구조적 의존 해소

| 배 | 담당 | 재개 근거(선행 참조배 → 완료) | 라우팅 |
|---|---|---|---|
| #597 NEXT-20260707-155721 | 시토 | CTO-2026-06-29-NORTHSTAR-RECOMMENDER → DONE | auto |
| #598 NEXT-20260707-155730 | 시토 | CTO-2026-07-02-KPI-PIPELINE-REPAIR-COO-CHECK → DONE | auto |
| #599 NEXT-20260707-160103 | 시토 | CTO-2026-07-06-KAKAO-REPORT-SENDER → DONE | auto |
| #600 NEXT-20260707-160113 | 시토 | CTO-2026-07-06-VOYAGE-MAP-PAGE → DONE | auto |
| #605 NEXT-20260707-161539 | 시토 | CTO-2026-07-06-NORTHSTAR-DEDUP-COMPLETED → DONE | auto |
| #607 NEXT-20260707-162046 | 시토 | CTO-2026-07-03-MONTHLY-REPORT-TELEGRAM → DONE | auto |
| #624 NEXT-20260707-171909 | 시토 | CTO-2026-07-04-NORTHSTAR-REDESIGN → DONE | auto |

## 3. 오탐 의심 — ⚠️ #237 (CEO-2026-07-02-GM-AIDE-AUTONOMY)

이 배 자체가 **본 검증(US-006)이 진행 중인 배237(b) 작업**이다. 감지기는 "마지막 활동 2026-07-04"로 판정해 4일 정체로 잡았지만, 실제로는 오늘(2026-07-08) `707c8acf`·`559390f5` 두 커밋으로 코드 구현이 진행됐다. 감지기의 활동 시그널이 **note 필드 날짜브래킷**(마지막 `[2026-07-04...]`) 기반이라, git 커밋은 있었지만 note에 날짜브래킷이 새로 안 찍혀 놓친 것 — 알고리즘 버그는 아니고 **note-브래킷 시그널의 구조적 한계**(코드 활동 ↔ note 텍스트 갱신 시차)다. 본 세션 끝에 배237 note를 갱신하면 다음 스캔부터는 정상적으로 최신 활동일로 잡힌다. 나머지 4건(정체)·7건(재개가능)은 note 브래킷/depends_on 값과 실제 상태가 일치 — 오탐 없음.

## 4. 요약

- 정체 5건 · 재개가능 7건 = 총 12건, 전량 라우팅 auto(비가역 요소 없음: revert_ok·非external·非data_loss)
- propose 폴백 0건
- 게이트 OFF → 실제 적용 0건(전부 `[dry-run] 자율 조치 예정` 로그만, `_queue.json` write 없음 — 해시 대조로 델타 0 확인)
- 오탐 의심 1건(#237, 위 3번 참고) — 라이브 발효 전 note-브래킷 시그널의 알려진 한계로 기록, 코드 수정 불요(본 세션 note 갱신으로 자연 해소)
