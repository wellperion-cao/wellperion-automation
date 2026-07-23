# COO 모듈 복제 절차 (등록부 1건 + fetcher 맵 등록 → 백엔드 자동 반영)

파일럿(점검현황) 검증 후, 나머지 모듈을 켜는 표준 절차. AI 없이도 따라 할 수 있게.
2번째 모듈(업무·결재, `coo-work-approval`) 복제로 소비자가 **공통 status 계약 + fetcher 맵**으로 일반화됨 — 이제 신규 모듈 추가 시 소비자 파일(`coo_report_line.py`/`coo_check_anomaly.py`)은 손대지 않는다.

정본 계약 = `docs/superpowers/specs/2026-07-09-module-registry-contract.md`(웰리 확정 13필드). 편집 대상 파일 = **`status/module_registry.json`**(`coo_modules.json`은 옛 이름 — 삭제됨·존재하지 않음).

## 공통 status 계약
모든 fetcher는 동일한 dict를 반환한다: `{"display": str, "anomaly": bool, "reasons": list[str], "tag": str, "metrics": dict}`.
- `display`: 텔레그램 한 줄용 요약 문자열
- `anomaly`/`reasons`: 이상 여부·근거(빈 리스트=이상 없음)
- `tag`: `"measured"`(실측)·`"estimated"`·`"unmeasured"`
- `metrics`: 화면/후속 로직용 구조화 수치
- 기존 필드(예: `fetch_check_status`의 `depts`)는 하위호환으로 유지되며 계약 필드에 추가된다.

## 새 모듈 켜기 3단계 (fetcher-맵 패턴)
1. **등록부 1건 추가**: `status/module_registry.json`의 `modules` 배열에 `coo-*` id로 13필드 항목 추가.
   - `data_source`: `{kind: gas|json|sheet, ref}` — 실제 fetch 설정(엔드포인트·쿼리)은 소비자(`coo_registry.py`)가 보유, `ref`는 포인터일 뿐(계약 §3)
   - `enabled: true`·`honesty_default`(measured·estimated·unmeasured) 정직 표기.
2. **`STATUS_FETCHERS`에 fetcher 추가**: `coo_registry.py`에 `fetch_<모듈>_status(fetch_fn=_http_get_json) -> dict`를 작성(공통 status 계약 반환), `STATUS_FETCHERS = {..., "coo-<id>": fetch_<모듈>_status}`에 한 줄 등록.
3. **`DISPLAY_NAME`에 표시명 추가**: `DISPLAY_NAME["coo-<id>"] = "짧은 이름"`.
4. 검증: `pytest tests/ -k coo` 전체 통과.

소비자(`coo_report_line.py`·`coo_check_anomaly.py`)는 `R.STATUS_FETCHERS.get(m["id"])`로 fetcher를 찾아 `f(fetch)`만 호출 — 모듈별 분기 코드를 추가할 필요가 없다.

## 실제로 자동 반영되는 것 vs 아직 수작업인 것
- **자동(등록부 + STATUS_FETCHERS 등록만으로 반영):** 08시 보고 라인(`coo_report_line`)·이상 알림(`anomaly`)·부팅 두뇌(`boot_brain`) — 이 3개 백엔드 소비자는 등록부 + fetcher 맵을 실제로 읽어 구동한다.
- **아직 수작업(후속 과제):** ERP O1 허브 카드(`o1-module-hub`)는 **현재 하드코딩** — 클라이언트에서 `module_registry.json`을 직접 읽지 않는다(그 파일은 Pages에 서빙되지 않음). 새 모듈을 카드에 띄우려면 프론트 JS(`wellperion_guide(main).html` 내 `#o1-module-hub` 스크립트)를 직접 수정해야 한다. "저장만 하면 카드도 자동 점등"은 아직 아니다 — 웰리 공유 렌더러 + 등록부 Pages 서빙 후속 과제.

검증: pytest 전체 + O1 시크릿 크롬 실측 + dry-run 보고 라인 확인.

## 게이트
- 라이브 발효(O1 push·텔레그램 실발송)는 GM go.
- 비가역(시트/GAS 변경)은 자율 금지 — 제안만.
