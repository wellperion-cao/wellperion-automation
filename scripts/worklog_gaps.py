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
SHIP_QUEUE_ARCHIVE_PATH = ROOT / "status" / "_queue_archive.json"
WORKLOG_PATH = ROOT / "status" / "worklog.jsonl"
GAPS_PATH = ROOT / "status" / "worklog_gaps.json"
GAPS_STATE_PATH = ROOT / "status" / "worklog_gaps_state.json"
INSTAGRAM_DIR = ROOT / "instagram"
INQUIRY_SNAPSHOT_MEMBER_PATH = ROOT / "status" / "inquiry_snapshot_member.json"
INQUIRY_SNAPSHOT_LESSON_PATH = ROOT / "status" / "inquiry_snapshot_lesson.json"

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
        # 그리드 전용 포맷 제외(2026-07-25) — 프로필 그리드 N칸을 채우려고 한 장을 조각내
        # 각 조각을 별도 IG 게시물로 올리는 형식이라, 애초에 블로그·카페에 낱개로 올릴
        # 콘텐츠가 아니다. '형제채널 미등록'으로 잡으면 영원히 안 없어지는 경고가 된다
        # (실제로 260616_웰페리온_프리미엄공간_3칸 left/center/right 3건이 한 달 넘게 떠 있었다).
        # ★판정은 IG 게시 여부가 아니라 '조각 포맷인가'로 한다 — 폴더/식별자의 구조적 신호만 본다.
        _sig = f"{it.get('folder', '')} {it.get('id', '')}".lower()
        if "grid" in _sig or "그리드" in _sig or re.search(r"_\d+칸", _sig):
            continue

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


# ─────────────────────────────────────────────────────────────────────────
# CMO 규칙 v2 — 2026-07-23 GM 지시("구조 탓 말고 본인 부주의로 정의") 반영.
# 공용 워크트리 레이스가 원인이더라도 "내 산출물이 지금 살아있는지" 확인은 CMO 책임이다.
# 계기 실측: 2026-07-21 「AI하루」 10편(190파일)이 무관 커밋에 삭제됐는데 이틀간 아무도
#   못 알아챘다(status/briefs/시모_커밋스테일트리_제기_20260723.md). 아래 두 규칙이
#   있었으면 당일에 걸렸다.
# ─────────────────────────────────────────────────────────────────────────


def _is_terminated(item: dict) -> bool:
    """정상 종결(폐기·취소)인가 — 유실이 아니므로 소실 판정에서 제외.
    ★판정은 신규 구현 없이 기존 _is_deprecated_folder(폐기 마커 파일 실존) 를 재사용하고,
    큐 자체의 종결 상태(status='폐기' · terminal 필드)만 추가로 본다."""
    if str(item.get("status", "")).strip() == "폐기":
        return True
    if item.get("terminal"):
        return True
    folder = str(item.get("folder", "")).strip()
    if folder:
        fpath = ROOT / folder
        if fpath.is_dir() and _is_deprecated_folder(fpath):
            return True
    return False


def _slide_exists(slide: str, folder_path: Path) -> bool:
    """slides 항목은 실측상 두 형태가 공존한다 — 저장소 상대(예 'instagram/…/post_1.jpg')와
    folder 상대(예 'ig_01.jpg', 골프 EP1~3 실측). 둘 중 하나로 존재하면 있는 것으로 본다
    (이 구분을 안 하면 골프 3건이 통째로 오탐)."""
    s = str(slide).strip()
    if not s:
        return True
    return (ROOT / s).is_file() or (folder_path / s).is_file()


def rule_content_folder_vanished() -> list[dict]:
    """review_queue.json 항목이 가리키는 콘텐츠 폴더·슬라이드가 디스크에 실제로 있는지 대조.
    "만들어서 큐에 올렸는데 원본이 사라진" 상태를 적발한다(2026-07-21 사고 유형).
    정상 폐기(_is_terminated)는 제외. 같은 폴더를 가리키는 채널 형제 항목은 폴더 단위로 묶는다."""
    queue = _load_review_queue()
    today = datetime.now(tz=KST).date()
    vanished: dict[str, list[dict]] = {}
    gaps: list[dict] = []
    for it in queue:
        if _is_terminated(it):
            continue
        folder = str(it.get("folder", "")).strip()
        if not folder:
            continue
        fpath = ROOT / folder
        if not fpath.is_dir():
            vanished.setdefault(folder, []).append(it)
            continue
        missing = [s for s in (it.get("slides") or []) if not _slide_exists(s, fpath)]
        if missing:
            title = it.get("title", it.get("id", "?"))
            target_date = _parse_iso_date(it.get("published_at", "")) or _parse_folder_date(
                Path(folder).name
            )
            gaps.append({
                "role": "cmo",
                "severity": "high",
                "title": f"{_truncate_title(title)} — 슬라이드 {len(missing)}장 소실",
                "detail": f"폴더는 있으나 파일 없음: {', '.join(missing[:3])}"
                          + (" 외" if len(missing) > 3 else ""),
                "hint": "원본 이미지 복구 또는 재생성 필요(발행물 원본 소실)",
                "ref": f"{it.get('id', folder)}::slides",
                "age": _classify_age(target_date, today),
            })
    for folder, items in vanished.items():
        titles = [str(i.get("title", i.get("id", "?"))) for i in items]
        target_date = _parse_folder_date(Path(folder).name)
        for i in items:
            target_date = target_date or _parse_iso_date(i.get("published_at", ""))
        gaps.append({
            "role": "cmo",
            "severity": "high",
            "title": f"{_truncate_title(titles[0])} — 콘텐츠 폴더 소실",
            "detail": f"큐 {len(items)}건이 가리키는 폴더가 디스크에 없음: {folder}",
            "hint": "git 이력에서 복구하거나(삭제 커밋 확인) 원본 재생성 필요",
            "ref": folder,
            "age": _classify_age(target_date, today),
        })
    return gaps


# 큐 id 형태(review_queue id · _queue.json task_id 공통) — 예 'CMO-2026-07-01-SUMMER-CAMP-EP3'.
_QUEUE_ID_RE = re.compile(r"^[A-Z]{2,4}-\d{4}-\d{2}-\d{2}-[A-Z0-9][A-Z0-9\-]*$")
# 산출물을 "만들었다/올렸다"고 주장하는 area(worklog 고정 스키마의 짧은 한국어 분류).
_CLAIM_AREAS = {"검수", "발행", "제작"}


