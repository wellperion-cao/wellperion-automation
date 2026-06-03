/**
 * 웰페리온 업장점검 — 구글 시트 자동 기록 (항목별 3단계)
 * 모바일 입력폼(강습부 업장관리.html)이 보낸 점검 결과를 받아
 * "점검기록" 시트에 하루 한 줄씩 기록합니다.
 *
 * 각 항목(업장 × 정리정돈/홍보물/청결/조명 및 냉난방)을 별도 컬럼에
 * 점검필요 / 양호 / 우수 3단계 값으로 기록합니다.
 *
 * 같은 날짜 + 같은 점검자의 기록이 이미 있으면 그 줄을 덮어씁니다(수정 재전송).
 *
 * ※ 항목 구조를 바꾼 뒤에는 편집기에서 setup() 함수를 1회 실행해
 *    "점검기록" 시트의 헤더를 새로 맞춰주세요.
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

// 각 업장 공통 점검 항목 (입력폼과 동일하게 유지)
var ITEMS = ["정리정돈", "홍보물", "청결", "조명 및 냉난방", "복장착용"];

var SHEET_NAME = "점검기록";
// 기록 대상 스프레드시트 ID (강습부 업장관리 체크)
var SPREADSHEET_ID = "19fyGlLvYjO_PWZGGxPa6S33PJ0dn5nwvBrdqYNPK7oI";

function ss_() {
  return SPREADSHEET_ID ? SpreadsheetApp.openById(SPREADSHEET_ID) : SpreadsheetApp.getActiveSpreadsheet();
}

// 헤더: 날짜 · 점검자 · (업장 · 항목)×n · 업장 이슈 · ... · 기록시각
function buildHeader_() {
  var header = ["날짜", "점검자"];
  SECTION_ORDER.forEach(function (s) {
    ITEMS.forEach(function (it) { header.push(s[1] + " · " + it); });
    header.push(s[1] + " 이슈");
  });
  header.push("기록시각");
  return header;
}

function writeHeader_(sh) {
  var header = buildHeader_();
  sh.clear();
  sh.appendRow(header);
  sh.getRange(1, 1, 1, header.length).setFontWeight("bold").setBackground("#f0ece2");
  sh.setFrozenRows(1);
  sh.getRange("A:A").setNumberFormat("yyyy. m. d");                                   // 날짜
  sh.getRange(1, header.length, sh.getMaxRows()).setNumberFormat("yyyy. m. d  a/p h:mm"); // 기록시각
  return header;
}

function getSheet_() {
  var ss = ss_();
  var sh = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  if (sh.getLastRow() === 0) writeHeader_(sh);
  return sh;
}

// 항목 구조 변경 후 1회 실행 — 헤더를 새 구조로 초기화 (기존 내용 삭제됨)
function setup() {
  var ss = ss_();
  var sh = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  var header = writeHeader_(sh);
  return "헤더 초기화 완료: " + header.length + "개 컬럼";
}

function buildRow_(data) {
  var row = [parseDate_(data.date), data.inspector || ""];   // 날짜(실제 Date) · 점검자
  SECTION_ORDER.forEach(function (s) {
    var sec = (data.sections && data.sections[s[0]]) || {};
    var items = sec.items || {};
    ITEMS.forEach(function (it) { row.push(items[it] || ""); });   // 항목별 3단계 값
    row.push(sec.issue || "");                                     // 업장 이슈
  });
  row.push(new Date());                                            // 기록시각
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
  return json_({ ok: true, msg: "웰페리온 업장점검 기록 엔드포인트 정상 동작 중" });
}

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
