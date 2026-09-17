# Product

<!-- impeccable:product-schema 1 -->

이 파일은 화면 디자인 도구(Impeccable · `/impeccable`)가 읽는 제품 사실 한 장이다. 값의 정본은 `ssot/canon_values.json`·`CLAUDE.md`·`wellperion-brand` 스킬이며 여기엔 베끼지 않고 가리킨다. 디자인 결정(색·글꼴·부품)은 여기 적지 않는다 — 정본 = `3. 웰페리온 가이드/erp/brand/tokens.css`(웰페리온) · `erp/admin/platform_brand.css`(AX 랩스) · `assets/wp-ui.css`(간격·글자 단계).

## Platform

web (순수 HTML/CSS/JS 정적 화면 · 서버는 FastAPI · 프레임워크 없음)

## Users

- 웰페리온 실무진(실장·소장·팀장·강사) — 폰과 PC 에서 회원·문의·점검·결재 화면을 하루 여러 번 연다. 화면은 설명 없이 바로 쓰여야 한다.
- GM(운영 책임자) — 화면을 A3 로 인쇄해 읽는다. 한 장에 한눈에 들어와야 한다.
- 회원·손님(공개 화면) — 문의·종합접수처·강습 안내. 폰 우선.
- 파트너 센터 대표(AX 랩스 화면) — 소개서·요금·온보딩. 우리 회사 이름이 아니라 「AX 랩스」로 만난다.

## Product Purpose

- 웰페리온 ERP: 3,000평 정원제 스포츠클럽의 회원·문의·점검·결재·보고를 한 곳에서 돌리는 사내 화면 묶음(약 100장). 목적 = 사람이 손으로 하던 반복을 체계가 대신하고, 사람은 회원 앞에 선다.
- AX 랩스(사업부): 위 자동화를 다른 센터에 월 구독으로 제공. 첫 프로젝트 = 「피트니스 AX」.

## Positioning

- 웰페리온 = 정원제 스포츠클럽(공식 포지셔닝 · canon `positioning_kr`). 「피트니스」라는 말을 쓰지 않는다.
- AX 랩스 = 만든 것을 파는 회사가 아니라 **매일 실제로 쓰고 있는 자동화**를 파는 회사(파일럿 2곳 실증).

## Terminology

- 강습(레슨 ✗) · 스포츠클럽(피트니스 ✗) · 웰페리온 ERP(가이드허브 ✗) · 직함 뒤 「님」.
- 전체 목록·금지어 = `wellperion-brand` 스킬 §1 · canon `brand_terms`.

## Constraints

- 색·글꼴·용어는 canon 이 이긴다 — 디자인 도구가 바꾸지 않는다.
- 인사(CHRO)·재무(CFO) 화면은 나우열M 라인 — AI 가 손대지 않는다.
- 종합접수처 최종본은 잠금(status/reception_freeze.json).
- 인쇄 문서(A3·A4)는 화면 규격 밖.
- 실무진 화면은 한 번에 바꾸지 않는다 — 화면 단위로 알리고 바꾼다.

## Evidence

- 화면 규격 실측 = `scripts/ui_standard_check.py --저장 --ux` → `status/ui_standard.json`(2026-09-16 · 100장 중 6규격 통과 11장).
- UX 검수기 19항목 = `scripts/design_audit.py`.

## Open decisions

- 없음(디자인 방향은 화면마다 `wellperion-brand` §6 변수 3개로 정한다).
