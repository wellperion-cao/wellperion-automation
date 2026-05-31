"""웰페리온 슬라이드 → Reels 영상 생성기 v2.0
JPG 슬라이드 시퀀스를 MP4(H.264)로 변환.

moviepy 우선, 미설치 시 ffmpeg CLI 폴백.
ffmpeg도 없으면 친절한 설치 안내 출력.

CLI:
    python scripts/slide_to_video.py --slides <폴더> [--sec 2.5] [--ratio 9:16]
        [--bgm <path>] [--out <path>] [--fade] [--engine auto|moviepy|ffmpeg]
        [--transition crossfade|slide|none]
        [--captions <txt|json>]
        [--batch <상위폴더>]

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

# Pretendard 폰트 경로 (설치된 경우 우선 사용)
_PRETENDARD_BOLD = Path(
    r"C:/Users/jjky0/Downloads/Pretendard-1.3.9/public/static/alternative/Pretendard-Bold.ttf"
)
_FALLBACK_FONT = Path(r"C:/Windows/Fonts/malgun.ttf")


def _find_font() -> Path | None:
    """Pretendard Bold → 맑은 고딕 → None 순으로 반환."""
    if _PRETENDARD_BOLD.exists():
        return _PRETENDARD_BOLD
    if _FALLBACK_FONT.exists():
        return _FALLBACK_FONT
    return None


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

def resolve_slides(slides_path: Path) -> list[Path]:
    """폴더 또는 파일 목록에서 JPG/PNG 시퀀스 반환 (정렬)."""
    if slides_path.is_dir():
        files = sorted(
            p for p in slides_path.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
            and not any(part.startswith("output") for part in p.parts)
        )
    else:
        raise ValueError(f"--slides 경로가 존재하지 않거나 폴더가 아닙니다: {slides_path}")
    if not files:
        raise ValueError(f"슬라이드 JPG/PNG 파일이 없습니다: {slides_path}")
    return files


def default_output(slides_path: Path) -> Path:
    """기본 출력 경로: <폴더>/{폴더명}_reels.mp4"""
    return slides_path / f"{slides_path.name}_reels.mp4"


def load_captions(captions_arg: str, slide_count: int) -> list[str]:
    """캡션 파일(txt 또는 json) 로드. 슬라이드 수보다 적으면 빈 문자열로 패딩."""
    p = Path(captions_arg)
    if not p.exists():
        print(f"[경고] 캡션 파일 없음: {p} — 자막 생략", file=sys.stderr)
        return [""] * slide_count

    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            texts = [str(x) for x in data]
        else:
            texts = list(data.values())
    else:
        # txt: 한 줄 = 한 슬라이드
        texts = [line.rstrip("\n") for line in p.read_text(encoding="utf-8").splitlines()]

    # 슬라이드 수에 맞춰 조정
    if len(texts) < slide_count:
        texts += [""] * (slide_count - len(texts))
    return texts[:slide_count]


def _letterbox_frame(img_path: Path, W: int, H: int):
    """PIL 이미지를 레터박스 처리한 numpy 배열 반환."""
    from PIL import Image as PILImage
    import numpy as np

    img = PILImage.open(img_path).convert("RGB")
    iw, ih = img.size
    scale = min(W / iw, H / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img_resized = img.resize((nw, nh), PILImage.LANCZOS)
    canvas = PILImage.new("RGB", (W, H), BRAND_BG)
    canvas.paste(img_resized, ((W - nw) // 2, (H - nh) // 2))
    return np.array(canvas)


def _add_caption_to_frame(frame_arr, text: str, W: int, H: int, font_path: Path | None):
    """numpy 배열(프레임)에 하단 캡션 오버레이 추가."""
    if not text.strip():
        return frame_arr

    from PIL import Image as PILImage, ImageDraw, ImageFont
    import numpy as np

    img = PILImage.fromarray(frame_arr)
    draw = ImageDraw.Draw(img)

    font_size = max(28, H // 40)
    font = None
    if font_path and font_path.exists():
        try:
            font = ImageFont.truetype(str(font_path), font_size)
        except Exception:
            font = None
    if font is None:
        try:
            font = ImageFont.load_default(size=font_size)
        except Exception:
            font = ImageFont.load_default()

    # 텍스트 크기 측정
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    # 배경 박스 (하단 여백 H//20)
    pad_x, pad_y = 20, 12
    margin_bottom = H // 20
    bx1 = (W - tw) // 2 - pad_x
    by1 = H - margin_bottom - th - pad_y * 2
    bx2 = (W + tw) // 2 + pad_x
    by2 = H - margin_bottom

    # 반투명 배경 (브랜드 다크 + 알파)
    overlay = PILImage.new("RGBA", img.size, (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rounded_rectangle([bx1, by1, bx2, by2], radius=8, fill=(34, 31, 32, 200))
    img = img.convert("RGBA")
    img = PILImage.alpha_composite(img, overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    tx = (W - tw) // 2
    ty = by1 + pad_y
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255))

    return np.array(img)


def _normalize_bgm(audio_clip, video_duration: float, target_lufs: float = -18.0):
    """BGM: 루프/트림 + 페이드인/아웃 + 볼륨 노멀라이즈."""
    from moviepy import vfx

    # 루프 또는 트림
    if audio_clip.duration < video_duration:
        audio_clip = audio_clip.with_effects([vfx.AudioLoop(duration=video_duration)])
    else:
        audio_clip = audio_clip.subclipped(0, video_duration)

    # 볼륨 노멀라이즈 (RMS 기반 간이 구현)
    try:
        import numpy as np
        samples = audio_clip.get_frame(0)
        # 전체 샘플로 RMS 계산은 비용이 크므로 앞 3초 샘플 사용
        t_sample = min(3.0, audio_clip.duration - 0.01)
        frames = [audio_clip.get_frame(t) for t in np.linspace(0, t_sample, 300)]
        rms = float(np.sqrt(np.mean(np.square(frames))))
        if rms > 0:
            # 목표 RMS ≈ 10^(target_lufs/20) ≈ 0.126 for -18 LUFS
            target_rms = 10 ** (target_lufs / 20)
            gain = target_rms / rms
            gain = min(max(gain, 0.1), 5.0)  # 클리핑 방지
            audio_clip = audio_clip.with_volume_scaled(gain)
    except Exception:
        pass  # 노멀라이즈 실패 시 원본 사용

    # 페이드인 1초, 페이드아웃 2초
    fade_in = min(1.0, video_duration * 0.1)
    fade_out = min(2.0, video_duration * 0.15)
    audio_clip = audio_clip.with_effects([
        vfx.AudioFadeIn(fade_in),
        vfx.AudioFadeOut(fade_out),
    ])
    return audio_clip


# ──────────────────────────────────────────────
# 전환효과 클립 빌더
# ──────────────────────────────────────────────

def _make_slide_clip(frame_arr, sec: float, fade: bool, transition: str):
    """numpy 배열 프레임 → ImageClip (fade/transition 적용)."""
    from moviepy import ImageClip, vfx

    clip = ImageClip(frame_arr, duration=sec)
    if fade or transition == "crossfade":
        clip = clip.with_effects([vfx.FadeIn(0.3), vfx.FadeOut(0.3)])
    return clip


def _build_slide_transition(
    clip_a, clip_b, transition: str, W: int, H: int, fps: int = 30
):
    """slide 전환: clip_a가 왼쪽으로 밀려나면서 clip_b가 오른쪽에서 진입."""
    if transition != "slide":
        return None  # 해당 없음 — 호출자가 직접 concat

    try:
        from moviepy import VideoClip
        import numpy as np

        overlap = 0.4  # 전환 구간 (초)
        fps_f = float(fps)

        def make_frame(t):
            # t: 0 → overlap
            progress = t / overlap  # 0.0 → 1.0
            offset = int(W * progress)

            frame_a = clip_a.get_frame(clip_a.duration - overlap + t)
            frame_b = clip_b.get_frame(t)

            combined = np.zeros((H, W, 3), dtype=np.uint8)
            # clip_a: 왼쪽으로 이동
            a_end = W - offset
            if a_end > 0:
                combined[:, :a_end] = frame_a[:, offset: offset + a_end]
            # clip_b: 오른쪽에서 진입
            if offset > 0:
                combined[:, a_end:] = frame_b[:, :offset]
            return combined

        trans_clip = VideoClip(make_frame, duration=overlap).with_fps(fps)
        return trans_clip
    except Exception:
        return None  # 실패 시 crossfade로 대체


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
    transition: str = "crossfade",
    captions: list[str] | None = None,
) -> None:
    try:
        from moviepy import ImageClip, concatenate_videoclips, AudioFileClip
        from moviepy import vfx
    except ImportError:
        raise ImportError("moviepy")

    import numpy as np

    W, H = resolution
    font_path = _find_font()
    clips = []

    for i, img_path in enumerate(slides):
        frame = _letterbox_frame(img_path, W, H)

        # 자막 오버레이
        caption_text = (captions[i] if captions and i < len(captions) else "") or ""
        if caption_text:
            frame = _add_caption_to_frame(frame, caption_text, W, H, font_path)

        clip = _make_slide_clip(frame, sec, fade, transition)
        clips.append(clip)

    # 전환효과 조합
    if transition == "slide" and len(clips) > 1:
        assembled: list = []
        for idx, clip in enumerate(clips):
            if idx == 0:
                assembled.append(clip)
                continue
            trans = _build_slide_transition(clips[idx - 1], clip, "slide", W, H)
            if trans is not None:
                assembled.append(trans)
            assembled.append(clip)
        video = concatenate_videoclips(assembled, method="compose")
    else:
        # crossfade / none / fade — 단순 concat
        video = concatenate_videoclips(clips, method="compose")

    # BGM
    if bgm and bgm.exists():
        audio = AudioFileClip(str(bgm))
        audio = _normalize_bgm(audio, video.duration)
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
    transition: str = "crossfade",
    captions: list[str] | None = None,
) -> None:
    if not _check_ffmpeg():
        raise RuntimeError("ffmpeg_not_found")

    W, H = resolution
    tmp_dir = out.parent / "_ffmpeg_tmp"
    tmp_dir.mkdir(exist_ok=True)

    from PIL import Image as PILImage
    import numpy as np

    font_path = _find_font()
    prepared: list[Path] = []
    for i, img_path in enumerate(slides):
        frame = _letterbox_frame(img_path, W, H)
        caption_text = (captions[i] if captions and i < len(captions) else "") or ""
        if caption_text:
            frame = _add_caption_to_frame(frame, caption_text, W, H, font_path)
        img = PILImage.fromarray(frame)
        tmp_path = tmp_dir / f"slide_{i:04d}.png"
        img.save(tmp_path)
        prepared.append(tmp_path)

    concat_txt = tmp_dir / "concat.txt"
    with open(concat_txt, "w", encoding="utf-8") as f:
        for p in prepared:
            f.write(f"file '{p.as_posix()}'\n")
            f.write(f"duration {sec}\n")
        f.write(f"file '{prepared[-1].as_posix()}'\n")

    vf = f"fps=30,scale={W}:{H}"
    if fade or transition == "crossfade":
        vf += ",fade=t=in:st=0:d=0.3,fade=t=out:st=0:d=0.3"

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
    ]

    if bgm and bgm.exists():
        cmd += ["-i", str(bgm), "-shortest", "-c:a", "aac", "-af", "afade=t=in:ss=0:d=1,afade=t=out:st=0:d=2"]

    cmd.append(str(out))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-2000:], file=sys.stderr)
        raise RuntimeError(f"ffmpeg 변환 실패 (exit {result.returncode})")

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"[ffmpeg] 완료: {out}")


# ──────────────────────────────────────────────
# 단일 폴더 변환 (공통 진입점)
# ──────────────────────────────────────────────

def convert_one(
    slides_path: Path,
    out: Path,
    sec: float,
    resolution: tuple[int, int],
    bgm: Path | None,
    fade: bool,
    engine: str,
    transition: str,
    captions_arg: str | None,
) -> bool:
    """단일 콘텐츠 폴더를 변환. 성공=True, 실패=False."""
    try:
        slides = resolve_slides(slides_path)
    except ValueError as e:
        print(f"[건너뜀] {e}", file=sys.stderr)
        return False

    captions: list[str] | None = None
    if captions_arg:
        captions = load_captions(captions_arg, len(slides))

    print(f"\n슬라이드 {len(slides)}장 → {resolution[0]}×{resolution[1]}, {sec}s/장, 전환={transition}")
    print(f"출력: {out}")

    errors: list[str] = []

    if engine in ("auto", "moviepy"):
        try:
            build_with_moviepy(slides, out, sec, resolution, bgm, fade, transition, captions)
            return True
        except ImportError:
            errors.append("moviepy 미설치")
        except Exception as e:
            errors.append(f"moviepy 오류: {e}")

    if engine in ("auto", "ffmpeg"):
        try:
            build_with_ffmpeg(slides, out, sec, resolution, bgm, fade, transition, captions)
            return True
        except RuntimeError as e:
            if "ffmpeg_not_found" in str(e):
                errors.append("ffmpeg 미설치")
            else:
                errors.append(f"ffmpeg 오류: {e}")
        except Exception as e:
            errors.append(f"ffmpeg 오류: {e}")

    print(f"[오류] {slides_path.name}: {'; '.join(errors)}", file=sys.stderr)
    return False


# ──────────────────────────────────────────────
# 일괄 변환
# ──────────────────────────────────────────────

def batch_convert(
    batch_root: Path,
    sec: float,
    resolution: tuple[int, int],
    bgm: Path | None,
    fade: bool,
    engine: str,
    transition: str,
    captions_arg: str | None,
) -> None:
    """상위 폴더 하위의 각 콘텐츠 폴더를 순회하며 일괄 변환."""
    if not batch_root.is_dir():
        print(f"[오류] --batch 경로가 폴더가 아닙니다: {batch_root}", file=sys.stderr)
        sys.exit(1)

    # 직접 자식 폴더만 (output 폴더 제외)
    subdirs = sorted(
        d for d in batch_root.iterdir()
        if d.is_dir() and not d.name.startswith("output") and not d.name.startswith("_")
    )

    if not subdirs:
        print(f"[오류] 하위 콘텐츠 폴더가 없습니다: {batch_root}", file=sys.stderr)
        sys.exit(1)

    print(f"일괄 변환 대상: {len(subdirs)}개 폴더")
    ok, fail = 0, 0
    for d in subdirs:
        out = default_output(d)
        success = convert_one(d, out, sec, resolution, bgm, fade, engine, transition, captions_arg)
        if success:
            ok += 1
        else:
            fail += 1

    print(f"\n일괄 완료: 성공 {ok}개 / 실패 {fail}개")
    if fail > 0:
        sys.exit(1)


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="웰페리온 슬라이드 JPG → Reels MP4 변환기 v2.0"
    )
    # 기존 인자 (호환 유지)
    parser.add_argument("--slides", default=None, help="슬라이드 JPG가 있는 폴더 경로")
    parser.add_argument("--sec",    type=float, default=2.5, help="장당 표시 초 (기본 2.5)")
    parser.add_argument("--ratio",  default="9:16", choices=list(RATIO_MAP.keys()),
                        help="출력 비율 (기본 9:16 Reels)")
    parser.add_argument("--bgm",    default=None, help="배경음악 파일 경로 (선택)")
    parser.add_argument("--out",    default=None, help="출력 MP4 경로 (기본: 슬라이드폴더/{폴더명}_reels.mp4)")
    parser.add_argument("--fade",   action="store_true", help="슬라이드 간 페이드 전환 (--transition crossfade 와 동일)")
    parser.add_argument("--engine", choices=["auto", "moviepy", "ffmpeg"], default="auto",
                        help="변환 엔진 선택 (기본 auto: moviepy 우선)")
    # v2 신규 인자
    parser.add_argument("--transition", choices=["crossfade", "slide", "none"], default="crossfade",
                        help="슬라이드 전환효과: crossfade(기본)·slide·none")
    parser.add_argument("--captions", default=None, metavar="FILE",
                        help="자막 파일 경로 (.txt 줄별 or .json 리스트/dict) — 슬라이드별 하단 오버레이")
    parser.add_argument("--batch", default=None, metavar="DIR",
                        help="상위 폴더 지정 시 하위 콘텐츠 폴더 일괄 변환")
    args = parser.parse_args()

    # --transition none 이면 fade도 끔
    if args.transition == "none":
        args.fade = False

    resolution = RATIO_MAP[args.ratio]
    bgm = Path(args.bgm) if args.bgm else None

    # 일괄 모드
    if args.batch:
        batch_convert(
            Path(args.batch),
            args.sec,
            resolution,
            bgm,
            args.fade,
            args.engine,
            args.transition,
            args.captions,
        )
        return

    # 단일 모드
    if not args.slides:
        print("[오류] --slides 또는 --batch 중 하나를 지정하세요.", file=sys.stderr)
        sys.exit(1)

    slides_path = Path(args.slides)
    out = Path(args.out) if args.out else default_output(slides_path)

    success = convert_one(
        slides_path, out,
        args.sec, resolution, bgm,
        args.fade, args.engine,
        args.transition, args.captions,
    )
    if not success:
        print("\n설치 안내:", file=sys.stderr)
        print("  moviepy:  pip install moviepy pillow", file=sys.stderr)
        print("  ffmpeg:   https://ffmpeg.org/download.html (Windows: winget install ffmpeg)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
