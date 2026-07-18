# 습득물 직원화면 종합접수처 통합 + 월별 필터 — Stage 3

> COO 시우 · 2026-07-18 · GM 확정(종합접수처 통합 추천 + 월필터 직원·회원 둘 다)
> 선행: 2트랙 처분(배1403)·가이드·뷰분리·중복제거 완료. 본 스펙 = 직원 처리면을 게이트된 종합접수처로 이관, 공개 현황은 회원 전용.

## 배경
공개 현황(/ko/lost-found/)은 회원도 보는데 ?staff=1 URL 토글로 직원 컨트롤 노출 = 불안전. GM 결정: 직원 습득물 처리를 이미 gate된 종합접수처_현황(습득물 7번째 카테고리로 이미 표시 중)에 통합. 공개 현황=순수 회원 둘러보기. 추가: 습득물·분실물 접수를 월 단위로 골라보기(직원·회원 둘 다).

## A. 공개 gallery 회원 전용화 (lost_found_gallery.html + wp_ block)
제거(조사 근거 라인): ?staff 감지 스크립트, staff-only CSS, 수령(claim)·삭제(del)·A3 인쇄 버튼, 처분완료 기록 섹션+렌더, 🛠직원모드 배지, info-note 직원문구, 수령 서명 모달 전체+JS(handover/delete), 직원전용 상수(VOC_SUBMIT_TOKEN·STAFF·확인비번·모달 LOCATIONS). count-pill·refresh도 제거(직원 화면으로 이관됨).
유지: 브랜드 헤더, 보관·처분 안내(.lf-policy), 카드(사진·설명·장소·시각), ⏳M월 처분예정 배지(회원 노출), loadDisposal의 upcoming 배지만(disposed 렌더 제거).
추가: **월 선택 필터** — 카드의 foundWhen(YYYY-MM-DDTHH:mm, slice(0,7)) 월 추출. 그리드 위 셀렉트/칩 '전체'+존재하는 습득월(내림차순). 선택 월만 카드 표시. 라벨 'YYYY년 M월'.

## B. 종합접수처_현황.html 직원 통합 (Pages 단독, gate.js 뒤)
습득물 카드(_card r._lf 분기, divider 뒤 빈자리)에 컨트롤 삽입 — VOC 카드가 같은 위치에 status select·저장 렌더하는 검증 패턴 재사용, 이벤트는 #board 위임(_wireBoard) 확장(data-lf-* 속성):
- **수령**: 서명 모달을 gallery에서 포팅(순수 canvas·fetch, 외부lib 0). 이식 묶음: VOC_SUBMIT_TOKEN·LOCATIONS·STAFF·확인비번(62611200)·모달CSS(다크테마 색 조정)·toast(종합접수처 없음→이식)·서명패드JS·_cur 흐름. lf_handover payload 동일. VOC_API=REG_API 동일 URL.
- **삭제**: lf_delete(오등록), confirm 후.
- **A3 처분공지**: lost_found_disposal.html 링크(이미 lf-note에 있음, 버튼화).
- **월 필터**: 3번째 .filter-block(월 칩/셀렉트) 추가, _filtered()에 월 조건 한 줄. 습득물=foundWhen 월, 분실물접수(VOC 📦)=createdAt 월(포맷 서버제공·표시용, 월 파싱 방어적). '전체'+월 내림차순.

## 검증
- 공개 gallery: 회원뷰 시크릿크롬 — 직원요소 0·월필터 동작·⏳배지 유지·콘솔0. Pages·WP 200.
- 종합접수처: gate 통과 후 습득물 카드 수령/삭제/A3 노출·월필터 동작·수령 모달 렌더·콘솔0. (수령 lf_handover는 테스트항목 1건 생성→handover→삭제 E2E 또는 렌더+배선 확인.)
- 백엔드 무변경(GAS 재배포 불요) — 표시·호출만.
- WP 재주입: gallery 1블록(register 무변경). 종합접수처는 Pages 단독(WP 아님).

## 후속(비목표)
- 진짜 인증(gate.js=세션 비번 커튼, JWT ≈9월). 분실물접수 createdAt 포맷 확정. 수령 위조방지 강화.
