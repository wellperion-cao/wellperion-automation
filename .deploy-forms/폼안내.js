/**
 * 웰페리온 구글폼 유지관리 — 자체폼 안내 문구 주입/원복
 * ─────────────────────────────────────────────────────────────────────────────
 * 배경(2026-07-24 GM 결정 "B 병행"):
 *   최근 한 주 접수 64건 중 강습 44건이 전부 구글폼으로 들어온다. 홈페이지(/ko/inquiry/)는
 *   이미 6종 모두 자체폼으로 연결돼 있는데도 그렇다 = 고객이 홈페이지를 안 거치고 구글폼
 *   주소를 직접 받아 들어온다는 뜻(강사 안내·카톡·QR·기존 안내물). 그래서 홈페이지를 고쳐도
 *   안 바뀌고, 구글폼 자체에 "여기로 오세요"를 붙이는 게 유일하게 듣는 지점이다.
 *   A(응답 중단)가 아니라 B(폼은 열어둔 채 안내만) — 고객 이탈 위험 없이 먼저 효과를 본다.
 *
 * ★왜 별도 프로젝트인가:
 *   운영 중인 문의 백엔드(.deploy-funnel-v2)에 FormApp 권한을 새로 붙이면 웹앱 재인증이
 *   필요해져 라이브 문의 접수가 멈출 수 있다. 폼 편집은 이 정비용 프로젝트에서만 한다.
 *
 * ★꼬리표 주의(실측 확인):
 *   자체폼 페이지는 URL 의 utm_source/medium/content 를 GAS 로 넘기고,
 *   Survey.js 가 채널칸을 `_canonicalChannel_(body.utmSource || body.inflow)` 로 정한다.
 *   → utm_source 를 붙이면 고객이 직접 고른 유입경로를 덮어써 채널 집계가 오염된다.
 *   그래서 여기서는 utm_medium·utm_content 만 쓴다(채널칸 무영향, 전환량은 그대로 측정).
 *
 * 사용법 (Apps Script 편집기에서 함수 선택 후 실행):
 *   1) reportForms()  — 읽기 전용. 각 폼 제목·응답접수 여부·안내 적용 여부만 확인.
 *   2) addNotice()    — 안내 문구를 폼 설명 맨 위에 붙인다. 원래 설명은 보존·복구용 저장.
 *   3) removeNotice() — 원래 설명으로 되돌린다.
 *   addNotice 는 멱등 — 여러 번 실행해도 안내가 겹쳐 쌓이지 않는다.
 */

// 국문 3종 — GM 지목(2026-07-24). 공유 드라이브 > 2. 운영부 > 1. 마케팅&회원 문의 관리.
var FORMS = [
  {
    id: '1TSKFow5_vcTimidjWI73Z4HZ3U1j8r8AGn6Z9EHvaQs',
    name: '멤버십 문의 Survey',
    url: 'http://wellperion.com/ko/inquiry-form/?type=membership&utm_medium=gform&utm_content=membership',
    tail: '상담·투어 예약까지 한 번에 진행됩니다.'
  },
  {
    id: '15ish7BWpc2lhZcuXYY1d3d2PUOe2-jeZgmFWjXWGknE',
    name: '성인 강습 Survey',
    url: 'http://wellperion.com/ko/inquiry-form/?type=adult&utm_medium=gform&utm_content=adult',
    tail: '종목·희망 시간까지 한 번에 남기실 수 있습니다.'
  },
  {
    id: '1QJ6q5WZ_KGgSdo9GbYEz3zilNx2bXnm5GS7NjFTToW8',
    name: 'WSC 강습 Survey',
    url: 'http://wellperion.com/ko/inquiry-form/?type=youth&utm_medium=gform&utm_content=youth',
    tail: '종목·자녀 연령까지 한 번에 남기실 수 있습니다.'
  }
];

// 안내 첫 줄 = 멱등 판정 표식. 이 문구가 이미 있으면 다시 붙이지 않는다.
var NOTICE_HEAD = '🔗 홈페이지에서 접수하시면 더 빠르게 안내받으실 수 있습니다';
var PROP_PREFIX = 'form_desc_backup_';

function _noticeText_(f) {
  return NOTICE_HEAD + '\n' + f.url + '\n\n' + f.tail + ' (이 양식으로도 접수하실 수 있습니다)';
}

