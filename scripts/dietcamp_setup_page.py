"""다캠 셋업 md → html 렌더 (정본은 md).
  기본 = GM 열람용 setup_v0.1.html (4종 md 전문 · 내부 표기 그대로)
  --partner = 대표님용 drafts_v0.1.html — 표지 허브(회사소개서·브랜드가이드·운영전략 3장 페이지 카드 + FAQ·상담봇 카드).
              3장 페이지 자체(intro.html·brand.html·strategy.html)는 정적 파일 — 이 스크립트는 손대지 않는다.
"""
import sys
PARTNER = "--partner" in sys.argv
import os, re, html
import datetime as _dt
_TODAY = _dt.date.today().strftime('%Y. %m. %d.')
os.chdir(r'C:\Users\jjky0\welperion-automation')
BASE = '2. 브랜드_자료/10_다이어트캠프_브랜드가이드/'
SRC = [('01_브랜드가이드/다캠_브랜드가이드_v0.1.md', '브랜드가이드'),
       ('02_회사소개서/다캠_회사소개서_v0.1.md', '회사소개서'),
       ('03_전략_구상안/다캠_전략구상안_v0.1.md', '운영전략'),
       ('06_현장업무_자동화/자동화_후보.md', '현장업무 자동화')]

def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1" loading="lazy">', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
    return s

def md2html(text):
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith('|') and i + 1 < len(lines) and re.match(r'^\|[\s:|-]+\|$', lines[i + 1]):
            hdr = [c.strip() for c in ln.strip('|').split('|')]
            out.append('<table><thead><tr>' + ''.join(f'<th>{inline(c)}</th>' for c in hdr) + '</tr></thead><tbody>')
            i += 2
            while i < len(lines) and lines[i].startswith('|'):
                cells = [c.strip() for c in lines[i].strip('|').split('|')]
                out.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in cells) + '</tr>')
                i += 1
            out.append('</tbody></table>')
            continue
        m = re.match(r'^(#{1,3})\s+(.*)', ln)
        if m:
            lv = len(m.group(1)) + 1
            out.append(f'<h{lv}>{inline(m.group(2))}</h{lv}>'); i += 1; continue
        if ln.startswith('> '):
            buf = []
            while i < len(lines) and lines[i].startswith('> '):
                buf.append(inline(lines[i][2:])); i += 1
            out.append('<blockquote>' + '<br>'.join(buf) + '</blockquote>'); continue
        if re.match(r'^(\d+)\.\s', ln) or ln.startswith('- '):
            tag = 'ol' if ln[0].isdigit() else 'ul'
            out.append(f'<{tag}>')
            while i < len(lines) and (re.match(r'^(\d+)\.\s', lines[i]) or lines[i].startswith('- ')):
                out.append('<li>' + inline(re.sub(r'^(\d+\.|-)\s', '', lines[i])) + '</li>'); i += 1
            out.append(f'</{tag}>'); continue
        if re.match(r'^!\[', ln):
            buf = []
            while i < len(lines) and re.match(r'^!\[', lines[i]):
                buf.append(inline(lines[i])); i += 1
            if len(buf) == 1:
                out.append(f'<p>{buf[0]}</p>')
            else:
                items = ''.join(f'<div class="pi">{x}</div>' for x in buf)
                out.append(f'<div class="photo-grid">{items}</div>')
            continue
        if ln.strip():
            out.append(f'<p>{inline(ln)}</p>')
        i += 1
    return '\n'.join(out)

PARTNER_SRC = SRC[:3]
FAQ_PATH = BASE + '07_FAQ/faq.json'
WIDGET = '<script src="/dietcamp/chat_widget.html" data-tenant="2_dietcamp" defer></script>'

def _ver(path):
    m = re.search(r'v(\d+\.\d+)', open(BASE + path, encoding='utf-8').readline())
    return m.group(1) if m else '0.1'

