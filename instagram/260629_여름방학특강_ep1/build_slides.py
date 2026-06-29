"""2026 여름 방학특강 Ep1 — 슬라이드 빌드 (정본 함수 전용 · 2분할/3분할 완전 폐기)
compose_cover + compose_story 만 사용. 한 슬라이드 = 사진 1장.
10장 / 원본 사진 9장 전부 사용.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from PIL import Image

SCRIPTS = Path(r"C:\Users\jjky0\welperion-automation\scripts")
sys.path.insert(0, str(SCRIPTS))

from compose_barre import compose_cover, compose_story  # 정본 함수 단일 사용

ROOT     = Path(r"C:\Users\jjky0\welperion-automation")
SRC      = ROOT / "instagram" / "Image" / "방학특강(원본 이미지)"
OUT      = ROOT / "instagram" / "260629_여름방학특강_ep1" / "output(인스타그램)"
GUIDE    = ROOT / "3. 웰페리온 가이드"
REVIEW   = GUIDE / "cmo" / "review"
QUEUE_F  = REVIEW / "review_queue.json"

TOTAL      = 10
CHIP_LABEL = "WELLPERION"
FOOTER     = "WELLPERION  ·  스포츠클럽"

SLIDES_SPEC = [
    # (type, photo, title_eng/meta, title_kor, sub/date_location)
    # type="cover" or "story"
    {
        "type":     "cover",
        "photo":    "3. 수영장.jpg",
        "eng":      "SUMMER CAMP",
        "kor":      "2026 여름 방학특강",
        "date_loc": "6.22 ~ 8.14  ·  2019년 이전 출생 유소년",
    },
    {
        "type":  "story",
        "photo": "방학 수영 레슨.png",
        "meta":  "SWIMMING",
        "title": "수영",
        "sub":   "기초 영법부터, 물과 친해지는 여름",
    },
    {
        "type":  "story",
        "photo": "방학 유소년 체조 강습.png",
        "meta":  "GYMNASTICS",
        "title": "체조",
        "sub":   "구르고 매달리며 키우는 균형감",
    },
    {
        "type":  "story",
        "photo": "트램폴린장.png",
        "meta":  "TRAMPOLINE",
        "title": "트램폴린",
        "sub":   "신나게 뛰며 기르는 순발력",
    },
    {
        "type":  "story",
        "photo": "체조룸(스프링매트 ).png",
        "meta":  "FACILITY",
        "title": "안전한 체조룸",
        "sub":   "스프링 매트 전용 공간",
    },
    {
        "type":  "story",
        "photo": "스쿼시 강습.jpg",
        "meta":  "SQUASH",
        "title": "스쿼시",
        "sub":   "순발력과 집중을 한 번에",
    },
    {
        "type":  "story",
        "photo": "스쿼시장.png",
        "meta":  "SQUASH COURT",
        "title": "전용 스쿼시 코트",
        "sub":   "정식 규격 코트에서",
    },
    {
        "type":  "story",
        "photo": "골프 강습.jpg",
        "meta":  "GOLF",
        "title": "골프",
        "sub":   "집중력과 매너를 배우는 시간",
    },
    {
        "type":  "story",
        "photo": "골프룸.jpg",
        "meta":  "GOLF STUDIO",
        "title": "실내 골프 연습실",
        "sub":   "날씨 걱정 없이 사계절",
    },
    {
        "type":  "story",
        "photo": "방학 수영 레슨.png",
        "meta":  "2026 SUMMER CAMP",
        "title": "여름 자리를 예약하세요",
        "sub":   "1:6 소수정예 · 횟수 자율조정 · 주차 제공",
    },
]

CAPTION = """2026 여름 방학특강 모집

6월 22일 ~ 8월 14일
2019년 이전 출생 유소년 대상

아이의 여름 한나절을, 네 가지 운동으로 채웁니다.
수영 · 체조 · 스쿼시 · 골프 — 한 곳에서.

1:6 소수정예로 꼼꼼하게, 횟수는 자율 조정,
주차도 제공합니다.

궁금하신 점은 프로필 링크로 문의해 주세요.

#한남동수영 #한남동골프 #유소년스포츠 #주니어스포츠 #여름방학특강 #키즈스포츠 #수영 #체조 #스쿼시 #골프 #스포츠클럽 #웰페리온 #WELLPERION"""


