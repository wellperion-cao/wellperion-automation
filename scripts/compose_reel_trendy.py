"""릴스 v2 트렌디 엔진 — 세로 풀크롭 · 모션컷 · 키네틱 자막 · 컬러 그레이딩.

GM 반려(기존 켄번즈 슬라이드쇼·레터박스·무음 = '싸 보임') 대응. 무료 로컬만 사용:
MoviePy + imageio-ffmpeg(동봉 ffmpeg) + Pillow + numpy. 결제 0.

기존 make_reel.py 대비 4대 수술:
  1) 세로 풀화면 FILL 크롭(cover) — 레터박스 0. 가로 사진은 중앙(약간 상단 바이어스) 크롭.
  2) 에너지 모션 — 컷당 1.6초, 줌인↔줌아웃 교차 + 미세 팬 + ease-out 펀치감, 짧은 크로스디졸브.
  3) 키네틱 자막 — 등장 시 아래→위 슬라이드업 + 페이드인, 홀드, 컷 끝 페이드아웃. 풀바 금지,
     하단 그라데이션 스크림으로 가독성만. Pretendard-Bold.
  4) 컬러 그레이딩 통일 — 대비 +10% · 채도 +5% · 따뜻한 화이트밸런스 · 약한 비네팅.
  + 상단 WELLPERION 워드마크(반투명·고정), 마지막 컷 CTA 강조.

사용:
  python scripts/compose_reel_trendy.py \
    --content-folder "instagram/260629_공식_시설투어_릴스" \
    --out 260629_공식_시설투어_릴스_v2
  옵션: --images-dir <폴더> · --captions <txt> · --sec 1.6 · --music <mp3>
출력: instagram/Movie/{out}_{timestamp}.mp4 (1080x1920 @30fps, H.264)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
from moviepy import VideoClip, concatenate_videoclips, AudioFileClip
from moviepy.video.fx import CrossFadeIn
from moviepy.audio.fx import AudioFadeOut

PROJECT_ROOT = Path(r"C:\Users\jjky0\welperion-automation")
MOVIE_DIR = PROJECT_ROOT / "instagram" / "Movie"

# 폰트 (실제 존재 경로 자동 선택)
_FONT_DIR_CANDIDATES = [
    PROJECT_ROOT / "2. 브랜드_공식문서" / "02_로고&워터마크&FONT" / "font",
    PROJECT_ROOT / "2. 브랜드_공식문서" / "font",
    PROJECT_ROOT / "brand" / "font",
]
FONT_DIR = next((d for d in _FONT_DIR_CANDIDATES if (d / "Pretendard-Bold.otf").exists()),
                _FONT_DIR_CANDIDATES[0])
FONT_BOLD = FONT_DIR / "Pretendard-Bold.otf"
FONT_MEDIUM = FONT_DIR / "Pretendard-Medium.otf"

# 릴스 캔버스
W, H = 1080, 1920
FPS = 30

# 타이밍
DEFAULT_SEC = 1.6        # 컷당 노출(초)
CROSSFADE_SEC = 0.18     # 컷 전환 크로스디졸브
CAP_IN_SEC = 0.30        # 자막 슬라이드업+페이드인
CAP_OUT_SEC = 0.20       # 자막 페이드아웃
CAP_SLIDE_PX = 34        # 자막 슬라이드업 거리(px)
MUSIC_FADEOUT_SEC = 0.6

# 켄번즈 줌 헤드룸 (플레이트는 캔버스보다 ZOOM배 크게 cover)
ZOOM = 1.18
PAN_FRAC = 0.018         # 미세 팬: 가용 슬랙의 ±비율
TOP_BIAS = 0.12          # cover 세로 슬랙에서 상단 바이어스(0=중앙, 0.5=완전상단)

IMG_EXTS = (".jpg", ".jpeg", ".png")
CAPTION_FILENAME = "reel_captions.txt"


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def _load_font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if weight == "bold" else FONT_MEDIUM
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# 입력 수집
# ---------------------------------------------------------------------------

def collect_images(args: argparse.Namespace) -> tuple[list[Path], str, Path]:
    """이미지 목록 · 출력 베이스명 · 소스 폴더 반환."""
    if args.images_dir:
        folder = _resolve(args.images_dir)
        if not folder.is_dir():
            sys.exit(f"[오류] --images-dir 폴더 없음: {folder}")
    elif args.content_folder:
        folder = _resolve(args.content_folder)
        # output(인스타그램) 또는 output 서브폴더 자동 탐색
        sub = None
        for name in ("output(인스타그램)", "output", "output(instagram)"):
            cand = folder / name
            if cand.is_dir():
                sub = cand
                break
        folder = sub or folder
    else:
        sys.exit("[오류] --images-dir 또는 --content-folder 필수")

    posts = sorted(p for p in folder.glob("post_*") if p.suffix.lower() in IMG_EXTS)
    imgs = posts or sorted(p for p in folder.iterdir() if p.suffix.lower() in IMG_EXTS)
    if not imgs:
        sys.exit(f"[오류] 이미지 없음: {folder}")
    base = args.out or folder.name
    return imgs, base, folder


def load_captions(args: argparse.Namespace, src_folder: Path, n: int) -> list[str]:
    cap_path: Path | None = None
    if args.captions:
        cap_path = _resolve(args.captions)
        if not cap_path.is_file():
            sys.exit(f"[오류] --captions 파일 없음: {cap_path}")
    else:
        cand = src_folder / CAPTION_FILENAME
        if cand.is_file():
            cap_path = cand
    if cap_path is None:
        return [""] * n
    raw = cap_path.read_text(encoding="utf-8").splitlines()
    caps = [line.rstrip() for line in raw if line.strip()]
    return (caps + [""] * n)[:n]


# ---------------------------------------------------------------------------
# 컬러 그레이딩 + cover 플레이트
# ---------------------------------------------------------------------------

def grade(img: Image.Image) -> Image.Image:
    """대비 +10% · 채도 +5% · 따뜻한 화이트밸런스. 톤 통일."""
    img = ImageEnhance.Contrast(img).enhance(1.10)
    img = ImageEnhance.Color(img).enhance(1.05)
    arr = np.asarray(img).astype(np.float32)
    # 따뜻한 WB: R 살짝 올리고 B 살짝 내림
    arr[..., 0] = np.clip(arr[..., 0] * 1.045, 0, 255)
    arr[..., 2] = np.clip(arr[..., 2] * 0.965, 0, 255)
    # 미세 밝기 리프트(어두운 톤 방지)
    arr = np.clip(arr * 1.01 + 2.0, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def cover_plate(img_path: Path) -> np.ndarray:
    """이미지를 (W*ZOOM)x(H*ZOOM) 에 cover(레터박스 0) — 가로는 상단 바이어스 크롭."""
    pw, ph = int(round(W * ZOOM)), int(round(H * ZOOM))
    img = Image.open(img_path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = grade(img)
    iw, ih = img.size
    s = max(pw / iw, ph / ih)  # cover
    nw, nh = int(round(iw * s)), int(round(ih * s))
    resized = img.resize((nw, nh), Image.LANCZOS)
    # 가로 슬랙 = 중앙 크롭 / 세로 슬랙 = 상단 바이어스(천장·공간 우선, 바닥 회피)
    x0 = (nw - pw) // 2
    slack_y = nh - ph
    y0 = int(round(slack_y * TOP_BIAS))
    plate = resized.crop((x0, y0, x0 + pw, y0 + ph))
    return np.asarray(plate)


# ---------------------------------------------------------------------------
# 고정 오버레이 레이어 (스크림 · 워드마크 · 비네팅)
# ---------------------------------------------------------------------------

def build_scrim() -> np.ndarray:
    """하단 그라데이션 스크림(투명→반투명 검정) RGBA. 풀바 금지 — 가독성만."""
    layer = np.zeros((H, W, 4), dtype=np.uint8)
    start = int(H * 0.52)
    top_layer = np.zeros((H, W, 4), dtype=np.uint8)
    ys = np.arange(start, H)
    frac = (ys - start) / max(1, (H - start))
    alpha = (frac ** 1.4 * 190).astype(np.uint8)  # 부드러운 ease, 최대 ~190
    top_layer[start:H, :, 3] = alpha[:, None]
    return top_layer


def build_wordmark() -> np.ndarray:
    """상단 WELLPERION 워드마크(반투명 흰색·자간) RGBA, 전 컷 고정."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _load_font(int(W * 0.030), "bold")
    text = "WELLPERION"
    tracking = int(W * 0.012)
    widths = [font.getbbox(c)[2] - font.getbbox(c)[0] for c in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = (W - total) // 2
    y = int(H * 0.045)
    for c, cw in zip(text, widths):
        draw.text((x, y), c, font=font, fill=(255, 255, 255, 150))
        x += cw + tracking
    return np.asarray(layer)


def build_vignette() -> np.ndarray:
    """약한 비네팅 곱셈 마스크 (H,W,1) float, 가장자리 어둡게."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2.0, H / 2.0
    nx = (xx - cx) / cx
    ny = (yy - cy) / cy
    r = np.sqrt(nx * nx + ny * ny)
    # r=0 중앙=1.0, 모서리(r≈1.41)≈0.82
    mask = 1.0 - 0.16 * np.clip((r - 0.55) / 0.85, 0, 1) ** 2
    return mask[:, :, None]


def build_caption_layer(caption: str, is_cta: bool) -> tuple[np.ndarray, int]:
    """자막 텍스트를 WxH 투명 캔버스 기준 위치에 렌더한 RGBA + 블록상단 y 반환."""
    if not caption.strip():
        return np.zeros((H, W, 4), dtype=np.uint8), H
    size = int(W * (0.072 if is_cta else 0.062))
    font = _load_font(size, "bold")
    margin = int(W * 0.08)
    max_w = W - 2 * margin

    # 자동 줄바꿈 (· 구분 우선 유지, 공백 기준 wrap)
    words = caption.replace(" · ", " ·§ ").split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip() if cur else w
        bb = font.getbbox(cand.replace("·§", "·"))
        if bb[2] - bb[0] <= max_w:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    lines = [ln.replace("·§", "·") for ln in lines]

    line_h = int(size * 1.28)
    block_h = line_h * len(lines)
    base_y = int(H * (0.74 if is_cta else 0.80)) - block_h

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cy = base_y
    for ln in lines:
        bb = font.getbbox(ln)
        tw = bb[2] - bb[0]
        x = (W - tw) // 2
        # 가벼운 그림자(가독성)
        draw.text((x + 2, cy + 2), ln, font=font, fill=(0, 0, 0, 150))
        draw.text((x, cy), ln, font=font, fill=(255, 255, 255, 255))
        cy += line_h
    return np.asarray(layer), base_y


# ---------------------------------------------------------------------------
# 합성 유틸
# ---------------------------------------------------------------------------

def _over(base_rgb: np.ndarray, layer_rgba: np.ndarray, alpha_mul: float = 1.0) -> np.ndarray:
    """base(float RGB) 위에 RGBA 레이어를 알파 합성."""
    a = layer_rgba[:, :, 3:4].astype(np.float32) / 255.0 * alpha_mul
    if a.max() <= 0:
        return base_rgb
    rgb = layer_rgba[:, :, :3].astype(np.float32)
    return base_rgb * (1.0 - a) + rgb * a


# 전역 고정 레이어 (1회 생성)
_SCRIM = build_scrim()
_WORDMARK = build_wordmark()
_VIGNETTE = build_vignette()
_PW, _PH = int(round(W * ZOOM)), int(round(H * ZOOM))


def make_cut(plate: np.ndarray, caption: str, sec: float, zoom_in: bool, pan_dir: int,
             is_cta: bool) -> VideoClip:
    """단일 컷 → VideoClip. cover 플레이트 위 켄번즈 + 키네틱 자막 + 고정 오버레이."""
    cap_layer, _ = build_caption_layer(caption, is_cta)

    def frame_fn(t: float) -> np.ndarray:
        prog = max(0.0, min(1.0, t / sec)) if sec > 0 else 0.0
        # ease-out (시작에 에너지 — 펀치감)
        eased = 1.0 - (1.0 - prog) ** 2
        if zoom_in:
            scale = 1.0 + (ZOOM - 1.0) * eased
        else:
            scale = ZOOM - (ZOOM - 1.0) * eased
        # 크롭 윈도우(스케일 클수록 작게=확대)
        cw = int(round(_PW / scale))
        ch = int(round(_PH / scale))
        cw = min(cw, _PW)
        ch = min(ch, _PH)
        slack_x = _PW - cw
        slack_y = _PH - ch
        # 미세 팬: 가로 슬랙 안에서 좌우 드리프트
        px = int(round(slack_x * (0.5 + pan_dir * PAN_FRAC * (eased - 0.5) * 2)))
        px = max(0, min(slack_x, px))
        py = slack_y // 2
        window = plate[py:py + ch, px:px + cw]
        frame = np.asarray(Image.fromarray(window).resize((W, H), Image.LANCZOS)).astype(np.float32)

        # 비네팅(곱셈)
        frame = frame * _VIGNETTE
        # 하단 스크림
        frame = _over(frame, _SCRIM)

        # 키네틱 자막: 슬라이드업 + 페이드인/홀드/페이드아웃
        if cap_layer[:, :, 3].max() > 0:
            if t < CAP_IN_SEC:
                p_in = t / CAP_IN_SEC
                alpha = p_in
                dy = int(round(CAP_SLIDE_PX * (1.0 - p_in)))
            elif t > sec - CAP_OUT_SEC:
                alpha = max(0.0, (sec - t) / CAP_OUT_SEC)
                dy = 0
            else:
                alpha = 1.0
                dy = 0
            cap = cap_layer if dy == 0 else np.roll(cap_layer, -dy, axis=0)
            frame = _over(frame, cap, alpha_mul=alpha)

        # 워드마크(고정)
        frame = _over(frame, _WORDMARK)
        return np.clip(frame, 0, 255).astype(np.uint8)

    return VideoClip(frame_fn, duration=sec).with_fps(FPS)


# ---------------------------------------------------------------------------
# 릴스 조립
# ---------------------------------------------------------------------------

def build_reel(imgs: list[Path], captions: list[str], base_name: str, sec: float,
               music: Path | None) -> tuple[Path, float]:
    MOVIE_DIR.mkdir(parents=True, exist_ok=True)
    n = len(imgs)
    clips = []
    for i, p in enumerate(imgs):
        plate = cover_plate(p)
        cap = captions[i] if i < len(captions) else ""
        is_cta = (i == n - 1)
        zoom_in = (i % 2 == 0)
        pan_dir = 1 if (i % 2 == 0) else -1
        clip = make_cut(plate, cap, sec, zoom_in, pan_dir, is_cta)
        if clips:
            clip = clip.with_effects([CrossFadeIn(CROSSFADE_SEC)])
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose", padding=-CROSSFADE_SEC)

    has_audio = False
    if music:
        audio = AudioFileClip(str(music))
        if audio.duration > video.duration:
            audio = audio.subclipped(0, video.duration)
        fade = min(MUSIC_FADEOUT_SEC, audio.duration)
        audio = audio.with_effects([AudioFadeOut(fade)])
        video = video.with_audio(audio)
        has_audio = True

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = MOVIE_DIR / f"{base_name}_{ts}.mp4"
    video.write_videofile(
        str(out_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac" if has_audio else None,
        preset="medium",
        bitrate="8000k",
        logger=None,
    )
    duration = video.duration
    video.close()
    return out_path, duration


def main() -> None:
    parser = argparse.ArgumentParser(description="릴스 v2 트렌디 엔진 (세로풀크롭·모션·키네틱자막·그레이딩)")
    parser.add_argument("--content-folder", help="콘텐츠 폴더 (output(인스타그램)/post_* 자동 탐색)")
    parser.add_argument("--images-dir", help="이미지 폴더 직접 지정 (post_*.jpg 순서)")
    parser.add_argument("--out", help="출력 파일명 베이스 (기본: 폴더명)")
    parser.add_argument("--sec", type=float, default=DEFAULT_SEC, help=f"컷당 노출 초 (기본 {DEFAULT_SEC})")
    parser.add_argument("--captions", help="캡션 txt (줄당 1캡션). 없으면 소스폴더 reel_captions.txt")
    parser.add_argument("--music", help="배경음악 mp3/m4a/wav (선택). 없으면 무음.")
    args = parser.parse_args()

    imgs, base, src_folder = collect_images(args)
    captions = load_captions(args, src_folder, len(imgs))

    music = None
    if args.music:
        music = _resolve(args.music)
        if not music.is_file():
            sys.exit(f"[오류] --music 파일 없음: {music}")

    print(f"[엔진] 릴스 v2 트렌디 — 세로풀크롭·모션·키네틱자막·그레이딩")
    print(f"[소스] {src_folder}")
    print(f"[이미지] {len(imgs)}장 · 컷당 {args.sec}s · 크로스디졸브 {CROSSFADE_SEC}s")
    for i, p in enumerate(imgs):
        cap = captions[i] if i < len(captions) else ""
        print(f"   {i+1:02d}. {p.name}  | {cap}")
    print(f"[음악] {music.name if music else '무음'}")

    out_path, duration = build_reel(imgs, captions, base, args.sec, music)

    print("\n[완료] 릴스 v2 생성")
    print(f"   경로  : {out_path}")
    print(f"   길이  : {duration:.2f}초")
    print(f"   해상도: {W}x{H} @ {FPS}fps (H.264/libx264) · cover 풀크롭(레터박스 0)")


if __name__ == "__main__":
    main()
