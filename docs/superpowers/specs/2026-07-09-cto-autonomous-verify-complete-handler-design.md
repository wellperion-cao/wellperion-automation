# 설계 스펙: 자동 검증-완결 핸들러 (자율 실행 루프 닫기 · 첫 슬라이스)

- 작성: 2026-07-09 · 시토(CTO) · 자율화 설계단 ⑥(자율 실행 루프)
- 배경: GM "자율화 설계단 집중". 실측 결과 자율 실행 arm(`aide_detectors/auto_actions.py`)은 태그·nudge·의존해소 3개(메타데이터)만 auto → **실제 도메인 일 0**. "손이 nudge에서 멈추고 세션을 기다린다"가 미완성 지점.
- 목표(한 문장): '검증형' 재개가능 배를 **세션 없이 코드가 대신 검증**해 조건 충족 시 입항(증거 첨부·보고)·불충족 시 surface — 반복 확인 세션일을 코드로 굳혀 GM·AI 개입을 줄이는 **loop의 첫 닫힘**.

## 범위 (딱 이것만 · 안 벌림)
- **핸들러 1개** + **검증기 유형 1개(`log_contains`)** + 게이트 1개. 그 이상 X.
- 대상 = `aide_detectors` 재개가능+가역(`route()=='auto'`) 배 중 **명시적 `verify` 스펙을 가진 배만**. (패턴 추측 금지 → 오완결 방지.)

## 비목표 (Non-Goals)
- 임의 도메인 실행·AI 워커 스폰(위험·후속). 이번은 **결정론적 검증형만**.
- 검증기 다유형(라이브 HTTP·GAS·이미지 대조)은 v2. v1=`log_contains` 하나.
- 패턴 추측으로 배 유형 판정(명시 스펙 없는 배는 손대지 않음).
- 웰리 오케스트레이션·시모 설계총괄 로직 변경(미접촉).

## 데이터 계약 — 배의 `verify` 스펙 (명시)
검증 대상 배만 아래 필드를 갖는다(없으면 핸들러가 무시):
```json
"verify": {
  "type": "log_contains",
  "path": "telegram_bot/bot.log",
  "match": "chat_id=-5498808140",
  "since": "2026-07-09T00:00:00",
  "evidence_label": "자동화현황방 도착"
}
```
- `type` v1 = `log_contains`만. `path`=파일(리포 상대), `match`=찾을 문자열, `since`=이 시각 이후 라인만(선택), `evidence_label`=증거 요약용.

## 흐름
`gm_aide_scan.run` 내 재개가능 auto 레인 처리 뒤에 핸들러 삽입:
```
for ship in resumable_auto with ship.get('verify'):
    result = verify(ship['verify'])           # 순수: (ok: bool, evidence: str)
    if result.ok and GATE_ON:
        close_ship(ship, evidence)            # status=DONE·terminal·artifact=evidence·next='🏁 입항(자동검증)'
        log_auto_exec(ship, 'verify_complete', evidence)   # 원장
        report(ship)                          # G1 반영 + 텔레그램 1줄(기존 clevel_post_action/모듈보고 재사용)
    else:
        surface(ship, reason)                 # 절대 완결 X — note에 '자동검증 대기/실패' 정보만(멱등)
```
- **PASS만 완결. FAIL·불명은 절대 완결하지 않는다(거짓완료 0 = 성공기준).**
- 멱등: 이미 DONE/terminal 배 skip. 재실행 중복 완결 0.

## 가드레일
- **게이트 `AIDE_VERIFY_APPLY`(env, 기본 0=OFF)**: OFF면 드라이런(무엇을 닫을지 로그만·큐 델타 0). GM go 시 gm_aide_scan.bat에 `set AIDE_VERIFY_APPLY=1` 한 줄 추가로 라이브. 역롤백=그 줄 제거.
- **가역성**: 완결=상태·메타 변경뿐(외부·파괴·전송 0). git revert로 즉시 원복.
- **보수 라우팅 재사용**: 기존 `reversibility.route()`로 auto 판정된 배만 대상(비가역은 애초 제외).
- **증거 필수**: 완결 배 artifact에 실측 증거 문자열(어느 로그·어느 라인 매칭) 기록 → 사후 추적.

## 수용 기준 (테스트 가능)
- [ ] AC-1 `verify` 스펙 없는 배 = 핸들러 무시(diff 0)
- [ ] AC-2 `log_contains` PASS(로그에 match 존재) + 게이트 ON → 배 DONE·terminal·artifact=증거·원장 기록
- [ ] AC-3 match 없음(FAIL) → 배 **완결 안 됨**(status 불변)·surface 정보만
- [ ] AC-4 게이트 OFF → 드라이런, 큐 델타 0(무엇을 닫을지 로그만)
- [ ] AC-5 이미 terminal 배 재실행 → skip(중복 완결 0·멱등)
- [ ] AC-6 pytest(verify 순수함수·PASS/FAIL/게이트/멱등) 통과
- [ ] AC-7 `since` 경계: since 이전 라인은 매칭 제외

## 파일 (최소)
- 신설: `scripts/aide_detectors/verify_complete.py`(순수 `verify(spec)->(ok,evidence)` + `handle(ships, gate)->summary`)
- 신설: `scripts/aide_detectors/test_verify_complete.py`
- 수정: `scripts/gm_aide_scan.py`(재개가능 레인 뒤 핸들러 호출 1블록·게이트 읽기)
- 수정(발효 시): `scripts/gm_aide_scan.bat`(GM go 후 `set AIDE_VERIFY_APPLY=1`)
- 파일럿: 기존 확인형 배 1척(예 ship599 '첫 무인 발송 09:30 도착')에 `verify` 스펙 주입해 실증.

## 성공의 모습 (GM 체감)
확인형 배가 **아무도 안 열어도 스스로 도착 확인→입항→보고**된다. GM이 "○○ 확인했어?"를 안 물어도 됨 = 개입↓. 유형을 늘릴수록 loop이 더 닫힌다.
