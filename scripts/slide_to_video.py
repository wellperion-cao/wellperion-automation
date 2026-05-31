"""웰페리온 슬라이드 → Reels 영상 생성기 v1.0
JPG 슬라이드 시퀀스를 MP4(H.264)로 변환.

moviepy 우선, 미설치 시 ffmpeg CLI 폴백.
ffmpeg도 없으면 친절한 설치 안내 출력.

CLI:
    python scripts/slide_to_video.py --slides <폴더> [--sec 2.5] [--ratio 9:16] [--bgm <path>] [--out <path>]

출력: <콘텐츠폴더>/{폴더명}_reels.mp4  (--out 지정 시 해당 경로)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# 브랜드 레터박스 배경색 (웰페리온 다크 #221F20)
BRAND_BG = (34, 31, 32)

# 비율 → 해상도 매핑
RATIO_MAP = {
    "9:16": (1080, 1920),  # Reels 기본
    "1:1":  (1080, 1080),  # 피드 정방형
    "4:5":  (1080, 1350),  # 피드 세로
    "16:9": (1920, 1080),  # 가로
}


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

def resolve_slides(slides_path: Path) -> list[Path]:
    """폴더 또는 파일 목록에서 JPG/PNG 시퀀스 반환 (정렬)."""
    if slides_path.is_dir():
        files = sorted(
            p for p in slides_path.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
            and "output" not in p.parts  # output 하위폴더 제외
        )
    else:
        raise ValueError(f"--slides 경로가 존재하지 않거나 폴더가 아닙니다: {slides_path}")
    if not files:
        raise ValueError(f"슬라이드 JPG/PNG 파일이 없습니다: {slides_path}")
    return files


def default_output(slides_path: Path) -> Path:
    """기본 출력 경로: <폴더>/{폴더명}_reels.mp4"""
    return slides_path / f"{slides_path.name}_reels.mp4"


# ──────────────────────────────────────────────
# moviepy 구현
# ──────────────────────────────────────────────

def build_with_moviepy(
    slides: list[Path],
    out: Path,
    sec: float,
    resolution: tuple[int, int],
    bgm: Path | None,
    fade: bool,
) -> None:
    try:
        from moviepy import ImageClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip
        from moviepy import vfx
    except ImportError:
        raise ImportError("moviepy")

    from PIL import Image as PILImage
    import numpy as np

    W, H = resolution
    clips = []

    for img_path in slides:
        img = PILImage.open(img_path).convert("RGB")
        iw, ih = img.size

        # 레터박스: 브랜드 배경 위에 center-fit
        scale = min(W / iw, H / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        img_resized = img.resize((nw, nh), PILImage.LANCZOS)
        canvas = PILImage.new("RGB", (W, H), BRAND_BG)
        x_off = (W - nw) // 2
        y_off = (H - nh) // 2
        canvas.paste(img_resized, (x_off, y_off))

        frame = np.array(canvas)
        clip = ImageClip(frame, duration=sec)

        if fade:
            clip = clip.with_effects([vfx.FadeIn(0.3), vfx.FadeOut(0.3)])

        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")

    if bgm and bgm.exists():
        audio = AudioFileClip(str(bgm))
        if audio.duration < video.duration:
            audio = audio.with_effects([vfx.AudioLoop(duration=video.duration)])
        else:
            audio = audio.subclipped(0, video.duration)
        video = video.with_audio(audio)

    video.write_videofile(
        str(out),
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        logger=None,
    )
    print(f"[moviepy] 완료: {out}")


# ──────────────────────────────────────────────
# ffmpeg CLI 구현
# ──────────────────────────────────────────────

def _check_ffmpeg() -> bool:
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def build_with_ffmpeg(
    slides: list[Path],
    out: Path,
    sec: float,
    resolution: tuple[int, int],
    bgm: Path | None,
    fade: bool,
) -> None:
    if not _check_ffmpeg():
        raise RuntimeError("ffmpeg_not_found")

    W, H = resolution
    tmp_dir = out.parent / "_ffmpeg_tmp"
    tmp_dir.mkdir(exist_ok=True)

    # 각 슬라이드를 레터박스 처리한 임시 PNG로 저장
    from PIL import Image as PILImage
    prepared: list[Path] = []
    for i, img_path in enumerate(slides):
        img = PILImage.open(img_path).convert("RGB")
        iw, ih = img.size
        scale = min(W / iw, H / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        img_resized = img.resize((nw, nh), PILImage.LANCZOS)
        canvas = PILImage.new("RGB", (W, H), BRAND_BG)
        canvas.paste(img_resized, ((W - nw) // 2, (H - nh) // 2))
        tmp_path = tmp_dir / f"slide_{i:04d}.png"
        canvas.save(tmp_path)
        prepared.append(tmp_path)

    # concat demuxer 입력 파일 생성
    concat_txt = tmp_dir / "concat.txt"
    with open(concat_txt, "w", encoding="utf-8") as f:
        for p in prepared:
            f.write(f"file '{p.as_posix()}'\n")
            f.write(f"duration {sec}\n")
        # 마지막 프레임 반복 (ffmpeg concat 요구사항)
        f.write(f"file '{prepared[-1].as_posix()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-vf", f"fps=30,scale={W}:{H}",
        "-c:v", "libx264",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
    ]

    if bgm and bgm.exists():
        cmd += ["-i", str(bgm), "-shortest", "-c:a", "aac"]

    cmd.append(str(out))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-2000:], file=sys.stderr)
        raise RuntimeError(f"ffmpeg 변환 실패 (exit {result.returncode})")

    # 임시 파일 정리
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"[ffmpeg] 완료: {out}")


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="웰페리온 슬라이드 JPG → Reels MP4 변환기 v1.0"
    )
    parser.add_argument("--slides", required=True, help="슬라이드 JPG가 있는 폴더 경로")
    parser.add_argument("--sec",    type=float, default=2.5, help="장당 표시 초 (기본 2.5)")
    parser.add_argument("--ratio",  default="9:16", choices=list(RATIO_MAP.keys()),
                        help="출력 비율 (기본 9:16 Reels)")
    parser.add_argument("--bgm",    default=None, help="배경음악 파일 경로 (선택)")
    parser.add_argument("--out",    default=None, help="출력 MP4 경로 (기본: 슬라이드폴더/{폴더명}_reels.mp4)")
    parser.add_argument("--fade",   action="store_true", help="슬라이드 간 페이드 전환 (moviepy 전용)")
    parser.add_argument("--engine", choices=["auto", "moviepy", "ffmpeg"], default="auto",
                        help="변환 엔진 선택 (기본 auto: moviepy 우선)")
    args = parser.parse_args()

    slides_path = Path(args.slides)
    try:
        slides = resolve_slides(slides_path)
    except ValueError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)

    resolution = RATIO_MAP[args.ratio]
    out = Path(args.out) if args.out else default_output(slides_path)
    bgm = Path(args.bgm) if args.bgm else None

    print(f"슬라이드 {len(slides)}장 → {args.ratio} {resolution[0]}×{resolution[1]}, {args.sec}s/장")
    print(f"출력: {out}")

    errors: list[str] = []

    # moviepy 시도
    if args.engine in ("auto", "moviepy"):
        try:
            build_with_moviepy(slides, out, args.sec, resolution, bgm, args.fade)
            return
        except ImportError:
            errors.append("moviepy 미설치")
        except Exception as e:
            errors.append(f"moviepy 오류: {e}")

    # ffmpeg 폴백
    if args.engine in ("auto", "ffmpeg"):
        try:
            build_with_ffmpeg(slides, out, args.sec, resolution, bgm, args.fade)
            return
        except RuntimeError as e:
            if "ffmpeg_not_found" in str(e):
                errors.append("ffmpeg 미설치")
            else:
                errors.append(f"ffmpeg 오류: {e}")
        except Exception as e:
            errors.append(f"ffmpeg 오류: {e}")

    # 둘 다 실패
    print("\n[오류] 영상 생성 엔진을 찾지 못했습니다.", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    print("\n설치 안내:", file=sys.stderr)
    print("  moviepy:  pip install moviepy pillow", file=sys.stderr)
    print("  ffmpeg:   https://ffmpeg.org/download.html (Windows: winget install ffmpeg)", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