def _load_worklog() -> list[dict]:
    """status/worklog.jsonl 을 읽어 레코드 리스트로. 파일 없음·깨진 줄은 조용히 건너뜀."""
    records: list[dict] = []
    try:
        text = WORKLOG_PATH.read_text(encoding="utf-8")
    except Exception:
        return records
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return records


def rule_claimed_but_missing() -> list[dict]:
    """"만들었다고 기록해놓고 실제로는 없는 것" 적발 — worklog.jsonl 의 산출물 주장을
    지금 실존하는 큐 항목과 대조한다. ref 가 어느 큐(검수큐·배큐·배아카이브)에도 없으면 유실 의심.

    오탐 방지(실측 가능한 것만 본다):
      - result='fail' 기록은 애초에 주장이 아니다 → 제외.
      - ref 가 큐 id 형태가 아니면(자유 텍스트) 판정 보류 → 건너뜀(지어내지 않음).
      - 배큐·배아카이브에 있는 task_id 는 산출물이 아니라 업무 id → 정상.
      - 같은 url 을 가진 큐 항목이 살아있으면 재번호(id 만 바뀜)이므로 유실 아님.
    """
    records = _load_worklog()
    if not records:
        return []
    queue = _load_review_queue()
    review_ids = {str(it.get("id", "")).strip() for it in queue if it.get("id")}
    review_urls = {
        u for it in queue
        if (u := str(it.get("url") or it.get("post_url") or "").strip())
    }
    ship_ids = {str(s.get("task_id", "")).strip() for s in _load_ship_queue() if s.get("task_id")}
    archive = _load_json(SHIP_QUEUE_ARCHIVE_PATH, [])
    if isinstance(archive, list):
        ship_ids |= {str(s.get("task_id", "")).strip() for s in archive if isinstance(s, dict) and s.get("task_id")}
    known_ids = review_ids | ship_ids

    today = datetime.now(tz=KST).date()
    seen_refs: set[str] = set()
    gaps: list[dict] = []
    for rec in records:
        if str(rec.get("role", "")).strip().lower() != "cmo":
            continue
        if str(rec.get("result", "")).strip() == "fail":
            continue
        ref = str(rec.get("ref", "")).strip()
        url = str(rec.get("url", "")).strip()
        area = str(rec.get("area", "")).strip()
        if not (area in _CLAIM_AREAS or url):
            continue  # 산출물 주장이 아닌 일반 기록
        if not _QUEUE_ID_RE.match(ref):
            continue  # 판정 불가(자유 텍스트 ref) — 보류
        if ref in known_ids:
            continue
        if url and url in review_urls:
            continue  # 재번호 — 같은 산출물이 다른 id 로 살아있음
        if ref in seen_refs:
            continue  # 같은 ref 기록이 여러 줄이면 1건으로
        seen_refs.add(ref)
        gaps.append({
            "role": "cmo",
            "severity": "high",
            "title": f"{_truncate_title(str(rec.get('event', ref)))} — 기록엔 있는데 실물 없음",
            "detail": f"worklog 기록 ref={ref}(area={area or '-'})가 검수큐·배큐 어디에도 없음"
                      + (f" · url={url}" if url else ""),
            "hint": "검수큐 등록분 유실 의심 — git 이력 확인 후 재등록 필요",
            "ref": ref,
            "age": _classify_age(_parse_iso_date(str(rec.get("ts", ""))), today),
        })
    return gaps


PUBLISH_AUDIT_STATE_PATH = ROOT / "status" / "publish_audit_state.json"


def rule_publish_overclaim() -> list[dict]:
    """발행완료 과대보고 감사기(publish_status_audit)가 실측한 '주소는 있는데 죽은' 항목 적발.

    감사기는 09:45 IG 도달 수집에 편승해 HTTP 실측을 하고 결과를 상태파일에 남긴다 —
    이 규칙은 그 결과를 읽기만 한다(스캔이 매번 수십 개 URL 을 크롤하면 07:30 카드 발송이
    느려진다). 상태파일이 없으면 gap 0건(아직 안 돌았을 뿐 — 지어내지 않는다).

    ★URL_MISSING 은 위 rule_published_without_url 이 이미 같은 사실을 표면화하므로 여기선
      제외한다(같은 항목이 화면에 두 줄로 뜨는 것 방지). 이 규칙의 고유 가치는 라이브 실측
      결과(URL_DEAD) — 주소가 적혀 있어서 아무 규칙에도 안 걸리는데 실제로는 안 열리는 건."""
    state = _load_json(PUBLISH_AUDIT_STATE_PATH, {})
    if not isinstance(state, dict):
        return []
    today = datetime.now(tz=KST).date()
    measured_date = _parse_iso_date(str(state.get("generated_at", "")))
    gaps: list[dict] = []
    for s in state.get("suspects", []) or []:
        if not isinstance(s, dict) or "URL_DEAD" not in str(s.get("level", "")):
            continue
        item_id = str(s.get("id", "")).strip()
        channel = _short_channel_label(str(s.get("channel", "")))
        gaps.append({
            "role": "cmo",
            "severity": "high",
            "title": f"{channel} · {_truncate_title(item_id or '?')} — 발행완료인데 주소가 안 열림",
            "detail": f"{s.get('detail', '')} · {s.get('url', '')}".strip(" ·"),
            "hint": "실제 게시 여부 확인 후 주소 정정 또는 status 되돌리기(과대보고 재발방지 감사기 적발)",
            "ref": f"{item_id}::{channel}::dead" if item_id else f"{s.get('url', '')}::dead",
            "age": _classify_age(measured_date, today),
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


# ─────────────────────────────────────────────────────────────────────────
# CMO 규칙 v3 — 2026-07-23. "만들기는 하고 잇기를 안 한다"를 구조로 막는다.
# 계기: 같은 실패가 하루에 3번 나왔다 — AI하루 EP10(만들고 검수큐 등록 안 함) ·
#   원본 7편(만들고 커밋 안 함) · 발행주소 회수기(만들고 어떤 실행 경로에도 연결 안 함).
#   앞의 둘은 위 규칙들이 잡지만, 세 번째("코드는 있는데 아무도 안 부른다")는 사각지대였다.
# ─────────────────────────────────────────────────────────────────────────

# 배선(호출자)이 존재할 수 있는 파일 확장자. .bat·.vbs 는 예약작업이 실제로 실행하는 진입점이라
# 반드시 포함해야 한다(실측: ig/start_ig_series_producer.bat 이 ai_daily_series_card.py 를 호출 —
# .py 만 훑으면 멀쩡한 스크립트를 고아로 오탐한다).
_WIRING_EXTS = {".py", ".bat", ".vbs", ".ps1", ".cmd", ".sh"}
# 스캔 제외 — 남의 저장소 사본·산출물 더미(여기서 나온 언급은 이 저장소의 배선이 아니다).
_WIRING_SKIP_PARTS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "profiles", "_archive",
    "worktrees", ".deploy-check", ".deploy-instructor", "qa_screenshots", "tmp",
    "scratchpad", "site-packages",
}
_SCHEDULE_INVENTORY_PATH = ROOT / "status" / "schedule_inventory.json"

_HANGUL_RE = re.compile(r"[가-힣]")
_PY_MENTION_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.py\b")
_PY_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([A-Za-z_][A-Za-z0-9_]*)\s+import|import\s+([A-Za-z_][A-Za-z0-9_]*))"
)

