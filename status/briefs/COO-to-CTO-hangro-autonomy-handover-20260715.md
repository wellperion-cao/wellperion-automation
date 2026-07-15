# [시우→시토] 항로 상시건 → 자율현황 이관 · 인수인계 (배237 / CEO-2026-07-15-HANGRO-STANDING-TO-AUTONOMY)

- 날짜: 2026-07-15
- 상황: GM이 CLI 세션에서 시우(COO)에게 같은 작업을 지시 → 시우가 병렬로 착수했으나, **이미 웰리 위임(배237·시포 실행안·시토 구현)으로 진행 중**임을 확인. **GM 결정 = "시토(배237)가 소유, 시우 조각 넘김".** 이 문서가 인수인계.

## ★ GM 기준 확정 (중요 — 현재 구현과 다름)
GM 최종 refine = **"자동화 넘어 자율화까지 되어 스스로 도는 상시 미션만"** 자율현황. **모든 IN_PROGRESS 아님.**
- 예: 1042(일정탭·곧 완료)·106(발동대기) 같은 **일시 진행건은 항로에 남긴다.**
- 현재 `자율현황.html`의 `renderActiveMissions()`는 `status==='IN_PROGRESS'` 전체를 보여줌 → **`board==='자율현황'` 필터로 바꿔야 GM 기준에 맞음.**

## 채택 메커니즘 = `board` 플래그 (이미 일부 라이브)
`status/_queue.json` 각 배에 `"board": "자율현황"` 필드. 있으면 항로 제외·자율현황行. 없으면(기본) 항로.
- **장점:** 상시/일시를 배별로 정밀 지정(GM "상시건만"), 라우터는 플래그만 읽어 자기유지. 순수 가역(필드 제거=원복).
- **현재 플래그된 배(시우 판단·HEAD 커밋됨):** 237·747·754·906·970. ※ **최종 목록은 오너 큐레이션** — 시모가 545·838도 하선(자율현황 이관) 중이니 그 배들도 `board` 플래그 부여 필요. 목록 판정은 시토/웰리/시모 조율.

## 소비처 배선 현황 (★ = 시토 마무리)
| 소비처 | 상태 | 내용 |
|---|---|---|
| `status/_queue.json` board 플래그 | ✅ HEAD 커밋됨 | 5배 `board:"자율현황"` |
| `scripts/hangro_board.py` | ✅ 이 커밋에 포함 | `fetch_queue_items`에 board 필드 전달 · `_classify`에서 board=='자율현황'→`sections['autonomy']`로 라우팅(항로 전 섹터 제외) · `build_board` 요약행+포인터 라인. **실측 PASS**(자율화 4배 항로 제외·누수 0) |
| `ceo_morning_pipeline.py` (8:00 텔레그램) | ✅ 이 커밋에 포함 | G1 SSOT 머지·시트 방어·폴백 3곳에 board 제외 필터. **실측 PASS**(라이브 수집서 자율화 배 잔존 0) |
| ★ 웹 G1 `wellperion_guide(main).html` | ⚠️ 유실(동시 리셋) | 시우가 넣었던 편집(merged에서 board 제외 + 🤖 포인터 배너)이 워처 리셋으로 날아감. **재적용 필요.** 재적용 지점: 큐 머지 push(약 8881)에 `board:String(q.board||'')` 추가 → 렌더 `merged.sort` 직후 `board==='자율현황'` 제외 + 진행중 카드 앞에 자율현황 링크 포인터. |
| ★ `자율현황.html` `renderActiveMissions` | 🔧 시토 소유 | 필터를 `status==='IN_PROGRESS'` → `board==='자율현황'` 로 변경(GM 기준). "여기 중복 표시 안 함"(erp-sys-summary 노트, 약 669줄) 문구도 정합. |
| ★ 문서 정합 | TODO | `ssot/약속.json` L16(항로 3섹터) + `.claude/agents/ai-*.md` 부팅 문구(_queue PENDING·IN_PROGRESS→항로) 에 "board='자율현황' 상시 미션은 항로 제외·자율현황行" 한 줄 반영. |

## ⚠️ 리스크 (GM께도 보고)
- **CEO 워처 동시 리셋:** 이 작업 중 워커트리 리셋으로 시우 main.html 편집 + 시토 자율현황 미커밋 작업이 churn됨(과거 사고 `reference_guidehub_concurrent_commit_corruption`). **여러 AI가 같은 파일 동시 편집 금지 · 커밋 직렬화 필수.** 시토 단일 오너로 정리된 이유.
- 보조 소비처(참고): `build_voyage_map.py`(북극성 렌즈 카운트)·`daily_scheduler.py` 9/15시 진행현황 로컬 폴백·`gm_hangro` 서버 GAS API도 항로 소스 → 상시 제외 일관성 원하면 동기화 검토(전수 매핑은 시우 Explore 결과 참조).

## 검증 로그 (시우)
- hangro_board: `autonomy 건수 4 · 누수 0 · 포인터 존재` PASS
- ceo_morning_pipeline stage1(라이브 g1_ssot): 자율화 배 항로 잔존 `없음(정상)` PASS
