# scripts/review_queue_util.py
# review_queue.json 단일 쓰기 관문(SSOT) — 락 직렬화 + 원자적 저장.
#
# 배경 (2026-07-21 사고):
#   11:25 커밋 fe9be3f9d 가 「AI하루」 10편(review_queue.json 10건)을 추가했는데,
#   4분 뒤 11:29 무관한 커밋 b96cac0ea 가 스테일 사본으로 덮어써 10건 전량 소실.
#   원인 = review_queue.json 쓰기 경로가 여러 개인데 파일 락이 0개(평범한
#   read→modify→write). 같은 문제를 겪은 status/_queue.json 은 QueueLock(msvcrt
#   바이트락) 도입 후 실무 유실 0건 → 그 장치를 그대로 재사용한다.
#
# 규칙:
#   - review_queue.json 을 쓰는 모든 코드는 이 모듈의 mutate_review_queue()
#     (또는 review_queue_lock() 임계구역)을 경유한다. 직접 write_text 금지.
#   - 임계구역 = load 부터 save 까지 전체. 읽기와 쓰기가 벌어지면 락이 무의미하다.
#   - 락 이름은 review_queue.lock — status/_queue.json(queue.lock)과 서로 안 막는다.
#   - 락 획득 실패는 조용히 덮어쓰지 않고 QueueLockTimeout 예외로 명확히 실패한다.
#     (획득/해제/타임아웃 로그 = logs/queue_lock.log)
#
# 공개 API:
#   review_queue_lock(holder)          — 임계구역 컨텍스트매니저
#   load_review_queue()                — 큐 로드(list)
#   save_review_queue_atomic(items)    — tmp+os.replace 원자적 저장
#   mutate_review_queue(mutator, holder) — 락 안에서 load→mutator→save
#   update_review_post_url(...)        — 발행 URL 기록(위 관문 경유)
import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
REVIEW_QUEUE_PATH = (
    _ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
)

# status/_queue.json 이 쓰는 검증된 락 장치를 그대로 재사용(새 락 발명 금지).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from queue_lock import QueueLock, QueueLockTimeout  # noqa: E402

REVIEW_QUEUE_LOCK_NAME = "review_queue.lock"

__all__ = [
    "REVIEW_QUEUE_PATH",
    "REVIEW_QUEUE_LOCK_NAME",
    "QueueLockTimeout",
    "review_queue_lock",
    "SkipSave",
    "load_review_queue",
    "save_review_queue_atomic",
    "mutate_review_queue",
    "merge_save_review_queue",
    "update_review_post_url",
]


def review_queue_lock(holder: str = "?") -> QueueLock:
    """review_queue.json 전용 크로스-프로세스 락.

    with review_queue_lock('holder'): <load→modify→save>
    획득 실패 시 QueueLockTimeout — 조용한 덮어쓰기 금지.
    """
    return QueueLock(holder, str(_ROOT), lock_name=REVIEW_QUEUE_LOCK_NAME)


def load_review_queue() -> list:
    """review_queue.json 로드.

    파일이 없을 때만 [] 를 준다. 파일이 있는데 파싱 실패·비배열이면 **예외**를 던진다
    — 여기서 [] 를 돌려주면 이어지는 저장이 큐 전체를 날린다(유실 사고 그 자체).
    """
    if not REVIEW_QUEUE_PATH.exists():
        return []
    raw = REVIEW_QUEUE_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)  # 파싱 실패 → 예외 전파(저장 중단)
    if not isinstance(data, list):
        raise ValueError("review_queue.json 최상위가 list 가 아님 — 저장 중단")
    return data


def save_review_queue_atomic(items: list) -> None:
    """tmp + os.replace 원자적 쓰기 — 락 없는 reader 도 반쪽 파일을 안 본다.

    포맷은 기존 write_text(json.dumps(..., indent=2)) 와 바이트 동일
    (ensure_ascii=False · indent=2 · 끝 개행 없음 · 텍스트모드 CRLF).
    """
    if not isinstance(items, list):
        raise ValueError("review_queue 저장 거부: 최상위가 list 가 아님")
    p = str(REVIEW_QUEUE_PATH)
    tmp = f"{p}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    last_err = None
    for _ in range(25):  # 윈도우 AV·인덱서 순간 잠금 대비 ~0.5s 재시도
        try:
            os.replace(tmp, p)
            return
        except PermissionError as e:
            last_err = e
            import time as _t

            _t.sleep(0.02)
    try:
        os.remove(tmp)
    except OSError:
        pass
    raise last_err