if PARTNER:
    HUB_CARDS = [
        ('intro.html', 'cover.jpg', '회사소개서', _ver(PARTNER_SRC[1][0]), '무거운 머신과 싸우지 마세요 — 30가지 도구, 300가지 프로그램'),
        ('brand.html', 'tools_01.jpg', '브랜드가이드', _ver(PARTNER_SRC[0][0]), 'Can · Need · Fun — 어떻게 말하고 어떤 색을 쓰는가'),
        ('strategy.html', 'space_03.jpg', '운영전략', _ver(PARTNER_SRC[2][0]), '운동을 그만두지 않게 한다 — 북극성 하나, 90일 계획'),
    ]
    hub_html = ''.join(
        f'<a class="hub-card" href="{href}"><img src="img/{img}" alt="{name}" loading="lazy">'
        f'<div class="hc-body"><div class="hc-name">{name}</div><div class="hc-ver">v{ver}</div>'
        f'<p>{blurb}</p><span class="hc-link">보기 →</span></div></a>'
        for href, img, name, ver, blurb in HUB_CARDS)
    faq_card = ('<div class="hub-card faq"><div class="hc-body"><div class="hc-name">FAQ · 상담봇</div>'
                '<p>궁금한 점은 이 화면 오른쪽 아래 「무엇이든 물어보세요」 창에 물어보세요 — 대표님 자료로만 답합니다.</p></div></div>')
    nav = ''
    body = f'<section class="hub-grid">{hub_html}{faq_card}</section>'
else:
    secs = []
    for path, name in SRC:
        raw = open(BASE + path, encoding='utf-8').read()
        secs.append((name, md2html(raw), path))

    import json as _json
    _faq = _json.load(open(FAQ_PATH, encoding='utf-8'))
    _rows = ''.join(f"<tr><td><b>{html.escape(f['q'])}</b></td><td>{html.escape(f['a'])}</td></tr>" for f in _faq['faq'])
    _faq_html = ('<h2>자주 묻는 질문 (FAQ) v0.1 — 상담봇이 이 답으로만 말합니다</h2>'
                 '<blockquote>' + f'정본 = {FAQ_PATH} · 서버 /srv/erp/faq/2_dietcamp/faq.json (같은 파일) · 답변 API /api/chat/2_dietcamp · 미답 = /api/chat/2_dietcamp/unanswered · 상담 예약 링크 = 미수령(meta.reservation_url 빈 값)' + '</blockquote>'
                 f'<table><thead><tr><th style="width:32%">질문</th><th>답</th></tr></thead><tbody>{_rows}</tbody></table>')
    secs.append(('FAQ · 상담봇', _faq_html, '07_FAQ/faq.json'))
    nav = ''.join(f'<a href="#s{n}">{name}</a>' for n, (name, _, _) in enumerate(secs))
    body = ''.join((f'<section id="s{n}"><div class="src">정본: 2. 브랜드_자료/10_다이어트캠프_브랜드가이드/{p}</div>{h}</section>')
                   for n, (name, h, p) in enumerate(secs))
