"""걷기 영상에서 뽑은 프레임 폴더 -> walk_frames.json 생성.
영상 -> 프레임 추출 (ffmpeg 예시, fps=8 초당 8장 · 1600px 폭):
  ffmpeg -i walk.mp4 -vf "fps=8,scale=1600:-1" frames/f_%04d.webp

사용법:
  python scripts/walk_frames_build.py <프레임폴더> <출력.json> [--src-prefix ../walk/]

space·caption 은 빈 값으로 나온다 — 동선 구간별로 수기 채운다(공간 경계는 사람이 안다).
정본 위치 = 3. 웰페리온 가이드/home/assets/360/walk_frames.json (2026-09-05 공개 홈 폴더로 이동 · 뷰어 = home/tour/index.html)
"""
import json
import sys
from pathlib import Path


def build(frames_dir: Path, out_path: Path, src_prefix: str = "") -> int:
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    files = sorted(p for p in frames_dir.iterdir() if p.suffix.lower() in exts)
    frames = [{"src": src_prefix + p.name, "space": "", "caption": ""} for p in files]
    out_path.write_text(
        json.dumps({"_doc": "walk_frames_build.py 생성 — space/caption 채울 것", "frames": frames}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return len(frames)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: walk_frames_build.py <frames_dir> <out.json> [--src-prefix PREFIX]")
    frames_dir, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    prefix = ""
    if "--src-prefix" in sys.argv:
        prefix = sys.argv[sys.argv.index("--src-prefix") + 1]
    n = build(frames_dir, out_path, prefix)
    print(f"{n} frames -> {out_path}")
