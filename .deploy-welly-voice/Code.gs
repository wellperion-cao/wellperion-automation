/**
 * 웰리 음성 응답기 — 폰에서 말로 부르면 답하는 창구
 *
 * 무엇을 하나
 *   GM 님이 폰에서 "헤이 구글, 웰리야" 로 부르면, 폰이 말을 받아 적어 이 웹앱으로 보낸다.
 *   이 웹앱은 그 말을 웰리(AI CEO)로서 읽고 짧은 답을 글로 돌려준다. 폰이 그 답을 소리로
 *   읽어 준다. 그래서 손을 대지 않고 대화가 된다.
 *
 * 왜 여기(Apps Script)에 두나
 *   웰페리온 PC 는 밤 22:30 에 꺼지고 바깥에서 접속할 주소가 없다. 구글 계정 안에서 도는
 *   이 웹앱은 24시간 살아 있고, 주소가 이미 우리 것이라 새 서버를 사지 않아도 된다.
 *
 * 안전 장치 (일부러 좁게 만들었다)
 *   · TOKEN 이 맞지 않으면 아무것도 하지 않는다. 주소만 알아도 남이 쓰지 못한다.
 *   · 모델 열쇠(API 키)는 코드에 적지 않는다. 스크립트 속성에 넣어 두고 꺼내 쓴다.
 *   · 한 번 답의 길이를 짧게 묶어 둔다(MAX_TOKENS) — 말로 듣는 답이라 길면 못 듣는다.
 *   · 하루 호출 한도를 둔다(DAILY_LIMIT). 넘으면 답하지 않고 알린다. 요금이 새는 것을 막는다.
 *
 * 설치 방법
 *   1) script.google.com 에서 새 프로젝트를 만들고 이 코드를 전부 붙여넣는다.
 *   2) 왼쪽 톱니(프로젝트 설정) → 스크립트 속성 → 속성 추가
 *        이름  ANTHROPIC_API_KEY
 *        값    (웰페리온 모델 열쇠)
 *   3) 아래 TOKEN 을 원하는 암호로 바꾼다. 폰 설정에도 같은 값을 넣는다.
 *   4) 배포 → 새 배포 → 유형 '웹 앱'
 *        실행 계정 = 나
 *        액세스 권한 = 모든 사용자
 *   5) 나온 주소(/exec 로 끝남)를 폰 앱에 넣는다.
 *
 * 고칠 때
 *   코드를 고친 뒤에는 반드시 '배포 → 배포 관리 → 편집(연필) → 버전: 새 버전 → 배포' 를
 *   눌러야 실제로 바뀐다. 저장만 하면 옛 버전이 계속 돈다.
 */

var TOKEN = 'welly-voice-2026';   // ★ 바꿔 주세요. 폰 설정에도 같은 값을 넣습니다.
var MODEL = 'claude-sonnet-5';    // 대화는 소넷. 판단·결재는 PC 쪽 웰리가 한다.
var MAX_TOKENS = 400;             // 말로 듣는 답이라 짧게 묶는다.
var HISTORY_TURNS = 6;            // 앞뒤 대화 기억 개수(말이 이어지게).
var HISTORY_TTL_SEC = 1800;       // 30분 지나면 대화가 새로 시작된다.
var DAILY_LIMIT = 200;            // 하루 호출 상한(요금 안전장치).

var PERSONA = [
  '너는 웰페리온(주식회사 웰페리온)의 AI CEO 웰리다. 김남욱 GM 님과 말로 대화하는 중이다.',
  '',
  '말투',
  '- 한국어로만 답한다. 답은 소리로 읽히므로 표·기호·이모지·줄바꿈 장식을 쓰지 않는다.',
  '- 세 문장 안쪽으로 답한다. 결론을 먼저 말한다.',
  '- 영어·약어·내부 번호(배 번호·작업 아이디)를 말하지 않는다. 사람 말로 푼다.',
  '- GM 님을 "GM님"이라고 부른다. "대표님"이라고 부르지 않는다.',
  '',
  '지킬 것',
  '- 모르는 것은 모른다고 말한다. 숫자를 지어내지 않는다. 확인이 필요하면 "PC 쪽에서 확인해서 알려드리겠습니다"라고 말한다.',
  '- 회사 밖으로 나가는 말(카톡 발송·공지·결제·보안·공식값)은 여기서 결정하지 않는다. "돌아가서 처리하겠습니다"로 받아 둔다.',
  '- 지시를 받으면 되묻지 말고 받아 적었다고 말한다.',
  '',
  '회사 기본',
  '- 하이엔드 프라이빗 스포츠클럽 멤버십 커뮤니티. 서울 용산구 한남동.',
  '- "피트니스"라고 하지 않고 "스포츠클럽"이라고 한다.',
  '- 투어·상담은 사전 예약제다. 예약 없이 오시는 것은 안 된다.'
].join('\n');


