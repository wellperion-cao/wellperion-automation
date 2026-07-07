"""공식 @wellperion 시설 시리즈 F1·F2·F3 — 사진형 슬라이드(테마 2·2·2).

GM 2026-07-07 지시: 기존 '시설 종합 F1'(6장 한 게시물)을 3편 시리즈로 분할.
  F1 물과 근력(수영·헬스) / F2 스포츠(골프·스쿼시) / F3 회복(사우나·건습식)
  스파(자쿠지, 094A9949·9951)는 제외 → 생크몽드 편의시설 편으로 이관.

디자인 정본 = compose_barre 스타일 프리미티브를 그대로 재사용(손 디자인 추측 금지).
전 슬라이드 = 풀사진 + 하단 그라디언트 + 좌상단 풀로고 + 우상단 WELLPERION 칩 + 카운터.
사진 정본 = 2. 브랜드_공식문서/01_시설_사진 (프로컷 094A* = web_10mb아래 / 사우나·탕 = 시설 사진/).

실행:
  python scripts\\compose_official_facility_series.py               # 3편 제작 + M5 등록
  python scripts\\compose_official_facility_series.py --no-register # 제작만(룩 확인용)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

sys.path.insert(0, str(Path(__file__).parent))
from compose_barre import (  # noqa: E402
    W, H, center_crop_fill, apply_bottom_gradient,
    paste_logo, draw_chip, draw_counter, load_font,
)
from brand_constants import BEIGE, WHITE, GRAY, PROJECT_ROOT  # noqa: E402

FAC = PROJECT_ROOT / "2. 브랜드_공식문서" / "01_시설_사진"
PRO = FAC / "web_10mb아래"     # 094A* 프로컷
KAKAO = FAC / "시설 사진"       # 사우나·탕·휴게 등
FOOT = "WELLPERION  ·  FACILITY"
META = "한남동 3,000평 종합 스포츠클럽"


def _base(photo_path: Path):
    canvas = center_crop_fill(photo_path, W, H)
    canvas = ImageEnhance.Brightness(canvas).enhance(0.90)
    canvas = apply_bottom_gradient(canvas, gradient_start_y=505)
    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)
    chip_font = load_font("bold", 28)
    draw_chip(draw, "WELLPERION", chip_font, W - 40 - 240, 38, 240, 52)
    return canvas, draw


def _save(canvas: Image.Image, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "JPEG", quality=93, optimize=True)
    print(f"  {out_path.name}  {out_path.stat().st_size // 1024}KB")


def compose_hero(photo_path, title_lines, sub, footer, cta, out_path,
                 title_size=66):
    canvas, draw = _base(photo_path)
    draw.multiline_text((40, 718), title_lines, font=load_font("bold", title_size),
                        fill=WHITE, spacing=16)
    if sub:
        draw.text((40, 928), sub, font=load_font("semibold", 30), fill=BEIGE)
    if cta:
        draw.text((40, 928), cta, font=load_font("semibold", 30), fill=BEIGE)
    draw.text((40, 1000), footer, font=load_font("medium", 26), fill=BEIGE)
    _save(canvas, out_path)


def compose_feature(photo_path, title, sub, current, total, out_path,
                    meta=META, footer=FOOT):
    canvas, draw = _base(photo_path)
    draw_counter(draw, current, total, load_font("medium", 28), W - 40 - 240, 38, 52)
    draw.text((40, 795), meta, font=load_font("medium", 26), fill=GRAY)
    draw.text((40, 858), title, font=load_font("bold", 64), fill=WHITE)
    draw.text((40, 958), sub, font=load_font("semibold", 30), fill=BEIGE)
    draw.text((40, 1026), footer, font=load_font("medium", 26), fill=BEIGE)
    _save(canvas, out_path)


def build_montage(slide_paths, dest, cols=4, cell=360):
    imgs = [Image.open(p).convert("RGB") for p in slide_paths if p.exists()]
    rows = (len(imgs) + cols - 1) // cols
    gap, bg = 12, (28, 26, 24)
    canvas = Image.new("RGB", (cols * cell + (cols + 1) * gap,
                               rows * cell + (rows + 1) * gap), bg)
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        thumb = im.copy(); thumb.thumbnail((cell, cell))
        canvas.paste(thumb, (gap + c * (cell + gap) + (cell - thumb.width) // 2,
                             gap + r * (cell + gap) + (cell - thumb.height) // 2))
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, quality=90)
    print(f"  montage → {dest.name}")


# ── 3편 구성 (테마 2·2·2) ────────────────────────────────────────────
EPISODES = [
    {
        "slug": "260707_공식_시설_F1_물과근력",
        "queue_id": "CMO-2026-07-07-OFFICIAL-F1-물과근력",
        "title": "공식 #F1 — 물과 근력 (수영·헬스)",
        "caption": (
            "운동의 하루는 물과 근력에서 시작됩니다.\n\n"
            "25m 정규 수영장에서 몸을 풀고,\n"
            "테크노짐 카디오·프리웨이트 존에서 오늘의 강도를 채웁니다.\n"
            "한남동 3,000평, 한 공간에서.\n\n"
            "문의: wellperion.com/ko/inquiry\n\n"
            "#웰페리온 #한남동 #스포츠클럽 #수영 #25m수영장 #헬스 "
            "#테크노짐 #근력운동 #프리미엄"
        ),
        "slides": [
            {"kind": "hero", "photo": PRO / "094A0032.jpg",
             "title": "물과 근력,\n하루가 깨어난다", "sub": META, "cta": ""},
            {"kind": "feature", "photo": PRO / "094A9901.jpg",
             "title": "수영", "sub": "25m 정규 레인"},
            {"kind": "feature", "photo": PRO / "094A9977.jpg",
             "title": "헬스", "sub": "테크노짐 카디오존"},
            {"kind": "hero", "photo": PRO / "094A9961.jpg",
             "title": "근력,\n오늘의 강도를 채우다", "sub": "",
             "cta": "문의 · wellperion.com/ko/inquiry", "title_size": 60},
        ],
    },
    {
        "slug": "260707_공식_시설_F2_스포츠",
        "queue_id": "CMO-2026-07-07-OFFICIAL-F2-스포츠",
        "title": "공식 #F2 — 스포츠 (골프·스쿼시)",
        "caption": (
            "집중해서 즐기는 운동, 웰페리온의 스포츠존.\n\n"
            "GDR·QED 15타석 오토티업 골프 연습장과 강습룸,\n"
            "정식 규격 스쿼시 코트까지.\n"
            "날씨와 상관없이, 실내에서 제대로.\n\n"
            "문의: wellperion.com/ko/inquiry\n\n"
            "#웰페리온 #한남동 #스포츠클럽 #골프 #실내골프 #스크린골프 "
            "#스쿼시 #스쿼시코트 #프리미엄"
        ),
        "slides": [
            {"kind": "hero", "photo": PRO / "094A0008.jpg",
             "title": "스포츠,\n제대로 즐기다", "sub": "골프 · 스쿼시", "cta": ""},
            {"kind": "feature", "photo": PRO / "094A9943.jpg",
             "title": "스쿼시", "sub": "정식 규격 코트"},
            {"kind": "feature", "photo": KAKAO / "골프장.jpg",
             "title": "골프", "sub": "GDR·QED 15타석 오토티업"},
            {"kind": "hero", "photo": KAKAO / "야외테라스.jpg",
             "title": "운동 후,\n한숨 돌리는 자리", "sub": "",
             "cta": "문의 · wellperion.com/ko/inquiry", "title_size": 60},
        ],
    },
    {
        "slug": "260707_공식_시설_F3_회복",
        "queue_id": "CMO-2026-07-07-OFFICIAL-F3-회복",
        "title": "공식 #F3 — 회복 (사우나·건습식)",
        "caption": (
            "운동 뒤의 시간도 웰페리온입니다.\n\n"
            "따뜻한 원목의 건식 사우나,\n"
            "몸을 데우는 습식 사우나, 그리고 온·냉탕까지.\n"
            "땀을 흘린 만큼, 제대로 회복하세요.\n\n"
            "문의: wellperion.com/ko/inquiry\n\n"
            "#웰페리온 #한남동 #스포츠클럽 #사우나 #건식사우나 #습식사우나 "
            "#찜질 #회복 #웰니스"
        ),
        "slides": [
            {"kind": "hero", "photo": KAKAO / "건식사우나.jpg",
             "title": "회복,\n하루의 마무리", "sub": "건식 · 습식 사우나 · 온냉탕",
             "cta": ""},
            {"kind": "feature", "photo": KAKAO / "습식사우나.jpg",
             "title": "습식 사우나", "sub": "깊게 데우는 스팀"},
            {"kind": "feature", "photo": KAKAO / "남자 탕.jpg",
             "title": "온·냉탕", "sub": "번갈아, 개운하게"},
            {"kind": "hero", "photo": KAKAO / "휴게공간.jpg",
             "title": "운동의 하루,\n여기서 완성됩니다", "sub": "",
             "cta": "문의 · wellperion.com/ko/inquiry", "title_size": 58},
        ],
    },
]


def build_episode(ep, register):
    out_dir = PROJECT_ROOT / "instagram" / ep["slug"] / "output(인스타그램)"
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(ep["slides"])
    for s in ep["slides"]:
        if not s["photo"].exists():
            print(f"[ERROR] 소스 사진 없음: {s['photo']}"); sys.exit(1)
    print(f"=== {ep['title']} — {total}장 ===")
    slides = []
    for i, s in enumerate(ep["slides"], start=1):
        out = out_dir / f"post_{i}.jpg"
        if s["kind"] == "hero":
            compose_hero(s["photo"], s["title"], s["sub"], FOOT, s["cta"], out,
                         title_size=s.get("title_size", 66))
        else:
            compose_feature(s["photo"], s["title"], s["sub"], i, total, out)
        slides.append(out)
    montage = out_dir / f"_검수_미리보기_{total}장.png"
    build_montage(slides, montage)

    if not register:
        return
    from publish_register import register_publish
    register_publish(
        content_folder=PROJECT_ROOT / "instagram" / ep["slug"],
        slug=ep["slug"], montage_path=montage, caption=ep["caption"],
        location="웰페리온 스포츠클럽", mentions=[], account="wellperion",
        slides=[p.relative_to(PROJECT_ROOT).as_posix() for p in slides],
        queue_id=ep["queue_id"], title=ep["title"],
        channel="인스타그램 (wellperion)", send_card=False,
    )


def main():
    register = "--no-register" not in sys.argv
    for ep in EPISODES:
        build_episode(ep, register)
    print("=== 시리즈 3편 완료 ===")


if __name__ == "__main__":
    main()
