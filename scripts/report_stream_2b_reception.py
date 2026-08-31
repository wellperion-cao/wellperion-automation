# -*- coding: utf-8 -*-
"""[스트림 #2b] 종합접수 현황 + 미처리 적체 리마인드 — 프로덕션 (CTO 2026-07-22).

GM 2026-07-22 지시: 배9424(2026-07-21)의 '종합접수 현황 → 점검현황방 병합'을 되돌림.
종합접수(VOC 6종: 분실물·시설물고장·청결·칭찬·쓴소리·컴플레인)는 점검(시설·지원·주차)과
분리해 별도 종합접수방으로 단독 발송한다. 점검 현황은 scripts/report_stream_2_check.py 참조.

통일 포맷 [하루 일과 정리]:
  ① 오늘 신규 접수 요약
  ━━━━━━━━━━
  ② 미처리 적체 리마인드 — 카테고리별 SLA(apps_script_voc.js REG_CATEGORIES가 SSOT)를
     넘긴 미처리 건을 담당자별로 묶어 매일 밤 상기(GM 신설 지시). 방치된 접수건이
     하루하루 다이제스트에 묻히지 않도록 '오늘 신규'와 별개로 매번 재노출한다 — 의도적
     크로스데이 억제 없음(리마인드 목적상 반복 노출이 맞다). 칭찬(slaHours=null)은
     SLA 개념이 없어 적체 집계에서 제외.

  ※ 2026-07-27 웰리 정정: 커밋 c33a79ac7에서 이 블록을 GAS reg_sla_check(전환 즉시
     통지)로의 이관을 이유로 제거했으나, 전환 알림이 **라이브 배포되어 실제 발신이
     확인된 뒤에만** 이 블록을 제거한다 — 대체가 살아있기 전에 원본을 지워 공백이
     생겼다(그날 밤부터 SLA 초과를 알려주는 경로가 전무). 복구.

텔레그램: 종합접수방(TELEGRAM_RECEPTION_CHAT_ID, -5065206276) 단일 발송.
발사 시각: 매일 22:30 (daily_scheduler.py run_daily_digest 경유) / 독립 실행 가능.
카카오톡: 이 모듈 자체는 텔레그램만 다룬다(build_digest만 노출). ★운영+시설+지원+주차 방
발송은 daily_scheduler.py run_daily_digest()가 이 모듈의 build_digest() 결과를 그대로
재사용해 처리한다(점검현황과 별도 메시지로 분리 — GM 2026-07-22 go, KAKAO_GO_STREAM2 게이트).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from collectors.ops_shared import RECEPTION_EXEC_URL, gas_get, reception_elapsed_days  # noqa: E402
from publish_digest import _load_env_val  # noqa: E402
from tg_outbound_log import send as tg_send  # noqa: E402

TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_RECEPTION_CHAT_ID") or -5065206276)  # 종합접수방
DASHBOARD_URL = "https://wellperion-cao.github.io/wellperion-automation/coo/reception/종합접수처_현황.html"
_WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]
_DIVIDER = "━" * 10

# ── 「급할 때만」 강등 스위치 (배 11070 잔여 · 발신 체계 확정안 텔레그램 11곳 중 하나) ──
# status/telegram_urgent_only.json 하나를 3개 스트림(문의·점검·접수)이 같이 쓴다(약속 L21).
# ★이 스트림은 카카오 이사 배선(kakao_go) 자체가 아직 없다 — urgent_only 를 켜도 대체
# 채널이 없어지므로, JSON 의 reception.urgent_only 는 그 배선이 생기기 전까지 false 로 둔다.
_URGENT_ONLY_FLAG = REPO_ROOT / "status" / "telegram_urgent_only.json"
_URGENT_MARKERS = ("❗", "🔴", "기한 초과", "지연")


def _urgent_only_enabled(stream_key: str) -> bool:
    try:
        import json
        cfg = json.loads(_URGENT_ONLY_FLAG.read_text(encoding="utf-8"))
        return bool((cfg.get(stream_key) or {}).get("urgent_only", False))
    except Exception:
        return False  # 못 읽으면 안전측(종전처럼 매번 발송)


def _looks_urgent(text: str) -> bool:
    """이상 신호 마커가 있는가 — 기준이탈(❗🔴)·기한 초과·지연."""
    return any(m in text for m in _URGENT_MARKERS)

# 카테고리(reg_list의 category=한글 라벨) → SLA 시간. SSOT=coo/reception/apps_script_reception.js
# REG_CATEGORIES(:38-43). 보드·다른 소비자에 하드코딩 복사 금지 원칙과 동일하게 이 표는
# GAS 응답 라벨 그대로를 키로 쓴다(코드 재구현 없이 라벨 정확일치). None=SLA 없음(집계 제외).
_SLA_HOURS: dict[str, int | None] = {
    "분실물 접수": 720,  # 30일 — GM 확정 2026-07-28(구 168h/7일). 사유=apps_script_reception.js 주석
    "시설물 고장 접수": 24,
    "청결 이슈 접수": 12,
    "직원·강사 칭찬합니다": None,
    "직원·강사 쓴소리합니다": 72,
    "컴플레인 접수": 48,
}


def _fetch_rows() -> list[dict] | None:
    resp = gas_get(RECEPTION_EXEC_URL, {"action": "reg_list"}, timeout=20, label="stream2b-reception")
    if resp is None:
        return None
    try:
        data = resp.json()
        return data.get("data", []) if data.get("ok") else None
    except Exception:
        return None


# 접수 정체 스냅샷(배627 후속 · GM 지시 2026-08-15) — "놓치지 않게 계속 챙겨줘".
#   부팅 화면(hangro_board.py --role coo)이 매일 손으로 세지 않고도 접수 적체를 볼 수 있게,
#   이 발송기가 이미 매 실행 읽는 rows(reg_list)로 status/reception_watch.json 하나만 남긴다.
#   새 스크립트·새 예약을 만들지 않는다(약속 L21). 발송 성공 여부와 무관 — 쓰기가 실패해도
#   발송을 막지 않는다(조용히 넘어가되 stderr에 한 줄 남긴다).
RECEPTION_WATCH_PATH = REPO_ROOT / "status" / "reception_watch.json"


def _ym_add(ym: str, delta: int) -> str:
    y, m = (int(x) for x in ym.split("-"))
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _lost_found_month_cycle() -> dict | None:
    """습득물(lf_list) 월 사이클 수치 — GM 지시 2026-08-15 "습득물 현황도 일정에 맞게끔
    정리해야 하는 것들은 따로 리스트업". lf_list는 reg_list(rows)와 다른 조회라 여기서
    한 번 더 gas_get 부른다 — 실패해도(GAS 무응답·파싱 오류 등) 발송을 막지 않게 통째로
    감싸 None을 돌려준다.

    사이클(정본=coo/reception/lost_found_guide.html): 습득월 M → M+1 공지 → M+2 처분.
    - notice_this_month  = 지난달 습득 · 아직 게시중(이번 달 공지 대상)
    - dispose_this_month = 지지난달 이전 습득 · 아직 게시중(이번 달 처분 대상 — 가장 급함)
    - dispose_next_month = 사이클상 notice_this_month와 동일 모집단(지난달 습득분은 다음 달
      처분월에 도달한다) — 새로 세지 않고 그대로 재사용."""
    try:
        resp = gas_get(RECEPTION_EXEC_URL, {"action": "lf_list"}, timeout=20, label="stream2b-lf")
        if resp is None:
            return None
        data = resp.json()
        if not data.get("ok"):
            return None
        posted = [r for r in data.get("data", []) if str(r.get("status", "")) == "게시중"]
        this_ym = datetime.now().strftime("%Y-%m")
        last_ym = _ym_add(this_ym, -1)

        def _ym_of(r: dict) -> str:
            return str(r.get("foundWhen") or r.get("createdAt") or "")[:7]

        notice = [r for r in posted if _ym_of(r) == last_ym]
        dispose = [r for r in posted if _ym_of(r) and _ym_of(r) < last_ym]
        found_dates = [str(r.get("foundWhen") or r.get("createdAt") or "")[:10] for r in posted]
        found_dates = [d for d in found_dates if d]
        return {
            "notice_this_month": len(notice),
            "dispose_this_month": len(dispose),
            "dispose_next_month": len(notice),
            "oldest_found_date": min(found_dates) if found_dates else "",
        }
    except Exception as e:
        print(f"[stream2b] 습득물 사이클 조회 실패: {e}", file=sys.stderr)
        return None


def _duration_stats(durations: list[int]) -> dict | None:
    if not durations:
        return None
    d = sorted(durations)
    n = len(d)
    mid = n // 2
    return {"count": n, "median_days": d[mid] if n % 2 else (d[mid - 1] + d[mid]) / 2,
            "max_days": d[-1]}


def _first_done_at_and_stats(rows: list[dict], now: datetime) -> tuple[dict[str, str], dict[str, str], dict | None]:
    """처리 소요일 자체 정립(GM 지시 2026-08-28) — reg_list에 완료 시각 칸이 없어
    「접수→완료」 소요일을 못 쟀다. 우리가 매일 이 관문을 도는 김에, regId별 '완료로
    처음 목격한 날'(first_done_at)을 기록해 두면 그 다음부터 소요일이 나온다.
    ▸최초값은 절대 덮어쓰지 않는다(행 삭제·상태 되돌림이 있어도 first_done_at 보존).
    ▸새 파일을 만들지 않는다(약속 L21) — 기존 reception_watch.json에 얹는다.
    ▸과거분은 backfill_first_done_at()이 메모·발신로그·통보스냅샷 3근거로 복원한다.
      근거는 first_done_at_src(regId→memo|log|bucket|unknown|live)에 남기고, 실측(live)이
      이미 있으면 백필이 절대 덮지 않는다. src에 있으면(=unknown 포함) 오늘 날짜를
      새로 찍지 않는다 — 과거 완료건에 오늘을 찍는 것이 원래의 거짓말이었다."""
    prev_done_at: dict[str, str] = {}
    src: dict[str, str] = {}
    try:
        prev = json.loads(RECEPTION_WATCH_PATH.read_text(encoding="utf-8"))
        prev_done_at = dict(prev.get("first_done_at") or {})
        src = dict(prev.get("first_done_at_src") or {})
    except Exception:
        pass
    today_str = now.strftime("%Y-%m-%d")
    for r in rows:
        if str(r.get("status", "")) == "완료":
            reg = str(r.get("regId") or "")
            if reg and reg not in prev_done_at and reg not in src:
                prev_done_at[reg] = today_str
                src[reg] = "live"

    by_src: dict[str, list[int]] = {}
    by_cat: dict[str, list[int]] = {}
    for r in rows:
        reg = str(r.get("regId") or "")
        done_at = prev_done_at.get(reg)
        if not done_at:
            continue
        days = reception_elapsed_days(r, datetime.strptime(done_at, "%Y-%m-%d"))
        by_src.setdefault(src.get(reg, "live"), []).append(days)
        by_cat.setdefault(str(r.get("category") or "").strip() or "미분류", []).append(days)
    memo_only = by_src.get("memo", [])
    memo_log = memo_only + by_src.get("log", [])
    every = [d for v in by_src.values() for d in v]
    stats = {
        "memo": _duration_stats(memo_only),
        "memo_log": _duration_stats(memo_log),
        "all": _duration_stats(every),
        "by_category": {k: _duration_stats(v) for k, v in sorted(by_cat.items())},
    } if every else None
    return prev_done_at, src, stats


# ── 과거 완료일 백필(GM 지적 2026-08-28: "과거분도 살릴 수 있을 것 같은데?") ──────────
# 완료 시각 칸이 없던 시절의 완료건도 근거 3갈래로 완료일을 복원한다. 우선순위=메모>로그>
# 스냅샷 구간. 셋 다 실패하면 unknown — 날짜를 지어내지 않는다.
_MEMO_DATE_RE = re.compile(
    r"(?P<y4>20\d{2})\s*[-./년]\s*(?P<y4m>\d{1,2})\s*[-./월]\s*(?P<y4d>\d{1,2})"      # 2026-08-24
    r"|(?P<y2>2\d)\s*[-./년]\s*(?P<y2m>\d{1,2})\s*[-./월]\s*(?P<y2d>\d{1,2})"          # 26/7/27, 26년 7월 7일
    r"|(?P<c6>2\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))\s*자"                      # 260816자로
    r"|(?P<m>\d{1,2})\s*[/월]\s*(?P<d>\d{1,2})"                                        # 8/26, 7월 21일
)


def _memo_done_date(memo: str, created: str, today: str) -> str | None:
    """처리메모에 적힌 조치 날짜 중 '접수일 이후 & 오늘 이전'인 가장 늦은 날짜.
    메모는 시간순 조치 로그라 마지막 날짜가 완료일에 가장 가깝다. 연도가 없으면 접수일의
    연도를 쓰고, 그 결과가 접수일보다 앞서면 채택하지 않는다(다음 근거로 넘긴다)."""
    best = None
    for mt in _MEMO_DATE_RE.finditer(str(memo or "")):
        g = mt.groupdict()
        if g["y4"]:
            y, mo, dy = int(g["y4"]), int(g["y4m"]), int(g["y4d"])
        elif g["y2"]:
            y, mo, dy = 2000 + int(g["y2"]), int(g["y2m"]), int(g["y2d"])
        elif g["c6"]:
            y, mo, dy = 2000 + int(g["c6"][:2]), int(g["c6"][2:4]), int(g["c6"][4:])
        else:
            y, mo, dy = int(created[:4]), int(g["m"]), int(g["d"])
        if not (1 <= mo <= 12 and 1 <= dy <= 31):
            continue
        try:
            cand = datetime(y, mo, dy).strftime("%Y-%m-%d")
        except ValueError:
            continue
        if created[:10] <= cand <= today and (best is None or cand > best):
            best = cand
    return best


def _log_last_seen() -> dict[str, str]:
    """logs/kakao_sent-YYYY-MM-DD.log 에 그 건이 마지막으로 등장한 날 = 완료 상한."""
    out: dict[str, str] = {}
    for p in sorted((REPO_ROOT / "logs").glob("kakao_sent-*.log")):
        day = p.stem.replace("kakao_sent-", "")
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for reg in set(re.findall(r"RECEPTION-\d+", txt)):
            out[reg] = day  # 날짜 오름차순 순회 → 마지막 등장일이 남는다
    return out


def _done_bucket_dates(today: str) -> dict[str, str]:
    """status/dept_completion_notify.json 의 reception_seen_done_ids(완료 목격 누적)를
    git 커밋 시점별로 꺼내 비교 — 어느 구간에서 처음 나타났는지 = 그 구간에 완료됐다.
    구간 끝 날짜(그 스냅샷의 커밋일)를 완료일로 쓴다. 현재 워킹 파일에만 있으면 오늘."""
    import subprocess
    rel = "status/dept_completion_notify.json"
    try:
        out = subprocess.run(["git", "log", "--format=%H %ad", "--date=short", "--", rel],
                             cwd=REPO_ROOT, capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return {}
    snaps: list[tuple[str, str]] = []          # (날짜, sha) 오래된 것부터
    for line in reversed([ln for ln in out.splitlines() if ln.strip()]):
        sha, _, day = line.partition(" ")
        snaps.append((day.strip(), sha))
    first: dict[str, str] = {}
    for day, sha in snaps:
        try:
            blob = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=REPO_ROOT,
                                  capture_output=True, timeout=30).stdout.decode("utf-8")
            ids = json.loads(blob).get("reception_seen_done_ids") or []
        except Exception:
            continue
        for reg in ids:
            first.setdefault(str(reg), day)
    try:
        cur = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))
        for reg in cur.get("reception_seen_done_ids") or []:
            first.setdefault(str(reg), today)
    except Exception:
        pass
    return first


def _selfcheck_memo_dates() -> None:
    """파서 자가점검 — 라이브 메모에서 실제로 겪은 모양만 고정한다."""
    t = "2026-08-28"
    assert _memo_done_date("8/26일 교체완료", "2026-08-20", t) == "2026-08-26"
    assert _memo_done_date("26/7/27 10:52 벨트 불량 교체 완료", "2026-07-25", t) == "2026-07-27"
    assert _memo_done_date("26년 7월 7일 정리\n26.7.20 경연", "2026-07-05", t) == "2026-07-20"
    assert _memo_done_date("260816자로 벌레 이슈 완료처리", "2026-07-25", t) == "2026-08-16"
    assert _memo_done_date("2026-07-29 용접, 2026-08-10 교체 (2026-08-19 확인)",
                           "2026-07-15", t) == "2026-08-19"
    assert _memo_done_date("7/21 자체방역 실시", "2026-07-30", t) is None   # 접수일보다 앞 → 기각
    assert _memo_done_date("22:30 이후 진행 / 010-8753-7909", "2026-08-01", t) is None
    assert _memo_done_date("약정 만료가 2027-03-31", "2026-08-08", t) is None  # 오늘 이후 → 기각


def backfill_first_done_at(rows: list[dict] | None = None, today: str | None = None) -> dict:
    """과거 완료건의 완료일을 3근거로 복원해 reception_watch.json에 얹는다(1회성).
    ★실측(src=live)이나 이미 박힌 first_done_at 은 절대 덮지 않는다."""
    _selfcheck_memo_dates()
    today = today or datetime.now().strftime("%Y-%m-%d")
    rows = rows if rows is not None else (_fetch_rows() or [])
    log_seen = _log_last_seen()
    bucket = _done_bucket_dates(today)
    try:
        watch = json.loads(RECEPTION_WATCH_PATH.read_text(encoding="utf-8"))
    except Exception:
        watch = {}
    done_at = dict(watch.get("first_done_at") or {})
    src = dict(watch.get("first_done_at_src") or {})

    report: dict = {"rows_done": 0, "by_src": {}, "samples": [], "rejected": []}
    for r in rows:
        if str(r.get("status", "")) != "완료":
            continue
        reg = str(r.get("regId") or "")
        if not reg:
            continue
        report["rows_done"] += 1
        if reg in done_at or src.get(reg) == "live":
            report["by_src"]["live"] = report["by_src"].get("live", 0) + 1
            continue
        created = str(r.get("createdAt") or "")[:10]
        memo_hit = _memo_done_date(r.get("memo"), created, today) if created else None
        cand, kind = None, "unknown"
        for value, name in ((memo_hit, "memo"), (log_seen.get(reg), "log"), (bucket.get(reg), "bucket")):
            if value and created and created <= value <= today:
                cand, kind = value, name
                break
            if value:
                report["rejected"].append((reg, name, value, created))
        if cand:
            done_at[reg] = cand
            if kind == "memo":
                report["samples"].append((reg, created, cand, str(r.get("memo") or "")))
        src[reg] = kind
        report["by_src"][kind] = report["by_src"].get(kind, 0) + 1

    watch["first_done_at"] = done_at
    watch["first_done_at_src"] = src
    RECEPTION_WATCH_PATH.write_text(json.dumps(watch, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    return report


def _write_reception_watch(rows: list[dict]) -> None:
    """미완 건을 부서별로 세어 스냅샷으로 남긴다.
    - 완료 도장이 아니라 memberReply(회원 안내) 빈칸을 진짜 마감 여부로 따로 센다
      (GM 지적 2026-08-15: 접수는 회원 수만큼 있고 건별로 닫는다).
    - 분실물 접수는 보관 성격이라 부서 적체 집계에서 빼고 따로 센다(웰리 실무진 공지 방침)."""
    try:
        now = datetime.now()
        first_done_at, first_done_src, processing_days = _first_done_at_and_stats(rows, now)
        by_dept: dict[str, dict] = {}
        member_reply_open = 0
        overdue_3d = 0
        overdue_7d = 0
        lost_open = 0
        for r in rows:
            if str(r.get("status", "")) == "완료":
                continue
            cat = str(r.get("category") or "").strip()
            days = reception_elapsed_days(r, now)
            if cat == "분실물 접수":
                lost_open += 1
                continue
            dept = str(r.get("dept") or "").strip() or "부서 미정"
            slot = by_dept.setdefault(dept, {"open": 0, "max_age_days": 0, "max_age_reg_id": ""})
            slot["open"] += 1
            if days >= slot["max_age_days"]:
                slot["max_age_days"] = days
                slot["max_age_reg_id"] = str(r.get("regId") or "")
            if not str(r.get("memberReply") or "").strip():
                member_reply_open += 1
            if days >= 3:
                overdue_3d += 1
            if days >= 7:
                overdue_7d += 1
        RECEPTION_WATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
        RECEPTION_WATCH_PATH.write_text(json.dumps({
            "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "by_dept": by_dept,
            "member_reply_open": member_reply_open,
            "overdue_3d": overdue_3d,
            "overdue_7d": overdue_7d,
            "lost_items_open": lost_open,
            "lost_found": _lost_found_month_cycle(),
            "first_done_at": first_done_at,
            "first_done_at_src": first_done_src,
            "processing_days": processing_days,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        # 살아있음 신호 — coo-reception 은 등록부에 enabled 로 올라 있는데 하트비트가 없어
        # 침묵 감지기가 이 모듈의 신선도를 판정할 자기 산출물이 없었다(2026-08-29 시우 자가점검).
        # 새 파일·새 관례를 만들지 않고 전 모듈이 이미 쓰는 module_heartbeat 관문에 합류한다(약속 L21).
        try:
            from module_heartbeat import record_heartbeat  # noqa: PLC0415
            open_total = sum(s["open"] for s in by_dept.values())
            record_heartbeat(
                "coo-reception",
                f"접수 현황 갱신 — 미처리 {open_total}건·3일초과 {overdue_3d}·"
                f"7일초과 {overdue_7d}·분실물 {lost_open}",
            )
        except Exception as exc:  # fail-soft — 하트비트 실패가 스냅샷을 무효로 만들지 않는다
            print(f"[stream2b] 하트비트 기록 건너뜀: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
    except Exception as e:
        print(f"[stream2b] reception_watch.json 쓰기 실패: {e}", file=sys.stderr)


def _parse_created(s) -> datetime | None:
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _today_section(rows: list[dict], today: str) -> str:
    """오늘 신규 접수 요약(카테고리별 건수 + 미처리)."""
    today_rows = [r for r in rows if str(r.get("createdAt", "")).startswith(today)]
    if not today_rows:
        return "📮 오늘 신규 접수 없음."
    cat_cnt: dict[str, int] = {}
    undone_today = 0
    for r in today_rows:
        cat = str(r.get("category") or "기타").strip()
        cat_cnt[cat] = cat_cnt.get(cat, 0) + 1
        if str(r.get("status", "")) != "완료":
            undone_today += 1
    cat_str = " · ".join(f"{c}:{n}" for c, n in sorted(cat_cnt.items(), key=lambda x: -x[1]))
    return f"📮 오늘 신규 접수 {len(today_rows)}건 (미처리 {undone_today}건)  {cat_str}"


def _fmt_age(days: int, elapsed_h: float) -> str:
    # ★일수는 reception_elapsed_days(정본=ops_shared) 그대로 씀 — 여기서 elapsed_h/24로
    # 다시 계산하면 소수점(28.8일)이 나와 ops_daily_digest의 정수 "N일째"와 갈라진다
    # (GM 2026-08-05 실측 지적, 약속 L01). 만 하루 미만만 시간 단위로 보여준다.
    return f"{days}일" if days >= 1 else f"{elapsed_h:.1f}시간"


def _collect_overdue(rows: list[dict], now: datetime | None = None,
                     scope: str = "ops") -> list[dict]:
    """기한(SLA) 넘긴 미처리 건 원자료 — _aging_block(상세 렌더)과 build_kakao_digest
    (압축 렌더) 양쪽이 같은 판정을 공유한다(약속 L01 — 판정을 두 곳에서 따로 하지 않는다).

    scope — 어느 방으로 갈 몫인가 (GM 지시 2026-08-18 '강습부건은 부서장방에,
    시설부/운영부/지원부건은 ★운영+시설+지원+주차 방에'). 판정은 _intake_room_for
    한 곳만 쓴다 — 부서 이름을 여기서 다시 따지면 규칙이 두 벌이 된다(약속 L01).
      ops    = ★운영+시설+지원+주차 몫(강습·업장 제외)
      lesson = ★부서장 몫(강습·업장만)
      all    = 종전 동작(전부) — 되돌릴 때 쓴다
    """
    now = now or datetime.now()
    want_room = {"ops": _INTAKE_ROOM_DEFAULT, "lesson": _INTAKE_ROOM_LESSON}.get(scope)
    undone = [r for r in rows if str(r.get("status", "")) != "완료"]

    overdue: list[dict] = []
    for r in undone:
        cat = str(r.get("category") or "").strip()
        sla = _SLA_HOURS.get(cat)
        if sla is None:  # 칭찬 등 SLA 없음 — 적체 집계 제외
            continue
        created = _parse_created(r.get("createdAt"))
        if created is None:
            continue
        elapsed_h = (now - created).total_seconds() / 3600.0
        if elapsed_h > sla:
            overdue.append({
                "regId": str(r.get("regId") or ""),
                "cat": cat,
                # 부서 — 묶음 기준을 사람에서 부서로 옮기기 위해 같이 담는다(배627 · GM 지시 2026-08-14
                # "담당자 칸은 없애고 각 부서에 전달되어야 한다"). 완료 통보 블록이 쓰는 것과 같은 칸이다.
                "dept": str(r.get("dept") or "").strip(),
                # 개행만 없앤다 — 자르지 않는다(GM 지시 2026-08-27 "내용 끊지말고 다 나오게").
                "content": " ".join(str(r.get("content") or "").split()),
                "elapsed_h": elapsed_h,
                "days": reception_elapsed_days(r, now),  # 표시용 "N일째" 정본(SLA 판정은 elapsed_h 유지)
                "sla": sla,
                "created_md": f"{created.month}/{created.day}",  # 압축본 "오래된 순" 표시용
            })

    # ★2026-08-07 시토(배429 · 약속 L24) — 받는 사람을 이경연 실장 한 곳으로 적는다.
    #   아래 담당자별 목록은 지우지 않는다 — 그건 '누구에게 시킨다'가 아니라 실장이 나눌 때
    #   보는 참고 정보다(GM 확정 2026-08-06: 실장이 분배하고, 상향 보고도 실장이 취합한다).
    if want_room:
        overdue = [it for it in overdue if _intake_room_for(it["dept"]) == want_room]
    return overdue


def _aging_block(rows: list[dict], now: datetime | None = None,
                 scope: str = "ops") -> str:
    """기한(SLA) 넘긴 미처리 건 — 부서별 그룹 + 오래된 순 상세(텔레그램 전문)."""
    overdue = _collect_overdue(rows, now, scope)
    undone = [r for r in rows if str(r.get("status", "")) != "완료"]

    # ★2026-08-21 시우(GM 지시 — 분실물은 접수 적체에서 뗀다).
    #   분실물은 보관 성격(30일 주기)이라 실장이 '처리'해 닫는 일이 아니고, 처분은
    #   습득물 사이클(coo/reception/lost_found_guide.html)이 따로 돈다. 부서 적체 집계
    #   (reception_watch by_dept)는 이미 빼고 세는데 이 전문만 섞여 있어 같은 날 숫자가
    #   두 벌로 보였다(약속 L01). 목록에서 빼고 건수만 한 줄로 남긴다 — 건수는 안 지운다.
    lost_overdue = [it for it in overdue if it["cat"] == "분실물 접수"]
    overdue = [it for it in overdue if it["cat"] != "분실물 접수"]
    lost_undone = sum(1 for r in undone
                      if str(r.get("category") or "").strip() == "분실물 접수")

    head = ("⏰ 미처리 적체 리마인드 (강습·업장)" if scope == "lesson"
            else "⏰ 미처리 적체 리마인드 (이경연 실장)")
    lines = [head, (f"기한초과 {len(overdue)}건" if scope == "lesson"
                    else f"미처리 {len(undone) - lost_undone}건 · 기한초과 {len(overdue)}건")]
    if lost_undone:
        lines.append(f"🧳 분실물 {lost_undone}건은 별도 — 습득물 보관·처분 주기로 관리합니다.")
    if not overdue:
        lines.append("기한 초과 건 없음.")
        return "\n".join(lines)

    def _fmt_item(it: dict) -> str:
        ratio = it["elapsed_h"] / it["sla"] if it["sla"] else 0.0
        flag = "🔴" if ratio >= 3 else "⚠️"
        # 제목 줄(분류·경과·접수번호)만 훑어도 뜻이 통하고, 내용은 다음 줄에 통째로 싣는다
        # (GM 지시 2026-08-27 — 잘린 내용으로는 무엇을 하라는 건지 알 수 없다).
        head = f"  {flag} [{it['cat']}] — {_fmt_age(it['days'], it['elapsed_h'])} 경과 ({it['regId']})"
        return head + (f"\n     {it['content']}" if it["content"] else "")

    # ★2026-08-14 시토(배627 · GM 지시) — 묶음 기준을 **사람에서 부서로** 옮긴다.
    #   GM 원문: "각 부서에 전달되어야 하고 그 부서에서 조치 및 회신까지 챙기는 게 낫다.
    #   다 운영부 라인으로 넘기니 병목이 일어나고 처리가 안 된다. 담당자 칸은 없애고."
    #   담당자 칸이 사라지면 사람 기준 묶음은 전건이 '미배정'으로 떨어져 목록이 무의미해진다.
    #   부서는 접수 행에 이미 있고 완료 통보 블록이 쓰던 바로 그 칸이라 새로 만들 것이 없다(L21).
    #   ▸★2026-08-21 GM 재확인 — 담당자 이름을 줄 끝에 남기던 것도 뗀다. 접수처의 사람
    #     분류는 접수자·처리자 둘뿐이고 '담당'은 없앤 칸이라, 그 값을 계속 비추면
    #     없앤 칸이 화면에서만 살아 있게 된다(약속 L01). 처리자는 완료 통보 블록이 낸다.
    by_dept: dict[str, list[dict]] = {}
    for it in overdue:
        by_dept.setdefault(it.get("dept") or "부서 미정", []).append(it)

    def _emit(title: str, items: list[dict]) -> None:
        items = sorted(items, key=lambda x: -x["elapsed_h"])
        lines.append(f"\n🏢 {title} ({len(items)}건)")
        for it in items:
            lines.append(_fmt_item(it))

    # 부서 미정을 맨 위로(주인이 없는 건이 묻히면 안 된다), 이후 최고령 건 기준 오래된 순.
    if "부서 미정" in by_dept:
        _emit("부서 미정", by_dept.pop("부서 미정"))
    for dept in sorted(by_dept, key=lambda d: -max(i["elapsed_h"] for i in by_dept[d])):
        _emit(dept, by_dept[dept])

    lines.append(f"\n👉 상세: {DASHBOARD_URL}")
    return "\n".join(lines)


def _score_block() -> str:
    """🏆 이번 주 점수판 — 접수 1점 + 처리 완료 1점 (GM 지시 2026-07-28).

    왜 여기에 붙나: 접수한 사람이 곧 처리까지 떠안는 구조라 '적을수록 손해'가 되어
    아예 안 적게 된다. 적는 행위 자체에 점수를 붙이고, 그걸 같이 보며 칭찬한다.
    ▸새 발송·새 예약을 만들지 않는다(약속 L21) — 이미 매일 밤 같은 방으로 나가는
      이 메시지 끝에 얹는다. 알림이 하나 더 늘면 그만큼 안 읽힌다.
    ▸셈법은 서버(reg_scoreboard) 한 곳뿐 — 여기서 다시 세지 않는다. 화면과 이 발표의
      숫자가 갈라지면 아무도 점수를 안 믿는다.
    """
    resp = gas_get(RECEPTION_EXEC_URL, {"action": "reg_scoreboard", "period": "week"},
                   timeout=20, label="stream2b-score")
    if resp is None:
        return ""
    try:
        data = resp.json()
        board = data.get("board", []) if data.get("ok") else []
    except Exception:
        return ""
    if not board:
        return (f"{_DIVIDER}\n🏆 이번 주 점수판 (접수 1점 + 완료 1점)\n\n"
                "아직 점수가 없습니다. 접수하시거나 처리를 끝내시면 쌓입니다.")

    lines = [_DIVIDER, "🏆 이번 주 점수판 (접수 1점 + 완료 1점)", ""]
    top = board[0]["total"]
    for x in board[:5]:
        mark = "🎉" if x["total"] == top else "▪"
        lines.append(f"{mark} {x['rank']}위 {x['name']} — {x['total']}점")
        lines.append(f"   접수 {x['intake']} · 완료 {x['done']}")
    winners = [x["name"] for x in board if x["total"] == top]
    lines.append("")
    lines.append(f"🎊 {' · '.join(winners)}님 수고하셨습니다! 이번 주 1위입니다 🎊")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# 접수 처리 점수제 4규칙 (GM 승인 2026-08-29 · status/previews/접수_점수제_설계.md)
# +1 완료일≤완료예정일(단 접수+7일 넘으면 무효) / +3 정책반영(체크만·GM 주간승인으로 확정,
# 자동 가산 안 함) / -1 접수+7일 초과 완료 / -3 접수+14일 미완 그 자리에서 확정(뒤에
# 완료해도 유지). 분실물 제외. 점수는 처리자·담당자(부서 책임자) 각각, 동일인 1회.
#
# ★완료일이 시트에 없다(_first_done_at_and_stats 주석 참고) — 유일한 출처가 이 파일의
#   first_done_at 저널(status/reception_watch.json)이라 판정은 여기서만 한다. 위 _score_block
#   (접수/완료 단순집계)의 "셈법은 서버(GAS) 한 곳" 원칙은 그 두 숫자에 한한다 — GAS는
#   완료일을 몰라 이 4규칙을 못 판정한다(설계 문서도 이를 전제로 "칸 신설 후 착수분부터
#   판정 가능"이라 적었다).
# ══════════════════════════════════════════════════════════════════════════
SCORE_DUE_DEFAULT_DAYS = 3     # 완료예정일 미설정 시 접수+3일로 간주(설계 ③)
SCORE_LATE_DAYS = 7            # 완료까지 이 날짜를 넘기면 -1(예정일을 넉넉히 잡아도 못 피한다)
SCORE_ABANDON_DAYS = 14        # 미완 상태로 이 날짜에 이르면 그 자리에서 -3 확정
SCORE_EXCLUDE_CATEGORY = "분실물 접수"   # 3단계 마감(보관·공지·이관) 별도 소관
SCORE_ESCALATE_MARKER = "14일 초과 — 운영부 실장 이관(원담당 −3 확정)"
SCORE_ESCALATE_DEPT = "운영부"


def _score_due_date(created: str, due_date_raw) -> "datetime | None":
    """완료예정일 유효값 — 비어 있으면 접수+3일(설계 ③ 기본 규칙, '안 적는 게 이득'을 막는다)."""
    created_s = str(created or "")[:10]
    try:
        created_dt = datetime.strptime(created_s, "%Y-%m-%d")
    except Exception:
        return None
    d = str(due_date_raw or "").strip()[:10]
    if d:
        try:
            return datetime.strptime(d, "%Y-%m-%d")
        except Exception:
            pass   # 값이 있는데 못 읽으면 기본값으로 폴백(판정 불가로 지어내지 않는다)
    return created_dt + timedelta(days=SCORE_DUE_DEFAULT_DAYS)


def score_row(row: dict, first_done_at: dict, today: datetime) -> "int | None":
    """접수 1건의 확정 점수. 반환: 1·-1·-3 또는 None(분실물·판정불가·아직 미확정).
    -3은 '미완 상태로 14일'에 확정되면 나중에 완료돼도 같은 값이 나온다 — days_to_complete
    자체가 이미 14 이상이라 완료 시점을 나중에 넣어도 결과가 안 바뀐다(재판정 안전)."""
    if str(row.get("category") or "").strip() == SCORE_EXCLUDE_CATEGORY:
        return None
    created_s = str(row.get("createdAt") or "")[:10]
    if not created_s:
        return None
    try:
        created_dt = datetime.strptime(created_s, "%Y-%m-%d")
    except Exception:
        return None
    due_dt = _score_due_date(created_s, row.get("dueDate"))
    if due_dt is None:
        return None
    reg_id = str(row.get("regId") or "")
    is_done = str(row.get("status") or "") == "완료"
    done_s = first_done_at.get(reg_id) if is_done else None
    if done_s:
        try:
            done_dt = datetime.strptime(done_s, "%Y-%m-%d")
        except Exception:
            return None
        days = (done_dt - created_dt).days
        if days >= SCORE_ABANDON_DAYS:
            return -3
        if days > SCORE_LATE_DAYS:
            return -1
        return 1 if done_dt <= due_dt else 0
    # 미완 — 14일 넘었으면 그 자리에서 -3 확정. 7~13일은 '예약'일 뿐 아직 확정 점수 없음.
    age = (today - created_dt).days
    return -3 if age >= SCORE_ABANDON_DAYS else None


def _selfcheck_score_rule() -> None:
    """경계값 자체 점검 — 실행하면 통과 시 조용히 끝나고, 실패하면 AssertionError."""
    today = datetime(2026, 8, 29)
    base = {"category": "컴플레인 접수", "createdAt": "2026-08-01", "regId": "T1"}

    # 분실물 제외
    assert score_row({**base, "category": SCORE_EXCLUDE_CATEGORY, "status": "완료"},
                      {"T1": "2026-08-30"}, today) is None

    # 완료예정일 미설정 = 접수+3일 기본값. 접수 8/1 → 기본 예정일 8/4.
    assert score_row({**base, "status": "완료"}, {"T1": "2026-08-04"}, today) == 1   # 예정일(기본) 안에 완료
    assert score_row({**base, "status": "완료"}, {"T1": "2026-08-05"}, today) == 0   # 기본 예정일은 넘겼지만 7일 안

    # 예정일을 스스로 잡은 경우(8/6=접수+5일) — 경계값 정확히
    row_due = {**base, "dueDate": "2026-08-06", "status": "완료"}
    assert score_row(row_due, {"T1": "2026-08-06"}, today) == 1     # 예정일 당일 = 안 늦음
    assert score_row(row_due, {"T1": "2026-08-05"}, today) == 1     # 예정일보다 일찍 = +1
    assert score_row(row_due, {"T1": "2026-08-07"}, today) == 0     # 예정일(8/6) 넘겼지만 7일(8/8) 안 = 무점
    assert score_row(row_due, {"T1": "2026-08-08"}, today) == 0     # 접수+7일 경계 — 아직 -1은 아니다(0)
    # ★핵심 위험 케이스: 예정일을 7일 넘게(8/10=접수+9일) 잡아도 8일째 완료는 그대로 -1이다
    #   ("예정일을 넉넉히 잡아 +1을 챙기는 길은 없다" — 설계 ① 위험 한 줄).
    row_due_late = {**base, "dueDate": "2026-08-10", "status": "완료"}
    assert score_row(row_due_late, {"T1": "2026-08-10"}, today) == -1   # 예정일 안에 완료해도 접수+9일 = -1
    assert score_row({**base, "status": "완료"}, {"T1": "2026-08-08"}, today) == 0   # 접수+7일(경계) — 기본예정일 넘겨 0
    assert score_row({**base, "status": "완료"}, {"T1": "2026-08-09"}, today) == -1  # 접수+8일 = -1(예정일 넉넉해도 못 피함)
    assert score_row({**base, "status": "완료"}, {"T1": "2026-08-14"}, today) == -1  # 13일째 완료 = -1
    assert score_row({**base, "status": "완료"}, {"T1": "2026-08-15"}, today) == -3  # 14일째 완료 = -3(그때부터 유지)
    assert score_row({**base, "status": "완료"}, {"T1": "2026-09-01"}, today) == -3  # 훨씬 늦게 완료해도 -3 유지

    # 미완 상태 — 7~13일은 아직 미확정(None), 14일부터 -3 확정
    assert score_row({**base, "createdAt": "2026-08-20", "status": "처리중"}, {}, today) is None   # 9일째, 아직
    assert score_row({**base, "createdAt": "2026-08-16", "status": "처리중"}, {}, today) is None   # 13일째, 아직
    assert score_row({**base, "createdAt": "2026-08-15", "status": "처리중"}, {}, today) == -3     # 14일째, 확정
    assert score_row({**base, "createdAt": "2026-06-01", "status": "접수"}, {}, today) == -3       # 훨씬 오래 미완도 -3


def build_score4_table(rows: list[dict], today: datetime | None = None) -> dict[str, dict]:
    """4규칙을 전 rows에 적용해 사람별 집계표를 만든다. 반환 {이름: {plus1,minus1,minus3,plus3_pending}}.
    담당자(부서 책임자) 이름은 kpi.json 정본을 send_ops_digest._ovd_leaders()로 그대로 재사용한다
    (약속 L01 — 여기서 다시 표를 만들지 않는다). 처리자·담당자가 동일인이면 그 건은 1회만 계상."""
    today = today or datetime.now()
    first_done_at, _src, _stats = _first_done_at_and_stats(rows, today)
    try:
        from send_ops_digest import _ovd_leaders  # noqa: PLC0415 (지연 임포트 — 순환 임포트 방지)
        leaders = _ovd_leaders()
    except Exception:
        leaders = {}

    # 처리자 칸(handlerCanon)은 GAS _regStaffCanonList 가 이미 직함을 뗀 맨이름으로 정규화한다
    # (예: '이정헌소장'→'이정헌'). 담당자(dept 책임자) 이름은 kpi.json 정본이 직함 포함형이다
    # (예: '이정헌 소장'). 같은 사람이 직함 유무로 갈려 두 줄로 잡히는 것을 막는다(GAS
    # REG_STAFF_TITLE_RE 와 같은 직함 목록 재사용 — 약속 L01, 새 규칙 만들지 않는다).
    _TITLE_SUFFIX_RE = re.compile(
        r"\s*(GM|AM|M|매니저|사원|주임|대리|과장|차장|부장|실장|소장|팀장|프로|강사|시니어|주니어|코치|반장|님)$")

    def _bare(name: str) -> str:
        return _TITLE_SUFFIX_RE.sub("", str(name or "").strip()).strip()

    bare_to_display = {_bare(disp): disp for disp in leaders.values() if disp}

    tally: dict[str, dict] = {}

    def _bump(name: str, key: str) -> None:
        name = str(name or "").strip()
        if not name:
            return
        tally.setdefault(name, {"plus1": 0, "minus1": 0, "minus3": 0, "plus3_pending": 0})
        tally[name][key] += 1

    for r in rows:
        dept = str(r.get("dept") or "").strip()
        owner = leaders.get(dept, "") if dept else ""
        handler_canon = r.get("handlerCanon") or []
        handler_raw = str(handler_canon[0]) if handler_canon else str(r.get("handler") or "").strip()
        # 처리자가 알려진 부서 책임자와 같은 사람이면(직함만 다르면) 책임자 표기로 합친다.
        handler = bare_to_display.get(_bare(handler_raw), handler_raw)

        delta = score_row(r, first_done_at, today)
        if delta == -3:
            recipients = {owner} if owner else set()          # -3은 담당자만(처리자 아직 없음)
        elif delta is not None:
            recipients = {n for n in (owner, handler) if n}    # +1/-1은 처리자·담당자 각각(동일인 1회)
        else:
            recipients = set()
        key = {1: "plus1", -1: "minus1", -3: "minus3"}.get(delta)
        if key:
            for who in recipients:
                _bump(who, key)

        # +3 후보 — 자동 확정 안 함(설계 GM 확정). 담당자·처리자 둘 다에 '후보'로만 표시.
        if str(r.get("policyFix") or "").strip():
            for who in {n for n in (owner, handler) if n}:
                _bump(who, "plus3_pending")

    return tally


def _score4_block(rows: list[dict], today: datetime | None = None) -> str:
    """📐 처리 점수제 — 기존 접수/완료 점수판(_score_block) 아래에 얹는 4규칙 요약.
    표만 낸다(사람 탓 문장 금지 — 설계 문서 지시)."""
    today = today or datetime.now()
    table = build_score4_table(rows, today)
    if not table:
        return ""
    names = sorted(table, key=lambda n: (-(table[n]["plus1"] - table[n]["minus1"] * 1 - table[n]["minus3"] * 3), n))
    lines = [_DIVIDER, "📐 처리 점수제 (완료예정일 신설 이후 집계)", ""]
    for name in names[:8]:
        t = table[name]
        net = t["plus1"] - t["minus1"] - t["minus3"] * 3
        bits = []
        if t["plus1"]:
            bits.append(f"+1×{t['plus1']}")
        if t["minus1"]:
            bits.append(f"-1×{t['minus1']}")
        if t["minus3"]:
            bits.append(f"-3×{t['minus3']}")
        if t["plus3_pending"]:
            bits.append(f"+3 후보×{t['plus3_pending']}(GM 승인 대기)")
        lines.append(f"▪ {name} — {net:+d}점 ({' · '.join(bits)})")
    return "\n".join(lines)


def apply_overdue_escalation(rows: list[dict], today: datetime | None = None,
                              dry_run: bool = True) -> list[dict]:
    """설계 ② — 14일 미완 확정건을 운영부로 재배정 + 메모 자동 기록(기존 처리메모 뒤에 덧붙임).
    실장도 이관일부터 새 시계로 같은 규칙을 받는다(재배정된 dept='운영부' 건이 그 다음부터
    createdAt 기준으로 다시 age를 재는 게 아니라, '이관 후 처리 소요'는 별도 시각이 없어
    이번 구현에서는 재배정 사실만 남긴다 — 실장 몫 재귀 판정은 이관일 기준 별도 시계가
    필요해 후속 과제로 남긴다).
    dry_run=True(기본)면 대상 목록만 반환하고 쓰지 않는다(새 액션 없음 — 기존 reg_update 재사용)."""
    today = today or datetime.now()
    targets = []
    for r in rows:
        if str(r.get("status") or "") == "완료":
            continue   # 이미 끝난 옛 건을 소급 이관하지 않는다 — '진행중' 확정건만
        if score_row(r, {}, today) != -3:
            continue
        if str(r.get("dept") or "").strip() == SCORE_ESCALATE_DEPT:
            continue   # 이미 운영부
        if SCORE_ESCALATE_MARKER in str(r.get("memo") or ""):
            continue   # 이미 이관 기록됨(멱등)
        targets.append(r)
    if dry_run or not targets:
        return targets
    done = []
    for r in targets:
        memo = str(r.get("memo") or "")
        new_memo = memo + ("\n" if memo else "") + SCORE_ESCALATE_MARKER
        payload = {"action": "reg_update", "id": r.get("regId"), "category": r.get("category"),
                   "dept": SCORE_ESCALATE_DEPT, "memo": new_memo}
        ok = _reg_update_post(payload)
        done.append({"regId": r.get("regId"), "ok": ok})
    return done


def _reg_update_post(payload: dict, timeout: int = 20) -> bool:
    """reg_update 관문 재사용(새 액션 안 만든다) — 화면(_update)과 같은 요청 형식(text/plain+JSON)."""
    try:
        resp = requests.post(RECEPTION_EXEC_URL,
                              data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              headers={"Content-Type": "text/plain;charset=UTF-8"}, timeout=timeout)
        return resp.status_code == 200 and bool(resp.json().get("ok"))
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════
# 부서 톡방 처리완료 통보(2026-08-01 GM 지시) — 개인 회신이 아니라 부서 단위로.
# GM: "접수한 사람으로 하는것보단, 톡방(부서 단위)으로 하는게 좋을 것 같아" — 접수자가
# 익명 회원인 접수도 많아 개인 회신 자체가 불가능하고, 처리도 팀 단위로 움직인다.
# 새 방·새 발신 경로를 만들지 않는다(약속 L21) — 이 다이제스트 본문에 블록 하나만 얹어
# 기존 배선(텔레그램 종합접수처방 + kakao-ops-stream2가 재사용하는 ★운영+시설+지원+주차
# 카톡방)을 그대로 탄다. 킬스위치=status/dept_completion_notify.json{"enabled":false}
# (기본 꺼짐 — GM go 전 실무진·부서 방 노출 금지). 완료건에 처리시각 칸이 없어(시트에
# completedAt 없음) "며칠 전 완료"를 못 구하는 대신, 직전 발신 이후 새로 status='완료'가
# 된 건만 골라 부서별로 묶는다(멱등 커서=reception_seen_done_ids, 매 실행 갱신) — 그래서
# 한 번에 최대 _COMPLETION_CAP건만 보이고 나머지는 "…외 N건"으로 접는다(폭주 방지).
# ══════════════════════════════════════════════════════════════════════════
COMPLETION_STATE_PATH = REPO_ROOT / "status" / "dept_completion_notify.json"
_COMPLETION_CAP = 0  # 0 = 전부 보여줌(GM 지시 2026-08-30 "다 보고 싶다"). 종전 6건


def _load_completion_state() -> dict:
    try:
        if COMPLETION_STATE_PATH.exists():
            return json.loads(COMPLETION_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"enabled": False, "reception_seen_done_ids": [], "inquiry_seen_keys": []}


# ★2026-08-05 시토 — 커서를 '보낸 뒤에' 파일에 쓴다.
#   전에는 _completion_block 이 문구를 만드는 그 자리에서 곧바로 파일에 커서를 적었다.
#   그런데 발송은 그 다음 단계라, 텔레그램이 실패하면(토큰 만료·429·방 권한 등) 아무 방에도
#   안 갔는데 커서만 전진해 있었다 — 그 완료건들은 다음 날에도 '이미 통보함'으로 걸러져
#   영영 통보되지 않는다. 조용히 사라지는 종류의 사고라 아무도 모른다.
#   그래서 문구를 만들 때는 메모리의 state 만 갱신해 두고(같은 실행 안에서의 멱등은 그대로),
#   실제 파일 쓰기는 발송 성공을 확인한 호출자가 commit_completion_cursor() 로 한 번 한다.
#   발송이 실패하면 커서가 안 움직이므로 다음 회차에 다시 통보된다(잃는 것보다 겹치는 게 낫다).
_pending_state: dict | None = None


def commit_completion_cursor() -> bool:
    """처리완료 통보가 실제로 나간 뒤 호출 — 대기 중인 커서를 파일에 확정한다.
    대기분이 없으면 아무것도 하지 않고 False."""
    global _pending_state
    if _pending_state is None:
        return False
    _save_completion_state(_pending_state)
    _pending_state = None
    return True


def _save_completion_state(state: dict) -> None:
    try:
        COMPLETION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        COMPLETION_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _completion_block(rows: list[dict], state: dict | None = None, persist: bool = True) -> str:
    """새로 완료된 종합접수 건을 부서별로 묶어 알림 블록으로 렌더. state 미지정 시 파일에서
    읽는다. persist=False면 커서를 갱신하지 않는다(검증·시뮬레이션에서 반복 실행해도 같은
    결과가 나와야 하므로 — 실제 22:30 다이제스트 발신 시에만 persist=True로 커서를 전진)."""
    state = state if state is not None else _load_completion_state()
    if not state.get("enabled"):
        return ""
    seen = set(state.get("reception_seen_done_ids") or [])
    done_now = [r for r in rows if str(r.get("status", "")) == "완료" and str(r.get("regId") or "")]
    new_done = [r for r in done_now if str(r["regId"]) not in seen]
    if persist:
        global _pending_state
        state["reception_seen_done_ids"] = sorted({str(r["regId"]) for r in done_now})
        _pending_state = state   # 파일 확정은 발송 성공 뒤 commit_completion_cursor()
    if not new_done:
        return ""

    remain_by_dept: dict[str, int] = {}
    for r in rows:
        if str(r.get("status", "")) != "완료":
            dept = str(r.get("dept") or "기타").strip() or "기타"
            remain_by_dept[dept] = remain_by_dept.get(dept, 0) + 1

    def _fmt(r: dict) -> str:
        dept = str(r.get("dept") or "기타").strip() or "기타"
        cat = str(r.get("category") or "").strip()
        content = " ".join(str(r.get("content") or "").split())   # 자르지 않는다(GM 2026-08-27)
        # 서버가 통일해 준 표기(handlerCanon)를 쓴다(2026-08-01) — 원문을 여기서 다시 판정하면
        # '최준용'/'최준용M' 이 또 갈라진다(약속 L01, _aging_block과 동일 원칙).
        # ★2026-08-21 GM 확정 — 담당(assignee) 대체값을 뺐다. 처리한 사람은 '처리자' 칸 하나다.
        who_list = [str(x).strip() for x in (r.get("handlerCanon") or []) if str(x).strip()]
        who = "/".join(who_list) if who_list else (
            str(r.get("handler") or "").strip() or "처리자 미기재")
        remain = remain_by_dept.get(dept, 0)
        head = f"✅ [{dept}] {cat} · 처리 {who} · 남은 미처리 {remain}건"
        return head + (f"\n     {content}" if content else "")

    shown = new_done if _COMPLETION_CAP <= 0 else new_done[:_COMPLETION_CAP]
    lines = [f"{_DIVIDER}\n✅ 처리 완료 알림 {len(new_done)}건"]
    lines += [_fmt(r) for r in shown]
    if len(new_done) > len(shown):
        lines.append(f"  …외 {len(new_done) - len(shown)}건 더")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# 접수 즉시 부서 전달(배627 · GM 지시 2026-08-14) — 아직 발송하지 않는다(드라이런만).
# GM: "컴플레인 접수 위치·내용이 나오면 각 부서에 전달되어야 하고, 그 부서에서 조치 및
# 회신까지 챙기는 게 낫다. 다 운영부 라인으로 넘기니 병목이 일어나고 처리가 안 된다."
# GM 결정(같은 날): 전달 범위는 컴플레인·고장만이 아니라 **전건**. 대신 폭주는 묶어서 막는다.
#
# ▸부서는 접수 시점에 카테고리로 이미 정해진다(apps_script_reception.js REG_CATEGORIES —
#   분실물/칭찬/쓴소리/컴플레인=운영부 · 시설물고장=시설부 · 청결=지원부). 여기서 다시
#   판정하지 않는다(약속 L01).
# ▸새 상태 파일을 만들지 않는다(약속 L21) — 완료 통보가 쓰던 dept_completion_notify.json 에
#   커서 키 하나만 얹는다. 커서 전진 규칙도 완료 통보와 같다(보낸 뒤에만 확정).
# ▸게이트 intake_relay_enabled 기본 꺼짐. 실무진 방으로 나가는 새 발신이라 GM 이 문구를
#   보고 확인한 뒤에만 켠다.
# ══════════════════════════════════════════════════════════════════════════
_INTAKE_CAP = 0  # 0 = 부서별 전부 보여줌(GM 지시 2026-08-30). 종전 6건


def _intake_relay_block(rows: list[dict], state: dict | None = None,
                        persist: bool = True, force: bool = False) -> str:
    """직전 전달 이후 새로 들어온 접수를 부서별로 묶어 전달 문구로 렌더.
    force=True면 게이트가 꺼져 있어도 문구를 만든다(드라이런 확인용 — 발송은 하지 않는다)."""
    state = state if state is not None else _load_completion_state()
    if not state.get("intake_relay_enabled") and not force:
        return ""
    seen = set(state.get("reception_seen_new_ids") or [])
    all_ids = {str(r.get("regId")) for r in rows if str(r.get("regId") or "")}
    new_rows = [r for r in rows if str(r.get("regId") or "") and str(r["regId"]) not in seen]
    if persist:
        global _pending_state
        state["reception_seen_new_ids"] = sorted(all_ids)
        _pending_state = state   # 파일 확정은 발송 성공 뒤 commit_completion_cursor()
    if not new_rows:
        return ""

    by_dept: dict[str, list[dict]] = {}
    for r in new_rows:
        by_dept.setdefault(str(r.get("dept") or "").strip() or "부서 미정", []).append(r)

    lines = [f"📮 새 접수 {len(new_rows)}건 — 해당 부서에서 조치·회신 부탁드립니다."]
    for dept in sorted(by_dept, key=lambda d: -len(by_dept[d])):
        items = by_dept[dept]
        lines.append(f"\n🏢 {dept} ({len(items)}건)")
        for r in (items if _INTAKE_CAP <= 0 else items[:_INTAKE_CAP]):
            cat = str(r.get("category") or "").strip()
            # ★2026-08-27 GM 지시 — "내용도 같이 넣어줘, 길어도 다 넣어줘". 종전에는 28자에서
            # 잘라 「수영장 내 샤워부스 총2개 남자쪽 1개 여자쪽 1개」처럼 무엇을 고쳐야 하는지
            # 모른 채 화면에 들어가야 했다. 이제 자르지 않는다.
            content = " ".join(str(r.get("content") or "").split())
            lines.append(f"  ▪ [{cat}] ({r.get('regId')})")
            if content:
                # 제목 줄만 훑어도 뜻이 통하게 — 상세는 다음 줄 들여쓰기(GM 2026-08-25 가독 규칙).
                lines.append(f"     {content}")
        if _INTAKE_CAP > 0 and len(items) > _INTAKE_CAP:
            lines.append(f"  …외 {len(items) - _INTAKE_CAP}건 더")
    lines.append(f"\n👉 상세·처리: {DASHBOARD_URL}")
    return "\n".join(lines)


# 부서 → 실제로 나가는 카톡 방 (GM 확정 2026-08-15).
#   강습 = ★부서장 방 / 그 밖의 부서 = ★운영+시설+지원+주차 방.
# 방 이름은 카톡 창 제목과 같아야 한다(정본 = scripts/kakao_rooms.json all_rooms).
_INTAKE_ROOM_DEFAULT = "★운영+시설+지원+주차"
_INTAKE_ROOM_LESSON = "★부서장"
TEST_CHAT_ID = 8254867551  # 텔레그램 업무관리방 — 테스트 발신은 항상 여기로(GM 확정)


def _intake_room_for(dept: str) -> str:
    """★2026-08-17 수리. 부서 구분이 3개에서 11개로 늘면서 이 판정이 죽어 있었다.
    옛 값에는 「강습」이라는 부서가 있어 문자열 포함으로 갈렸는데, 새 11개 값
    (운영부·시설부·지원부(남)·지원부(여)·수영팀·P.T팀·골프팀·스쿼시팀·체조팀·
    뮤지컬팀·루프메소드팀) 중 「강습」을 품은 값이 **하나도 없다** → 업장 접수가
    전부 기본 방으로 새고 있었다(GM 확정 2026-08-15 '강습·업장=부서장방'이 무효화).
    업장 = 이름이 「팀」으로 끝나는 부서다. 옛 값 호환으로 「강습」 포함 판정도 남긴다.
    """
    d = str(dept or "").strip()
    return _INTAKE_ROOM_LESSON if ("강습" in d or d.endswith("팀")) else _INTAKE_ROOM_DEFAULT


# ── 접수 사진 첨부(GM 지시 2026-08-27) ────────────────────────────────────────
# 접수 폼이 받은 사진은 구글 드라이브에 있고 행의 photoUrl 에 보기 주소로 들어온다
# (실측: 124건 중 13건에 사진 · 시설물 고장 8건). 보기 주소는 카톡에서 눌러도 로그인
# 화면이 뜰 수 있어, 파일을 내려받아 사진 자체를 붙인다. 발신은 기존 관문 그대로(L21).
_DRIVE_ID_RE = re.compile(r"/d/([\w-]+)")
_PHOTO_MAX_BYTES = 15 * 1024 * 1024
_PHOTO_MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")


def _download_photo(url: str, dest_dir: Path, name: str) -> Path | None:
    """드라이브 보기 주소 → 로컬 이미지 파일. 실패하면 None(사진 없이 글만 나간다)."""
    import urllib.request  # noqa: PLC0415
    m = _DRIVE_ID_RE.search(str(url or ""))
    if not m:
        return None
    dl = f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download"
    try:
        req = urllib.request.Request(dl, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            blob = resp.read(_PHOTO_MAX_BYTES + 1)
    except Exception as e:
        print(f"[intake-relay] 사진 내려받기 실패({name}): {e}", flush=True)
        return None
    # 권한이 없으면 구글이 이미지 대신 로그인 HTML 을 200 으로 준다 — 머리 몇 바이트로 가린다
    if len(blob) > _PHOTO_MAX_BYTES or not blob.startswith(_PHOTO_MAGIC):
        print(f"[intake-relay] 사진 아님/너무 큼 — 건너뜀({name})", flush=True)
        return None
    ext = ".png" if blob.startswith(_PHOTO_MAGIC[1]) else ".jpg"
    path = dest_dir / f"{name}{ext}"
    path.write_bytes(blob)
    return path


def _send_intake_photos(room: str, rows: list[dict]) -> int:
    """사진이 딸린 접수만 골라 글 다음에 사진을 이어 보낸다. 반환 = 보낸 장수."""
    import tempfile  # noqa: PLC0415
    targets = [r for r in rows if str(r.get("photoUrl") or "").strip()]
    if not targets:
        return 0
    n = 0
    with tempfile.TemporaryDirectory(prefix="intake_photo_") as tmp:
        for r in targets:
            reg = str(r.get("regId") or "접수")
            p = _download_photo(r["photoUrl"], Path(tmp), reg)
            if not p:
                continue
            cat = str(r.get("category") or "").strip()
            content = " ".join(str(r.get("content") or "").split())
            caption = f"📷 {reg} · [{cat}]" + (f"\n{content}" if content else "")
            if _send_kakao(room, caption, image=p):
                n += 1
    return n


def _send_kakao(room: str, text: str, image: Path | None = None) -> bool:
    """카톡 발신 관문(kakao_report_sender)을 그대로 탄다 — 새 발신 경로를 만들지 않는다(L21).

    ★승인 가드 보류는 한 번 다시 시도한다 (GM 지적 2026-08-29 · 실무진 알림 2회 유실).
      2026-08-29 16:11·16:56 두 번, 이 경로가 「보류: 웰리_승인_필요」로 막혀 접수 알림이
      실무진에게 안 갔다. --sender 는 아래대로 정확히 붙어 나가고(인자 실측 확인), 같은 인자·
      같은 환경으로 손으로 부르면 그때도 지금도 통과한다 — **재현이 안 된다.** 원인을 모르는
      채 판정 로직을 손대면 가드가 헛돌 수 있으므로, 여기서는 두 가지만 한다:
        ① 보류로 막히면 5초 뒤 한 번 더 보낸다 — 사람에게 갈 것이 조용히 사라지지 않게.
        ② 실패하면 관문이 낸 출력을 통째로 남긴다 — 종전엔 마지막 한 줄만 남아
           「보류」라는 결과만 보이고 어느 발신 주체로 거부됐는지가 로그에 없었다.
           다음 발생 때 [gate] 줄이 남으면 그 자리에서 원인이 확정된다.
    """
    import subprocess  # noqa: PLC0415
    args = (["--image", str(image), "--caption", text] if image else ["--message", text])

    def _once() -> tuple[int, str]:
        proc = subprocess.run(
            # --sender 접수전달 — room 이 사람 방(★부서장·★운영+시설+지원+주차 등)일 때 가드(약속
            # L24) 통과용. room 이 사람 방이 아니면 가드가 무시하는 값이라 항상 붙여도 무해하다.
            [sys.executable, "-u", str(SCRIPTS_DIR / "kakao_report_sender.py"),
             *args, "--only-room", room, "--sender", "접수전달"],
            cwd=str(REPO_ROOT), capture_output=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        return proc.returncode, (proc.stdout or b"").decode("utf-8", "replace").strip()

    rc, out = _once()
    if rc != 0 and "웰리_승인_필요" in out:
        print(f"[intake-relay] 승인 가드 보류 — 5초 뒤 재시도({room})\n{out}", flush=True)
        time.sleep(5)
        rc, out = _once()
    if rc != 0:
        print(f"[intake-relay] 카톡 발송 실패({room}) — 관문 출력 전문:\n{out or 'no output'}", flush=True)
    return rc == 0


def run_intake_relay(dry_run: bool = True, test: bool = False) -> list[str]:
    """새 접수를 부서별로 묶어 **목적지 방마다 한 통씩** 카톡 방에 전달(GM 확정 2026-08-15,
    합본 지시 2026-08-15 후속).

    부서별로 나누는 이유 = 그 부서가 자기 것만 보고 바로 조치하라는 GM 지시(배627). 단,
    같은 방으로 갈 부서가 여럿이면(예: 시설부·운영부 둘 다 ★운영+시설+지원+주차) 한 통 안에서
    부서 소제목(🏢)으로만 가른다 — 제목 동일한 메시지가 연달아 뜨는 것을 막는다(중복 알림
    정리 2026-08-15, 실측 8/15 11:56 2통). 새 접수가 없는 방은 아무것도 보내지 않는다.
    ▸test=True면 실무진 방 대신 텔레그램 업무관리방으로만 보낸다(GM 확정 — 테스트는 늘 그 방).
    """
    # [2026-08-29 GM 지시 · 카톡 중복 정리 ⑦] 밤 22시~아침 7시엔 즉시 전달을 쉬고 다음 날
    # 아침 회차로 미룬다(실무진 취침 시간 발신 금지). 커서(reception_seen_new_ids)는 실제
    # 발송 후에만 전진하므로 밤 사이 접수는 사라지지 않고 아침 첫 회차에 그대로 나간다.
    if not (dry_run or test) and not (7 <= datetime.now().hour < 22):
        return []
    rows = _fetch_rows()
    if rows is None:
        return []
    state = _load_completion_state()
    if not state.get("intake_relay_enabled") and not (dry_run or test):
        return []
    seen = set(state.get("reception_seen_new_ids") or [])
    depts = sorted({str(r.get("dept") or "").strip() or "부서 미정" for r in rows
                    if str(r.get("regId") or "") and str(r["regId"]) not in seen})
    if not depts:
        return []

    # 2026-08-15 GM 지시(중복 알림 정리) — 같은 방으로 갈 부서가 여럿이면 한 통에 묶는다.
    #   실측: 8/15 11:56 ★운영+시설+지원+주차 에 제목 동일 2통(시설부 1건·운영부 1건)이
    #   따로 나갔다. _intake_relay_block 이 이미 부서별 소제목(🏢 …)으로 나눠 렌더하므로,
    #   부서 단위 대신 **목적지 방 단위**로 rows 를 묶어 방마다 한 통만 보낸다(내용 그대로,
    #   묶는 순서만 바꿈).
    by_room: dict[str, list[str]] = {}
    for dept in depts:
        by_room.setdefault(_intake_room_for(dept), []).append(dept)

    sent: list[str] = []
    for room, room_depts in by_room.items():
        sub = [r for r in rows if (str(r.get("dept") or "").strip() or "부서 미정") in room_depts]
        text = _intake_relay_block(sub, state={"intake_relay_enabled": True,
                                               "reception_seen_new_ids": sorted(seen)},
                                   persist=False, force=True)
        if not text:
            continue
        new_sub = [r for r in sub if str(r.get("regId") or "") and str(r["regId"]) not in seen]
        if dry_run:
            _pn = sum(1 for r in new_sub if str(r.get("photoUrl") or "").strip())
            print(f"[intake-relay] DRY-RUN {room_depts} → {room} (사진 {_pn}장)\n{text}\n", flush=True)
            sent.extend(room_depts)
        elif test:
            token = _load_env_val("TELEGRAM_BOT_TOKEN")
            if token and tg_send(token, TEST_CHAT_ID, f"🧪 [테스트] {room_depts} → 실제로는 {room} 방\n\n{text}",
                                 source="report_stream_2b_intake_relay_test"):
                sent.extend(room_depts)
        elif _send_kakao(room, text):
            sent.extend(room_depts)
            # 글이 나간 뒤에만 사진을 잇는다 — 사진이 실패해도 접수 전달 자체는 이미 갔다.
            _n = _send_intake_photos(room, new_sub)
            if _n:
                print(f"[intake-relay] {room} 사진 {_n}장 첨부", flush=True)
    # 커서는 **전부 보낸 뒤에만** 전진한다(완료 통보와 같은 규칙 — 중간에 실패하면 다음
    # 회차에 다시 나간다. 잃는 것보다 겹치는 게 낫다). 테스트 발신은 커서를 건드리지 않는다.
    if not dry_run and not test and sent:
        state["reception_seen_new_ids"] = sorted(
            {str(r["regId"]) for r in rows if str(r.get("regId") or "")})
        _save_completion_state(state)
    return sent


def build_digest(today: str | None = None, persist_completion: bool = True) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    weekday = _WEEKDAY_KOR[datetime.strptime(today, "%Y-%m-%d").weekday()]
    # 보낸이를 밝힌다(2026-07-31 GM 지시 "웰리가 보냈다는 것도 인지시켜야 하고").
    # 실무진 방에 뜨는 메시지가 누가 보낸 것인지 모르면 답할 곳도 모른다.
    header = (f"🌙 하루의 마무리 — 접수 {today}({weekday})\n📮 종합접수 현황\n"
              "— 웰페리온 AI 운영지원 '웰리'가 정리해 보내드립니다.")
    rows = _fetch_rows()
    if rows is None:
        return f"{header}\n\n조회 실패 (GAS 응답 없음)"
    _write_reception_watch(rows)
    # 2026-07-31 GM 지시 — 점수판을 맨 위로 올린다.
    #   "점수 랭킹하는 걸 상단에 알림으로 올려주고, 더 활성화될 수 있게."
    #   맨 아래에 있으면 스크롤 끝까지 내려야 보인다 = 사실상 없는 것과 같았다. 접수를 피할
    #   이유를 없애려고 만든 장치라, 방을 열자마자 눈에 들어와야 제 일을 한다.
    score = _score_block()
    parts = [header]
    if score:
        parts.append(score.lstrip("\n").removeprefix(_DIVIDER).strip())
    score4 = _score4_block(rows)
    if score4:
        parts.append(score4.lstrip("\n").removeprefix(_DIVIDER).strip())
    parts.append(f"{_DIVIDER}\n{_today_section(rows, today)}")
    parts.append(f"{_DIVIDER}\n{_aging_block(rows)}")
    completion = _completion_block(rows, persist=persist_completion)
    if completion:
        parts.append(completion)
    # 14일 미완 확정건 운영부 이관 — 실제 쓰기는 이 다이제스트가 진짜 나갈 때만
    # (persist_completion=not dry_run 과 같은 게이트, run() 참고). dry-run·수동 조회는 절대 안 쓴다.
    apply_overdue_escalation(rows, dry_run=not persist_completion)
    return "\n\n".join(parts)


# ── 카카오 ★운영+시설+지원+주차 압축본 (2026-08-18 GM 결정 · 배670) ────────────────
# 미처리 적체 부서별 전체 목록(약 40줄)을 매일 재발신하던 것을 총건수+가장 오래된 3건+
# 링크로 줄인다. 판정은 _collect_overdue 그대로 재사용(약속 L01) — 텔레그램(_aging_block)
# 과 같은 숫자를 쓴다.
def build_kakao_digest(today: str | None = None) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    rows = _fetch_rows()
    if rows is None:
        return "📮 접수 — 조회 실패"

    today_rows = [r for r in rows if str(r.get("createdAt", "")).startswith(today)]
    cat_cnt: dict[str, int] = {}
    for r in today_rows:
        cat = str(r.get("category") or "기타").strip()
        cat_cnt[cat] = cat_cnt.get(cat, 0) + 1
    cat_str = "·".join(f"{c}{n}" for c, n in sorted(cat_cnt.items(), key=lambda x: -x[1]))

    undone = [r for r in rows if str(r.get("status", "")) != "완료"]
    overdue = _collect_overdue(rows, scope="ops")

    # [2026-08-29 GM 지시 · 카톡 중복 정리] 저녁은 건수·변동만 — 접수 원문 펼침은 아침
    # 4부서방 통(send_ops_digest._build_ovd_block) 한 곳뿐이다. 종전 「오래된 순 3건 전문」
    # (2026-08-27 지시분)은 아침 통과 같은 건을 하루 두 번 전문으로 싣는 중복이라 뺐다 —
    # 원문은 아침 통·종합접수처 화면에 그대로 있다(정보 손실 없음).
    # 변동(몇 건 → 몇 건)은 직전 회차 값을 상태파일에 적어 두고 대조한다(새 파일 없음).
    state = _load_completion_state()
    prev = state.get("kakao_digest_prev") or {}
    delta = ""
    if str(prev.get("date") or "") and str(prev["date"]) != today and isinstance(prev.get("undone"), int):
        delta = f" · 전회 {prev['undone']}건 → 오늘 {len(undone)}건"
    state["kakao_digest_prev"] = {"date": today, "undone": len(undone), "overdue": len(overdue)}
    _save_completion_state(state)

    line = f"📮 접수 — 오늘 {len(today_rows)}건" + (f"({cat_str})" if cat_str else "")
    line += f" · 미처리 {len(undone)}건" + (f"(기한 지난 {len(overdue)}건)" if overdue else "")
    line += delta
    lines = [line]
    # 탭 없는 단일 보드라 해시 딥링크가 없다 — 카톡이 ?쿼리를 자르므로 필터 파라미터도
    # 못 쓴다(2026-07-15 실측). 대신 화면 안 어디를 보면 되는지 한 줄로 안내한다
    # (STATUS_LIST=['접수','처리중','완료'] 순서라 맨 왼쪽 칸이 미처리 · 배670 후속 2026-08-20).
    lines.append(f"👉 전체 목록: {DASHBOARD_URL} → 맨 왼쪽 「접수」칸이 미처리 목록")
    return "\n".join(lines)


def build_lesson_digest(today: str | None = None) -> str:
    """★부서장 방 몫 — 강습·업장(팀) 기한초과분만. 없으면 빈 문자열(발신 안 함).

    GM 지시 2026-08-18: '강습부건은 부서장방에, 시설부/운영부/지원부건은
    ★운영+시설+지원+주차 방에'. 종전에는 전 부서가 한 방으로만 나가서 P.T팀·수영팀
    건이 강습 담당이 안 보는 방에 섞여 있었다(2026-08-19 웰리 실측 · 배696).
    같은 목록을 두 방에 통째로 보내지 않는다 — 방마다 자기 몫만 간다.
    """
    today = today or datetime.now().strftime("%Y-%m-%d")
    rows = _fetch_rows()
    if rows is None:
        return ""
    body = _aging_block(rows, scope="lesson")
    if "기한 초과 건 없음" in body:
        return ""      # 조용히 넘어간다 — 없는 날 매일 뜨면 소음이다
    weekday = _WEEKDAY_KOR[datetime.strptime(today, "%Y-%m-%d").weekday()]
    return (f"🌙 하루의 마무리 — 접수 {today}({weekday})\n📮 강습·업장 접수 현황\n"
            "— 웰페리온 AI 운영지원 '웰리'가 정리해 보내드립니다.\n\n" + body)


def seed_completion_cursor() -> int:
    """처리완료 통보를 켜기(enabled:true) 직전 1회 실행 — 지금 이미 '완료'인 건 전부를
    커서에 채워 넣어, 켜는 첫 회차에 오래된 완료건(현재 실측 43건)이 한꺼번에 '신규
    완료'로 통보되는 것을 막는다(활성화 당일 백로그 통보 방지 — 진짜 새 완료건만
    그 다음부터 나간다). enabled 값 자체는 건드리지 않는다(그건 GM go 별도 승인)."""
    rows = _fetch_rows() or []
    state = _load_completion_state()
    done_ids = {str(r["regId"]) for r in rows
                if str(r.get("status", "")) == "완료" and str(r.get("regId") or "")}
    state["reception_seen_done_ids"] = sorted(done_ids)
    # 접수 즉시 전달 커서도 같은 자리에서 채운다(배627) — 안 채우면 켜는 첫 회차에 기존
    # 접수 전건(실측 100건)이 '새 접수'로 한꺼번에 나간다. 완료 통보와 같은 함정이라 같이 막는다.
    state["reception_seen_new_ids"] = sorted(
        {str(r["regId"]) for r in rows if str(r.get("regId") or "")})
    _save_completion_state(state)
    return len(done_ids)


def run(today: str | None = None, dry_run: bool = True) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    text = build_digest(today, persist_completion=not dry_run)
    if dry_run:
        print(f"[stream2b] DRY-RUN — chat_id={TELEGRAM_CHAT_ID} 발송 안 함", flush=True)
        return text
    token = _load_env_val("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[stream2b] TELEGRAM_BOT_TOKEN 미설정", flush=True)
        return text
    # 전역 페이싱·429 재시도·로깅 = tg_outbound_log.send() 경유(플러드 방어, 개별 requests 금지).
    if _urgent_only_enabled("reception") and not _looks_urgent(text):
        print(f"[stream2b] 텔레그램 SKIP — 급할 때만 모드·이상 신호 없음", flush=True)
        return text
    ok = tg_send(token, TELEGRAM_CHAT_ID, text, source="report_stream_2b_reception")
    print(f"[stream2b] 텔레그램 {'완료' if ok else '실패'} → {TELEGRAM_CHAT_ID}", flush=True)
    if ok:
        commit_completion_cursor()   # 실제로 나간 뒤에만 커서 전진(실패 시 다음 회차 재통보)
    return text


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="스트림 #2b 종합접수 현황+미처리 적체 리마인드 보고")
    p.add_argument("--live", action="store_true", help="실발송")
    p.add_argument("--today", default=None, help="날짜 YYYY-MM-DD (기본=오늘)")
    p.add_argument("--seed-completion", action="store_true",
                    help="처리완료 통보 커서 시딩(enabled:true 켜기 직전 1회 — 백로그 통보 방지)")
    p.add_argument("--intake-relay", action="store_true",
                    help="새 접수를 부서별 카톡 방에 전달(기본 드라이런 · --live 실발송 · --test 텔레그램 업무관리방)")
    p.add_argument("--test", action="store_true",
                    help="테스트 발신 — 실무진 방 대신 텔레그램 업무관리방으로만 보낸다")
    p.add_argument("--backfill", action="store_true",
                    help="과거 완료건 완료일 복원(메모·발신로그·통보스냅샷 3근거 · 실측 보존)")
    p.add_argument("--selftest", action="store_true",
                    help="접수 처리 점수제 4규칙 경계값 자체 점검(쓰기 없음)")
    a = p.parse_args()
    if a.selftest:
        _selfcheck_score_rule()
        print("[selftest] 점수제 4규칙 경계값 OK")
        sys.exit(0)
    if a.backfill:
        _rows = _fetch_rows() or []
        _rep = backfill_first_done_at(_rows, today=a.today)
        _write_reception_watch(_rows)
        _w = json.loads(RECEPTION_WATCH_PATH.read_text(encoding="utf-8"))
        print(f"[backfill] 완료 {_rep['rows_done']}건 근거별 {_rep['by_src']}")
        print(json.dumps(_w.get("processing_days"), ensure_ascii=False, indent=2))
        sys.exit(0)
    if a.intake_relay:
        _mode = "테스트발송" if a.test else ("발송" if a.live else "렌더")
        _sent = run_intake_relay(dry_run=not (a.live or a.test), test=a.test)
        print(f"[intake-relay] {_mode} {len(_sent)}개 부서 — {_sent or '새 접수 없음'}")
        sys.exit(0)
    if a.seed_completion:
        n = seed_completion_cursor()
        print(f"[stream2b] 완료 커서 시딩 완료 — 현재 완료 {n}건을 '이미 통보됨'으로 표시")
        sys.exit(0)
    result = run(today=a.today, dry_run=not a.live)
    print("\n=== 렌더 ===")
    print(result)
