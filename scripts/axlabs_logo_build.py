# -*- coding: utf-8 -*-
"""AX 랩스 로고·파비콘 생성기 (배 12731 · GM 2026-09-17 「AX랩스 파비콘은? 로고는?」).

심볼 = 「AX 합자(合字)」 — A 의 오른쪽 다리가 X 의 한 획을 겸한다. 두 안(A/B)은 같은 심볼에 바탕만 다르다.
  A = 청록 정사각 타일 + 흰 글자(관리 화면·파비콘에 강함)
  B = 민트 원 + 청록 글자(문서·밝은 바탕에 부드러움)
글꼴 = Pretendard Bold(브랜드 가이드 · 2. 브랜드_자료/02_로고&워터마크&FONT/font) → 외곽선(path)으로 박아 어디서나 같게 보인다.
색 = erp/admin/platform_brand.css 토큰(--pf-pri #0E9488 · --pf-pri-dk #0A6E66 · --pf-tint #CFF5EE · --pf-ink #0F3D3A).

사용:
  .venv/Scripts/python.exe scripts/axlabs_logo_build.py --variant a            # 정본 자산 생성(덮어쓰기)
  .venv/Scripts/python.exe scripts/axlabs_logo_build.py --ab <out.png>         # A/B 비교 그림 한 장(GM 선택용)
산출(한 이름 덮어쓰기 · 판 번호 없음):
  1. AI자료_아카이브/08_로고&워터마크/_assets/logo/axlabs/  axlabs_symbol.svg · axlabs_logo.svg · axlabs_logo{,_white,_black}.png · axlabs_symbol.png · favicon-{16,32,180,256}.png · favicon.svg
  3. 웰페리온 가이드/erp/admin/                               axlabs_logo.svg · axlabs_logo_white.svg · axlabs_favicon.png(256) · axlabs_favicon.svg  (서버가 서빙하는 사본 · 위 정본에서 파생)
"""
import argparse, io, pathlib, sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

ROOT = pathlib.Path(__file__).resolve().parents[1]
FONT = ROOT / "2. 브랜드_자료" / "02_로고&워터마크&FONT" / "font" / "Pretendard-Bold.otf"
SSOT = ROOT / "1. AI자료_아카이브" / "08_로고&워터마크" / "_assets" / "logo" / "axlabs"
WEB = ROOT / "3. 웰페리온 가이드" / "erp" / "admin"

PRI, PRI_DK, TINT, INK, WHITE, BLACK = "#0E9488", "#0A6E66", "#CFF5EE", "#0F3D3A", "#FFFFFF", "#111111"

# ---------- 심볼(256×256) ----------
def mark_paths(letter, cross, sw=26):
    """A 합자 획(letter 색) + X 교차 획(cross 색). 좌표는 256 뷰박스."""
    a = (f'<path d="M40 200 L108 62 L176 200" fill="none" stroke="{letter}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
         f'<path d="M70 152 H120" fill="none" stroke="{letter}" stroke-width="{sw}" stroke-linecap="round"/>')
    x = f'<path d="M176 62 L108 200" fill="none" stroke="{cross}" stroke-width="{sw}" stroke-linecap="round"/>'
    # 교차점(142,131)에 작은 점 — 「자동화가 맞물리는 자리」
    dot = f'<circle cx="142" cy="131" r="{sw*0.42:.1f}" fill="{cross}"/>'
    return a + x + dot

def symbol_svg(variant, size=256):
    if variant == "a":
        bg = f'<rect width="256" height="256" rx="58" fill="{PRI}"/>'
        body = mark_paths(WHITE, TINT)
    else:
        bg = f'<circle cx="128" cy="128" r="128" fill="{TINT}"/>'
        body = mark_paths(PRI_DK, PRI)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="{size}" height="{size}" role="img" aria-label="AX LABS">'
            f'{bg}{body}</svg>')

