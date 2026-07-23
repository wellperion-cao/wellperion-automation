/** 웰페리온 | 강습 문의 알림 (성명 + 문의경로 + 문의내용 + 시트 링크) **/
function onFormSubmit(e) {
  if (!e) return;

  var ADMIN = "cao@wellperion.com";
  var SHEET_LINK = "https://docs.google.com/spreadsheets/d/1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw/edit?gid=111889422";

  // 항상 참조 보낼 이메일(원하면 여러 개)
  var CC_ALWAYS = [ADMIN];          // 필요 시 ["admin@...", "ops@..."] 식으로 확장

  function normKey(s) {
    return String(s||"").toLowerCase()
      .replace(/\s+/g,"")
      .replace(/[()\[\]{}]/g,"")
      .replace(/[.:/_-]/g,"");
  }

  // ── 1순위: 제출된 시트 행을 '실제 시트 헤더' 기준으로 직접 읽는다.
  //    (폼 질문 제목 변경·유소년 폼 잔재 키워드 등으로 namedValues 매칭이 어긋나
  //     이름·경로·내용이 '미기재'로 빠지던 버그 근본 차단. 2026-06-23)
  var name = "", route = "", content = "", sportRaw = "";
  try {
    if (e.range && e.range.getSheet) {
      var sh = e.range.getSheet();
      var lastCol = sh.getLastColumn();
      var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0];
      var vals    = sh.getRange(e.range.getRow(), 1, 1, lastCol).getValues()[0];
      var hNorm = headers.map(normKey);
      function bySheet(mustContain) {
        var wanted = mustContain.map(normKey);
        for (var i = 0; i < hNorm.length; i++) {
          var ok = wanted.every(function(f){ return hNorm[i].indexOf(f) !== -1; });
          if (ok) {
            var v = String(vals[i] == null ? "" : vals[i]).trim();
            if (v) return v;
          }
        }
        return "";
      }
      name     = bySheet(["성함"]) || bySheet(["이름"]);
      route    = bySheet(["문의","경로"]) || bySheet(["유입","경로"]);
      content  = bySheet(["문의","사항"]) || bySheet(["자유롭게"]);
      sportRaw = bySheet(["성인","강습","종목"]) || bySheet(["종목"]);
    }
  } catch (err) { /* 시트 읽기 실패 시 아래 namedValues 폴백 */ }

  // ── 2순위(폴백): e.namedValues 키워드 매칭 (시트 행을 못 읽었을 때만)
  var nv = e.namedValues || {};
  function getByKeywords(mustContain) {
    var wanted = mustContain.map(normKey);
    for (var k in nv) {
      var nk = normKey(k);
      var ok = wanted.every(function(f){ return nk.indexOf(f) !== -1; });
      if (ok && nv[k] && nv[k][0] !== undefined) return String(nv[k][0]).trim();
    }
    return "";
  }
  if (!name)     name     = getByKeywords(["성함"]) || getByKeywords(["이름"]);
  if (!route)    route    = getByKeywords(["문의","경로"]) || getByKeywords(["유입","경로"]);
  if (!content)  content  = getByKeywords(["문의","사항"]) || getByKeywords(["자유롭게","적어주세요"]);
  if (!sportRaw) sportRaw = getByKeywords(["성인","강습","종목"]) || getByKeywords(["종목"]);

  var sport = normalizeSport_(sportRaw);

  var emailMap = {
    "수영": "seo861027@gmail.com",
    "wsc수영": "seo861027@gmail.com",
    "wsc모자수영": "seo861027@gmail.com",
    "아쿠아": "seo861027@gmail.com",
    "pt": "psykss0420@gmail.com",
    "필라테스": "ej9582@gmail.com",
    "wsc필라테스": "ej9582@gmail.com",
    "골프": "jun88020800@gmail.com",
    "wsc골프": "jun88020800@gmail.com",
    "스쿼시": "h00nster15@gmail.com",
    "wsc스쿼시": "h00nster15@gmail.com",
    "체조": "a23718619@gmail.com",
    "wsc체조": "a23718619@gmail.com",
    "뮤지컬": "lizziepyun@gmail.com",
    "wsc뮤지컬": "lizziepyun@gmail.com"
  };
  var recipient = emailMap[sport] || ADMIN;

  // 메일·텔레그램 공통 본문 (동일 내용)
  var body = [
    "📌 신규 강습 문의가 접수되었습니다.",
    "문의자: " + (name   || "이름 미기재"),
    "문의경로: " + (route  || "경로 미기재"),
    "문의내용: " + (content|| "내용 미기재"),
    "",
    "📎 [접수 시트 바로가기] " + SHEET_LINK
  ].join("\n");

  // ① 담당 팀장 메일 (기존 유지)
  MailApp.sendEmail({
    to: recipient,
    subject: "[웰페리온] 신규 강습 문의 접수 알림",
    body: body
  });

  // ② 핵심멤버방 텔레그램에도 동일 내용 전달 (2026-06-23 GM)
  try {
    var TG_TOKEN = "8297784147:AAFxi1HGVYfqn4EuVtO3pgpaqbNdiVGiUh4";        // @namuki_report_bot (출처 telegram_bot/.env)
    var CORE_CHAT_ID = "-5065206276";      // 웰페리온 핵심멤버방 (group)
    UrlFetchApp.fetch("https://api.telegram.org/bot" + TG_TOKEN + "/sendMessage", {
      method: "post",
      payload: { chat_id: CORE_CHAT_ID, text: body },
      muteHttpExceptions: true
    });
  } catch (err) { /* 텔레그램 실패해도 메일은 이미 발송됨 */ }
}

function normalizeSport_(raw) {
  if (!raw) return "";
  var s = String(raw).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
  var isWSC = s.indexOf("wsc") === 0;
  var core  = isWSC ? s.replace(/^wsc/, "") : s;

  function has(str){ return core.indexOf(str) !== -1; }

  if (has("수영")) return isWSC ? "wsc수영" : "수영";
  if (has("모자수영")) return "wsc모자수영";
  if (has("아쿠아")) return "아쿠아";
  if (core.replace(/[^a-z]/g,"").indexOf("pt") !== -1) return "pt";
  if (has("필라테스")) return isWSC ? "wsc필라테스" : "필라테스";
  if (has("골프")) return isWSC ? "wsc골프" : "골프";
  if (has("스쿼시") || core.indexOf("squash") !== -1) return isWSC ? "wsc스쿼시" : "스쿼시";
  if (has("체조")) return isWSC ? "wsc체조" : "체조";
  if (has("뮤지컬")) return isWSC ? "wsc뮤지컬" : "뮤지컬";

  return s;
}