function doGet(e) { return handle_(e); }
function doPost(e) { return handle_(e); }


function handle_(e) {
  try {
    var p = (e && e.parameter) || {};
    if (String(p.t || '') !== TOKEN) return text_('죄송합니다. 확인되지 않은 요청입니다.');

    var q = String(p.q || '').trim();
    if (!q) return text_('네, 말씀하세요.');

    if (q === '초기화' || q === '새로 시작') {
      CacheService.getScriptCache().remove('welly_hist');
      return text_('대화를 새로 시작하겠습니다.');
    }

    if (!underDailyLimit_()) {
      return text_('오늘 통화 한도를 다 썼습니다. 내일 다시 불러 주세요.');
    }

    var key = PropertiesService.getScriptProperties().getProperty('ANTHROPIC_API_KEY');
    if (!key) return text_('모델 열쇠가 아직 설정되지 않았습니다.');

    var history = loadHistory_();
    var messages = history.concat([{ role: 'user', content: q }]);
    var answer = askClaude_(key, messages);
    saveHistory_(messages.concat([{ role: 'assistant', content: answer }]));
    return text_(answer);
  } catch (err) {
    return text_('죄송합니다. 지금 답을 만들지 못했습니다. ' + String(err).slice(0, 80));
  }
}


function askClaude_(key, messages) {
  var res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    headers: { 'x-api-key': key, 'anthropic-version': '2023-06-01' },
    payload: JSON.stringify({
      model: MODEL,
      max_tokens: MAX_TOKENS,
      system: PERSONA + '\n\n오늘은 ' + today_() + ' 입니다.',
      messages: messages
    })
  });
  var code = res.getResponseCode();
  var body = JSON.parse(res.getContentText() || '{}');
  if (code !== 200) {
    var msg = (body.error && body.error.message) || ('오류 코드 ' + code);
    throw new Error(msg);
  }
  var parts = body.content || [];
  var out = [];
  for (var i = 0; i < parts.length; i++) {
    if (parts[i] && parts[i].type === 'text') out.push(parts[i].text);
  }
  return (out.join(' ').trim()) || '답을 만들지 못했습니다.';
}


/** 앞뒤 대화를 짧게 기억한다 — 30분 지나면 저절로 지워진다. */
function loadHistory_() {
  var raw = CacheService.getScriptCache().get('welly_hist');
  if (!raw) return [];
  try { return JSON.parse(raw); } catch (err) { return []; }
}

function saveHistory_(messages) {
  var keep = messages.slice(-HISTORY_TURNS * 2);
  CacheService.getScriptCache().put('welly_hist', JSON.stringify(keep), HISTORY_TTL_SEC);
}


/** 하루 호출 상한 — 날짜가 바뀌면 저절로 0부터 다시 센다. */
function underDailyLimit_() {
  var props = PropertiesService.getScriptProperties();
  var day = today_();
  var used = 0;
  if (props.getProperty('count_day') === day) {
    used = Number(props.getProperty('count_n') || 0);
  }
  if (used >= DAILY_LIMIT) return false;
  props.setProperties({ count_day: day, count_n: String(used + 1) });
  return true;
}


function today_() {
  return Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
}

function text_(s) {
  return ContentService.createTextOutput(s).setMimeType(ContentService.MimeType.TEXT);
}


/**
 * 설치 뒤 한 번 눌러 확인하는 자체 점검 — 열쇠·토큰·모델 호출이 실제로 되는지 본다.
 * 실행 로그에 결과가 찍힌다. 네트워크 밖 다른 것은 건드리지 않는다.
 */
function selfCheck() {
  var key = PropertiesService.getScriptProperties().getProperty('ANTHROPIC_API_KEY');
  if (!key) { Logger.log('실패 — 스크립트 속성에 ANTHROPIC_API_KEY 가 없습니다.'); return; }
  var answer = askClaude_(key, [{ role: 'user', content: '한 문장으로 인사해 줘.' }]);
  Logger.log('성공 — 웰리 답: ' + answer);
}
