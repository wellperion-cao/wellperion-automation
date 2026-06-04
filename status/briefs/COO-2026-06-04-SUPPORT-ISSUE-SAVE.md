# COO-2026-06-04-SUPPORT-ISSUE-SAVE — 지원부 점검 앱 이슈 저장 유실 위험 수정

**인계: 시토(CTO) → 시우(COO)** · 2026-06-04 · GM 지시(시토 진단 후 COO 위임 승인)

## 증상 (GM 보고)
지원부 체계 점검 체크리스트 앱에 이슈를 기록했는데 시트에 반영이 안 된다고 느낌.

## 시토 진단 결과 (코드·라이브 실측 완료)
- **코드 배선은 정상**: 프론트 `onExtra`→`saveState`→`pushToServer`(자동 push), GAS `handleSave`/`_handleSaveV2Compat` 모두 `c.issue`를 시트에 기록(미체크 항목 이슈도 포함).
- **라이브 시트 실측**: 2026-06-04 이슈 1건 저장 확인 — `d1 → "지하1층 여화장실 오른쪽 변기 속 청소필요"`. 즉 **완전 미저장이 아니라 일부만/덮어쓰기 정황**.

## 근본 원인 (유력)
- 프론트 `pushToServer`(`coo/check/지원부 체계.html` ~line 1531-1560)가 POST에 **`zone`을 안 보내고 `genderTab`만 전송**.
- GAS `handleSave`(`coo/check/apps_script_v3.js` line 295-296)는 `if(!body.zone) return _handleSaveV2Compat(body)` → **항상 구호환 경로로 폴백**.
- `_handleSaveV2Compat`(line 375-438)는 해당 **날짜의 시트 행을 전부 삭제 후 현재 push의 버킷 항목만 재기록**(line 410-413). → 남/여 탭 전환하며 여러 번 저장하면, 특히 **공용(common) 항목 이슈가 마지막 push에 덮어써져 유실** 가능.
- 안전한 신버전 경로(zone 기반, line 295-350: 행 삭제 없이 update/add)가 코드엔 있으나 프론트가 안 탐.

## 수정 방향 (택1, COO 판단)
1. **프론트가 zone 기반으로 저장** → 신버전 `handleSave`(비파괴 update/add) 경로 사용. zone은 male/female/common 3분기라 `_routeItem` 로직을 프론트에서 미러링하거나, push를 zone별로 분리.
2. 또는 `_handleSaveV2Compat`를 **비파괴(행 전체삭제 금지, itemId 단위 update/add)**로 개선.
- 권장: 2번이 회귀 적음(프론트 다중 push 구조 안 건드림).

## 검증 의무
- **GAS 웹앱 재배포 필수** — `clasp push`만으로는 `/exec` 미반영(메모리 reference_clasp_webapp_redeploy). 새 버전 배포 후 라이브 실측.
- 라이브 실측: 남/여/공용 탭에 각각 이슈 입력 → 전부 시트 잔존하는지(덮어쓰기 0) 확인.
- API_URL: `…/AKfycbzcOTihPYfTWQ64rbNMpfgv9p2keav0mcf7x0LrPhHm8nOUIlsqPTwCOumzE-JIcv1F/exec`

## 관련 파일
- `3. 웰페리온 가이드/coo/check/지원부 체계.html` (pushToServer ~1531)
- `3. 웰페리온 가이드/coo/check/apps_script_v3.js` (handleSave 295 / V2Compat 375)
