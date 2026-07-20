# -*- coding: utf-8 -*-
"""
module_silence_detector.py — 모듈 침묵 감지기 (배1307 3차, INC-018 재발방지 확장).
─────────────────────────────────────────────────────────────────────────────
문제: status/module_registry.json 등록 모듈 28개 중 다수가 notify_wired:false
또는 bot_id:null — 돌긴 도는데 결과가 GM에게 도달하지 않는다. 더 심각한 실증
= KPI 집계기가 6일간 죽어있었는데(INC-018) integration_health.check_kpi_freshness()
(25h 초과시 warn) 같은 "측정의 측정"이 그 모듈에는 없어서 아무도 몰랐다.

이 모듈은 그 패턴(check_kpi_freshness)을 등록부 28개 전체로 확장한다.
"알림 붙이기"가 아니라 "침묵 감지기" — 정상일 때는 아무것도 보내지 않고,
예상 주기를 넘겨 조용할 때만, 하루 최대 1통으로 묶어서, 기존 텔레그램
방(자동화현황방)에만 알린다. 새 채널·새 봇 없음.

판정 규칙(코드 한 곳):
  1) "마지막으로 실제 결과를 낸 시각" — 모듈의 data_source.ref 를 프로젝트 루트
     기준으로 해석해 로컬 아티팩트를 찾는다(json/jsonl 내부 timestamp 필드 우선,
     없으면 파일 mtime; ref 가 " + " 로 여러 경로를 겹쳐 적었으면 각각 시도해
     그 중 가장 최근 신호를 채택 — 과소경보보다 과다경보가 더 나쁘다는 설계
     원칙에 따라 관대하게 판단). .py 파일은 "코드 수정"이지 "가동 결과"가
     아니므로 신호 후보에서 제외한다. kind=doc(정적 설계문서)는 애초에 감시
     대상이 아니므로 not_applicable.
  2) "예상 주기" — 등록부에 있는 유일한 주기 필드는 notify_spec.daily/weekly/
     monthly(원래는 '보고 주기' 의미로 만들어졌지만 등록부에 존재하는 유일한
     주기 정보라 이것을 예상 갱신주기로 쓴다 — 없는 필드를 새로 추정하지
     않는다). daily→30h(24h+6h 여유) · weekly→216h(7d+2d 여유) ·
     monthly→840h(31d+4d 여유). 셋 다 false 면 판정불가(임의 추정 금지).
  3) 로컬 아티파트를 못 찾거나 주기가 없으면 무조건 "판정불가" — silent 로
     오분류하지 않는다(실제 KPI 프레시니스 감시는 integration_health.py 의
     check_kpi_freshness 가 여전히 담당·본 모듈은 건드리지 않음).

발신: 침묵 모듈이 1개 이상이면 하루 1통으로 묶어 자동화현황방(기존 채널,
telegram_rooms.json 배선 재사용)에 발송. 정상이면 발신 0. 멱등 로그 =
status/module_silence_log.jsonl(dedup 키 = 날짜만 — 하루 최대 1통).
"""
from __future__ import annotations

import argparse
import glob as glob_mod
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))  # 이 저장소 관행: tz표기 없는 timestamp=KST(erp_status.json
                                     # generated_at(Z)·generated_at_kst 병기 확인, 나머지 jsonl/json
                                     # 은 Z없이 KST 벽시계로 기록 — UTC로 오판정하면 최대 9h 오차)

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from module_registry import load_registry  # noqa: E402
from clevel_colors import color_dot  # noqa: E402

PROJECT_ROOT = Path(_PROJECT_ROOT)
STATUS_DIR = PROJECT_ROOT / "status"
LOG_PATH = STATUS_DIR / "module_silence_log.jsonl"
SNAPSHOT_PATH = STATUS_DIR / "module_silence_snapshot.json"  # 자율현황.html #layer-automation 이 읽는 발행물(로컬 기록 전용·알림 아님)
ROOMS_PATH = STATUS_DIR / "telegram_rooms.json"
BOT_ROOM = "자동화현황방"  # 기존 채널 재사용(새 봇·새 방 금지)
LINK = "https://wellperion-cao.github.io/wellperion-automation/자율현황.html#health"

