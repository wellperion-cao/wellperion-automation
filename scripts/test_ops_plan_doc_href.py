# -*- coding: utf-8 -*-
"""월간운영계획 목표의 자료 링크가 실제 파일을 가리키는지 확인한다.

monthly_ops_plan.json 의 doc / docs[].href 는 coo/chairman/GM업무.html 기준 상대경로다.
월간운영계획.html 은 가이드 루트에 있어 같은 값을 그대로 쓰면 저장소 밖으로 튄다 —
그 페이지의 resolveDocHref() 가 하는 정규화를 여기서 같은 규칙으로 재현해 대조한다.
(GM 지적 2026-09-05 "사우나 정비 클릭하면 이상한 데로 넘어간다")

    python scripts/test_ops_plan_doc_href.py [YYYY-MM ...]
"""
import json, os, posixpath, sys, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(ROOT, '3. 웰페리온 가이드')
PLAN = os.path.join(ROOT, 'status', 'monthly_ops_plan.json')


def resolve_doc_href(href):
    """월간운영계획.html resolveDocHref() 와 같은 규칙."""
    h = (href or '').strip()
    if not h or h[0] in '#/' or h.startswith(('http://', 'https://', '//')):
        return h
    return posixpath.normpath('coo/chairman/' + h)


def hrefs_of(obj):
    out = []
    if obj.get('doc'):
        out.append(obj['doc'])
    for d in (obj.get('docs') or []):
        h = d if isinstance(d, str) else (d or {}).get('href')
        if h:
            out.append(h)
    return out


def check(months=None):
    plan = json.load(open(PLAN, encoding='utf-8'))
    bad = []
    checked = 0
    for mk, m in plan.get('months', {}).items():
        if months and mk not in months:
            continue
        for o in (m.get('objectives') or []):
            for h in hrefs_of(o):
                r = resolve_doc_href(h)
                if r.startswith(('http', '//')) or not r:
                    continue
                checked += 1
                rel = urllib.parse.unquote(r.split('#')[0].split('?')[0])
                path = os.path.join(GUIDE, rel.replace('/', os.sep))
                if not os.path.exists(path):
                    bad.append((mk, o.get('id'), h, r))
    return checked, bad


if __name__ == '__main__':
    n, bad = check(sys.argv[1:] or None)
    for mk, oid, h, r in bad:
        print('X %s %s | %s -> %s (없는 파일)' % (mk, oid, h, r))
    print('로컬 자료 링크 %d건 · 깨진 링크 %d건' % (n, len(bad)))
    assert not bad, '깨진 자료 링크 %d건' % len(bad)
