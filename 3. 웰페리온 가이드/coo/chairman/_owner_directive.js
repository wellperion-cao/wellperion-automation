/*!
 * 대표님_지시사항.html · 김남욱GM_업무.html 공용 로직 (2026-08-05 GM 지시 — "판정·문안 생성 로직을 복제하지
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

  // ── 발송 담당(2026-08-05 GM 지시) — 지금은 클립보드 복사만 한다. 텔레그램 봇 토큰을 브라우저(공개 소스)에
  //    넣으면 전 채널 발신 권한이 그대로 노출돼 절대 금지(GM 확인 완료). 업무 시트 GAS 의 텔레그램 발신
  //    (_notifyTelegram)도 2026-05-28 GM 결재로 no-op 폐기 상태라 지금 호출 가능한 발송 액션이 없다
  //    (GAS 재배포는 백엔드라 시토 배403 으로 이관됨). 나중에 발송 액션이 생기면 이 함수 하나만 고치면
  //    대표님·GM 페이지 양쪽이 한 번에 자동 발송으로 바뀐다 — 호출부는 손대지 않는다.
  function dispatchReport(text, onDone) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { onDone(true); }).catch(function () { onDone(false); });
    } else { onDone(false); }
  }

  // 👑 회장님 지시건 현황 — 2026-08-05 GM 지시("회장님 업무보고건을 대표님에게도 같이 회장님 업무 지시건으로
  // 정리해서 한 번에 복사해 붙여넣게"). 목록 정본 = _chairman_items.js(배열 한 벌·복제 없음). 그 파일을 안 실은
  // 페이지에서는 빈 문자열이 되어 문안이 예전 그대로다(조용히 빠지지 않게 cfg.includeChairman 로만 켠다).
  function chairmanSection() {
    var items = window.WellperionChairmanItems || [];
    if (!items.length) return '';
    return '\n\n■ 회장님 업무 지시건 ' + items.length + '건 (진행 현황)\n\n' +
      items.map(function (it, i) {
        return (i + 1) + '. ' + it.title + ' (' + (it.cat || '분류 미정') + ')' +
          '\n   · 진행: ' + it.when;
      }).join('\n');
  }

  function buildDigest(items, introLine, includeChairman) {
    var body = items.map(function (it, i) {
      return (i + 1) + '. ' + it.title +
        '\n   · 카테고리: ' + (it.category || '—') +
        '\n   · 일정: ' + it.schedule +
        (it.content ? ('\n   · 내용: ' + it.content) : '');
    }).join('\n\n');
    var head = includeChairman ? '■ 대표님 보고 필요건 ' + items.length + '건\n\n' : '';
    return introLine + ' (' + todayStr() + ')\n\n' + head + body +
      (includeChairman ? chairmanSection() : '') + '\n\n확인 부탁드립니다.';
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
        reported: isReported(content, cfg.markPrefix)
      };
    }

    function render() {
      if (_items === null) {
        elGrid.innerHTML = '<div class="rep-empty">데이터를 불러오지 못했습니다.</div>';
        elCount.textContent = '조회 실패';
        elBulkBtn.disabled = true;
        return;
      }
      var need = _items.filter(function (it) { return !it.reported; });
      var done = _items.filter(function (it) { return it.reported; });
      elCount.textContent = '보고 필요 ' + need.length + '건 · 보고 완료 ' + done.length + '건';
      elGrpCnt.textContent = _items.length + '건';
      // 대표님 보고 필요건이 0건이어도 회장님 지시건 현황만으로 보낼 수 있게 열어 둔다(둘 다 0일 때만 잠금).
      elBulkBtn.disabled = need.length === 0 && !(cfg.includeChairman && (window.WellperionChairmanItems || []).length);

      if (!_items.length) {
        elGrid.innerHTML = '<div class="rep-empty">' + esc(cfg.emptyMsg) + '</div>';
        elSum.innerHTML = '';
        return;
      }

      elGrid.innerHTML = _items.map(function (it, i) {
        var no = String(i + 1).length < 2 ? '0' + (i + 1) : String(i + 1);
        var actionHtml = it.reported
          ? '<span class="done-badge">✓ 보고 완료</span>'
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

      elSum.innerHTML = _items.map(function (it, i) {
        var no = String(i + 1).length < 2 ? '0' + (i + 1) : String(i + 1);
        return '<tr><td>' + no + '</td><td>' + esc(it.title) + (it.reported ? ' <span class="done-badge">✓</span>' : '') + '</td><td>' + esc(it.schedule) + '</td></tr>';
      }).join('');

      elGrid.querySelectorAll('button[data-id]').forEach(function (btn) {
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

    // 「보고 필요건 통합 보고」 — 아직 보고 안 한 건만 모아 문안 1개로 만들어 클립보드에 복사(자동 발송은 준비 중).
    elBulkBtn.addEventListener('click', function () {
      var need = (_items || []).filter(function (it) { return !it.reported; });
      var chN = cfg.includeChairman ? (window.WellperionChairmanItems || []).length : 0;
      if (!need.length && !chN) return;
      var text = buildDigest(need, cfg.reportIntro, cfg.includeChairman);
      elDigest.style.display = 'block';
      elDigest.textContent = text;
      elBulkStatus.textContent = '문안 생성 중…';
      var chCnt = cfg.includeChairman ? (window.WellperionChairmanItems || []).length : 0;
      var cntLabel = need.length + '건' + (chCnt ? ' + 회장님 지시건 ' + chCnt + '건' : '');
      dispatchReport(text, function (ok) {
        elBulkStatus.textContent = ok ? ('복사됨 ✓ — 업무보고방에 붙여넣어 주세요(' + cntLabel + ')') : '클립보드 복사 실패 — 아래 문안을 직접 복사해 주세요.';
      });
    });

    // 👑 회장님 업무 지시건 표 — 정본 배열(_chairman_items.js)을 그대로 그린다. 문안(chairmanSection)과 같은
    // 배열을 읽으므로 화면과 복사본이 어긋날 수 없다. 그 파일을 안 실은 페이지에는 요소 자체가 없어 그냥 건너뛴다.
    var elChCnt = document.getElementById('chairman-grp-cnt');
    var elChSum = document.getElementById('chairman-sum-body');
    if (elChSum) {
      var chItems = window.WellperionChairmanItems || [];
      if (elChCnt) elChCnt.textContent = chItems.length + '건';
      elChSum.innerHTML = chItems.length
        ? chItems.map(function (it, i) {
            var no = String(i + 1).length < 2 ? '0' + (i + 1) : String(i + 1);
            return '<tr><td>' + no + '</td><td>' + esc(it.title) +
              ' <span class="cat">(' + esc(it.cat || '분류 미정') + ')</span></td><td>' + esc(it.when || '일정 미정') + '</td></tr>';
          }).join('')
        : '<tr><td colspan="3">회장님 지시건이 없습니다.</td></tr>';
    }

    load();
  }

  window.OwnerDirective = { mount: mount };
})();