# ── 예상 갱신주기(h) — notify_spec 의 유일한 주기 필드를 그대로 쓴다 ──────────
DAILY_MAX_H = 30
WEEKLY_MAX_H = 24 * 9   # 216
MONTHLY_MAX_H = 24 * 35  # 840

# json/jsonl 내부에서 찾을 timestamp 키(우선순위 순, 실측 확인한 키들)
TS_KEYS = ("generated_at", "updated_at", "last_run", "logged_at", "ts", "timestamp", "at", "date")

# 신호로 쓰지 않을 확장자(코드 파일 — 수정 시각≠가동 결과)
_EXCLUDE_EXTS = (".py",)
_DATA_EXTS = (".json", ".jsonl")


def _now_utc(now=None):
    if now is not None:
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _parse_ts(s):
    """ISO 계열 문자열 → tz-aware datetime. 실패 시 None(예외로 죽지 않음)."""
    if not isinstance(s, str) or not s:
        return None
    try:
        has_z = "Z" in s
        v = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            # Z 없이 저장된 timestamp = 이 저장소 관행상 KST 벽시계(위 KST 상수 주석 참조)
            dt = dt.replace(tzinfo=timezone.utc if has_z else KST)
        return dt
    except Exception:
        return None


def _mtime_dt(path: Path):
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except Exception:
        return None


