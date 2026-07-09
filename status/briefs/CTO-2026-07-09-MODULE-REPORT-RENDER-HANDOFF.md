# 인계 브리프 — 모듈 보고 현황 렌더 (시토 → 웰리·시우 조율)

- 작성: 2026-07-09 · 시토(CTO) · 배 #750
- 목적: 시토가 만든 **모듈 자동보고 리포터 엔진**의 결과(모듈별 주기·최근발송·상태)를 **자율현황(T2) 화면**에 렌더. 화면은 웰리/시우 소유라 단독 편집 안 하고 조율.
- GM 결정(2026-07-09): "프론트 렌더를 웰리·시우와 조율해 마저."

## 배경 (안 겹치게)
- 공유 등록부 = `status/module_registry.json`(시우 구축·웰리 3-2 거버넌스). 시토 모듈 3건 등록: `cto-automation-health`·`cto-aide-gap-detector`·`cto-check-gas`.
- 시토 엔진(커밋 620a541c): `scripts/module_reporter.py`가 등록부를 **읽기만** 소비 → notify_spec 주기에 맞춰 텔레그램 보고. 실행 로그 = `status/module_report_log.jsonl`. 결정 큐 = `status/module_decisions.json`.
- 현재 자율현황.html `#layer-automation` 섹션 존재하나 **등록부 미연동**. 각 모듈 `front_card.anchor`(layer-automation / layer-autonomy)가 렌더 위치를 이미 가리킴.

## 렌더 요청 (읽기 전용·비파괴)
`#layer-automation`(또는 각 모듈 front_card.anchor)에 "모듈 보고 현황" 표 1개 추가:

| 칼럼 | 소스 |
|---|---|
| 모듈 | `module_registry.json` name/feature |
| 담당 | owner_nick |
| 주기 | notify_spec(daily/weekly/monthly) |
| 채널·봇 | notify_spec.channel + bot_id(null=미발효 배지) |
| 최근 발송 | `module_report_log.jsonl` 마지막 항목(없으면 '미발송') |
| 상태 | bot_id null=⚪미발효 / 발송성공=🟢 / 실패=🔴 / collector 미구현=⚪준비중 |

**정직 배지 필수**: bot_id 없는 모듈은 '미발효(방·봇ID 대기)', collector 없는 모듈은 '준비중'으로 — 도는 것처럼 보이게 하지 말 것.

## 시토가 제공 가능 (요청 시)
- 화면이 바로 쓸 **렌더 데이터 조립 헬퍼**를 시토 엔진 쪽에 추가 가능: `module_reporter`에 `render_rows()` 함수(등록부+로그→표 행 dict 리스트 반환, 읽기 전용). 화면은 이 함수/JSON만 렌더 → HTML 로직 최소화. **원하면 시토가 헬퍼만 별도 커밋**(화면 파일 미접촉).

## 경계
- 화면 HTML(`자율현황.html`) 편집 = 웰리/시우. 시토는 데이터·엔진만.
- 스키마 변경 필요 시 = 웰리 승인(3-2 거버넌스).
- 라이브 발효(방 생성→bot_id 기입→enabled→예약작업)는 별개 GM go.

## 다음
1. 웰리/시우: 위 표를 자율현황에 렌더할지·anchor 확정.
2. 필요 시 시토에 `render_rows()` 헬퍼 요청 → 시토 별도 커밋.
3. 렌더 후 시크릿 크롬 라이브 검수(웰리 표준).
