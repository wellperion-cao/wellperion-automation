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
var ALLOWED_CELLS = ['P20'];             // 여기 없는 칸에는 절대 쓰지 않는다

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
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
