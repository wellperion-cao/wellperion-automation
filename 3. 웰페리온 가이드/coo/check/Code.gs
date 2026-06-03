/**
 * 웰페리온 업장점검 — 구글 시트 자동 기록 (업장별 항목, 3단계)
 * 모바일 입력폼(강습부 업장관리.html)이 보낸 점검 결과를 받아
 * "점검기록" 시트에 하루 한 줄씩 기록합니다.
 *
 * 각 항목(업장 × 점검항목)을 별도 컬럼에 점검필요 / 양호 / 우수 값으로 기록합니다.
 * - 복도: 정리정돈 · 홍보물 · 청결 · 조명 및 냉난방   (복장착용 제외)
 * - 그 외 업장: 정리정돈 · 청결 · 조명 및 냉난방 · 복장착용 (홍보물 제외)
 *
 * 같은 날짜 + 같은 점검자의 기록이 이미 있으면 그 줄을 덮어씁니다(수정 재전송).
 *
 * ※ 항목 구조를 바꾼 뒤에는 편집기에서 setup() 함수를 1회 실행해
 *    "점검기록" 시트의 헤더를 새로 맞춰주세요.
 */

// 업장 + 항목 정의 (입력폼과 동일하게 유지)
var ITEMS_HALL  = ["정리정돈", "홍보물", "청결", "조명 및 냉난방"];   // 복도
var ITEMS_VENUE = ["정리정돈", "청결", "조명 및 냉난방", "복장착용"]; // 그 외 업장

var SECTIONS = [
  { id: "hallway",    name: "복도",     items: ITEMS_HALL },
  { id: "pilates",    name: "필라테스", items: ITEMS_VENUE },
  { id: "gym",        name: "헬스장",   items: ITEMS_VENUE },
  { id: "golf",       name: "골프장",   items: ITEMS_VENUE },
  { id: "pool",       name: "수영장",   items: ITEMS_VENUE },
  { id: "gymnastics", name: "체조장",   items: ITEMS_VENUE },
  { id: "squash",     name: "스쿼시장", items: ITEMS_VENUE }
];

var SHEET_NAME = "점검기록";
// 기록 대상 스프레드시트 ID (강습부 업장관리 체크)
var SPREADSHEET_ID = "19fyGlLvYjO_PWZGGxPa6S33PJ0dn5nwvBrdqYNPK7oI";

function ss_() {
  return SPREADSHEET_ID ? SpreadsheetApp.openById(SPREADSHEET_ID) : SpreadsheetApp.getActiveSpreadsheet();
}

