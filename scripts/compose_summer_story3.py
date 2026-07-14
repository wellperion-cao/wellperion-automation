# -*- coding: utf-8 -*-
"""개인계정(@namuk.wellperion) 여름 개편 — 3번째 이야기 "시스템은 AI가, 공간은 내가"
템플릿 엔진 (표지 · 본문 · 마무리).

스펙 정본: docs/superpowers/specs/2026-07-07-namuk-summer-story3-design.md
디자인 원리 = "여백 그릇"(넓은 화이트스페이스가 메시지를 담는 그릇) + 하단 자동화
신호줄("시스템은 AI가") + 에메랄드/시트러스 시그니처. 캔바·PIL 텍스트드로잉 없이
기존 손글씨 엔진(render_hand_slides.py) 패턴을 그대로 재사용 — HTML/CSS를
Playwright로 스크린샷한 뒤, 최종 해상도로 다운샘플만 PIL로 처리한다.

⚠️ 이 스크립트가 만드는 카피는 전부 [TODO: ...] 플레이스홀더다.
   실제 "공간의 본질 연구" 콘텐츠·마무리 카피는 GM 인풋 대기(스펙 §7) —
   여기서 채우지 않는다. 표지 헤드라인만 스펙 §4에서 이미 확정된 문구라
   그대로 사용한다.

사용 예 (렌더 테스트):
    C:\\Python314\\python.exe scripts/compose_summer_story3.py --out-dir <경로>

산출: {prefix}_cover.jpg / {prefix}_body.jpg / {prefix}_closing.jpg (1080x1350)
      + _검수_미리보기_3장.png (가로 스티치 미리보기)
"""
from __future__ import annotations

import argparse
import base64
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

FONT_PATH = os.path.join(
    REPO_ROOT, "2. 브랜드_공식문서", "02_로고&워터마크&FONT", "font", "Pretendard-Bold.otf",
)

OUT_W, OUT_H = 1080, 1350  # 인스타 4:5
SCALE = 2  # 슈퍼샘플 배수(폰트 안티에일리어싱용) — render_hand_slides.py와 동일 기법

# -----------------------------------------------------------------
# 디자인 토큰 (스펙 §3 "여백 그릇" 그대로 — 새 값 추가 없이 스펙값만 사용)
# -----------------------------------------------------------------
EMERALD_LIGHT = "#2E6E5B"
EMERALD_DARK = "#63BBA0"
INK = "#164b3a"          # 딥 에메랄드 잉크(헤드라인)
CITRUS = "#d9c94a"
CITRUS_HI = "#ecdf6a"
BG = "#eef3f0"            # 쿨 페일 민트그레이
BG_BAND = "#e5ede8"       # 하단 밴드

FONT_STACK = "'namuk-pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif"
MONO_STACK = "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"

# 자동화 신호줄 — 숫자는 실값만(약속 L05). 렌더 테스트 단계 = 플레이스홀더.
STATUS_PLACEHOLDER = "auto-run · [TODO: 실측 자동처리 건수]"


def _embed_font() -> str:
    """Pretendard-Bold.otf를 base64 그대로 임베드(서브셋 없이 — 1회성 로컬 렌더용)."""
    data = io.open(FONT_PATH, "rb").read()
    b64 = base64.b64encode(data).decode("ascii")
    return (
        "@font-face{font-family:'namuk-pretendard';"
        f"src:url(data:font/opentype;base64,{b64}) format('opentype');"
        "font-weight:400 800;font-style:normal;font-display:swap;}\n"
    )


