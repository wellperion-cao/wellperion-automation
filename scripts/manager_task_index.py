# -*- coding: utf-8 -*-
"""중간관리자 3인 업무 목차 — GM 이 목차로 체크하는 한 장.

만드는 이유(GM 지시 2026-09-09): "실장님에게 목차 리스트를 줘서 내가 업무를 체크하는게 훨씬 효율적"
새 원장을 만들지 않는다(약속 L21) — 이미 매일 쌓이는 `_digest_ledger.json` 의 번호(no) 건을 사람별로 갈라 렌더할 뿐이다.
GM 이 화면에서 체크한 것은 그 브라우저에만 남는다(localStorage) — 원장 상태는 실무진 회신으로만 바뀐다.

읽기 편하게 다듬음(GM 지시 2026-09-10 "이거 조금 더 친절하게 정리해줄 수 있어? 그리고 GM업무에 붙여줘"):
  · 맨 위 요약 띠 + 「먼저 볼 것」(경과 긴 순 5건)
  · 「최근 상황」은 40자까지만 보이고 전문은 title(마우스 올리면)
  · 경과 14일↑ 빨강 / 7~13일 주황
  · 담당 미정 건은 성격별 <details> 묶음

갱신: python scripts/manager_task_index.py   (매일 아침 정리 뒤 다시 돌리면 최신)

업무 SSOT 와 안 겹치게(나우열M 지적 2026-09-10 "직원들은 SSOT 와 너가 준 페이지 두 개를
중복으로 확인하는 비효율적인 상황"): 렌더 때마다 업무 SSOT(GAS todo_list)를 읽어 제목이
닮은 건은 사람별 표에서 빼고 맨 아래 접힘 목록("업무 SSOT 로 넘어간 것")으로 옮긴다.
SSOT 조회가 실패하면 대조 없이 종전대로 렌더하고 화면에 실패를 적는다.
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 원장은 방마다 한 벌씩 있다. 이 화면이 보여 주는 세 사람(실장·소장·나우열M)에게 실제로
# 통이 나가는 곳은 ★중간관리자 방이고, 07:50 아침 통(send_ops_digest.MGR_LEDGER)도 그 원장을
# 읽는다. 그런데 이 화면만 ★운영부 원장을 읽고 있어 두 목록이 어긋났다 — 2026-09-10 실측:
# ★중간관리자 10:36 갱신·번호 230까지 / ★운영부 07:34 갱신·번호 226까지. GM 결재 3건을
# ★중간관리자에 등록했더니 이 화면에만 안 떴다. 보내는 곳과 보는 곳을 같은 원장으로 맞춘다.
LEDGER = ROOT / "1. AI자료_아카이브" / "11_카카오톡" / "★중간관리자" / "_digest_ledger.json"
OUT = ROOT / "3. 웰페리온 가이드" / "coo" / "chairman" / "중간관리자_업무목차.html"

MANAGERS = [("이경연 실장", "운영부", "★중간관리자 방"),
            ("이정헌 소장", "시설부", "★중간관리자 방"),
            ("나우열M", "인사·파트너", "텔레그램 업무관리 방")]
DONE = {"resolved", "done", "closed", "완료", "취소", "삭제"}
CAT = {"1": "매출·영업", "2": "인사", "3": "파트너팀", "4": "운영 정책", "5": "시설·환경",
       "6": "회원·CS", "7": "IT·자동화", "8": "교육·조직문화", "9": "회의"}

# 담당 미정 건을 성격으로 가르는 기준 — 원장의 category 가 먼저, 없거나 안 맞으면 제목·상황의 낱말로.
GROUPS = [
    ("안전·시설", {"시설·환경", "시설 및 환경"},
     ("안전", "소방", "미끄러", "사우나", "수리", "고장", "청소", "설치", "공조", "칠러",
      "정비", "주차", "시설", "환경", "타석", "청정기", "점검", "휴관")),
    ("회원·응대", {"회원·CS"},
     ("회원", "컴플레인", "분실", "환불", "문의", "안내", "접수", "응대", "공지", "강습")),
    ("매출·영업", {"매출·영업"},
     ("매출", "LOSS", "요금", "견적", "결제", "영업", "선물세트", "쿠팡", "보고서")),
    ("시스템·IT", {"IT·자동화", "IT·시스템·자동화"},
     ("서버", "ERP", "AWS", "자동", "시스템", "PC", "화면", "링크", "로그인", "데이터")),
]
# 「먼저 볼 것」에 붙는 성격 딱지 — 왜 급한지 한 낱말로 보인다.
FLAGS = [("안전", ("안전", "소방", "미끄러", "화재", "사고")),
         ("법정·규정", ("법", "변호사", "규정", "계약", "노동", "점검 의무")),
         ("회원", ("회원", "컴플레인", "환불", "분실", "고객"))]


def latest_by_no() -> dict[int, tuple[str, dict]]:
    """번호마다 가장 최근 기록 하나만 남긴다 — 같은 건이 날짜마다 다시 실리기 때문."""
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))
    seen: dict[int, tuple[str, dict]] = {}
    for e in rows:
        for it in e.get("issues") or []:
            n = it.get("no")
            if n is None:
                continue
            d = str(e.get("date") or "")
            if n not in seen or d >= seen[n][0]:
                seen[n] = (d, it)
    return seen


def days_since(d: str) -> int:
    try:
        return (date.today() - datetime.strptime(d[:10], "%Y-%m-%d").date()).days
    except Exception:
        return 0


def fetch_ssot_rows() -> list | None:
    """업무 SSOT(GAS todo_list) 전체 행 — 이 목차와 겹치는 건을 가려낼 때만 쓴다(읽기 전용).
    gmkey 없이 부르면 GM 행이 통째로 빠진다(2026-09-07 실측) — 반드시 넣는다.
    조회 실패(느림·타임아웃)면 None — 호출부가 '대조 없이 종전대로'로 처리한다."""
    try:
        from collectors.ops_shared import SSOT_API_URL, gas_get
    except Exception:
        return None
    resp = gas_get(SSOT_API_URL, params={"action": "todo_list", "include_gm": "1", "gmkey": "1531"},
                    timeout=90, label="manager_task_index")
    if resp is None:
        return None
    try:
        data = resp.json()
        rows = data.get("data") or data.get("rows") or []
        return rows if isinstance(rows, list) else None
    except Exception:
        return None


def _title_key(t: str) -> str:
    """한글·영문·숫자만 남기고 앞 24자 — 웰리 실측(09-10)과 같은 대조 기준."""
    return "".join(ch for ch in str(t or "") if ch.isalnum())[:24]


def find_ssot_match(issue: str, ssot_rows: list) -> dict | None:
    """제목이 0.62 이상 닮은 SSOT 행 하나. 완료·폐기 여부는 안 가린다 — 끝난 건도 목차에
    남아 있으면 안 된다(GM 지시)."""
    key = _title_key(issue)
    if not key:
        return None
    for r in ssot_rows:
        rk = _title_key(r.get("업무명"))
        if rk and difflib.SequenceMatcher(None, key, rk).ratio() >= 0.62:
            return r
    return None


def cat_name(it: dict) -> str:
    """category 칸이 '5' · '시설 및 환경' · '[6] 회원·CS' 로 섞여 들어온다 — 이름 하나로 편다."""
    raw = str(it.get("category") or "").strip().lstrip("[").replace("]", " ").strip()
    if not raw:
        return ""
    head = raw.split()[0]
    if head in CAT:
        return CAT[head]
    return raw


def group_of(it: dict) -> str:
    cn = cat_name(it)
    text = f'{it.get("issue") or ""} {it.get("note") or ""}'
    for name, cats, words in GROUPS:
        if cn in cats:
            return name
    for name, cats, words in GROUPS:
        if any(w in text for w in words):
            return name
    return "기타"


def flags_of(it: dict) -> list[str]:
    text = f'{it.get("issue") or ""} {it.get("note") or ""}'
    return [n for n, words in FLAGS if any(w in text for w in words)]


def short(t: str, n: int = 40) -> str:
    """첫 문장 또는 40자까지만 — 전문은 지우지 않고 title 로 접어 둔다."""
    s = t.split(". ")[0].strip()
    if len(s) > n:
        return s[:n].rstrip() + "…"
    return s + "…" if len(s) < len(t) else s


def age_cls(age: int) -> str:
    return "old" if age >= 14 else ("warn" if age >= 7 else "")


# 담당 후보 — 부서 순서대로(GM 지시 2026-09-10). 운영부 6 · 시설부 3 · 그 밖 5.
#   2026-09-11 GM 지적("담당칸에 각 부서장이 담당자 배정까지도 할 수 있게 드랍다운 항목에")으로
#   이 목록을 JS 에서 파이썬으로 옮겼다 — 담당칸이 datalist(입력칸 자동완성)라 칸에 이름이 이미
#   있으면 눌러도 목록이 안 펼쳐졌다. 이제 <select> 로 서버에서 찍는다.
OWNER_CHOICES = [
    "이경연 실장", "최준용M", "임정은M", "윤병현AM", "백승화 사원", "진수아 사원",   # 운영부
    "이정헌 소장", "김종현 차장", "박호균 과장",                                    # 시설부
    "나우열M", "이연희 반장", "박남일 반장", "양상규 고문", "김남욱 GM",            # 그 밖
]


def owner_select(no: int, who: str) -> str:
    """담당 드롭다운. 원장 값이 후보에 없는 이름이면 그 이름을 옵션으로 더해 선택 상태로 둔다
    (값을 잃지 않게). 저장 자리는 종전과 같은 공용 보드 MGR_TASK_OWNER 다."""
    opts = ['<option value="">— 미지정 —</option>']
    opts += [f'<option value="{html.escape(n)}"{" selected" if n == who else ""}>{html.escape(n)}</option>'
             for n in OWNER_CHOICES]
    if who and who not in OWNER_CHOICES:
        opts.append(f'<option value="{html.escape(who)}" selected>{html.escape(who)}</option>')
    return f'<select class="own-sel" data-o="{no}">{"".join(opts)}</select>'


def row_html(no: int, seen_date: str, it: dict) -> str:
    age = days_since(seen_date)
    due = str(it.get("due") or "").strip() or "—"
    note = str(it.get("note") or "").strip()
    cn = cat_name(it)
    note_td = (f'<td class="note" title="{html.escape(note)}">{html.escape(short(note))}</td>'
               if note else '<td class="note">—</td>')
    ss = ('<span class="ss-rc">접수처에서 닫음</span>' if is_reception_item(it)
          else '<span class="ss-no">SSOT 미등록</span>')
    who = str(it.get("owner") or "").strip()      # owner_select 가 escape 한다
    return (f'<tr data-no="{no}"><td class="ck"><input type="checkbox" data-k="mgr-{no}"></td>'
            f'<td class="no">#{no}</td>'
            f'<td class="ti">{html.escape(str(it.get("issue") or ""))}'
            f'{f"<span class=cat>{html.escape(cn)}</span>" if cn else ""}</td>'
            f'<td class="own">{owner_select(no, who)}</td>'
            f'<td class="due">{html.escape(due)}</td>'
            f'<td class="ss">{ss}</td>'
            f'{note_td}'
            f'<td class="age {age_cls(age)}">{age}일</td></tr>')


HEAD_ROW = ('<tr><th class="ck">✓</th><th class="no">번호</th><th>업무</th>'
            '<th class="own">담당</th><th class="due">기한</th><th class="ss">업무·결재 SSOT</th>'
            '<th>최근 상황</th><th class="age">경과</th></tr>')


# 종합접수처에서 들어와 접수처에서 닫는 건 — 업무 SSOT 에 올릴 것이 아니다(GM 2026-09-10
#   "종합접수처까지 내용이 다 올라가있는데, 이것을 SSOT에 올리는건 아닌 것 같아").
#   접수는 접수번호로 열리고 그 화면에서 닫힌다. 여기서는 「접수처에서 닫음」으로만 표시하고
#   「SSOT 미등록」 셈에서 뺀다 — 안 그러면 실무진이 같은 건을 두 곳에 올리게 된다.
_RECEPTION_MARK = re.compile(r"접수\s*\d+|RECEPTION-\d+|접수ID|FB\d{6}|종합접수처")
_RECEPTION_WORDS = ("컴플레인", "분실물", "미끄러", "고장", "청결", "매너", "자리 부족")


def is_reception_item(it: dict) -> bool:
    text = f'{it.get("issue") or ""} {it.get("note") or ""}'
    if _RECEPTION_MARK.search(text):
        return True
    return any(w in text for w in _RECEPTION_WORDS)


# 업무 구분 (GM 2026-09-11 「중간관리자 업무에 종합접수처 등의 내용까지 업무화 시켜놨던데,
#   업무구분이 명확해야할 것 같아」). 낱말 추측보다 원장의 kind 값이 먼저다 — 추측은 kind 가
#   없을 때만 쓴다. 값을 두 곳에 두지 않으려고 판정은 이 함수 하나만 쓴다.
#     routine   = 끝나지 않는 상시 책임(주간 점검·접수 마무리·점검 이행·SSOT 갱신)
#     reception = 종합접수처에서 열려 그 화면에서 닫히는 건
#     task      = 기한이 있고 끝나면 닫히는 일 — 이것만이 「업무」다
KINDS = ("routine", "reception", "task")


def kind_of(it: dict) -> str:
    k = str(it.get("kind") or "").strip().lower()
    if k in KINDS:
        return k
    return "reception" if is_reception_item(it) else "task"


OWNER_BOARD_KEY = "MGR_TASK_OWNER"      # 목차에서 GM 이 지정한 담당(공용 보드) — 체크(MGR_TASK_DONE)와 같은 보드
BOARD_URL = ("https://script.google.com/macros/s/"
             "AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec")


def fetch_owner_board() -> dict:
    """목차 화면에서 지정한 담당 — 다음 갱신 때 원장 owner 빈칸을 이 값으로 채운다.
    조회 실패면 빈 dict(담당 지정이 없던 것과 같게 — 지어내지 않는다)."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{BOARD_URL}?action=board&key={OWNER_BOARD_KEY}", timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d.get("board") or {} if d.get("ok") else {}
    except Exception:
        return {}


