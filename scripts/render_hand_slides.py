# -*- coding: utf-8 -*-
"""
손글씨(나눔펜+나눔붓) 다이어리형 슬라이드 HTML(갤러리)을
인스타 4:5 (1080x1350) 개별 PNG/JPG 슬라이드로 렌더.

입력: "갤러리" 소스 HTML — <style> + <div class="wrap"><div class="inner">
      <div class="head">...</div><div class="strip"> 여러 .cell > .sheet > .pad
      </div><p class="note">...</p></div></div> 구조 (namuk_ep01_diary.html 계열).
      룩(종이질감·먹빛·손그린 밑줄 .u·붓 강조 .hit)은 CSS 그대로 재사용 —
      이 스크립트는 폰트를 임베드하고 "손글씨 override CSS"를 씌운 뒤
      갤러리 grid를 걷어내 슬라이드 1장 = 1페이지(1080x1350)로 재구성만 한다.

사용 예:
    .venv/Scripts/python scripts/render_hand_slides.py \
        --diary-html "instagram/namuk.wellperion/260707_AI_종합접수처_사례/ep01_diary_source.html" \
        --out-dir "instagram/namuk.wellperion/260707_AI_종합접수처_사례/output" \
        --prefix post

기본값은 EP01(종합접수처) 기준으로 맞춰져 있어 --diary-html/--out-dir만
바꾸면 다음 편에도 그대로 재사용 가능.
"""
import argparse
import base64
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

DEFAULT_DIARY = os.path.join(
    REPO_ROOT, "instagram", "namuk.wellperion",
    "260707_AI_종합접수처_사례", "ep01_diary_source.html",
)
DEFAULT_OUT_DIR = os.path.join(
    REPO_ROOT, "instagram", "namuk.wellperion",
    "260707_AI_종합접수처_사례", "output",
)
DEFAULT_PEN = os.path.join(REPO_ROOT, "instagram", "_assets", "fonts", "NanumPenScript-Regular.ttf")
DEFAULT_BRUSH = os.path.join(REPO_ROOT, "instagram", "_assets", "fonts", "NanumBrushScript-Regular.ttf")

# 승인 카드(갤러리 .strip 카드 ~404px 폭·4:5)와 근사한 CSS 렌더 크기.
# .pad 패딩·.entry 폰트 px는 그대로 두고 "카드 폭에서 렌더"해야
# 승인 미리보기와 같은 글자 밀도(꽉 찬 손글씨)가 재현된다.
# 이후 고 deviceScaleFactor로 캡처해 최종 출력 크기(OUT_W x OUT_H)로 다운샘플.
CARD_W, CARD_H = 432, 540  # 4:5, 렌더(CSS px) 크기
OUT_W, OUT_H = 1080, 1350  # 최종 인스타 4:5 출력 크기

# 원본 갤러리 CSS의 .cell:nth-child(N) .sheet{background:...} 매핑을
# 그대로 옮긴 값(회전만 제거) — 장마다 미묘한 종이 톤 차이를 보존.
SLIDE_BG_VAR = {
    1: "var(--sheet)",
    2: "var(--sheet-2)",
    3: "var(--sheet-3)",
    4: "var(--sheet-2)",
    5: "var(--sheet-3)",
    6: "var(--sheet)",
}

