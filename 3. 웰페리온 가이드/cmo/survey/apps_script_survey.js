// 웰페리온 랜딩 페이지 추적 Apps Script v1.0
// 리틀리(litt.ly) 대체 — 클릭·문의 추적 → 시트 누적
// 시트 2개: 클릭로그 | 문의접수

// ─── 상수 ───
const LANDING_SPREADSHEET_ID = '1g9Ohmd8C_WxyvWt9EX58oEFZLiOAJ_EG7t7XteJFuGE';
const CLICK_SHEET = '클릭로그';
const INQUIRY_SHEET = '문의접수';

// 회원부 시트 (유효회원 탭)
const MEMBER_SPREADSHEET_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';
const MEMBER_SHEET = '유효회원';
const MEMBER_PHONE_COL = '휴대폰 번호';   // 회원부 전화번호 헤더
const MEMBER_DATE_COL  = '등록 일자';      // 회원부 등록일 헤더

const CLICK_HEADERS = ['id', '시각', '링크명', '링크URL', 'UTM소스', 'UTM미디엄', '리퍼러', '디바이스'];
const INQUIRY_HEADERS = ['id', '시각', '이름', '연락처', '문의유형', '내용', '유입채널', 'UTM소스', 'UTM미디엄', '상태', '메모'];

const INQUIRY_TYPES = ['투어 예약', '프로그램 문의', '멤버십 상담', '시설 안내', '기타'];

// ─── 시트 초기화 ───
function _getSheet(name, headers) {
  const ss = SpreadsheetApp.openById(LANDING_SPREADSHEET_ID);
  let sh = ss.getSheetByName(name);
  if (sh) return sh;

  sh = ss.insertSheet(name);
  sh.getRange(1, 1, 1, headers.length).setValues([headers]);
  sh.getRange(1, 1, 1, headers.length)
    .setFontWeight('bold')
    .setBackground('#2a2725')
    .setFontColor('#B79F8A');
  sh.setFrozenRows(1);
  return sh;
}

function initSheets() {
  _getSheet(CLICK_SHEET, CLICK_HEADERS);
  _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
  return 'OK';
}

// ─── 유틸 ───
function _now() { return Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss'); }
function _genId(prefix) {
  return prefix + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMddHHmmss')
    + ('000' + new Date().getMilliseconds()).slice(-3);
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function _prop(key) {
  return PropertiesService.getScriptProperties().getProperty(key) || '';
}

// 전화번호 정규화 — 숫자만 추출, 국가코드 82→0 치환, 빈값→''
function normalizePhone_(s) {
  if (!s) return '';
  var digits = String(s).replace(/\D/g, '');
  if (digits.length >= 11 && digits.slice(0, 2) === '82') {
    digits = '0' + digits.slice(2);
  }
  return digits;
}

function _notifyTelegram(text) {
  const token = _prop('BOT_TOKEN') || _prop('TELEGRAM_BOT_TOKEN');
  const chatId = _prop('CHAT_ID') || _prop('TELEGRAM_CHAT_ID');
  if (!token || !chatId) return;
  try {
    UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
      method: 'post', contentType: 'application/json',
      payload: JSON.stringify({ chat_id: chatId, text: text, parse_mode: 'HTML' }),
      muteHttpExceptions: true
    });
  } catch (e) { Logger.log('텔레그램 실패: ' + e.message); }
}

