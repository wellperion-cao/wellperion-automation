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


def render(html, seo, tenant_id=None):
    """seo 표시를 갈아 끼우고, tenant_id 를 주면 <!--TENANT--> 표시도 그 업체 값으로 박는다.

    ★업체 박기(2026-09-10 GM 「파트너사 구분에 근본적으로 선 그어놔줘」) — 화면은 이 박힌 값과 주소 표가
    일치할 때만 상담을 연다. 그래서 사본을 만들 때 반드시 그 업체 값이 들어가야 하고, 안 들어가면
    그 페이지는 열리지 않는다(남의 업체 답을 내주느니 안 여는 쪽). 09-09 개명 사고의 재발 방지 자리다."""
    s = dict(NEUTRAL)
    s.update({k: v for k, v in (seo or {}).items() if v})
    if tenant_id:
        html = re.sub(r"<!--TENANT-->.*?<!--/TENANT-->", tenant_id, html, count=1, flags=re.S)
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

    # 업체 박기(2026-09-10) — 사본마다 그 업체 값이 들어가야 하고, 표시가 남으면 안 된다.
    t2 = 'var BAKED_TENANT = "<!--TENANT-->1_wellperion<!--/TENANT-->";'
    baked = render(t2, {}, "2_dietcamp")
    assert baked == 'var BAKED_TENANT = "2_dietcamp";', baked
    assert "<!--TENANT-->" not in baked, "표시가 남으면 화면이 업체 판정을 못 해 안 열린다"
    assert render(t2, {}) == t2, "업체 id 를 안 주면 템플릿 그대로 — 웰페리온 원본이 바뀌면 안 된다"

    # 실제 템플릿에 그 표시가 살아 있는지 — 표시를 지우면 사본이 전부 웰페리온으로 굳는다
    import os
    real = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "..", "3. 웰페리온 가이드", "counsel", "index.html")
    if os.path.exists(real):
        src = io.open(real, encoding="utf-8").read()
        assert "<!--TENANT-->" in src and "<!--/TENANT-->" in src, "상담 페이지에서 업체 표시가 사라졌다"
        # 표에 없는 주소가 특정 업체로 떨어지는 길이 되살아나면 안 된다(09-09 사고 자리 둘)
        assert '|| "1_wellperion"' not in src, "주소 표에 웰페리온 기본값이 되살아났다"
        assert 'searchParams.get("t")' not in src, "?t= 로 남의 업체를 여는 길이 되살아났다"
    print("자체점검 통과")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        raise SystemExit(0)
    tpl_p, prof_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    prof = json.load(io.open(prof_p, encoding="utf-8"))
    tid = ((prof.get("tenant") or {}).get("id") or "").strip()
    if not tid:
        raise SystemExit("업체 id 가 없다 — %s 의 tenant.id 를 채워라(사본에 업체를 못 박으면 그 페이지는 안 열린다)" % prof_p)
    html = render(io.open(tpl_p, encoding="utf-8").read(), prof.get("seo"), tid)
    if "<!--TENANT-->" in html:
        raise SystemExit("업체 표시를 못 갈아 끼웠다 — 템플릿의 <!--TENANT-->…<!--/TENANT--> 표시를 확인해라")
    io.open(out_p, "w", encoding="utf-8", newline="\n").write(html)
    print("%s → %s (업체 %s · 제목 %s)" % (prof_p, out_p, tid, (prof.get("seo") or {}).get("title") or "상담(중립)"))
