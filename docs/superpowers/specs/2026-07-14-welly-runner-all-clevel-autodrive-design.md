# 예약 러너 전 C-Level 확장 + 자동 검수·자동 기록 — 설계 노트

- 작성: 2026-07-14 (시토, GM 요구 배237 phase4 — CTO-2026-07-14-RUNNER-ALL-CLEVEL-AUTODRIVE)
- 전제: `scripts/welly_auto_runner.py` phase3(가역·저위험·클린트리·재귀방지·모호성 park·역롤백) 이미 라이브(CTO 1개 clevel, RUNNER_LIVE=1).
- 이 문서 범위: **증분2 — 자동 검수·자동 기록(구현 완료).** 증분1(전 C-Level 순회 엔진)은 코드로 이미 구현·dry-run 검증 완료(`run_cycle()`, 아래 "구현 완료" 절 참조). 증분2 로드맵1·3(스크립트 자동 검수·사후감사)은 구현 완료(커밋 f54bcb66), 로드맵2(러너 독립 렌더 실측)도 이번 세션 구현 완료 — 아래 "증분2 — 구현 상태" 절 참조.

## ★비협상 원칙(GM 2026-07-14 추가 못박기)★
**모호성이 조금이라도 있으면 무조건 deep-interview 방식(parked-interview 경로)으로 게이트한다 — 절대 모호한 채 자율 구동하지 않는다.** 배 note·요구가 불명확하면(2026-07-13 설계의 `is_ambiguous()` 휴리스틱: note 8자 미만·복수 접근법 키워드·스코프결정 키워드·🛳️크루즈 난이도 중 하나라도 해당) 러너는 자율 구동 대상에서 제외하고 GM 인터뷰 대기(park)로 넘긴다 — **임의 판단·추측 진행 금지.**

전 C-Level 확장(`run_cycle()`)에서도 이 원칙에 예외·우회가 없다: `run_cycle()`은 clevel마다 `run_once()`를 그대로 호출하므로, `is_ambiguous()` 게이트가 clevel 7종 전부에 동일하게 적용된다(clevel별 우회 경로를 신설하지 않음 — 새 코드도 이 게이트를 다시 통과하게만 설계됨). 실측(2026-07-14, `--clevel all --force-dry-run`, 실제 `status/_queue.json` 기준): COO의 모호 배(`COO-2026-07-13-CHECK-ALERT-CLOSEDDAY`, 사유="접근법이 여러 개")가 `mode=parked·executed=False`로 정확히 걸러졌고, 나머지 clevel은 후보 없음 또는 명확한 배(CMO)만 선택됨 — 모호 배가 자율 실행되는 경로는 실측상 확인되지 않음. 회귀 방지 테스트: `tests/test_welly_auto_runner.py::test_run_cycle_never_executes_ambiguous_ship_across_any_clevel`(라이브 모드에서도 모호 배 2종이 clevel 무관하게 100% park·실행 0·subprocess 미호출을 고정).

## 구현 완료 (증분1) — 참고용 요약
- `run_cycle(clevels=DEFAULT_CLEVELS, ...)`: `DEFAULT_CLEVELS = ("cmo","coo","cto","cpo","ceo","cfo","chro")` 순회, clevel마다 `run_once()`를 그대로 호출(신규 안전 로직 추가 없음 — 기존 가드 100% 재사용).
- `CLEVEL_NICKS` 매핑(웰리·시뽀·시로·시모·시우·시포·시토)으로 프롬프트 인사말 자동 배선.
- `MAX_SHIPS_PER_CYCLE = 3` — 사이클당 라이브 성공 실행 총 상한(clevel별 1척은 선별기 구조가 이미 보장). 상한 도달 시 남은 clevel은 `mode="cycle-cap-skipped"`로 건너뜀(claude 미호출).
- CLI: `--clevel all`로 전 clevel 사이클 실행(단일 clevel 경로와 완전 별도 분기 — 기존 `--clevel cto` 등 단일 호출 회귀 0).
- **`welly_auto_runner.bat`는 이번 세션에서 `--clevel cto` 그대로 유지.** "전면 확산 전 GM go 존중" 원칙 — 엔진은 준비됐지만 예약(07:30 매일) 라이브 스코프를 CTO 1개→7개로 넓히는 것 자체가 별도 승인 대상이라 판단(기존 RUNNER_LIVE=1은 "CTO 1척 자동구동"에 대한 GM go였지 "7개 도메인 동시 자동구동"에 대한 go가 아님). 역롤백/전진 모두 1줄(`.bat`의 `--clevel cto` → `--clevel all`).

