# scripts/review_queue_util.py
# 공유 헬퍼 — review_queue.json 발행 URL 기록
# danggn_upload_playwright.py · kakao_channel_upload_playwright.py 양쪽에서 import.
#
# update_review_post_url(folder, channel_keyword, url)
#   review_queue.json에서 folder 일치 + channel에 channel_keyword 포함 행을 찾아
#   post_url·status·note 갱신 (비파괴·백업 1회).
#   이미 post_url이 있으면 덮지 않는다.
import json
import os
import shutil
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
REVIEW_QUEUE_PATH = (
    _ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
)


def update_review_post_url(folder: str, channel_keyword: str, url: str) -> bool:
    """review_queue.json에서 (folder, channel_keyword) 행을 찾아 post_url 기록.

    Args:
        folder: review_queue 행의 folder 값 (예: 'instagram/260426_WJO_스쿼시_대회')
        channel_keyword: channel 필드에 포함될 부분 문자열 (예: '당근', '카카오 채널')
        url: 캡처한 발행 URL

    Returns:
        True: 갱신 성공 / False: 행 미발견·이미 url 존재(비파괴)·오류
    """
    if not REVIEW_QUEUE_PATH.exists():
        print(f"[WARN] review_queue.json 미존재: {REVIEW_QUEUE_PATH}")
        return False
    try:
        data = json.loads(REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] review_queue.json 읽기 실패: {e}")
        return False

    # folder 정규화 — 슬래시 통일·앞뒤 공백·끝 슬래시 제거
    folder_norm = folder.strip().replace("\\", "/").rstrip("/")

    target_idx = None
    for i, item in enumerate(data):
        item_folder = (item.get("folder") or "").strip().replace("\\", "/").rstrip("/")
        item_channel = item.get("channel") or ""
        if item_folder == folder_norm and channel_keyword in item_channel:
            target_idx = i
            break

    if target_idx is None:
        print(
            f"[WARN] review_queue 행 미발견 — "
            f"folder={folder_norm!r}, channel_keyword={channel_keyword!r}"
        )
        return False

    target = data[target_idx]
    if target.get("post_url"):
        print(f"[INFO] post_url 이미 존재 — 덮지 않음 ({target['post_url']})")
        return False

    # 저장 전 백업 1회
    bak = REVIEW_QUEUE_PATH.with_suffix(".json.bak")
    try:
        shutil.copy2(str(REVIEW_QUEUE_PATH), str(bak))
    except Exception as e:
        print(f"[WARN] 백업 실패 (저장 계속): {e}")

    today = date.today().strftime("%Y-%m-%d")
    target["post_url"] = url
    target["status"] = "발행완료"
    existing_note = (target.get("note") or "").strip()
    append_note = f"[발행시점 캡처 {today}] URL 자동기록"
    target["note"] = (
        (existing_note + " " + append_note).strip() if existing_note else append_note
    )

    try:
        REVIEW_QUEUE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[INFO] review_queue 갱신 완료 — {url}")
        return True
    except Exception as e:
        print(f"[WARN] review_queue.json 저장 실패: {e}")
        return False