# ── ② 화면 청소 (GM 2026-09-11 "쓸데없는게 너무 많던데") ────────────────────────────────
#   원장 status 는 건드리지 않는다 — 사람이 답한 증거 없이 닫는 것은 금지. 화면에서만 가른다.
def find_dups(opens: dict[int, tuple[str, dict]]) -> dict[int, int]:
    """같은 일이 번호만 달리 두 줄로 있는 것 — {접을 옛 번호: 살릴 새 번호}.
    판정 근거 두 가지뿐: ① 제목이 다른 열린 번호를 (#NNN) 으로 가리킨다(사람이 손으로
    이어 적은 건) ② 제목 앞 24자가 0.72 이상 닮았다. 날짜가 뒤인 쪽을 살린다."""
    out: dict[int, int] = {}

    def mark(a: int, b: int) -> None:
        old, new = (a, b) if opens[a][0] <= opens[b][0] else (b, a)
        if old not in out and new not in out:
            out[old] = new

    for n, (_d, it) in opens.items():
        for m in re.finditer(r"[(（]#(\d+)[)）]", str(it.get("issue") or "")):
            t = int(m.group(1))
            if t != n and t in opens:
                mark(t, n)
    keys = sorted(opens)
    for i, n1 in enumerate(keys):
        for n2 in keys[i + 1:]:
            k1, k2 = _title_key(opens[n1][1].get("issue")), _title_key(opens[n2][1].get("issue"))
            if k1 and k2 and difflib.SequenceMatcher(None, k1, k2).ratio() >= 0.72:
                mark(n1, n2)
    return out


