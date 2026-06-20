"""YuNet 기반 완성 슬라이드 얼굴 모자이크 후처리
대상: output(인스타그램)/ep*/ig_01~04.jpg (ig_05 가이드카드·ep3/ig_02 제외)
방식: cv2.FaceDetectorYN, score_threshold=0.3, padding=30%, block=20
덮어쓰기.
"""
from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from PIL import Image, ImageOps

MODEL = Path(__file__).parent / "_models" / "face_detection_yunet.onnx"
OUTPUT_ROOT = (
    Path(__file__).parent.parent
    / "instagram"
    / "260620_골프_유소년_KPGA주니어대회"
    / "output(인스타그램)"
)

# 예외: 처리 금지 슬라이드
SKIP = {
    "ep3/ig_02.jpg",  # 김태엽 프로 (공개 동의)
    "ep1/ig_05.jpg",
    "ep2/ig_05.jpg",
    "ep3/ig_05.jpg",
}

# 처리 대상
TARGETS = [
    ("ep1", "ig_01.jpg"),
    ("ep1", "ig_02.jpg"),
    ("ep1", "ig_03.jpg"),
    ("ep1", "ig_04.jpg"),
    ("ep2", "ig_01.jpg"),
    ("ep2", "ig_02.jpg"),
    ("ep2", "ig_03.jpg"),
    ("ep2", "ig_04.jpg"),
    ("ep3", "ig_01.jpg"),
    ("ep3", "ig_03.jpg"),
    ("ep3", "ig_04.jpg"),
]

# 수동 보완 박스 {ep/file: [(x, y, w, h) 비율 좌표 0~1]}
# 듀오톤·역광 등으로 YuNet 검출 실패한 얼굴 수동 지정
MANUAL_RATIO: dict[str, list[tuple[float, float, float, float]]] = {
    # ep1/ig_01 ep3/ig_01: 여아 스윙 표지(듀오톤) — 얼굴만 (모자 아래 ~ 턱)
    "ep1/ig_01.jpg": [(0.315, 0.463, 0.12, 0.093)],
    "ep3/ig_01.jpg": [(0.315, 0.463, 0.12, 0.093)],
    # ep1/ig_04: 좌측 성인(파란조끼) 얼굴 누락 — 수동 보완
    # 그리드 재측정: x=50~150, y=170~300
    "ep1/ig_04.jpg": [(0.046, 0.157, 0.093, 0.120)],
}


def pil_to_bgr(path: Path) -> tuple[np.ndarray, tuple[int, int]]:
    """PIL로 읽어 BGR ndarray 반환 (한글경로·EXIF 안전)."""
    pil = ImageOps.exif_transpose(Image.open(path).convert("RGB"))
    arr = np.array(pil)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), pil.size  # (W, H)


def bgr_to_pil(bgr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def pixelate(img: np.ndarray, x1: int, y1: int, x2: int, y2: int, block: int = 20) -> np.ndarray:
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return img
    h, w = roi.shape[:2]
    bw, bh = max(1, w // block), max(1, h // block)
    small = cv2.resize(roi, (bw, bh), interpolation=cv2.INTER_LINEAR)
    roi[:] = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    img[y1:y2, x1:x2] = roi
    return img


def detect_yunet(bgr: np.ndarray, score_th: float = 0.3) -> list[tuple[int, int, int, int]]:
    H, W = bgr.shape[:2]
    detector = cv2.FaceDetectorYN.create(
        str(MODEL), "", (W, H),
        score_threshold=score_th,
        nms_threshold=0.3,
        top_k=500,
    )
    _, faces = detector.detect(bgr)
    if faces is None:
        return []
    boxes = []
    for f in faces:
        x, y, w, h = int(f[0]), int(f[1]), int(f[2]), int(f[3])
        boxes.append((x, y, w, h))
    return boxes


def apply_mosaic(bgr: np.ndarray, boxes: list[tuple[int, int, int, int]],
                 padding: float = 0.30, block: int = 20) -> tuple[np.ndarray, int]:
    H, W = bgr.shape[:2]
    count = 0
    for (x, y, w, h) in boxes:
        px, py = int(w * padding), int(h * padding)
        x1 = max(0, x - px)
        y1 = max(0, y - py)
        x2 = min(W, x + w + px)
        y2 = min(H, y + h + py)
        bgr = pixelate(bgr, x1, y1, x2, y2, block=block)
        count += 1
    return bgr, count


def process_slide(ep: str, fname: str) -> int:
    key = f"{ep}/{fname}"
    if key in SKIP:
        print(f"  SKIP  {key}")
        return 0

    path = OUTPUT_ROOT / ep / fname
    if not path.exists():
        print(f"  MISS  {key} (파일 없음)")
        return 0

    bgr, (W, H) = pil_to_bgr(path)

    # YuNet 검출
    boxes = detect_yunet(bgr, score_th=0.3)

    # 수동 박스 추가 (비율 → 픽셀)
    manual = MANUAL_RATIO.get(key, [])
    for (rx, ry, rw, rh) in manual:
        boxes.append((int(rx * W), int(ry * H), int(rw * W), int(rh * H)))

    # 모자이크 적용
    bgr, count = apply_mosaic(bgr, boxes, padding=0.30, block=20)

    # PIL로 저장 (한글경로 안전)
    bgr_to_pil(bgr).save(str(path), "JPEG", quality=95)
    print(f"  OK    {key}  검출{count}명 (수동{len(manual)})")
    return count


def main() -> None:
    print("=== YuNet 슬라이드 얼굴 모자이크 후처리 ===")
    if not MODEL.exists():
        print(f"BLOCKED: 모델 없음 {MODEL}")
        return

    total = 0
    for ep, fname in TARGETS:
        total += process_slide(ep, fname)

    print(f"\n완료: 총 {total}개 얼굴 모자이크")
    print("출력:", OUTPUT_ROOT)


if __name__ == "__main__":
    main()
