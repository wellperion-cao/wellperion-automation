# -*- coding: utf-8 -*-
"""
notify_gm_progress.py — AI 진행현황방으로 "단계마다 1줄" 진행 보고 헬퍼(단일 관문).
─────────────────────────────────────────────────────────────────────────────
배경(2026-07-13, GM 지시): 의미 있는 완료(딜리버러블)마다 짧게 1줄 보고.

[2026-07-25 GM 지시로 확장·이설 — 새 모듈 신설 없이 이 관문 하나만 고침(약속 L21)]
GM 질문: "진행중인 걸 내가 어떻게 확인할 수 있지?" — G1 항로 보드는 '진행중' 딱지만
보여줄 뿐 지금 어디까지 갔는지가 안 보여, GM 이 매번 물어봐야 했다. 원인은 이 헬퍼가
2026-07-13 배선 후 12일간 한 번도 안 쓰인 채 잠들어 있었기 때문이다(실측: 발송 이력
1건, 배선 완료 알림 그 자체뿐). 그래서 새로 만들지 않고 이 잠든 관문을 되살린다.

바뀐 것 2가지:
  1) 목적지 = AI 진행현황방(구 자동화현황방). GM 확정(2026-07-25): 업무보고방은 사람이
     하는 현실 업무만, AI 항로·C-Level 진행건은 AI 진행현황방. 이 헬퍼가 나르는 것은
     정의상 후자다. chat_id 는 하드코딩하지 않고 status/telegram_rooms.json 에서
     module_reporter.resolve_chat_id() 단일 지점으로 해소한다(약속 L01 — 판정 로직 복제 금지).
  2) '완료' 한 종류였던 것을 단계 상태 4종으로 넓힌다 — 시작·진행·완료·막힘. 배 번호와
     단계 이름을 함께 실어 GM 이 한 줄만 보고 "누가·몇 번 배·몇 단계까지" 를 안다.

  예) ⏳ 시토 81 · 2단계 — AI 백엔드 발신 6건 이동, 코드 수정 중
      ⏸ 시토 81 · 방 이름 변경 — GM 권한 필요로 막힘

clevel_post_action.py 의 정식 L18 완료 보고(C-Level .bat/큐 흐름)와는 별개의
경량 채널 — 세션 중 단계를 넘길 때 즉석에서 호출한다.

스팸 방지 게이트(그대로 유지 — 채널만 바뀌었지 폭주 위험은 같다):
  1) PROGRESS_REPORT_LIVE env(킬스위치) — "0"/"false"/"off"/"no" 로 끄면 미발송.
  2) dedup — 동일 본문이 최근 DEDUP_WINDOW_MINUTES 이내 발송된 적 있으면 스킵.
  3) daily cap — 하루 DAILY_CAP 건 초과 시 스킵(폭주 방지 안전판).
  4) 루틴 필터(is_routine) — task_id/커밋 메시지에 ADHOC·auto-log·chore·mirror
     류 마커가 있으면 호출측(clevel_post_action.py 등)이 애초에 notify() 를
     부르지 않도록 판별하는 헬퍼(스팸 원천 차단).

CLI:
  python scripts/notify_gm_progress.py "요약" [링크] [--ship "시토 81"] [--step "2단계"]
                                        [--state start|doing|done|blocked] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# ── 상수 ─────────────────────────────────────────────────────────────────────
GM_CHAT_ID = 8254867551  # GM 개인 업무보고방 — 이 헬퍼의 목적지가 아니다(폴백 아님).
                         # is_routine 만 쓰는 기존 import 를 깨지 않으려 상수는 남긴다.
ROOM_KEY = "자동화현황방"  # status/telegram_rooms.json 의 키. 방 표시명은 2026-07-25
                          # GM 이 "AI 진행현황"으로 변경 — 키 개명은 별도 단계에서 참조
                          # 전수 정리와 함께(지금 키만 바꾸면 module_registry 참조가 끊긴다).
ROOMS_PATH = _ROOT / "status" / "telegram_rooms.json"
LOG_PATH = _ROOT / "status" / "progress_report_log.jsonl"
DAILY_CAP = 40
DEDUP_WINDOW_MINUTES = 60
KST = timezone(timedelta(hours=9))

_ROUTINE_MARKERS = ("adhoc", "auto-log", "autolog", "chore", "mirror")

# 단계 상태 → 머리 아이콘. G1 항로 보드 아이콘 표준과 같은 뜻으로 맞춘다
# (⚓=대기·막힘 / 🏁=입항 완료). 여기선 한 줄 알림이라 ⏸ 대신 ⚓ 를 쓴다.
STATE_ICONS = {
    "start": "🚀",    # 착수
    "doing": "⏳",    # 진행중
    "done": "✅",     # 단계 완료
    "blocked": "⚓",  # 막힘·대기(완료 아님)
}
DEFAULT_STATE = "done"


# ── 루틴/자동 마커 판별(스팸 원천 차단용 헬퍼 — 호출측이 사용) ────────────────
def is_routine(*texts: str) -> bool:
    """task_id·커밋 메시지 등에 루틴/자동 마커(ADHOC·auto-log·chore·mirror)가
    있으면 True. 대소문자 무시. 호출측(clevel_post_action.py 등)이 완료라도
    notify 호출 자체를 건너뛰는 데 사용한다."""
    for t in texts:
        low = (t or "").lower()
        if any(marker in low for marker in _ROUTINE_MARKERS):
            return True
    return False


def _live() -> bool:
    val = os.environ.get("PROGRESS_REPORT_LIVE", "1").strip().lower()
    return val not in ("0", "false", "off", "no")


def _now_kst() -> datetime:
    return datetime.now(tz=KST)


def _load_log(log_path: Path) -> list:
    if not log_path.exists():
        return []
    out = []
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return out


def _append_log(log_path: Path, record: dict) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _recent_duplicate(key: str, now: datetime, entries: list) -> bool:
    """key = 조립된 한 줄 본문. 2026-07-25 이전 기록에는 text 칸이 없으므로
    summary 로 폴백한다 — 옛 기록이 dedup 에서 통째로 빠지면 배선 직후 같은
    보고가 한 번 더 나간다(무해하지만 정확하지 않다)."""
    cutoff = now - timedelta(minutes=DEDUP_WINDOW_MINUTES)
    for rec in entries:
        stored = rec.get("text") or rec.get("summary")
        if stored != key or not rec.get("sent"):
            continue
        try:
            ts = datetime.fromisoformat(rec["ts"])
        except Exception:
            continue
        if ts >= cutoff:
            return True
    return False


def _today_sent_count(now: datetime, entries: list) -> int:
    today = now.strftime("%Y-%m-%d")
    return sum(1 for rec in entries if rec.get("sent") and str(rec.get("ts", "")).startswith(today))


def resolve_room(rooms_path=None):
    """AI 진행현황방 chat_id 해소. 해소 실패 시 None(발송 스킵 — 조용히 엉뚱한 방으로
    보내지 않는다). 판정 로직은 module_reporter.resolve_chat_id 하나만 쓴다(약속 L01)."""
    path = Path(rooms_path) if rooms_path else ROOMS_PATH
    try:
        rooms = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    try:
        from module_reporter import resolve_chat_id  # noqa: PLC0415
    except Exception:
        return None
    return resolve_chat_id(ROOM_KEY, rooms)


# 섹션 표기 — 순서 고정. GM 이 폰에서 훑는 순서와 같게 둔다(무엇을 왜 → 뭘 했나 → 진짜 되나 → 다음).
_SECTIONS = (("cause", "🔎 원인"), ("fix", "🔧 고친 것"),
             ("check", "📊 확인"), ("next", "👉 다음"))


def _bullets(raw: str) -> str:
    """'|' 로 나눈 항목을 한 줄에 하나씩. 폰에서 줄이 길면 안 읽히므로 문장을 쪼개 둔다."""
    items = [x.strip() for x in str(raw).split("|") if x.strip()]
    return "\n".join("· " + x for x in items)


def build_text(summary: str, link: str | None = None, *,
               ship: str | None = None, step: str | None = None,
               state: str = DEFAULT_STATE, cause: str | None = None,
               fix: str | None = None, check: str | None = None,
               nxt: str | None = None) -> str:
    """진행현황방 본문 조립.

    ▸섹션 인자(cause·fix·check·nxt)를 하나라도 주면 **여러 줄 구조**로 낸다:
        ✅ 시토 147 — 제목
        (빈 줄)
        🔎 원인 / 🔧 고친 것 / 📊 확인 / 👉 다음  — 각 항목 '· ' 불릿
      왜: 한 줄에 [원인][고침][실측][다음]을 이어붙이면 폰에서 글벽이 된다(GM 2026-07-27
      "명확하게, 가독성있게"). 약속 L12(짧고 한눈에)는 방 보고에도 그대로 적용된다.
    ▸섹션을 하나도 안 주면 기존 그대로 한 줄 — 짧은 완료 보고를 쓰는 호출부와 호환."""
    icon = STATE_ICONS.get(state, STATE_ICONS[DEFAULT_STATE])
    head = " · ".join(p for p in ((ship or "").strip(), (step or "").strip()) if p)
    body = summary.strip()
    title = f"{icon} {head} — {body}" if head else f"{icon} {body}"

    vals = {"cause": cause, "fix": fix, "check": check, "next": nxt}
    blocks = [f"{label}\n{_bullets(vals[key])}" for key, label in _SECTIONS if (vals.get(key) or "").strip()]
    if not blocks:
        return title + (" " + link.strip() if link else "")
    text = title + "\n\n" + "\n\n".join(blocks)
    return text + (("\n\n🔗 " + link.strip()) if link else "")


def notify(summary: str, link: str | None = None, *, ship: str | None = None,
           step: str | None = None, state: str = DEFAULT_STATE,
           dry_run: bool = False, now: datetime | None = None,
           sender=None, log_path=None, rooms_path=None,
           cause: str | None = None, fix: str | None = None,
           check: str | None = None, nxt: str | None = None) -> dict:
    """
    AI 진행현황방으로 진행 1줄 발송.

    ship/step: 배 이름(예 "시토 81")·단계 이름(예 "2단계"). 없으면 생략된다.
    state: start|doing|done|blocked (기본 done — 기존 호출부 동작 보존).
    sender: send(chat_id, text) -> bool. None 이면 notify.telegram_send.send 지연 로드.
    dry_run: True 면 실제 발송/로그 기록 없이 payload 만 반환(네트워크 0).
    반환: {"sent": bool, "reason": str, "text": str, "chat_id": int|None}
    """
    log_path = Path(log_path) if log_path else LOG_PATH
    now = now or _now_kst()
    text = build_text(summary, link, ship=ship, step=step, state=state,
                      cause=cause, fix=fix, check=check, nxt=nxt)

    if dry_run:
        return {"sent": False, "reason": "dry_run", "text": text,
                "chat_id": resolve_room(rooms_path)}

    if not _live():
        return {"sent": False, "reason": "gate_off", "text": text, "chat_id": None}

    entries = _load_log(log_path)

    # dedup 키 = 조립된 본문. 같은 배의 단계가 다르면 다른 줄이라 통과한다
    # (요약만 비교하면 "1단계 완료"와 "2단계 완료"가 같은 걸로 묶여 삼켜진다).
    if _recent_duplicate(text, now, entries):
        return {"sent": False, "reason": "dedup", "text": text, "chat_id": None}

    if _today_sent_count(now, entries) >= DAILY_CAP:
        return {"sent": False, "reason": "daily_cap", "text": text, "chat_id": None}

    chat_id = resolve_room(rooms_path)
    if chat_id is None:
        # 방을 못 찾으면 보내지 않는다. 조용한 실패를 남기지 않게 로그에는 남긴다.
        _append_log(log_path, {
            "ts": now.isoformat(), "summary": summary.strip(), "text": text,
            "link": link or "", "sent": False, "reason": "room_unresolved",
            "room_key": ROOM_KEY,
        })
        return {"sent": False, "reason": "room_unresolved", "text": text, "chat_id": None}

    if sender is None:
        from notify.telegram_send import send as sender  # noqa: PLC0415

    ok = bool(sender(chat_id, text))
    _append_log(log_path, {
        "ts": now.isoformat(), "summary": summary.strip(), "text": text,
        "link": link or "", "ship": ship or "", "step": step or "", "state": state,
        "sent": ok, "chat_id": chat_id,
    })
    return {"sent": ok, "reason": "sent" if ok else "send_failed",
            "text": text, "chat_id": chat_id}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="AI 진행현황방 진행 보고 1줄 발송 헬퍼")
    ap.add_argument("summary", help='보고 요약 1줄 (예: "AI 백엔드 발신 6건 이동")')
    ap.add_argument("link", nargs="?", default=None, help="증거/산출물 링크(선택)")
    ap.add_argument("--ship", default=None, help='배 이름 (예: "시토 81")')
    ap.add_argument("--step", default=None, help='단계 이름 (예: "2단계")')
    ap.add_argument("--state", default=DEFAULT_STATE, choices=sorted(STATE_ICONS),
                    help="단계 상태 (start·doing·done·blocked, 기본 done)")
    # 섹션 인자 — 여러 항목은 '|' 로 나눈다(한 줄에 하나씩 불릿으로 나간다).
    ap.add_argument("--cause", default=None, help='원인 (여러 개면 "A|B")')
    ap.add_argument("--fix", default=None, help='고친 것 (여러 개면 "A|B")')
    ap.add_argument("--check", default=None, help='확인·실측 (여러 개면 "A|B")')
    ap.add_argument("--next", dest="nxt", default=None, help='다음 (여러 개면 "A|B")')
    ap.add_argument("--dry-run", action="store_true", help="실제 발송 없이 payload 미리보기")
    args = ap.parse_args(argv)

    out = notify(args.summary, args.link, ship=args.ship, step=args.step,
                 state=args.state, dry_run=args.dry_run,
                 cause=args.cause, fix=args.fix, check=args.check, nxt=args.nxt)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.dry_run or out["reason"] in ("sent", "gate_off", "dedup", "daily_cap"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