# ── ③ 원장 note 청소 (GM 2026-09-11) ─────────────────────────────────────────────────
#   우리가 방에 보낸 공고문이 회신으로 잘못 쌓였다. 사람이 쓴 회신은 절대 안 지운다.
_OUR_NOTICE = ("한 줄이면 됩니다",            # 공고문 예시 문구
               "그 번호로 진행을 체크하고")    # 같은 공고문의 뒷부분(예시 괄호가 잘려 들어온 조각)


def is_our_echo(frag: str, issue: str) -> bool:
    """이 note 조각이 우리 발신인가. 「회신: #번호 + 그 건 자기 제목」도 우리 공고문이다 —
    사람은 자기가 답하는 건의 제목을 그대로 되풀이하지 않는다."""
    if any(w in frag for w in _OUR_NOTICE):
        return True
    m = re.match(r"회신:\s*#\d+\s+(.+)$", frag.strip(), re.S)
    if not m:
        return False
    title = _title_key(issue)
    return len(title) >= 10 and _title_key(m.group(1)).startswith(title[:10])


def clean_notes(dry: bool = True) -> int:
    """원장 note 에서 우리 발신 조각과 똑같이 겹친 조각을 걷어낸다. 고치는 유일한 원장 항목."""
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))
    hit = 0
    for e in rows:
        for it in e.get("issues") or []:
            note = str(it.get("note") or "")
            if not note:
                continue
            issue = str(it.get("issue") or "")
            kept, dropped, saw = [], [], set()
            for f in (p.strip() for p in note.split(" · ")):
                if not f:
                    continue
                if is_our_echo(f, issue) or f in saw:
                    dropped.append(f)
                    continue
                saw.add(f)
                kept.append(f)
            if not dropped:
                continue
            hit += 1
            print(f'#{it.get("no")} {e.get("date")} {issue}')
            for f in dropped:
                print("   − " + f.replace("\n", " ")[:96])
            print("   ⇒ " + (" · ".join(kept).replace("\n", " ")[:130] or "(빈 값)"))
            if not dry:
                it["note"] = " · ".join(kept)
    if not dry:
        tmp = LEDGER.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, LEDGER)
    print(f"[clean-notes] {'(미리보기) ' if dry else ''}{hit}건")
    return hit


