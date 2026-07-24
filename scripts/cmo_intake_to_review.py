#!/usr/bin/env python3
"""콘텐츠 접수(강사·직원 등) → 검수큐 배선 + GM 카드 발신 (2026-07-24 · 배9888)

흐름: 접수 폼(3. 웰페리온 가이드/cmo/intake/instructor_intake.html)이 GAS 시트
      ('마케팅 접수' 탭)에 쌓는 접수 건을 조회 액션(action=rows)으로 가져와
      review_queue.json(cmo/review/)에 status="접수검토" 로 추가하고, 신규 건만
      GM 업무보고방(TELEGRAM_CHAT_ID)에 텔레그램 카드 1장을 보낸다.

★ status="접수검토" 는 기존 발행 파이프라인이 쓰는 "검수대기"·APPROVED_STATES
  ({"승인","승인발행대기","approved"}) 어디에도 속하지 않는다 — ig_review_publish_watcher.py
  (검수대기 필터)·ai_daily_series_card.py(검수대기+AIDAY 필터)·publish_digest.py
  (발행완료 그룹 다이제스트, folder 없는 단독 id 그룹이라 애초에 대상 밖)에 걸리지 않는다.
  근거는 이 파일 하단 주석(§근거) 참조.

GAS exec URL은 하드코딩하지 않는다 — instructor_intake.html 안의 GAS_PROD 상수를
정규식으로 읽어 단일 출처를 유지한다(그 파일이 배포 URL의 정본).

토큰(INTAKE_READ_TOKEN)·봇 토큰(TELEGRAM_BOT_TOKEN)·챗ID(TELEGRAM_CHAT_ID)는 전부
telegram_bot/.env 에서만 읽는다(코드·커밋에 값 금지). INTAKE_READ_TOKEN 미설정이면
"미설정" 안내만 하고 정상 종료(0)한다 — 에러로 취급하지 않는다.

멱등: id = "CMO-INTAKE-{YYYYMMDD}-{성함}-{분류}"(특수문자·공백 제거). review_queue.json에
이미 같은 id가 있으면 재추가하지 않는다. 텔레그램 카드도 scripts/.intake_card_sent.json
에 id를 기록해 재발송하지 않는다.

플래그: --dry-run(큐 추가·텔레그램 발송 없이 무엇을 할지만 출력) · --once(1회 실행 ·
반복 루프 없음, 향후 스케줄러 연동 대비 플래그만 수용) · --include-test(테스트 접수행 포함)
· --limit N(조회 건수, 기본 500).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTAKE_HTML = ROOT / "3. 웰페리온 가이드" / "cmo" / "intake" / "instructor_intake.html"
ENV_FILE = ROOT / "telegram_bot" / ".env"
SENT_STATE_PATH = ROOT / "scripts" / ".intake_card_sent.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_queue_util import (  # noqa: E402
    load_review_queue,
    mutate_review_queue,
    SkipSave,
    QueueLockTimeout,
)

try:  # 전역 발송 페이싱(프로세스 간 429 방지) — best-effort
    from tg_outbound_log import log_outbound, pace as _tg_pace
except Exception:
    def log_outbound(*a, **k):
        pass

    def _tg_pace(*a, **k):
        return None

# 시트 헤더 정본(.deploy-instructor/instructor_intake.js INTAKE_HEADER 와 동일 순서) —
# 헤더가 깨져 조회 응답이 col1..col9 로 올 때 이 순서로 이름을 되붙인다.
INTAKE_HEADER = ["접수일시", "성함", "분류", "한줄소개", "회원이얻는것", "사진링크", "영상링크", "드라이브폴더", "상태"]

_TEST_MARKERS = ("__TEST__", "__배포검증__", "__폼검증__")
_ID_SAFE_RE = re.compile(r"[^0-9A-Za-z가-힣]+")
_GAS_URL_RE = re.compile(r'GAS_PROD\s*=\s*"([^"]+)"')


# ---------------------------------------------------------------------------
# .env 로더 (publish_digest.py 와 동형 — os.environ 우선, 없으면 telegram_bot/.env)
# ---------------------------------------------------------------------------
def _load_env_val(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if val:
        return val
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


def _extract_gas_url() -> str:
    """접수 폼 HTML에서 GAS_PROD exec URL을 뽑는다(단일 출처 — 하드코딩 금지)."""
    if not INTAKE_HTML.exists():
        return ""
    text = INTAKE_HTML.read_text(encoding="utf-8")
    m = _GAS_URL_RE.search(text)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# GAS 조회
# ---------------------------------------------------------------------------
def fetch_intake_rows(gas_url: str, token: str, limit: int = 500):
    """action=rows 조회. 반환: (rows list, error_message). 실패 시 rows=None."""
    qs = urllib.parse.urlencode({"action": "rows", "token": token, "limit": str(limit)})
    url = f"{gas_url}?{qs}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:  # urllib 은 GET 리다이렉트 기본 추적
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        return None, f"GAS 조회 네트워크 오류: {e}"
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return None, f"GAS 응답 JSON 파싱 실패: {e}"
    if not data.get("ok"):
        return None, f"GAS 조회 실패 응답: {data.get('error') or data.get('err') or data}"
    return data.get("rows") or [], None


def normalize_row(row: dict) -> dict:
    """실제 헤더명(호환)·col1..col9 폴백(헤더 깨짐) 둘 다 흡수해 표준 키로 통일."""
    out = {}
    for i, key in enumerate(INTAKE_HEADER, start=1):
        if key in row and row[key] not in (None, ""):
            out[key] = row[key]
        else:
            out[key] = row.get(f"col{i}", "")
    out["_row"] = row.get("_row")
    return out


def is_test_row(row: dict) -> bool:
    combined = f"{row.get('성함', '')}{row.get('분류', '')}"
    return any(marker in combined for marker in _TEST_MARKERS)


def _id_safe(s: str) -> str:
    return _ID_SAFE_RE.sub("", str(s or "").strip())


def make_id(row: dict) -> str:
    ts = str(row.get("접수일시") or "")
    date_part = re.sub(r"[^0-9]", "", ts[:10]) or datetime.now().strftime("%Y%m%d")
    date_part = date_part[:8] if len(date_part) >= 8 else date_part
    name = _id_safe(row.get("성함"))
    cat = _id_safe(row.get("분류"))
    return f"CMO-INTAKE-{date_part}-{name}-{cat}"


def build_item(row: dict, item_id: str) -> dict:
    """review_queue.json 기존 스키마(title/channel/account/folder/slides/caption/
    location/collaborators/mentions/status/preview/id/note)에 맞춘 신규 항목.
    접수 원문은 intake 키에 보존(기존 항목 필드는 건드리지 않음)."""
    photo_first = (row.get("사진링크") or "").split("\n")[0].strip()
    return {
        "title": f"콘텐츠 접수 — {row.get('성함', '')} ({row.get('분류', '')})",
        "channel": "콘텐츠 접수",
        "account": "wellperion",
        "folder": "",
        "slides": [],
        "caption": "",
        "location": "",
        "collaborators": [],
        "mentions": [],
        "status": "접수검토",
        "preview": photo_first,
        "id": item_id,
        "note": f"[콘텐츠 접수 {row.get('접수일시', '')}] cmo_intake_to_review.py 자동 수집(배9888)",
        "intake": {
            "성함": row.get("성함", ""),
            "분류": row.get("분류", ""),
            "한줄소개": row.get("한줄소개", ""),
            "회원이얻는것": row.get("회원이얻는것", ""),
            "사진링크": row.get("사진링크", ""),
            "영상링크": row.get("영상링크", ""),
            "드라이브폴더": row.get("드라이브폴더", ""),
            "접수일시": row.get("접수일시", ""),
        },
    }


# ---------------------------------------------------------------------------
# 텔레그램 카드 (GM 업무보고방 · 버튼 없음)
# ---------------------------------------------------------------------------
def _send_telegram_card(bot_token: str, chat_id: str, item: dict) -> bool:
    intake = item.get("intake") or {}
    lines = [
        f"🎬 새 콘텐츠 접수 — {intake.get('성함', '')} ({intake.get('분류', '')})",
        "",
    ]
    if intake.get("한줄소개"):
        lines.append(f"한줄소개: {intake['한줄소개']}")
    if intake.get("회원이얻는것"):
        lines.append(f"회원이 얻는 것: {intake['회원이얻는것']}")
    if intake.get("드라이브폴더"):
        lines.append(f"드라이브 폴더: {intake['드라이브폴더']}")
    if intake.get("접수일시"):
        lines.append(f"접수일시: {intake['접수일시']}")
    message = "\n".join(lines)
    try:
        data = urllib.parse.urlencode({
            "chat_id": chat_id, "text": message,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage", data=data, method="POST")
        _tg_pace()
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
            log_outbound(message, chat_id=chat_id, source="cmo_intake_to_review", ok=ok, kind="sendMessage")
            return ok
    except Exception:
        log_outbound(message, chat_id=chat_id, source="cmo_intake_to_review", ok=False, kind="sendMessage")
        return False


def _load_sent_state() -> dict:
    if not SENT_STATE_PATH.exists():
        return {}
    try:
        data = json.loads(SENT_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_sent_state(state: dict) -> None:
    SENT_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="콘텐츠 접수 → 검수큐 배선 + GM 카드 발신")
    ap.add_argument("--dry-run", action="store_true", help="큐 추가·텔레그램 발송 없이 무엇을 할지만 출력")
    ap.add_argument("--once", action="store_true", help="1회 실행(반복 루프 없음 — 현재 기본 동작과 동일)")
    ap.add_argument("--include-test", action="store_true", help="테스트 접수행(__TEST__ 등)도 포함")
    ap.add_argument("--limit", type=int, default=500, help="GAS 조회 건수(기본 500)")
    args = ap.parse_args()

    gas_url = _extract_gas_url()
    if not gas_url:
        print(f"[ERROR] GAS_PROD URL을 {INTAKE_HTML} 에서 찾지 못함")
        return 1

    token = _load_env_val("INTAKE_READ_TOKEN")
    if not token:
        print("[INFO] INTAKE_READ_TOKEN 미설정 — telegram_bot/.env 에 값 추가 필요(정상 종료)")
        return 0

    raw_rows, err = fetch_intake_rows(gas_url, token, args.limit)
    if err:
        print(f"[ERROR] {err}")
        return 1

    rows = [normalize_row(r) for r in raw_rows]
    total_fetched = len(rows)

    skipped_test = 0
    if not args.include_test:
        kept = [r for r in rows if not is_test_row(r)]
        skipped_test = len(rows) - len(kept)
        rows = kept

    existing = load_review_queue()
    existing_ids = {it.get("id") for it in existing if isinstance(it, dict)}

    candidates = []
    for row in rows:
        item_id = make_id(row)
        if item_id in existing_ids:
            continue
        candidates.append((item_id, row))

    print(
        f"[INFO] 조회 {total_fetched}건 · 테스트제외 {skipped_test}건 · "
        f"기존등록 {len(rows) - len(candidates)}건 · 신규후보 {len(candidates)}건"
    )
    for item_id, row in candidates:
        print(f"  - {item_id}: 성함={row.get('성함')} 분류={row.get('분류')} 접수일시={row.get('접수일시')}")

    if not candidates:
        print("[INFO] 신규 접수 없음 — 종료")
        return 0

    if args.dry_run:
        print("[DRY-RUN] review_queue.json 추가·텔레그램 발송 생략")
        return 0

    added_items: list[dict] = []

    def _mutator(items: list) -> list:
        current_ids = {it.get("id") for it in items if isinstance(it, dict)}
        for item_id, row in candidates:
            if item_id in current_ids:
                continue
            item = build_item(row, item_id)
            items.append(item)
            added_items.append(item)
        if not added_items:
            raise SkipSave
        return items

    try:
        mutate_review_queue(_mutator, holder="cmo_intake_to_review")
    except QueueLockTimeout as e:
        print(f"[ERROR] review_queue 락 획득 실패 — 저장 중단: {e}")
        return 1

    if not added_items:
        print("[INFO] 락 안 재확인 결과 신규 없음(동시 실행으로 이미 추가됨) — 종료")
        return 0

    print(f"[INFO] review_queue.json 에 {len(added_items)}건 추가 완료(status=접수검토)")

    bot_token = _load_env_val("TELEGRAM_BOT_TOKEN")
    chat_id = _load_env_val("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("[WARN] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 미설정 — 카드 발송 생략")
        return 0

    sent_state = _load_sent_state()
    sent_count = 0
    for item in added_items:
        iid = item["id"]
        if sent_state.get(iid):
            continue
        ok = _send_telegram_card(bot_token, chat_id, item)
        sent_state[iid] = {"sent_at": datetime.now().isoformat(timespec="seconds"), "ok": ok}
        if ok:
            sent_count += 1
        else:
            print(f"[WARN] 텔레그램 카드 발송 실패: {iid}")
    _save_sent_state(sent_state)
    print(f"[INFO] GM 업무보고방 카드 발송 {sent_count}/{len(added_items)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# §근거 — status="접수검토" 가 기존 발행 파이프라인에 걸리지 않는 이유
# ---------------------------------------------------------------------------
# 1) scripts/ig_review_publish_watcher.py:336
#      `if it.get("status") != "검수대기": continue`  ← "접수검토" != "검수대기" → 스킵.
# 2) scripts/ig_review_publish_watcher.py:908
#      `if it.get("status") not in APPROVED_STATES: ...`
#      APPROVED_STATES(83행) = {"승인", "승인발행대기", "approved"} ← "접수검토" 미포함.
# 3) scripts/ai_daily_series_card.py:76
#      `if item.get("status") == "검수대기"` 이면서 id 에 "-AIDAY" 포함 요구(70행 주석) —
#      이중으로 걸러짐("접수검토"도 아니고 id 도 "CMO-INTAKE-" 접두라 AIDAY 아님).
# 4) scripts/publish_digest.py
#      send_publish_digest() 는 watcher 가 "이번 실행에서 발행완료로 전환된 항목"만 넘겨
#      호출(위 1·2 에서 이미 걸러진 항목은 애초에 여기 도달 안 함). 설사 그룹 판정이
#      돌아도 _base_key()(136행)는 folder 가 빈 문자열이면 id 로 그룹키를 만들어
#      (141행) 우리 항목만의 고유 그룹이 되므로 다른 콘텐츠 발행 판정과 섞이지 않는다.