class SkipSave(Exception):
    """mutator 가 '바꿀 게 없다'고 알릴 때 raise — 저장 없이 락만 풀고 빠진다."""


def mutate_review_queue(mutator, holder: str = "?") -> list:
    """락 임계구역에서 load → mutator(items) → 원자적 save.

    mutator(items): 새 리스트를 반환하거나, items 를 in-place 수정 후 None 반환.
                    변경 없음이면 SkipSave 를 raise (파일 무변경).
    긴 네트워크 작업(Playwright 등)은 락 밖에서 끝내고, 여기서 최신본을 다시
    읽어 필드만 반영할 것 — 락을 길게 잡지 않으면서도 스테일 덮어쓰기를 막는다.
    """
    with review_queue_lock(holder):
        items = load_review_queue()
        try:
            result = mutator(items)
        except SkipSave:
            return items
        new_items = result if result is not None else items
        save_review_queue_atomic(new_items)
        return new_items


def merge_save_review_queue(updated_items: list, holder: str = "?", id_key: str = "id") -> list:
    """긴 작업(Playwright 발행·URL 회수 등) 뒤 저장용 — id 기준 병합 저장.

    락을 몇 분씩 잡으면 다른 writer 가 전부 타임아웃 나므로, 무거운 작업은 락 밖에서
    끝낸다. 대신 저장 순간 락 안에서 디스크 최신본을 다시 읽어, updated_items 의
    항목을 id 로 덮어쓰고(없으면 append) 저장한다.
    → 그 사이 다른 프로세스가 추가한 신규 항목은 절대 사라지지 않는다(07-21 사고 유형).
    """
    by_id = {}
    no_id = []
    for it in updated_items:
        if isinstance(it, dict) and it.get(id_key):
            by_id[it[id_key]] = it
        else:
            no_id.append(it)

    def _apply(fresh: list):
        merged = []
        seen = set()
        for it in fresh:
            key = it.get(id_key) if isinstance(it, dict) else None
            if key and key in by_id:
                merged.append(by_id[key])
                seen.add(key)
            else:
                merged.append(it)
        # 디스크에 없던(=이번 실행이 새로 만든) 항목만 뒤에 append
        for key, it in by_id.items():
            if key not in seen:
                merged.append(it)
        # id 없는 항목: 디스크에 이미 있는 만큼은 위에서 보존됐다. 초과분(=이번에 새로
        # 생긴 것)만 추가 — 무조건 extend 하면 중복이 쌓인다.
        fresh_no_id = sum(
            1 for it in fresh if not (isinstance(it, dict) and it.get(id_key))
        )
        surplus = len(no_id) - fresh_no_id
        if surplus > 0:
            merged.extend(no_id[-surplus:])
        return merged

    return mutate_review_queue(_apply, holder=holder)


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

    # folder 정규화 — 슬래시 통일·앞뒤 공백·끝 슬래시 제거
    folder_norm = folder.strip().replace("\\", "/").rstrip("/")
    outcome = {"ok": False}

    def _apply(data: list):
        target_idx = None
        for i, item in enumerate(data):
            item_folder = (
                (item.get("folder") or "").strip().replace("\\", "/").rstrip("/")
            )
            item_channel = item.get("channel") or ""
            if item_folder == folder_norm and channel_keyword in item_channel:
                target_idx = i
                break

        if target_idx is None:
            print(
                f"[WARN] review_queue 행 미발견 — "
                f"folder={folder_norm!r}, channel_keyword={channel_keyword!r}"
            )
            raise SkipSave

        target = data[target_idx]
        if target.get("post_url"):
            print(f"[INFO] post_url 이미 존재 — 덮지 않음 ({target['post_url']})")
            raise SkipSave

        # 저장 전 백업 1회 (락 안에서 — 백업과 저장 사이 끼어들기 없음)
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
        outcome["ok"] = True
        return data

    try:
        mutate_review_queue(_apply, holder="review_queue_util:update_post_url")
    except QueueLockTimeout as e:
        print(f"[WARN] review_queue 락 획득 실패 — 저장 중단(덮어쓰기 안 함): {e}")
        return False
    except Exception as e:
        print(f"[WARN] review_queue.json 저장 실패: {e}")
        return False

    if outcome["ok"]:
        print(f"[INFO] review_queue 갱신 완료 — {url}")
    return outcome["ok"]
