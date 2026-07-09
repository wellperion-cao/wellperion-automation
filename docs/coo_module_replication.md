# COO 모듈 복제 절차 (등록부 1건 추가 → 백엔드 자동 반영)

파일럿(점검현황) 검증 후, 나머지 모듈을 켜는 표준 절차. AI 없이도 따라 할 수 있게.

정본 계약 = `docs/superpowers/specs/2026-07-09-module-registry-contract.md`(웰리 확정 13필드). 편집 대상 파일 = **`status/module_registry.json`**(`coo_modules.json`은 옛 이름 — 삭제됨·존재하지 않음).

## 새 모듈 켜기 5단계
1. `status/module_registry.json`의 `modules` 배열에 `coo-*` id로 새 항목 추가 — **5개 모듈(예: reception_locker 등)은 스텁이 아직 없다. 새로 작성해야 한다.**
2. 13필드를 채운다:
   - `id`·`owner_role`(coo)·`owner_nick`(시우)·`feature`
   - `data_source`: `{kind: gas|json|sheet, ref}` — 실제 fetch 설정(엔드포인트·쿼리)은 소비자(`coo_registry.py`)가 보유, `ref`는 포인터일 뿐(계약 §3)
   - `notify_spec`: `{daily, weekly, monthly, channel, bot_id}`
   - `front_card`: `{window, anchor}`
   - `autonomy`: auto·semi·mech·propose·manual 중 하나
   - `ai_free_fallback`: AI 없이도 작동하는 근거
   - `feedback`: `{enabled, audience, entries[]}`
   - `reversible`: bool — 가역이면 자율 완료 가능
   - `enabled`: bool
   - `honesty_default`: measured·estimated·unmeasured 중 실제 측정수준
3. `coo_registry.py`에 해당 모듈의 fetch 로직(엔드포인트·쿼리·집계)을 소비자 코드로 추가.
4. `enabled: true`로 전환.
5. 검증: `pytest tests/ -k coo` 전체 통과.

## 실제로 자동 반영되는 것 vs 아직 수작업인 것
- **자동(등록부 저장만으로 반영):** 08시 보고 라인(`coo_report_line`)·이상 알림(`anomaly`)·부팅 두뇌(`boot_brain`) — 이 3개 백엔드 소비자는 등록부를 실제로 읽어 구동한다.
- **아직 수작업(후속 과제):** ERP O1 허브 카드(`o1-module-hub`)는 **현재 하드코딩** — 클라이언트에서 `module_registry.json`을 직접 읽지 않는다(그 파일은 Pages에 서빙되지 않음). 새 모듈을 카드에 띄우려면 프론트 JS(`wellperion_guide(main).html` 내 `#o1-module-hub` 스크립트)를 직접 수정해야 한다. "저장만 하면 카드도 자동 점등"은 아직 아니다 — 웰리 공유 렌더러 + 등록부 Pages 서빙 후속 과제.

검증: pytest 전체 + O1 시크릿 크롬 실측 + dry-run 보고 라인 확인.

## 게이트
- 라이브 발효(O1 push·텔레그램 실발송)는 GM go.
- 비가역(시트/GAS 변경)은 자율 금지 — 제안만.
