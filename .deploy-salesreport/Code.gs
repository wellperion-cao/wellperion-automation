/**
 * 매출 보고 시트 — 운영 현황 칸(P20) 채우기 전용 웹앱
 *
 * 무엇을 하나
 *   웰페리온 자동화 PC가 매일 아침 09:00 에 시설·청결·주차·밸류업 현황을 만들어
 *   이 웹앱으로 보내면, 「보고」 탭 P20 한 칸에만 써 넣는다. 09:30 매출보고 이미지가
 *   그 칸을 포함해 찍히므로 회장님·관리부·부서장·운영부가 같은 화면에서 함께 본다.
 *
 * 안전 장치 (일부러 좁게 만들었다)
 *   · 쓰기 대상 칸이 ALLOWED_CELLS 목록에 있는 것만 허용한다. 다른 칸은 요청이 와도 거부한다.
 *   · TOKEN 이 맞지 않으면 아무것도 하지 않는다.
 *   · 쓰기 전 그 칸의 값 길이를 응답에 담아 돌려준다(덮어쓴 것이 무엇이었는지 남는다).
 *   · 읽기(doGet)는 현재 값 확인만 한다. 지우거나 다른 시트를 건드리지 않는다.
 *
 * 설치 방법
 *   1) 이 스프레드시트에서 확장 프로그램 → Apps Script
 *   2) 코드를 전부 지우고 이 내용을 붙여넣기
 *   3) 아래 TOKEN 을 원하는 값으로 바꾸기(웰페리온 자동화 쪽에도 같은 값을 넣는다)
 *   4) 배포 → 새 배포 → 유형 '웹 앱'
 *        실행 계정 = 나
 *        액세스 권한 = 모든 사용자
 *   5) 나온 웹앱 주소(/exec 로 끝나는 것)를 알려주면 매일 09:00 발송을 붙인다
 *
 * 고칠 때
 *   코드를 고친 뒤에는 반드시 '배포 → 배포 관리 → 편집(연필) → 버전: 새 버전 → 배포' 를
 *   눌러야 실제로 바뀐다. 저장만 하면 옛 버전이 계속 돈다.
 */

var TOKEN = 'wellperion-2026';           // ★ 바꿔 주세요. 자동화 쪽에도 같은 값을 넣습니다.
var SHEET_NAME = '보고';
// 여기 없는 칸에는 절대 쓰지 않는다.
//   P20 = 운영 현황(09:00 sales_report_ops_summary 가 채운다)
//   I16 = 「금일 예상 컨택 및 매출 현황」 오늘 열 — 총 예약자·신규(투어/체험 이름)·재등록·LOSS 를
//         지금은 사람이 손으로 친다. 원천은 이미 매일 자동으로 쌓인다(문의 원장 예약/체험 · 종료회원 원장 LOSS).
//         2026-08-21 시토가 「보고」 탭을 직접 읽어 이 칸임을 확인하고 열었다(배738).
//         ※ 왼쪽 블록 B16 은 '어제' 열이라 열지 않는다 — 사람이 옮겨 적는 자리가 아니라 지나간 기록이다.
//   I18 = 「로스자」 칸 — 전날 LOSS 기준. 2026-08-28 GM 이 두 칸의 뜻을 직접 갈라 주셨다:
//         "I16은 내일 투어 및 체험 예약(오늘 예약 달력 참고) / I18은 전날 LOSS기준".
//         그 전까지는 I16 한 칸에 예약과 LOSS 를 함께 써서 기준일이 섞여 있었다.
var ALLOWED_CELLS = ['P20', 'I16', 'I18'];
// 통째 읽기(dump) 허용 범위 — 09:30 매출보고 이미지가 찍히는 그 범위와 같다.
// 여기를 넓히면 시트의 다른 내용까지 밖으로 나간다. 넓힐 때는 무엇이 함께 나가는지 보고 정한다.
var DUMP_RANGE = 'H2:S21';

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/** 열 번호 → A1 표기(1=A · 27=AA). find 응답에서 칸 주소를 만들 때만 쓴다. */
function _a1(col) {
  var s = '';
  while (col > 0) {
    var m = (col - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    col = (col - 1 - m) / 26;
  }
  return s;
}

/** 강습 상품명 → 보고 표의 팀 이름. 시트 오른쪽 팀별 매출표와 같은 말을 쓴다.
 *  못 가리는 상품은 '기타'로 둔다 — 엉뚱한 팀에 붙이는 것보다 낫다. */
function _lessonTeam(item) {
  var s = String(item || '');
  if (/P\.?\s*T|피티/i.test(s))              return 'P.T팀';
  if (/필라테스/.test(s))                     return 'P.L팀';
  if (/스쿼시/.test(s))                       return '스쿼시팀';
  if (/수영|아쿠아/.test(s))                  return '수영팀';
  if (/체조|트램폴린/.test(s))                return '체조팀';
  if (/골프/.test(s))                         return '골프팀';
  if (/GXE|줌바|G\.?X/i.test(s))              return 'GXE(파트너팀)';
  if (/발레|바레|뮤지컬/.test(s))             return '뮤지컬팀';
  return '기타';
}

function _sheet() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  if (!sh) throw new Error('시트를 찾지 못했습니다: ' + SHEET_NAME);
  return sh;
}

