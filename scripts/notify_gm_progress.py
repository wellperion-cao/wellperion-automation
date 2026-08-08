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
import re
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
# 라벨은 GM 이 셸에서 보는 표준 표(wellperion-gm-report §4 5요소)와 같은 말을 쓴다
#   — GM 지시 2026-08-06: "차라리 우리 쿵짝내용 처럼 정리해서 주는게 더 이해하기 쉬워질 것 같은데".
#   두 곳(셸·방)이 다른 어휘를 쓰면 같은 일을 두 번 해독해야 한다.
_SECTIONS = (("cause", "🔍 무엇이 문제였나"), ("fix", "✅ 무엇을 했나"),
             ("check", "🔎 확인한 것"), ("next", "👉 다음"))

# 섹션 없이 통째로 보낼 수 있는 한 줄 보고의 상한(글자).
#   왜: 이 관문은 2026-07-27 부터 섹션 인자를 갖고 있었는데 아무도 안 써서, 방에는 계속
#   기술 용어를 이어 붙인 글벽이 나갔다(GM 2026-08-06 "9:00~9:20 사이에 보내준 것들이
#   이해가 하나도 안 되"). 문서로 권하는 것으로는 안 지켜졌으므로 관문에서 막는다(약속 L02).
#   짧은 한 줄 완료 보고는 그대로 통과한다 — 길어질 때만 나눠 쓰게 만든다.
PLAIN_SUMMARY_MAX = 120

# GM 이 이미 아는 약어 — 이건 기술어로 세지 않는다.
_OK_WORDS = {"ai", "gm", "erp", "ig", "kpi", "pc", "url", "sns", "voc", "cs", "qr", "pdf", "a3"}


def count_jargon(text: str) -> list[str]:
    """GM 이 못 읽는 기술어(라틴 문자 토큰) 목록. 발신은 막지 않고 경고·집계만 한다.

    왜 막지 않나: 이 관문이 거부하면 호출측이 업무보고방으로 폴백해 같은 글벽이 다른 방에
    남는다(조용한 소멸 방지 규칙과 충돌). 대신 매 발신마다 세어 로그에 남긴다 — 건수가
    안 줄면 그때 강제한다(GM 지시 2026-08-06 "이해가 하나도 안 되").
    """
    found = [w for w in re.findall(r"[A-Za-z][A-Za-z_.=-]{2,}", str(text or ""))
             if w.lower().strip("_.=-") not in _OK_WORDS]
    return found


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