# build_hand.py와 동일한 "손글씨 override" — 본문=펜, 강조(.hit)=붓.
# 룩을 바꾸지 않기 위해 문자 그대로 재사용한다.
HAND_OVERRIDE_CSS = """
  /* -- 손글씨 적용: 펜=본문 / 붓=강조 (build_hand.py와 동일) -- */
  .entry,.date,.sign,.aside,.next,.insert{font-family:var(--hand)!important;}
  .entry{font-size:24px; line-height:1.68; letter-spacing:.01em; text-shadow:0 0 .5px rgba(38,34,28,.3);}
  .entry.lead{font-size:27px; line-height:1.62;}
  .entry.small{font-size:23px; line-height:1.66;}
  .date{font-size:17px;} .date .d{font-weight:400;} .date .w{font-size:15px;}
  .sign{font-size:20px; font-weight:400;}
  .aside{font-size:16px;} .next{font-size:17px;} .next em{font-style:normal;}
  .insert{font-size:20px;}
  .hit{font-family:var(--brush)!important; color:#1a1611; font-size:1.28em; line-height:1;
       -webkit-text-stroke:.35px #1a1611; letter-spacing:.005em;
       text-shadow:0 0 .7px rgba(20,16,10,.5);}
  .entry.lead .hit{font-size:1.34em;}
  .u{background-size:100% .32em; padding-bottom:.05em;}
  .cap,.kicker,.head h1,.head p,.note{font-family:var(--serif);}
"""


def embed_font(path, family):
    """build_hand.py와 동일한 subset+woff2 base64 임베드."""
    from fontTools.subset import Subsetter, Options
    from fontTools.ttLib import TTFont

    text = _charset_placeholder  # main()에서 미리 채워둔 전역 charset
    opt = Options()
    opt.flavor = "woff2"
    opt.desubroutinize = True
    opt.layout_features = ["*"]
    f = TTFont(path)
    ss = Subsetter(options=opt)
    ss.populate(text=text)
    ss.subset(f)
    buf = io.BytesIO()
    f.save(buf)
    b = buf.getvalue()
    b64 = base64.b64encode(b).decode("ascii")
    print(f"  [font] {family}: {len(b)} bytes (woff2)")
    return (
        f"@font-face{{font-family:'{family}';"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2');"
        "font-weight:400;font-style:normal;font-display:swap;}\n"
    )


def find_matching_close(html, start_idx):
    """start_idx = 여는 <div ...> 태그 바로 다음 위치. 짝이 맞는 </div> 시작 위치 반환."""
    depth = 1
    tag_re = re.compile(r"<div\b|</div>")
    for m in tag_re.finditer(html, start_idx):
        if m.group() == "</div>":
            depth -= 1
        else:
            depth += 1
        if depth == 0:
            return m.start(), m.end()
    raise ValueError("unmatched <div> in source html")


def extract_style(html):
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    if not m:
        raise ValueError("no <style> block found in diary html")
    return m.group(1)


def extract_pads(html):
    """`.strip` 안의 각 .sheet > <div class="pad X"> 블록을 순서대로 추출."""
    pads = []
    for m in re.finditer(r'<div class="pad ([a-z]+)">', html):
        cls = m.group(1)
        inner_start = m.end()
        inner_end, _ = find_matching_close(html, inner_start)
        pads.append((cls, html[inner_start:inner_end]))
    if not pads:
        raise ValueError("no .pad blocks found — diary html 구조 확인 필요")
    return pads


def build_slide_html(style_css, faces_css, pad_cls, pad_inner, bg_var):
    slide_css = f"""
html,body{{margin:0;padding:0;width:{CARD_W}px;height:{CARD_H}px;overflow:hidden;}}
.wrap{{padding:0;width:{CARD_W}px;height:{CARD_H}px;}}
.inner{{max-width:none;margin:0;width:{CARD_W}px;height:{CARD_H}px;}}
.sheet{{width:{CARD_W}px;height:{CARD_H}px;aspect-ratio:auto;border-radius:0;
        box-shadow:none;transform:none;background:{bg_var};}}
"""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
{faces_css}
{style_css}
{HAND_OVERRIDE_CSS}
{slide_css}
</style></head>
<body><div class="wrap"><div class="inner">
  <div class="sheet"><div class="pad {pad_cls}">
{pad_inner}
  </div></div>