def _base_css() -> str:
    return f"""
html,body{{margin:0;padding:0;width:{OUT_W}px;height:{OUT_H}px;overflow:hidden;
  background:{BG};font-family:{FONT_STACK};}}
.page{{position:relative;width:{OUT_W}px;height:{OUT_H}px;}}
.rail{{position:absolute;left:0;top:0;width:16px;height:100%;
  background:linear-gradient(180deg,{CITRUS_HI},{CITRUS});}}
.band{{position:absolute;left:0;bottom:0;width:100%;height:132px;background:{BG_BAND};}}
.badge{{position:absolute;top:64px;left:76px;width:56px;height:56px;border-radius:50%;
  background:{INK};color:#fff;display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:26px;letter-spacing:-.02em;}}
.status{{position:absolute;left:76px;bottom:52px;right:76px;display:flex;align-items:center;
  gap:10px;font-family:{MONO_STACK};font-size:19px;color:{EMERALD_DARK};letter-spacing:.01em;}}
.status .dot{{width:9px;height:9px;border-radius:50%;background:{EMERALD_LIGHT};flex:0 0 auto;}}
.status .txt{{color:{INK};opacity:.82;}}
"""


def _status_html() -> str:
    return f'<div class="status"><span class="dot"></span><span class="txt">{STATUS_PLACEHOLDER}</span></div>'


def _badge_html() -> str:
    return '<div class="badge">W</div>'


