"""
이미지를 화질 최대한 살려 지정 용량(기본 10MB) 아래로 변환.
원본은 보존하고 결과는 하위 web_10mb/ 폴더에 저장.

사용: python compress_images_under_limit.py "<폴더경로>" [목표MB]
기본 폴더가 없으면 시설 사진 폴더 사용.
"""
import io
import os
import sys
from PIL import Image, ImageOps

DEFAULT_DIR = r"C:\Users\jjky0\welperion-automation\2. 브랜드_공식문서\시설 사진"


def encode(im, quality):
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def fit_under(im, ceil_bytes):
    """현재 해상도에서 quality를 낮춰보고, 그래도 안 되면 85%씩 축소. (화질 우선)"""
    edge_cap = max(im.size)
    while True:
        for q in (95, 93, 90, 88, 85, 82, 80, 78, 75):
            data = encode(im, q)
            if len(data) <= ceil_bytes:
                return data, q, im.size
        # q75에도 초과 → 해상도 85% 축소 후 재시도
        new_edge = int(max(im.size) * 0.85)
        if new_edge < 1600:  # 안전 하한
            return encode(im, 75), 75, im.size
        scale = new_edge / max(im.size)
        im = im.resize((int(im.size[0] * scale), int(im.size[1] * scale)), Image.LANCZOS)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    target_mb = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    ceil_bytes = int(target_mb * 1024 * 1024 * 0.95)  # 10MB면 안전하게 9.5MB 목표
    max_edge = 4500  # 너무 저용량 방지: 긴 변 최대 4500px 유지(고화질)

    out = os.path.join(src, "web_10mb")
    os.makedirs(out, exist_ok=True)

    files = [f for f in os.listdir(src)
             if f.lower().endswith((".jpg", ".jpeg", ".png")) and os.path.isfile(os.path.join(src, f))]
    files.sort()
    print(f"[INFO] 대상 {len(files)}장 · 목표 < {target_mb}MB · 출력 {out}")
    print("-" * 70)

    for f in files:
        p = os.path.join(src, f)
        orig_mb = os.path.getsize(p) / 1024 / 1024
        im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        if max(im.size) > max_edge:
            scale = max_edge / max(im.size)
            im = im.resize((int(im.size[0] * scale), int(im.size[1] * scale)), Image.LANCZOS)
        data, q, size = fit_under(im, ceil_bytes)
        name = os.path.splitext(f)[0] + ".jpg"
        with open(os.path.join(out, name), "wb") as w:
            w.write(data)
        print(f"{f:18s} {orig_mb:6.1f}MB -> {len(data)/1024/1024:5.2f}MB  q{q}  {size[0]}x{size[1]}")

    print("-" * 70)
    print(f"[DONE] {out}")


if __name__ == "__main__":
    main()
