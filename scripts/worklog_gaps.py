# scripts/worklog_gaps.py
# 전 C-Level 공용 "빠진 것" 감지기 (2026-07-23, GM 승인 · CMO-2026-07-23-WORKLOG-PANEL).
#
# 계기: AI하루 EP10이 검수큐 등록 누락돼 아무도 못 봄(2026-07-23 실사고). worklog.py 는
# "한 일"만 남긴다 — 이 모듈은 실제 파일을 대조해 "빠진 것"(짝 불일치)을 자동 적발한다.
#
# 구조: role 별 규칙 등록부(_RULES). 각 규칙은 인자 없이 호출되어 gap dict 리스트를
#   반환한다. CMO 외 role 은 규칙 0건(비워둠) — 각 C-Level 은 나중에 자기 규칙만
#   _RULES[role] 에 append 하면 됨(공용 스캔·출력 로직은 그대로 재사용).
#
# 규칙 에러 격리: 규칙 하나가 예외를 던져도 해당 규칙만 rules_run 에 error 로 남고
#   나머지 규칙은 계속 실행한다(전체 실패 금지).
#
# 산출: status/worklog_gaps.json (고정 스키마 — 화면 담당 에이전트가 이 규격으로 렌더 중,
#   기존 필드 절대 변경 금지 · first_seen/age 2필드는 2026-07-23 추가):
#   {"generated_at": "...",
#    "gaps": [{"role","severity","title","detail","hint","ref","first_seen","age"}],
#    "rules_run": [{"role","rule","ok","error"}],
#    "summary": {"신규": N, "누적": M}}
#   - first_seen(YYYY-MM-DD) = 이 gap 이 처음 발견된 날짜. status/worklog_gaps_state.json
#     (role|rule|ref 키 → first_seen) 로 스캔 간 유지 — 이미 있던 키는 날짜 유지, 사라진 키는
#     상태에서 제거(재발하면 그때가 새 first_seen).
#   - age("신규"/"누적") = gap 이 가리키는 대상 자체가 언제 것이냐(발견일 아님) 기준 판정.
#     대상 날짜를 못 구하면 보수적으로 "누적".
#
# CLI:
#   python scripts/worklog_gaps.py --scan
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
REVIEW_QUEUE_PATH = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
SHIP_QUEUE_PATH = ROOT / "status" / "_queue.json"
GAPS_PATH = ROOT / "status" / "worklog_gaps.json"
GAPS_STATE_PATH = ROOT / "status" / "worklog_gaps_state.json"
INSTAGRAM_DIR = ROOT / "instagram"

KST = timezone(timedelta(hours=9))
_NEW_AGE_DAYS = 14  # 대상 날짜가 이 안이면 "신규", 넘으면 "누적"(배9578 백로그 판정 기준)


def _parse_folder_date(name: str) -> date | None:
    """폴더명 앞 6자리 날짜접두(YYMMDD, 예 '260627')를 date 로 변환. 실패 시 None."""
    m = re.match(r"^(\d{2})(\d{2})(\d{2})", name)
    if not m:
        return None
    try:
        return date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return None


