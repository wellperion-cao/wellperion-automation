"""골프 유소년 KPGA 주니어대회 슬라이드 합성 스크립트 (바레 SSOT import)
레퍼런스: scripts/compose_ballet.py — 동일 구조 복제, 사진·텍스트만 골프용으로 교체.
스타일(좌표·폰트·색)은 바레 함수를 그대로 호출 — 추측 0.

캔버스: 1080x1080
구조:
  ig_01 표지   = 사진 상단 65%(듀오톤) + 검정 하단 35% 정보영역
  ig_02~04 본문 = 전체 사진 fill + 하단 그라디언트 + 좌하단 텍스트 + 우상단 칩
  ig_05 가이드  = guideline_card_golf.jpg (골프 전용 가이드카드)

편 구성:
  ep1 — "코스에 서다"     (ig_01~05)
  ep2 — "시상대에 서다"   (ig_01~05)
  ep3 — "비결은 프로였다" (ig_01~05)
"""
from __future__ import annotations

import sys
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

# 캐논 값 단일출처 직독 (ssot/canon_values.json)
sys.path.insert(0, str(Path(__file__).parent.parent))
from ssot.canon import canon_get
_INQUIRY_URL = "문의 :  " + canon_get("inquiry_path")

# ── 바레 SSOT import ─────────────────────────────────────────────────────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from brand_constants import (
    PROJECT_ROOT,
    BEIGE, BLACK_BG, WHITE, GRAY, CHIP_BEIGE, SEP_LINE,
    FONT_BOLD, FONT_SEMIBOLD, FONT_MEDIUM,
)
from compose_barre import (
    W, H,
    to_duotone,
    load_font,
    center_crop_fill,
    apply_bottom_gradient,
    paste_logo,
    draw_chip,
    draw_counter,
    compose_guide_card,  # 표준 카드 (ep1·ep2는 미사용, 골프 전용으로 대체)
)

# 골프 전용 가이드카드 경로 (compose_guideline_card_golf.py 생성) — 완성 가이드 단일 보관소
_GOLF_GUIDE_CARD = PROJECT_ROOT / "instagram" / "_assets" / "각 업장 가이드" / "골프 가이드.jpg"