# CMO 소관 판정(다른 role 소관은 대상 밖 — 이건 시모 규칙이다).
# 근거: 파일이 CMO 단일 SSOT(review_queue.json)를 다루거나, 파일명이 CMO 도메인 접두를 가진다.
# 접두만으로는 부족하고 본문 근거만으로도 부족해 둘 중 하나면 소관으로 본다(실측 조정 결과 —
# 'status/'·'가이드/cmo' 같은 흔한 문자열을 근거에 넣으면 CEO 도구 delegation_state_check 까지
# 딸려 들어와 오탐이 된다).
_CMO_SCRIPT_PREFIXES = (
    "cmo_", "ig_", "publish_", "compose_", "naver_", "danggn_", "kakao_channel_", "instagram_",
)
# 이미지·영상 합성 라이브러리를 쓰는 파일 = 사람이 필요할 때 직접 돌리는 제작 도구(고아 아님).
# 실측: compose_* 12개·mosaic_* 2개가 전부 여기 걸린다 — 이 제외가 없으면 규칙이 오탐에 묻힌다.
_MEDIA_TOOL_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(?:PIL|cv2|moviepy|numpy)\b", re.M)
# 주기 실행 의도가 파일 머리에 적혀 있으면 "돌아야 하는데 안 돈다"가 확실 → mid.
_SCHEDULE_INTENT_WORDS = ("매일", "매주", "매월", "정기", "예약", "스윕", "주기")
_HEAD_LINES = 40
# 무인 배선 대상이 아니라고 파일 머리에 '선언'된 스크립트는 제외한다.
# 근거: 이 파일이 이미 쓰는 것과 같은 원리 — 폴더 폐기 판정을 폴더명 블랙리스트가 아니라
#   "폐기 기록 파일 실존"이라는 구조적 신호로 하듯(_is_deprecated_folder), 여기서도
#   파일명 하드코딩 대신 "담당이 남긴 선언이 소스에 실존하는가"로 판정한다.
# 선언 형식(둘 중 하나를 파일 머리 40줄 안에, 사유와 함께 한 줄로):
#   [폐기] …사유…            → 대체된 레거시. 되살리려면 결재 필요.
#   [수동 실행 전용] …사유…   → 사람이 필요할 때 직접 돌리는 도구(조회 리포트·파괴적 정리 등).
# 선언 없이 방치된 것만 고아로 남는다 = 결정을 미룰 수 없게 만드는 게 이 규칙의 목적.
_NOT_UNMANNED_DECL_RE = re.compile(r"\[\s*(?:폐기|DEPRECATED|수동 실행 전용)\s*\]", re.IGNORECASE)


def _wiring_files() -> list[Path]:
    """호출자가 있을 수 있는 파일 목록(저장소 전체 · 사본·산출물 더미 제외) + git 훅."""
    files: list[Path] = []
    try:
        for f in ROOT.rglob("*"):
            if not f.is_file():
                continue
            if any(part in _WIRING_SKIP_PARTS for part in f.parts):
                continue
            if f.suffix.lower() in _WIRING_EXTS:
                files.append(f)
    except Exception:
        pass
    hooks_dir = ROOT / ".git" / "hooks"
    if hooks_dir.is_dir():
        try:
            files += [f for f in hooks_dir.iterdir() if f.is_file() and f.suffix != ".sample"]
        except Exception:
            pass
    return files


def _build_caller_index(stems: set[str]) -> dict[str, set[str]]:
    """스크립트별 '실제 배선으로 볼 수 있는 언급' 색인.

    .py 에서는 ① import 문 ② 한글이 없는 줄의 'X.py' 언급만 배선으로 센다.
    한글이 섞인 줄은 사람이 읽는 설명·힌트다(실측: 이 규칙 파일 자신의 hint 문구
    "scripts/reconcile_published.py 로 재회수"를 배선으로 세면, 정작 잡아야 할 진짜 고아를
    놓친다 — 이 한 줄 때문에 규칙이 죽을 뻔했다).
    """
    refs: dict[str, set[str]] = {s: set() for s in stems}
    for f in _wiring_files():
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        try:
            rel = str(f.relative_to(ROOT))
        except Exception:
            rel = str(f)
        is_py = f.suffix.lower() == ".py"
        self_stem = f.stem if is_py and f.parent == _SCRIPTS_DIR else None
        for line in text.splitlines():
            if is_py:
                m = _PY_IMPORT_RE.match(line)
                if m:
                    name = m.group(1) or m.group(2)
                    if name in refs and name != self_stem:
                        refs[name].add(rel)
                if _HANGUL_RE.search(line):
                    continue
            for name in _PY_MENTION_RE.findall(line):
                if name in refs and name != self_stem:
                    refs[name].add(rel)
    return refs