def verify_sources() -> None:
    required = [
        "3. 수영장.jpg",
        "방학 수영 레슨.png",
        "방학 유소년 체조 강습.png",
        "트램폴린장.png",
        "체조룸(스프링매트 ).png",
        "스쿼시 강습.jpg",
        "스쿼시장.png",
        "골프 강습.jpg",
        "골프룸.jpg",
    ]
    missing = [f for f in required if not (SRC / f).exists()]
    if missing:
        print(f"[ERROR] 원본 누락: {missing}")
        raise SystemExit(1)
    print("  원본 9장 확인 완료")


def build_slides() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    # 기존 슬라이드 삭제 (post_*.jpg 한정)
    for old in OUT.glob("post_*.jpg"):
        old.unlink()

    paths: list[Path] = []
    story_num = 1  # cover = 1, story = 2~10
    for spec in SLIDES_SPEC:
        out_path = OUT / f"post_{story_num}.jpg"
        if spec["type"] == "cover":
            compose_cover(
                photo_path=SRC / spec["photo"],
                title_eng=spec["eng"],
                title_kor=spec["kor"],
                date_location=spec["date_loc"],
                output_path=out_path,
            )
        else:
            compose_story(
                photo_path=SRC / spec["photo"],
                meta_line=spec["meta"],
                title_kor=spec["title"],
                sub_text=spec["sub"],
                footer_text=FOOTER,
                current=story_num,
                total=TOTAL,
                output_path=out_path,
                chip_label=CHIP_LABEL,
            )
        paths.append(out_path)
        story_num += 1
    return paths


def build_montage(slide_paths: list[Path]) -> Path:
    """5×2 그리드 몽타주."""
    COLS = 5
    TW   = 1080 // COLS  # 216
    TH   = 1080 // COLS  # 216
    ROWS = 2
    mont = Image.new("RGB", (TW * COLS, TH * ROWS), (20, 20, 20))
    for i, p in enumerate(slide_paths):
        if not p.exists():
            continue
        thumb = Image.open(p).convert("RGB").resize((TW, TH), Image.LANCZOS)
        row, col = divmod(i, COLS)
        mont.paste(thumb, (col * TW, row * TH))
    out = OUT / "_검수_미리보기_10장.png"
    mont.save(out, "PNG", optimize=True)
    print(f"  [몽타주] {out.name} ({out.stat().st_size // 1024} KB)")
    return out


def update_review_queue(montage: Path) -> str:
    """review_queue.json 의 CMO-2026-06-29-SUMMER-CAMP-EP1 항목 업데이트.
    slides·caption·preview 갱신, status=검수대기 유지, 새 항목 추가 금지."""
    ts    = datetime.now().strftime("%Y%m%d%H%M%S")
    prev_name = f"260629_여름방학특강_ep1_preview_{ts}.png"
    prev_dest = REVIEW / prev_name

    # 몽타주를 cmo/review 에 복사
    shutil.copy2(montage, prev_dest)
    print(f"  [preview] {prev_dest.name} 복사 완료")

    slides_list = [
        f"instagram/260629_여름방학특강_ep1/output(인스타그램)/post_{i}.jpg"
        for i in range(1, TOTAL + 1)
    ]
    prev_rel = f"cmo/review/{prev_name}"

    data = json.loads(QUEUE_F.read_text(encoding="utf-8"))
    updated = False
    for item in data:
        if item.get("id") == "CMO-2026-06-29-SUMMER-CAMP-EP1":
            item["slides"]  = slides_list
            item["caption"] = CAPTION
            item["preview"] = prev_rel
            item["status"]  = "검수대기"  # 유지
            updated = True
            break
    if not updated:
        raise RuntimeError("review_queue.json 에서 CMO-2026-06-29-SUMMER-CAMP-EP1 항목을 찾을 수 없습니다.")

    QUEUE_F.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  [queue] 업데이트 완료 (slides={len(slides_list)}, preview={prev_rel})")
    return prev_rel


def main() -> None:
    print("=== 2026 여름 방학특강 Ep1 — 정본 재제작 (compose_cover + compose_story) ===")
    print(f"출력: {OUT}")

    verify_sources()
    slides = build_slides()
    assert len(slides) == TOTAL, f"슬라이드 수 불일치: {len(slides)}"

    montage = build_montage(slides)
    preview_rel = update_review_queue(montage)

    print(f"\n=== 빌드 완료 ===")
    print(f"  슬라이드 {TOTAL}장 / 몽타주 1장")
    print(f"  preview: {preview_rel}")


if __name__ == "__main__":
    main()
