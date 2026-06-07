"""채널(블로그·카페·카카오·당근) 콘텐츠 → M5 검수큐 등록 헬퍼 (2026-06-05 AI CMO 시모).

IG용 register_publish.py 의 채널(non-IG) 짝꿍.
콘텐츠 폴더 1개의 채널별 본문/이미지를 review_queue.json 에 status='검수대기' 로 upsert 하고,
슬라이드 montage 미리보기를 cmo/review/ 로 복사한다(M5 라이브 표시 + 텔레그램 검수카드 첨부용).

설계 원칙(기존 파이프라인과 동일):
  - id 기준 upsert — 있으면 본문필드 갱신, 없으면 append. 다른 엔트리·파일 절대 삭제 안 함.
  - 이미 status='발행완료' 인 엔트리는 검수대기로 강등 금지(회귀 가드).
  - 발행/카드 발송은 하지 않는다(공개 부작용 분리). 등록·미리보기까지만.
    → 카드 발송: scripts/send_review_card.py --id <id>
    → 승인 후 발행: scripts/ig_review_publish_watcher.py (채널 분기)

실행(발레 4채널 기본):
  python scripts\\register_channel_review.py
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

for _s in ("stdout", "stderr"):
    _st = getattr(sys, _s, None)
    _rc = getattr(_st, "reconfigure", None) if _st is not None else None
    if _rc is not None:
        try:
            _rc(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
GUIDE_ROOT = ROOT / "3. 웰페리온 가이드"
REVIEW_DIR = GUIDE_ROOT / "cmo" / "review"
REVIEW_QUEUE_PATH = REVIEW_DIR / "review_queue.json"

_TERMINAL_PUBLISHED = "발행완료"


def _make_montage(slide_paths: list[Path], dest: Path, cols: int = 4, cell: int = 360) -> bool:
    """슬라이드 여러 장을 grid montage 로 합쳐 dest 에 저장. 미리보기(검수 썸네일)용."""
    try:
        from PIL import Image
    except Exception as exc:
        print(f"[WARN] Pillow 미설치 — montage 생략: {exc}")
        return False
    imgs = []
    for p in slide_paths:
        if p.exists():
            try:
                imgs.append(Image.open(str(p)).convert("RGB"))
            except Exception as exc:
                print(f"[WARN] 이미지 열기 실패(건너뜀) {p.name}: {exc}")
    if not imgs:
        print("[WARN] montage 대상 이미지 0장 — 생략")
        return False
    rows = (len(imgs) + cols - 1) // cols
    gap = 12
    bg = (28, 26, 24)
    W = cols * cell + (cols + 1) * gap
    H = rows * cell + (rows + 1) * gap
    from PIL import Image as _I
    canvas = _I.new("RGB", (W, H), bg)
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        thumb = im.copy()
        thumb.thumbnail((cell, cell))
        x = gap + c * (cell + gap) + (cell - thumb.width) // 2
        y = gap + r * (cell + gap) + (cell - thumb.height) // 2
        canvas.paste(thumb, (x, y))
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(dest), quality=88)
    print(f"[INFO] montage 저장 → {dest}")
    return True


def _load_queue() -> list:
    if not REVIEW_QUEUE_PATH.exists():
        return []
    loaded = json.loads(REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, list) else []


def _upsert(queue: list, queue_id: str, fields: dict) -> str:
    """id 기준 upsert. 발행완료는 강등 금지. 반환: 최종 status."""
    match = next((it for it in queue if it.get("id") == queue_id), None)
    if match is not None:
        prev = match.get("status", "")
        for k, v in fields.items():
            if k == "status":
                continue
            match[k] = v
        if prev == _TERMINAL_PUBLISHED:
            print(f"[INFO] {queue_id} 이미 발행완료 — status 유지, 본문만 갱신")
            return _TERMINAL_PUBLISHED
        final = fields.get("status", prev or "검수대기")
        match["status"] = final
        print(f"[INFO] update {queue_id} / status={final}")
        return final
    item = dict(fields)
    item["id"] = queue_id
    item.setdefault("status", "검수대기")
    queue.append(item)
    print(f"[INFO] append(신규) {queue_id} / status={item['status']}")
    return item["status"]


def register_channels(folder_rel: str, slide_glob: str, channels: list[dict],
                      preview_slug: str) -> None:
    """채널 엔트리들을 review_queue 에 등록 + 슬라이드 montage 미리보기 생성 + 채널폴더에 슬라이드 채움."""
    folder = ROOT / folder_rel
    # 1) 마스터 슬라이드 수집 (output/ig_*.jpg)
    master_dir = folder / "output"
    slides = sorted(master_dir.glob(slide_glob))
    print(f"[INFO] 마스터 슬라이드 {len(slides)}장: {[p.name for p in slides]}")

    # 2) montage 미리보기 → cmo/review/
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    preview_dest = REVIEW_DIR / f"{preview_slug}_preview_{ts}.png"
    preview_rel = None
    if _make_montage(slides, preview_dest):
        preview_rel = preview_dest.relative_to(GUIDE_ROOT).as_posix()  # cmo/review/... (M5 호환)

    # 3) 각 채널 폴더에 슬라이드 채우기 (image_glob=ig_*.jpg 로 stale 대표이미지 회피)
    queue = _load_queue()
    for ch in channels:
        ch_dir = ROOT / ch["image_dir"]
        ch_dir.mkdir(parents=True, exist_ok=True)
        for sp in slides:
            try:
                shutil.copyfile(str(sp), str(ch_dir / sp.name))
            except Exception as exc:
                print(f"[WARN] 슬라이드 복사 실패 {sp.name}→{ch['image_dir']}: {exc}")
        # 본문 인라인(M5 표시용) — 파일에서 읽기
        body_path = ROOT / ch["body_file"]
        body_text = body_path.read_text(encoding="utf-8") if body_path.exists() else ""

        fields = {
            "title": ch["title"],
            "channel": ch["channel"],
            "account": ch.get("account", "wellperion"),
            "folder": folder_rel,
            "body_file": ch["body_file"],
            "image_dir": ch["image_dir"],
            "image_glob": ch.get("image_glob", "ig_*.jpg"),
            "body": body_text,
            "status": "검수대기",
        }
        if "menuid" in ch:
            fields["menuid"] = ch["menuid"]
        if preview_rel:
            fields["preview"] = preview_rel
        _upsert(queue, ch["id"], fields)

    REVIEW_QUEUE_PATH.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] review_queue 등록 완료 — {len(channels)}개 채널 / preview={preview_rel}")


# ---------------------------------------------------------------------------
# 발레 신규 클래스 런칭 — 4채널 기본 설정
BALLET_FOLDER = "instagram/260520_발레_런칭"
BALLET_CHANNELS = [
    {
        "id": "CMO-2026-05-20-BALLET-BLOG",
        "title": "발레 신규 클래스 런칭 — 네이버 블로그",
        "channel": "네이버 블로그",
        "body_file": "instagram/260520_발레_런칭/output(블로그)/_blog_body.txt",
        "image_dir": "instagram/260520_발레_런칭/output(블로그)",
    },
    {
        "id": "CMO-2026-05-20-BALLET-CAFE",
        "title": "발레 신규 클래스 런칭 — 네이버 카페(동부이촌동)",
        "channel": "네이버 카페 (동부이촌동)",
        "body_file": "instagram/260520_발레_런칭/output(카페)/_cafe_body.txt",
        "image_dir": "instagram/260520_발레_런칭/output(카페)",
        "menuid": 659,
    },
    {
        "id": "CMO-2026-05-20-BALLET-KAKAO",
        "title": "발레 신규 클래스 런칭 — 카카오 채널",
        "channel": "카카오 채널",
        "body_file": "instagram/260520_발레_런칭/output(카카오 채널)/kakao_copy.md",
        "image_dir": "instagram/260520_발레_런칭/output(카카오 채널)",
    },
    {
        "id": "CMO-2026-05-20-BALLET-DANGGN",
        "title": "발레 신규 클래스 런칭 — 당근채널",
        "channel": "당근채널",
        "body_file": "instagram/260520_발레_런칭/output(당근)/danggn_copy.md",
        "image_dir": "instagram/260520_발레_런칭/output(당근)",
    },
]


BARRE_FOLDER = "instagram/260520_바레_런칭"
BARRE_CHANNELS = [
    {
        "id": "CMO-2026-06-08-BARRE-BLOG",
        "title": "바레 신규 클래스 런칭 — 네이버 블로그",
        "channel": "네이버 블로그",
        "body_file": "instagram/260520_바레_런칭/output(블로그)/_blog_body.txt",
        "image_dir": "instagram/260520_바레_런칭/output(블로그)",
    },
    {
        "id": "CMO-2026-06-08-BARRE-CAFE",
        "title": "바레 신규 클래스 런칭 — 네이버 카페(동부이촌동)",
        "channel": "네이버 카페 (동부이촌동)",
        "body_file": "instagram/260520_바레_런칭/output(카페)/_cafe_body.txt",
        "image_dir": "instagram/260520_바레_런칭/output(카페)",
        "menuid": 659,
    },
    {
        "id": "CMO-2026-06-08-BARRE-KAKAO",
        "title": "바레 신규 클래스 런칭 — 카카오 채널",
        "channel": "카카오 채널",
        "body_file": "instagram/260520_바레_런칭/output(카카오 채널)/kakao_copy.md",
        "image_dir": "instagram/260520_바레_런칭/output(카카오 채널)",
    },
    {
        "id": "CMO-2026-06-08-BARRE-DANGGN",
        "title": "바레 신규 클래스 런칭 — 당근채널",
        "channel": "당근채널",
        "body_file": "instagram/260520_바레_런칭/danggn_copy.md",
        "image_dir": "instagram/260520_바레_런칭/output(당근)",
    },
]


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "barre"
    if target == "ballet":
        register_channels(
            folder_rel=BALLET_FOLDER,
            slide_glob="ig_*.jpg",
            channels=BALLET_CHANNELS,
            preview_slug="260520_발레_채널검수",
        )
    else:
        register_channels(
            folder_rel=BARRE_FOLDER,
            slide_glob="ig_*.jpg",
            channels=BARRE_CHANNELS,
            preview_slug="260520_바레_채널검수",
        )
