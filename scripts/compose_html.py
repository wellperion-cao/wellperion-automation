"""웰페리온 HTML/CSS 슬라이드 엔진 (compose_html) — 프리미엄 타이포그래피 렌더러.

파일럿(HTML/CSS + Playwright 스크린샷)의 프로덕션 일반화.
기존 Pillow 엔진(compose_barre 등)은 폴백으로 유지 — 이 엔진은 대체가 아니라 추가.

원리:
  슬라이드 1장 = HTML 템플릿(scripts/templates/*.html) + 브랜드 토큰 CSS 주입
  → Playwright(Chromium) deviceScaleFactor=2 슈퍼샘플링 스크린샷
  → PIL LANCZOS 다운샘플 → 정확히 1080x1080(또는 1080x1350) JPG/PNG.
  캐러셀 전체는 asyncio 병렬 페이지로 동시 렌더(직렬 대비 수 배 단축).

HTML/CSS가 Pillow 대비 이기는 것:
  letter-spacing(자간)·line-height·text-wrap:balance(단어 균형 줄바꿈)·
  font-kerning·부드러운 다단계 그라디언트(밴딩 없음)·tabular-nums 카운터.

브랜드 SSOT (새 값 도입 금지):
  색·폰트 경로·로고 경로 = scripts/brand_constants.py
  사진 크롭·듀오톤 = compose_barre.center_crop_fill / to_duotone 재사용(픽셀 정합)
  계정 규칙 = .claude/skills/wellperion-brand (개인=W심볼+에메랄드 / 공식=풀로고+베이지)

★ 사진 소스 규율(파일럿 교훈): 반드시 "텍스트가 박히지 않은" 원본 사진만 입력한다.
  텍스트가 이미 합성된 발행본을 소스로 쓰면 고스팅(이중 텍스트)이 생긴다.
  시설 사진 정본 라이브러리 = "2. 브랜드_공식문서/01_시설_사진"
  (프로컷 094A* = web_10mb아래 / 사우나·탕·휴게 = 시설 사진/ / 스파 = 생크몽드(26년도)).

입력 스펙(JSON 또는 dict):
  {
    "account": "official" | "personal",     # 로고·액센트 자동 (기본 official)
    "size": "1080x1080" | "1080x1350",      # 기본 1080x1080
    "chip_label": "WELLPERION",              # 우상단 칩 (기본 WELLPERION)
    "slides": [
      {"type": "cover",   "photo": "...", "title_eng": "RECOVERY",
       "title_kor": "회복", "date_location": "2026.07 · 한남동"},
      {"type": "hero",    "photo": "...", "title": "회복,\n하루의 마무리",
       "sub": "건식 · 습식 · 찜질 · 탕", "footer": "WELLPERION · FACILITY",
       "title_size": 66},
      {"type": "feature", "photo": "...", "title": "찜질방",
       "sub": "뜨끈하게 지지는 온기", "meta": "한남동 3,000평 종합 스포츠클럽",
       "footer": "WELLPERION · FACILITY"},        # counter 자동 (i/total)
      {"type": "guide",   "headline": "...", "body": "...",
       "cta": "문의 : wellperion.com/ko/inquiry", "footer": "WELLPERION"},
      {"type": "paper",   "title": ["몸이 달라지는 건", "[[작은 루틴]]이더라고요."],
       "body": ["같은 요일, 같은 시간에 오는 것."],   # str("\n" 분리)도 허용
       "bottom": ["더 보기  >"], "counter": true,      # counter 기본 꺼짐 → (ii/tt)
       "top_pct": 40, "title_size": 62,
       "mark_tilt": -1.6, "mark_pad_x": 9, "mark_pad_y": 26}
      # paper: 종이질감+마커 원(레퍼런스 스타일, 사진 없음). [[구절]] = 손그림 마커 원.
      #   마커 색 = 계정 자동(개인 에메랄드 / 공식 HIGHLIGHT). 짧은 구절은 pad 크게.
      #   "whisper": 속삭임 브랜딩 1줄 (기본 계정별 자동, false 로 끔).
    ]
  }
  counter: feature 슬라이드는 (슬라이드 순번/전체 장수) 자동. "counter": false 로 끔.
  total 은 스펙 "total" 로 오버라이드 가능(영상 장수 포함 시).

출력: out_dir/post_1.jpg … post_N.jpg (JPEG q93 — compose_barre 와 동일 스펙,
  M5 발행 파이프라인이 그대로 소비). --fmt png 시 PNG.

사용:
  python scripts\\compose_html.py spec.json --out <dir> [--fmt jpg|png] [--concurrency 4]
  또는: from compose_html import render_carousel
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import html as _html
import io
import json
import re
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from brand_constants import (  # noqa: E402
    FONT_BOLD, FONT_SEMIBOLD, FONT_MEDIUM,
    LOGO_WHITE_ALPHA, LOGO_BEIGE_ALPHA,
)
from compose_barre import center_crop_fill, to_duotone  # noqa: E402  (사진 파이프라인 SSOT)

TEMPLATE_DIR = Path(__file__).parent / "templates"

# ── 브랜드 토큰 (hex — brand_constants.py RGB 값과 동일) ──────────────
BEIGE = "#B79F8A"
BLACK = "#221F20"
GRAY = "#AAA098"
CHIP = "#BAA28C"
SEP = "#ABA197"
HIGHLIGHT = "#ED5B3F"
# 개인계정 시그니처 에메랄드 (wellperion-brand 스킬 §1 — 라이트/다크 정본 2값)
EMERALD_ON_DARK = "#63BBA0"
EMERALD_ON_LIGHT = "#2E6E5B"

# paper(종이 카드) 팔레트 — 검증 파일럿("종이 위의 루틴") 실측값 그대로 이관.
# 브랜드 색이 아니라 종이 질감 배경값(레퍼런스 실측 ~#B2AB9D 계열) — 여기가 단일 출처.
PAPER_BASE = "#BAB1A3"
PAPER_LIGHT = "#CDC5B7"
PAPER_EDGE = "#A89F91"
PAPER_INK = "#2F2A24"                 # 종이 위 잉크 (소프트 블랙)
PAPER_MUTED = "rgba(58,52,45,0.55)"   # 속삭임 브랜딩·CTA

ACCOUNTS = {
    # marker = 손그림 마커 원 (본선, 되그은 선). 개인=에메랄드 시그니처(라이트 배경 정본),
    # 공식=브랜드 블랙 잉크 #221F20 (brand_constants.BLACK_BG SSOT — 종이 위 프리미엄 펜
    # 느낌. HIGHLIGHT #ED5B3F(레드 계열)는 GM 피드백으로 폐기 — 브랜드 색 가이드 위반.
    # 에메랄드는 개인 전용이라 여전히 금지. 되그은 선은 같은 잉크의 반투명 톤(새 색상 아님).
    "official": {"logo_style": "full", "accent": BEIGE,
                 "marker": (BLACK, "rgba(34,31,32,0.55)"),
                 "paper_whisper": "WELLPERION  ·  한남동"},
    "personal": {"logo_style": "symbol", "accent": EMERALD_ON_DARK,
                 "marker": (EMERALD_ON_LIGHT, EMERALD_ON_DARK),
                 "paper_whisper": "namuk.wellperion  ·  한남동에서 천천히"},
}

SIZES = {"1080x1080": (1080, 1080), "1080x1350": (1080, 1350)}

_FONT_CSS_CACHE: str | None = None


def _b64_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _font_css() -> str:
    """Pretendard 3웨이트 @font-face (base64 임베드 — 파일럿 검증 방식). 1회 생성 캐시."""
    global _FONT_CSS_CACHE
    if _FONT_CSS_CACHE is None:
        faces = []
        for path, weight in ((FONT_BOLD, 700), (FONT_SEMIBOLD, 600), (FONT_MEDIUM, 500)):
            faces.append(
                "@font-face { font-family: 'Pretendard'; "
                f"src: url(data:font/otf;base64,{_b64_file(path)}) format('opentype'); "
                f"font-weight: {weight}; font-style: normal; }}"
            )
        _FONT_CSS_CACHE = "\n".join(faces)
    return _FONT_CSS_CACHE


def _gradient_css(start_y: int, total_h: int, steps: int = 48) -> str:
    """compose_barre.apply_bottom_gradient 의 t**1.2 곡선(캡 230/255)을
    다단계 CSS linear-gradient 로 재현 — CSS 보간 덕에 Pillow 밴딩 없이 매끈."""
    stops = [f"rgba(0,0,0,0) {start_y / total_h * 100:.2f}%"]
    for i in range(1, steps + 1):
        t = i / steps
        y_pct = (start_y + t * (total_h - start_y)) / total_h * 100
        alpha = min(230, 255 * (t ** 1.2)) / 255
        stops.append(f"rgba(34,31,32,{alpha:.4f}) {y_pct:.2f}%")
    return "linear-gradient(to bottom, " + ", ".join(stops) + ")"


def _esc(text: str) -> str:
    """HTML 이스케이프 (줄바꿈 \\n 은 보존 → CSS white-space:pre-line 이 렌더)."""
    return _html.escape(str(text or ""))


def _photo_b64(photo_path: Path, w: int, h: int, duotone: bool = False) -> str:
    """원본(텍스트 없는) 사진 → center-crop → (표지는 듀오톤) → JPEG base64."""
    img = center_crop_fill(photo_path, w, h)
    if duotone:
        img = to_duotone(img, normalize=True)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _logo_html(account_cfg: dict, on_dark: bool = False) -> str:
    """계정별 로고 (브랜드 스킬 §1: 개인=W심볼 텍스트 / 공식=풀 로고 PNG)."""
    if account_cfg["logo_style"] == "symbol":
        color = account_cfg["accent"] if on_dark else "#FFFFFF"
        cls = "guide-sym" if on_dark else "logo-sym"
        return f'<div class="{cls}" style="color:{color}">W</div>'
    logo_path = LOGO_BEIGE_ALPHA if on_dark else LOGO_WHITE_ALPHA
    cls = "guide-logo" if on_dark else "logo-img"
    return f'<img class="{cls}" src="data:image/png;base64,{_b64_file(logo_path)}">'


# ── paper 전용 헬퍼 (검증 파일럿 mark()/build_html 이관) ─────────────
_MARK_RE = re.compile(r"\[\[(.+?)\]\]")


def _marker_wrap(text_html: str, main: str, second: str, *,
                 tilt: float = -1.6, pad_x: int = 9, pad_y: int = 26) -> str:
    """key phrase 를 감싸는 손그림 마커 타원. 2패스(진한 본선 + 옅은 되그은 선).

    일부러 안 닫히고 시작점을 지나쳐 겹치는 마커펜 궤적(파일럿 검증 베지어).
    pad_x/pad_y: 글자 대비 원의 여유(%) — 짧은 구절은 크게 줘야 '둘러싼' 원이 된다.
    """
    style = (f"left:-{pad_x}%;width:{100 + 2 * pad_x}%;"
             f"top:-{pad_y}%;height:{100 + 2 * pad_y}%;"
             f"transform:rotate({tilt}deg)")
    return (
        '<span class="mk">' + text_html +
        f'<svg class="mkc" viewBox="0 0 320 120" preserveAspectRatio="none" '
        f'style="{style}" aria-hidden="true">'
        # 본선: 왼쪽 중간에서 출발 → 시계방향 한 바퀴 → 시작점을 지나쳐 위로 겹침
        '<path d="M 26 64 C 30 30, 92 10, 166 12 C 246 14, 308 32, 303 60 '
        'C 298 92, 226 111, 146 107 C 70 103, 12 88, 18 58 '
        'C 22 40, 46 25, 86 20" '
        f'fill="none" stroke="{main}" stroke-width="5.2" '
        'stroke-linecap="round" opacity="0.93"/>'
        # 되그은 선: 살짝 어긋난 부분 궤적(마커 잉크 겹침)
        '<path d="M 34 70 C 44 38, 108 17, 178 18 C 248 20, 298 38, 294 62" '
        f'fill="none" stroke="{second}" stroke-width="3.4" '
        'stroke-linecap="round" opacity="0.45"/>'
        "</svg></span>"
    )


def _as_lines(value) -> list[str]:
    """str("\\n" 분리) 또는 list[str] → 줄 리스트."""
    if not value:
        return []
    if isinstance(value, str):
        return value.split("\n")
    return [str(v) for v in value]


def _paper_lines_html(lines: list[str], cls: str, marker: tuple[str, str],
                      *, tilt: float, pad_x: int, pad_y: int) -> str:
    """[[구절]] → 마커 원 span 으로 치환하며 줄 div 생성 (텍스트는 전부 이스케이프)."""
    out = []
    for line in lines:
        parts, pos = [], 0
        for m in _MARK_RE.finditer(line):
            parts.append(_esc(line[pos:m.start()]))
            parts.append(_marker_wrap(_esc(m.group(1)), *marker,
                                      tilt=tilt, pad_x=pad_x, pad_y=pad_y))
            pos = m.end()
        parts.append(_esc(line[pos:]))
        out.append(f'<div class="{cls}">' + "".join(parts) + "</div>")
    return "".join(out)


def _paper_logo_html(account_cfg: dict) -> str:
    """paper(라이트 종이) 위 계정 로고 — 개인=에메랄드 W 심볼 / 공식=풀 로고 잉크 실루엣."""
    if account_cfg["logo_style"] == "symbol":
        return f'<div class="paper-sym" style="color:{EMERALD_ON_LIGHT}">W</div>'
    # 베이지 알파 PNG 를 CSS filter(brightness 0)로 잉크 실루엣화 — 새 자산 불필요
    return f'<img class="paper-logo-img" src="data:image/png;base64,{_b64_file(LOGO_BEIGE_ALPHA)}">'


def _fill(template: str, mapping: dict) -> str:
    for key, val in mapping.items():
        template = template.replace("{{" + key + "}}", val)
    return template


def _load_template(name: str) -> str:
    return (TEMPLATE_DIR / f"{name}.html").read_text(encoding="utf-8")


def _base_css() -> str:
    return (TEMPLATE_DIR / "base.css").read_text(encoding="utf-8")


# ── 슬라이드 1장 → HTML ─────────────────────────────────────────────
def build_slide_html(slide: dict, *, w: int, h: int, account: str,
                     chip_label: str, index: int, total: int) -> str:
    kind = slide["type"]
    cfg = ACCOUNTS[account]
    accent = slide.get("accent", cfg["accent"])
    grad_start = int(slide.get("gradient_start", h - 575))  # 1080 기준 505 (F시리즈 정본)
    cover_photo_h = int(round(h * 0.648))                   # 1080 기준 700 (compose_cover 정본)

    tokens = (
        f"--W: {w}px; --H: {h}px; "
        f"--black: {BLACK}; --beige: {BEIGE}; --gray: {GRAY}; "
        f"--chip: {CHIP}; --sep: {SEP}; --highlight: {HIGHLIGHT}; "
        f"--accent: {accent}; "
        f"--title-size: {slide.get('title_size', 66 if kind == 'hero' else 64)}px; "
        f"--gradient: {_gradient_css(grad_start, h)}; "
        f"--cover-photo-h: {cover_photo_h}px;"
    )
    if kind == "paper":
        tokens += (
            f" --paper-base: {PAPER_BASE}; --paper-light: {PAPER_LIGHT}; "
            f"--paper-edge: {PAPER_EDGE}; --paper-ink: {PAPER_INK}; "
            f"--paper-muted: {PAPER_MUTED}; "
            f"--paper-top: {slide.get('top_pct', 40)}%; "
            f"--paper-title-size: {slide.get('title_size', 62)}px;"
        )
    common = {
        "FONT_CSS": _font_css(),
        "TOKENS_CSS": tokens,
        "BASE_CSS": _base_css(),
        "CHIP": _esc(slide.get("chip_label", chip_label)),
    }

    if kind in ("hero", "feature"):
        photo = Path(slide["photo"])
        mapping = dict(common,
                       PHOTO_SRC=_photo_b64(photo, w, h),
                       LOGO_HTML=_logo_html(cfg),
                       TITLE=_esc(slide["title"]),
                       FOOTER=_esc(slide.get("footer", "WELLPERION")))
        if kind == "hero":
            sub = slide.get("sub") or slide.get("cta") or ""
            mapping["SUB_HTML"] = f'<div class="sub">{_esc(sub)}</div>' if sub else ""
            return _fill(_load_template("hero"), mapping)
        counter = slide.get("counter", True)
        mapping["COUNTER_HTML"] = (
            f'<div class="counter">{index:02d} / {total:02d}</div>' if counter else "")
        mapping["META"] = _esc(slide.get("meta", ""))
        mapping["SUB"] = _esc(slide.get("sub", ""))
        return _fill(_load_template("feature"), mapping)

    if kind == "cover":
        photo = Path(slide["photo"])
        return _fill(_load_template("cover"), dict(
            common,
            PHOTO_SRC=_photo_b64(photo, w, cover_photo_h, duotone=True),
            LOGO_HTML=_logo_html(cfg),
            TITLE_KOR=_esc(slide["title_kor"]),
            TITLE_ENG=_esc(slide["title_eng"]),
            DATE_LOCATION=_esc(slide.get("date_location", "")),
        ))

    if kind == "guide":
        body = slide.get("body", "")
        return _fill(_load_template("guide"), dict(
            common,
            LOGO_HTML=_logo_html(cfg, on_dark=True),
            HEADLINE=_esc(slide["headline"]),
            BODY_HTML=f'<p class="guide-body">{_esc(body)}</p>' if body else "",
            CTA=_esc(slide.get("cta", "문의 : wellperion.com/ko/inquiry")),
            FOOTER=_esc(slide.get("footer", "WELLPERION")),
        ))

    if kind == "paper":
        marker = cfg["marker"]
        tilt = float(slide.get("mark_tilt", -1.6))
        pad_x = int(slide.get("mark_pad_x", 9))
        pad_y = int(slide.get("mark_pad_y", 26))
        title_html = _paper_lines_html(_as_lines(slide.get("title")), "paper-tl",
                                       marker, tilt=tilt, pad_x=pad_x, pad_y=pad_y)
        body_html = _paper_lines_html(_as_lines(slide.get("body")), "paper-bl",
                                      marker, tilt=tilt, pad_x=pad_x, pad_y=pad_y)
        whisper = slide.get("whisper", cfg["paper_whisper"])
        whisper_html = (f'<div class="paper-whisper">{_esc(whisper)}</div>'
                        if whisper else "")
        bottom_lines = _as_lines(slide.get("bottom"))
        bottom_html = (
            '<div class="paper-bottom">'
            + "".join(f'<div class="paper-cta">{_esc(ln)}</div>' for ln in bottom_lines)
            + "</div>") if bottom_lines else ""
        counter_html = (f'<div class="paper-counter">({index:02d}/{total:02d})</div>'
                        if slide.get("counter") else "")
        return _fill(_load_template("paper"), dict(
            common,
            LOGO_HTML=_paper_logo_html(cfg),
            TITLE_HTML=title_html,
            BODY_HTML=body_html,
            WHISPER_HTML=whisper_html,
            BOTTOM_HTML=bottom_html,
            COUNTER_HTML=counter_html,
        ))

    raise ValueError(f"Unknown slide type: {kind!r}")


# ── Playwright 병렬 렌더 ────────────────────────────────────────────
async def _render_batch(html_docs: list[str], w: int, h: int,
                        scale: int, concurrency: int) -> list[bytes]:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        sem = asyncio.Semaphore(concurrency)

        async def render_one(doc: str) -> bytes:
            async with sem:
                page = await browser.new_page(
                    viewport={"width": w, "height": h}, device_scale_factor=scale)
                await page.set_content(doc, wait_until="load")
                # 미사용 웨이트는 lazy-load 되지 않으므로 3웨이트 강제 로드 후 검증
                await page.evaluate(
                    "Promise.all(['700','600','500'].map(w =>"
                    " document.fonts.load(w + \" 20px 'Pretendard'\")))")
                await page.wait_for_function("document.fonts.status === 'loaded'")
                ok = await page.evaluate("document.fonts.check(\"700 20px 'Pretendard'\")")
                if not ok:
                    raise RuntimeError("Pretendard 폰트 로드 실패 — 렌더 중단(폴백 방지)")
                await page.evaluate(
                    "Promise.all([...document.images].map(i => i.decode().catch(() => null)))")
                await page.wait_for_timeout(80)  # 디코딩·레이아웃 안정화
                png = await page.screenshot(clip={"x": 0, "y": 0, "width": w, "height": h})
                await page.close()
                return png

        results = await asyncio.gather(*(render_one(d) for d in html_docs))
        await browser.close()
    return list(results)


def render_carousel(spec: dict, out_dir: Path, *, fmt: str = "jpg",
                    scale: int = 2, concurrency: int = 4) -> list[Path]:
    """스펙 → 캐러셀 전체 렌더. post_1.{fmt} … 반환 (정확히 WxH, M5 호환)."""
    account = spec.get("account", "official")
    if account not in ACCOUNTS:
        raise ValueError(f"Unknown account: {account!r} (official|personal)")
    w, h = SIZES[spec.get("size", "1080x1080")]
    chip_label = spec.get("chip_label", "WELLPERION")
    slides = spec["slides"]
    total = int(spec.get("total", len(slides)))

    for s in slides:
        if "photo" in s and not Path(s["photo"]).exists():
            raise FileNotFoundError(f"소스 사진 없음: {s['photo']}")

    t0 = time.perf_counter()
    docs = [build_slide_html(s, w=w, h=h, account=account, chip_label=chip_label,
                             index=i, total=total)
            for i, s in enumerate(slides, start=1)]
    t_html = time.perf_counter() - t0

    t1 = time.perf_counter()
    pngs = asyncio.run(_render_batch(docs, w, h, scale, concurrency))
    t_render = time.perf_counter() - t1

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, png in enumerate(pngs, start=1):
        img = Image.open(io.BytesIO(png))
        if img.size != (w, h):
            img = img.resize((w, h), Image.LANCZOS)
        out = out_dir / f"post_{i}.{fmt}"
        if fmt == "jpg":
            img.convert("RGB").save(out, "JPEG", quality=93, optimize=True)
        else:
            img.save(out, "PNG")
        assert Image.open(out).size == (w, h), f"치수 불일치: {out}"
        paths.append(out)
        print(f"  [{i:02d}/{len(pngs):02d}] {out.name}  {out.stat().st_size // 1024}KB  {w}x{h}")

    print(f"[TIME] HTML 빌드 {t_html:.1f}s + 병렬 렌더 {t_render:.1f}s "
          f"(동시 {concurrency}·스케일 x{scale}) = 총 {t_html + t_render:.1f}s / {len(pngs)}장")
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description="웰페리온 HTML/CSS 슬라이드 엔진")
    ap.add_argument("spec", help="캐러셀 스펙 JSON 경로")
    ap.add_argument("--out", required=True, help="출력 폴더")
    ap.add_argument("--fmt", default="jpg", choices=["jpg", "png"])
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--scale", type=int, default=2)
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    render_carousel(spec, Path(args.out), fmt=args.fmt,
                    scale=args.scale, concurrency=args.concurrency)


if __name__ == "__main__":
    main()