def _ts_from_json_file(path: Path):
    """json 파일 내부 TS_KEYS 중 첫 매치 → datetime. 없으면 None(mtime은 호출부가 fallback)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    for k in TS_KEYS:
        if k in data:
            dt = _parse_ts(data.get(k))
            if dt is not None:
                return dt
    return None


def _ts_from_jsonl_file(path: Path):
    """jsonl 마지막 비공백 줄 → TS_KEYS 매치. 없으면 None."""
    try:
        with path.open("r", encoding="utf-8") as f:
            last = None
            for line in f:
                line = line.strip()
                if line:
                    last = line
        if last is None:
            return None
        rec = json.loads(last)
    except Exception:
        return None
    if not isinstance(rec, dict):
        return None
    for k in TS_KEYS:
        if k in rec:
            dt = _parse_ts(rec.get(k))
            if dt is not None:
                return dt
    return None


def _latest_file_in_dir(dir_path: Path):
    """디렉터리 재귀 탐색 → 가장 최근 mtime 파일(.py·__pycache__·숨김 제외). 없으면 None."""
    best = None
    best_dt = None
    try:
        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
            for fn in files:
                if fn.startswith(".") or fn.endswith(_EXCLUDE_EXTS):
                    continue
                p = Path(root) / fn
                dt = _mtime_dt(p)
                if dt is not None and (best_dt is None or dt > best_dt):
                    best, best_dt = p, dt
    except Exception:
        return None, None
    return best, best_dt


def _candidate_signal(path: Path):
    """단일 파일 후보 → (datetime, method설명). .py는 호출부에서 이미 걸러짐."""
    ext = path.suffix.lower()
    if ext == ".json":
        ts = _ts_from_json_file(path)
        if ts is not None:
            return ts, f"{path.name} 내부 timestamp"
        mt = _mtime_dt(path)
        return mt, f"{path.name} mtime"
    if ext == ".jsonl":
        ts = _ts_from_jsonl_file(path)
        if ts is not None:
            return ts, f"{path.name} 마지막 레코드 timestamp"
        mt = _mtime_dt(path)
        return mt, f"{path.name} mtime"
    mt = _mtime_dt(path)
    return mt, f"{path.name} mtime"


def _strip_paren(s: str) -> str:
    return re.sub(r"\([^)]*\)", "", s).strip()


def _resolve_segment(seg: str, root: Path):
    """ref 한 조각(paren 제거 전) → 유효 신호 후보 (datetime, method) 또는 None.
    - '{date}' 등 플레이스홀더 → glob 패턴으로 최신 매치 탐색
    - 정확한 파일 경로 → 그 파일
    - 정확한 디렉터리 경로 → 디렉터리 내 최신 파일
    - 그 외 → 경로 구성요소를 뒤에서부터 줄여가며(최소 2단) 존재하는 디렉터리 탐색
      (예: 'wellperion-hr/drafts/loops/ 스윕 결과' → 'wellperion-hr/drafts/loops' 시도)
    """
    seg = _strip_paren(seg).strip()
    if not seg:
        return None

    if "{" in seg and "}" in seg:
        pattern = re.sub(r"\{[^}]*\}", "*", seg)
        full_pattern = str(root / pattern)
        matches = glob_mod.glob(full_pattern)
        matches = [m for m in matches if not m.endswith(_EXCLUDE_EXTS)]
        if not matches:
            return None
        best_path = max(matches, key=lambda m: os.path.getmtime(m))
        return _candidate_signal(Path(best_path))

    candidate = root / seg
    if candidate.is_file() and not seg.endswith(_EXCLUDE_EXTS):
        return _candidate_signal(candidate)
    if candidate.is_dir():
        p, dt = _latest_file_in_dir(candidate)
        if p is not None:
            return dt, f"디렉터리 {seg} 내 최신파일({p.name}) mtime"
        return None

    # 경로 구성요소를 뒤에서부터 줄여 유효 디렉터리 탐색 — 설명 문구가 경로 뒤에
    # 공백으로 붙은 케이스만("wellperion-hr/drafts/loops/ 스윕 결과" 등). 공백이
    # 없는 순수 파일경로(예: "status/module_silence_log.jsonl"가 아직 없는 경우)는
    # 절대 부모 디렉터리로 대체하지 않는다 — 그러면 무관한 형제파일 mtime을 빌려와
    # '그 파일이 없어도 항상 ok'로 오판정하는 자기지시적 함정이 생긴다(실측 발견:
    # 본 모듈 cto-module-silence-detector 자기등록 시 재현·수정).
    if " " not in seg:
        return None
    parts = [p for p in re.split(r"[/\\]", seg) if p]
    while len(parts) >= 2:
        parts = parts[:-1]
        trial = root / "/".join(parts)
        if trial.is_dir():
            p, dt = _latest_file_in_dir(trial)
            if p is not None:
                return dt, f"디렉터리 {'/'.join(parts)} 내 최신파일({p.name}) mtime"
            return None
        if trial.is_file() and not trial.suffix.lower() in _EXCLUDE_EXTS:
            return _candidate_signal(trial)
    return None


def resolve_last_activity(module: dict, root: Path = PROJECT_ROOT, now=None):
    """모듈의 data_source.ref → (datetime|None, method:str, detail:str).
    로컬 아티팩트를 하나도 못 찾으면 (None, 'unresolvable', 사유)."""
    ds = module.get("data_source") or {}
    ref = ds.get("ref") or ""
    if not ref:
        return None, "unresolvable", "data_source.ref 없음"

    segments = [s for s in ref.split(" + ") if s.strip()]
    best_dt = None
    best_method = None
    tried = []
    for seg in segments:
        result = _resolve_segment(seg, root)
        tried.append(_strip_paren(seg).strip())
        if result is None:
            continue
        dt, method = result
        if dt is None:
            continue
        if best_dt is None or dt > best_dt:
            best_dt, best_method = dt, method

    if best_dt is None:
        return None, "unresolvable", f"로컬 아티팩트 없음(시도: {tried})"
    return best_dt, best_method, ""


def expected_max_silence_hours(notify_spec):
    """notify_spec.daily/weekly/monthly → 예상 최대 침묵 시간(h). 셋 다 false면 None."""
    spec = notify_spec or {}
    if spec.get("daily"):
        return DAILY_MAX_H, "daily"
    if spec.get("weekly"):
        return WEEKLY_MAX_H, "weekly"
    if spec.get("monthly"):
        return MONTHLY_MAX_H, "monthly"
    return None, None


def judge_module(module: dict, root: Path = PROJECT_ROOT, now=None):
    """모듈 1개 판정 → dict(id, owner_role, owner_nick, feature, status, ...).
    status: silent | ok | unmeasurable | not_applicable"""
    now = _now_utc(now)
    mid = module.get("id")
    base = {
        "id": mid,
        "owner_role": module.get("owner_role"),
        "owner_nick": module.get("owner_nick"),
        "feature": module.get("feature"),
    }

    ds = module.get("data_source") or {}
    if ds.get("kind") == "doc":
        return {**base, "status": "not_applicable", "detail": "정적 설계문서(가동형 모듈 아님)"}

    last_dt, method, detail = resolve_last_activity(module, root=root, now=now)
    max_h, cadence_label = expected_max_silence_hours(module.get("notify_spec"))

    if last_dt is None:
        return {**base, "status": "unmeasurable", "detail": f"로컬 아티팩트 판정불가 — {detail}",
                "method": method}

    if max_h is None:
        silence_h = (now - last_dt).total_seconds() / 3600
        return {**base, "status": "unmeasurable",
                "detail": f"주기 미선언(daily/weekly/monthly 전부 false) — 판정불가",
                "last_activity": last_dt.isoformat(), "method": method,
                "silence_hours": round(silence_h, 1)}

    silence_h = (now - last_dt).total_seconds() / 3600
    status = "silent" if silence_h > max_h else "ok"
    return {
        **base,
        "status": status,
        "last_activity": last_dt.isoformat(),
        "method": method,
        "cadence": cadence_label,
        "max_allowed_hours": max_h,
        "silence_hours": round(silence_h, 1),
        "detail": f"{silence_h:.1f}h 전 마지막 신호({method}) · 허용 {max_h}h({cadence_label})",
    }


def scan_registry(registry=None, root: Path = PROJECT_ROOT, now=None, registry_path=None):
    """등록부 전체 모듈 판정 → list[dict]."""
    reg = registry if registry is not None else load_registry(registry_path)
    modules = reg.get("modules", []) if isinstance(reg, dict) else []
    return [judge_module(m, root=root, now=now) for m in modules]


def silent_modules(scan_result):
    return [r for r in scan_result if r.get("status") == "silent"]


# ── 스냅샷 발행(로컬 파일만 기록 · 알림·발신과 무관) ────────────────────────
def build_snapshot(scan, now=None):
    """전체 스캔 결과 → 화면(자율현황.html)이 읽을 스냅샷 dict."""
    now = _now_utc(now)
    counts = {"ok": 0, "silent": 0, "unmeasurable": 0, "not_applicable": 0}
    for r in scan:
        st = r.get("status")
        if st in counts:
            counts[st] += 1
    return {
        "_doc": "모듈 침묵 감지기 최신 스캔 스냅샷 — 자율현황.html #layer-automation 렌더 전용. "
                "알림 발신과 무관(발신 로그는 module_silence_log.jsonl). "
                "발행: module_silence_detector.py --publish.",
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_kst": (now.astimezone(KST)).strftime("%Y-%m-%d %H:%M"),
        "total": len(scan),
        "summary": counts,
        "modules": scan,
    }


def publish_snapshot(path: Path = SNAPSHOT_PATH, root: Path = PROJECT_ROOT, now=None,
                      registry_path=None):
    """전체 스캔 → 스냅샷 파일 기록(덮어쓰기). 네트워크 호출·알림 발신 없음."""
    scan = scan_registry(root=root, now=now, registry_path=registry_path)
    snap = build_snapshot(scan, now=now)
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return snap


# ── 발신(하루 1통 묶음) ────────────────────────────────────────────────────
def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _already_sent_today(date_str, log_path=LOG_PATH):
    if not os.path.exists(log_path):
        return False
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("date") == date_str and rec.get("sent") is True:
                    return True
    except Exception:
        return False
    return False


def _already_logged_today(date_str, log_path=LOG_PATH):
    """오늘자 레코드가 하나라도 있으면 True(발송 여부 무관 — 하트비트 중복 방지용)."""
    if not os.path.exists(log_path):
        return False
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if json.loads(line).get("date") == date_str:
                    return True
    except Exception:
        return False
    return False


def _append_log(record, log_path=LOG_PATH):
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def build_digest_message(silent_list, now=None):
    """침묵 모듈 목록 → 텔레그램 메시지(1통). silent_list 비어있으면 None(발송 없음)."""
    if not silent_list:
        return None
    now = _now_utc(now)
    lines = [f"🔇 모듈 침묵 감지 — {len(silent_list)}건 (예상 주기 초과)"]
    for m in sorted(silent_list, key=lambda x: -(x.get("silence_hours") or 0)):
        dot = color_dot(m.get("owner_role"))
        days = (m.get("silence_hours") or 0) / 24
        lines.append(
            f"  {dot} {m['id']} — {days:.1f}일째 조용함 "
            f"(허용 {m.get('cadence')}주기 · {m.get('feature', '')[:40]})"
        )
    lines.append(LINK)
    return "\n".join(lines)


def run_detector(*, dry_run=True, root: Path = PROJECT_ROOT, now=None,
                  registry_path=None, log_path=LOG_PATH, rooms_path=ROOMS_PATH,
                  sender=None):
    """전체 스캔 → 침묵 있으면 하루 1통(멱등) 발송/드라이런. 반환: 결과 dict."""
    now = _now_utc(now)
    date_str = now.strftime("%Y-%m-%d")

    scan = scan_registry(root=root, now=now, registry_path=registry_path)
    silent = silent_modules(scan)

    if not silent:
        # 하트비트: 발신 없음(무소식이 희소식)이지만, 이 감지기 자신도 등록부 모듈
        # (cto-module-silence-detector)이라 매일 1줄이라도 남겨야 자기 신선도를
        # 스스로 증명할 수 있다(라이브 실행시에만 — dry-run 은 부작용 0 유지).
        if not dry_run and not _already_logged_today(date_str, log_path=log_path):
            _append_log({"date": date_str, "sent": False, "reason": "no_op",
                         "n_silent": 0}, log_path=log_path)
        return {"date": date_str, "scan": scan, "silent": [], "action": "no_op",
                "reason": "침묵 모듈 없음 — 발신 없음(무소식이 희소식)"}

    text = build_digest_message(silent, now=now)

    if dry_run:
        return {"date": date_str, "scan": scan, "silent": silent, "action": "dry-run",
                "text": text}

    if _already_sent_today(date_str, log_path=log_path):
        return {"date": date_str, "scan": scan, "silent": silent, "action": "skip",
                "reason": "dedup(오늘 이미 발송)"}

    rooms = _load_json(rooms_path, {})
    chat_id = rooms.get(BOT_ROOM)
    if chat_id is None:
        _append_log({"date": date_str, "sent": False, "reason": "room_unresolved",
                      "n_silent": len(silent)}, log_path=log_path)
        return {"date": date_str, "scan": scan, "silent": silent, "action": "skip",
                "reason": "room_unresolved"}

    if sender is None:
        from notify.telegram_send import send as sender  # noqa: PLC0415

    ok = bool(sender(chat_id, text))
    _append_log({"date": date_str, "sent": ok, "chat_id": chat_id,
                 "n_silent": len(silent), "ids": [m["id"] for m in silent]},
                log_path=log_path)
    return {"date": date_str, "scan": scan, "silent": silent,
            "action": "sent" if ok else "send_failed", "text": text}


def main(argv=None):
    ap = argparse.ArgumentParser(description="모듈 침묵 감지기(배1307 3차)")
    ap.add_argument("--live", action="store_true",
                     help="실제 발송(기본은 드라이런 — 안전 기본값)")
    ap.add_argument("--scan-only", action="store_true", help="전체 스캔 표만 출력, 발신 로직 미실행")
    ap.add_argument("--publish", action="store_true",
                     help="스냅샷 파일만 기록(status/module_silence_snapshot.json) — 알림 발신 없음")
    args = ap.parse_args(argv)

    if args.publish:
        snap = publish_snapshot()
        c = snap["summary"]
        print(f"[published] {SNAPSHOT_PATH} — 총 {snap['total']}건 "
              f"(정상 {c['ok']} · 침묵 {c['silent']} · 모름 {c['unmeasurable']} · 대상아님 {c['not_applicable']})")
        return 0

    if args.scan_only:
        scan = scan_registry()
        for r in scan:
            print(f"[{r['status']:>13}] {r['id']:<32} {r.get('detail', '')}")
        n_silent = sum(1 for r in scan if r["status"] == "silent")
        n_unmeas = sum(1 for r in scan if r["status"] == "unmeasurable")
        n_na = sum(1 for r in scan if r["status"] == "not_applicable")
        n_ok = sum(1 for r in scan if r["status"] == "ok")
        print(f"\n총 {len(scan)}건 — ok {n_ok} · silent {n_silent} · "
              f"판정불가 {n_unmeas} · 대상아님 {n_na}")
        return 0

    out = run_detector(dry_run=not args.live)
    print(f"[{out['action']}] date={out['date']} 침묵 {len(out.get('silent', []))}건")
    if out.get("text"):
        print("--- 메시지 미리보기 ---")
        print(out["text"])
    if out.get("reason"):
        print(f"사유: {out['reason']}")
    return 0


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
