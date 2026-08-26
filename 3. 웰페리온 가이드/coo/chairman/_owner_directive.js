/*!
 * 대표님_지시사항.html · GM업무.html 공용 로직 (2026-08-05 GM 지시 — "판정·문안 생성 로직을 복제하지
 * 마라", "일관성이 핵심"). 월간운영계획.html 의 readWorkApproval()/renderOwnerTodoFold() 와 같은 판정
 * (담당자=김남욱 + 상태 진행중·보류 + 내용칸 "대표님 보고건" 포함여부)을 그대로 재사용한다 — 규칙이 바뀌면
 * 이 파일 + 월간운영계획.html 두 곳을 함께 고친다(약속 L01, GAS·저장키 신설 없음 — 약속 L21).
 * 사용법: 페이지가 <script>window.OWNER_DIR_CFG = {...}</script> 로 설정한 뒤 이 파일을 로드하고
 * document ready 시 OwnerDirective.mount() 를 호출한다(각 페이지 하단 스크립트에서).
 */
(function () {
  "use strict";

  // 월간운영계획.html 과 동일 GAS(약속 L21 — 새 GAS 미생성). 열쇠도 그 페이지 gm1TodoKey()와 동일값
  // (telegram_bot/.env GM_TODO_KEY와 동일 — 값을 두는 자리는 이 두 곳뿐).
  var GAS_URL = 'https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec';
  var GM_KEY = '1531';
  var CEO_MARK = '대표님 보고건';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function catName(raw) { return String(raw || '').trim().replace(/^\[\d+\]\s*/, ''); }
  function fmtSchedule(startRaw, endRaw) {
    function short(v) {
      var m = String(v || '').trim().match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
      return m ? (m[1].slice(2) + '.' + parseInt(m[2], 10) + '.' + parseInt(m[3], 10)) : '';
    }
    var s = short(startRaw), e = short(endRaw);
    if (s && e) return s === e ? s : (s + '~' + e);
    return s || e || '일정 미정';
  }
  function pad2(n) { return n < 10 ? '0' + n : '' + n; }
  function todayStr() {
    var d = new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }
  // 보고완료 날짜 표시 — 연도 없이 "M/D"(GM 지시 2026-08-11). 저장(todayStr)은 그대로 YYYY-MM-DD —
  // 여기서 화면 표시용으로만 짧게 자른다. 이 함수 하나만 고치면 회장님·대표님·결재문서 인쇄까지
  // 전부 같이 바뀐다(아래 chDate·reportedDate가 이 함수를 거쳐 나가므로 — 약속 L01, 표시 로직 복제 없음).
  function fmtNoYear(s) {
    var m = /^\d{4}-0?(\d{1,2})-0?(\d{1,2})/.exec(String(s || '').trim());
    return m ? (m[1] + '/' + m[2]) : '';
  }
  // 진척률(%) — 원천(회장님 when 문구·대표님 SSOT 상태값)에 % 칸이 없어, 이미 화면에 보이는 상태
  // 문구를 단계로 읽어 산출한다(GM 확정 2026-08-11 "약간의 색깔 및 %로" — 웰리 방침: 지어내지 않고
  // 단계표 하나로 근거를 남긴다). 여기 표 하나만 고치면 회장님·대표님 전부 같이 바뀐다.
  // 순서=우선순위. 겹친 단어는 더 구체적인 쪽이 이긴다 — "조사 착수"=30(50 아님), "보고 완료·결재 대기"=70
  // (100 아님, "완료"가 있어도 뒤에 결재대기가 붙으면 그쪽이 실제 단계) — GM 확정 표의 두 예시와 일치.
  var PCT_STAGES = [
    { pct: 70, re: /결재\s*대기|승인\s*대기/ },
    { pct: 100, re: /완료|보고완료/ },
    { pct: 30, re: /조사|검토|현장\s*확인|통화\s*완료/ },
    { pct: 50, re: /진행\s*중|착수/ },
    { pct: 10, re: /예정|다음\s*주/ }
  ];
  // ★2026-08-11 웰리 정정 — isDone(보고완료 배지)으로 100%를 단정하지 않는다. 보고완료="회장님/대표님께
  // 알렸다"이지 "일이 끝났다"가 아니다(다른 축). 오늘 그 배지 자체도 GAS 토큰 만료로 갱신이 막혀 있어
  // 죽은 값으로 진척을 정하면 거짓말이 된다. 진척은 오직 상태 문구로만 판단 — 배지는 배지대로 따로 보인다.
  function stagePct(text) {
    var s = String(text || '');
    for (var i = 0; i < PCT_STAGES.length; i++) { if (PCT_STAGES[i].re.test(s)) return PCT_STAGES[i].pct; }
    return null; // 어느 단계인지 못 가리면 비운다(지어내지 않음).
  }
  // GM 직접 카드(GM업무.html)가 이미 쓰는 .pct/.pbar 재사용 — 새 CSS 없음. 표 칸 안이라 폭만 인라인으로 줄인다.
  function pctBadge(pct) {
    if (pct === null) return '';
    return ' <span class="pct" style="font-size:11px;">' + pct + '%</span>' +
      '<div class="pbar" style="width:44px;height:4px;display:inline-block;vertical-align:middle;margin:0 0 0 5px;"><i style="width:' + pct + '%"></i></div>';
  }
  // 내용칸 꼬리표(분류용 "대표님 보고건(...)"·보고완료로 표시할 때 붙이는 "[…보고완료 날짜]") 를 화면·문안에서
  // 걷어낸 본문. 붙는 순서가 항상 "…원문 → 대표님 보고건(...) → [보고완료 …]"라 끝에서부터 역순으로 떼어낸다
  // (먼저 [보고완료] 를 떼야 그 아래 있던 대표님 보고건(...) 이 다시 맨 끝으로 나와 두 번째 규칙에 걸린다).
  function stripTags(content) {
    return String(content || '')
      .replace(/\n?\[[^\]]*보고완료[^\]]*\]\s*$/, '')
      .replace(/\n?대표님\s*보고건\([^)]*\)\s*$/, '')
      .trim();
  }
  function isReported(content, markPrefix) {
    return new RegExp('\\[' + markPrefix + ' \\d{4}-\\d{2}-\\d{2}\\]').test(String(content || ''));
  }
  // 완료 배지에 쓸 날짜 — 위 표식([마크 YYYY-MM-DD])에서 날짜만 뽑는다(회장님 쪽 chDate()와 형식 통일, GM 지적 2026-08-10).
  function reportedDate(content, markPrefix) {
    var m = new RegExp('\\[' + markPrefix + ' (\\d{4}-\\d{2}-\\d{2})\\]').exec(String(content || ''));
    return m ? fmtNoYear(m[1]) : '';
  }

  // 업무&결재 SSOT(action=todo_list) — 월간운영계획.html readWorkApproval() 과 동일 조회 + AI배 제외.
  function readWorkApproval() {
    return fetch(GAS_URL + '?action=todo_list&include_gm=1&gmkey=' + encodeURIComponent(GM_KEY), { method: 'GET', redirect: 'follow' })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res || !(res.ok || res.success) || !Array.isArray(res.data || res.todos)) return null;
        var aiOwnerRe = /웰리|시뽀|시로|시모|시우|시포|시토|ai\s*ceo|ai\s*cfo|ai\s*chro|ai\s*cmo|ai\s*coo|ai\s*cpo|ai\s*cto/i;
        return (res.data || res.todos).filter(function (r) {
          var cat = String(r['카테고리'] || '').trim();
          var owner = String(r['담당자'] || '').trim();
          return cat !== '[7]AI배(C레벨)' && !aiOwnerRe.test(owner);
        });
      })
      .catch(function () { return null; });
  }

  // 담당자=김남욱 + 상태(진행중·보류) + 대표님 보고건 표식 유무로 양분 — 월간운영계획.html renderOwnerTodoFold()와 동일 판정.
  // ▸대표님 칸이 0건인 것에 대해 2026-08-26 검수에서 "표식 행 2건([결재] 아르모니움·오넛티)이
  //   보고 여부 확인 없이 완료로 내려간 것 아니냐"는 의문이 나왔다. GM 확인 결과 두 건 모두
  //   실제로 보고를 마친 건이다("보고완료"). 즉 지금의 0건은 정상이고 필터도 그대로 둔다.
  //   같은 의문이 또 나오지 않게 여기에 적어 둔다.
  function filterRows(rows, wantCeoRows) {
    if (!rows) return null;
    return rows.filter(function (r) {
      var owner = String(r['담당자'] || '').trim();
      var status = String(r['상태'] || '').trim();
      if (owner.indexOf('김남욱') === -1 || (status !== '진행중' && status !== '보류')) return false;
      var isCeoRow = String(r['내용'] || '').indexOf(CEO_MARK) !== -1;
      return isCeoRow === wantCeoRows;
    }).sort(function (a, b) {
      var da = String(a['종료일'] || '').trim() || '9999-99-99';
      var db = String(b['종료일'] || '').trim() || '9999-99-99';
      return da < db ? -1 : da > db ? 1 : 0;
    });
  }

  // ── 발송 담당(2026-08-05 GM 지시 · 2026-08-06 시토 배403 — GAS 쪽 action=owner_report_send
  //    신설로 실발송 연결) — 클립보드 복사는 그대로 안전망으로 남긴다(텔레그램 실패해도 사람이
  //    직접 붙여넣을 수 있게). 봇 토큰은 여전히 브라우저에 안 넣는다 — 발송은 GAS 서버측
  //    (.deploy-todo/업무&결재 현황.js _sendOwnerReportTelegram, GM 확인 완료 패턴 재사용)이
  //    한다. ⚠️ GAS 쪽 코드는 준비만 됐고 재배포 전까지는 이 fetch 가 구버전 GAS에서 action
  //    미인식 응답을 받을 뿐 — 클립보드 흐름은 그 실패와 무관하게 그대로 동작한다.
  function dispatchReport(text, onDone) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { onDone(true); }).catch(function () { onDone(false); });
    } else { onDone(false); }
    fetch(GAS_URL + '?action=owner_report_send&text=' + encodeURIComponent(text), { method: 'GET', redirect: 'follow' })
      .catch(function () {}); // best-effort — 실패해도 위 클립보드 흐름을 막지 않는다.
  }

  // 👑 회장님 보고건 현황 — 2026-08-05 GM 지시("회장님 업무보고건을 대표님에게도 같이 회장님 보고건으로
  // 정리해서 한 번에 복사해 붙여넣게"). 목록 정본 = _chairman_items.js(배열 한 벌·복제 없음). 그 파일을 안 실은
  // 페이지에서는 빈 문자열이 되어 문안이 예전 그대로다(조용히 빠지지 않게 cfg.includeChairman 로만 켠다).
  // 👑 회장님 보고 완료 상태 — 같은 폴더 chairman_reported.json(id → 보고한 날짜) 한 곳만 읽고 쓴다.
  // GM 2026-08-06 "회장님건도 대표님건처럼 보고된 건이면 보고 완료로 문안 복사에서 제외".
  // 대표님건은 시트 '내용' 칸 표식으로, 회장님건은 시트에 없어 이 파일로 — 판정 규칙(있으면 완료)은 같다.
  var CH_STATE_PATH = '3. 웰페리온 가이드/coo/chairman/chairman_reported.json';
  // ★2026-08-12 GM 지시 "회장님 저장 일시중단? 해결하자" — 저장 경로를 갈아탔다.
  // 전에는 commit_file(GitHub API)로 저장소 파일을 직접 고쳤는데 그 출입 열쇠가 만료돼
  // 눌러도 401 로 실패했다(그래서 버튼을 막아 뒀다). 열쇠를 새로 받는 대신, 부서보드·브로제이가
  // 이미 쓰는 공용 키-값 저장소를 그대로 쓴다 — 새 저장소도, 새 열쇠도 만들지 않는다(약속 L21).
  var CH_BOARD_URL = 'https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec';
  var CH_BOARD_KEY = 'CHAIRMAN_REPORTED';
  var chReported = {};   // 조회 실패 시 {} — 전부 '보고 대기'로 보여 문안에서 빠지는 일이 없게 한다.
  // 배포(GitHub Pages) 반영이 늦으면 같은 파일을 저장소 raw 에서 한 번 더 찾는다 — 못 읽은 채로 그리면
  // 이미 보고한 건이 다시 '보고 대기'로 올라가 문안에 섞인다(GM 2026-08-06 가 막으라고 한 바로 그 상태).
  var RAW_STATE = 'https://raw.githubusercontent.com/wellperion-cao/wellperion-automation/master/' + encodeURI(CH_STATE_PATH);
  // ★2026-08-12 실측 — 표가 「불러오는 중…」에서 멈춰 있었다. 공용 저장소(Apps Script)가 느린 날
  // 응답이 수십 초 걸리는데, 그걸 기다렸다 그리게 해 두어 화면 전체가 붙들렸다. 그래서:
  //   ① 저장소에 시간 제한(8초)을 건다 — 늦으면 그냥 없는 셈 친다.
  //   ② 같은 폴더 파일로 **먼저 그리고**, 저장소 답이 오면 그때 덮어 다시 그린다.
  // 사람은 즉시 보고, 최신값은 오는 대로 반영된다. 어느 쪽도 못 읽으면 전부 '보고 대기'로 남는다.
  function _chGet(url, ms) {
    var u = url + (url.indexOf('?') === -1 ? '?' : '&') + 't=' + Date.now();
    var timed = new Promise(function (resolve) { setTimeout(function () { resolve(null); }, ms || 8000); });
    var req = fetch(u, { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
    return Promise.race([req, timed]);
  }
  function loadChairmanReported() {
    // 1차 = 파일(같은 폴더 → 저장소 raw). 빠르고 거의 항상 열린다.
    return _chGet('chairman_reported.json', 6000)
      .then(function (j) { return j || _chGet(RAW_STATE, 6000); })
      .then(function (j) { chReported = j || {}; });
  }
  // 2차 = 공용 저장소(정본). 늦게 와도 되고, 오면 화면을 다시 그린다.
  function refreshChairmanFromBoard(onDone) {
    // 25초 — 실측 8.6초(2026-08-19)인데 12초로 잡아 두어 콜드스타트 때마다 정본을 놓쳤다.
    // 놓치면 화면이 뒤처진 파일 값으로 남아 「보고 완료」가 되살아난다(GM 2026-08-19 실사고).
    return _chGet(CH_BOARD_URL + '?action=board&key=' + CH_BOARD_KEY, 25000)
      .then(function (j) {
        if (j && j.ok && j.board && Object.keys(j.board).length) {
          chReported = j.board;
          if (typeof onDone === 'function') onDone();
        }
      })
      .catch(function () { /* 못 읽으면 파일 값 그대로 — 화면은 이미 그려져 있다 */ });
  }
  function chDate(it) { return fmtNoYear(chReported[it.id]); }
  function chairmanPending() {
    return (window.WellperionChairmanItems || []).filter(function (it) { return !chDate(it); });
  }
  function chairmanDone() {
    return (window.WellperionChairmanItems || []).filter(function (it) { return !!chDate(it); });
  }
  function chairmanSection() {
    var items = chairmanPending();
    if (!items.length) return '';
    return '■ 회장님 보고건 ' + items.length + '건 (진행 현황)\n\n' +
      items.map(function (it, i) {
        return (i + 1) + '. ' + it.title + ' (' + (it.cat || '분류 미정') + ')' +
          (it.when ? ('\n   · 진행: ' + it.when) : '');
      }).join('\n');
  }

  /* 문안은 실제로 담긴 것만 적는다(GM 지적 2026-08-14 "보고문안복사도 이상해").
     예전엔 대표님 보고건이 0건이어도 '■ 대표님 보고건 0건' 과 빈 줄이 그대로 찍히고,
     회장님 건만 있는데도 첫 줄이 '대표님께 …' 로 나갔다. 0건 구획은 빼고 인사말을 실제 대상에 맞춘다. */
  function buildDigest(items, introLine, includeChairman) {
    var blocks = [];
    if (items.length) {
      var body = items.map(function (it, i) {
        return (i + 1) + '. ' + it.title +
          '\n   · 카테고리: ' + (it.category || '—') +
          '\n   · 일정: ' + it.schedule +
          (it.content ? ('\n   · 내용: ' + it.content) : '');
      }).join('\n\n');
      blocks.push((includeChairman ? '■ 대표님 보고건 ' + items.length + '건\n\n' : '') + body);
    }
    var ch = includeChairman ? chairmanSection() : '';
    if (ch) blocks.push(ch);
    var intro = (!items.length && ch) ? '회장님께 아래 업무를 보고드립니다.'
              : (items.length && ch) ? '대표님·회장님께 아래 업무를 보고드립니다.'
              : introLine;
    return intro + ' (' + todayStr() + ')\n\n' + blocks.join('\n\n') + '\n\n확인 부탁드립니다.';
  }

  // ── 화면 렌더 + 이벤트(대표님/GM 페이지 공용 — cfg 로만 갈린다) ──
  function mount(cfg) {
    var elCount = document.getElementById('owner-count');
    var elBulkBtn = document.getElementById('owner-bulk-btn');
    var elBulkStatus = document.getElementById('owner-bulk-status');
    var elDigest = document.getElementById('owner-digest');
    var elGrpCnt = document.getElementById('owner-grp-cnt');
    var elGrid = document.getElementById('owner-grid');
    var elSum = document.getElementById('owner-sum-body');
    // owner-bulk-btn 은 없는 페이지도 있다(GM업무.html — GM 지시 2026-08-24 "보고문안 복사 버튼 삭제").
    // 그 페이지에서 elBulkBtn 이 null 이어도 mount() 전체가 죽지 않게 아래 사용처마다 가드를 둔다.
    var origBtnLabel = elBulkBtn ? elBulkBtn.textContent : ''; // 조회 실패 시 「다시 불러오기」로 바꿨다가 성공하면 이 라벨로 되돌린다.

    var _items = null; // {id,title,category,schedule,status,owner,note,content,reported}

    function toItem(r) {
      var content = String(r['내용'] || '').trim();
      return {
        id: String(r['id'] || '').trim(),
        title: String(r['업무명'] || '').trim(),
        category: catName(r['카테고리']),
        schedule: fmtSchedule(r['시작일'], r['종료일']),
        status: String(r['상태'] || '').trim(),
        owner: String(r['담당자'] || '').trim(),
        note: String(r['보류사유'] || '').trim(),
        content: stripTags(content),
        rawContent: content,
        reported: isReported(content, cfg.markPrefix),
        reportedAt: reportedDate(content, cfg.markPrefix)
      };
    }

    function render() {
      if (_items === null) {
        // 영구 잠금 대신 재시도 — 사람이 한 번 누르면 load()를 다시 돈다(GM 지적 2026-08-08).
        elGrid.innerHTML = '<div class="rep-empty">데이터를 불러오지 못했습니다.</div>';
        elCount.textContent = '조회 실패';
        if (elBulkBtn) { elBulkBtn.disabled = false; elBulkBtn.textContent = '다시 불러오기'; }
        elBulkStatus.textContent = '업무·결재 자료를 못 불러왔습니다. 다시 불러오기를 눌러 주세요.';
        return;
      }
      if (elBulkBtn) elBulkBtn.textContent = origBtnLabel;
      var need = _items.filter(function (it) { return !it.reported; });
      var done = _items.filter(function (it) { return it.reported; });
      elCount.textContent = '보고 필요 ' + need.length + '건 · 보고 완료 ' + done.length + '건';
      // 소제목 옆 카운트 — 대기·완료 둘 다 보인다(GM 지시 2026-08-10, 대기·완료 한 표 통합에 맞춰 통일).
      elGrpCnt.textContent = '대기 ' + need.length + '건 · 완료 ' + done.length + '건';
      // 대표님 보고건이 0건이어도 회장님 보고건 현황만으로 보낼 수 있게 열어 둔다(둘 다 0일 때만 잠금).
      if (elBulkBtn) elBulkBtn.disabled = need.length === 0 && !(cfg.includeChairman && chairmanPending().length);

      if (!_items.length) {
        elGrid.innerHTML = '<div class="rep-empty">' + esc(cfg.emptyMsg) + '</div>';
        elSum.innerHTML = '';
        return;
      }

      elGrid.innerHTML = _items.map(function (it, i) {
        var no = String(i + 1).length < 2 ? '0' + (i + 1) : String(i + 1);
        var actionHtml = it.reported
          ? '<span class="done-badge">✅ 보고완료 ' + esc(it.reportedAt) + '</span>'
          : '<button type="button" class="ebtn save" data-id="' + esc(it.id) + '">보고 완료로 표시</button>';
        return (
          '<div class="item">' +
          // 카테고리는 별도 줄이 아니라 제목 옆 소괄호(GM 지시 2026-08-05 · 월간운영계획 카드 3종과 같은 표기).
          '<div class="top"><h2><span class="no">' + no + '</span>' + esc(it.title) +
          (it.category ? ' <span class="cat">(' + esc(it.category) + ')</span>' : '') +
          '</h2><span class="when">' + esc(it.schedule) + '</span></div>' +
          '<p class="body">' + esc(it.content || '내용 없음') + '</p>' +
          '<dl>' +
          '<div><dt>상태</dt><dd>' + esc(it.status || '—') + '</dd></div>' +
          '<div><dt>담당</dt><dd>' + esc(it.owner || '—') + '</dd></div>' +
          '<div><dt>비고</dt><dd>' + esc(it.note || '—') + '</dd></div>' +
          '</dl>' +
          '<div class="rpt-actions">' + actionHtml + '</div>' +
          '</div>'
        );
      }).join('');

      // 회장님 표(chRows)와 같은 4열(번호·제목+카테고리·상태/일정·액션)로 통일(GM 지적 2026-08-10).
      // 대기 건이 위, 완료 건이 아래로 오도록 정렬한다(GM 지시 2026-08-10 — 대기·완료 한 표 통합).
      elSum.innerHTML = need.concat(done).map(function (it, i) {
        var no = String(i + 1).length < 2 ? '0' + (i + 1) : String(i + 1);
        var noteFull = it.note || '';
        var noteShort = noteFull.length > 12 ? (noteFull.slice(0, 12) + '…') : noteFull;
        // 진행 상태 색+% 직관화(GM 확정 2026-08-11) — GM업무.html에 이미 있는 .st/.pct/.pbar
        // 클래스(GM 직접 카드와 동일)를 재사용, 새 CSS 없음. %는 stagePct() 단계표 산출값(지어낸 값 아님).
        var stCls = it.status === '진행중' ? 'on' : (it.status === '보류' ? 'carry' : 'plan');
        var statusHtml = '<span class="st ' + stCls + '">' + esc(it.status || '—') + '</span> · ' + esc(it.schedule) +
          (it.status === '보류' && noteFull ? ' <span class="cat" title="' + esc(noteFull) + '">(' + esc(noteShort) + ')</span>' : '') +
          pctBadge(stagePct(it.status));
        var actionHtml = it.reported
          ? '<span class="done-badge">✅ 보고완료 ' + esc(it.reportedAt) + '</span>'
          : '<button type="button" class="ebtn save" data-id="' + esc(it.id) + '">보고 완료로 표시</button>';
        return '<tr><td>' + no + '</td><td>' + esc(it.title) +
          (it.category ? ' <span class="cat">(' + esc(it.category) + ')</span>' : '') + '</td><td>' + statusHtml + '</td>' +
          '<td class="rpt-actions">' + actionHtml + '</td></tr>';
      }).join('');

      elGrid.querySelectorAll('button[data-id]').forEach(function (btn) {
        btn.addEventListener('click', function () { markReported(btn, btn.getAttribute('data-id')); });
      });
      // 요약표 행 버튼(카드는 CSS로 숨어 있어 이 표가 유일한 조작 지점 — GM 지적 2026-08-10).
      elSum.querySelectorAll('button[data-id]').forEach(function (btn) {
        btn.addEventListener('click', function () { markReported(btn, btn.getAttribute('data-id')); });
      });
    }

    function load() {
      elGrid.innerHTML = '<div class="rep-empty">불러오는 중…</div>';
      readWorkApproval().then(function (rows) {
        var filtered = filterRows(rows, cfg.wantCeoRows);
        _items = filtered ? filtered.map(toItem) : null;
        render();
      });
    }

    // 「보고 완료로 표시」 — 새 칸을 만들지 않고 기존 '내용' 칸 끝에 표식을 덧붙인다(원문 보존, todo_update 재사용).
    function markReported(btn, id) {
      var it = _items.filter(function (x) { return x.id === id; })[0];
      if (!it) return;
      btn.disabled = true; btn.textContent = '저장 중…';
      var mark = '[' + cfg.markPrefix + ' ' + todayStr() + ']';
      var newContent = (it.rawContent ? it.rawContent + '\n' : '') + mark;
      var qs = 'action=todo_update&id=' + encodeURIComponent(id) + '&' + encodeURIComponent('내용') + '=' + encodeURIComponent(newContent);
      fetch(GAS_URL + '?' + qs, { method: 'GET', redirect: 'follow' })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (res && res.ok) { load(); }
          else { btn.disabled = false; btn.textContent = '보고 완료로 표시'; alert('저장하지 못했습니다' + (res && res.error ? (': ' + res.error) : '.')); }
        })
        .catch(function () { btn.disabled = false; btn.textContent = '보고 완료로 표시'; alert('저장하지 못했습니다.'); });
    }

    // 「보고건 통합 보고」 — 아직 보고 안 한 건만 모아 문안 1개로 만들어 클립보드에 복사(자동 발송은 준비 중).
    if (elBulkBtn) elBulkBtn.addEventListener('click', function () {
      if (_items === null) { elBulkStatus.textContent = '다시 불러오는 중…'; load(); return; } // 조회 실패 재시도
      var need = (_items || []).filter(function (it) { return !it.reported; });
      var chN = cfg.includeChairman ? chairmanPending().length : 0;
      if (!need.length && !chN) return;
      var text = buildDigest(need, cfg.reportIntro, cfg.includeChairman);
      elDigest.style.display = 'block';
      elDigest.textContent = text;
      elBulkStatus.textContent = '문안 생성 중…';
      var chCnt = chN;
      var cntLabel = need.length + '건' + (chCnt ? ' + 회장님 보고건 ' + chCnt + '건' : '');
      dispatchReport(text, function (ok) {
        elBulkStatus.textContent = ok ? ('복사됨 ✓ — 업무보고방에 붙여넣어 주세요(' + cntLabel + ')') : '클립보드 복사 실패 — 아래 문안을 직접 복사해 주세요.';
      });
    });

    // 👑 회장님 보고건 표 — 목록 정본(_chairman_items.js) + 보고 완료 상태(chairman_reported.json).
    // 문안(chairmanSection)과 같은 두 소스를 읽으므로 화면과 복사본이 어긋날 수 없다.
    // 그 파일을 안 실은 페이지에는 요소 자체가 없어 그냥 건너뛴다.
    var elChCnt = document.getElementById('chairman-grp-cnt');
    var elChSum = document.getElementById('chairman-sum-body');

    // 자료 링크(docs)는 2026-08-19 GM 지시로 이 표에서 걷어냈다 — "회장님 보고에 있는 링크들은
    // GM업무라인으로 넘겨줘 … 결국 내가 업무 진행하는 건들이니까". A3·검토서는 이제 GM 업무 목표
    // (monthly_ops_plan objectives[].docs)에만 달린다. 아래 chLink 로 그 목표까지 한 번에 간다.
    // chDocs() 는 읽을 데이터가 없어져 함께 지웠다(꺼둔 채 남기지 않는다 · 약속 L21).

    // 관련 GM 직접 업무로 연결(2026-08-11 GM 지시 "스토리가 이어지는 맥락으로") — it.link 있는 건만
    // GM업무.html #gm-<목표id> 카드로 바로 간다. 억지 연결 금지라 정본(_chairman_items.js)에 실재하는
    // 건만 필드를 들고 있다 — 여기서는 있으면 그리고 없으면 건너뛴다.
    function chLink(it) {
      // cfg.hideChairmanLinks — GM업무.html 전용 지시(GM 2026-08-24 "회장님 등록 목록에 링크좀
      // 안달았으면 좋겠어"). 대표님_지시사항.html 은 이 cfg 를 안 넘기므로 그대로 링크가 보인다.
      if (!it.link || cfg.hideChairmanLinks) return '';
      return ' <a class="doc-link" href="' + esc(it.link.href) + '" target="_blank" rel="noopener">🔗 ' + esc(it.link.label) + '</a>';
    }

    // startNo — 대기·완료를 한 표에 이어붙일 때(GM 지시 2026-08-10) 번호가 1부터 다시 시작하지 않게.
    function chRows(list, isDone, startNo) {
      var base = startNo || 0;
      return list.map(function (it, i) {
        var n = base + i + 1;
        var no = String(n).length < 2 ? '0' + n : String(n);
        // ★2026-08-12 GM 지시로 되살렸다. 2026-08-11 에는 이 버튼이 commit_file(GitHub API)로 저장하다
        // 열쇠 만료(401)로 항상 실패해 「저장 일시중단」으로 막아 뒀었다. 이제 부서보드·브로제이가 쓰는
        // 공용 저장소로 갈아타 열쇠 없이 저장된다 — 위 CH_BOARD_URL·CH_BOARD_KEY 참조.
        var act = isDone
          ? '<span class="done-badge">✅ 보고완료 ' + esc(chDate(it)) + '</span>'
          : '<button type="button" class="ebtn save ch-rep-btn" data-ch-id="' + esc(it.id) + '">보고 완료로 표시</button>';
        // 대표님 표(elSum)와 같은 4열로 통일(GM 지적 2026-08-10) — 일정/액션을 별도 칸으로 분리.
        return '<tr><td>' + no + '</td><td>' + esc(it.title) +
          ' <span class="cat">(' + esc(it.cat || '분류 미정') + ')</span>' + chLink(it) + '</td><td>' + esc(it.when || '일정 미정') +
          pctBadge(stagePct(it.when)) + '</td>' +
          '<td class="rpt-actions">' + act + '</td></tr>';
      }).join('');
    }

    function renderChairman() {
      if (!elChSum) return;
      var pend = chairmanPending(), done = chairmanDone();
      // 🤵 대표님 줄(owner-grp-cnt)과 같은 형식으로 통일(GM 지시 2026-08-10) — 대기·완료 둘 다 보인다.
      if (elChCnt) elChCnt.textContent = '대기 ' + pend.length + '건 · 완료 ' + done.length + '건';
      // 대기 건이 위, 완료 건이 아래로 오도록 한 표에 합친다(GM 지시 2026-08-10) — 대기 0건이어도
      // 빈 안내문 대신 완료 행이 그대로 보인다.
      elChSum.innerHTML = chRows(pend, false, 0) + chRows(done, true, pend.length);
      // 대표님 칸과 같은 규칙 — 양쪽 다 보고 대기 0건이면 문안 복사 버튼을 잠근다.
      if (elBulkBtn) {
        var needOwner = (_items || []).filter(function (it) { return !it.reported; }).length;
        elBulkBtn.disabled = needOwner === 0 && !(cfg.includeChairman && pend.length);
      }
      Array.prototype.forEach.call(elChSum.querySelectorAll('.ch-rep-btn'), function (btn) {
        btn.addEventListener('click', function () { markChairmanReported(btn, btn.getAttribute('data-ch-id')); });
      });
    }

    // 「보고 완료로 표시」(회장님) — 완료 날짜만 공용 저장소에 넣는다(목록 정본은 손대지 않는다).
    // 저장 직전 최신값을 다시 읽어 얹는다 — 두 사람이 같이 눌러도 앞사람 표시가 지워지지 않게.
    // 비밀번호를 묻지 않는다: 이 화면은 이미 잠금(1531)을 지나야 열리고, 저장하는 값은 날짜 하나다.
    function markChairmanReported(btn, id) {
      if (!id) return;
      btn.disabled = true; btn.textContent = '저장 중…';
      // ★저장 전에 반드시 공용 저장소를 먼저 읽는다. 파일 값만 보고 저장하면, 저장소에만 있고
      // 파일엔 아직 없는 완료 표시가 이 저장 한 번에 통째로 지워진다(덮어쓰기 저장이라서).
      refreshChairmanFromBoard().then(function () {
        var next = {};
        Object.keys(chReported).forEach(function (k) { if (k.charAt(0) !== '_') next[k] = chReported[k]; });
        next[id] = todayStr();
        return fetch(CH_BOARD_URL, {
          method: 'POST', redirect: 'follow', headers: { 'Content-Type': 'text/plain;charset=utf-8' },
          body: JSON.stringify({ action: 'saveBoard', key: CH_BOARD_KEY, board: next })
        }).then(function (r) { return r.json(); }).then(function (res) {
          if (res && res.ok) { chReported = next; renderChairman(); }
          else {
            btn.disabled = false; btn.textContent = '보고 완료로 표시';
            alert('저장하지 못했습니다' + (res && res.error ? (': ' + res.error) : '.'));
          }
        });
      }).catch(function () {
        btn.disabled = false; btn.textContent = '보고 완료로 표시';
        alert('저장하지 못했습니다.');
      });
    }

    // 파일 값으로 먼저 그리고(즉시), 공용 저장소 답이 오면 그때 다시 그린다.
    loadChairmanReported().then(function () {
      renderChairman();
      refreshChairmanFromBoard(renderChairman);
    });
    load();
  }

  // 보고 대기/완료 판정은 이 파일 하나만 갖는다 — 읽는 쪽(GM업무.html 인쇄·건수)은 이 두 함수를
  // 쓴다(약속 L01 · 판정 복제 금지). 상태 파일 조회 전에는 전부 '대기'로 나온다.
  window.OwnerDirective = { mount: mount, chairmanPending: chairmanPending, chairmanDone: chairmanDone, chairmanDate: chDate };
})();