def _scheduled_script_stems() -> set[str]:
    """예약작업(Windows Task Scheduler) 등록부에 등장하는 스크립트 이름.
    status/schedule_inventory.json(멱등 생성 SSOT)을 읽는다 — 스캔 때마다 schtasks 를
    호출하지 않는다(느리고 권한 의존)."""
    data = _load_json(_SCHEDULE_INVENTORY_PATH, {})
    try:
        blob = json.dumps(data, ensure_ascii=False)
    except Exception:
        return set()
    return set(_PY_MENTION_RE.findall(blob))


def rule_orphan_automation() -> list[dict]:
    """CMO 소관 자동화 스크립트 중 '어디서도 안 불리는' 것 적발(만들고 안 이은 것).

    고아 = 호출자 0(다른 파일 import·subprocess 배선 없음) + .bat/.vbs/git훅 등록 없음 +
           예약작업 등록 없음.
    오탐 제외(실측으로 정한 기준 — 저장소 실제 파일 55개 무호출 목록을 눈으로 검토해 조정):
      · 라이브러리성 모듈(`if __name__ == "__main__"` 없음) — 애초에 단독 실행 대상 아님.
      · 이미지·영상 합성 도구(PIL·cv2·moviepy·numpy 사용) — 사람이 제작할 때 직접 돌린다.
      · argparse 에 required=True 인자가 있는 것 — 매 실행 사람이 값을 넣어야 하므로 무인 배선 불가.
    """
    scripts = sorted(_SCRIPTS_DIR.glob("*.py")) if _SCRIPTS_DIR.is_dir() else []
    if not scripts:
        return []
    stems = {p.stem for p in scripts}
    refs = _build_caller_index(stems)
    scheduled = _scheduled_script_stems()
    today = datetime.now(tz=KST).date()

    gaps: list[dict] = []
    for path in scripts:
        stem = path.stem
        if refs.get(stem) or stem in scheduled:
            continue
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        is_cmo = ("review_queue" in src) or stem.startswith(_CMO_SCRIPT_PREFIXES)
        if not is_cmo:
            continue  # 다른 role 소관은 대상 밖(이건 시모 규칙)
        if 'if __name__ ==' not in src:
            continue  # 라이브러리성 모듈
        if _MEDIA_TOOL_IMPORT_RE.search(src):
            continue  # 제작 도구(사람이 직접 실행)
        if "required=True" in src:
            continue  # 실행 때마다 사람 입력이 필요 — 무인 배선 대상 아님
        head = "\n".join(src.splitlines()[:_HEAD_LINES])
        if _NOT_UNMANNED_DECL_RE.search(head):
            continue  # [폐기]·[수동 실행 전용] 선언 실존 — 무인 배선 대상 아님(결정이 이미 남아있음)
        has_intent = any(w in head for w in _SCHEDULE_INTENT_WORDS)
        try:
            target_date = datetime.fromtimestamp(path.stat().st_mtime, tz=KST).date()
        except Exception:
            target_date = None
        gaps.append({
            "role": "cmo",
            "severity": "mid" if has_intent else "low",
            "title": f"{stem}.py — 만들어놓고 아무 데도 안 붙임",
            "detail": "다른 스크립트·배치파일·git훅·예약작업 어디에서도 호출되지 않음"
                      + (" · 파일 머리에 주기 실행 의도 명시" if has_intent
                         else " · 주기 실행 의도 불명(수동 도구일 수 있음)"),
            "hint": "기존 예약작업에 best-effort 편승(신규 예약작업 금지) 또는 폐기 결정 필요",
            "ref": f"scripts/{stem}.py",
            "age": _classify_age(target_date, today),
        })
    return gaps


# ─────────────────────────────────────────────────────────────────────────
# COO 규칙 v1 — 2026-07-23 시우, 배9959(GM 지시 "타 C-Level 확장" → 웰리 배정).
# CMO(시모)가 먼저 적용·검증한 틀을 운영 도메인에 확장. 신규 로직 최소화 원칙에 따라
# 가능한 곳은 기존 감사기(check_incomplete_detector)·기존 레지스트리(coo_registry)의
# 판정 조건을 그대로 재사용한다(중복 로직 새로 안 만든다).
#
# ★네트워크 호출 주의: 아래 4개 규칙 中 3개(결재·마감·VOC)는 CMO 규칙(전부 로컬 파일)과 달리
#   TODO_API·VOC_EXEC_URL(GAS)을 스캔 시점에 직접 조회한다. worklog_gaps.py --scan 이 아직
#   예약작업에 배선되지 않아(2026-07-23 기준 미확인) 지금은 문제 없으나, 나중에 이 스캔이
#   빈번한 자동화(예: 07:30 다이제스트)에 얹히면 네트워크 지연·실패가 그 자동화에 영향을 줄 수
#   있다 — 배선 전 웰리 판단 필요(보고에 명시).
# ─────────────────────────────────────────────────────────────────────────

CHECK_INCOMPLETE_LEDGER_PATH = ROOT / "status" / "check_incomplete_ledger.json"

_TODO_ROWS_CACHE: list | None = None


def _todo_rows() -> list[dict]:
    """업무·결재 SSOT(TODO_API todo_list) 행 — 한 스캔 안에서 1회만 조회하고 재사용한다.

    ★2026-07-25 시우: 아래 COO 규칙 3종이 각자 같은 todo_list 를 따로 불러 스캔 1회에
    동일 GAS 호출이 3번 나가고 있었다(규칙을 늘릴수록 선형 증가). 판정 로직 복제 금지와
    같은 원리로 조회도 한 지점으로 모은다(약속 L01·L21). 캐시는 프로세스 수명 한정 —
    scan() 은 1회성 실행이라 신선도 문제가 없다."""
    global _TODO_ROWS_CACHE
    if _TODO_ROWS_CACHE is None:
        import coo_registry  # noqa: PLC0415

        data = coo_registry._http_get_json(f"{coo_registry.TODO_API}?action=todo_list")
        rows = data.get("data", []) if isinstance(data, dict) else []
        _TODO_ROWS_CACHE = rows if isinstance(rows, list) else []
    return _TODO_ROWS_CACHE


