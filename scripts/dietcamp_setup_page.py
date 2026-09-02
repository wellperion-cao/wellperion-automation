"""다캠 셋업 3종 md → GM 열람용 html 1장 (정본은 md · 이 파일은 렌더)."""
import os, re, html
os.chdir(r'C:\Users\jjky0\welperion-automation')
BASE = '2. 브랜드_자료/10_다이어트캠프_브랜드가이드/'
SRC = [('01_브랜드가이드/다캠_브랜드가이드_v0.1.md', '브랜드가이드'),
       ('02_회사소개서/다캠_회사소개서_v0.1.md', '회사소개서'),
       ('03_전략_구상안/다캠_전략구상안_v0.1.md', '전략 구상안')]

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

secs = []
for path, name in SRC:
    secs.append((name, md2html(open(BASE + path, encoding='utf-8').read()), path))

nav = ''.join(f'<a href="#s{n}">{name}</a>' for n, (name, _, _) in enumerate(secs))
body = ''.join(f'<section id="s{n}"><div class="src">정본: 2. 브랜드_자료/10_다이어트캠프_브랜드가이드/{p}</div>{h}</section>'
               for n, (name, h, p) in enumerate(secs))
page = f'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>다캠 셋업 v0.1 — 브랜드가이드 · 회사소개서 · 전략 구상안</title>
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
@media (max-width:720px){{table{{display:block;overflow-x:auto}}h1{{font-size:20px}}}}
</style></head><body><div class="wrap">
<header><div class="brand">WELLPERION · AI CBO 시보</div><h1>다이어트캠프(다캠) 셋업 v0.1 — 브랜드가이드 · 회사소개서 · 전략 구상안</h1>
<div class="meta">2026-09-02 · 초안(GM 검토 전 · 대표님 회신 6개 수령 전) · 정본은 다캠 폴더의 md, 이 화면은 렌더 · 배 892</div></header>
<nav>{nav}</nav>
{body}
</div></body></html>'''
out = '3. 웰페리온 가이드/cbo/dietcamp/setup_v0.1.html'
open(out, 'w', encoding='utf-8').write(page)
print(out, len(page))
