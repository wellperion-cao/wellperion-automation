# -*- coding: utf-8 -*-
"""중간관리자 3인 업무 목차 — GM 이 목차로 체크하는 한 장.

만드는 이유(GM 지시 2026-09-09): "실장님에게 목차 리스트를 줘서 내가 업무를 체크하는게 훨씬 효율적"
새 원장을 만들지 않는다(약속 L21) — 이미 매일 쌓이는 `_digest_ledger.json` 의 번호(no) 건을 사람별로 갈라 렌더할 뿐이다.
GM 이 화면에서 체크한 것은 그 브라우저에만 남는다(localStorage) — 원장 상태는 실무진 회신으로만 바뀐다.

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


def row_html(no: int, seen_date: str, it: dict) -> str:
    age = days_since(seen_date)
    age_cls = "old" if age >= 5 else ("warn" if age >= 3 else "")
    due = str(it.get("due") or "").strip() or "—"
    note = str(it.get("note") or "").strip() or "—"
    cat = CAT.get(str(it.get("category") or ""), "")
    return (f'<tr data-no="{no}"><td class="ck"><input type="checkbox" data-k="mgr-{no}"></td>'
            f'<td class="no">#{no}</td>'
            f'<td class="ti">{html.escape(str(it.get("issue") or ""))}'
            f'{f"<span class=cat>{html.escape(cat)}</span>" if cat else ""}</td>'
            f'<td class="due">{html.escape(due)}</td>'
            f'<td class="note">{html.escape(note)}</td>'
            f'<td class="age {age_cls}">{age}일</td></tr>')


def build() -> str:
    seen = latest_by_no()
    opens = {n: v for n, v in seen.items() if str(v[1].get("status", "")).lower() not in DONE}
    blocks = []
    counts = []
    for name, dept, room in MANAGERS:
        mine = sorted(((n, d, it) for n, (d, it) in opens.items()
                       if str(it.get("owner") or "").strip() == name), key=lambda x: x[0])
        counts.append((name, len(mine)))
        rows = "\n          ".join(row_html(n, d, it) for n, d, it in mine) or \
            '<tr><td colspan="6" class="empty">열린 건 없음</td></tr>'
        blocks.append(f'''      <div class="blk">
        <h2>{html.escape(name)} <span class="sub">{html.escape(dept)} · {html.escape(room)} · 열린 건 {len(mine)}건</span></h2>
        <table>
          <tr><th class="ck">✓</th><th class="no">번호</th><th>업무</th><th class="due">기한</th><th>최근 상황</th><th class="age">경과</th></tr>
          {rows}
        </table>
      </div>''')

    unassigned = sorted(((n, d, it) for n, (d, it) in opens.items()
                         if not str(it.get("owner") or "").strip()), key=lambda x: x[0])
    un_rows = "\n          ".join(row_html(n, d, it) for n, d, it in unassigned) or \
        '<tr><td colspan="6" class="empty">없음</td></tr>'
    blocks.append(f'''      <div class="blk">
        <h2>담당 미정 <span class="sub">GM 이 세 사람 중 누구 몫인지 정하면 그 사람 목차로 옮긴다 · {len(unassigned)}건</span></h2>
        <table>
          <tr><th class="ck">✓</th><th class="no">번호</th><th>업무</th><th class="due">기한</th><th>최근 상황</th><th class="age">경과</th></tr>
          {un_rows}
        </table>
      </div>''')

    head = " · ".join(f"{n} {c}건" for n, c in counts)
    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>중간관리자 업무 목차 — 웰페리온 GM업무</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  :root {{ --ink:#101418; --navy:#14304E; --navy-bg:#EDF1F6; --line:#E3E7EB; --dim:#6B7683; --warn:#96601A; --bad:#9E2A2A; }}
  body {{ font-family:'Noto Sans KR',sans-serif; color:var(--ink); background:#F4F6F8; padding:22px 18px 60px; }}
  .wrap {{ max-width:1180px; margin:0 auto; }}
  h1 {{ font-family:'Noto Serif KR',serif; font-size:27px; letter-spacing:-.6px; }}
  .lede {{ margin-top:6px; color:var(--dim); font-size:14px; line-height:1.7; }}
  .bar {{ margin-top:14px; background:var(--navy); color:#fff; padding:10px 14px; font-size:14px; font-weight:700; }}
  .blk {{ background:#fff; border:1px solid var(--line); margin-top:14px; }}
  h2 {{ font-size:16px; padding:10px 14px; background:var(--navy-bg); color:var(--navy); border-bottom:1px solid var(--line); }}
  h2 .sub {{ font-weight:400; color:var(--dim); font-size:13px; margin-left:8px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th, td {{ padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; text-align:left; }}
  th {{ background:#FAFBFC; font-size:12.5px; color:var(--dim); font-weight:700; }}
  td.ck, th.ck {{ width:34px; text-align:center; }}
  td.no, th.no {{ width:62px; color:var(--dim); font-weight:700; }}
  td.due, th.due {{ width:104px; }}
  td.age, th.age {{ width:64px; text-align:right; color:var(--dim); }}
  td.age.warn {{ color:var(--warn); font-weight:700; }}
  td.age.old {{ color:var(--bad); font-weight:700; }}
  td.note {{ color:var(--dim); }}
  .cat {{ display:inline-block; margin-left:6px; font-size:11.5px; color:var(--dim); border:1px solid var(--line); padding:0 5px; }}
  tr.done td.ti {{ text-decoration:line-through; color:var(--dim); }}
  .empty {{ color:var(--dim); }}
  .foot {{ margin-top:16px; color:var(--dim); font-size:13px; line-height:1.8; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>중간관리자 업무 목차</h1>
  <div class="lede">이경연 실장 · 이정헌 소장 · 나우열M 세 사람의 <b>열린 업무</b>를 번호순으로 편 목차입니다.
    회신은 번호로 받습니다 — 「#번호 + 했다/진행중/언제」 한 줄.<br>
    체크는 GM 화면에만 남습니다(이 브라우저). 원장 상태는 실무진 회신이 오면 바뀝니다.</div>
  <div class="bar">기준 {date.today().isoformat()} · {html.escape(head)}</div>
{chr(10).join(blocks)}
  <div class="foot">
    자료 원천 = 아침 정리 원장(<code>_digest_ledger.json</code>) · 번호는 건마다 고정입니다.<br>
    갱신 = <code>python scripts/manager_task_index.py</code> — 아침 정리가 돈 뒤 다시 돌리면 최신이 됩니다.
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
