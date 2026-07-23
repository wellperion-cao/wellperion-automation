# M1 웹 승인 ↔ 텔레그램 승인 통일 — 봇 발행 트리거 수렴 (설계)

**날짜:** 2026-07-16 · **소유:** 시모(CMO) · **배:** ship 1170 · **연결:** `2026-07-15-cmo-content-module-semi-unmanned-m1-design.md`

## 0. 현황 — 두 승인 경로, 한쪽만 발행

콘텐츠 검수 SSOT = `3. 웰페리온 가이드/cmo/review/review_queue.json` (status: 대기/승인/반려). 승인 진입점이 둘인데 동작이 갈렸다.

| 경로 | 승인 처리 | 발행 트리거 | 상태 |
|---|---|---|---|
| **텔레그램 카드** [✅승인] | `telegram_bot/bot.py` `cmd_publish_callback` (~1599행) — status='승인' write+커밋 | subprocess로 `ig_review_publish_watcher.py --once` 기동 (~1703-1724행, 구 코드) | **정상 작동 중(GM 상시 사용)** |
| **M1 웹** [승인] | GAS `.deploy-todo/업무&결재 현황.js` `_reviewSetStatus()` (515-537행) — GitHub API로 status='승인' 커밋 | **없음** — 커밋만 하고 멈춤 | 조용한 정지(발행 안 됨) |

발행 엔진 자체(`scripts/ig_review_publish_watcher.py`, `APPROVED_STATES`에 '승인' 포함, `--once`)는 공용. 문제는 **트리거가 텔레그램 경로에만 배선**돼 있던 것.

## 1. GM 확정 방식 — 「봇 발행 재사용」

M1이 발행 엔진을 직접 부르지 않는다(GAS→로컬 subprocess 불가). 대신 **M1 승인 시 텔레그램 봇에 신호를 보내, 봇이 텔레그램 카드 승인과 동일한 코드 경로로 발행**시킨다.

```
M1 [승인] 클릭
  → GAS _reviewSetStatus(): review_queue.json status='승인' 커밋 (기존 그대로)
  → 커밋 성공 시 GAS _signalM1Publish(id): 텔레그램 sendMessage "/m1pub <id>" → GM 챗
  → 봇 cmd_m1_publish(): GM 챗 확인 → git pull(직렬화) → 큐 재로드 → status 확인
  → 게이트(M1_AUTO_PUBLISH) ON이면 _launch_publish_engine([id], source="m1-web") 호출
       (= cmd_publish_callback 이 쓰던 subprocess 기동 로직을 그대로 재사용)
```

텔레그램 카드 경로(`cmd_publish_callback`)의 **외부 동작은 100% 보존** — subprocess 기동부만 `_launch_publish_engine()`으로 추출해 두 경로가 같은 함수를 호출하도록 수렴시켰을 뿐, 콜백의 메시지·edit·pending-ping 로직은 무변경.

## 2. 구현

### 2-1. `telegram_bot/bot.py`
- **`_launch_publish_engine(item_ids, *, source="tg")`** (신설, ~1599행 앞) — 구 `cmd_publish_callback` 인라인 subprocess 블록을 그대로 추출. 로그 헤더에 `src={source}` 추가(진단용, 동작 무변경).
- `cmd_publish_callback` 승인 분기 → `await _launch_publish_engine(item_ids, source="tg")` 호출로 교체(외부 동작 동일).
- **`cmd_m1_publish(update, ctx)`** (신설) — `/m1pub <id>` 핸들러.
  - GM 챗(`_GM_CHAT_ID=8254867551`, `ssot/canon_values.json telegram_chat_id` 정본과 동일) 아니면 조용히 무시.
  - `_git_pull_locked()` — `_git_seq_locked`와 **동일 GitLock 임계구역**으로 `git pull --rebase --autostash`만 수행(파괴적 옵션 없음). GAS가 GitHub REST로 직접 커밋한 내용을 로컬로 당겨오는 단계 — 동시커밋 레포 손상(`reference_guidehub_concurrent_commit_corruption` 교훈) 방지.
  - 큐 재로드 → id 없음/미승인 → 안내만 하고 종료(발행 안 함).
  - **게이트** `M1_AUTO_PUBLISH`(`.env`, 기본 `0`) OFF → "🔒 게이트 OFF" 안내만, 발행 없음. ON → `_launch_publish_engine([id], source="m1-web")`.
  - 전체 try/except — 실패 시 GM 챗에 사유 안내(예외 무시하지 않음).
- `main()`에 `CommandHandler("m1pub", cmd_m1_publish)` 등록(~2065행 부근).

### 2-2. `telegram_bot/.env`
- `M1_AUTO_PUBLISH=0` 추가(신규 키 — 라이브 발효 게이트, 기본 OFF).

### 2-3. GAS `.deploy-todo/업무&결재 현황.js`
- **`_signalM1Publish(id)`** (신설) — `TELEGRAM_BOT_TOKEN` ScriptProperty(= `.deploy-check/지원팀 일일점검.js`와 동일 키) 로 `sendMessage`, GM 챗(`8254867551`) 고정 대상으로 `/m1pub <id>` 발송. `muteHttpExceptions: true` + try/catch — **신호 실패는 비치명**(승인 커밋 자체는 이미 성공한 뒤이므로 승인 결과에 영향 없음).
- `_reviewSetStatus()` 끝: 커밋 성공(`cr.ok`) **AND** `status === '승인'`일 때만 `_signalM1Publish(id)` 호출. 반려는 호출 안 함.
- 파일 상단·함수 주석에 "이 변경은 GAS 재배포(새 `/exec` 버전) 필요" 명시 — `clasp push`만으론 웹앱 미반영.

## 3. 라이브 발효 게이트 — 기본 OFF, 영향 0

- `M1_AUTO_PUBLISH=0`(기본)이면 `/m1pub` 신호는 수신·안내만 하고 **발행 엔진을 절대 호출하지 않는다**. 기존 텔레그램 카드 승인 경로는 게이트와 무관하게 무변경 동작.
- GAS는 재배포 전까지 `_signalM1Publish` 자체가 발효되지 않음(구 `/exec` 버전이 살아있는 한 신호가 안 나감) — 이중 안전.

### GM go-steps (라이브 발효 순서)
1. GAS `.deploy-todo/업무&결재 현황.js` 재배포(새 `/exec` 버전) — `_signalM1Publish` 발효.
2. `.env` `M1_AUTO_PUBLISH=1` 로 전환.
3. 봇 재시작(env 재로딩).
4. L2 PT 검수건(`CMO-2026-07-14-LSERIES-L2-PT`)으로 M1 승인→발행 e2e 1회 실측 확인.

## 4. 테스트

`tests/test_m1_telegram_approval_unify.py` — `cmd_m1_publish` 단위검증(mock update/ctx, `_launch_publish_engine`·`_git_pull_locked` patch):
① GM 아닌 챗=무시 ② id 없음=사용법 ③ status≠승인=보류 ④ 게이트 OFF=발행 안 함 ⑤ 게이트 ON+승인=`_launch_publish_engine(["id"], source="m1-web")` 호출.