def _parse_iso_date(value: str) -> date | None:
    """ISO8601 문자열(타임존 유무 무관)에서 date 만 추출. 실패 시 None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        return None


def _classify_age(target_date: date | None, today: date) -> str:
    """대상 날짜 기준 신규(14일 이내)/누적 판정. 대상 날짜 못 구하면 보수적으로 '누적'."""
    if target_date is None:
        return "누적"
    days = (today - target_date).days
    if days < 0:
        days = 0
    return "신규" if days <= _NEW_AGE_DAYS else "누적"

_SCRIPTS_DIR = ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_review_queue() -> list[dict]:
    data = _load_json(REVIEW_QUEUE_PATH, [])
    return data if isinstance(data, list) else []


def _load_ship_queue() -> list[dict]:
    data = _load_json(SHIP_QUEUE_PATH, [])
    return data if isinstance(data, list) else []


# ─────────────────────────────────────────────────────────────────────────
# CMO 규칙 v1 — 전부 2026-07-23 실사고(AI하루 EP10 검수큐 등록 누락) 기반, 파일로 검증 가능.
# ─────────────────────────────────────────────────────────────────────────

# 날짜접두 폴더명에서 시리즈 접두(숫자 앞 비숫자 구간)를 뽑는다. 예:
#   "260721_AI하루01_아침항로" → ("AI하루", "01")   "260602_AI3_초등생도AI" → ("AI","3")
_SERIES_DIR_RE = re.compile(r"^\d{6}_([^\d]+)(\d+)")
_MIN_SERIES_SIZE = 2  # 최소 2편 모여야 '시리즈'로 판정(단발 폴더의 우연한 숫자 오탐 방지)

# 폐기 마커 — 실제 파일로 GM 폐기 결정이 남아있는 폴더(예 _폐기_DEPRECATED.md)는
# 시리즈 모수에서 제외. 폴더명 블랙리스트가 아니라 "GM이 남긴 폐기 기록 파일 실존 여부"라는
# 구조적 신호(2026-07-23 실측 발견 — 260616_AI16_휴관이벤트공지문AI로채널별).
_DEPRECATED_MARKER_RE = re.compile(r"폐기|DEPRECATED", re.IGNORECASE)


def _is_deprecated_folder(folder: Path) -> bool:
    try:
        return any(_DEPRECATED_MARKER_RE.search(p.name) for p in folder.glob("*.md"))
    except Exception:
        return False


def _looks_like_real_content(folder: Path) -> bool:
    """실제 발행 콘텐츠 폴더의 구조적 특징으로 판정(폴더명 블랙리스트 아님, 2026-07-23 보강):
    output* 하위(최대 3단계 재귀 — 채널별 output(블로그) 등 다단 구조 지원)에 실제 이미지
    파일이 있으면 제작완료로 판정. 폐기 마커가 있으면 무조건 제외(GM 폐기 결정 보존).
    실측 근거: 웰페리온_프리미엄공간_3칸(목업, output* 없음) 오탐 vs 실전사례08(output/post_*.jpg
    실존, 진짜 미등록) 대조로 검증."""
    if _is_deprecated_folder(folder):
        return False
    try:
        for sub in folder.rglob("output*"):
            if not sub.is_dir():
                continue
            if any(sub.glob("*.jpg")) or any(sub.glob("*.jpeg")) or any(sub.glob("*.png")):
                return True
    except Exception:
        return False
    return False


def _series_episode_dirs() -> dict[tuple[str, str], list[Path]]:
    """instagram/ (공식) 과 instagram/namuk.wellperion/ (개인) 하위 날짜접두 폴더를
    시리즈 접두로 그룹핑 — 실제 발행 콘텐츠 폴더(_looks_like_real_content)만 대상.
    key=(parent_label, series_prefix) → 폴더 경로 리스트. 실제 디렉터리 목록만 사용(지어내지 않음)."""
    groups: dict[tuple[str, str], list[Path]] = {}
    scan_targets: list[tuple[str, Path, set[str]]] = []
    if INSTAGRAM_DIR.exists():
        scan_targets.append(("instagram", INSTAGRAM_DIR, {"namuk.wellperion", "Image", "Movie"}))
        namuk_dir = INSTAGRAM_DIR / "namuk.wellperion"
        if namuk_dir.exists():
            scan_targets.append(("instagram/namuk.wellperion", namuk_dir, set()))
    for parent_label, parent_dir, exclude_names in scan_targets:
        try:
            children = sorted(p for p in parent_dir.iterdir() if p.is_dir() and p.name not in exclude_names)
        except Exception:
            continue
        for child in children:
            m = _SERIES_DIR_RE.match(child.name)
            if not m:
                continue
            if not _looks_like_real_content(child):
                continue  # 목업·시안·폐기 — 시리즈 모수에서 제외(오탐 방지, 2026-07-23)
            series_prefix = m.group(1)
            key = (parent_label, series_prefix)
            groups.setdefault(key, []).append(child)
    return {k: v for k, v in groups.items() if len(v) >= _MIN_SERIES_SIZE}


def rule_series_queue_parity() -> list[dict]:
    """시리즈 폴더 편수 ↔ review_queue.json 등록 편수(폴더 단위 존재 여부) 불일치 적발.
    (오늘 EP10 누락이 걸렸어야 했던 규칙 — 지금은 등록 완료라 통과가 정상.)"""
    queue = _load_review_queue()
    registered_folders = {
        str(it.get("folder", "")).strip() for it in queue if str(it.get("folder", "")).strip()
    }
    today = datetime.now(tz=KST).date()
    gaps: list[dict] = []
    for (parent_label, series_prefix), dirs in _series_episode_dirs().items():
        missing_names = []
        for d in dirs:
            try:
                rel = d.relative_to(ROOT).as_posix()
            except Exception:
                continue
            if rel not in registered_folders:
                missing_names.append(d.name)
        if missing_names:
            total = len(dirs)
            # age 판정용 대상 날짜 = 미등록 폴더 중 가장 최근 날짜(가장 최근 것 기준 신규 판정 — 보수적).
            missing_dates = [dt for n in missing_names if (dt := _parse_folder_date(n)) is not None]
            target_date = max(missing_dates) if missing_dates else None
            gaps.append({
                "role": "cmo",
                "severity": "high",
                "title": f"{series_prefix} 시리즈 {total}편 / 검수큐 등록 {total - len(missing_names)}편",
                "detail": f"{', '.join(missing_names)} 미등록 — 순번이 와도 카드가 안 나감",
                "hint": "review_queue.json 에 등록 필요 (register_publish / register_channel_review)",
                # 시리즈 정체성(안정 키) — 특정 미등록 폴더명이 아니라 시리즈 자체를 가리켜야
                # 스캔마다 first_seen 키가 흔들리지 않음(2026-07-23 보강).
                "ref": f"{parent_label}::{series_prefix}",
                "age": _classify_age(target_date, today),
            })
    return gaps


_URL_REQUIRED_STATUSES = {"발행완료", "발행검증대기"}

# 실측(review_queue.json) 상 실제 등장하는 channel 원문 7종을 실무진이 읽는 짧은 이름으로 정리.
# 키워드 포함 매칭 — 특정 문자열 하드코딩 블랙리스트가 아니라 채널 실명 축약(2026-07-23 보강,
# 같은 콘텐츠가 채널별로 여러 줄 뜰 때 제목만으론 구분 안 되던 문제 수정).
_CHANNEL_LABEL_KEYWORDS = (
    ("블로그", "블로그"),
    ("카페", "카페"),
    ("카카오", "카카오"),
    ("당근", "당근"),
    ("인스타그램", "인스타그램"),
)
_TITLE_TRUNC_LEN = 24  # 이 길이를 넘으면 말줄임(…) — 화면 잘림 방지, 채널명은 항상 앞에 두어 보존


def _short_channel_label(channel: str) -> str:
    """channel 원문(예 '인스타그램 (namuk.wellperion)')을 짧은 이름으로. 알려진 채널 키워드가
    없으면 원문 그대로 반환(지어내지 않음)."""
    ch = (channel or "").strip()
    for keyword, label in _CHANNEL_LABEL_KEYWORDS:
        if keyword in ch:
            return label
    return ch or "채널미상"


def _truncate_title(text: str, limit: int = _TITLE_TRUNC_LEN) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def rule_published_without_url() -> list[dict]:
    """status='발행완료'/'발행검증대기' 인데 url·post_url 둘 다 빈 항목 적발.
    같은 콘텐츠가 채널별(블로그·카페·카카오·당근 등)로 여러 엔트리 존재할 수 있어 title 에
    채널명을 앞세우고 ref 도 채널까지 포함해 항목마다 고유하게 만든다(2026-07-23 보강 —
    화면에 동일 제목이 중복으로 보이던 문제·first_seen 키 충돌 위험 방지).
    age 판정 = published_at(콘텐츠가 실제 발행된 시점) 기준 — 없으면 보수적으로 '누적'
    (배9578 발행 주소 회수 정착 백로그, 지금 당장 손댈 일 아님)."""
    queue = _load_review_queue()
    today = datetime.now(tz=KST).date()
    gaps: list[dict] = []
    for it in queue:
        status = it.get("status", "")
        if status not in _URL_REQUIRED_STATUSES:
            continue
        url = (it.get("url") or it.get("post_url") or "").strip()
        if url:
            continue
        title = it.get("title", it.get("id", "?"))
        item_id = it.get("id", "")
        channel_label = _short_channel_label(it.get("channel", ""))
        short_title = _truncate_title(title)
        target_date = _parse_iso_date(it.get("published_at", ""))
        gaps.append({
            "role": "cmo",
            "severity": "mid",
            "title": f"{channel_label} · {short_title} — {status}인데 URL 없음",
            "detail": f"status={status} · url/post_url 필드 모두 비어있음 · 콘텐츠={title}",
            "hint": "게시 URL 수동 보강 또는 scripts/reconcile_published.py 로 재회수",
            "ref": f"{item_id}::{channel_label}" if item_id else f"{title}::{channel_label}",
            "age": _classify_age(target_date, today),
        })
    return gaps


def rule_ig_only_no_siblings() -> list[dict]:
    """공식계정(wellperion) IG만 등록되고 블로그·카페·카카오·당근 형제가 0건인 항목 적발.
    ★ ig_review_publish_watcher.find_missing_channel_siblings() 그대로 재사용(신규 로직 미작성).
    해당 함수가 없으면(임포트 실패) 이 규칙은 건너뛰고 rules_run 에 사유를 남긴다."""
    from ig_review_publish_watcher import find_missing_channel_siblings  # noqa: PLC0415

    queue = _load_review_queue()
    missing_items = find_missing_channel_siblings(queue)
    today = datetime.now(tz=KST).date()
    gaps: list[dict] = []
    for it in missing_items:
        title = it.get("title", it.get("id", "?"))
        # age 판정 = published_at 우선, 없으면 folder 폴더명 날짜접두 폴백, 둘 다 없으면 '누적'.
        target_date = _parse_iso_date(it.get("published_at", "")) or _parse_folder_date(
            Path(str(it.get("folder", ""))).name
        )
        gaps.append({
            "role": "cmo",
            "severity": "mid",
            "title": f"{title} — 형제채널 미등록(인스타만)",
            "detail": "공식계정 인스타는 등록됐으나 블로그·카페·카카오·당근 형제 엔트리 0건",
            "hint": "register_channel_review.register_channels() 로 형제 채널 등록 확인 필요",
            "ref": it.get("folder", it.get("id", "")),
            "age": _classify_age(target_date, today),
        })
    return gaps


_NOTE_DATE_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2})")
_STALE_DAYS = 7


def rule_stale_ship_note() -> list[dict]:
    """status/_queue.json 의 CMO 배 중 status=IN_PROGRESS 인데 note 안 마지막 날짜 표기가
    7일 이상 지난 건 적발("기록이 일을 못 따라옴"). 날짜 표기 자체가 없는 note 는 판정
    보류(지어내지 않음 — 못 찾으면 건너뜀)."""
    ships = _load_ship_queue()
    today = datetime.now(tz=KST).date()
    gaps: list[dict] = []
    for ship in ships:
        if ship.get("clevel") != "cmo" or ship.get("status") != "IN_PROGRESS":
            continue
        note = ship.get("note", "") or ""
        dates = _NOTE_DATE_RE.findall(note)
        if not dates:
            continue
        try:
            last_date = max(datetime.strptime(d, "%Y-%m-%d").date() for d in dates)
        except Exception:
            continue
        days = (today - last_date).days
        if days >= _STALE_DAYS:
            title = ship.get("title", ship.get("task_id", "?"))
            gaps.append({
                "role": "cmo",
                "severity": "low",
                "title": f"{title} — note 최근기록 {days}일 경과",
                "detail": f"마지막 note 날짜 표기={last_date.isoformat()} · 오늘={today.isoformat()}",
                "hint": "진행 현황 note append 필요(기록이 일을 못 따라옴)",
                "ref": ship.get("task_id", ""),
                "age": _classify_age(last_date, today),
            })
    return gaps


# role 별 규칙 등록부 — 다른 C-Level 은 자기 role 리스트에 함수만 추가하면 됨(공용 스캔 재사용).
_RULES: dict[str, list] = {
    "ceo": [],
    "cfo": [],
    "chro": [],
    "cmo": [
        rule_series_queue_parity,
        rule_published_without_url,
        rule_ig_only_no_siblings,
        rule_stale_ship_note,
    ],
    "coo": [],
    "cpo": [],
    "cto": [],
}


def _load_gaps_state() -> dict:
    data = _load_json(GAPS_STATE_PATH, {})
    return data if isinstance(data, dict) else {}


def _gap_key(gap: dict) -> str:
    """first_seen 안정 키 — role|rule|ref (스캔마다 흔들리지 않게 각 규칙에서 ref 를 안정값으로 유지)."""
    return f"{gap.get('role', '')}|{gap.get('_rule', '')}|{gap.get('ref', '')}"


def _apply_first_seen(all_gaps: list[dict], today_str: str) -> None:
    """status/worklog_gaps_state.json 로 첫 발견일을 유지·갱신하며 각 gap 에 first_seen 을 붙인다.
    이미 있던 키는 날짜 유지, 처음 보는 키만 오늘 날짜로 신규 기록, 사라진 키는 상태에서 제거."""
    old_state = _load_gaps_state()
    new_state: dict[str, str] = {}
    for gap in all_gaps:
        key = _gap_key(gap)
        first_seen = old_state.get(key) or today_str
        new_state[key] = first_seen
        gap["first_seen"] = first_seen
    try:
        GAPS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        GAPS_STATE_PATH.write_text(json.dumps(new_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"[WARN] worklog_gaps_state.json 저장 실패(best-effort, first_seen 유지 불가): {exc}")


def scan() -> dict:
    """전 role 규칙 실행 → status/worklog_gaps.json 갱신 + 결과 dict 반환.
    best-effort — 규칙 하나가 예외를 던져도 나머지는 계속 실행, 파일 저장 실패도 삼킨다."""
    all_gaps: list[dict] = []
    rules_run: list[dict] = []
    for role, rules in _RULES.items():
        for rule_fn in rules:
            rule_name = rule_fn.__name__.removeprefix("rule_")
            try:
                gaps = rule_fn()
                for g in gaps:
                    g["_rule"] = rule_name  # first_seen 안정 키 계산용 내부 태그(임시)
                    g.setdefault("age", "누적")  # 규칙이 age 를 못 채웠으면 보수적 폴백
                all_gaps.extend(gaps)
                rules_run.append({"role": role, "rule": rule_name, "ok": True, "error": ""})
            except Exception as exc:
                rules_run.append({"role": role, "rule": rule_name, "ok": False, "error": str(exc)})

    today_str = datetime.now(tz=KST).date().isoformat()
    _apply_first_seen(all_gaps, today_str)
    for g in all_gaps:
        g.pop("_rule", None)  # 내부 태그 제거 — 화면 담당 규격에 없는 필드 노출 방지

    summary = {"신규": 0, "누적": 0}
    for g in all_gaps:
        summary[g.get("age", "누적")] = summary.get(g.get("age", "누적"), 0) + 1

    result = {
        "generated_at": datetime.now(tz=KST).isoformat(timespec="seconds"),
        "gaps": all_gaps,
        "rules_run": rules_run,
        "summary": summary,
    }
    try:
        GAPS_PATH.parent.mkdir(parents=True, exist_ok=True)
        GAPS_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"[WARN] worklog_gaps.json 저장 실패(best-effort): {exc}")
    return result


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="공용 '빠진 것' 감지기 — role별 규칙 스캔")
    p.add_argument("--scan", action="store_true", help="스캔 실행 + status/worklog_gaps.json 갱신")
    args = p.parse_args()
    if not args.scan:
        p.print_help()
        return 0

    result = scan()
    summary = result.get("summary", {})
    print(f"[INFO] 규칙 {len(result['rules_run'])}건 실행 — 빠진 것 {len(result['gaps'])}건 "
          f"(신규 {summary.get('신규', 0)} / 누적 {summary.get('누적', 0)})")
    for r in result["rules_run"]:
        status = "OK" if r["ok"] else f"ERROR({r['error']})"
        print(f"  - [{r['role']}] {r['rule']}: {status}")
    if result["gaps"]:
        print("\n=== 빠진 것 ===")
        for g in result["gaps"]:
            print(f"  [{g['severity']}/{g.get('age', '?')}] {g['title']} (첫발견 {g.get('first_seen', '?')})")
            print(f"    {g['detail']}")
            if g.get("hint"):
                print(f"    힌트: {g['hint']}")
    else:
        print("\n[INFO] 빠진 것 없음.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