## 증분2 — 구현 상태 (2026-07-15 갱신)

- **로드맵1(스크립트류 자동 검수) — 구현 완료(커밋 f54bcb66).** `parse_verification_result()`(세션 stdout의 `WELLY_VERIFY:` JSON 한 줄 파싱)·`build_auto_review_verdict()`(passed/ambiguous/실패 판정)·`run_once()` 배선(`success = execution_ok and verdict["passed"]`).
- **로드맵3(사후감사) — 구현 완료(커밋 f54bcb66).** `audit_completion_in_queue()`로 세션 선언 완료가 실제 큐에 반영됐는지 대조.
- **로드맵2(러너 독립 렌더 실측) — 이번 세션 구현 완료.** 러너가 프론트 배의 라이브 URL을 세션 자기보고와 독립적으로 headless 재렌더해 200·콘솔0·셀렉터를 재확인하고 판정에 접어 넣는다.
  - `WELLY_VERIFY` 계약에 `"url"` 필드 추가(frontend가 검증한 라이브 URL). `parse_verification_result()`가 파싱(`build_orchestration_prompt`가 frontend에 url 포함을 지시).
  - `render_verify_url(url, required_selectors, evidence_dir, timeout_ms)`: playwright 지연 import(단위테스트는 브라우저 없이 통과) · headless chromium 렌더 · main response HTTP status + 콘솔 error만 수집 + 셀렉터 존재 확인 + 스크린샷(URL 슬러그 파일명) 저장. **어떤 예외도 던지지 않고** 인프라 실패는 `error` 필드로 반환(렌더 성공했지만 조건 미달=`error` None + `ok` False와 구분).
  - `fold_render_into_verdict(verdict, verify_parsed, render_result, render_enabled)`(PURE): 인프라 실패=passed 유지+정직 태그(park 아님) · 렌더 통과=passed 유지+재확인 태그 · **불일치(세션 성공 주장 vs 렌더 실패)=passed False·ambiguous True로 강등→park(비협상)**.
  - **게이트 `RUNNER_RENDER_VERIFY` 기본 OFF.** `_render_verify_enabled()`가 `=="1"`일 때만 True. `run_once()`는 `live and _render_verify_enabled() and verdict["passed"]`일 때만 `render_verify_url` 호출 → `fold_render_into_verdict`로 verdict 갱신. **게이트 OFF(기본)면 render_verify_url 절대 미호출 — 기존 88테스트·현행 라이브 동작 100% 불변.** 게이트 활성은 시토가 실측 후 수동으로 켠다(`.bat` 미변경).
  - 검증 CLI: `--render-verify-url <URL>`(run_once 미가동, 단독 렌더 결과만 출력 — 수동 실측용).
  - 회귀 테스트: `test_run_once_render_gate_off_never_calls_render_verify`(게이트 OFF 시 미호출·기존 동작 불변)·`test_run_once_render_gate_on_mismatch_parks`(불일치→park)·`fold_render_into_verdict` 전 분기·`parse_verification_result` url 파싱.

## 증분2 — 설계 배경 (원본 로드맵)