# ---------- 워드마크(글꼴 → 외곽선) ----------
def text_path(text, size_px, x=0, y=0, tracking=0.02):
    f = TTFont(str(FONT)); gs = f.getGlyphSet(); cmap = f.getBestCmap(); upm = f["head"].unitsPerEm
    scale = size_px / upm; pen_out = []; cursor = x
    for ch in text:
        if ch == " ":
            cursor += size_px * 0.28; continue
        g = cmap[ord(ch)]; sp = SVGPathPen(gs)
        tp = TransformPen(sp, (scale, 0, 0, -scale, cursor, y))
        gs[g].draw(tp); pen_out.append(sp.getCommands())
        cursor += gs[g].width * scale + size_px * tracking
    return " ".join(pen_out), cursor - x

def logo_svg(variant, color=None, height=64):
    """가로 락업: 심볼(height) + 간격 + AX LABS 워드마크. color 지정 시 단색(흰/검) 판."""
    fs = height * 0.62
    d, w = text_path("AX LABS", fs, x=0, y=height * 0.72)
    gap = height * 0.28; total_w = height + gap + w
    if color is None:
        sym = symbol_svg(variant).split(">", 1)[1].rsplit("</svg>", 1)[0]
        text_fill = INK
    else:  # 단색: 심볼도 같은 색 한 톤(타일 대신 획만)
        sym = mark_paths(color, color)
        text_fill = color
    s = height / 256
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w:.0f} {height}" width="{total_w:.0f}" height="{height}" role="img" aria-label="AX LABS">'
            f'<g transform="scale({s:.5f})">{sym}</g>'
            f'<g transform="translate({height + gap:.1f},0)"><path d="{d}" fill="{text_fill}"/></g></svg>')

