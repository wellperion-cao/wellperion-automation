# [CTO] 인스타 검수 승인 → 발행 중계 구축 (Phase 2 연결)

task_id: CTO-2026-05-29-IG-APPROVAL-RELAY
요청: GM · 작성: AI CMO · 2026-05-29
선행: 없음 (단, 보안 토큰 단계는 GM 결재 필요 — 아래 §4)

## 1. 목표 (이 한 줄만 하면 됨)
김남욱 페이지 검수 카드의 **[승인]** 클릭 → 검수 큐의 해당 항목 `status`를
`"검수대기"` → `"승인"` 으로 **GitHub에 기록**되게 한다. (1~2분 내 반영)
그 뒤는 이미 만들어진 감시기가 알아서 발행한다.

## 2. 이미 완성된 것 (재사용·수정 금지, "중계"만 만들면 됨)
| 구성 | 위치 | 상태 |
|---|---|---|
| 검수 카드 UI | `3. 웰페리온 가이드/wellperion_guide(main).html` (id=`gm1-review-section`) | 완성. 현재 [승인]은 localStorage(`gm1_review_decisions`)에만 기록 |
| 검수 큐 | `3. 웰페리온 가이드/cmo/review/review_queue.json` | 항목 필드: id·title·channel·preview·caption·status·folder. status 흐름 검수대기→승인→발행완료 |
| 발행 감시기 | `scripts/ig_review_publish_watcher.py` | 완성·검증. status="승인" 건을 publish→발행완료 갱신→커밋/푸시→텔레그램. `--once`(예약작업)·`--dry-run` |
| 실제 발행기 | `scripts/instagram_upload_playwright.py --mode publish` | 검증됨(seed #09 2회 발행 성공) |

## 3. 만들 것 = "역방향 중계" 한 칸
**브라우저 [승인] 클릭 → GitHub의 review_queue.json status="승인" 기록.**

- 권장(재사용): S4 페이지가 쓰는 기존 Apps Script 중계(`TODO_API_URL`,
  가이드 HTML 내 검색)는 이미 편집 내용을 GitHub에 저장한다. 이 Apps Script에
  액션 추가: `action=review_set_status & id=<항목 id> & status=승인`
  → Apps Script가 `cmo/review/review_queue.json`에서 해당 id의 status를 갱신·커밋.
  ※ Apps Script 소스는 repo에 없고 클라우드에 있음 → CTO가 배포본 확인/확장.
- gm1 검수 카드의 [승인] 핸들러를 localStorage 기록 → 위 중계 호출로 교체
  (반려도 동일 패턴: status="반려").
- COO 태스크 `COO-2026-05-29-S4-SSOT-REVAMP`도 같은 Apps Script에 PIN 서버검증을
  다루므로 **동일 인프라 — 충돌·중복 없게 COO와 조율**.

## 4. 🔒 보안 (GM 결재 필요)
- GitHub 쓰기 토큰: **fine-grained PAT, 단일 repo, contents:write 최소권한**.
- 저장: Apps Script **스크립트 속성(PropertiesService)** 에 GM이 직접 설정.
  평문 코드·평문 파일 저장 금지([[feedback_credentials_policy]]·[[feedback_no_token_in_stdout]]).
- 토큰 발급·전달은 GM 1:1. CTO는 저장 위치·사용 코드만 준비.

## 5. 검증 기준 (완료 보고 전 실측)
1. 검수 카드에서 [승인] 클릭 → 1~2분 내 라이브 review_queue.json status="승인" 확인(curl).
2. `python scripts/ig_review_publish_watcher.py --once` → 해당 건 발행 → status="발행완료"+게시 URL.
3. 게시물 URL 실측(화면 확인). [[feedback_screenshot_visual_verify]]·[[feedback_verify_deployed_not_local]]

## 6. 경계
- 검수 카드·감시기·발행기는 CMO가 완성 — **재설계 금지**(보수적 증분).
- CTO 범위 = "승인 클릭 → GitHub 기록" 중계 + 보안 토큰 저장 구조 + gm1 버튼 핸들러 교체.
- 감시기 예약작업(Windows) 등록·실발행 가동 = GM go 후(개인 계정 외부 공개).
