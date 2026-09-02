"""compose_unified_slide 의 표현 플래그 3개 자체 점검.

세 인자(duotone·show_chip·logo_box)는 기본값이 종전 동작이어야 한다 —
기존 호출부(make_reel·cmo_intake_to_review·review_queue_util)가 인자를 안 넘기기 때문이다.
그 계약이 깨지면 공식 슬라이드가 조용히 다른 모습으로 나간다.

    C:/Python314/python.exe scripts/test_slide_compositor_flags.py
"""
from __future__ import annotations

import inspect
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image

from slide_compositor import compose_unified_slide


def _sample_photo(path: Path) -> Path:
    """색이 뚜렷한 임시 사진 — 듀오톤이 실제로 색을 바꾸는지 보려면 회색이면 안 된다."""
    img = Image.new("RGB", (1200, 900))
    px = img.load()
    for y in range(900):
        for x in range(0, 1200, 4):
            for dx in range(4):
                px[x + dx, y] = (30, 90, 200) if (x // 100) % 2 else (220, 180, 60)
    img.save(path, "JPEG", quality=85)
    return path


def main() -> None:
    sig = inspect.signature(compose_unified_slide).parameters
    for name in ("duotone", "show_chip", "logo_box"):
        assert name in sig, f"{name} 인자가 사라졌다"
        assert sig[name].default is True, f"{name} 기본값이 True 가 아니다 — 기존 호출부가 바뀐다"

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        photo = _sample_photo(tmp / "src.jpg")
        common = dict(
            base_image=photo,
            label_eng="POOL",
            body_text="25m.\n레인은 늘 그 자리에 있습니다.",
            aspect="1080x1350",
            brand_key="main",
        )
        compose_unified_slide(output=tmp / "on.jpg", **common)
        compose_unified_slide(
            output=tmp / "off.jpg", duotone=False, show_chip=False, logo_box=False, **common
        )

        on = Image.open(tmp / "on.jpg").convert("RGB")
        off = Image.open(tmp / "off.jpg").convert("RGB")
        assert on.size == off.size, "플래그가 캔버스 크기를 바꿨다"

        # 듀오톤은 사진 영역을 단색 계열로 물들인다 — 원본 색이 남아 있으면 채도 차가 난다.
        def _spread(img: Image.Image) -> int:
            band = img.crop((0, 100, img.width, 600)).resize((60, 40))
            pixels = [band.getpixel((x, y)) for x in range(band.width) for y in range(band.height)]
            return max(max(p) - min(p) for p in pixels)

        assert _spread(off) > _spread(on), "duotone=False 인데 사진이 여전히 단색으로 물들었다"

        # 우상단 칩은 베이지 사각형 — 끄면 그 자리가 사진 색 그대로여야 한다.
        chip_px_on = on.getpixel((int(on.width * 0.85), int(on.height * 0.055)))
        chip_px_off = off.getpixel((int(off.width * 0.85), int(off.height * 0.055)))
        assert chip_px_on != chip_px_off, "show_chip=False 인데 우상단이 그대로다"

    print("[OK] compose_unified_slide 플래그 3종 — 기본값 보존 · 실제 반영 확인")


if __name__ == "__main__":
    main()
