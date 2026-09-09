# -*- coding: utf-8 -*-
"""상담 페이지 한 벌을 테넌트 머리글로 갈아 끼운다 (배1002 AEO · 2026-09-09 시토).

  python render_counsel_page.py <템플릿.html> <tenants/2_dietcamp.json> <낼 파일.html>

왜 필요한가 — 세 테넌트가 파일 하나를 나눠 쓴다. 크롤러는 자바스크립트를 안 돌리므로 제목·소개가
정적 HTML 에 있어야 하는데, 그 값은 테넌트마다 다르다. 그래서 표시(<!--SEO:start-->·<!--H1-->·
<!--GREET-->) 안쪽만 프로필의 seo 로 바꾼다.

★프로필에 seo 가 없으면 중립문을 넣는다 — 템플릿에 남아 있는 웰페리온 문구가 다캠 페이지에
그대로 실리는 사고를 구조로 막는다(값이 없을 때 조용히 남의 이름을 다는 쪽이 훨씬 나쁘다).

자체점검: python render_counsel_page.py --selftest
"""
import io
import json
import re
import sys

NEUTRAL = {"title": "상담", "description": "", "canonical": "",
           "h1": "상담", "greet": "궁금한 것을 편하게 물어보세요."}


def render(html, seo):
    s = dict(NEUTRAL)
    s.update({k: v for k, v in (seo or {}).items() if v})
    head = ["<title>%s</title>" % s["title"]]
    if s["description"]:
        head.append('<meta name="description" content="%s">' % s["description"])
    if s["canonical"]:
        head.append('<link rel="canonical" href="%s">' % s["canonical"])
    html = re.sub(r"<!--SEO:start.*?<!--SEO:end-->", "\n".join(head), html, count=1, flags=re.S)
    html = re.sub(r"<!--H1-->.*?<!--/H1-->", s["h1"], html, count=1, flags=re.S)
    html = re.sub(r"<!--GREET-->.*?<!--/GREET-->", s["greet"], html, count=1, flags=re.S)
    return html


def _selftest():
    tpl = ('<head><!--SEO:start 설명-->\n<title>가</title>\n<link rel="canonical" href="X">\n<!--SEO:end-->'
           '</head><h1><!--H1-->가<!--/H1--></h1><p><!--GREET-->나<!--/GREET--></p>')
    out = render(tpl, {"title": "다캠 상담", "h1": "다캠에 물어보세요"})
    assert "<title>다캠 상담</title>" in out, out
    assert "다캠에 물어보세요" in out
    assert "궁금한 것을 편하게" in out, "seo 에 없는 칸은 중립문으로 채워야 한다"
    assert "canonical" not in out, "빈 canonical 은 아예 안 낸다"
    assert "SEO:start" not in out and "<!--H1-->" not in out, "표시가 남으면 안 된다"
    bare = render(tpl, {})
    assert "<title>상담</title>" in bare and "가" not in bare, "seo 가 없으면 템플릿 값이 남으면 안 된다"
    print("자체점검 통과")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        raise SystemExit(0)
    tpl_p, prof_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    prof = json.load(io.open(prof_p, encoding="utf-8"))
    html = render(io.open(tpl_p, encoding="utf-8").read(), prof.get("seo"))
    io.open(out_p, "w", encoding="utf-8", newline="\n").write(html)
    print("%s → %s (제목 %s)" % (prof_p, out_p, (prof.get("seo") or {}).get("title") or "상담(중립)"))