// 헤더: 날짜 · 점검자 · (업장 · 항목)… · 업장 이슈 · … · 기록시각
function buildHeader_() {
  var header = ["날짜", "점검자"];
  SECTIONS.forEach(function (s) {
    s.items.forEach(function (it) { header.push(s.name + " · " + it); });
    header.push(s.name + " 이슈");
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
  sh.getRange("A:A").setNumberFormat("yyyy. m. d");                                       // 날짜
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
  SECTIONS.forEach(function (s) {
    var sec = (data.sections && data.sections[s.id]) || {};
    var items = sec.items || {};
    s.items.forEach(function (it) { row.push(items[it] || ""); });   // 항목별 3단계 값
    row.push(sec.issue || "");                                       // 업장 이슈
  });
  row.push(new Date());                                              // 기록시각
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

    try { buildDashboard(); } catch (e2) {}   // 제출할 때마다 대시보드 자동 갱신 (실패해도 기록은 유지)

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

/* ===================== 대시보드 ===================== */
var DASH_NAME = "대시보드";
var ITEMS_UNION = ["정리정돈", "홍보물", "청결", "조명 및 냉난방", "복장착용"]; // 전체 항목(합집합)

// 점검기록을 집계해 "대시보드" 시트를 다시 그린다.
// 월별·업장별·항목별 「점검필요」 횟수 + 이슈사항 목록.
function buildDashboard() {
  var ss = ss_();
  var src = ss.getSheetByName(SHEET_NAME);
  var dash = ss.getSheetByName(DASH_NAME) || ss.insertSheet(DASH_NAME);
  var tz = Session.getScriptTimeZone();

  // ---- 집계 ----
  var counts = {};      // month -> venue -> item -> 점검필요 수
  var monthsSet = {};
  var issues = [];      // [월, 날짜, 업장, 점검자, 이슈내용]
  if (src && src.getLastRow() >= 2) {
    var data = src.getRange(2, 1, src.getLastRow() - 1, src.getLastColumn()).getValues();
    data.forEach(function (r) {
      if (!r[0]) return;
      var d = (r[0] instanceof Date) ? r[0] : parseDate_(r[0]);
      var month = Utilities.formatDate(d, tz, "yyyy-MM");
      var dateStr = Utilities.formatDate(d, tz, "yyyy. M. d");
      monthsSet[month] = true;
      var inspector = r[1];
      var c = 2;
      SECTIONS.forEach(function (s) {
        s.items.forEach(function (it) {
          var v = String(r[c]).trim(); c++;
          if (v === "점검필요") {
            counts[month] = counts[month] || {};
            counts[month][s.name] = counts[month][s.name] || {};
            counts[month][s.name][it] = (counts[month][s.name][it] || 0) + 1;
          }
        });
        var issue = String(r[c]).trim(); c++;
        if (issue) issues.push([month, dateStr, s.name, inspector, issue]);
      });
    });
  }
  var months = Object.keys(monthsSet).sort();          // 오름차순
  issues.sort(function (a, b) { return a[0] < b[0] ? 1 : (a[0] > b[0] ? -1 : 0); });

  // ---- 시트 내용 구성 ----
  var COLS = 7;
  var out = [];
  function push(row) { while (row.length < COLS) row.push(""); out.push(row.slice(0, COLS)); return out.length; }
  var fmtTitle = [], fmtSection = [], fmtMonth = [], fmtTblHeader = [], totalCols = [];
  var countAreaStart = 0, countAreaEnd = 0;

  push(["📊 강습부 업장점검 대시보드"]); var titleRow = out.length;
  push(["최종 업데이트: " + Utilities.formatDate(new Date(), tz, "yyyy. M. d a/p h:mm")]); var timeRow = out.length;
  push([""]);

  fmtSection.push(push(["■ 월별 · 업장별 · 항목별 「점검필요」 횟수"]));
  var colHeader = ["업장"].concat(ITEMS_UNION).concat(["합계"]);
  if (months.length === 0) {
    push(["(아직 점검 기록이 없습니다)"]);
  } else {
    months.forEach(function (m) {
      fmtMonth.push(push(["📅 " + m]));
      fmtTblHeader.push(push(colHeader.slice()));
      if (!countAreaStart) countAreaStart = out.length + 1;
      SECTIONS.forEach(function (s) {
        var row = [s.name]; var sum = 0;
        ITEMS_UNION.forEach(function (it) {
          if (s.items.indexOf(it) < 0) { row.push(""); }
          else { var cnt = (counts[m] && counts[m][s.name] && counts[m][s.name][it]) || 0; row.push(cnt); sum += cnt; }
        });
        row.push(sum);
        push(row);
      });
      countAreaEnd = out.length;
      totalCols.push(out.length); // 마지막 합계행 위치(불필요시 무시)
      push([""]);
    });
  }

  push([""]);
  fmtSection.push(push(["■ 이슈사항 (최근순)"]));
  fmtTblHeader.push(push(["월", "날짜", "업장", "점검자", "이슈내용"]));
  var issueStart = out.length + 1;
  if (issues.length === 0) {
    push(["(등록된 이슈가 없습니다)"]);
  } else {
    issues.forEach(function (it) { push(it.slice()); });
  }
  var issueEnd = out.length;

  // ---- 쓰기 (시트를 매번 새로 만들어 병합·서식 충돌을 원천 차단) ----
  var existing = ss.getSheetByName(DASH_NAME);
  if (existing) ss.deleteSheet(existing);
  dash = ss.insertSheet(DASH_NAME);
  dash.getRange(1, 1, out.length, COLS).setValues(out);

  // ---- 서식 ----
  dash.getRange(titleRow, 1, 1, COLS).merge()
    .setFontSize(15).setFontWeight("bold").setBackground("#22324a").setFontColor("#ffffff").setVerticalAlignment("middle");
  dash.setRowHeight(titleRow, 34);
  dash.getRange(timeRow, 1, 1, COLS).merge().setFontColor("#6c6961").setFontStyle("italic");

  fmtSection.forEach(function (rw) {
    dash.getRange(rw, 1, 1, COLS).merge().setFontWeight("bold").setBackground("#efece4").setFontColor("#3c3a35");
  });
  fmtMonth.forEach(function (rw) {
    dash.getRange(rw, 1, 1, COLS).merge().setFontWeight("bold").setBackground("#e8eef5").setFontColor("#22324a");
  });
  fmtTblHeader.forEach(function (rw) {
    dash.getRange(rw, 1, 1, COLS).setFontWeight("bold").setBackground("#faf9f6")
      .setBorder(null, null, true, null, false, false, "#d8d4ca", SpreadsheetApp.BorderStyle.SOLID);
  });

  // 숫자 영역 가운데 정렬 + 점검필요>0 빨강 강조
  if (countAreaStart && countAreaEnd >= countAreaStart) {
    dash.getRange(countAreaStart, 2, countAreaEnd - countAreaStart + 1, COLS - 1).setHorizontalAlignment("center");
    var cRng = dash.getRange(countAreaStart, 2, countAreaEnd - countAreaStart + 1, COLS - 1);
    var rule = SpreadsheetApp.newConditionalFormatRule()
      .whenNumberGreaterThan(0).setBackground("#f6e6e4").setFontColor("#b14238").setBold(true)
      .setRanges([cRng]).build();
    dash.setConditionalFormatRules([rule]);
  }

  // 이슈내용 줄바꿈
  if (issues.length > 0) {
    dash.getRange(issueStart, 5, issueEnd - issueStart + 1, 1).setWrap(true);
  }

  // 열 너비 / 고정
  dash.setColumnWidth(1, 150);
  dash.setColumnWidth(2, 100);
  dash.setColumnWidth(3, 95);
  dash.setColumnWidth(4, 110);
  dash.setColumnWidth(5, 300);
  dash.setColumnWidth(6, 95);
  dash.setColumnWidth(7, 70);
  dash.setFrozenRows(2);

  // 대시보드 탭을 맨 앞으로
  try { ss.setActiveSheet(dash); ss.moveActiveSheet(1); } catch (e) {}

  return "대시보드 갱신 완료 (월 " + months.length + " · 이슈 " + issues.length + ")";
}