### 문제
현재 완료 루프는 사람(웰리)이 수동으로 담당: 배 실행 → **실측 검수**(시크릿 크롬 라이브 렌더 등) → **G1/큐 기록**(`clevel_post_action.py --status 완료`). run_cycle()로 실행까지는 무인화됐지만, 이 뒤 두 단계가 여전히 사람 개입 지점 — "GM 반복승인 제거"를 완결하려면 이 둘도 기계화 검토가 필요하다.

### A. 자동 검수 — 어디까지 가능한가
분류:
1. **스크립트/백엔드 산출물** (로그·테스트·exit code로 증명 가능) → **완전 자동화 가능.** 이미 헤드리스 세션 프롬프트(`build_orchestration_prompt` 절차 2)가 "실행 로그/테스트로 증명"을 요구 — 검증 결과를 세션이 stdout에 구조화(JSON 한 줄)로 남기게 하면 러너가 파싱해 `success` 판정에 반영 가능.
2. **프론트/페이지 변경** (라이브 렌더 실측 필요) → **부분 자동화 가능, 신뢰 상한 있음.** Playwright headless로 URL 렌더 후 콘솔 에러 0·특정 셀렉터 존재·스크린샷 저장까지는 스크립트화 가능(기존 `wordpress_admin_playwright.py` 등 패턴 재사용). 단, "디자인이 GM 기대와 맞는가"·"카피 톤이 적절한가" 같은 **주관적 판단은 자동화 불가** — 스크린샷을 아티팩트로 남기고 정직 꼬리표(예: "자동 렌더 확인 — 200·콘솔0·셀렉터 존재. 디자인 적합성은 미검수")를 붙여 표면화하는 것이 현실적 목표.
3. **비가역 산출물**(발행·배포 등) → 애초에 러너가 실행 자체를 거부(IRREVERSIBLE_KEYWORDS) — 검수 자동화 논의 대상 아님.

권고: v1은 (1) 완전자동 + (2) 부분자동(렌더 실측+정직 꼬리표, 주관판단은 "미검수"로 명시)만 구현. "완전 자동 검수"를 전 케이스에 약속하지 않는다(정직 원칙, feedback_no_100pct_overclaim_report_actual_progress).

### B. 자동 기록 — G1/커밋
- **커밋**: 이미 세션 프롬프트가 "명시 경로만 git add" + 표준 커밋 메시지(Co-Authored-By 등)를 강제 — 추가 자동화 불요(세션 자체가 수행).
- **G1/큐 기록**: 이미 세션 프롬프트가 `clevel_post_action.py --status 완료 --artifact-url <증거> --next ...` 호출을 절차 4에 명시 — 세션이 직접 기록. 러너 쪽에서 추가할 것은 **사후 감사(post-hoc audit)** 뿐: `run_cycle()` 결과의 `changed_files`(이미 존재, `_commit_changed_files`)를 큐 변경분과 대조해 "선언한 task_id가 실제로 완료 처리됐는가"를 다음 사이클 시작 시 가볍게 검증(불일치 시 park 또는 로그 경고) — 이건 신규 코드지만 소규모.

### 권고 로드맵 (구현 순서, 각 단계 GM go 별도)
1. 세션 stdout 구조화 검증 결과(JSON 한 줄) 파싱 → 스크립트류 산출물 자동 검수.
2. Playwright headless 렌더 체크(콘솔0·200·셀렉터) + 정직 꼬리표 자동 첨부 → 프론트류 부분 자동 검수.
3. 사후 감사(선언 완료 vs 실제 큐 반영 대조) — 신뢰 붕괴 조기 감지.
4. (사람 남김) 디자인·톤·전략적 적합성 판단 — 자동화 비대상, 계속 웰리/GM 수동 확인.

### 비목표(v1)
- 완전 무인 "검수까지 100% 자동" 약속 — 하지 않는다(정직 원칙 위반 위험).
- 러너가 직접 `clevel_post_action.py`를 호출(세션 대신 기록) — 세션이 이미 그 책임을 지므로 중복·권한 혼선 위험, 하지 않는다.