// ═══════════════════════════════════════════
//  액션 처리
// ═══════════════════════════════════════════
function _processAction(body) {
  const action = body.action || '';

  // ─── 클릭 추적 ───
  if (action === 'track_click') {
    const sh = _getSheet(CLICK_SHEET, CLICK_HEADERS);
    const row = [
      _genId('CLK-'),
      _now(),
      body.linkName || '',
      body.linkUrl || '',
      body.utmSource || '',
      body.utmMedium || '',
      body.referrer || '',
      body.device || ''
    ];
    sh.getRange(sh.getLastRow() + 1, 1, 1, row.length).setValues([row]);
    return _json({ ok: true });
  }

  // ─── 문의 접수 ───
  if (action === 'submit_inquiry') {
    const sh = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    const id = _genId('INQ-');
    const row = [
      id,
      _now(),
      body.name || '',
      body.phone || '',
      body.type || '기타',
      body.message || '',
      body.inflow || '',
      body.utmSource || '',
      body.utmMedium || '',
      '신규',
      ''
    ];
    sh.getRange(sh.getLastRow() + 1, 1, 1, row.length).setValues([row]);

    _notifyTelegram(
      '🔔 <b>[신규 문의]</b>\n'
      + '이름: ' + (body.name || '-') + '\n'
      + '연락처: ' + (body.phone || '-') + '\n'
      + '유형: ' + (body.type || '-') + '\n'
      + '유입채널: ' + (body.inflow || '-') + '\n'
      + '내용: ' + (body.message || '-').substring(0, 100)
    );

    return _json({ ok: true, id: id, message: '문의가 접수되었습니다.' });
  }

  // ─── 클릭 통계 ───
  if (action === 'click_stats') {
    const sh = _getSheet(CLICK_SHEET, CLICK_HEADERS);
    const last = sh.getLastRow();
    if (last < 2) return _json({ ok: true, total: 0, byLink: {} });

    const data = sh.getRange(2, 1, last - 1, CLICK_HEADERS.length).getValues();
    const byLink = {};
    data.forEach(row => {
      const name = row[2] || '기타';
      byLink[name] = (byLink[name] || 0) + 1;
    });
    return _json({ ok: true, total: data.length, byLink: byLink });
  }

  // ─── 문의 목록 ───
  if (action === 'inquiry_list') {
    const sh = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    const last = sh.getLastRow();
    if (last < 2) return _json({ ok: true, count: 0, data: [] });

    const data = sh.getRange(2, 1, last - 1, INQUIRY_HEADERS.length).getValues();
    const items = data.map(row => {
      const obj = {};
      INQUIRY_HEADERS.forEach((h, i) => { obj[h] = row[i]; });
      return obj;
    });
    return _json({ ok: true, count: items.length, data: items });
  }

  // ─── 문의→가입 전환 집계 ───
  if (action === 'funnel_conversion') {
    // ① 회원부 전화번호 Set 생성
    var memberSs  = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    var memberSh  = memberSs.getSheetByName(MEMBER_SHEET);
    var memberLast = memberSh.getLastRow();
    var memberSet = {};
    if (memberLast >= 2) {
      var memberHeaders = memberSh.getRange(1, 1, 1, memberSh.getLastColumn()).getValues()[0];
      var phoneColIdx   = memberHeaders.indexOf(MEMBER_PHONE_COL);
      if (phoneColIdx >= 0) {
        var memberPhones = memberSh.getRange(2, phoneColIdx + 1, memberLast - 1, 1).getValues();
        memberPhones.forEach(function(r) {
          var n = normalizePhone_(r[0]);
          if (n) memberSet[n] = true;
        });
      }
    }

    // ② 문의접수 시트 집계
    var inqSh   = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    var inqLast = inqSh.getLastRow();
    var totalInq = 0, totalConv = 0;
    var byChannel = {};  // { 채널명: {inquiries, converted} }

    if (inqLast >= 2) {
      var inqData = inqSh.getRange(2, 1, inqLast - 1, INQUIRY_HEADERS.length).getValues();
      // 헤더 인덱스
      var idxPhone   = INQUIRY_HEADERS.indexOf('연락처');   // 3
      var idxChannel = INQUIRY_HEADERS.indexOf('유입채널'); // 6

      inqData.forEach(function(row) {
        var phone   = normalizePhone_(row[idxPhone]);
        var channel = String(row[idxChannel] || '기타').trim() || '기타';

        totalInq++;
        if (!byChannel[channel]) byChannel[channel] = { inquiries: 0, converted: 0 };
        byChannel[channel].inquiries++;

        if (phone && memberSet[phone]) {
          totalConv++;
          byChannel[channel].converted++;
        }
      });
    }

    // ③ 반환 JSON — 집계 수치만, 개인정보 절대 미포함
    var rate = totalInq > 0 ? Math.round((totalConv / totalInq) * 1000) / 10 : 0;
    var channelArr = Object.keys(byChannel).map(function(ch) {
      var d = byChannel[ch];
      return {
        channel:   ch,
        inquiries: d.inquiries,
        converted: d.converted,
        rate:      d.inquiries > 0 ? Math.round((d.converted / d.inquiries) * 1000) / 10 : 0
      };
    });
    channelArr.sort(function(a, b) { return b.inquiries - a.inquiries; });

    return _json({
      ok: true,
      total: { inquiries: totalInq, converted: totalConv, rate: rate },
      byChannel: channelArr,
      generatedAt: _now()
    });
  }

  return _json({ ok: false, error: '알 수 없는 action: ' + action });
}

// ═══════════════════════════════════════════
//  doGet / doPost
// ═══════════════════════════════════════════
function doGet(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) || '';
    if (action) {
      const body = {};
      Object.keys(e.parameter).forEach(k => body[k] = e.parameter[k]);
      return _processAction(body);
    }
    return _json({ ok: false, error: 'action 필수' });
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    return _processAction(body);
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}