// ═══════════════════════════════════════════════════════════════════════════
// 응답 마감 + 안내 (GM 2026-07-24 결정) — "질문 없이 안내만 보이게"
// ───────────────────────────────────────────────────────────────────────────
// 질문을 지우면 복구가 안 되므로(구글폼은 되돌리기 기록이 없다) 대신 폼을 '응답 마감'
// 상태로 돌린다. 방문자에겐 제목 + 아래 안내 문구만 보이고, 질문·과거 응답은 그대로
// 보존된다. 되돌리기 = reopenForms() 한 번.
// ★마감 상태에선 폼 '설명'이 표시되지 않는다 → 링크를 반드시 마감 메시지에 넣는다.
// ═══════════════════════════════════════════════════════════════════════════
function _closedMsg_(f) {
  return '문의 접수가 홈페이지로 옮겨졌습니다.\n\n'
       + '아래 주소에서 접수해 주시면 담당자가 확인 후 연락드립니다.\n'
       + f.url + '\n\n'
       + f.tail;
}

function _closeOne_(f) {
  var form = FormApp.openById(f.id);
  form.setCustomClosedFormMessage(_closedMsg_(f));
  form.setAcceptingResponses(false);
  return f.name + ' — 응답 마감 + 안내 문구 적용';
}

/** 1단계: 멤버십 폼만 마감(가장 위험 작은 것부터 — 웹이 이미 4건 중 3건을 받는다). */
function closeMembershipForm() {
  var out = [_closeOne_(FORMS[0])];
  Logger.log(out.join('\n'));
  return out;
}

/** 2단계: 강습 2종(성인·유소년) 마감 — 1단계 화면 확인 후 실행. */
function closeLessonForms() {
  var out = [_closeOne_(FORMS[1]), _closeOne_(FORMS[2])];
  Logger.log(out.join('\n'));
  return out;
}

/** 되돌리기 — 3종 모두 다시 응답 받기. 질문·과거 응답은 애초에 손대지 않았다. */
function reopenForms() {
  var out = [];
  for (var i = 0; i < FORMS.length; i++) {
    try {
      FormApp.openById(FORMS[i].id).setAcceptingResponses(true);
      out.push(FORMS[i].name + ' — 다시 응답 받는 중');
    } catch (e) { out.push(FORMS[i].name + ' — 실패: ' + e); }
  }
  Logger.log(out.join('\n'));
  return out;
}

/** 읽기 전용 — 현재 상태만 본다. 아무것도 바꾸지 않는다. */
function reportForms() {
  var out = [];
  for (var i = 0; i < FORMS.length; i++) {
    var f = FORMS[i];
    try {
      var form = FormApp.openById(f.id);
      var desc = form.getDescription() || '';
      out.push({
        폼: f.name,
        제목: form.getTitle(),
        응답받는중: form.isAcceptingResponses(),
        안내적용됨: desc.indexOf(NOTICE_HEAD) === 0,
        설명길이: desc.length
      });
    } catch (e) {
      out.push({ 폼: f.name, 오류: String(e) });
    }
  }
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}

/** 안내 문구를 폼 설명 맨 위에 붙인다(멱등). 원래 설명은 되돌리기용으로 보관. */
function addNotice() {
  var props = PropertiesService.getScriptProperties();
  var out = [];
  for (var i = 0; i < FORMS.length; i++) {
    var f = FORMS[i];
    try {
      var form = FormApp.openById(f.id);
      var desc = form.getDescription() || '';
      if (desc.indexOf(NOTICE_HEAD) === 0) { out.push(f.name + ' — 이미 적용됨(건너뜀)'); continue; }
      // 원래 설명 백업 — 한 번만 저장한다(재실행이 백업을 덮어쓰지 않게).
      var key = PROP_PREFIX + f.id;
      if (props.getProperty(key) === null) props.setProperty(key, desc);
      form.setDescription(_noticeText_(f) + (desc ? '\n\n' + desc : ''));
      out.push(f.name + ' — 안내 추가함');
    } catch (e) {
      out.push(f.name + ' — 실패: ' + e);
    }
  }
  Logger.log(out.join('\n'));
  return out;
}

/** 원래 설명으로 되돌린다. 백업이 없으면 안내 블록만 잘라낸다. */
function removeNotice() {
  var props = PropertiesService.getScriptProperties();
  var out = [];
  for (var i = 0; i < FORMS.length; i++) {
    var f = FORMS[i];
    try {
      var form = FormApp.openById(f.id);
      var key = PROP_PREFIX + f.id;
      var backup = props.getProperty(key);
      if (backup !== null) {
        form.setDescription(backup);
        props.deleteProperty(key);
        out.push(f.name + ' — 원래 설명으로 복구함');
      } else {
        var desc = form.getDescription() || '';
        var notice = _noticeText_(f);
        if (desc.indexOf(notice) === 0) {
          form.setDescription(desc.slice(notice.length).replace(/^\n+/, ''));
          out.push(f.name + ' — 안내만 제거함(백업 없음)');
        } else {
          out.push(f.name + ' — 안내 없음(변경 없음)');
        }
      }
    } catch (e) {
      out.push(f.name + ' — 실패: ' + e);
    }
  }
  Logger.log(out.join('\n'));
  return out;
}
