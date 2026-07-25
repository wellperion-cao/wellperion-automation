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
import functools
import json
import os
import re
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


# ─────────────────────────────────────────────────────────────────────────
# 발행 품질 게이트 — 금지어 · CTA 표준 · 과장 신호 (배10038, 2026-07-25 시모)
#
# 배경: 2026-07-24 회사소개서에서 금지어 6건(현대하이페리온·피트니스·하이엔드·사교)이
#   사람 눈에만 발견됐다. 기계가 발행 전(M5 등록 시점)에 잡아야 한다.
#
# 새 관문 금지(약속 L21) — review_queue.json 을 쓰는 모든 경로가 예외 없이 지나는
#   mutate_review_queue() 한 곳(위 21행 규칙 참조)에만 흡수한다. register_channel_review.py·
#   publish_register.py 등 어떤 등록 헬퍼를 거치든 결국 이 함수를 통과하므로 우회로가 없다.
#
# 새 금지어 목록 금지(약속 L01) — 하드코딩 사본을 두지 않고 기존 단일 출처를 런타임 직독한다:
#   CLAUDE.md §0 브랜드 용어 표 + ssot/약속.json L08(브랜드 말투). CTA 표준 문구는
#   scripts/cta_utm.py CLEAN_CTA_TEXT(코드 정본, canon_values.json cta_channel_rules 확정)를
#   그대로 재사용 — 재서술하지 않는다.
#
# 검사 항목: ①금지어 ②미기입 플레이스홀더('[GM 확인' — 대필방지용 자리가 안 채워진 채
#   승인·발행된 2026-07-18/07-25 실사고 재발방지, 캡션/본문 + folder 내 *_diary_source.html
#   모두 스캔) ③CTA 표준 문구 ④과장 신호.
#
# 위반해도 저장을 막지 않는다(요구사항 ④) — status='검수대기' 항목에 qc_flags(list) 로
# 경고만 남긴다. 통과하면 qc_flags 를 지운다(본문 수정 후 재검수 시 옛 경고가 안 남게).
# ─────────────────────────────────────────────────────────────────────────

_CLAUDE_MD_PATH = _ROOT / "CLAUDE.md"
_YAKSOK_PATH = _ROOT / "ssot" / "약속.json"

# 과장 신호 — 팀 지시 원문 예시(최고·1위·100%) 그대로. 별도 SSOT 없음(요구사항 원문 명시값).
_OVERCLAIM_TERMS = ("최고", "1위", "100%")


@functools.lru_cache(maxsize=1)
def _load_banned_terms() -> tuple:
    """금지어 목록 — CLAUDE.md §0 브랜드 용어 표 + ssot/약속.json L08 을 직독해 합집합.

    새 금지어 SSOT 신설 금지(약속 L01) — 기존 두 출처만 파싱한다. 실패해도 예외로 죽지
    않게 best-effort(파일 형식이 바뀌어도 등록 자체는 계속되게).
    """
    terms: set = set()
    try:
        text = _CLAUDE_MD_PATH.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "브랜드 용어" not in line:
                continue
            # "X" 금지→"Y" 패턴에서 왼쪽(금지어)만 — 오른쪽(대체어)은 "금지"가 안 붙어 매칭 안 됨
            for m in re.finditer(r'"([^"]+)"\s*금지', line):
                t = m.group(1).strip()
                if t:
                    terms.add(t)
    except Exception as exc:
        print(f"[WARN] qc_gate: CLAUDE.md 금지어 표 파싱 실패(무시): {exc}")
    try:
        yaksok = json.loads(_YAKSOK_PATH.read_text(encoding="utf-8"))
        for lesson in yaksok.get("lessons", []) or []:
            if lesson.get("id") != "L08":
                continue
            m = re.search(r"외부엔\s*'([^']+)'", lesson.get("내용", "") or "")
            if m:
                for t in m.group(1).split("·"):
                    t = t.strip()
                    if t:
                        terms.add(t)
    except Exception as exc:
        print(f"[WARN] qc_gate: 약속.json L08 파싱 실패(무시): {exc}")
    return tuple(sorted(terms))


