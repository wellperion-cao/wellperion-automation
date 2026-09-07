"""다캠 셋업 3종 md → html 렌더 (정본은 md).
  기본 = GM 열람용 setup_v0.1.html (4종 · 내부 표기 그대로)
  --partner = 대표님용 drafts_v0.1.html (3종 · 결재선·웰페리온 벤치마크 절 제외 · 내부 이름 치환 · 다캠 라인으로 배포)
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
PARTNER_DROP = {'03_전략_구상안/다캠_전략구상안_v0.1.md': ('## 6. ',)}   # 리스크·결재선 + 벤치마크(§6 이후 전부)
PARTNER_WORDS = [('GM 확정 전', '대표님 확정 전'), ('GM 검토 전', '대표님 확인 전'), ('AI 시보', '웰페리온 AI'), ('시보', '웰페리온 AI'), ('GM 지시', '웰페리온 요청'), ('GM 확정', '웰페리온 확정'),
                 ('GM 검토', '웰페리온 검토'), ('GM', '웰페리온'), ('시토', '웰페리온 AI'), ('웰리', '웰페리온 AI'), ('배 892', '')]

PARTNER_DROP_LINES = ('시보 내부', '> GM 2026-09-02', '시보가 손대는 자리')   # 대표님께 안 보이는 내부 줄

def partner_text(path, text):
    for mark in PARTNER_DROP.get(path, ()):
        i = text.find(chr(10) + mark)
        if i > 0: text = text[:i] + chr(10)
    text = chr(10).join(ln for ln in text.splitlines() if not any(k in ln for k in PARTNER_DROP_LINES))
    for a, b in PARTNER_WORDS: text = text.replace(a, b)
    return text

secs = []
for path, name in (PARTNER_SRC if PARTNER else SRC):
    raw = open(BASE + path, encoding='utf-8').read()
    if PARTNER: raw = partner_text(path, raw)
    secs.append((name, md2html(raw), path))

import json as _json
_faq = _json.load(open(FAQ_PATH, encoding='utf-8'))
_rows = ''.join(f"<tr><td><b>{html.escape(f['q'])}</b></td><td>{html.escape(f['a'])}</td></tr>" for f in _faq['faq'])
_faq_html = ('<h2>자주 묻는 질문 (FAQ) v0.1 — 상담봇이 이 답으로만 말합니다</h2>'
             '<blockquote>' + ('대표님 자료(설문·가격표·재활 솔루션)에 있는 내용만으로 적은 초안입니다. 이 페이지 오른쪽 아래 「무엇이든 물어보세요」 창이 바로 이 FAQ 로 답합니다 — 여기에 없는 질문에는 지어내지 않고 "상담 예약" 으로 안내합니다. 틀린 답, 빠진 질문을 짚어 주시면 그 자리에서 고칩니다. 금액은 넣지 않았습니다(상담 시 가격표).' if PARTNER else
                               f'정본 = {FAQ_PATH} · 서버 /srv/erp/faq/2_dietcamp/faq.json (같은 파일) · 답변 API /api/chat/2_dietcamp · 미답 = /api/chat/2_dietcamp/unanswered · 상담 예약 링크 = 미수령(meta.reservation_url 빈 값)') + '</blockquote>'
             f'<table><thead><tr><th style="width:32%">질문</th><th>답</th></tr></thead><tbody>{_rows}</tbody></table>')
secs.append(('FAQ · 상담봇', _faq_html, '07_FAQ/faq.json'))
nav = ''.join(f'<a href="#s{n}">{name}</a>' for n, (name, _, _) in enumerate(secs))
body = ''.join((f'<section id="s{n}">' + ('' if PARTNER else f'<div class="src">정본: 2. 브랜드_자료/10_다이어트캠프_브랜드가이드/{p}</div>') + f'{h}</section>')
               for n, (name, h, p) in enumerate(secs))
HEAD_GM = """<header><div class="brand">WELLPERION · AI CBO 시보</div><h1>다이어트캠프(다캠) 셋업 v0.1 — 브랜드가이드 · 회사소개서 · 전략 구상안</h1>
<div class="meta">2026-09-02 · 초안(GM 검토 전 · 대표님 회신 수령 중) · 정본은 다캠 폴더의 md, 이 화면은 렌더 · 배 892</div>
<div class="meta">만들어 드리는 것 4가지 — ①브랜드가이드 ②회사소개서 ③운영전략 ④현장업무 자동화</div></header>"""
HEAD_PARTNER = """<header><div class="brand">WELLPERION · AI 브랜딩</div><h1>다이어트캠프 — 초안 세 가지 (브랜드가이드 · 회사소개서 · 운영전략)</h1>
<div class="meta">받는 분: 다이어트캠프 이승기 대표님 · 이대우 대표님 &nbsp;|&nbsp; 만든 이: 웰페리온 AI &nbsp;|&nbsp; v0.2 · """ + _TODAY + """</div></header>
<div class="lead"><b>이 초안은 기준점입니다. 방향은 대표님이 정하십니다.</b><br>
저희가 대표님 자료와 답변만으로 먼저 적어 둔 것이라, 틀린 곳·다른 생각이 있는 곳이 당연히 있습니다. 그 줄을 짚어 주시면 그 자리에서 고칩니다.<br>
한 번에 완성하는 문서가 아니라 <b>v0.1 → v0.2 → v1.0</b>으로 대표님 말씀을 받아 계속 수정·보완하며 발전시켜 가는 문서입니다. 「미수령」은 아직 못 받은 것 — 지어내지 않고 비워 두었습니다.</div>"""
PAGE_TITLE = '다이어트캠프 — 초안 세 가지 (v0.1)' if PARTNER else '다캠 셋업 v0.1 — 브랜드가이드 · 회사소개서 · 전략 구상안'
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
@media (max-width:720px){{table{{display:block;overflow-x:auto}}h1{{font-size:20px}}section{{margin:12px 0;padding:16px 16px}}nav,header,.lead,.foot{{padding-left:16px;padding-right:16px}}}}
</style></head><body><div class="wrap">
{HEAD_PARTNER if PARTNER else HEAD_GM}
<nav>{nav}</nav>
{body}
{'<div class="foot">비용·조건은 이 페이지에 없으며 별도로 말씀드립니다. 이 초안은 대표님 확인 뒤에만 밖으로 나갑니다. — 웰페리온 AI</div>' if PARTNER else ''}
{WIDGET if PARTNER else ''}
</div></body></html>"""
out = '3. 웰페리온 가이드/cbo/dietcamp/' + ('drafts_v0.1.html' if PARTNER else 'setup_v0.1.html')
open(out, 'w', encoding='utf-8').write(page)
print(out, len(page))
