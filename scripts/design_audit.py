"""화면 디자인 검수기 — 디자인 규칙집(UI/UX Pro Max · ~/.claude/skills/ui-ux-pro-max) 중
순수 HTML 화면에 적용되는 규칙만 골라 헤드리스로 잰다. 시모(CMO) 소관.

왜 있나: 2026-09-15 새 홈 검수 때 초점 표시·이모지 아이콘·srcset·버튼 커서를 시토가 숫자로 짚어 준 뒤에야
고쳤다. 화면을 눈으로 열어서는 안 보이는 종류라, 만들 때마다 같은 잣대로 먼저 재는 도구가 필요하다.
색·글꼴은 재지 않는다 — 그건 canon(ssot/canon_values.json · brand_constants.py)이 정한다.

사용:
  .venv/Scripts/python.exe scripts/design_audit.py "<html 경로 또는 URL>" [--json]
  (여러 장: 경로를 나열)
출력: 항목 | 값 | 판정(✅/⚠️) 마크다운 표 한 장. exit 0 = 전부 통과, 1 = ⚠️ 있음.
  --json : 화면마다 {"path","warn":[걸린 항목 이름]} 한 줄(JSON Lines) — scripts/ui_standard_check.py --ux 가 읽는다.
"""
import json
import pathlib
import re
import sys
from urllib.parse import unquote

from playwright.sync_api import sync_playwright

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")

# 브라우저 안에서 재는 것 — 규칙집 ux-guidelines · web-interface 항목 번호를 주석에 둔다.
JS = r"""
(() => {
  const out = {};
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  // 반응형: viewport meta · 확대 금지 안티패턴(web-interface 27)
  const vp = document.querySelector('meta[name=viewport]');
  out.viewport = vp ? vp.content : '';
  // 본문 글자 16px(ux 'Readable Font Size')
  out.bodyFont = parseFloat(getComputedStyle(document.body).fontSize);
  // 가로 넘침(ux 'Horizontal Scroll')
  out.overflowX = document.documentElement.scrollWidth - innerWidth;
  // 터치 44px(ux 'Touch Friendly') — 보이는 링크·버튼만
  out.smallTargets = [...document.querySelectorAll('a[href],button,[role=button]')]
    .filter(vis).filter(e => { const r = e.getBoundingClientRect(); return r.width < 44 || r.height < 44; })
    .map(e => (e.getAttribute('aria-label') || e.textContent.trim() || e.className || e.tagName).slice(0, 18));
  // 버튼 커서(ux 'cursor-pointer')
  out.btnNoPointer = [...document.querySelectorAll('button,[role=button]')].filter(vis).filter(e => !e.disabled)
    .filter(e => getComputedStyle(e).cursor !== 'pointer').length;
  // 아이콘만 있는 버튼에 aria-label(web-interface 1)
  out.iconBtnNoLabel = [...document.querySelectorAll('button,a[href]')].filter(vis)
    .filter(e => !e.textContent.trim() && !e.getAttribute('aria-label') && !e.querySelector('img[alt]')).length;
  // 사진: alt · lazy · srcset(ux 'Image Optimization')
  const imgs = [...document.querySelectorAll('img')].filter(vis);
  out.imgTotal = imgs.length;
  out.imgNoAlt = imgs.filter(i => !i.hasAttribute('alt')).length;
  out.imgBigNoSrcset = imgs.filter(i => i.naturalWidth > 800 && !i.srcset).length;
  out.imgBelowFoldNoLazy = imgs.filter(i => i.getBoundingClientRect().top > innerHeight && i.loading !== 'lazy').length;
  // 초점 표시(web-interface 7·8): 첫 5개 초점 대상에 Tab 을 보내 outline 이 보이는지
  out.focusChecked = 0; out.focusNone = 0;
  // (Tab 은 파이썬 쪽에서 보낸다 — 여기선 자리만)
  // 활성 메뉴 표시(ux 'Active State') — 같은 페이지 앵커 메뉴가 있을 때만
  const anchors = [...document.querySelectorAll('nav a[href^="#"]')];
  out.navAnchors = anchors.length;
  out.navHasCurrent = !!document.querySelector('nav a[aria-current]');
  // 명암비 4.5:1(ux 'Color Contrast') — 뒤가 불투명 색인 글자만(사진 위 글자는 못 잰다 → 추정)
  const lum = c => { const m = c.match(/\d+(\.\d+)?/g); if (!m) return null; const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(+m[0]) + .7152 * f(+m[1]) + .0722 * f(+m[2]); };
  // 글자 뒤 배경색 — 조상 중 사진(img/video)이 글자 상자를 덮고 있으면 잴 수 없다(null)
  const covers = (a, b) => a.left <= b.left + 1 && a.top <= b.top + 1 && a.right >= b.right - 1 && a.bottom >= b.bottom - 1;
  // 반투명 배경(rgba … 0.1 칩·배지)은 아래 층과 섞어 실제 보이는 색으로 잰다 — 불투명으로 재면 과대 판정
  const rgba = c => { const m = c.match(/[\d.]+/g); return m ? [+m[0], +m[1], +m[2], m[3] == null ? 1 : +m[3]] : null; };
  const bgOf = (el, rc) => { const layers = []; while (el) { const cs = getComputedStyle(el); const c = cs.backgroundColor;
    if ([...el.querySelectorAll('img,video,iframe')].some(i => covers(i.getBoundingClientRect(), rc))) return null;
    const p = c && c !== 'transparent' ? rgba(c) : null;
    if (p && p[3] > 0) { layers.push(p); if (p[3] >= 1) break; }
    if (cs.backgroundImage !== 'none') return null; el = el.parentElement; }
    let b = layers.length && layers[layers.length - 1][3] >= 1 ? layers.pop() : [255, 255, 255, 1];
    for (let i = layers.length - 1; i >= 0; i--) { const [r, g, bl, a] = layers[i]; b = [r * a + b[0] * (1 - a), g * a + b[1] * (1 - a), bl * a + b[2] * (1 - a), 1]; }
    return 'rgb(' + b.slice(0, 3).map(Math.round).join(',') + ')'; };
  const low = new Map();
  document.querySelectorAll('p,a,span,li,h1,h2,h3,h4,figcaption,div,td,th,label,button').forEach(e => {
    if (!vis(e)) return;
    const own = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) return;
    const cs = getComputedStyle(e); if (+cs.opacity === 0) return;
    const bg = bgOf(e, e.getBoundingClientRect()); if (!bg) return;
    const L1 = lum(cs.color), L2 = lum(bg); if (L1 == null || L2 == null) return;
    const r = (Math.max(L1, L2) + .05) / (Math.min(L1, L2) + .05);
    const fs = parseFloat(cs.fontSize);
    const big = fs >= 24 || (fs >= 18.66 && +cs.fontWeight >= 700);
    if (r < (big ? 3 : 4.5)) low.set(cs.color + '|' + bg, (e.className || e.tagName).toString().slice(0, 14) + ' ' + r.toFixed(1));
  });
  out.lowContrast = [...low.values()];
  // 줄 길이 65~75자(typography 'line-length') — 문단만, 한글은 1em 폭이라 width/fontSize
  out.longLines = [...document.querySelectorAll('p')].filter(vis)
    .filter(p => { const cs = getComputedStyle(p); return p.getBoundingClientRect().width / parseFloat(cs.fontSize) > 75 && p.textContent.length > 120; }).length;
  out.cssLinks = [...document.querySelectorAll('link[rel=stylesheet]')].map(l => l.href);
  out.inlineCss = [...document.querySelectorAll('style')].map(t => t.textContent).join(' ');
  return out;
})()
"""


