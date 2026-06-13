"""
archive_review_queue.py — review_queue.json 죽은 이력 stub화 + 아카이브 이관 (멱등)

동작:
  1. review_queue.json 로드 (utf-8)
  2. TERMINAL 항목(발행완료·폐기·반려·rejected) → stub 대상
     그 외 → 살아있음, 풀데이터 그대로 유지
  3. TERMINAL 항목 처리 (멱등):
     - 무거운 필드(caption/body/slides) 중 하나라도 있으면 '풀데이터'
     - 풀데이터면: review_queue_archive.json 에 append (같은 id 이미 있으면 skip)
     - review_queue.json 의 해당 항목을 stub 으로 치환
       유지 키: id, title, channel, account, folder, status,
                post_url, published_at, preview, disposed_at,
                processed_at, note
  4. 두 파일 저장 (ensure_ascii=False, indent=2)
  5. 결과 출력

재실행 시 이미 stub 이면 건너뜀, 이미 아카이브에 있으면 append 안 함.
"""

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
QUEUE_PATH = BASE / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
ARCHIVE_PATH = BASE / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue_archive.json"

TERMINAL_STATUSES = {"발행완료", "폐기", "반려", "rejected"}
HEAVY_FIELDS = {"caption", "body", "slides"}
STUB_KEEP_KEYS = {
    "id", "title", "channel", "account", "folder", "status",
    "post_url", "published_at", "preview", "disposed_at",
    "processed_at", "note",
}


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def count_lines(path: Path) -> int:
    with open(path, encoding="utf-8") as f:
        return sum(1 for _ in f)


def main():
    # --- 로드 ---
    queue: list = load_json(QUEUE_PATH)
    archive: list = load_json(ARCHIVE_PATH) if ARCHIVE_PATH.exists() else []

    lines_before = count_lines(QUEUE_PATH)
    archive_ids_before = {item.get("id") for item in archive}

    total = len(queue)
    live_count = 0
    stubbed_count = 0
    already_stub_count = 0
    archive_appended = 0

    new_queue = []
    new_archive = list(archive)  # 기존 아카이브 복사

    for item in queue:
        status = item.get("status", "")
        is_terminal = status in TERMINAL_STATUSES
        has_heavy = any(k in item for k in HEAVY_FIELDS)

        if not is_terminal:
            # 살아있는 항목 — 풀데이터 그대로 유지
            live_count += 1
            new_queue.append(item)
            continue

        # TERMINAL 항목
        if not has_heavy:
            # 이미 stub — 건너뜀
            already_stub_count += 1
            new_queue.append(item)
            continue

        # 풀데이터 TERMINAL → stub화
        item_id = item.get("id")

        # 아카이브에 없으면 원본 append
        if item_id not in archive_ids_before:
            new_archive.append(item)
            archive_ids_before.add(item_id)  # 같은 실행 내 중복 방지
            archive_appended += 1

        # stub 생성 (존재하는 키 중 STUB_KEEP_KEYS 만)
        stub = {k: item[k] for k in STUB_KEEP_KEYS if k in item}
        new_queue.append(stub)
        stubbed_count += 1

    # --- 저장 ---
    save_json(QUEUE_PATH, new_queue)
    save_json(ARCHIVE_PATH, new_archive)

    # --- 검증: 파싱 OK ---
    try:
        load_json(QUEUE_PATH)
        load_json(ARCHIVE_PATH)
    except Exception as e:
        print(f"BLOCKED: 파일 파싱 실패 — {e}", file=sys.stderr)
        sys.exit(1)

    lines_after = count_lines(QUEUE_PATH)
    archive_total = len(new_archive)

    print(
        f"전체 {total}건 / "
        f"살아있음 {live_count}건(풀유지) / "
        f"stub화 {stubbed_count}건 / "
        f"이미stub {already_stub_count}건 / "
        f"아카이브 누적 {archive_total}건(이번 +{archive_appended}) / "
        f"review_queue.json 행수 {lines_before}→{lines_after}"
    )


if __name__ == "__main__":
    main()