def rule_recurring_check_incomplete() -> list[dict]:
    """지원부 일일점검 반복 미완료 적발 — 신규 판정 로직 없음, scripts/check_incomplete_detector.py
    (GM 2026-07-15 기존 감사기 · 23시 마감 원장 기반)의 detect_recurring() 그대로 재사용.
    콜드스타트(원장 7일 미만)·반복 0건이면 그 모듈이 이미 []를 반환(가짜 제안 금지는 원 모듈 보장).
    age는 판정 대상이 '오늘도 이어지는 패턴'이라 특정 발생일을 못 짚어 보수적으로 '누적' 고정."""
    import check_incomplete_detector as cid  # noqa: PLC0415 — scripts/ 이미 sys.path(위에서 삽입)

    today = datetime.now(tz=KST).date().isoformat()
    ledger = cid.load_ledger(CHECK_INCOMPLETE_LEDGER_PATH)
    recurring = cid.detect_recurring(ledger, today)
    gaps: list[dict] = []
    for r in recurring:
        gaps.append({
            "role": "coo",
            "severity": "high" if r["days"] >= 6 else "mid",
            "title": f"'{r['item']}' — 최근 7일 中 {r['days']}일 미완료({r['shift_label']})",
            "detail": "지원부 마감(23시) 반복 미체크 — check_incomplete_ledger.json 기반 자동 감지",
            "hint": "일정(조·시각) 조율 검토 또는 담당 배정 재확인",
            "ref": f"{r['item']}::{r['shift']}::recurring",
            "age": "누적",
        })
    return gaps


def rule_approval_stale_pending() -> list[dict]:
    """업무·결재 SSOT(TODO_API) 결재대기 항목 중 마지막 갱신(수정일)이 오래된 것 적발.
    ★결재 '요청 시점' 자체를 담는 필드가 시트에 없어(지어내기 금지) 수정일을 대리 신호로 쓴다
    — rule_stale_ship_note와 동일 원리("기록이 일을 못 따라옴"). 판정 조건은
    coo_registry.fetch_workapproval_status()의 pending 필터(결재상태 있고 결재완료 아니고
    반려 아님)와 동일 — 그 함수는 집계값만 반환해 항목 단위가 필요한 여기선 같은 조건을
    그대로 재적용한다(신규 판정 로직 아님)."""
    rows = _todo_rows()
    today = datetime.now(tz=KST).date()
    gaps: list[dict] = []
    for r in rows:
        appr = str(r.get("결재상태") or "")
        if not (r.get("결재상태") or r.get("결재요청")):
            continue
        if appr == "결재완료" or "반려" in appr:
            continue
        target_date = _parse_iso_date(str(r.get("수정일", "")))
        if target_date is None:
            continue  # 판정 불가(수정일 없음) — 지어내지 않고 건너뜀
        days = (today - target_date).days
        if days < _STALE_DAYS:
            continue
        title = r.get("업무명", r.get("id", "?"))
        gaps.append({
            "role": "coo",
            "severity": "mid",
            "title": f"{_truncate_title(str(title))} — 결재 대기 {days}일째",
            "detail": f"결재요청={r.get('결재요청', '?')} · 결재상태={appr or '대기'}"
                      f" · 최근 수정일={target_date.isoformat()}(그 뒤 갱신 없음)",
            "hint": "업무&결재 현황 SSOT에서 결재요청 대상자 확인 후 후속 조치 필요",
            "ref": f"{r.get('id', title)}::approval",
            "age": _classify_age(target_date, today),
        })
    return gaps


def rule_task_deadline_passed_active() -> list[dict]:
    """업무·결재 SSOT(TODO_API) 활성 업무(완료·보류 아님) 중 종료일이 이미 지난 것 적발.
    판정 조건은 coo_registry.fetch_workapproval_status()의 overdue 필터(활성 + 종료일<오늘)와
    동일 — 그 함수는 건수만 반환해 항목 단위가 필요한 여기선 같은 조건을 그대로 재적용한다.
    ★"전사 일정(법정점검) 기한 경과" 후보와는 다른 대상(전사 일정 페이지는 아직 검사일 데이터
    자체가 없어 그 규칙은 만들 수 없었다 — 대신 실데이터가 있는 일반 업무 마감초과로 적는다)."""
    import coo_registry  # noqa: PLC0415

    rows = _todo_rows()
    today_str = coo_registry._kst_today()
    today = datetime.now(tz=KST).date()
    gaps: list[dict] = []
    for r in rows:
        if r.get("상태") in ("완료", "보류"):
            continue
        end = str(r.get("종료일") or "")
        if not end or end[:10] >= today_str:
            continue
        target_date = _parse_iso_date(end)
        title = r.get("업무명", r.get("id", "?"))
        days = (today - target_date).days if target_date else None
        gaps.append({
            "role": "coo",
            "severity": "mid",
            "title": f"{_truncate_title(str(title))} — 마감 {days if days is not None else '?'}일 경과",
            "detail": f"종료일={end[:10]} · 상태={r.get('상태', '?')}(완료·보류 아님)",
            "hint": "종료일 갱신 또는 완료·보류 처리 필요",
            "ref": f"{r.get('id', title)}::overdue",
            "age": _classify_age(target_date, today),
        })
    return gaps


# 보류 방치 판정 임계 — 2026-07-25 시우, 실측 분포 근거로 확정(추정값 아님).
# 실측: 업무 SSOT 115행 中 보류 4건, 그중 마감 경과 3건(마감초과 56·41·37일 / 무갱신 45·28·19일).
# 마감 30일 + 무갱신 14일 = 3건 전부 표면화. 대상 모수가 4건뿐이라 "경고가 벽이 된다"는
# 위험이 구조적으로 없고(배10065 note 의 경계 사항), 누가 한 번이라도 손대면 무갱신이
# 리셋돼 스스로 목록에서 빠진다 — 방치된 것만 남는 자기정리형 임계.
_HOLD_OVERDUE_DAYS = 30
_HOLD_STALE_DAYS = 14