/** 현재 값 확인용 — 아무것도 바꾸지 않는다. */
function doGet(e) {
  var p = (e && e.parameter) || {};
  if (p.token !== TOKEN) return _json({ ok: false, error: 'unauthorized' });
  // 칸 찾기 — 보고 탭에서 어떤 글이 어느 칸에 있는지 주소를 돌려준다(읽기 전용).
  // 쓰기 허용 칸을 늘릴 때마다 사람이 시트를 열어 주소를 확인해 주던 것을 없앤다(2026-08-28).
  // 값은 앞 40자만 돌려준다 — 주소를 찾는 것이 목적이라 본문을 통째로 내보내지 않는다.
  if (p.find) {
    var rng = _sheet().getRange(p.range || 'A1:S40');
    var vals = rng.getDisplayValues();
    var r0 = rng.getRow(), c0 = rng.getColumn(), out = [];
    for (var r = 0; r < vals.length; r++) {
      for (var c = 0; c < vals[r].length; c++) {
        var s = String(vals[r][c] || '');
        if (s && s.indexOf(p.find) >= 0) {
          out.push({ cell: _a1(c0 + c) + (r0 + r), head: s.substring(0, 40) });
        }
      }
    }
    return _json({ ok: true, find: p.find, hits: out });
  }
  // 보고 범위 통째 읽기 — ERP 「일일 운영보고」 화면이 시트 캡처 대신 값을 받아 직접 그린다.
  //   (GM 지시 2026-08-28: "운영 현황 상세에 버튼 누르면 지금 나오는 보고시트처럼 정리해서")
  //   읽기 전용이고 범위는 09:30 보고가 찍는 그 범위(H2:S21)로 고정한다 — 시트 다른 곳은 안 준다.
  if (p.dump) {
    // sheet·range 를 주면 같은 파일의 다른 탭(일자탭 등)도 읽는다 — 읽기 전용이고 400칸으로 막는다.
    // 어느 칸이 어디서 오는지 사람이 시트를 열어 확인해 주던 것을 없애려고 열었다(2026-08-28).
    var dsh = p.sheet ? SpreadsheetApp.getActiveSpreadsheet().getSheetByName(p.sheet) : _sheet();
    if (!dsh) return _json({ ok: false, error: 'sheet not found: ' + p.sheet });
    var dr = dsh.getRange(p.sheet ? (p.range || 'A1:H20') : DUMP_RANGE);
    if (dr.getNumRows() * dr.getNumColumns() > 400) return _json({ ok: false, error: 'range too large' });
    var dv = dr.getDisplayValues();
    var dr0 = dr.getRow(), dc0 = dr.getColumn(), cells = {};
    for (var dy = 0; dy < dv.length; dy++) {
      for (var dx = 0; dx < dv[dy].length; dx++) {
        var val = String(dv[dy][dx] || '');
        if (val) cells[_a1(dc0 + dx) + (dr0 + dy)] = val;
      }
    }
    // formula=1 이면 각 칸의 수식도 함께 준다 — 어느 칸이 자동(수식)이고 어느 칸이
    // 사람 손입력인지 가리는 데 쓴다. 값은 그대로 두고 fx 맵만 덧붙이므로 기존 호출부는 영향 없다.
    var fx = null;
    if (p.formula) {
      var df = dr.getFormulas();
      fx = {};
      for (var fy = 0; fy < df.length; fy++) {
        for (var fxi = 0; fxi < df[fy].length; fxi++) {
          var f = String(df[fy][fxi] || '');
          if (f) fx[_a1(dc0 + fxi) + (dr0 + fy)] = f;
        }
      }
    }
    return _json({ ok: true, range: dr.getA1Notation(), sheet: dsh.getName(), cells: cells, fx: fx, at: Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm') });
  }
  // 강습 신규·재등록 — 일자탭 「강습 계약 현황」 블록(H8:N60)을 종목 × 등록분류로 센다.
  //   시트는 이 블록을 팀별 매출 합계로만 접어서 오른쪽 표에 올린다. 그래서 신규인지 재등록인지는
  //   사람이 매일 M열에 적고 있는데도 어디에도 안 보였다(GM 2026-08-28: "강습도 신규/재등록 구분이
  //   가능한지"). 여기서는 이미 적힌 칸을 읽기만 한다 — 실무진이 새로 채울 칸을 만들지 않는다.
  if (p.lesson) {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var dayName = String(_sheet().getRange('I1').getDisplayValue() || '').trim();
    var dsh2 = ss.getSheetByName(dayName);
    if (!dsh2) return _json({ ok: false, error: 'day tab not found: ' + dayName });
    var lv = dsh2.getRange('J8:N60').getDisplayValues();   // 종목 · 결제금액 · 결제방법 · 등록분류 · 등록경로
    var teams = {}, total = {};
    for (var li = 0; li < lv.length; li++) {
      var item = String(lv[li][0] || '').trim();
      var cls  = String(lv[li][3] || '').trim();
      if (!item || !cls) continue;
      if (cls.indexOf('신규') < 0 && cls.indexOf('재등록') < 0) continue;   // 양도·환불은 세지 않는다
      var kind = cls.indexOf('신규') >= 0 ? '신규' : '재등록';
      var amt = Number(String(lv[li][1] || '').replace(/[^0-9-]/g, '')) || 0;
      var team = _lessonTeam(item);
      if (!teams[team]) teams[team] = {};
      if (!teams[team][kind]) teams[team][kind] = { count: 0, amount: 0 };
      teams[team][kind].count++; teams[team][kind].amount += amt;
      if (!total[kind]) total[kind] = { count: 0, amount: 0 };
      total[kind].count++; total[kind].amount += amt;
    }
    return _json({ ok: true, day: dayName, teams: teams, total: total,
      at: Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm') });
  }

  var cell = p.cell || ALLOWED_CELLS[0];
  if (ALLOWED_CELLS.indexOf(cell) < 0) return _json({ ok: false, error: 'cell not allowed: ' + cell });
  var v = _sheet().getRange(cell).getDisplayValue();
  return _json({ ok: true, cell: cell, length: v.length, value: v });
}

/** 값 써 넣기 — 허용된 한 칸에만. */
function doPost(e) {
  var body;
  try {
    body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
  } catch (err) {
    return _json({ ok: false, error: 'bad json' });
  }
  if (body.token !== TOKEN) return _json({ ok: false, error: 'unauthorized' });

  var cell = body.cell || ALLOWED_CELLS[0];
  if (ALLOWED_CELLS.indexOf(cell) < 0) return _json({ ok: false, error: 'cell not allowed: ' + cell });

  var text = body.text;
  if (typeof text !== 'string' || !text.length) {
    return _json({ ok: false, error: 'empty text — 빈 값으로 덮어쓰지 않습니다' });
  }

  var sh = _sheet();
  var before = sh.getRange(cell).getDisplayValue();
  sh.getRange(cell).setValue(text);
  SpreadsheetApp.flush();
  var after = sh.getRange(cell).getDisplayValue();

  return _json({
    ok: true,
    cell: cell,
    before_length: before.length,
    after_length: after.length,
    wrote_at: Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss')
  });
}