</div></div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diary-html", default=DEFAULT_DIARY)
    ap.add_argument("--pen-font", default=DEFAULT_PEN)
    ap.add_argument("--brush-font", default=DEFAULT_BRUSH)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--prefix", default="post")
    ap.add_argument("--jpg-quality", type=int, default=92)
    ap.add_argument("--scale", type=int, default=5, help="deviceScaleFactor: CARD_W/H x scale 캡처 후 OUT_W/H로 다운샘플")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    html = io.open(args.diary_html, encoding="utf-8").read()
    style_css = extract_style(html)
    # build_hand.py와 동일: --serif 변수 줄 앞에 --hand/--brush 변수 삽입
    style_css = style_css.replace(
        "--serif:'Nanum Myeongjo'",
        "--hand:'namuk-pen','Nanum Myeongjo';\n    --brush:'namuk-brush','Nanum Myeongjo';\n    --serif:'Nanum Myeongjo'",
        1,
    )
    pads = extract_pads(html)
    print(f"[슬라이드] {len(pads)}장 추출 완료")

    # 폰트 서브셋 대상 문자: 전체 다이어리 html 텍스트 + 기본 문장부호/자모(build_hand.py와 동일 정책)
    global _charset_placeholder
    used = set(html)
    extra_chars = "0123456789.,·—…()~!?：:’‘“”\"'/ \n\t월일맑음"
    for c in extra_chars:
        used.add(c)
    _charset_placeholder = "".join(sorted(used))

    faces_css = embed_font(args.pen_font, "namuk-pen") + embed_font(args.brush_font, "namuk-brush")

    slide_paths = []
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": CARD_W, "height": CARD_H},
            device_scale_factor=args.scale,
        )
        for idx, (pad_cls, pad_inner) in enumerate(pads, start=1):
            bg_var = SLIDE_BG_VAR.get(idx, "var(--sheet)")
            slide_html = build_slide_html(style_css, faces_css, pad_cls, pad_inner, bg_var)
            tmp_html = os.path.join(args.out_dir, f"_slide_{idx}.html")
            io.open(tmp_html, "w", encoding="utf-8").write(slide_html)
            page.goto("file:///" + tmp_html.replace("\\", "/"))
            page.wait_for_timeout(200)  # 폰트/텍스처 렌더 안정화
            png_path = os.path.join(args.out_dir, f"_raw_{idx}.png")
            page.screenshot(path=png_path)
            slide_paths.append((idx, png_path))
        browser.close()

    # PIL로 정확히 OUT_W x OUT_H(1080x1350)로 다운샘플 + JPG 저장
    from PIL import Image

    final_paths = []
    for idx, png_path in slide_paths:
        img = Image.open(png_path).convert("RGB")
        if img.size != (OUT_W, OUT_H):
            img = img.resize((OUT_W, OUT_H), Image.LANCZOS)
        out_path = os.path.join(args.out_dir, f"{args.prefix}_{idx}.jpg")
        img.save(out_path, "JPEG", quality=args.jpg_quality)
        final_paths.append(out_path)
        os.remove(png_path)

    # 검수용 6장 가로 이어붙이기 미리보기
    imgs = [Image.open(p) for p in final_paths]
    strip = Image.new("RGB", (OUT_W * len(imgs), OUT_H), "white")
    for i, im in enumerate(imgs):
        strip.paste(im, (i * OUT_W, 0))
    preview_path = os.path.join(args.out_dir, "_검수_미리보기_6장.png")
    strip.save(preview_path)

    # 임시 슬라이드 html 정리
    for idx, _ in slide_paths:
        tmp_html = os.path.join(args.out_dir, f"_slide_{idx}.html")
        if os.path.exists(tmp_html):
            os.remove(tmp_html)

    print("\n[검증] 픽셀 크기")
    for p in final_paths:
        with Image.open(p) as im:
            print(f"  {p} -> {im.size[0]}x{im.size[1]}")
    print(f"  {preview_path} -> {Image.open(preview_path).size}")


if __name__ == "__main__":
    main()