# ---------- PNG 렌더(Playwright) ----------
def render_pngs(jobs):
    """jobs = [(svg_text, out_path, width_px)] · 투명 배경."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(device_scale_factor=1)
        for svg, out, width in jobs:
            pg.set_content(f'<html><body style="margin:0;background:transparent">{svg}</body></html>')
            el = pg.locator("svg"); pg.evaluate("(w)=>{const s=document.querySelector('svg');const r=s.viewBox.baseVal;s.setAttribute('width',w);s.setAttribute('height',Math.round(w*r.height/r.width));}", width)
            el.screenshot(path=str(out), omit_background=True)
        b.close()

def build(variant):
    SSOT.mkdir(parents=True, exist_ok=True)
    sym = symbol_svg(variant); logo = logo_svg(variant)
    (SSOT / "axlabs_symbol.svg").write_text(sym, encoding="utf-8")
    (SSOT / "favicon.svg").write_text(sym, encoding="utf-8")
    (SSOT / "axlabs_logo.svg").write_text(logo, encoding="utf-8")
    (WEB / "axlabs_logo.svg").write_text(logo, encoding="utf-8")
    (WEB / "axlabs_logo_white.svg").write_text(logo_svg(variant, WHITE), encoding="utf-8")  # 어두운 머리띠(topbar)용
    (WEB / "axlabs_favicon.svg").write_text(sym, encoding="utf-8")
    jobs = [(logo, SSOT / "axlabs_logo.png", 1200),
            (logo_svg(variant, WHITE), SSOT / "axlabs_logo_white.png", 1200),
            (logo_svg(variant, BLACK), SSOT / "axlabs_logo_black.png", 1200),
            (sym, SSOT / "axlabs_symbol.png", 512)]
    for n in (16, 32, 180, 256):
        jobs.append((sym, SSOT / f"favicon-{n}.png", n))
    jobs.append((sym, WEB / "axlabs_favicon.png", 256))
    render_pngs(jobs)
    readme = SSOT / "_README.md"
    readme.write_text(
        "# AX 랩스(AX LABS) 로고 정본 — 웰페리온과 별개 회사(색·글꼴이 갈린다)\n\n"
        "- 심볼 = AX 합자(A 오른 다리 = X 한 획) · 색 = erp/admin/platform_brand.css 토큰 · 글꼴 = Pretendard Bold 외곽선\n"
        "- axlabs_logo.svg(가로) · axlabs_symbol.svg(정사각) · png 3색(컬러·흰·검) · favicon-16/32/180/256.png · favicon.svg\n"
        "- 서버가 서빙하는 사본 = 3. 웰페리온 가이드/erp/admin/axlabs_logo.svg · axlabs_logo_white.svg · axlabs_favicon.png · axlabs_favicon.svg (이 폴더에서 파생 · 손으로 고치지 않는다)\n"
        "- 생성기 = scripts/axlabs_logo_build.py --variant a (판 번호 없음 · 한 이름 덮어쓰기 · GM 이 B 를 고르면 --variant b 로 다시 돌린다)\n"
        f"- 현재 판 = {variant.upper()} · 2026-09-17 시모\n", encoding="utf-8")
    print("built", variant, "->", SSOT, "|", WEB)

# ---------- A/B 비교 그림 ----------
def ab_image(out):
    from playwright.sync_api import sync_playwright
    def block(v, name, desc):
        return f'''
        <section><h2>{name} <small>{desc}</small></h2>
          <div class="row"><div class="cell white">{logo_svg(v, height=56)}</div>
            <div class="cell teal">{logo_svg(v, WHITE, height=56)}</div>
            <div class="cell dark">{logo_svg(v, WHITE, height=56)}</div></div>
          <div class="row">
            <div class="cell white topbar"><div class="tb">{logo_svg(v, height=26)}<span>센터 자동화 운영 플랫폼</span></div></div>
            <div class="cell white tab"><div class="t">{symbol_svg(v, 16)}<span>AX 랩스 관리</span></div><div class="t">{symbol_svg(v, 16)}<span>회사 소개서</span></div></div>
            <div class="cell white icons">{symbol_svg(v, 180)}{symbol_svg(v, 64)}{symbol_svg(v, 32)}{symbol_svg(v, 16)}</div>
          </div></section>'''
    html = f'''<html><head><meta charset="utf-8"><style>
    body{{margin:0;padding:28px 32px;background:#F3FBF9;font-family:Pretendard,'Segoe UI',sans-serif;color:{INK};width:1180px}}
    h1{{font-size:22px;margin:0 0 6px}} .sub{{font-size:13px;color:#4F6B68;margin-bottom:18px}}
    h2{{font-size:17px;margin:14px 0 8px}} h2 small{{font-size:12px;font-weight:400;color:#4F6B68;margin-left:8px}}
    .row{{display:flex;gap:12px;margin-bottom:12px}} .cell{{flex:1;border-radius:12px;padding:18px;display:flex;align-items:center;justify-content:center;min-height:96px;border:1px solid #BFE6DF}}
    .white{{background:#fff}} .teal{{background:{PRI}}} .dark{{background:#0F3D3A}}
    .topbar .tb{{display:flex;align-items:center;gap:10px;width:100%;padding:8px 12px;border-bottom:1px solid #BFE6DF;font-size:12px;color:#4F6B68}}
    .tab{{flex-direction:column;align-items:flex-start;gap:6px}} .tab .t{{display:flex;align-items:center;gap:8px;background:#E8F6F3;border-radius:8px 8px 0 0;padding:6px 12px;font-size:12px}}
    .icons{{gap:18px}}
    </style></head><body>
    <h1>AX 랩스 로고 A / B</h1><div class="sub">같은 심볼(AX 합자 — A 의 오른 다리가 X 의 한 획) · 바탕만 다르다 · 왼쪽부터 흰 바탕·청록 바탕·어두운 바탕 / 관리 화면 머리·브라우저 탭·파비콘 4크기</div>
    {block("a", "A 청록 타일", "정사각 타일 + 흰 글자 · 파비콘·관리 화면에 또렷 (시모 권고)")}
    {block("b", "B 민트 원", "밝은 원 + 청록 글자 · 문서·소개서에 부드러움")}
    </body></html>'''
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1244, "height": 900}, device_scale_factor=2)
        pg.set_content(html); pg.wait_for_timeout(300); pg.screenshot(path=str(out), full_page=True); b.close()
    print("ab ->", out)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--variant", choices=["a", "b"]); ap.add_argument("--ab")
    a = ap.parse_args()
    if a.variant: build(a.variant)
    if a.ab: ab_image(pathlib.Path(a.ab))
    if not a.variant and not a.ab: ap.error("--variant a|b 또는 --ab <png>")
