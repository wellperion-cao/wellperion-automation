"""무료 영상 자동 제작 파이프라인 — 슬라이드/이미지 → 세로 릴스 MP4.

웰페리온 디자이너(시디)용 도구. 결제 0 — MoviePy + imageio-ffmpeg(동봉 ffmpeg)만 사용.

입력  : --images-dir <폴더>  그 폴더의 post_*.jpg / *.png 를 순서대로
        --content-folder <instagram/...>  그 안의 output/post_*.jpg 를 순서대로
출력  : instagram/Movie/{name}_{timestamp}.mp4  (세로 릴스 1080x1920, H.264, fps 30)

규칙(GM 확정 2026-06-04):
  - 입력 이미지 원본 = instagram/Image/ 또는 콘텐츠 폴더 output
  - 출력 영상 = instagram/Movie/  (없으면 자동 생성)
  - 비율 다른 이미지는 1080x1920 캔버스에 센터핏(레터박스, 브랜드 배경색)

사용 예:
  python scripts/make_reel.py --content-folder "instagram/260604_AI6_작은가게도AI팀을가질수있다" --out AI6_test
  python scripts/make_reel.py --images-dir "instagram/Image/바레_런칭(원본 이미지)" --sec 3.0
  python scripts/make_reel.py --images-dir <폴더> --music bgm.mp3
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from moviepy import ImageClip, concatenate_videoclips, AudioFileClip
from moviepy.video.fx import CrossFadeIn

PROJECT_ROOT = Path(r"C:\Users\jjky0\welperion-automation")
MOVIE_DIR = PROJECT_ROOT / "instagram" / "Movie"

# 릴스 캔버스
W, H = 1080, 1920
FPS = 30
BRAND_BG = (34, 31, 32)  # #221F20 웰페리온 다크 배경

# 기본 타이밍
DEFAULT_SEC = 2.5
FADE_SEC = 0.4

IMG_EXTS = (".jpg", ".jpeg", ".png")


def _resolve(p: str) -> Path:
    """상대경로면 프로젝트 루트 기준으로 절대경로화."""
    path = Path(p)
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def collect_images(args: argparse.Namespace) -> tuple[list[Path], str]:
    """입력 옵션에서 이미지 경로 목록과 기본 출력명을 반환."""
    if args.images_dir:
        folder = _resolve(args.images_dir)
        if not folder.is_dir():
            sys.exit(f"[오류] --images-dir 폴더 없음: {folder}")
        # post_*.jpg 우선, 없으면 모든 이미지
        posts = sorted(p for p in folder.glob("post_*") if p.suffix.lower() in IMG_EXTS)
        imgs = posts or sorted(p for p in folder.iterdir() if p.suffix.lower() in IMG_EXTS)
        base = args.out or folder.name
        return imgs, base

    if args.content_folder:
        folder = _resolve(args.content_folder)
        out_dir = folder / "output"
        if not out_dir.is_dir():
            sys.exit(f"[오류] 콘텐츠 폴더에 output/ 없음: {out_dir}")
        imgs = sorted(p for p in out_dir.glob("post_*") if p.suffix.lower() in IMG_EXTS)
        base = args.out or folder.name
        return imgs, base

    sys.exit("[오류] --images-dir 또는 --content-folder 중 하나는 필수")


def fit_canvas(img_path: Path) -> np.ndarray:
    """이미지를 1080x1920 캔버스에 센터핏(레터박스, 브랜드 배경)으로 올려 RGB 배열 반환."""
    img = Image.open(img_path)
    # EXIF 회전 보정
    img = ImageOps.exif_transpose(img).convert("RGB")
    # 캔버스 비율에 맞춰 잘림 없이 contain
    fitted = ImageOps.contain(img, (W, H), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), BRAND_BG)
    x = (W - fitted.width) // 2
    y = (H - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return np.asarray(canvas)


def build_reel(imgs: list[Path], base_name: str, sec: float, music: Path | None) -> tuple[Path, float]:
    """이미지 목록으로 릴스 MP4를 생성하고 (출력경로, 길이초)를 반환."""
    MOVIE_DIR.mkdir(parents=True, exist_ok=True)

    clips = []
    for i, p in enumerate(imgs):
        frame = fit_canvas(p)
        clip = ImageClip(frame).with_duration(sec).with_fps(FPS)
        # 첫 장 외에는 크로스페이드 인 → concatenate에서 음수 패딩으로 겹침
        if i > 0:
            clip = clip.with_effects([CrossFadeIn(FADE_SEC)])
        clips.append(clip)

    # 인접 클립을 FADE_SEC 만큼 겹쳐 크로스페이드 연결
    video = concatenate_videoclips(clips, method="compose", padding=-FADE_SEC)

    if music:
        audio = AudioFileClip(str(music))
        if audio.duration > video.duration:
            audio = audio.subclipped(0, video.duration)
        video = video.with_audio(audio)

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = MOVIE_DIR / f"{base_name}_{ts}.mp4"

    video.write_videofile(
        str(out_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac" if music else None,
        preset="medium",
        logger=None,
    )
    duration = video.duration
    video.close()
    return out_path, duration


def main() -> None:
    parser = argparse.ArgumentParser(description="슬라이드/이미지 → 세로 릴스 MP4 (무료)")
    src = parser.add_argument_group("입력 (택1)")
    src.add_argument("--images-dir", help="이미지 폴더 (post_*.jpg/png 순서대로)")
    src.add_argument("--content-folder", help="콘텐츠 폴더 (그 안 output/post_*.jpg)")
    parser.add_argument("--out", help="출력 파일명 베이스 (기본: 폴더명)")
    parser.add_argument("--sec", type=float, default=DEFAULT_SEC, help=f"이미지당 노출 초 (기본 {DEFAULT_SEC})")
    parser.add_argument("--music", help="배경음악 mp3 (선택, 영상 길이에 맞춤)")
    args = parser.parse_args()

    imgs, base = collect_images(args)
    if not imgs:
        sys.exit("[오류] 이미지를 찾지 못함")

    music = _resolve(args.music) if args.music else None
    if music and not music.is_file():
        sys.exit(f"[오류] --music 파일 없음: {music}")

    print(f"[입력] 이미지 {len(imgs)}장:")
    for p in imgs:
        print(f"   - {p.name}")
    if music:
        print(f"[음악] {music.name}")

    out_path, duration = build_reel(imgs, base, args.sec, music)

    print("\n[완료] 릴스 생성")
    print(f"   경로  : {out_path}")
    print(f"   길이  : {duration:.2f}초")
    print(f"   해상도: {W}x{H} @ {FPS}fps (H.264/libx264)")


if __name__ == "__main__":
    main()
