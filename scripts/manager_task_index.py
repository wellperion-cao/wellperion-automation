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
"""
from __future__ import annotations

import html
import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "1. AI자료_아카이브" / "11_카카오톡" / "★운영부" / "_digest_ledger.json"
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


def row_html(no: int, seen_date: str, it: dict) -> str:
    age = days_since(seen_date)
    due = str(it.get("due") or "").strip() or "—"
    note = str(it.get("note") or "").strip()
    cn = cat_name(it)
    note_td = (f'<td class="note" title="{html.escape(note)}">{html.escape(short(note))}</td>'
               if note else '<td class="note">—</td>')
    return (f'<tr data-no="{no}"><td class="ck"><input type="checkbox" data-k="mgr-{no}"></td>'
            f'<td class="no">#{no}</td>'
            f'<td class="ti">{html.escape(str(it.get("issue") or ""))}'
            f'{f"<span class=cat>{html.escape(cn)}</span>" if cn else ""}</td>'
            f'<td class="due">{html.escape(due)}</td>'
            f'{note_td}'
            f'<td class="age {age_cls(age)}">{age}일</td></tr>')


HEAD_ROW = ('<tr><th class="ck">✓</th><th class="no">번호</th><th>업무</th>'
            '<th class="due">기한</th><th>최근 상황</th><th class="age">경과</th></tr>')


def table(rows: list[str], empty: str) -> str:
    body = "\n          ".join(rows) or f'<tr><td colspan="6" class="empty">{empty}</td></tr>'
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
<title>중간관리자 업무 목차 — 웰페리온 GM업무</title>
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
    <span class="b2">{html.escape(head)} · 담당 미정 {len(unassigned)}건</span></div>

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
  // 체크 상태는 이 브라우저에만 남긴다(GM 개인 체크용). 원장은 건드리지 않는다.
  document.querySelectorAll('input[data-k]').forEach(function (b) {{
    var k = b.dataset.k;
    try {{ b.checked = localStorage.getItem(k) === '1'; }} catch (e) {{}}
    if (b.checked) b.closest('tr').classList.add('done');
    b.addEventListener('change', function () {{
      try {{ localStorage.setItem(k, b.checked ? '1' : '0'); }} catch (e) {{}}
      b.closest('tr').classList.toggle('done', b.checked);
    }});
  }});
</script>
</body>
</html>
'''


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"[manager_task_index] {OUT.relative_to(ROOT)} · {OUT.stat().st_size:,} bytes")