def rule_hold_abandoned() -> list[dict]:
    """보류인데 마감이 지나고 오래 방치된 업무 적발 — "멈춰둔 것"과 "잊힌 것"을 가른다.

    ★왜 필요한가(2026-07-25 시우 실측): rule_task_deadline_passed_active 는 상태가
    '완료·보류'면 건너뛴다. 그래서 보류로 돌려둔 순간 그 업무는 어느 화면에도 안 뜬다 —
    배10065 가 근거로 든 바로 그 사례('목욕탕 허가건', 마감 56일 초과·45일 무갱신)가
    지금까지 아무 규칙에도 안 걸린 이유다. 보류는 정당한 상태지만, 재개 조건 없이
    마감까지 지나면 그건 보류가 아니라 표류다.

    ★재개조건 필드가 아직 없어(배9836 GM 결재 대기) 대리 신호로 '마감 경과 + 무갱신'을
    쓴다 — 그 배가 재개조건 입력 게이트를 붙이면 이 규칙의 판정 근거를 그 필드로 바꾼다
    (지금은 없는 필드를 있다고 가정하지 않는다).
    """
    rows = _todo_rows()
    today = datetime.now(tz=KST).date()
    gaps: list[dict] = []
    for r in rows:
        if str(r.get("상태") or "") != "보류":
            continue
        end_date = _parse_iso_date(str(r.get("종료일") or "")[:10])
        if end_date is None:
            continue  # 마감이 없는 보류는 판정 불가 — 지어내지 않고 건너뜀
        overdue = (today - end_date).days
        if overdue < _HOLD_OVERDUE_DAYS:
            continue
        mod_date = _parse_iso_date(str(r.get("수정일") or "")[:10])
        if mod_date is None:
            continue
        stale = (today - mod_date).days
        if stale < _HOLD_STALE_DAYS:
            continue  # 최근에 누가 손댔음 — 잊힌 게 아니다
        title = r.get("업무명", r.get("id", "?"))
        gaps.append({
            "role": "coo",
            "severity": "mid",
            "title": f"{_truncate_title(str(title))} — 보류인 채 마감 {overdue}일 경과",
            "detail": f"상태=보류 · 종료일={end_date.isoformat()} · 최근 수정일={mod_date.isoformat()}"
                      f"(그 뒤 {stale}일간 갱신 없음) — 재개 조건 없이 멈춰 있음",
            "hint": "재개 조건·중단 사유를 적거나, 되살릴 게 아니면 종결 처리 필요",
            "ref": f"{r.get('id', title)}::hold-abandoned",
            "age": _classify_age(mod_date, today),
        })
    return gaps


_VOC_EXCLUDE_CATEGORY = "분실물 접수"  # 분실물=주인이 찾아갈 때까지 대기가 정상이라 미처리와 다름
_VOC_DONE_STATUSES = {"완료", "처리완료", "해결"}


def rule_voc_stale_unresolved() -> list[dict]:
    """VOC·종합접수처(VOC_EXEC_URL reg_list) 중 분실물 제외 항목이 접수 후 오래 미처리인 것 적발.
    ★분실물 접수 제외 근거(실측 2026-07-23): 미해결 26건 中 14건이 분실물 — 그대로 넣으면
    "주인 대기 중"인 정상 상태가 진짜 이슈(컴플레인·청결·시설물고장 등)를 묻어버린다.
    ★PII 미노출(공개 화면 규격): title·detail에 접수자 이름·연락처·본문(content)을 절대 넣지
    않는다 — regId·category·dept·경과일만 사용."""
    from collectors.ops_shared import VOC_EXEC_URL, gas_get  # noqa: PLC0415

    resp = gas_get(VOC_EXEC_URL, {"action": "reg_list"}, label="VOC")
    if resp is None:
        return []
    data = resp.json()
    rows = data.get("data", []) if isinstance(data, dict) else []
    today = datetime.now(tz=KST).date()
    gaps: list[dict] = []
    for r in rows:
        category = str(r.get("category", "")).strip()
        if category == _VOC_EXCLUDE_CATEGORY:
            continue
        status = str(r.get("status", "")).strip()
        if status in _VOC_DONE_STATUSES:
            continue
        created = str(r.get("createdAt", ""))[:10]
        target_date = _parse_iso_date(created)
        if target_date is None:
            continue
        days = (today - target_date).days
        if days < _STALE_DAYS:
            continue
        urgency = str(r.get("urgency") or r.get("severity") or "")
        severity = "high" if urgency in ("긴급", "높음") else "mid"
        reg_id = r.get("regId", "?")
        gaps.append({
            "role": "coo",
            "severity": severity,
            "title": f"{category} — 접수 {days}일째 미처리 (regId={reg_id})",
            "detail": f"dept={r.get('dept', '?')} · status={status or '접수'} · 접수일={created}",
            "hint": "종합접수처에서 처리 상태 갱신 필요",
            "ref": f"{reg_id}::voc",
            "age": _classify_age(target_date, today),
        })
    return gaps


# ─────────────────────────────────────────────────────────────────────────
# CPO 규칙 v1 — 2026-07-23 시포, 배9960(GM 지시 "타 C-Level 확장" → 웰리 배정).
# CMO(시모)가 먼저 적용·검증한 틀을 회원 도메인에 확장. 신규 판정 로직 최소화 원칙에 따라
# 가능한 곳은 기존 감사기(cpo_report.py 의 unassigned_lesson_candidates·_SUCCESS_STATUSES)
# 그대로 재사용한다(중복 로직 새로 안 만든다).
#
# ★전부 로컬 스냅샷 파일만 읽는다 — status/inquiry_snapshot_member.json ·
#   status/inquiry_snapshot_lesson.json (cpo_inquiry_snapshot.py 가 주기 갱신하는 캐시).
#   COO 규칙 3종과 달리 네트워크(GAS) 직접 조회 없음.
#
# ★검토했지만 만들지 않은 후보(오탐 위험·데이터 부재 — 시우 4종 중 2개 포기 사례와 동일 원칙):
#   - "만료 임박인데 갱신 컨택 기록 없음"(member_expiry_summary.json) — 그 파일은 월 1회
#     (4주차 월요일) 생성 시점의 스냅샷이라 애초에 "미컨택 다수"가 정상 초기값이고, 이후
#     실제 컨택 진행을 반영하지 않는다(재생성 전까진 숫자가 고정) — 지금 만들면 항상 울린다.
#   - "상담 예약일 지났는데 결과 미기록" — visited/visitDate 필드를 실측(638행 전수)했더니
#     항상 false/공백이었다(운영에서 이 필드 자체를 안 씀) — 이 필드로 판정하면 전건이 걸려
#     정상상태 오탐이 된다.
#   - "휴회 종료일 지났는데 복귀 처리 없음" — 로컬 스냅샷 자체가 없음(휴회접수.html 은
#     폼 접수 전용, 상태 원장 캐시가 없다).
#   - "등록됐는데 회원 원장 누락"(문의↔등록 짝 불일치) — 로컬엔 회원 원장 전체 스냅샷이 없고
#     월 1회 집계(member_expiry_summary.json)뿐이라 대조 불가. GAS(member_active_list)
#     직접 조회가 필요해 이번(로컬 우선) 범위에서는 만들지 않음.
# ─────────────────────────────────────────────────────────────────────────