@functools.lru_cache(maxsize=1)
def _load_cta_standard() -> str:
    """표준 CTA 문구 — scripts/cta_utm.py CLEAN_CTA_TEXT 를 그대로 재사용(코드 정본).

    새로 재서술하지 않는다(약속 L01) — import 실패해도 등록은 계속되게 안전한 폴백만 둔다.
    """
    try:
        _scripts_dir = str(Path(__file__).resolve().parent)
        if _scripts_dir not in sys.path:
            sys.path.insert(0, _scripts_dir)
        from cta_utm import CLEAN_CTA_TEXT  # noqa: E402

        return CLEAN_CTA_TEXT
    except Exception as exc:
        print(f"[WARN] qc_gate: cta_utm.CLEAN_CTA_TEXT import 실패 — 폴백 사용: {exc}")
        return "문의: wellperion.com/ko/inquiry"


def _qc_scan_item(item: dict) -> list:
    """검수대기 항목 1건의 title/body/caption을 스캔해 경고 문구 리스트 반환(통과=[]).

    CTA 검사는 URL-CTA 채널(블로그·카페·카카오·당근)에만 적용한다 — IG는 설계상(원칙 ⑤,
    cta_utm.py) 캡션에 CTA URL 없이 bio 링크로 유도하므로 같은 검사를 적용하면 정상 IG
    캡션마다 오탐이 난다.
    """
    text = " ".join(str(item.get(k) or "") for k in ("title", "body", "caption"))
    flags: list = []

    banned = [t for t in _load_banned_terms() if t and t in text]
    if banned:
        flags.append(f"금지어: {', '.join(banned)}")

    # 미기입 플레이스홀더 — 대필 방지용 '[GM 확인: …]' 자리가 GM 미기입 채로 승인·발행된 실제
    # 사고(2026-07-18 CASE12 캡션, 2026-07-25 CASE14 슬라이드) 재발방지. 캡션/본문뿐 아니라
    # 개인계정 손글씨 슬라이드 원본(ep{NN}_diary_source.html)에도 같은 표기로 남으므로 함께 스캔.
    placeholder_hits = []
    if "[GM 확인" in text:
        placeholder_hits.append("캡션/본문")
    folder = item.get("folder")
    if folder:
        try:
            for html_path in sorted((_ROOT / folder).glob("*_diary_source.html")):
                try:
                    if "[GM 확인" in html_path.read_text(encoding="utf-8"):
                        placeholder_hits.append(html_path.name)
                except Exception:
                    pass
        except Exception:
            pass
    if placeholder_hits:
        flags.append(f"미기입 플레이스홀더([GM 확인] 남음): {', '.join(placeholder_hits)}")

    channel = str(item.get("channel") or "")
    is_ig = "인스타그램" in channel
    if not is_ig and "문의" in text:
        cta = _load_cta_standard()
        if cta not in text:
            if "문의 :" in text:  # 콜론 앞 공백 — 07-24 GM 결재로 폐기된 옛 표기(cta_utm.py 주석)
                flags.append(f"CTA 문구가 옛 표기('문의 :' 공백) — 표준('{cta}')과 다름")
            else:
                flags.append(f"CTA 문구가 표준('{cta}')과 다름 — 확인 필요")

    overclaim = [t for t in _OVERCLAIM_TERMS if t in text]
    if overclaim:
        flags.append(f"과장 표현: {', '.join(overclaim)}")

    return flags


def _apply_quality_gate(items: list) -> None:
    """status='검수대기' 항목만 in-place 스캔해 qc_flags 갱신. 저장을 막지 않는다(플래그만)."""
    for it in items:
        if not isinstance(it, dict) or it.get("status") != "검수대기":
            continue
        try:
            flags = _qc_scan_item(it)
        except Exception as exc:
            print(f"[WARN] qc_gate: 스캔 예외(등록은 계속) — {it.get('id')}: {exc}")
            continue
        if flags:
            it["qc_flags"] = flags
        elif "qc_flags" in it:
            del it["qc_flags"]


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
        # 발행 품질 게이트 — 저장 직전, 검수대기 항목만 스캔해 qc_flags 갱신(차단 없음).
        # 이 자리(락 임계구역 안, save 직전)가 모든 review_queue 쓰기가 예외 없이 지나는
        # 지점이라 여기 한 곳에만 박으면 우회로가 없다(약속 L21).
        try:
            _apply_quality_gate(new_items)
        except Exception as exc:
            print(f"[WARN] qc_gate: 전체 예외(저장은 계속) — {exc}")
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
