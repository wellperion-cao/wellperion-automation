/* 구매 품의 승인 비밀번호 — 한 곳 (배2542 · GM 승인 2026-09-11 「우열M 요청대로 해줘」).
 *
 * 왜 여기 모았나: 같은 값이 매출지출현황.html·지출품의.html 두 곳에 박히면 한쪽만 고쳐져
 * 어긋난다. 두 화면이 이 파일 하나를 읽는다(약속 L01).
 *
 * ⚠️ 이 값은 화면 소스에 그대로 실린다 — 사람을 확인하는 장치가 아니라 오조작을 막는 잠금이다.
 *    "누가 승인했나" 는 시트의 「승인자」 칸, "언제" 는 GAS 가 검토 전환 때 찍는 「승인날짜」 칸이
 *    남긴다. 실무진 ERP 개인 계정이 깔리면 이 방식을 계정 권한으로 옮긴다(그때 이 파일은 지운다).
 */
var APPR_PW = { "김남욱": "1531" };   // 승인자 이름에 이 문자열이 포함되면 해당 비번
var APPR_PW_DEFAULT = "1202";
var APPR_PW_REVIEW = "1202!";          // 검토완료(정산)

/* next = 바꾸려는 상태. rows = 그 화면이 들고 있는 품의 목록(REQ_ACTIVE + REQ_DONE). */
function apprPwFor(next, row, rows) {
  if (next === "정산") return APPR_PW_REVIEW;
  if (next === "완료" || next === "반려") return APPR_PW_DEFAULT;
  var it = (rows || []).filter(function (x) { return String(x.row) === String(row); })[0];
  var who = String((it && it.승인자) || "");
  for (var k in APPR_PW) { if (who.indexOf(k) >= 0) return APPR_PW[k]; }
  return APPR_PW_DEFAULT;
}

/* 자가점검 — 브라우저에서는 안 돈다. 확인: node "3. 웰페리온 가이드/cfo/finance/_appr_pw.js" */
if (typeof module !== "undefined" && typeof require !== "undefined" && require.main === module) {
  var _rows = [{ row: 1, 승인자: "김남욱GM" }, { row: 2, 승인자: "이경연실장" }, { row: 3, 승인자: "" }];
  var _eq = function (a, b, m) { if (a !== b) { throw new Error(m + " : " + a + " != " + b); } };
  _eq(apprPwFor("검토", 1, _rows), "1531", "GM 건은 GM 비번");
  _eq(apprPwFor("검토", 2, _rows), "1202", "실장 건은 기본 비번");
  _eq(apprPwFor("검토", 3, _rows), "1202", "승인자 빈칸도 기본 비번");
  _eq(apprPwFor("반려", 1, _rows), "1202", "반려는 승인자와 무관하게 기본");
  _eq(apprPwFor("정산", 1, _rows), "1202!", "검토완료는 별도");
  _eq(apprPwFor("검토", 99, _rows), "1202", "없는 행이면 기본");
  console.log("[selfcheck] 승인 비밀번호 판정 OK (6케이스)");
}
