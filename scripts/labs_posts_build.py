#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""labs_posts_build.py — 「피트니스 AX」 첫 글 3편(시모 정본 md · 배 12691)을 공개 사이트 /labs/posts.html 한 장으로 (시보 · 배 11386).

원고 정본 = 2. 브랜드_자료/12_AX랩스/채널/글_*.md 의 「## 네이버 블로그 (본문)」 절만(제목 줄 + 문단). 채널판(스레드·인스타·카톡)은 안 싣는다.
출력 = 3. 웰페리온 가이드/erp/admin/labs_posts.html (deploy_labs.sh 가 /labs/posts.html 로 올린다). 글이 늘면 이 파일을 다시 돌린다.
  C:/Python314/python.exe scripts/labs_posts_build.py
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "2. 브랜드_자료" / "12_AX랩스" / "채널"
OUT = ROOT / "3. 웰페리온 가이드" / "erp" / "admin" / "labs_posts.html"
AXIS = {"글_01_왜": "왜", "글_02_어떻게": "어떻게", "글_03_언제부터": "언제부터"}


def parse(md: str) -> tuple[str, list[str]]:
    body = md.split("## 네이버 블로그 (본문)", 1)[1]
    body = re.split(r"\n## ", body, 1)[0]
    title = re.search(r"^제목:\s*(.+)$", body, re.M).group(1).strip()
    paras = [p.strip() for p in body.split("제목:", 1)[1].split("\n", 1)[1].split("\n\n") if p.strip() and not p.strip().startswith("<!--")]
    return title, paras


def build() -> str:
    posts = []
    for stem, axis in AXIS.items():
        p = SRC / f"{stem}.md"
        if not p.exists():
            continue
        title, paras = parse(p.read_text(encoding="utf-8"))
        posts.append((axis, title, paras))
    arts = "\n".join(
        f'<article id="p{i}"><span class="axis">{html.escape(axis)}</span><h2>{html.escape(title)}</h2>' +
        "".join(f"<p>{html.escape(q)}</p>" for q in paras) + "</article>"
        for i, (axis, title, paras) in enumerate(posts, 1))
    toc = " · ".join(f'<a href="#p{i}">{html.escape(axis)} — {html.escape(title)}</a>' for i, (axis, title, _) in enumerate(posts, 1))
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>피트니스 AX — 첫 글 3편</title>
<link rel="icon" href="axlabs_favicon.svg">
<link rel="stylesheet" href="platform_brand.css">
<style>
/* 「피트니스 AX」 채널 글 자리(/labs/posts.html) — 원고 정본은 2. 브랜드_자료/12_AX랩스/채널/*.md(시모) · 이 파일은 scripts/labs_posts_build.py 가 만든다. 손으로 고치지 않는다. */
body{{margin:0;background:var(--pf-bg,#F6FBFA);color:var(--pf-ink,#14302C);font-family:var(--pf-body,'Pretendard',system-ui,sans-serif);line-height:1.75}}
.wrap{{max-width:760px;margin:0 auto;padding:40px 20px 72px}}
h1{{font-family:var(--pf-head,inherit);font-size:26px;margin:0 0 6px}}
.meta{{color:var(--pf-soft,#5E7A75);font-size:14px;margin-bottom:18px}}
.toc{{font-size:14px;line-height:1.9;margin-bottom:28px}}
.toc a{{color:var(--pf-pri-dk,#0B6B62);text-decoration:none;min-height:44px;display:inline-block}}
article{{background:#fff;border:1px solid var(--pf-line,#D7E7E3);border-radius:12px;padding:26px 24px;margin-bottom:18px}}
article h2{{font-family:var(--pf-head,inherit);font-size:21px;margin:6px 0 14px;letter-spacing:-.01em}}
article p{{margin:0 0 12px;font-size:16px}}
.axis{{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.08em;color:var(--pf-pri-dk,#0B6B62);background:var(--pf-tint,#E3F3F0);border-radius:999px;padding:2px 10px}}
.back{{display:inline-block;margin-top:10px;color:var(--pf-pri-dk,#0B6B62);min-height:44px;line-height:44px}}
@media(prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important}}}}
</style>
</head>
<body>
<div class="wrap">
<h1>피트니스 AX — 첫 글 3편</h1>
<div class="meta">웰페리온 AX 랩스 · 매일 한 편: 왜 · 어떻게 · 언제부터 · 실제로 돈 것만 적습니다 · {datetime.now().strftime('%Y-%m-%d')}</div>
<div class="toc">{toc}</div>
{arts}
<a class="back" href="./">← 첫 화면</a>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print("ok", OUT, OUT.stat().st_size, "bytes")