def _send_photo(chat_id: int, caption: str, image_path: str) -> bool:
    """그림 1장 + 설명을 방에 보낸다. 실패하면 False (호출부가 글만 보내는 쪽으로 떨어진다).

    2026-08-08 GM 지시로 추가 — 방별 요약 카드를 만들었는데 이 방에 보여줄 길이 없었다.
    발신 관문은 하나로 유지한다: 새 발신 스크립트를 만들지 않고 이 파일 안에 둔다(약속 L21).
    텔레그램 설명(caption)은 1024자 상한이라 넘치면 잘라 보낸다 — 잘린 티가 나게 …을 붙인다.
    """
    import mimetypes, urllib.request, uuid, io, json as _json
    p = Path(image_path)
    if not p.exists():
        print(f"[notify_gm_progress] 그림 파일 없음: {p}", file=sys.stderr)
        return False
    env = {}
    try:
        for line in (_ROOT / "telegram_bot" / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except Exception as exc:
        print(f"[notify_gm_progress] 봇 토큰 읽기 실패: {exc}", file=sys.stderr)
        return False
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False
    cap = caption if len(caption) <= 1024 else caption[:1020].rstrip() + "…"
    b = uuid.uuid4().hex
    buf = io.BytesIO()

    def part(name, val):
        buf.write(f'--{b}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{val}\r\n'.encode())

    part("chat_id", str(chat_id))
    part("caption", cap)
    ctype = mimetypes.guess_type(p.name)[0] or "image/png"
    buf.write(f'--{b}\r\nContent-Disposition: form-data; name="photo"; '
              f'filename="{p.name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode())
    buf.write(p.read_bytes())
    buf.write(f"\r\n--{b}--\r\n".encode())
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendPhoto", data=buf.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return bool(_json.loads(r.read().decode("utf-8")).get("ok"))
    except Exception as exc:
        print(f"[notify_gm_progress] 그림 발송 예외: {type(exc).__name__}: {str(exc)[:120]}",
              file=sys.stderr)
        return False


def notify(summary: str, link: str | None = None, *, ship: str | None = None,
           step: str | None = None, state: str = DEFAULT_STATE,
           dry_run: bool = False, now: datetime | None = None,
           sender=None, log_path=None, rooms_path=None,
           cause: str | None = None, fix: str | None = None,
           check: str | None = None, nxt: str | None = None,
           image: str | None = None) -> dict:
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

    # ★긴 보고는 섹션으로 나눠 써야 나간다(GM 지시 2026-08-06). 한 줄에 다 이어 붙이면
    #   방에 글벽이 남고 GM 은 읽어도 무슨 일인지 모른다. 섹션 인자는 2026-07-27 부터
    #   있었지만 강제가 없어 아무도 안 썼다 — 그래서 관문에서 막는다(약속 L02·L21).
    if (len(summary.strip()) > PLAIN_SUMMARY_MAX
            and not any((v or "").strip() for v in (cause, fix, check, nxt))):
        hint = ("진행현황방 보고가 너무 깁니다(%d자 > %d자)."
                " 한 덩어리로 보내지 말고 --cause(무엇이 문제였나) ·"
                " --fix(무엇을 했나) · --check(확인한 것) · --next(다음) 로 나눠 쓰세요."
                " summary 는 제목 한 줄로 줄입니다."
                % (len(summary.strip()), PLAIN_SUMMARY_MAX))
        print("[notify_gm_progress] " + hint, file=sys.stderr)
        return {"sent": False, "reason": "needs_sections", "text": summary.strip(),
                "chat_id": None, "hint": hint}

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

    # 그림이 있으면 그림 + 설명 한 통으로 보낸다 (GM 지시 2026-08-08 — "요약카드도 만들어지면
    # AI 진행현황에 보여줘"). 글만 보내면 카드를 만들어도 GM 이 볼 데가 없다.
    # 그림 발송이 실패하면 글만이라도 나가게 떨어진다 — 보고가 통째로 사라지면 안 된다.
    if image:
        if _send_photo(chat_id, text, image):
            ok = True
        else:
            print(f"[notify_gm_progress] 그림 발송 실패 — 글만 보냅니다: {image}", file=sys.stderr)
            ok = bool(sender(chat_id, text))
    else:
        ok = bool(sender(chat_id, text))
    jargon = count_jargon(text)
    if jargon:
        print("[notify_gm_progress] GM 이 못 읽는 기술어 %d개: %s — 다음부터 사람 말로 바꿔 쓰세요."
              % (len(jargon), ", ".join(jargon[:8])), file=sys.stderr)
    _append_log(log_path, {
        "ts": now.isoformat(), "summary": summary.strip(), "text": text,
        "link": link or "", "ship": ship or "", "step": step or "", "state": state,
        "sent": ok, "chat_id": chat_id, "jargon": len(jargon), "jargon_words": jargon[:12],
    })
    return {"sent": ok, "reason": "sent" if ok else "send_failed",
            "text": text, "chat_id": chat_id}


def notify_or_fallback(summary: str, link: str | None = None, *, fallback=None, **kwargs) -> dict:
    """notify() 를 부르고, 조용히 사라질 위험이 있는 결과면 fallback 을 호출하는 단일
    관문(2026-07-30 배202 팀리드 지시 — 조용한 소멸 구멍 폐쇄).

    notify() 의 미발송 사유 4가지(gate_off·dedup·daily_cap·room_unresolved, 그 외
    send_failed 포함) 중 **dedup 만 소멸이 아니다**(같은 내용이 최근에 이미 전달됨).
    나머지는 전부 fallback(text) 을 호출해 다른 경로(보통 업무보고방)로 반드시 내보낸다.
    호출부를 여러 곳에서 각자 이 판단을 복제하지 않도록, 그 판단 자체를 여기 하나로
    모은다(약속 L01·L21) — clevel_post_action.py·ig_review_publish_watcher.py 둘 다
    이 함수를 통해서만 AI방 발송을 시도한다.

    fallback: (text: str) -> bool. None 이면 폴백 없이 notify() 결과 그대로 반환(호출부가
    직접 처리해야 하면 이 경우에 한해 자체 판단 — 새 호출부를 늘릴 땐 이 함수를 쓸 것).
    dry_run=True 면 fallback 을 부르지 않는다(payload 미리보기만, 부작용 0).
    반환에 notify() 의 필드 + fell_back(bool) + fallback_ok(bool|None) 를 더해 돌려준다.
    """
    result = notify(summary, link, **kwargs)
    result["fell_back"] = False
    result["fallback_ok"] = None
    if kwargs.get("dry_run"):
        return result
    if result.get("sent") or result.get("reason") == "dedup":
        return result
    if fallback is not None:
        result["fell_back"] = True
        result["fallback_ok"] = bool(fallback(result.get("text", summary)))
    return result


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
    ap.add_argument("--image", default=None,
                    help="같이 보낼 그림 경로(요약 카드 등) — 그림+설명 한 통으로 나간다")
    ap.add_argument("--dry-run", action="store_true", help="실제 발송 없이 payload 미리보기")
    args = ap.parse_args(argv)

    out = notify(args.summary, args.link, ship=args.ship, step=args.step,
                 state=args.state, dry_run=args.dry_run,
                 cause=args.cause, fix=args.fix, check=args.check, nxt=args.nxt,
                 image=args.image)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.dry_run or out["reason"] in ("sent", "gate_off", "dedup", "daily_cap"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