def selfcheck() -> None:
    t = "수영장 타일 사이 오염 부분 청소 가능 여부"
    assert is_our_echo(f"회신: #149 {t} — 9/12", t)
    assert is_our_echo("회신: #174 키즈락커\n👉 회신·보고는 「#번호 + 했다」 한 줄이면 됩니다(예:", "키즈락커 짤순이")
    assert not is_our_echo('회신: 이정헌 소장 13:17 "#149 진행중(휴관일에 실리콘작업하기로 정함)"', t)
    assert not is_our_echo("회신: #149 진행중(휴관일에 실리콘작업하기로 정함)", t)
    assert not is_our_echo("회신: #163 했다", "에스컬레이터 정밀진단 소견서·견적서 접수(#163)")
    o = {1: ("2026-09-01", {"issue": "회원 접수 4건 처리 방향 미정"}),
         2: ("2026-09-07", {"issue": "회원 접수 4건 처리방향 미정(#1)"}),
         3: ("2026-09-05", {"issue": "에스컬레이터 견적"})}
    assert find_dups(o) == {1: 2}, find_dups(o)
    print("[selfcheck] 담당 드롭다운·중복 판정·note 청소 판정 OK")


def approval_badge(m: dict) -> str:
    """업무·결재 SSOT 행 하나의 진행·결재 상태를 배지 두 개로. 값이 없으면 안 지어낸다."""
    st = str(m.get("상태") or "").strip() or "상태없음"
    ap_req = str(m.get("결재요청") or "").strip()
    ap_st = str(m.get("결재상태") or "").strip()
    gm_sign = bool(str(m.get("GM싸인") or "").strip())
    rep_sign = bool(str(m.get("대표싸인") or "").strip())
    out = [f'<span class="ss-st">{html.escape(st)}</span>']
    if ap_st == "결재완료":
        who = "GM·대표" if (gm_sign and rep_sign) else ("GM" if gm_sign else "")
        out.append(f'<span class="ss-ap done">결재완료{(" " + who) if who else ""}</span>')
    elif ap_req:
        out.append(f'<span class="ss-ap wait">결재대기 {html.escape(ap_req)}</span>')
    return "".join(out)


def table(rows: list[str], empty: str) -> str:
    body = "\n          ".join(rows) or f'<tr><td colspan="8" class="empty">{empty}</td></tr>'
    return f'<table>\n          {HEAD_ROW}\n          {body}\n        </table>'


def top_html(items: list[tuple[int, str, dict, str]]) -> str:
    """먼저 볼 것 — 사람 상관없이 경과가 긴 순 5건."""
    cards = []
    for no, d, it, who in items:
        age = days_since(d)
        fl = "".join(f'<span class="fl">{f}</span>' for f in flags_of(it))
        note = str(it.get("note") or "").strip()
        cards.append(
            f'<div class="top-i"><span class="top-age {age_cls(age)}">{age}일</span>'
            f'<div class="top-b"><b>#{no} {html.escape(str(it.get("issue") or ""))}</b>{fl}'
            f'<div class="top-w">{html.escape(who)}'
            f'{" · " + html.escape(short(note, 46)) if note else ""}</div></div></div>')
    return "\n      ".join(cards)


