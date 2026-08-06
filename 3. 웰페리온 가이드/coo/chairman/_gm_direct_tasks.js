/*!
 * _gm_direct_tasks.js · 김남욱GM_업무.html · 월간운영계획.html(GM 토글) 공용 소스 (2026-08-05 GM 지시 —
 * "구매 관련은 시뽀 건이라 건드리지 말고, 김남욱GM 업무 진행건은 업무 시트에서 가져올 생각 말고 별도로
 * 만들어" — 정본을 업무 시트(todo_list)에서 status/monthly_ops_plan.json 해당월 목표로 전환). 대표님 칸은
 * 여전히 업무 시트(todo_list)를 그대로 쓴다(월간운영계획.html readWorkApproval() 참조) — 두 칸이 서로 다른
 * 소스를 쓰는 것은 GM 지시에 따른 의도된 분리다.
 * 판정 기준: 해당월 objectives 중 제목에 "(GM 직접)" 포함 — GM 이 직접 관장하는 건만(실측 예: 리셉션
 * 상담실 리뉴얼 · 목욕탕 허가건 진행 · 지원부 약품·비품 비교 구매 구조 만들기). 원본 데이터엔 카테고리 칸이
 * 없어 목표 내용을 보고 업무 시트와 동일한 9종 체계로 사람이 분류해 아래 표에 고정했다(회장님_지시사항.html
 * CHAIRMAN_ITEMS.cat과 같은 방식) — 새 GM 직접 건이 늘면 이 표에 한 줄만 추가한다(약속 L01, 로직 복제 없음).
 * 판단이 서지 않는 항목은 '분류 미정'(지어내지 않음).
 */
(function () {
  "use strict";
  var GM_TAG = '(GM 직접)';
  // id → 9종 체계 카테고리(시트 9종: 매출 및 영업/인사/파트너팀/운영 정책/시설 및 환경/회원·CS/IT·시스템·자동화/교육·조직문화/회의)
  var CATEGORY_BY_ID = {
    '2026-08-18': '시설 및 환경', // 리셉션 상담실 리뉴얼 — 공사·공간 전환
    '2026-08-21': '시설 및 환경', // 목욕탕 허가건 진행 — 시설(목욕탕) 인허가
    '2026-08-23': '운영 정책',    // 지원부 약품·비품 비교 구매 구조 — 내부 프로세스 설계
    '2026-08-07': '운영 정책',    // 4개 부서 통합 관리 안정화 — 부서 운영 체계(2026-08-05 GM 담당 확정 건)
    '2026-08-24': '매출 및 영업'  // 오넛티 추석 선물세트 2차 — 제휴 판매 프로젝트(2026-08-06 GM 등록)
  };
  function catFor(id) { return CATEGORY_BY_ID[id] || '분류 미정'; }
  // 판정 함수 단일 출처(약속 L01) — 월간운영계획.html의 "이달 핵심 과제 상세" 목록도 이 함수로 GM 직접 건을
  // 제외한다(2026-08-05 GM 지시). 두 화면이 각자 title.indexOf(...)를 다시 짜면 판정이 두 벌로 갈라진다.
  function isGmDirect(title) { return String(title || '').indexOf(GM_TAG) !== -1; }
  // 'YYYY-MM' → '26.8.1~26.8.31' (해당월 전체 — 목표 자체에 시작·종료일이 없어 추적 대상 월 범위를 그대로 표기, 날짜 지어내지 않음).
  function monthRange(monthKey) {
    var m = String(monthKey || '').match(/^(\d{4})-(\d{2})$/);
    if (!m) return '일정 미정';
    var y = +m[1], mo = +m[2];
    var last = new Date(y, mo, 0).getDate();
    var yy = String(y).slice(2);
    return yy + '.' + mo + '.1~' + yy + '.' + mo + '.' + last;
  }
  // plan = status/monthly_ops_plan.json 파싱 결과, monthKey = 'YYYY-MM'. 반환 = []( 정상 0건 ) · [{...}](정상 n건).
  // plan 자체가 없으면 [] (호출부에서 조회 실패와 정상 0건을 구분해 처리).
  function extract(plan, monthKey) {
    var month = plan && plan.months && plan.months[monthKey];
    var objs = (month && month.objectives) || [];
    var schedule = monthRange(monthKey);
    return objs
      .filter(function (o) { return isGmDirect(o.title); })
      .map(function (o) {
        return {
          id: o.id,
          // 화면 제목에서 "(GM 직접)" 표식은 뗀다 — 이 목록 자체가 GM 직접 건이라 매 줄에 붙으면 군더더기고,
          // 카테고리도 소괄호로 붙어(2026-08-05 GM 지시) 괄호가 겹쳐 읽힌다. 표식은 정본(monthly_ops_plan.json)
          // 제목에 그대로 남아 판정(isGmDirect)은 계속 그 값으로 한다.
          title: String(o.title || '').replace(GM_TAG, '').replace(/\s{2,}/g, ' ').trim(),
          category: catFor(o.id),
          schedule: schedule,
          target: o.target || '',
          status: o.status || '',
          progress: o.progress
        };
      });
  }
  window.WellperionGmDirect = { extract: extract, isGmDirect: isGmDirect, GM_TAG: GM_TAG };
})();