HEAD_GM = """<header><div class="brand">WELLPERION · AI CBO 시보</div><h1>다이어트캠프(다캠) 셋업 v0.1 — 브랜드가이드 · 회사소개서 · 전략 구상안</h1>
<div class="meta">2026-09-02 · 초안(GM 검토 전 · 대표님 회신 수령 중) · 정본은 다캠 폴더의 md, 이 화면은 렌더 · 배 892</div>
<div class="meta">만들어 드리는 것 4가지 — ①브랜드가이드 ②회사소개서 ③운영전략 ④현장업무 자동화</div></header>"""
HEAD_PARTNER = """<header><div class="brand">WELLPERION · AI 브랜딩</div><h1>다이어트캠프 — 회사소개서 · 브랜드가이드 · 운영전략</h1>
<div class="meta">받는 분: 다이어트캠프 이승기 대표님 · 이대우 대표님 &nbsp;|&nbsp; 만든 이: 웰페리온 AI &nbsp;|&nbsp; """ + _TODAY + """</div></header>
<div class="lead"><b>이 초안은 기준점입니다. 방향은 대표님이 정하십니다.</b> v0.1 → v0.2 → v1.0 으로 계속 수정·보완합니다. 「미수령」은 아직 못 받은 것입니다.</div>"""
PAGE_TITLE = '다이어트캠프 — 회사소개서 · 브랜드가이드 · 운영전략' if PARTNER else '다캠 셋업 v0.1 — 브랜드가이드 · 회사소개서 · 전략 구상안'
page = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>{PAGE_TITLE}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--ink:#101418;--green:#4E7432;--green-bg:#EEF4E8;--line:#D8E4D2;--dim:#5C666F;--dark:#0B0B0D;--muted:#CBCCCA}}
body{{font-family:'Noto Sans KR',sans-serif;color:var(--ink);background:#F3F6F0;font-size:15px;line-height:1.7;word-break:keep-all;overflow-wrap:anywhere}}
.wrap{{max-width:1080px;margin:0 auto;background:#fff;box-shadow:0 2px 40px rgba(0,0,0,.08);min-height:100vh}}
header{{border-bottom:4px solid var(--green);padding:22px 32px 18px}}
.brand{{font-size:11px;letter-spacing:5px;color:var(--green);font-weight:700}}
h1{{font-size:24px;font-weight:900;margin-top:6px;color:var(--dark);line-height:1.3}}
.meta{{font-size:13px;color:var(--dim);margin-top:6px}}
.lead{{background:var(--dark);color:#fff;padding:16px 32px;font-size:15px;line-height:1.8}}
.lead b{{color:#9FD068}}
nav{{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);padding:10px 32px;display:flex;gap:8px;flex-wrap:wrap;z-index:5}}
nav a{{text-decoration:none;color:var(--dark);font-weight:700;font-size:13.5px;padding:5px 14px;border:1px solid var(--line);border-radius:20px}}
nav a:hover{{background:var(--green);color:#fff;border-color:var(--green)}}
section{{border:1px solid var(--line);border-top:4px solid var(--green);padding:22px 32px;margin:18px 24px;border-radius:0 0 4px 4px}}
.src{{font-size:12px;color:var(--dim);margin-bottom:8px}}
h2{{font-size:21px;font-weight:900;margin:4px 0 12px;color:var(--dark)}}
h3{{font-size:16px;color:var(--green);margin:22px 0 9px;padding-left:10px;border-left:4px solid var(--green);font-weight:700}}
h4{{font-size:15px;margin:14px 0 7px;font-weight:700}}
blockquote{{background:var(--green-bg);border-left:4px solid var(--green);padding:11px 16px;font-size:13.5px;color:#2D3B25;margin-bottom:12px;border-radius:0 4px 4px 0}}
table{{width:100%;border-collapse:collapse;margin:8px 0 14px;font-size:14px}}
th,td{{border:1px solid var(--line);padding:8px 11px;vertical-align:top;text-align:left}}
th{{background:var(--green-bg);color:var(--dark);font-size:13px;font-weight:700}}
ul,ol{{padding-left:24px;margin:7px 0 11px}} li{{margin-bottom:5px}}
p{{margin-bottom:9px}} code{{background:#EEF4E8;padding:2px 6px;border-radius:3px;font-size:13px;color:#2D4A1A}}
img{{max-width:100%;border-radius:6px;margin:6px 0;display:block}}
.photo-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px;margin:14px 0}}
.photo-grid .pi img{{width:100%;height:200px;object-fit:cover;border-radius:6px;display:block}}
.foot{{padding:16px 32px;font-size:13px;color:var(--dim);background:var(--green-bg);border-top:1px solid var(--line)}}
.hub-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:20px;border:none;margin:24px 24px;padding:0}}
.hub-card{{display:block;text-decoration:none;color:inherit;border:1px solid var(--line);border-top:4px solid var(--green);border-radius:0 0 4px 4px;overflow:hidden;background:#fff}}
.hub-card img{{width:100%;height:170px;object-fit:cover;border-radius:0;margin:0}}
.hub-card .hc-body{{padding:18px 20px}}
.hub-card .hc-name{{font-size:17px;font-weight:900;color:var(--dark)}}
.hub-card .hc-ver{{font-size:11px;color:var(--green);font-weight:700;margin-top:2px}}
.hub-card .hc-body p{{font-size:13.5px;color:var(--dim);margin-top:10px}}
.hub-card .hc-link{{display:inline-block;margin-top:10px;font-size:13px;font-weight:700;color:var(--green)}}
.hub-card.faq{{background:var(--green-bg)}}
@media (max-width:720px){{table{{display:block;overflow-x:auto}}h1{{font-size:20px}}section{{margin:12px 0;padding:16px 16px}}nav,header,.lead,.foot{{padding-left:16px;padding-right:16px}}.hub-grid{{grid-template-columns:1fr;margin:12px 0}}}}
</style></head><body><div class="wrap">
{HEAD_PARTNER if PARTNER else HEAD_GM}
{'' if PARTNER else f'<nav>{nav}</nav>'}
{body}
{'<div class="foot">비용·조건은 이 페이지에 없으며 별도로 말씀드립니다. 이 초안은 대표님 확인 뒤에만 밖으로 나갑니다. — 웰페리온 AI</div>' if PARTNER else ''}
{WIDGET if PARTNER else ''}
</div></body></html>"""
out = '3. 웰페리온 가이드/cbo/dietcamp/' + ('drafts_v0.1.html' if PARTNER else 'setup_v0.1.html')
open(out, 'w', encoding='utf-8').write(page)
print(out, len(page))
