"""다캠 셋업 3종 md → html 렌더 (정본은 md).
  기본 = GM 열람용 setup_v0.1.html (4종 · 내부 표기 그대로)
  --partner = 대표님용 drafts_v0.1.html (3종 · 결재선·웰페리온 벤치마크 절 제외 · 내부 이름 치환 · 다캠 라인으로 배포)
"""
import sys
PARTNER = "--partner" in sys.argv
import os, re, html
os.chdir(r'C:\Users\jjky0\welperion-automation')
BASE = '2. 브랜드_자료/10_다이어트캠프_브랜드가이드/'
SRC = [('01_브랜드가이드/다캠_브랜드가이드_v0.1.md', '브랜드가이드'),
       ('02_회사소개서/다캠_회사소개서_v0.1.md', '회사소개서'),
       ('03_전략_구상안/다캠_전략구상안_v0.1.md', '운영전략'),
       ('06_현장업무_자동화/자동화_후보.md', '현장업무 자동화')]

def inline(s):
    s = html.escape(s, quote=False)
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
        if ln.strip():
            out.append(f'<p>{inline(ln)}</p>')
        i += 1
    return '\n'.join(out)

PARTNER_SRC = SRC[:3]
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

nav = ''.join(f'<a href="#s{n}">{name}</a>' for n, (name, _, _) in enumerate(secs))
body = ''.join((f'<section id="s{n}">' + ('' if PARTNER else f'<div class="src">정본: 2. 브랜드_자료/10_다이어트캠프_브랜드가이드/{p}</div>') + f'{h}</section>')
               for n, (name, h, p) in enumerate(secs))
HEAD_GM = """<header><div class="brand">WELLPERION · AI CBO 시보</div><h1>다이어트캠프(다캠) 셋업 v0.1 — 브랜드가이드 · 회사소개서 · 전략 구상안</h1>
<div class="meta">2026-09-02 · 초안(GM 검토 전 · 대표님 회신 수령 중) · 정본은 다캠 폴더의 md, 이 화면은 렌더 · 배 892</div>
<div class="meta">만들어 드리는 것 4가지 — ①브랜드가이드 ②회사소개서 ③운영전략 ④현장업무 자동화</div></header>"""
HEAD_PARTNER = """<header><div class="brand">WELLPERION · AI 브랜딩</div><h1>다이어트캠프 — 초안 세 가지 (브랜드가이드 · 회사소개서 · 운영전략)</h1>
<div class="meta">받는 분: 다이어트캠프 이승기 대표님 · 이대우 대표님 &nbsp;|&nbsp; 만든 이: 웰페리온 AI &nbsp;|&nbsp; v0.1 · 2026. 09. 05.</div></header>
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
:root{{--ink:#101418;--navy:#14304E;--navy-bg:#EDF1F6;--line:#E3E7EB;--dim:#5C666F;--good:#146B4F}}
body{{font-family:'Noto Sans KR',sans-serif;color:var(--ink);background:#fff;font-size:15px;line-height:1.6;word-break:keep-all;overflow-wrap:anywhere}}
.wrap{{max-width:1180px;margin:0 auto;padding:24px 20px 60px}}
header{{border-bottom:3px solid var(--navy);padding-bottom:12px;margin-bottom:10px}}
.brand{{font-size:12px;letter-spacing:4px;color:var(--navy);font-weight:700}}
h1{{font-size:24px;font-weight:900;margin-top:4px}}
.meta{{font-size:13px;color:var(--dim);margin-top:4px}}
.lead{{background:var(--navy);color:#fff;padding:14px 18px;border-radius:6px;margin:12px 0 18px;font-size:15px;line-height:1.7}}
.lead b{{color:#FFD86B}}
nav{{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);padding:8px 0;margin-bottom:14px;display:flex;gap:8px;flex-wrap:wrap;z-index:5}}
nav a{{text-decoration:none;color:var(--navy);font-weight:700;font-size:14px;padding:5px 12px;border:1px solid var(--line);border-radius:4px}}
nav a:hover{{background:var(--navy-bg)}}
section{{border:1px solid var(--line);border-top:4px solid var(--navy);padding:18px 20px;margin-bottom:26px}}
.src{{font-size:12px;color:var(--dim);margin-bottom:6px}}
h2{{font-size:22px;font-weight:900;margin:4px 0 10px}}
h3{{font-size:17px;color:var(--navy);margin:20px 0 8px;padding-left:8px;border-left:4px solid var(--navy)}}
h4{{font-size:15px;margin:12px 0 6px}}
blockquote{{background:var(--navy-bg);border-left:4px solid var(--navy);padding:10px 14px;font-size:13.5px;color:#2B3A4A;margin-bottom:10px}}
table{{width:100%;border-collapse:collapse;margin:8px 0 12px;font-size:14px}}
th,td{{border:1px solid var(--line);padding:7px 10px;vertical-align:top;text-align:left}}
th{{background:var(--navy-bg);color:var(--navy);font-size:13px}}
ul,ol{{padding-left:22px;margin:6px 0 10px}} li{{margin-bottom:4px}}
p{{margin-bottom:8px}} code{{background:#F3F5F7;padding:1px 5px;border-radius:3px;font-size:13px}}
.foot{{margin-top:30px;border-top:1px solid var(--line);padding-top:12px;font-size:12.5px;color:var(--dim)}}
@media (max-width:720px){{table{{display:block;overflow-x:auto}}h1{{font-size:20px}}}}
</style></head><body><div class="wrap">
{HEAD_PARTNER if PARTNER else HEAD_GM}
<nav>{nav}</nav>
{body}
{'<div class="foot">비용·조건은 이 페이지에 없으며 별도로 말씀드립니다. 이 초안은 대표님 확인 뒤에만 밖으로 나갑니다. — 웰페리온 AI</div>' if PARTNER else ''}
</div></body></html>"""
out = '3. 웰페리온 가이드/cbo/dietcamp/' + ('drafts_v0.1.html' if PARTNER else 'setup_v0.1.html')
open(out, 'w', encoding='utf-8').write(page)
print(out, len(page))
