/**
 * 멤버십 문의 관리 시트 — '26년 신규문의(영)' 탭 폐기 (설문지 연결 해제 + 탭 삭제)
 * ─────────────────────────────────────────────────────────────────────────────
 * GM 지시 2026-07-24. 근거: 영문 멤버십 폼은 전 기간 접수 0건이고, 영어 문의는 자체폼으로
 * 전환돼 한글 탭에 '유입언어'·[영어] 표식으로 함께 쌓인다 → 별도 탭을 둘 이유가 없다.
 *
 * ★순서를 지켜야 하는 이유(Survey.js:39 에 박힌 함정):
 *   폼이 살아있는 채로 연결만 끊으면, 다음 응답이 올 때 구글이 **새 응답탭을 자동 생성**한다.
 *   그 탭은 아무 코드도 안 읽으므로 영어 문의가 조용히 사라진다(2026-07-09 CRM 누락 사고와 동종).
 *   그래서 반드시  ① 폼 응답 받기 중지 → ② 연결 해제 → ③ 탭 삭제  순서로 진행한다.
 *
 * ★안전장치: 탭에 헤더 말고 실제 데이터가 한 줄이라도 있으면 **삭제하지 않고 중단**한다.
 *   '0건'은 기록이 아니라 실제로 세어 확인한다.
 *
 * 사용법 (편집기에서 함수 선택 후 실행):
 *   1) reportEnSheet()  — 읽기 전용. 탭 존재·데이터 줄수·폼 연결·응답 수신 여부만 본다.
 *   2) retireEnSheet()  — 위 순서대로 실제 정리. 데이터가 있으면 스스로 중단한다.
 */

var MI_SS_ID     = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';  // 1-1) 멤버십 문의 관리(26년도)
var EN_SHEET_GID = 1887747109;                                       // '26년 신규문의(영)' 응답탭
var EN_FORM_ID   = '1MAqXaoH_nb2UznpTigd4nDnp_gFygkMn1cYpdpB7Z74';   // 1) Membership Inquiry (영문)

function _enSheet_(ss) {
  var all = ss.getSheets();
  for (var i = 0; i < all.length; i++) if (all[i].getSheetId() === EN_SHEET_GID) return all[i];
  return null;
}

/** 읽기 전용 — 아무것도 바꾸지 않는다. */
function reportEnSheet() {
  var ss = SpreadsheetApp.openById(MI_SS_ID);
  var sh = _enSheet_(ss);
  var out = { 스프레드시트: ss.getName() };
  if (!sh) {
    out.탭 = '없음(이미 삭제된 듯)';
  } else {
    var last = sh.getLastRow();
    out.탭이름 = sh.getName();
    out.전체줄수 = last;
    out.데이터줄수 = Math.max(0, last - 1);          // 1줄 = 헤더만
    out.삭제해도되나 = (last <= 1);
    out.연결된폼 = sh.getFormUrl() || '(연결 없음)';
    if (last > 1) {
      // 데이터가 있으면 뭐가 들어있는지 앞 3줄만 보여준다(삭제 전 판단 근거).
      out.앞3줄 = sh.getRange(1, 1, Math.min(4, last), Math.min(6, sh.getLastColumn())).getDisplayValues();
    }
  }
  try {
    var form = FormApp.openById(EN_FORM_ID);
    out.폼제목 = form.getTitle();
    out.폼_응답받는중 = form.isAcceptingResponses();
    out.폼_응답수 = form.getResponses().length;
    out.폼_연결대상 = form.getDestinationId ? (form.getDestinationId() || '(없음)') : '(확인불가)';
  } catch (e) {
    out.폼오류 = String(e);
  }
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}

/** 실제 정리 — ①응답 중지 ②연결 해제 ③탭 삭제. 데이터가 있으면 삭제하지 않고 중단. */
function retireEnSheet() {
  var log = [];
  var ss = SpreadsheetApp.openById(MI_SS_ID);
  var sh = _enSheet_(ss);

  // ── 0) 삭제해도 되는지 먼저 센다(기록 아니라 실제 값으로) ──
  if (!sh) {
    log.push('탭이 이미 없음 — 삭제 단계 건너뜀');
  } else {
    var last = sh.getLastRow();
    log.push('탭 「' + sh.getName() + '」 전체 ' + last + '줄 (데이터 ' + Math.max(0, last - 1) + '줄)');
    if (last > 1) {
      log.push('❌ 중단 — 데이터가 남아 있어 삭제하지 않았습니다. 내용을 먼저 확인하세요.');
      Logger.log(log.join('\n'));
      return log;
    }
  }

  // ── 1) 폼 응답 받기 중지 (이걸 먼저 안 하면 연결 해제 후 새 탭이 자동 생성된다) ──
  try {
    var form = FormApp.openById(EN_FORM_ID);
    var n = form.getResponses().length;
    log.push('폼 「' + form.getTitle() + '」 누적 응답 ' + n + '건');
    if (n > 0) {
      log.push('❌ 중단 — 폼에 응답이 남아 있습니다. 폐기 전 확인 필요.');
      Logger.log(log.join('\n'));
      return log;
    }
    if (form.isAcceptingResponses()) {
      form.setAcceptingResponses(false);
      log.push('① 폼 응답 받기 중지함');
    } else {
      log.push('① 폼은 이미 응답 중지 상태');
    }
    // ── 2) 스프레드시트 연결 해제 ──
    try {
      form.removeDestination();
      log.push('② 설문지↔시트 연결 해제함');
    } catch (e2) {
      log.push('② 연결 해제 건너뜀(이미 해제됨 또는 불가): ' + e2);
    }
  } catch (e) {
    log.push('폼 처리 실패: ' + e);
    log.push('❌ 중단 — 폼을 못 다뤘으므로 탭은 그대로 둡니다(연결만 끊고 삭제하면 새 탭이 생긴다).');
    Logger.log(log.join('\n'));
    return log;
  }

  // ── 3) 탭 삭제 ──
  if (sh) {
    ss.deleteSheet(sh);
    log.push('③ 탭 삭제함');
  }
  log.push('✅ 완료');
  Logger.log(log.join('\n'));
  return log;
}
