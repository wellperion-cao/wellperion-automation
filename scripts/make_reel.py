"""무료 영상 자동 제작 파이프라인 v2 — 슬라이드/이미지 → 움직이는 세로 릴스 MP4.

웰페리온 디자이너(시디)용 도구. 결제 0 — MoviePy + imageio-ffmpeg(동봉 ffmpeg) + Pillow만 사용.
저작권 음악 자동 다운로드 없음 — 음원은 GM/시디가 직접 받아 --music 으로 넣는다.

입력  : --images-dir <폴더>  그 폴더의 post_*.jpg / *.png 를 순서대로
        --content-folder <instagram/...>  그 안의 output/post_*.jpg 를 순서대로
출력  : instagram/Movie/{name}_{timestamp}.mp4  (세로 릴스 1080x1920, H.264, fps 30)

v2 강화(GM 지시 2026-06-04):
  - Ken Burns 움직임: 이미지마다 느린 줌인/줌아웃 — 정적 슬라이드쇼가 아닌 '움직이는 영상'.
    옵션 --motion(기본 on) / --no-motion(끔). 1080x1920 비율 유지·잘림 최소.
  - 자막/텍스트 오버레이(선택): PIL(Pretendard)로 프레임에 직접 렌더 — ImageMagick 의존 없음.
    캡션 입력: --captions <txt>(줄당 1캡션) 또는 콘텐츠/이미지 폴더의 reel_captions.txt.
    없으면 자막 없이 진행.
  - 음악 견고화: --music <mp3> 를 영상 길이에 맞춰 자동 트림 + 끝 0.5초 페이드아웃.

규칙(GM 확정 2026-06-04):
  - 입력 이미지 원본 = instagram/Image/ 또는 콘텐츠 폴더 output
  - 출력 영상 = instagram/Movie/  (없으면 자동 생성)
  - 비율 다른 이미지는 1080x1920 캔버스에 센터핏(레터박스, 브랜드 배경색)

사용 예:
  python scripts/make_reel.py --content-folder "instagram/260604_AI6_작은가게도AI팀을가질수있다" --out AI6_test
  python scripts/make_reel.py --images-dir "instagram/Image/바레_런칭(원본 이미지)" --sec 3.0 --no-motion
  python scripts/make_reel.py --images-dir <폴더> --music bgm.mp3 --captions caps.txt
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Windows 콘솔(CP949)에서 한글·em-dash 등 출력 시 인코딩 에러 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from moviepy import ImageClip, VideoClip, concatenate_videoclips, AudioFileClip
from moviepy.video.fx import CrossFadeIn
from moviepy.audio.fx import AudioFadeOut

PROJECT_ROOT = Path(r"C:\Users\jjky0\welperion-automation")
MOVIE_DIR = PROJECT_ROOT / "instagram" / "Movie"

# 폰트 위치 후보 (slide_compositor 와 동일 — 실제 존재 경로 자동 선택)
_FONT_DIR_CANDIDATES = [
    PROJECT_ROOT / "brand" / "font",
    PROJECT_ROOT / "2. 브랜드_공식문서" / "font",
]
FONT_DIR = next((d for d in _FONT_DIR_CANDIDATES if d.exists()), _FONT_DIR_CANDIDATES[0])
FONT_BOLD = FONT_DIR / "Pretendard-Bold.otf"
FONT_SEMIBOLD = FONT_DIR / "Pretendard-SemiBold.otf"

# 릴스 캔버스
W, H = 1080, 1920
FPS = 30
BRAND_BG = (34, 31, 32)       # #221F20 웰페리온 다크 배경
BRAND_BEIGE = (183, 159, 138)  # #B79F8A

# 기본 타이밍
DEFAULT_SEC = 2.5
FADE_SEC = 0.4
MUSIC_FADEOUT_SEC = 0.5

# Ken Burns 줌 비율 (시작/끝 스케일 1.0 ~ KEN_BURNS_ZOOM)
KEN_BURNS_ZOOM = 1.12

IMG_EXTS = (".jpg", ".jpeg", ".png")
CAPTION_FILENAME = "reel_captions.txt"


def _resolve(p: str) -> Path:
    """상대경로면 프로젝트 루트 기준으로 절대경로화."""
    path = Path(p)
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def collect_images(args: argparse.Namespace) -> tuple[list[Path], str, Path]:
    """입력 옵션에서 (이미지 경로 목록, 기본 출력명, 소스 폴더)를 반환."""
    if args.images_dir:
        folder = _resolve(args.images_dir)
        if not folder.is_dir():
            sys.exit(f"[오류] --images-dir 폴더 없음: {folder}")
        posts = sorted(p for p in folder.glob("post_*") if p.suffix.lower() in IMG_EXTS)
        imgs = posts or sorted(p for p in folder.iterdir() if p.suffix.lower() in IMG_EXTS)
        base = args.out or folder.name
        return imgs, base, folder

    if args.content_folder:
        folder = _resolve(args.content_folder)
        out_dir = folder / "output"
        if not out_dir.is_dir():
            sys.exit(f"[오류] 콘텐츠 폴더에 output/ 없음: {out_dir}")
        imgs = sorted(p for p in out_dir.glob("post_*") if p.suffix.lower() in IMG_EXTS)
        base = args.out or folder.name
        return imgs, base, folder

    sys.exit("[오류] --images-dir 또는 --content-folder 중 하나는 필수")


def load_captions(args: argparse.Namespace, src_folder: Path, n: int) -> list[str]:
    """캡션 목록 로드. 우선순위: --captions > 소스폴더/reel_captions.txt > 없음.
    줄당 1캡션, 이미지 수에 맞춰 자르거나 빈 문자열로 채움. 빈 줄/주석(#) 무시 안 함(자막 없는 장은 빈 줄로)."""
    cap_path: Path | None = None
    if args.captions:
        cap_path = _resolve(args.captions)
        if not cap_path.is_file():
            sys.exit(f"[오류] --captions 파일 없음: {cap_path}")
    else:
        candidate = src_folder / CAPTION_FILENAME
        if candidate.is_file():
            cap_path = candidate

    if cap_path is None:
        return [""] * n

    raw = cap_path.read_text(encoding="utf-8").splitlines()
    caps = [line.rstrip() for line in raw]
    # 이미지 수에 맞춤
    caps = (caps + [""] * n)[:n]
    return caps


def _load_font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    """Pretendard 폰트 로드. 없으면 PIL 기본 폰트로 폴백(에러 대신 진행)."""
    path = FONT_BOLD if weight == "bold" else FONT_SEMIBOLD
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """캡션 자동 줄바꿈(공백 기준, 원본 개행 보존)."""
    out: list[str] = []
    for orig in text.split("\n"):
        if not orig.strip():
            continue
        words = orig.split(" ")
        cur = ""
        for w in words:
            cand = (cur + " " + w).strip() if cur else w
            bbox = font.getbbox(cand)
            if bbox[2] - bbox[0] <= max_w:
                cur = cand
            else:
                if cur:
                    out.append(cur)
                cur = w
        if cur:
            out.append(cur)
    return out


def fit_canvas(img_path: Path, scale: float = 1.0) -> np.ndarray:
    """이미지를 (W*scale)x(H*scale) 캔버스에 센터핏(레터박스, 브랜드 배경)으로 올려 RGB 배열 반환.
    scale>1 이면 Ken Burns 줌 여유분(오버샘플) 확보용 큰 소스 프레임."""
    cw, ch = int(round(W * scale)), int(round(H * scale))
    img = Image.open(img_path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    fitted = ImageOps.contain(img, (cw, ch), Image.LANCZOS)
    canvas = Image.new("RGB", (cw, ch), BRAND_BG)
    x = (cw - fitted.width) // 2
    y = (ch - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return np.asarray(canvas)


def draw_caption(frame: np.ndarray, caption: str) -> np.ndarray:
    """프레임(RGB ndarray) 하단에 PIL로 캡션을 렌더해 돌려준다. ImageMagick 의존 없음."""
    if not caption.strip():
        return frame
    img = Image.fromarray(frame).convert("RGB")
    cw, ch = img.size
    draw = ImageDraw.Draw(img)

    margin = int(cw * 0.08)
    max_w = cw - 2 * margin
    font = _load_font(int(cw * 0.055), "bold")
    lines = _wrap(caption, font, max_w)
    line_h = int(font.size * 1.3)
    block_h = line_h * len(lines)

    # 하단 18% 지점 기준으로 텍스트 블록 배치
    base_y = int(ch * 0.82) - block_h

    # 가독성용 반투명 그라데이션 띠(아래쪽 어둡게)
    band = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(band)
    band_top = max(0, base_y - int(line_h * 0.6))
    bdraw.rectangle([0, band_top, cw, ch], fill=(0, 0, 0, 120))
    img = Image.alpha_composite(img.convert("RGBA"), band).convert("RGB")
    draw = ImageDraw.Draw(img)

    cy = base_y
    for line in lines:
        bbox = font.getbbox(line)
        tw = bbox[2] - bbox[0]
        x = (cw - tw) // 2
        # 외곽선(가독성) — 어두운 테두리
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            draw.text((x + dx, cy + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, cy), line, font=font, fill=(255, 255, 255))
        cy += line_h
    return np.asarray(img)


def make_clip(img_path: Path, caption: str, sec: float, motion: bool):
    """단일 이미지 → (sec초) 클립. motion이면 Ken Burns 줌, 아니면 정적."""
    idx_zoom_in = make_clip._counter % 2 == 0
    make_clip._counter += 1

    if not motion:
        frame = fit_canvas(img_path, scale=1.0)
        frame = draw_caption(frame, caption)
        return ImageClip(frame).with_duration(sec).with_fps(FPS)

    # 오버샘플 소스(줌 여유분 포함) + 캡션 베이크.
    # draw_caption은 입력 크기에 비례해 폰트·여백을 잡으므로 오버샘플 좌표계에서 그대로 사용 가능.
    src = fit_canvas(img_path, scale=KEN_BURNS_ZOOM)
    if caption.strip():
        src = draw_caption(src, caption)
    sh, sw = src.shape[0], src.shape[1]

    def frame_function(t: float) -> np.ndarray:
        prog = max(0.0, min(1.0, t / sec)) if sec > 0 else 0.0
        # 줌인: 1.0→ZOOM, 줌아웃: ZOOM→1.0 (소스가 ZOOM배 크므로 crop 창 크기로 환산)
        if idx_zoom_in:
            scale = 1.0 + (KEN_BURNS_ZOOM - 1.0) * prog
        else:
            scale = KEN_BURNS_ZOOM - (KEN_BURNS_ZOOM - 1.0) * prog
        # crop 창: 출력 1080x1920 을 source 좌표계에서 scale 만큼 (작을수록 더 확대)
        crop_w = int(round(W * (KEN_BURNS_ZOOM / scale)))
        crop_h = int(round(H * (KEN_BURNS_ZOOM / scale)))
        crop_w = min(crop_w, sw)
        crop_h = min(crop_h, sh)
        x0 = (sw - crop_w) // 2
        y0 = (sh - crop_h) // 2
        window = src[y0:y0 + crop_h, x0:x0 + crop_w]
        # 출력 해상도로 리샘플
        out = Image.fromarray(window).resize((W, H), Image.LANCZOS)
        return np.asarray(out)

    return VideoClip(frame_function, duration=sec).with_fps(FPS)


make_clip._counter = 0  # type: ignore[attr-defined]


def build_reel(imgs: list[Path], captions: list[str], base_name: str,
               sec: float, motion: bool, music: Path | None) -> tuple[Path, float]:
    """이미지 목록으로 릴스 MP4를 생성하고 (출력경로, 길이초)를 반환."""
    MOVIE_DIR.mkdir(parents=True, exist_ok=True)

    make_clip._counter = 0  # type: ignore[attr-defined]
    clips = []
    for i, p in enumerate(imgs):
        cap = captions[i] if i < len(captions) else ""
        clip = make_clip(p, cap, sec, motion)
        if i > 0:
            clip = clip.with_effects([CrossFadeIn(FADE_SEC)])
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose", padding=-FADE_SEC)

    has_audio = False
    if music:
        audio = AudioFileClip(str(music))
        if audio.duration > video.duration:
            audio = audio.subclipped(0, video.duration)
        # 끝 0.5초 페이드아웃
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
        logger=None,
    )
    duration = video.duration
    video.close()
    return out_path, duration


def main() -> None:
    parser = argparse.ArgumentParser(description="슬라이드/이미지 → 움직이는 세로 릴스 MP4 (무료)")
    src = parser.add_argument_group("입력 (택1)")
    src.add_argument("--images-dir", help="이미지 폴더 (post_*.jpg/png 순서대로)")
    src.add_argument("--content-folder", help="콘텐츠 폴더 (그 안 output/post_*.jpg)")
    parser.add_argument("--out", help="출력 파일명 베이스 (기본: 폴더명)")
    parser.add_argument("--sec", type=float, default=DEFAULT_SEC, help=f"이미지당 노출 초 (기본 {DEFAULT_SEC})")
    parser.add_argument("--music", help="배경음악 mp3 (선택, 영상 길이에 맞춤 + 끝 0.5초 페이드아웃)")
    parser.add_argument("--captions", help="캡션 txt (줄당 1캡션). 없으면 소스폴더 reel_captions.txt 자동 탐색")
    parser.add_argument("--no-motion", dest="motion", action="store_false",
                        help="Ken Burns 움직임 끄기 (기본은 움직임 on)")
    parser.set_defaults(motion=True)
    args = parser.parse_args()

    imgs, base, src_folder = collect_images(args)
    if not imgs:
        sys.exit("[오류] 이미지를 찾지 못함")

    music = _resolve(args.music) if args.music else None
    if music and not music.is_file():
        sys.exit(f"[오류] --music 파일 없음: {music}")

    captions = load_captions(args, src_folder, len(imgs))
    n_caps = sum(1 for c in captions if c.strip())

    print(f"[입력] 이미지 {len(imgs)}장:")
    for i, p in enumerate(imgs):
        tag = f"  자막: {captions[i]}" if (i < len(captions) and captions[i].strip()) else ""
        print(f"   - {p.name}{tag}")
    print(f"[움직임] Ken Burns {'ON (줌인/줌아웃 교차)' if args.motion else 'OFF (정적)'}")
    print(f"[자막] {n_caps}장 적용 (PIL/Pretendard, ImageMagick 불필요)")
    if music:
        print(f"[음악] {music.name} (영상 길이 트림 + 끝 {MUSIC_FADEOUT_SEC}s 페이드아웃)")
    else:
        print("[음악] 없음 (무음) — 음원은 사람이 직접 받아 --music 으로 투입")

    out_path, duration = build_reel(imgs, captions, base, args.sec, args.motion, music)

    print("\n[완료] 릴스 생성")
    print(f"   경로  : {out_path}")
    print(f"   길이  : {duration:.2f}초")
    print(f"   해상도: {W}x{H} @ {FPS}fps (H.264/libx264)")
    print(f"   움직임: {'Ken Burns 적용' if args.motion else '정적'}")


if __name__ == "__main__":
    main()