def audit(target: str, browser) -> dict:
    url = target if re.match(r"^https?://", target) else pathlib.Path(target).resolve().as_uri()
    res = {}
    for w in (400, 1400):
        pg = browser.new_page(viewport={"width": w, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(url, wait_until="load", timeout=60000)
        pg.wait_for_timeout(800)
        r = pg.evaluate(JS)
        # 초점: Tab 5번 — 초점 받은 요소의 outline 이 none 이면 안 보이는 것
        none = 0
        for _ in range(5):
            pg.keyboard.press("Tab")
            o = pg.evaluate("(()=>{const e=document.activeElement;if(!e||e===document.body)return null;const s=getComputedStyle(e);return s.outlineStyle==='none'&&s.boxShadow==='none'})()")
            if o is True:
                none += 1
        r["focusNone"] = none
        r["emoji"] = len(EMOJI.findall(pg.evaluate("document.body.innerText")))
        r["jsErrors"] = errs
        css = r["inlineCss"]
        for href in r["cssLinks"]:
            try:
                css += pg.request.get(href).text() if href.startswith("http") else pathlib.Path(unquote(href[8:] if href.startswith("file:///") else href)).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)   # 주석 속 예시(예: ":focus{outline:none}")를 세지 않는다
        r["reducedMotion"] = "prefers-reduced-motion" in css
        r["transitionAll"] = len(re.findall(r"transition\s*:\s*all", css))
        r["slowTransitions"] = sum(1 for d in re.findall(r"(?:transition|animation)[^;{}]*?(\d*\.?\d+)(m?s)", css) if float(d[0]) * (1 if d[1] == "ms" else 1000) > 1000)
        r["outlineNone"] = len(re.findall(r":focus(?!-visible)[^{}]*\{[^}]*outline\s*:\s*(?:none|0)", css))
        # 현재 위치 메뉴: 한 화면 내려가 본 뒤 잰다(맨 위에선 아직 안 붙는다)
        if r.get("navAnchors"):
            pg.evaluate("window.scrollBy(0, innerHeight * 1.5)"); pg.wait_for_timeout(700)
            r["navHasCurrent"] = pg.evaluate("!!document.querySelector('nav a[aria-current=\"true\"]')")
        res[w] = r
        pg.close()
    return res


def rows(res: dict):
    m, d = res[400], res[1400]
    ok = lambda c: "✅" if c else "⚠️"
    yield ("viewport meta", m["viewport"] or "없음", ok("width=device-width" in m["viewport"] and "user-scalable=no" not in m["viewport"]))
    yield ("본문 글자(폰)", f"{m['bodyFont']:.0f}px", ok(m["bodyFont"] >= 16))
    yield ("가로 넘침(폰)", f"{m['overflowX']}px", ok(m["overflowX"] <= 0))
    yield ("터치 44px 미만(폰)", f"{len(m['smallTargets'])}건 " + " · ".join(m["smallTargets"][:4]), ok(not m["smallTargets"]))
    yield ("버튼 커서 없음", f"{d['btnNoPointer']}건", ok(d["btnNoPointer"] == 0))
    yield ("아이콘 버튼 이름 없음", f"{d['iconBtnNoLabel']}건", ok(d["iconBtnNoLabel"] == 0))
    yield ("Tab 초점 안 보임(5회)", f"{d['focusNone']}회", ok(d["focusNone"] == 0))
    yield ("이모지 아이콘", f"{d['emoji']}개", ok(d["emoji"] == 0))
    yield ("사진 alt 없음", f"{d['imgNoAlt']}/{d['imgTotal']}", ok(d["imgNoAlt"] == 0))
    yield ("큰 사진 srcset 없음", f"{d['imgBigNoSrcset']}/{d['imgTotal']}", ok(d["imgBigNoSrcset"] == 0))
    yield ("아래쪽 사진 lazy 없음", f"{d['imgBelowFoldNoLazy']}건", ok(d["imgBelowFoldNoLazy"] == 0))
    if d["navAnchors"]:
        yield ("현재 위치 메뉴 표시", "있음" if d["navHasCurrent"] else "없음", ok(d["navHasCurrent"]))
    yield ("명암비 4.5 미만(추정·사진 위 제외)", f"{len(d['lowContrast'])}쌍 " + " · ".join(d["lowContrast"][:3]), ok(not d["lowContrast"]))
    yield ("긴 문단 75자 초과(PC)", f"{d['longLines']}개", ok(d["longLines"] == 0))
    yield ("1초 넘는 전환", f"{d['slowTransitions']}건", ok(d["slowTransitions"] == 0))
    yield ("transition: all", f"{d['transitionAll']}건", ok(d["transitionAll"] == 0))
    yield ("outline:none(초점 대체 없음)", f"{d['outlineNone']}건", ok(d["outlineNone"] == 0))
    yield ("움직임 줄이기 설정 존중", "있음" if d["reducedMotion"] else "없음", ok(d["reducedMotion"]))
    yield ("자바스크립트 오류", f"{len(d['jsErrors'])}건 " + " · ".join(e[:40] for e in d["jsErrors"][:2]), ok(not d["jsErrors"]))


def main(argv):
    as_json = "--json" in argv
    targets = [a for a in argv if not a.startswith("--")]
    if not targets:
        print(__doc__); return 2
    bad = 0
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for t in targets:
            try:
                res = audit(t, b)
            except Exception as e:  # 한 장이 못 열려도 나머지는 잰다
                if as_json:
                    print(json.dumps({"path": t, "error": str(e)[:120]}, ensure_ascii=False), flush=True)
                else:
                    print(f"\n### {t}\n열기 실패: {e}")
                continue
            if as_json:
                walked = [name for name, _v, mark in rows(res) if mark == "⚠️"]
                print(json.dumps({"path": t, "warn": walked}, ensure_ascii=False), flush=True); continue
            print(f"\n### {t}\n| 항목 | 값 | 판정 |\n|---|---|---|")
            for name, val, mark in rows(res):
                bad += mark == "⚠️"
                print(f"| {name} | {val} | {mark} |")
        b.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