def build() -> str:
    seen = latest_by_no()
    opens = {n: v for n, v in seen.items() if str(v[1].get("status", "")).lower() not in DONE}

    # 목차 화면에서 GM 이 지정한 담당을 원장 빈칸에 채운다(GM 2026-09-10 "SSOT 등록건은 담당자도
    #   설정할 수 있어야해"). 원장에 이미 사람이 적혀 있으면 그 값이 먼저다 — 화면 입력이 실무진
    #   회신으로 들어온 담당을 덮지 않는다.
    owner_board = fetch_owner_board()
    if owner_board:
        for n, (d, it) in opens.items():
            picked = str(owner_board.get(f"mgr-{n}") or "").strip()
            if picked and not str(it.get("owner") or "").strip():
                it["owner"] = picked

    ssot_rows = fetch_ssot_rows()
    ssot_ok = ssot_rows is not None
    moved: list[tuple[int, str, dict, dict]] = []  # (no, date, it, ssot_row) — 업무 SSOT 로 넘어간 것
    if ssot_ok:
        remain = {}
        for n, (d, it) in opens.items():
            m = find_ssot_match(str(it.get("issue") or ""), ssot_rows)
            if m:
                moved.append((n, d, it, m))
            else:
                remain[n] = (d, it)
        opens = remain

    # ② 열린 목록에서 가를 것 셋 — 원장은 그대로 두고 화면에서만 가른다.
    dup_of = find_dups(opens)
    aside_dup = [(n, *opens.pop(n)) for n in sorted(dup_of)]
    aside_rt = [(n, *opens.pop(n)) for n in sorted(n for n, (_d, it) in opens.items()
                                                   if kind_of(it) == "routine")]
    aside_rc = [(n, *opens.pop(n)) for n in sorted(n for n, (_d, it) in opens.items()
                                                   if kind_of(it) == "reception")]

    blocks = []
    counts = []
    shown: list[tuple[int, str, dict, str]] = []

    for name, dept, room in MANAGERS:
        mine = sorted(((n, d, it) for n, (d, it) in opens.items()
                       if str(it.get("owner") or "").strip() == name), key=lambda x: x[0])
        counts.append((name, len(mine)))
        shown += [(n, d, it, name) for n, d, it in mine]
        blocks.append(f'''      <div class="blk">
        <h2>{html.escape(name)} <span class="sub">{html.escape(dept)} · {html.escape(room)} · 열린 건 {len(mine)}건</span></h2>
        {table([row_html(n, d, it) for n, d, it in mine], "열린 건 없음")}
      </div>''')

    # ★MANAGERS 밖 담당(예: 최준용M)도 반드시 어딘가에 보인다 — 2026-09-11 사고: 상가 4건 담당을
    #   최준용M 으로 바꾸자 사람별 블록(3인)에도, 담당 미정(빈칸)에도 안 걸려 화면에서 통째로
    #   사라졌다(GM 「업무SSOT에서 분리수거장 시안물 부착 업무가 사라졌어요」). 이름을 늘리는 대신
    #   「그 밖의 담당」 한 자리를 두어, 앞으로 어떤 이름이 와도 사라지지 않게 한다.
    mgr_names = {m[0] for m in MANAGERS}
    others = sorted(((n, d, it) for n, (d, it) in opens.items()
                     if str(it.get("owner") or "").strip()
                     and str(it.get("owner") or "").strip() not in mgr_names), key=lambda x: x[0])
    if others:
        shown += [(n, d, it, str(it.get("owner") or "").strip()) for n, d, it in others]
        blocks.append(f'''      <div class="blk">
        <h2>그 밖의 담당 <span class="sub">위 세 분이 아닌 분께 배정된 것 · {len(others)}건 ·
          그 방에 안 계신 분이면 실장·소장을 거쳐 전달됩니다</span></h2>
        {table([row_html(n, d, it) for n, d, it in others], "없음")}
      </div>''')

    unassigned = sorted(((n, d, it) for n, (d, it) in opens.items()
                         if not str(it.get("owner") or "").strip()), key=lambda x: x[0])
    shown += [(n, d, it, "담당 미정") for n, d, it in unassigned]

    # 성격별 묶음 — 각 묶음은 접힘, 제목에 건수. 어디에도 안 걸리면 「기타」.
    order = [g[0] for g in GROUPS] + ["기타"]
    buckets: dict[str, list] = {k: [] for k in order}
    for n, d, it in unassigned:
        buckets[group_of(it)].append((n, d, it))
    groups_html = "\n        ".join(
        f'<details class="grp"><summary>{html.escape(k)} <span class="gc">{len(v)}건</span></summary>\n        '
        + table([row_html(n, d, it) for n, d, it in v], "없음") + "\n        </details>"
        for k, v in buckets.items() if v)
    blocks.append(f'''      <div class="blk">
        <h2>담당 미정 <span class="sub">GM 이 세 사람 중 누구 몫인지 정하면 그 사람 목차로 옮긴다 · {len(unassigned)}건 · 성격별로 묶어 접어 뒀습니다</span></h2>
        <div class="grps">
        {groups_html or '<div class="empty" style="padding:10px 14px;">없음</div>'}
        </div>
      </div>''')

    if moved:
        moved_sorted = sorted(moved, key=lambda x: x[0])
        moved_rows = "\n        ".join(
            f'<li>#{no} {html.escape(str(it.get("issue") or ""))}'
            f'<span class="mvd">→ SSOT: {html.escape(str(m.get("업무명") or ""))} '
            f'{approval_badge(m)}</span></li>'
            for no, d, it, m in moved_sorted)
        blocks.append(f'''      <div class="blk">
        <details class="grp"><summary>업무 SSOT 로 넘어간 것 <span class="gc">{len(moved)}건</span></summary>
        <ul class="mvlist">
        {moved_rows}
        </ul>
        </details>
      </div>''')

    if aside_rt:
        blocks.insert(0, f'''      <div class="blk">
        <h2>상시 책임 <span class="sub">끝나는 일이 아니라 계속 보는 자리 · {len(aside_rt)}건 ·
          이 줄은 완료로 닫지 않습니다 — 아래 「업무」와 구분해 주십시오</span></h2>
        {table([row_html(n, d, it) for n, d, it in aside_rt], "없음")}
      </div>''')

    if aside_rc:
        blocks.append(f'''      <div class="blk">
        <details class="grp"><summary>다른 곳에서 닫힌 것 <span class="gc">{len(aside_rc)}건</span>
          <span class="gw">종합접수처에서 열리고 그 화면에서 닫는 건 — 여기서 하실 일은 없습니다</span></summary>
        {table([row_html(n, d, it) for n, d, it in aside_rc], "없음")}
        </details>
      </div>''')

    if aside_dup:
        dup_rows = "\n        ".join(
            f'<li>#{n} {html.escape(str(it.get("issue") or ""))}'
            f'<span class="mvd">→ 같은 건이 <b>#{dup_of[n]}</b> 로 새로 잡혀 있습니다(날짜가 뒤인 쪽을 살렸습니다)</span></li>'
            for n, d, it in aside_dup)
        blocks.append(f'''      <div class="blk">
        <details class="grp"><summary>중복 — 새 번호로 이어진 것 <span class="gc">{len(aside_dup)}건</span>
          <span class="gw">원장 상태는 그대로입니다 · 화면에서만 내렸습니다</span></summary>
        <ul class="mvlist">
        {dup_rows}
        </ul>
        </details>
      </div>''')

    ssot_note = ""
    if not ssot_ok:
        ssot_note = '<span class="b2 fail">⚠ 업무 SSOT 대조 실패 — 겹친 건이 그대로 보일 수 있습니다.</span>'
    elif moved:
        ssot_note = (f'<span class="b2">업무·결재 SSOT 에 올라간 것 {len(moved)}건 · 다른 곳에서 닫힌 것 '
                     f'{len(aside_rc)}건 · 중복 {len(aside_dup)}건은 맨 아래 접힘 목록으로 내렸습니다 · '
                     f'<b>여기 남은 {len(shown)}건이 업무 SSOT 에 올려야 하는 것</b>입니다.</span>')

    top5 = sorted(shown, key=lambda x: (-days_since(x[1]), x[0]))[:5]
    head = " · ".join(f"{n} {c}건" for n, c in counts)
    total = len(shown)
    oldest = max((days_since(d) for _, d, _, _ in shown), default=0)
    # 세 번째 숫자는 「급한 것이 몇 개인가」 — 아래 표의 빨간 경과(14일 이상)와 같은 기준이다.
    stale = sum(1 for _, d, _, _ in shown if days_since(d) >= 14)

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>중간관리자 업무</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  :root {{ --ink:#101418; --navy:#14304E; --navy-bg:#EDF1F6; --line:#E3E7EB; --dim:#6B7683; --warn:#96601A; --bad:#9E2A2A; }}
  body {{ font-family:'Noto Sans KR',sans-serif; color:var(--ink); background:#F4F6F8; padding:22px 18px 60px; }}
  .wrap {{ max-width:1180px; margin:0 auto; }}
  h1 {{ font-family:'Noto Serif KR',serif; font-size:27px; letter-spacing:-.6px; }}
  .lede {{ margin-top:6px; color:var(--dim); font-size:14px; line-height:1.7; }}
  .bar {{ margin-top:14px; background:var(--navy); color:#fff; padding:10px 14px; font-size:14px; font-weight:700; line-height:1.6; }}
  .bar .b2 {{ display:block; font-weight:400; font-size:13px; opacity:.85; }}
  .blk {{ background:#fff; border:1px solid var(--line); margin-top:14px; }}
  h2 {{ font-size:16px; padding:10px 14px; background:var(--navy-bg); color:var(--navy); border-bottom:1px solid var(--line); }}
  h2 .sub {{ font-weight:400; color:var(--dim); font-size:13px; margin-left:8px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th, td {{ padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; text-align:left; }}
  th {{ background:#FAFBFC; font-size:12.5px; color:var(--dim); font-weight:700; }}
  td.ck, th.ck {{ width:34px; text-align:center; }}
  td.no, th.no {{ width:62px; color:var(--dim); font-weight:700; }}
  td.due, th.due {{ width:104px; }}
  td.age, th.age {{ width:64px; text-align:right; color:var(--dim); font-variant-numeric:tabular-nums; }}
  td.age.warn {{ color:var(--warn); font-weight:700; }}
  td.age.old {{ color:var(--bad); font-weight:900; }}
  td.note {{ color:var(--dim); }}
  .cat {{ display:inline-block; margin-left:6px; font-size:11.5px; color:var(--dim); border:1px solid var(--line); padding:0 5px; }}
  tr.done td.ti {{ text-decoration:line-through; color:var(--dim); }}
  .empty {{ color:var(--dim); }}
  /* 먼저 볼 것 */
  .top {{ background:#fff; border:1px solid var(--line); border-left:4px solid var(--bad); margin-top:14px; padding:12px 14px 14px; }}
  .top h2 {{ background:none; border:0; padding:0 0 8px; font-size:16px; }}
  .top .why {{ color:var(--dim); font-size:13px; font-weight:400; margin-left:8px; }}
  .top-i {{ display:flex; gap:12px; align-items:baseline; padding:7px 0; border-top:1px solid var(--line); }}
  .top-age {{ flex:0 0 58px; text-align:right; font-size:16px; font-weight:900; color:var(--dim); font-variant-numeric:tabular-nums; }}
  .top-age.warn {{ color:var(--warn); }}
  .top-age.old {{ color:var(--bad); }}
  .top-b {{ flex:1 1 auto; min-width:0; }}
  .top-b b {{ font-size:15px; }}
  .top-w {{ color:var(--dim); font-size:13px; margin-top:2px; }}
  .fl {{ display:inline-block; margin-left:6px; font-size:11.5px; font-weight:700; color:var(--bad); border:1px solid var(--bad); padding:0 5px; vertical-align:middle; }}
  /* 담당 미정 성격별 묶음 */
  .grps {{ padding:6px 0; }}
  .grp {{ border-bottom:1px solid var(--line); }}
  .grp > summary {{ cursor:pointer; padding:9px 14px; font-size:14px; font-weight:700; color:var(--navy); list-style:none; }}
  .grp > summary::-webkit-details-marker {{ display:none; }}
  .grp > summary::before {{ content:"▸ "; color:var(--dim); }}
  .grp[open] > summary::before {{ content:"▾ "; }}
  .grp .gc {{ font-weight:400; color:var(--dim); font-size:13px; margin-left:6px; }}
  .grp .gw {{ font-weight:400; color:var(--dim); font-size:12.5px; margin-left:6px; }}
  .own {{ white-space:nowrap; }}
  .own-sel {{ max-width:118px; padding:3px 4px; border:1px solid var(--line); border-radius:6px;
              background:#fff; color:inherit; font:inherit; font-size:12.5px; }}
  .own-sel:focus {{ outline:2px solid rgba(183,159,138,0.5); }}
  .own-sel.saved {{ border-color:#6abf7b; }}
  .ss-rc {{ display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
            background:rgba(255,255,255,0.08); color:var(--dim); }}
  .ss {{ white-space:nowrap; }}
  .ss-no {{ display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
            background:rgba(237,91,63,0.14); color:#ED5B3F; }}
  .ss-st {{ display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
            background:rgba(255,255,255,0.08); color:var(--dim); margin-right:4px; }}
  .ss-ap {{ display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px; }}
  .ss-ap.done {{ background:rgba(106,191,123,0.16); color:#6abf7b; }}
  .ss-ap.wait {{ background:rgba(230,200,78,0.16); color:#e6c84e; }}
  .mvlist {{ list-style:none; padding:2px 14px 10px; }}
  .mvlist li {{ padding:5px 0; font-size:13.5px; border-top:1px solid var(--line); }}
  .mvlist li:first-child {{ border-top:0; }}
  .mvd {{ display:block; color:var(--dim); font-size:12.5px; margin-top:2px; }}
  .bar .fail {{ color:#FFD37A; }}
  .foot {{ margin-top:16px; color:var(--dim); font-size:13px; line-height:1.8; }}
  @media (max-width:640px) {{
    body {{ padding:16px 10px 50px; }}
    h1 {{ font-size:21px; }}
    table {{ font-size:13px; }}
    th, td {{ padding:6px 6px; }}
    td.due, th.due {{ width:72px; }}
    td.no, th.no {{ width:46px; }}
    td.age, th.age {{ width:48px; }}
    /* 좁은 폭에서 표를 억지로 구겨 넣지 않는다 — 블록만 옆으로 밀어서 본다. */
    .blk {{ overflow-x:auto; }}
    .blk table {{ min-width:620px; }}
    .top-age {{ flex:0 0 46px; font-size:15px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>중간관리자 업무 목차</h1>
  <div class="lede">이경연 실장 · 이정헌 소장 · 나우열M 세 사람의 <b>열린 업무</b>를 번호순으로 편 목차입니다.
    회신은 번호로 받습니다 — 「#번호 + 했다/진행중/언제」 한 줄.<br>
    체크는 GM 화면에만 남습니다(이 브라우저). 원장 상태는 실무진 회신이 오면 바뀝니다.</div>
  <div class="bar">기준 {date.today().isoformat()} · 열린 {total}건 · 가장 오래된 것 {oldest}일 · 14일 넘게 답 없는 것 {stale}건
    <span class="b2">{html.escape(head)} · 담당 미정 {len(unassigned)}건</span>
    {ssot_note}</div>

  <div class="top">
    <h2>🔺 먼저 볼 것 <span class="why">사람 상관없이 오래 묵은 순 5건 — 여기부터 답을 받으세요</span></h2>
      {top_html(top5)}
  </div>

{chr(10).join(blocks)}
  <div class="foot">
    <b>이 목록은 무엇인가</b><br>
    ① 값은 매일 아침 카카오·텔레그램 방을 정리해 쌓는 원장(<code>_digest_ledger.json</code>)에서 그대로 옵니다 — 이 화면이 따로 적어 두는 건 없습니다.<br>
    ② 번호(#)는 건마다 처음 잡힌 그대로 고정입니다 — 목록이 바뀌어도 번호는 안 바뀌므로 그 번호로 이야기하시면 됩니다.<br>
    ③ 회신은 번호로 붙습니다 — 실무진이 방에 「#번호 + 했다/진행중/언제」로 답하면 다음 날 아침 정리에서 그 건의 「최근 상황」이 바뀌고, 끝난 건은 이 목록에서 내려갑니다.<br>
    갱신 = <code>python scripts/manager_task_index.py</code> · 경과 색 = 14일 이상 빨강 · 7~13일 주황.
  </div>
</div>
<script>
  // 체크 상태는 공용 보드에 남긴다(GM 지적 2026-09-10 "아무 추적 및 연동 관련된 부분이 어설픈데?").
  //   종전엔 localStorage 라 그 브라우저에만 남았다 — 다른 기기로 열거나 다른 사람이 보면
  //   아무 흔적이 없었다. GM_TASK_OWNERS 담당 칸이 쓰는 그 보드(GAS saveBoard)에 키만 하나
  //   더 둔다 — 새 저장소를 만들지 않는다(약속 L21). 저장은 최신 보드를 다시 읽어 내 값 하나만
  //   얹는 방식이라 남의 체크를 덮지 않는다.
  var BOARD_URL = 'https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec';
  var BOARD_KEY = 'MGR_TASK_DONE';
  var ERP_API_ON = /^(erp[.]wellperion[.]com|15[.]164[.]151[.]105)$/.test(location.hostname);
  var boardCache = {{}};
  function readBoard() {{
    var gas = function () {{
      return fetch(BOARD_URL + '?action=board&key=' + BOARD_KEY, {{cache:'no-store'}})
        .then(function (r) {{ return r.json(); }});
    }};
    if (!ERP_API_ON) return gas();
    return fetch('/api/board/' + BOARD_KEY, {{cache:'no-store'}})
      .then(function (r) {{ if (!r.ok) throw new Error('api ' + r.status); return r.json(); }})
      .catch(gas);
  }}
  function saveCheck(k, on) {{
    return readBoard().then(function (j) {{
      var fresh = (j && j.ok && j.board) ? j.board : {{}};
      if (on) fresh[k] = new Date().toISOString().slice(0, 16).replace('T', ' ');
      else delete fresh[k];
      boardCache = fresh;
      return fetch(BOARD_URL, {{method:'POST', headers:{{'Content-Type':'text/plain;charset=UTF-8'}},
                              body: JSON.stringify({{action:'saveBoard', key: BOARD_KEY, board: fresh}}),
                              redirect:'follow'}}).then(function (r) {{ return r.json(); }});
    }});
  }}
  var boxes = Array.prototype.slice.call(document.querySelectorAll('input[data-k]'));
  readBoard().then(function (j) {{
    boardCache = (j && j.ok && j.board) ? j.board : {{}};
    boxes.forEach(function (b) {{
      var when = boardCache[b.dataset.k];
      if (!when) return;
      b.checked = true;
      b.closest('tr').classList.add('done');
      b.title = '체크 ' + when;
    }});
  }}).catch(function (e) {{ console.warn('[목차] 체크 보드 읽기 실패', e && e.message); }});
  // ── 담당 지정 (GM 2026-09-10 "SSOT 등록건은 담당자도 설정할 수 있어야해") ──────────────
  //   저장 자리 = 같은 공용 보드의 다른 키(MGR_TASK_OWNER). 체크와 같은 방식이라 새 저장소가 없다.
  //   다음 갱신(manager_task_index.py)이 이 값을 읽어 원장 담당 빈칸을 채우고 사람별 표로 옮긴다.
  //   칸은 <select> 다(GM 2026-09-11 "드랍다운 항목에 넣어달라고 했는데") — 종전 datalist 는
  //   칸에 이름이 이미 있으면 목록이 안 펼쳐져 드롭다운으로 보이지 않았다. 후보 14명은
  //   파이썬(OWNER_CHOICES)이 서버에서 찍는다.
  var OWNER_KEY = 'MGR_TASK_OWNER';
  function readOwnerBoard() {{
    var gas = function () {{
      return fetch(BOARD_URL + '?action=board&key=' + OWNER_KEY, {{cache:'no-store'}})
        .then(function (r) {{ return r.json(); }});
    }};
    if (!ERP_API_ON) return gas();
    return fetch('/api/board/' + OWNER_KEY, {{cache:'no-store'}})
      .then(function (r) {{ if (!r.ok) throw new Error('api ' + r.status); return r.json(); }})
      .catch(gas);
  }}
  var owns = Array.prototype.slice.call(document.querySelectorAll('select[data-o]'));
  readOwnerBoard().then(function (j) {{
    var b = (j && j.ok && j.board) ? j.board : {{}};
    owns.forEach(function (inp) {{
      var v = b['mgr-' + inp.dataset.o];
      if (!v || inp.value) return;             // 원장에 이미 사람이 있으면 그 값을 덮지 않는다
      if (!inp.querySelector('option[value="' + v.replace(/"/g, '&quot;') + '"]')) {{
        var o = document.createElement('option'); o.value = v; o.textContent = v; inp.appendChild(o);
      }}
      inp.value = v;
      before[inp.dataset.o] = v;
    }});
  }}).catch(function (e) {{ console.warn('[목차] 담당 보드 읽기 실패', e && e.message); }});
  var before = {{}};
  owns.forEach(function (inp) {{ before[inp.dataset.o] = inp.value; }});
  owns.forEach(function (inp) {{
    inp.addEventListener('change', function () {{
      var v = inp.value.trim(), was = before[inp.dataset.o];
      if (v === was) return;
      inp.disabled = true;
      readOwnerBoard().then(function (j) {{
        var fresh = (j && j.ok && j.board) ? j.board : {{}};
        if (v) fresh['mgr-' + inp.dataset.o] = v; else delete fresh['mgr-' + inp.dataset.o];
        return fetch(BOARD_URL, {{method:'POST', headers:{{'Content-Type':'text/plain;charset=UTF-8'}},
                                body: JSON.stringify({{action:'saveBoard', key: OWNER_KEY, board: fresh}}),
                                redirect:'follow'}}).then(function (r) {{ return r.json(); }});
      }}).then(function (res) {{
        inp.disabled = false;
        if (res && res.ok) {{ before[inp.dataset.o] = v; inp.classList.add('saved');
                             setTimeout(function () {{ inp.classList.remove('saved'); }}, 1500); }}
        else {{ inp.value = was; alert('담당을 저장하지 못했습니다 — 잠시 뒤 다시 시도해 주세요.'); }}
      }}).catch(function () {{
        inp.disabled = false; inp.value = was;
        alert('담당을 저장하지 못했습니다 — 잠시 뒤 다시 시도해 주세요.');
      }});
    }});
  }});

  boxes.forEach(function (b) {{
    b.addEventListener('change', function () {{
      var on = b.checked;
      b.closest('tr').classList.toggle('done', on);
      b.disabled = true;
      saveCheck(b.dataset.k, on).then(function (res) {{
        b.disabled = false;
        if (!(res && res.ok)) {{ b.checked = !on; b.closest('tr').classList.toggle('done', !on);
                                alert('체크를 저장하지 못했습니다 — 잠시 뒤 다시 눌러 주세요.'); }}
      }}).catch(function () {{
        b.disabled = false; b.checked = !on; b.closest('tr').classList.toggle('done', !on);
        alert('체크를 저장하지 못했습니다 — 잠시 뒤 다시 눌러 주세요.');
      }});
    }});
  }});
</script>
</body>
</html>
'''


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="중간관리자 업무 목차 렌더")
    ap.add_argument("--clean-notes", action="store_true",
                    help="원장 note 에서 우리 발신 조각·똑같이 겹친 조각을 걷어낸다(원장을 고침)")
    ap.add_argument("--dry", action="store_true", help="--clean-notes 미리보기 — 파일은 안 고침")
    ap.add_argument("--selfcheck", action="store_true", help="판정 규칙 자가검사")
    args = ap.parse_args()
    if args.selfcheck:
        selfcheck()
    elif args.clean_notes:
        clean_notes(dry=args.dry)
    else:
        OUT.write_text(build(), encoding="utf-8")
        print(f"[manager_task_index] {OUT.relative_to(ROOT)} · {OUT.stat().st_size:,} bytes")
