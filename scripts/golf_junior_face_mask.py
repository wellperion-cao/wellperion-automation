"""KPGA 유소년 대회 사진 — 미성년 얼굴 모자이크 (privacy)

haar 3종(frontal_default·alt2·profile) + 좌우반전 프로파일 union → 검출.
박스 확장(이마·턱 포함) 후 강한 픽셀화. 검출 누락 대비 MANUAL 보강 박스 지원.
김태엽 프로(png)·공개 대상은 KEEP_CLEAR 또는 처리 제외.

산출: _faces_masked/*.jpg (덮어쓰기) + _verify_masked.jpg (검증 컨택트시트)
실행: python scripts/golf_junior_face_mask.py
"""
from __future__ import annotations
import cv2
import numpy as np
from pathlib import Path


def imread_u(path: Path):
    """한글 경로 대응 imread (np.fromfile + imdecode)."""
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_u(path: Path, img, params=None):
    """한글 경로 대응 imwrite (imencode + tofile)."""
    ext = path.suffix
    ok, buf = cv2.imencode(ext, img, params or [])
    if ok:
        buf.tofile(str(path))
    return ok

SRC = Path(r"instagram/Image/골프_유소년_주니어대회(원본 이미지)")
OUT = SRC / "_faces_masked"
OUT.mkdir(exist_ok=True)

_MODEL = str(Path(__file__).parent / "_models" / "face_detection_yunet_2023mar.onnx")
SCORE_THRESH = 0.55   # YuNet 신뢰도 임계 (낮을수록 더 많이 잡음)

# 수동 보강 박스 (검증 후 채움) — 원본 픽셀 절대좌표 [x, y, w, h]
MANUAL: dict[str, list[list[int]]] = {}

# png(프로 카드)·확실한 무얼굴은 스킵
SKIP = {"KakaoTalk_20260618_135750819.png"}


def detect(img):
    """YuNet DNN 얼굴 검출 — 큰 원본은 1280px 폭으로 축소 후 좌표 환원."""
    H, W = img.shape[:2]
    scale = 1280 / W if W > 1280 else 1.0
    small = cv2.resize(img, (int(W * scale), int(H * scale))) if scale != 1.0 else img
    sh, sw = small.shape[:2]
    det = cv2.FaceDetectorYN.create(_MODEL, "", (sw, sh), SCORE_THRESH, 0.3, 5000)
    det.setInputSize((sw, sh))
    _, faces = det.detect(small)
    boxes = []
    if faces is not None:
        for fc in faces:
            x, y, w, h = fc[:4]
            boxes.append([int(x / scale), int(y / scale), int(w / scale), int(h / scale)])
    return boxes


def expand(b, W, H, fx=0.5, ftop=0.65, fbot=0.35):
    x, y, w, h = b
    nx = int(max(0, x - w * fx / 2)); nw = int(min(W - nx, w * (1 + fx)))
    ny = int(max(0, y - h * ftop)); nh = int(min(H - ny, h * (1 + ftop + fbot)))
    return [nx, ny, nw, nh]


def mosaic(img, b, blocks=9):
    x, y, w, h = b
    if w <= 1 or h <= 1:
        return
    roi = img[y:y + h, x:x + w]
    small = cv2.resize(roi, (blocks, blocks), interpolation=cv2.INTER_LINEAR)
    img[y:y + h, x:x + w] = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def main():
    thumbs = []
    for f in sorted(SRC.glob("*.jpg")):
        if f.name in SKIP or f.name.startswith("_"):  # _verify 등 산출물 제외
            continue
        img = imread_u(f)
        if img is None:
            continue
        H, W = img.shape[:2]
        raw = detect(img)
        boxes = [expand(b, W, H) for b in raw]
        for b in MANUAL.get(f.name, []):
            x, y, w, h = b
            boxes.append([max(0, x), max(0, y), min(W - x, w), min(H - y, h)])
        for b in boxes:
            mosaic(img, b)
        imwrite_u(OUT / f.name, img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"{f.name}: auto {len(raw)} + manual {len(MANUAL.get(f.name, []))} = {len(boxes)} boxes")
        # 컨택트시트 썸네일 (라벨)
        th = cv2.resize(img, (300, int(300 * H / W)))
        cv2.putText(th, f.name.split('135719893')[-1] or '_00', (6, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        thumbs.append(th)

    # 4열 컨택트시트
    if thumbs:
        hmax = max(t.shape[0] for t in thumbs)
        import numpy as np
        cols = 4
        rows = (len(thumbs) + cols - 1) // cols
        cell_w = 300
        sheet = np.full((rows * hmax, cols * cell_w, 3), 40, dtype='uint8')
        for i, t in enumerate(thumbs):
            r, c = divmod(i, cols)
            sheet[r * hmax:r * hmax + t.shape[0], c * cell_w:c * cell_w + t.shape[1]] = t
        imwrite_u(SRC / "_verify_masked.jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
        print(f"\n검증 컨택트시트: {SRC / '_verify_masked.jpg'}")


if __name__ == "__main__":
    main()
