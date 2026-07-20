// AUTO-GENERATED — 손 편집 금지.
// 정본 = scripts/sport_colors.py (SPORT_DOT). 값이 바뀌면 그 파일을 고치고
// `C:\Python314\python.exe scripts\gen_sport_colors_js.py` 로 이 파일을 다시 생성하세요.
// 매칭 알고리즘(키워드 부분포함·대소문자 무시·표 순서상 첫 매치)도 Python 쪽과 동일해야 합니다.
var SPORT_DOT_TABLE = [["아쿠아", "🔵"], ["수영", "🔵"], ["Swimming", "🔵"], ["P.T", "🔴"], ["PT", "🔴"], ["Personal Training", "🔴"], ["필라", "🟠"], ["Pilates", "🟠"], ["스쿼시", "🟩"], ["Squash", "🟩"], ["골프", "🟢"], ["Golf", "🟢"], ["트램폴린", "🟦"], ["체조", "🟦"], ["Gymnastics", "🟦"], ["멤버십", "🟡"], ["Membership", "🟡"], ["뮤지컬", "⚫"], ["Musical", "⚫"], ["발레", "🟣"], ["바레", "🟣"], ["루프", "🟣"], ["Ballet", "🟣"], ["Barre", "🟣"]];
function sportDot(name) {
  var k = String(name || '').trim().toLowerCase();
  if (!k) return '';
  for (var i = 0; i < SPORT_DOT_TABLE.length; i++) {
    var kw = SPORT_DOT_TABLE[i][0], dot = SPORT_DOT_TABLE[i][1];
    if (k.indexOf(kw.toLowerCase()) >= 0) return dot;
  }
  return '';
}
