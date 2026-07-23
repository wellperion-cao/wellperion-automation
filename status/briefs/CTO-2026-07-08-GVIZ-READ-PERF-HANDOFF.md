# [시포→시토] 문의현황 로딩 성능 근본 개선 — gviz 직접 읽기 재설계

- **일자**: 2026-07-08 · 요청=GM("너무 느려, 시토한테 말해서라도 정리") · 소유 이관=시포(CPO)→시토(CTO, 인프라)
- **결정**: GM이 3안(캐시워머/gviz/서버위임) 중 **gviz 직접 읽기** 택 (첫 로딩 6~9초→~1초 목표)

## 문제 (현행)
- `member_inquiry_list`·`lesson_inquiry_list`가 호출마다 Apps Script로 600행 콜드 리드 → 첫 로딩 6~9초(과부하 시 40~70초).
- 시포가 넣은 60초 조회 캐시(licache/micache, 청크분할)는 **연속 재호출만** 빠르게 함 → 단일 사용자 첫 로딩엔 무효.
- 근본 지연 = GAS 스크립트 콜드스타트 + 대량 행 읽기. 캐시로는 반쪽.

## 방향 (gviz)
- 읽기를 Apps Script 우회 → 시트 gviz 엔드포인트 직접 조회:
  `https://docs.google.com/spreadsheets/d/{SS_ID}/gviz/tq?tqx=out:json&gid={GID}`
- **쓰기(update/add/delete)는 그대로 GAS 유지** (gviz는 읽기전용). contacts·status·owner 저장 = 기존 `*_inquiry_update`.

## ⚠️ 보안 게이트 (GM go 필수)
- gviz가 공개 페이지에서 읽으려면 대상 시트를 **"링크 있는 누구나 보기"로 공개**해야 함.
- 결과: 현행 입장 비밀번호 게이트(pii_status) 무의미화 + 회원 실명·전화 링크 노출. 9월 JWT 로드맵과 상충하나 GM "의도된 임시 공개" 방침과는 일관.
- **발효(시트 공개)는 GM 명시 승인 시에만.** 역롤백=공유 해제 1초. feedback_security_live_activation_needs_gm_go 준수.

## 구현 설계 (핵심 난점 = 컬럼 매핑 이식)
1. **컬럼 검출 로직 클라이언트 이식**: 현재 `_lessonReadRows_`/`_miReadRows_`(Survey.js)의 `_findCol_` 퍼지 헤더 매칭 + 관리컬럼(진행상태·관리담당·연락이력·상담메모·상담예약·방문상태)을 gviz 파싱 클라이언트 코드로 복제. 헤더 변형에 강하게.
2. **gviz JSON 파싱**: `google.visualization.Query.setResponse({...})` 언랩 → rows/cols → 행객체(timestamp/name/phone/sport/status/owner/memo/contacts…)로. 기존 프론트 렌더(lessonRender/renderDbTable)가 받는 shape와 동일하게 어댑터.
3. **연락이력(JSON 컬럼) 파싱 + 흡수**: gviz로 읽은 `연락이력` 파싱 + 비면 C1/2/3(멤버십)·상담메모(강습) 합성 — 백엔드와 동일 규칙 클라 이식.
4. **역롤백 스위치**: 프론트 플래그(예 `USE_GVIZ`)로 gviz↔GAS 읽기 즉시 전환. 문제 시 GAS 읽기로 1줄 복귀.
5. **PII 최소화 검토**: 가능하면 gviz `tq` 쿼리(select)로 필요한 열만 요청(전체 시트 통째 노출 축소).

## 대상 시트
- 멤버십: `26년 신규문의`(SS_ID=시포 `_miSheet_` 참조 — Survey.js에서 확인).
- 강습: `LESSON_SS_ID=1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw` · gid 성인 `111889422` / 유소년 `268994754`.

## 검증
- 로딩 시간 실측(gviz vs 현행), 컬럼 매핑 회귀(모든 필드 동일 렌더), 콘솔0, 역롤백 스위치 동작.
- ⚠️ GAS 과호출 금지(오늘 throttle 이력) — 검증 최소.

## 병행
- 시포는 강습 CONTACT 백엔드/프론트를 **현행 GAS 읽기** 위에 계속 완성(읽기 소스만 후속 gviz 교체). 렌더 로직 유지가 전제라 어댑터만 갈아끼우면 됨.
