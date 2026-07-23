"""얼굴 모자이크 전처리 스크립트 — 골프 유소년 사진 초상권 보호
Haar cascade(정면+옆모습) 자동검출 + 모자이크(픽셀화) 처리.
원본 보존, 처리본은 _faces_masked/ 에 저장.
예외: PNG 프로필 카드(김태엽 프로) 제외.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

# cascade 경로
CASCADE_DIR = Path(r"C:\Users\jjky0\AppData\Roaming\Python\Python314\site-packages\cv2\data")
FRONTAL_CASCADE = str(CASCADE_DIR / "haarcascade_frontalface_default.xml")
FRONTAL_ALT2    = str(CASCADE_DIR / "haarcascade_frontalface_alt2.xml")
PROFILE_CASCADE = str(CASCADE_DIR / "haarcascade_profileface.xml")

SRC_DIR = (
    Path(r"C:\Users\jjky0\welperion-automation")
    / "instagram" / "Image" / "골프_유소년_주니어대회(원본 이미지)"
)
OUT_DIR = SRC_DIR / "_faces_masked"
OUT_DIR.mkdir(exist_ok=True)

# 처리 대상 파일 (png=김태엽 프로 제외)
PFX = "KakaoTalk_20260618_135719893"
TARGETS = [
    SRC_DIR / f"{PFX}.jpg",      # 라운딩 캐디+아이
    SRC_DIR / f"{PFX}_01.jpg",   # 여자아이 아이언 임팩트
    SRC_DIR / f"{PFX}_03.jpg",   # 시상대 트로피 3명
    SRC_DIR / f"{PFX}_05.jpg",   # 코치+아이 시상대
    SRC_DIR / f"{PFX}_06.jpg",   # 단체 트로피
    SRC_DIR / f"{PFX}_09.jpg",   # 단체 출발 (세로/EXIF)
    SRC_DIR / f"{PFX}_11.jpg",   # 코치+아이 현장 투샷 (세로/EXIF)
    SRC_DIR / f"{PFX}_12.jpg",   # 티잉그라운드 티샷
    SRC_DIR / f"{PFX}_15.jpg",   # 상장 장면 (2편 미사용이나 혹시 몰라 처리)
]

# 수동 보완 좌표 {파일명: [(x,y,w,h), ...]}
# 원본 해상도 기준. 자동검출이 부족한 경우 여기서 강제 지정.
# 썸네일(1000px) 좌표 × (원본_폭/썸네일_폭) 로 역산.
MANUAL_BOXES: dict[str, list[tuple[int,int,int,int]]] = {
    # _03: 6000×4000, thumb_scale=1/0.1667=6.0
    # 시상대 3명: 좌(흰셔츠), 중(녹색셔츠), 우(검정셔츠)
    "KakaoTalk_20260618_135719893_03.jpg": [
        (1020, 1350, 420, 420),   # 좌 아이
        (2640, 1200, 480, 480),   # 중앙 아이
        (4140, 1380, 390, 390),   # 우 아이
    ],
    # _06: 6000×4000, thumb 1000x667, scale x=6.0 y=5.997
    # 단체 앞줄+뒷줄 전원 — 그리드 측정 기반 최종
    "KakaoTalk_20260618_135719893_06.jpg": [
        # 앞줄 (그리드 기반 재측정)
        (300,  2368, 420, 419),   # 좌1 여자아이(갈색)
        (750,  1859, 450, 599),   # 검정 성인여자
        (1200, 2308, 420, 419),
        (1620, 2308, 420, 419),
        (2070, 2308, 420, 419),
        (2520, 2308, 420, 419),
        (3000, 2308, 420, 419),
        (3450, 2308, 420, 419),
        (3900, 2308, 420, 419),
        (4380, 2308, 420, 419),
        (4860, 2308, 420, 419),
        (5310, 2338, 390, 389),
        # 뒷줄
        (869,  1109, 329, 329),
        (1319, 1049, 329, 329),
        (2159, 1049, 329, 329),
        (2639, 1049, 329, 329),
        (3119, 1079, 329, 329),
        (3599, 1079, 329, 329),
        (4079, 1079, 329, 329),
        (4529, 1079, 329, 329),
        (5008, 1049, 329, 329),
        (5458, 1049, 329, 329),
    ],
    # _09: 4284×5712, thumb 750x1000, scale x=5.712 y=5.712
    # 등록 대기 줄 — 좌표 정밀 보정
    "KakaoTalk_20260618_135719893_09.jpg": [
        (228,  1513, 428, 485),   # 좌 성인(파란조끼)
        (714,  1713, 342, 399),   # 좌2 소년(녹색)
        (1685, 1228, 428, 485),   # 중앙 흰셔츠 아이
        (2341, 1142, 371, 428),   # 중우 아이
        (3027, 1113, 371, 428),   # 우측 마스크 아이
        (3655, 1056, 371, 428),   # 최우측 아이
    ],
    # _05: 6000×4000, thumb_scale=6.0
    # 프로(선글라스)+아이 2명
    "KakaoTalk_20260618_135719893_05.jpg": [
        (1680, 960,  540, 540),   # 프로(성인)
        (3180, 900,  480, 480),   # 아이
    ],
    # _12: 3024×4032, thumb_scale≈4.032
    # 티샷 아이 + 캐디(마스크)
    "KakaoTalk_20260618_135719893_12.jpg": [
        (907,  1008, 403, 403),   # 아이(노란모자)
        (2117, 1210, 362, 362),   # 캐디(마스크)
    ],
    # _11: 4284×5712, thumb 750x1000, scale x=5.712 y=5.712
    # 아이(좌)+프로(우) 투샷 — 그리드 측정 기반 최종
    "KakaoTalk_20260618_135719893_11.jpg": [
        (656,  2284, 399, 456),   # 아이 (thumb x=115,y=400,w=70,h=80)
        (2113, 1770, 571, 571),   # 프로 (thumb x=370,y=310,w=100,h=100)
    ],
    # _15: 4032×3024, thumb_scale≈4.032
    # 프로(핑크)+아이 2명
    "KakaoTalk_20260618_135719893_15.jpg": [
        (1330, 282,  484, 484),   # 프로
        (2218, 363,  403, 403),   # 아이
    ],
    # _00 (기본): 3000×2000 — 원거리라 얼굴 작음, 자동검출 보완
    "KakaoTalk_20260618_135719893.jpg": [
        (870,  570,  270, 270),   # 성인(캐디)
        (1290, 630,  240, 240),   # 아이
    ],
    # _01: 2000×3000 — 스윙 중 고개 숙여 얼굴 거의 안 보이나 보수적 처리
    "KakaoTalk_20260618_135719893_01.jpg": [
        (620,  270,  360, 360),   # 모자 아래 얼굴 추정 영역
    ],
}


def pixelate(img: np.ndarray, x: int, y: int, w: int, h: int, block: int = 18) -> np.ndarray:
    """지정 영역을 픽셀 블록(모자이크)으로 처리."""
    roi = img[y:y+h, x:x+w]
    if roi.size == 0:
        return img
    small = cv2.resize(roi, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_LINEAR)
    mosaic = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    img[y:y+h, x:x+w] = mosaic
    return img


def _iou_nms(boxes: list[tuple[int,int,int,int]], iou_thresh: float = 0.35) -> list[tuple[int,int,int,int]]:
    """간단한 IoU NMS — cv2.dnn 호환 문제 우회."""
    if not boxes:
        return []
    arr = np.array([[x, y, x+w, y+h] for (x,y,w,h) in boxes], dtype=np.float32)
    areas = (arr[:,2]-arr[:,0]) * (arr[:,3]-arr[:,1])
    order = areas.argsort()[::-1]
    keep = []
    while len(order):
        i = order[0]
        keep.append(i)
        if len(order) == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(arr[i,0], arr[rest,0])
        yy1 = np.maximum(arr[i,1], arr[rest,1])
        xx2 = np.minimum(arr[i,2], arr[rest,2])
        yy2 = np.minimum(arr[i,3], arr[rest,3])
        inter = np.maximum(0, xx2-xx1) * np.maximum(0, yy2-yy1)
        iou = inter / (areas[i] + areas[rest] - inter + 1e-6)
        order = rest[iou <= iou_thresh]
    return [boxes[i] for i in keep]


def detect_faces(gray: np.ndarray) -> list[tuple[int,int,int,int]]:
    """정면+alt2+옆모습 cascade 조합. 보수적 파라미터로 다단계 검출."""
    boxes: list[tuple[int,int,int,int]] = []

    def _det(cascade_path: str, scale: float, mn: int, ms: tuple[int,int]) -> list:
        cc = cv2.CascadeClassifier(cascade_path)
        det = cc.detectMultiScale(gray, scaleFactor=scale, minNeighbors=mn,
                                  minSize=ms, flags=cv2.CASCADE_SCALE_IMAGE)
        return [tuple(d) for d in det.tolist()] if len(det) > 0 else []

    # 정면 — 여러 스케일
    for scale, mn, ms in [(1.05, 4, (25,25)), (1.1, 3, (20,20)), (1.15, 3, (15,15))]:
        boxes += _det(FRONTAL_CASCADE, scale, mn, ms)
    for scale, mn, ms in [(1.05, 4, (25,25)), (1.1, 3, (20,20))]:
        boxes += _det(FRONTAL_ALT2, scale, mn, ms)

    # 옆모습 — 원본 + 좌우 반전
    for scale, mn, ms in [(1.05, 4, (25,25)), (1.1, 3, (20,20))]:
        boxes += _det(PROFILE_CASCADE, scale, mn, ms)
    IW = gray.shape[1]
    gray_flip = cv2.flip(gray, 1)
    for scale, mn, ms in [(1.05, 4, (25,25)), (1.1, 3, (20,20))]:
        cc = cv2.CascadeClassifier(PROFILE_CASCADE)
        det = cc.detectMultiScale(gray_flip, scaleFactor=scale, minNeighbors=mn,
                                  minSize=ms, flags=cv2.CASCADE_SCALE_IMAGE)
        if len(det) > 0:
            for (x, y, w, h) in det:
                boxes.append((IW - x - w, y, w, h))

    return _iou_nms(boxes, iou_thresh=0.35)


def process(src: Path, padding: float = 0.28) -> Path:
    """원본 읽기 → EXIF 회전 → 얼굴 검출 → 모자이크 → 저장. 반환: 출력 경로."""
    # cv2.imread는 한글 경로 미지원 → PIL로 읽어 numpy 변환
    from PIL import Image as PILImage, ImageOps
    pil = ImageOps.exif_transpose(PILImage.open(src).convert("RGB"))
    img_bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    H, W = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    faces = detect_faces(gray)

    # 수동 보완 좌표 추가
    manual = MANUAL_BOXES.get(src.name, [])
    faces = faces + manual

    # padding 적용 + 클리핑 + 모자이크
    count = 0
    for (fx, fy, fw, fh) in faces:
        px = int(fw * padding)
        py = int(fh * padding)
        x1 = max(0, fx - px)
        y1 = max(0, fy - py)
        x2 = min(W, fx + fw + px)
        y2 = min(H, fy + fh + py)
        img_bgr = pixelate(img_bgr, x1, y1, x2-x1, y2-y1, block=14)
        count += 1

    # cv2.imwrite 한글 경로 미지원 → PIL로 저장
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    out = OUT_DIR / src.name
    from PIL import Image as PILSave
    PILSave.fromarray(img_rgb).save(str(out), "JPEG", quality=95)
    print(f"  {src.name}: 얼굴 {count}개 모자이크 → {out.name}")
    return out


def main() -> None:
    print("=== 얼굴 모자이크 전처리 ===")
    for src in TARGETS:
        if not src.exists():
            print(f"  [SKIP] 파일 없음: {src.name}")
            continue
        process(src)
    print(f"\n출력: {OUT_DIR}")
    print("완료. Read로 결과 이미지 육안 확인 후 MANUAL_BOXES에 누락 추가.")


if __name__ == "__main__":
    main()