def compose_golf_guide_card(output_path: Path) -> None:
    """골프 전용 가이드카드 복사 (표준 compose_guide_card 대체 — barre 수정 금지)."""
    import shutil as _shutil
    if not _GOLF_GUIDE_CARD.exists():
        raise FileNotFoundError(f"골프 가이드카드 없음: {_GOLF_GUIDE_CARD}. "
                                f"python scripts/compose_guideline_card_golf.py 먼저 실행.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copy2(_GOLF_GUIDE_CARD, output_path)
    print(f"  [골프가이드] {output_path.name} ({output_path.stat().st_size // 1024}KB)")
# ─────────────────────────────────────────────────────────────────────────────

# 소스 사진 루트
_SRC = (
    PROJECT_ROOT
    / "instagram"
    / "Image"
    / "골프_유소년_주니어대회(원본 이미지)"
)
_MASKED = _SRC / "_faces_masked"  # 모자이크 처리본 폴더
_PFX = "KakaoTalk_20260618_135719893"

def _p(suffix: str) -> Path:
    """파일명 헬퍼 — suffix="" → .jpg / suffix="_01" → _01.jpg.
    PNG(김태엽 프로)는 원본 사용. 나머지는 모자이크본(_faces_masked/) 우선."""
    if suffix.endswith(".png"):
        # 김태엽 프로 PNG — 모자이크 예외, 원본 사용
        return _SRC / "KakaoTalk_20260618_135750819.png"
    name = f"{_PFX}.jpg" if suffix == "" else f"{_PFX}{suffix}.jpg"
    masked = _MASKED / name
    if masked.exists():
        return masked
    return _SRC / name  # 폴백: 원본


# ---------------------------------------------------------------------------
# 표지 (ig_01) — compose_ballet.py의 compose_cover 1:1 복제
# ---------------------------------------------------------------------------
def top_crop_fill(
    img_path: Path,
    w: int,
    h: int,
    x_bias: float = 0.5,
    top_bias: float = 0.18,
    zoom: float = 1.0,
) -> Image.Image:
    """표지용 — 상단(머리/얼굴)을 살리는 top-biased crop."""
    img = Image.open(img_path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    sw, sh = img.size
    tr = w / h
    sr = sw / sh
    if sr > tr:
        nw, nh = int(sh * tr), sh
    else:
        nw, nh = sw, int(sw / tr)
    nw = int(nw / zoom)
    nh = int(nh / zoom)
    x0 = int((sw - nw) * x_bias)
    y0 = int((sh - nh) * top_bias)
    img = img.crop((x0, y0, x0 + nw, y0 + nh))
    return img.resize((w, h), Image.LANCZOS)


def compose_cover(
    photo_path: Path,
    title_eng: str,
    title_kor: str,
    date_location: str,
    output_path: Path,
    cover_x_bias: float = 0.5,
    cover_zoom: float = 1.0,
) -> None:
    canvas = Image.new("RGB", (W, H), BLACK_BG)

    PHOTO_H = 700
    photo = top_crop_fill(photo_path, W, PHOTO_H, x_bias=cover_x_bias, zoom=cover_zoom)
    photo = to_duotone(photo, normalize=True)
    canvas.paste(photo, (0, 0))

    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(50, 701), (1030, 702)], fill=SEP_LINE)

    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)

    chip_font = load_font("bold", 24)
    chip_w, chip_h = 180, 48
    chip_x = W - 50 - chip_w
    chip_y = 60
    draw_chip(draw, "WELLPERION", chip_font, chip_x, chip_y, chip_w, chip_h)

    eng_font = load_font("bold", 58)
    draw.text((W // 2, 786), title_eng, font=eng_font, fill=BEIGE, anchor="mm")

    kor_font = load_font("semibold", 38)
    draw.text((W // 2, 860), title_kor, font=kor_font, fill=WHITE, anchor="mm")

    sub_line_y = 920
    draw.rectangle(
        [(W // 2 - 30, sub_line_y), (W // 2 + 30, sub_line_y + 2)],
        fill=BEIGE,
    )

    date_font = load_font("medium", 26)
    draw.text((W // 2, 962), date_location, font=date_font, fill=(166, 151, 139), anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [표지] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


# ---------------------------------------------------------------------------
# 스토리 슬라이드 — compose_ballet.py의 compose_story 1:1 복제
# ---------------------------------------------------------------------------
def compose_story(
    photo_path: Path,
    meta_line: str,
    title_kor: str,
    sub_text: str,
    footer_text: str,
    current: int,
    total: int,
    output_path: Path,
    chip_label: str = "WELLPERION",
    full_dark: bool = False,
    png_portrait: bool = False,
) -> None:
    if png_portrait:
        # PNG 프로필 카드 — 좌측 인물만 크롭: x_bias=0.05(좌측), zoom=1.9(우측 텍스트 밖으로), top_bias=0.04(얼굴 상단)
        canvas = top_crop_fill(photo_path, W, H, x_bias=0.05, top_bias=0.04, zoom=1.9)
        canvas = ImageEnhance.Brightness(canvas).enhance(0.90)
        canvas = apply_bottom_gradient(canvas, gradient_start_y=555)
    elif full_dark:
        canvas = center_crop_fill(photo_path, W, H)
        canvas = ImageEnhance.Brightness(canvas).enhance(0.95)
        canvas = apply_bottom_gradient(canvas, gradient_start_y=600)
    else:
        canvas = center_crop_fill(photo_path, W, H)
        canvas = ImageEnhance.Brightness(canvas).enhance(0.90)
        canvas = apply_bottom_gradient(canvas, gradient_start_y=555)

    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)

    chip_font = load_font("bold", 24)
    chip_w, chip_h = 180, 48
    chip_x = W - 50 - chip_w
    chip_y = 60
    draw_chip(draw, chip_label, chip_font, chip_x, chip_y, chip_w, chip_h)

    draw.line([(40, 772), (W - 40, 772)], fill=(150, 138, 120), width=1)

    meta_font = load_font("medium", 26)
    draw.text((40, 795), meta_line, font=meta_font, fill=BEIGE)

    title_font = load_font("bold", 64)
    draw.text((40, 860), title_kor, font=title_font, fill=WHITE)

    sub_font = load_font("medium", 30)
    sub_lines = sub_text.split("\n")
    if len(sub_lines) == 1:
        draw.text((40, 958), sub_text, font=sub_font, fill=BEIGE)
    else:
        sy = 936
        for sl in sub_lines:
            draw.text((40, sy), sl, font=sub_font, fill=BEIGE)
            sy += 40

    footer_font = load_font("bold", 26)
    draw.text((40, 1026), footer_text, font=footer_font, fill=WHITE)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [{current:02d}/{total:02d}] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


# ---------------------------------------------------------------------------
# 편별 생성 함수
# ---------------------------------------------------------------------------
FOOTER = "WELLPERION  ·  JUNIOR GOLF"
TOTAL = 5  # 표지 + 본문3 + 가이드

# M5 검수큐 엔트리 메타 (공식계정 wellperion · 기존 id 업데이트)
EP_META = {
    "ep1": ("CMO-2026-06-20-GOLF-EP1-COURSE", "골프 #1편 — 코스에 서다 (회사공식)"),
    "ep2": ("CMO-2026-06-20-GOLF-EP2-PODIUM", "골프 #2편 — 시상대에 서다 (회사공식)"),
    "ep3": ("CMO-2026-06-20-GOLF-EP3-COACH", "골프 #3편 — 비결은 프로였다 (회사공식)"),
}


def make_montage(ep_dir: Path) -> Path:
    """ig_01~05 가로 5연결 몽타주(검수 미리보기) 생성."""
    cell = 420
    imgs = [Image.open(ep_dir / f"ig_{i:02d}.jpg").convert("RGB").resize((cell, cell))
            for i in range(1, 6)]
    m = Image.new("RGB", (cell * 5, cell), (20, 20, 20))
    for i, im in enumerate(imgs):
        m.paste(im, (cell * i, 0))
    out = ep_dir / f"{ep_dir.name}_montage.jpg"
    m.save(out, "JPEG", quality=90)
    return out


def build_ep1(out_ep: Path) -> None:
    """1편 — 코스에 서다"""
    print("\n=== EP1: 코스에 서다 ===")

    # ig_01 표지: _01 (세로 여자아이 아이언 임팩트)
    compose_cover(
        photo_path=_p("_01"),
        title_eng="JUNIOR GOLF",
        title_kor="코스에 서다",
        date_location="2026 KPGA 주니어리그",
        output_path=out_ep / "ig_01.jpg",
        cover_x_bias=0.50,
        cover_zoom=1.20,
    )

    story_data = [
        # (photo, meta, title_kor, sub, full_dark)
        (_p("_12"), "JUNIOR GOLF  ·  2026 KPGA", "진짜 대회, 진짜 코스",
         "웰페리온 주니어가 출전했습니다", False),
        (_p(""),    "JUNIOR GOLF  ·  2026 KPGA", "제 발로 걷는 18홀",
         "누가 대신 쳐주지 않는 길", False),
        (_p("_09"), "JUNIOR GOLF  ·  2026 KPGA", "그리고, 결과는?",
         "다음 편에서", True),
    ]
    for idx, (photo, meta, title_kor, sub, full_dark) in enumerate(story_data, start=2):
        compose_story(
            photo_path=photo,
            meta_line=meta,
            title_kor=title_kor,
            sub_text=sub,
            footer_text=FOOTER,
            current=idx,
            total=TOTAL,
            output_path=out_ep / f"ig_{idx:02d}.jpg",
            full_dark=full_dark,
        )

    # ig_05 가이드카드
    compose_golf_guide_card(output_path=out_ep / "ig_05.jpg")


def build_ep2(out_ep: Path) -> None:
    """2편 — 시상대에 서다"""
    print("\n=== EP2: 시상대에 서다 ===")

    # ig_01 표지: _03 (시상대 트로피 3명)
    compose_cover(
        photo_path=_p("_03"),
        title_eng="ON THE PODIUM",
        title_kor="시상대에 서다",
        date_location="2026 KPGA 주니어리그 2회",
        output_path=out_ep / "ig_01.jpg",
        cover_x_bias=0.50,
        cover_zoom=1.10,
    )

    story_data = [
        # _05: 코치+아이 1:2 시상대 — KPGA 2회 배경, 레인보우 배너 없음
        (_p("_05"), "KPGA 주니어리그 2회", "해냈다는 증거",
         "시상대에 오른 순간", False),
        (_p("_06"), "KPGA 주니어리그 2회", "혼자가 아니었다",
         "함께 준비한 팀의 결과", False),
        # _07: 시상대 3인 다른 컷 (표지 _03 중복 제거 — 같은 사진 반복 금지)
        (_p("_07"), "KPGA 주니어리그 2회", "비결이 있었습니다",
         "다음 편에서", True),
    ]
    for idx, (photo, meta, title_kor, sub, full_dark) in enumerate(story_data, start=2):
        compose_story(
            photo_path=photo,
            meta_line=meta,
            title_kor=title_kor,
            sub_text=sub,
            footer_text=FOOTER,
            current=idx,
            total=TOTAL,
            output_path=out_ep / f"ig_{idx:02d}.jpg",
            full_dark=full_dark,
        )

    compose_golf_guide_card(output_path=out_ep / "ig_05.jpg")


def build_ep3(out_ep: Path) -> None:
    """3편 — 비결은 프로였다"""
    print("\n=== EP3: 비결은 프로였다 ===")

    # ig_01 표지: _02 (파란 하늘 티샷 — ep1 표지 _01 중복 제거)
    compose_cover(
        photo_path=_p("_02"),
        title_eng="THE PRO",
        title_kor="비결은 프로였다",
        date_location="웰페리온 골프",
        output_path=out_ep / "ig_01.jpg",
        cover_x_bias=0.50,
        cover_zoom=1.20,
    )

    # ig_02: PNG 프로필 카드 — 좌측 인물(검은 폴로)만 크롭, 우측 경력 텍스트 블록 제거
    # top_crop_fill + x_bias=0.05(좌측 치우침) + zoom=1.8(우측 텍스트 밖으로 잘라냄)
    # top_bias=0.05 → 얼굴이 상단에, 그라디언트(하단 텍스트)에 가리지 않게
    compose_story(
        photo_path=_p(".png"),
        meta_line="WELLPERION GOLF",
        title_kor="김태엽 투어프로",
        sub_text="KPGA 정회원 · 투어프로 · 주니어 전문",
        footer_text=FOOTER,
        current=2,
        total=TOTAL,
        output_path=out_ep / "ig_02.jpg",
        full_dark=False,
        png_portrait=True,  # PNG 인물 좌측 크롭 플래그
    )

    # ig_03~04: 일반 사진형
    story_data = [
        (_p("_11"),  "WELLPERION GOLF", "아이 몸에 맞춘 1:1",
         "성장 · 스윙 · 거리 맞춤", False),
        # _13: 연습장 타석 샷 (ep1·ep3 표지 _01 중복 제거 — 같은 사진 반복 금지)
        (_p("_13"),  "WELLPERION GOLF", "우리 아이도 함께",
         "체계적 주니어 육성", True),
    ]
    for idx, (photo, meta, title_kor, sub, full_dark) in enumerate(story_data, start=3):
        compose_story(
            photo_path=photo,
            meta_line=meta,
            title_kor=title_kor,
            sub_text=sub,
            footer_text=FOOTER,
            current=idx,
            total=TOTAL,
            output_path=out_ep / f"ig_{idx:02d}.jpg",
            full_dark=full_dark,
        )

    compose_golf_guide_card(output_path=out_ep / "ig_05.jpg")


# ---------------------------------------------------------------------------
# 캡션 파일 생성
# ---------------------------------------------------------------------------
_HASHTAGS = "#웰페리온 #WELLPERION #한남동골프 #유소년골프 #주니어골프 #KPGA #골프레슨 #스포츠클럽"
_CTA = "문의 : wellperion.com/ko/inquiry"


def write_captions(base_out: Path) -> None:
    captions = {
        "ep1": """\
코스에 서다.

진짜 대회, 진짜 코스 위에 섰습니다.

웰페리온 주니어들이 2026 KPGA 주니어리그에 출전했습니다.
캐디와 함께 18홀을 직접 걸으며, 누가 대신 쳐주지 않는 길을 완주했습니다.

그 결과가 궁금하신가요?
다음 편에서 이어집니다.

{cta}

{tags}""",
        "ep2": """\
시상대에 서다.

KPGA 주니어리그 2회, 웰페리온 주니어가 시상대에 올랐습니다.

상장을 받아 든 손.
혼자가 아닌, 함께 준비한 팀의 결과입니다.

비결이 무엇이냐고요?
다음 편에서 공개합니다.

{cta}

{tags}""",
        "ep3": """\
비결은 프로였다.

김태엽 투어프로.
KPGA 정회원이자 주니어 전문 프로입니다.

아이의 몸에 맞춘 스윙, 성장 단계에 맞는 거리 설계.
웰페리온 골프는 아이 한 명 한 명을 위한 1:1 레슨으로 주니어를 키웁니다.

우리 아이도 함께, 체계적으로.

{cta}

{tags}""",
    }

    for ep, text in captions.items():
        ep_dir = base_out / ep
        ep_dir.mkdir(parents=True, exist_ok=True)
        caption_path = ep_dir / "캡션.txt"
        caption_path.write_text(
            text.format(cta=_CTA, tags=_HASHTAGS),
            encoding="utf-8",
        )
        print(f"  [캡션] {caption_path.relative_to(PROJECT_ROOT)}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    base_ig = (
        PROJECT_ROOT
        / "instagram"
        / "260620_골프_유소년_KPGA주니어대회"
        / "output(인스타그램)"
    )
    base_master = (
        PROJECT_ROOT
        / "instagram"
        / "260620_골프_유소년_KPGA주니어대회"
        / "output"
    )

    # 소스 파일 존재 확인
    required = [
        _p(""), _p("_01"), _p("_03"), _p("_06"),
        _p("_09"), _p("_11"), _p("_12"), _p("_15"), _p(".png"),
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        for m in missing:
            print(f"[ERROR] 소스 없음: {m}")
        sys.exit(1)

    print("=== 골프 주니어대회 슬라이드 합성 (바레 SSOT import) ===")

    for ep, builder in [("ep1", build_ep1), ("ep2", build_ep2), ("ep3", build_ep3)]:
        ep_ig = base_ig / ep
        ep_ig.mkdir(parents=True, exist_ok=True)
        builder(ep_ig)

        # 마스터 폴더 동기화
        ep_master = base_master / ep
        ep_master.mkdir(parents=True, exist_ok=True)
        for f in sorted(ep_ig.glob("ig_*.jpg")):
            shutil.copy2(f, ep_master / f.name)

    # 캡션
    print("\n=== 캡션 작성 ===")
    write_captions(base_ig)

    # 몽타주(검수 미리보기) 생성
    print("\n=== 몽타주 생성 ===")
    montages = {}
    for ep in ["ep1", "ep2", "ep3"]:
        montages[ep] = make_montage(base_ig / ep)
        # 마스터 폴더에도 동기화
        shutil.copy2(montages[ep], base_master / ep / montages[ep].name)
        print(f"  [몽타주] {ep}/{montages[ep].name}")

    # M5 검수큐 재등록 (--register) — 공식계정 wellperion, 기존 id 업데이트 + 승인카드 발송
    if "--register" in sys.argv:
        print("\n=== M5 재등록 (공식계정 wellperion) ===")
        from publish_register import register_publish
        for ep in ["ep1", "ep2", "ep3"]:
            qid, title = EP_META[ep]
            ep_ig = base_ig / ep
            caption = (ep_ig / "캡션.txt").read_text(encoding="utf-8")
            slides = [f"ig_{i:02d}.jpg" for i in range(1, 6)]
            register_publish(
                content_folder=ep_ig,
                slug=f"260620_골프_{ep.upper()}",
                montage_path=montages[ep],
                caption=caption,
                location="웰페리온 스포츠클럽",
                account="wellperion",
                slides=slides,
                queue_id=qid,
                title=title,
                channel="인스타그램 (wellperion)",
                send_card=True,
            )

    print("\n=== 합성 완료 ===")
    for ep in ["ep1", "ep2", "ep3"]:
        ep_dir = base_ig / ep
        files = sorted(ep_dir.iterdir()) if ep_dir.exists() else []
        for f in files:
            if f.is_file():
                print(f"  {ep}/{f.name}  {f.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