def _load_member_inquiry_rows() -> list[dict]:
    """status/inquiry_snapshot_member.json 캐시에서 문의 행 리스트만 평탄화."""
    data = _load_json(INQUIRY_SNAPSHOT_MEMBER_PATH, {})
    rows = data.get("rows", []) if isinstance(data, dict) else []
    return rows if isinstance(rows, list) else []


_LESSON_LABEL = {"adult": "성인강습", "youth": "유소년강습"}


def _load_lesson_inquiry_rows() -> dict[str, list[dict]]:
    """status/inquiry_snapshot_lesson.json 캐시 — {'adult': rows, 'youth': rows}로 평탄화
    (원본 구조가 {adult:{year:{rows:[...]}}, youth:{...}} 라 한 단계 파고들어야 함)."""
    data = _load_json(INQUIRY_SNAPSHOT_LESSON_PATH, {})
    out: dict[str, list[dict]] = {}
    for key in ("adult", "youth"):
        sec = data.get(key, {}) if isinstance(data, dict) else {}
        year = sec.get("year", {}) if isinstance(sec, dict) else {}
        rows = year.get("rows", []) if isinstance(year, dict) else []
        out[key] = rows if isinstance(rows, list) else []
    return out


# LOSS 사유 모달 실제 배선일(멤버십·강습 공용, GM 요청 사양 2026-07-18·시토 대행). 이 날짜
# 이전 LOSS 는 애초에 사유를 기록할 UI 자체가 없었다 — "미기록"이 아니라 "그 시점엔 기록할
# 수단이 없었다"이므로 판정 대상에서 제외한다(실측: 제외 전엔 멤버십 4건·강습 168건이 전부
# 걸려 배선일 이전 구버전 데이터로 오탐 — 제외 후 0건, 기능이 정상 작동 중임을 확인).
_LOSS_REASON_FEATURE_DATE = "2026-07-18"


def rule_inquiry_loss_no_reason() -> list[dict]:
    """문의 단계 LOSS(등록 무산)인데 사유 미기록 적발 — 멤버십·강습(성인·유소년) 공용.
    ★기존 회원 종료(scope=ended)의 '종료사유 미기록'과는 별개 체계(문의 단계 전용, 등록
    자체가 무산된 건) — 그 쪽은 이미 '오늘 할 일' 액션 패널이 상시 표시 중이므로 중복 아님.
    LOSS 사유 모달 배선일(2026-07-18) 이후 발생분만 대상으로 한다."""
    today = datetime.now(tz=KST).date()
    gaps: list[dict] = []

    def _scan(rows: list[dict], source_label: str, ref_prefix: str) -> None:
        for r in rows:
            if str(r.get("status", "")).strip() != "LOSS":
                continue
            ts = str(r.get("timestamp", ""))[:10]
            if not ts or ts < _LOSS_REASON_FEATURE_DATE:
                continue  # 배선일 이전 — 기록 수단 자체가 없었음(오탐 방지)
            if str(r.get("lossReason") or "").strip():
                continue
            target_date = _parse_iso_date(ts)
            gaps.append({
                "role": "cpo",
                "severity": "low",
                "title": f"{source_label} · LOSS(미등록) 처리인데 사유 미기록",
                "detail": f"진행상태=LOSS · 접수일={ts} · '미등록 사유' 칸 공란",
                "hint": "문의 현황 표에서 진행상황 LOSS 재클릭 → 사유 입력",
                "ref": f"{ref_prefix}::{r.get('rowIndex', ts)}::lossreason",
                "age": _classify_age(target_date, today),
            })

    _scan(_load_member_inquiry_rows(), "멤버십 문의", "member")
    for key, rows in _load_lesson_inquiry_rows().items():
        _scan(rows, f"강습({_LESSON_LABEL[key]}) 문의", f"lesson-{key}")
    return gaps


def rule_lesson_owner_unassigned() -> list[dict]:
    """강습 문의 담당자 미배정(흔적 0건) 적발 — 신규 판정 로직 없음,
    cpo_report.unassigned_lesson_candidates() 그대로 재사용(2026-07-23 시포 실측 근거:
    상태·담당자·메모·연락이력이 전부 공란인 건은 상태 미입력이 아니라 '담당자 미배정'이
    원인 — 배정이 안 되면 아무도 안 잡고 고객이 유실된다). 로컬 스냅샷만 읽는다
    (cpo_report.fetch_lesson_inquiries 의 GAS 직접호출 대신 캐시 파일 사용 — 신규 네트워크 호출 없음)."""
    from cpo_report import unassigned_lesson_candidates  # noqa: PLC0415

    today = datetime.now(tz=KST).date()
    gaps: list[dict] = []
    for key, rows in _load_lesson_inquiry_rows().items():
        for r in unassigned_lesson_candidates(rows):
            ts = str(r.get("timestamp", ""))[:10]
            target_date = _parse_iso_date(ts)
            sport = str(r.get("sport") or r.get("bucket") or "종목미상").strip()
            gaps.append({
                "role": "cpo",
                "severity": "mid",
                "title": f"강습({_LESSON_LABEL[key]}) 문의 — 담당자 미배정(흔적 0건)",
                "detail": f"종목={sport or '종목미상'} · 접수일={ts or '?'} · 상태·담당자·메모·연락이력 전부 공란",
                "hint": "담당 강사 배정 필요(배정 안 되면 고객이 연락을 못 받는다)",
                "ref": f"lesson-{key}::{r.get('rowIndex', ts)}::unassigned",
                "age": _classify_age(target_date, today),
            })
    return gaps