def _wrap(body_css: str, body_html: str, faces_css: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
{faces_css}
{_base_css()}
{body_css}
</style></head>
<body><div class="page">
  <div class="rail"></div>
  {_badge_html()}
  {body_html}
  <div class="band"></div>
  {_status_html()}
</div></body></html>"""


# -----------------------------------------------------------------
# 1. 표지(Cover) — 스펙 §4-1: 헤드라인(확정 카피) + 서브(TODO) + 신호줄 + W + 저장CTA
# -----------------------------------------------------------------
def cover_html(faces_css: str) -> str:
    css = f"""
.headline{{position:absolute;left:76px;right:76px;top:520px;
  font-weight:800;font-size:76px;line-height:1.24;letter-spacing:-.022em;
  color:{INK};white-space:pre-line;}}
.subhead{{position:absolute;left:76px;right:76px;top:756px;
  font-size:29px;line-height:1.5;color:{EMERALD_LIGHT};white-space:pre-line;}}
.cta{{position:absolute;left:76px;bottom:196px;font-size:23px;color:{INK};opacity:.86;}}
"""
    # 헤드라인 = 스펙 §4-1에서 이미 확정된 카피 그대로(수정 금지). 서브는 GM 인풋 대기.
    headline = "시스템은 AI가.\n공간은 내가."
    subhead = "[TODO: 부제 문구 — 공간의 본질 연구 콘텐츠 확정 후 채움]"
    html = (
        f'<div class="headline">{headline}</div>'
        f'<div class="subhead">{subhead}</div>'
        f'<div class="cta">📌 저장</div>'
    )
    return _wrap(css, html, faces_css)


# -----------------------------------------------------------------
# 2. 본문(Body) — 스펙 §4-2: "AI가 대신(반복) → 내가 집중(본질)" 2열 대비 그리드 + 신호줄
# -----------------------------------------------------------------
def body_html(faces_css: str) -> str:
    css = f"""
.kicker{{position:absolute;left:76px;top:120px;font-size:24px;font-weight:800;
  color:{INK};letter-spacing:-.01em;}}
.grid{{position:absolute;left:76px;right:76px;top:220px;bottom:220px;display:flex;}}
.col{{flex:1 1 0;padding-right:36px;}}
.col + .col{{padding-left:36px;padding-right:0;border-left:1px solid rgba(22,75,58,.18);}}
.col h3{{margin:0 0 22px;font-size:27px;font-weight:800;color:{INK};letter-spacing:-.015em;}}
.col ul{{margin:0;padding:0;list-style:none;}}
.col li{{margin:0 0 18px;font-size:22px;line-height:1.5;color:{EMERALD_LIGHT};}}
.col.right h3{{color:{EMERALD_LIGHT};}}
.col.right li{{color:{INK};opacity:.85;}}
"""
    left_items = "".join(
        f"<li>· {t}</li>" for t in [
            "[TODO: ERP 자동처리 항목 1 — 실측]",
            "[TODO: ERP 자동처리 항목 2 — 실측]",
            "[TODO: ERP 자동처리 항목 3 — 실측]",
        ]
    )
    right_items = "".join(
        f"<li>· {t}</li>" for t in [
            "[TODO: 공간 연구 항목 1 — GM 인풋 대기]",
            "[TODO: 공간 연구 항목 2 — GM 인풋 대기]",
            "[TODO: 공간 연구 항목 3 — GM 인풋 대기]",
        ]
    )
    html = (
        '<div class="kicker">시스템은 AI가 → 공간은 내가</div>'
        '<div class="grid">'
        f'  <div class="col left"><h3>AI가 대신<br>(반복)</h3><ul>{left_items}</ul></div>'
        f'  <div class="col right"><h3>내가 집중<br>(본질)</h3><ul>{right_items}</ul></div>'
        "</div>"
    )
    return _wrap(css, html, faces_css)


# -----------------------------------------------------------------
# 3. 마무리(Closing) — 스펙 §4-3: (미확정) 저장·팔로우 유도 + 다음 편 브릿지
# -----------------------------------------------------------------
def closing_html(faces_css: str) -> str:
    css = f"""
.c-headline{{position:absolute;left:76px;right:76px;top:480px;
  font-weight:800;font-size:52px;line-height:1.3;letter-spacing:-.02em;
  color:{INK};white-space:pre-line;}}
.c-bridge{{position:absolute;left:76px;right:76px;top:660px;
  font-size:26px;line-height:1.55;color:{EMERALD_LIGHT};white-space:pre-line;}}
.c-cta{{position:absolute;left:76px;bottom:196px;font-size:23px;line-height:1.7;
  color:{INK};opacity:.86;white-space:pre-line;}}
"""
    headline = "[TODO: 마무리 카피 확정 대기]"
    bridge = "[TODO: 다음 편 브릿지 문구 — 카피 후속 확정(스펙 §4-3)]"
    cta = "📌 저장\n💬 댓글\n👀 팔로우"
    html = (
        f'<div class="c-headline">{headline}</div>'
        f'<div class="c-bridge">{bridge}</div>'
        f'<div class="c-cta">{cta}</div>'
    )
    return _wrap(css, html, faces_css)


TEMPLATES = {
    "cover": cover_html,
    "body": body_html,
    "closing": closing_html,
}


def render_all(out_dir: str, prefix: str = "sample", jpg_quality: int = 92) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    faces_css = _embed_font()

    from playwright.sync_api import sync_playwright
    from PIL import Image

    raw_paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": OUT_W, "height": OUT_H},
            device_scale_factor=SCALE,
        )
        for name, builder in TEMPLATES.items():
            html = builder(faces_css)
            tmp_html = os.path.join(out_dir, f"_slide_{name}.html")
            io.open(tmp_html, "w", encoding="utf-8").write(html)
            page.goto("file:///" + tmp_html.replace("\\", "/"))
            page.wait_for_timeout(150)
            raw_png = os.path.join(out_dir, f"_raw_{name}.png")
            page.screenshot(path=raw_png)
            raw_paths.append((name, raw_png))
            os.remove(tmp_html)
        browser.close()

    final_paths = []
    for name, raw_png in raw_paths:
        img = Image.open(raw_png).convert("RGB")
        if img.size != (OUT_W, OUT_H):
            img = img.resize((OUT_W, OUT_H), Image.LANCZOS)
        out_path = os.path.join(out_dir, f"{prefix}_{name}.jpg")
        img.save(out_path, "JPEG", quality=jpg_quality)
        final_paths.append(out_path)
        os.remove(raw_png)

    # 검수용 3장 가로 스티치 미리보기
    imgs = [Image.open(p) for p in final_paths]
    strip = Image.new("RGB", (OUT_W * len(imgs), OUT_H), "white")
    for i, im in enumerate(imgs):
        strip.paste(im, (i * OUT_W, 0))
    preview_path = os.path.join(out_dir, "_검수_미리보기_3장.png")
    strip.save(preview_path)
    final_paths.append(preview_path)

    return final_paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--prefix", default="sample")
    args = ap.parse_args()

    paths = render_all(args.out_dir, prefix=args.prefix)
    print("[검증] 픽셀 크기")
    from PIL import Image
    for p in paths:
        with Image.open(p) as im:
            print(f"  {p} -> {im.size[0]}x{im.size[1]}")


if __name__ == "__main__":
    main()
