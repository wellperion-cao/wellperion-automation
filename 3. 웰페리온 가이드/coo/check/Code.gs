/**
 * 웰페리온 업장 순회 점검 — 구글 시트 자동 기록
 * 모바일 입력폼(업장순회점검.html)이 보낸 점검 결과를 받아
 * 현재 스프레드시트의 "점검기록" 시트에 하루 한 줄씩 기록합니다.
 *
 * 같은 날짜 + 같은 점검자의 기록이 이미 있으면 그 줄을 덮어씁니다(수정 재전송).
 *
 * 설치: 설치안내.md 참고
 */

// 업장 순서 (입력폼과 동일하게 유지)
var SECTION_ORDER = [
  ["hallway", "복도"],
  ["pilates", "필라테스"],
  ["gym", "헬스장"],
  ["golf", "골프장"],
  ["pool", "수영장"],
  ["gymnastics", "체조장"],
  ["squash", "스쿼시장"]
];

var SHEET_NAME = "점검기록";
// 기록 대상 스프레드시트 ID (강습부 업장관리 체크)
var SPREADSHEET_ID = "19fyGlLvYjO_PWZGGxPa6S33PJ0dn5nwvBrdqYNPK7oI";

function getSheet_() {
  var ss = SPREADSHEET_ID ? SpreadsheetApp.openById(SPREADSHEET_ID) : SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
  }
  // 헤더가 없으면 생성
  if (sh.getLastRow() === 0) {
    var header = ["날짜", "점검자"];
    SECTION_ORDER.forEach(function (s) {
      header.push(s[1] + " 상태");
      header.push(s[1] + " 이슈");
    });
    header.push("기록시각");
    sh.appendRow(header);
    sh.getRange(1, 1, 1, header.length).setFontWeight("bold").setBackground("#f0ece2");
    sh.setFrozenRows(1);
    sh.getRange("A:A").setNumberFormat("yyyy. m. d");          // 날짜: 실제 날짜값 + 표시형식
    var lastCol = header.length;                              // 기록시각: 날짜 + 시:분
    sh.getRange(1, lastCol, sh.getMaxRows()).setNumberFormat("yyyy. m. d  a/p h:mm");
  }
  return sh;
}

function buildRow_(data) {
  var dateVal = parseDate_(data.date);            // 실제 Date (정렬용)
  var row = [dateVal, data.inspector || ""];
  SECTION_ORDER.forEach(function (s) {
    var sec = (data.sections && data.sections[s[0]]) || {};
    row.push(sec.status || "");
    row.push(sec.issue || "");
  });
  row.push(new Date());                            // 기록시각
  return row;
}

function parseDate_(str) {
  if (!str) return new Date();
  var m = String(str).match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
  return new Date(str);
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var data = JSON.parse(e.postData.contents);
    var sh = getSheet_();
    var newRow = buildRow_(data);

    // 같은 날짜 + 점검자 행 찾기 → 있으면 덮어쓰기
    var keyDate = Utilities.formatDate(parseDate_(data.date), Session.getScriptTimeZone(), "yyyy-MM-dd");
    var lastRow = sh.getLastRow();
    var targetRow = 0;
    if (lastRow >= 2) {
      var values = sh.getRange(2, 1, lastRow - 1, 2).getValues();  // 날짜, 점검자
      for (var i = 0; i < values.length; i++) {
        var d = values[i][0];
        var dStr = (d instanceof Date)
          ? Utilities.formatDate(d, Session.getScriptTimeZone(), "yyyy-MM-dd")
          : String(d);
        if (dStr === keyDate && String(values[i][1]) === String(data.inspector || "")) {
          targetRow = i + 2;
          break;
        }
      }
    }

    if (targetRow) {
      sh.getRange(targetRow, 1, 1, newRow.length).setValues([newRow]);
    } else {
      sh.appendRow(newRow);
    }

    return json_({ ok: true, mode: targetRow ? "updated" : "appended" });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

// 브라우저로 URL 직접 열었을 때 동작 확인용
function doGet() {
  return json_({ ok: true, msg: "웰페리온 업장 점검 기록 엔드포인트 정상 동작 중" });
}

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
