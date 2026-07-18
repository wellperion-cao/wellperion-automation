# 습득물 파이프라인 단순화 + 폐기물 생애주기 (COO 시우 · 2026-07-18)

## 배경 / GM 지시
GM 피드백: 습득물이 종합접수처 6종과 따로 노는 느낌. 별도 '등록·관리·철회' 페이지 불필요.
→ **접수(6종처럼) → 습득물 보기에서 수령 마무리** 2단계로 단순화. 철회 폐지.
+ 30일 경과 미수령품 = **폐기물**(A3 공지 + 시트 정리).

## GM 확정 결정 (AskUserQuestion 2026-07-18)
1. 폐기물 전환 = **완전 자동** (30일 경과 시 시스템이 폐기물 처리·게시서 내림)
2. A3 공지 = **폐기 예정 + 폐기 완료 둘 다** 한 장
3. 시트 = **기존 습득물 시트에 통합** (상태값 '폐기물' + '폐기일' 컬럼)

## 새 생애주기 (상태)
- `게시중`(POSTED) → 갤러리·현황 노출
- `수령완료`(HANDED) → lf_handover(서명)
- `폐기물`(DISPOSED) ← **신규**. 습득일+30일 경과 & 게시중 → 자동 전환, 폐기일 기록, 공개 갤러리서 제외
- `삭제` ← 오등록(lf_delete, 직원 게이트). 철회(VOID) 폐지
- (기존 VOID '철회' = 제거)

## 백엔드 (GAS · VOC_배포.js 배포본 + apps_script_voc.js 소스 동시)
1. `LF_STATUS`에 `DISPOSED:'폐기물'` 추가. `VOID` 제거(라우터·게이트·_lfVoid 삭제).
2. `LF_HEADERS` 맨 끝에 `{ key:'disposedAt', label:'폐기일' }` 추가(positional write 정합 위해 반드시 끝).
3. `_lfGetSheet_`에 **헤더 리페어**: 기존 시트 헤더행에 없는 라벨(폐기일) 자동 append(기존 데이터 무손상).
4. `_lfAutoDispose_(sh)`: 게시중 행 중 습득일(foundWhen 없으면 createdAt)+30일 ≤ 오늘 → status=폐기물·disposedAt=오늘 일괄 write. 변경 있을 때만 저장(멱등).
   - `_lfGallery`·`_lfList`·`_lfDisposal` 시작부에서 호출(read-time sweep = 크론 없이 완전자동, 자가치유).
5. `_lfGallery`: 게시중만(폐기물·수령완료 제외) — 자동 sweep 후라 폐기물 자동 제외됨.
6. **신규 `lf_disposal`**(공개 read·민감필드 미반환): `{ upcoming:[게시중·잔여일≤7], disposed:[폐기물·폐기일 desc] }` 반환. 각 항목 foundId·itemDesc·foundLoc·foundWhen·photoUrl·잔여일/폐기일만.
7. `lf_delete`(기존) 유지 = 오등록 삭제(행삭제·게이트). 프론트는 갤러리 직원 게이트에서 호출.

## 프론트
- **lost_found_register.html (습득물 접수)**: 관리 탭 완전 제거. 접수(등록) 단일 폼만. 안내문 '30일 미수령 자동 폐기(폐기 공지 게시)'로 갱신.
- **lost_found_gallery.html (습득물 보기)**: 수령(서명) 유지. 직원 게이트 뒤 **🗑 삭제(오등록)** 추가(lf_delete·확인+토큰). 안내 '30일 자동 폐기' 한 줄.
- **NEW lost_found_disposal.html (폐기물 공지 A3)**: 좌측정렬 풀폭 A3 한 장. ⏳폐기 예정(회원 '찾아가세요' 독촉) + 🗑 폐기 완료(기록) 2블록. lf_disposal 소스. 게시판 인쇄용.
- **종합접수처_현황.html**: 습득물 카드 안내문/링크 갱신 — "수령=습득물 보기 · 30일 미수령 자동 폐기(폐기 공지)". '철회/등록·관리' 문구·링크 제거. 링크 3개(접수·보기·폐기공지).
- **reception_block.html**: lf-btn 링크 정리(습득물 접수 · 습득물 보기 · 폐기 공지).
- **WP 블록**(wp_lost_found_register_block·wp_lost_found_gallery_block) + WP 발행페이지 재주입(관리탭 제거·삭제 추가 반영). ★WP발행=즉시라이브 → 검수 후 주입.

## 배포 핸드오프
- 프론트(GitHub Pages)=커밋·푸시 즉시 라이브.
- GAS 웹앱=수동 재배포 필수(clasp≠웹앱배포). VOC_배포.js 코드 → Apps Script 편집기 붙여넣기 → /exec 새 버전 배포. GM 크롬+메모장 페어. 배포 전까지 폐기물 자동전환·lf_disposal·삭제는 미발효(프론트는 준비).

## 검증
- 시크릿 크롬 Playwright: 접수(관리탭 없음)·보기(수령/삭제)·폐기공지 A3 렌더·현황 안내 정합·콘솔0.
- 폐기 자동전환은 GAS 배포 후 실데이터로 확인(습득일 30일+ 항목).