def _has_registration_trace(row: dict) -> bool:
    """등록 흔적 판정 — memo 또는 연락이력(contacts) 어디든 '등록' 문자열이 있으면 기록된
    것으로 본다(실측 함정: 등록완료 메모가 memo 칸이 아니라 연락이력 마지막 줄에 적히는
    사례가 실존해 memo 만 보면 오탐이 난다). 넓게 잡아 과소적발(false negative)만 허용한다
    — "회원권 등록부터 도와드려야" 같은 진행중 멘션까지 걸러 안전 쪽으로 치우친다."""
    if "등록" in str(row.get("memo") or ""):
        return True
    for c in (row.get("contacts") or []):
        if "등록" in str(c.get("note") or ""):
            return True
    return False


def rule_registration_no_trace() -> list[dict]:
    """등록완료(cpo_report._SUCCESS_STATUSES) 처리인데 등록 기록(메모·연락이력) 흔적이
    전혀 없는 건 적발 — 멤버십·강습(성인·유소년) 공용. age(신규/누적) 자동 분류로 오래된
    건(실측상 대부분 1~3월 과거 건)은 접힌 누적 줄로만, 최근 14일 내 건만 눈에 띄게 표시."""
    from cpo_report import _SUCCESS_STATUSES  # noqa: PLC0415

    today = datetime.now(tz=KST).date()
    gaps: list[dict] = []

    def _scan(rows: list[dict], source_label: str, ref_prefix: str) -> None:
        for r in rows:
            if str(r.get("status", "")).strip() not in _SUCCESS_STATUSES:
                continue
            if _has_registration_trace(r):
                continue
            ts = str(r.get("timestamp", ""))[:10]
            target_date = _parse_iso_date(ts)
            gaps.append({
                "role": "cpo",
                "severity": "low",
                "title": f"{source_label} · 등록완료 처리인데 기록 흔적 없음",
                "detail": f"진행상태={r.get('status')} · 접수일={ts or '?'} · 메모·연락이력 모두 등록 흔적 없음",
                "hint": "실제 등록 여부 확인 후 메모 보강(오기재 가능성도 확인)",
                "ref": f"{ref_prefix}::{r.get('rowIndex', ts)}::regtrace",
                "age": _classify_age(target_date, today),
            })

    _scan(_load_member_inquiry_rows(), "멤버십 문의", "member")
    for key, rows in _load_lesson_inquiry_rows().items():
        _scan(rows, f"강습({_LESSON_LABEL[key]}) 문의", f"lesson-{key}")
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
        rule_claimed_but_missing,      # 2026-07-23 신설 — 만들었다고 하고 실물 없는 것
        rule_content_folder_vanished,  # 2026-07-23 신설 — 콘텐츠 폴더·슬라이드 소실
        rule_orphan_automation,        # 2026-07-23 신설 — 만들고 아무 실행 경로에도 안 이은 것
        rule_publish_overclaim,        # 2026-07-23 신설 — 감사기 실측 '주소 죽음'(과대보고 재발방지)
    ],
    "coo": [
        rule_recurring_check_incomplete,   # 2026-07-23 신설 — 지원부 반복 미완료(기존 감사기 재사용)
        rule_approval_stale_pending,       # 2026-07-23 신설 — 결재 대기 N일 초과
        rule_task_deadline_passed_active,  # 2026-07-23 신설 — 업무 마감(종료일) 경과인데 방치
        rule_hold_abandoned,               # 2026-07-25 신설 — 보류인 채 마감 지나고 방치(위 규칙 사각지대)
        rule_voc_stale_unresolved,         # 2026-07-23 신설 — VOC 접수 후 N일 미처리(분실물 제외)
    ],
    "cpo": [
        rule_inquiry_loss_no_reason,     # 2026-07-23 신설 — 문의 LOSS(미등록)인데 사유 미기록
        rule_lesson_owner_unassigned,    # 2026-07-23 신설 — 강습 문의 담당자 미배정(흔적 0건)
        rule_registration_no_trace,      # 2026-07-23 신설 — 등록완료 처리인데 기록 흔적 없음
    ],
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
    _publish_best_effort()
    return result


def _publish_best_effort() -> None:
    """스캔 산출물을 그 자리에서 깃에 올린다(약속 L13 · INC-006 동류).

    ★필요한 이유(2026-07-25 시우 실측): 패널(worklog_panel.js)은 로컬 파일이 아니라
    raw.githubusercontent master 를 읽는다. 07:30 스캔이 파일만 갱신하고 아무도 커밋하지
    않아, 화면에는 2026-07-23 20:41 데이터가 이틀째 떠 있었다(coo 25건 · 실제로는 39건).
    "고쳤다"가 화면에 도달하지 않는 전형적 형태 — 쓰는 자리 = 올리는 자리로 붙인다.

    ★장치를 늘리지 않는다(약속 L21): 새 워처·새 예약작업 없이 기존 관문
    scripts/safe_commit.py 를 그대로 호출한다(락 직렬화·지정 경로만·push 연계 전부 그쪽 보장).
    best-effort — 깃 실패가 스캔·상위 자동화(07:30 카드 발송)를 절대 깨뜨리지 않는다.
    """
    try:
        from safe_commit import safe_commit  # noqa: PLC0415 — scripts/ 는 위에서 sys.path 삽입
    except Exception as exc:
        print(f"[WARN] 산출물 게시 건너뜀(safe_commit 임포트 실패): {exc}")
        return
    try:
        res = safe_commit(
            [GAPS_PATH, GAPS_STATE_PATH],
            "chore: 빠진 것 스캔 결과 갱신 (worklog_gaps)",
            holder="worklog_gaps_scan",
        )
        if res.get("committed"):
            print(f"[INFO] 스캔 결과 게시 완료 — {res.get('sha', '')[:7]}")
        else:
            print(f"[INFO] 스캔 결과 게시 생략 — {res.get('reason', '')}")
    except Exception as exc:
        print(f"[WARN] 스캔 결과 게시 실패(best-effort, 스캔 자체는 정상): {exc}")


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
