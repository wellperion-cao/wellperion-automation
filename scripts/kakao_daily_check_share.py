#!/usr/bin/env python3
"""일일 점검 현황 공유 — 매일 23:00 카톡 '웰페리온 운영+시설+지원' 방 자동 발송 (kakao_daily_check_share.py)

GM 지시(2026-07-09, 오늘 23시 발효). 하루 점검 현황을 실데이터로 정리해
'개선을 유도'하는 톤으로 공유한다 — 미흡/미체크/이슈/기준이탈을 앞쪽에 짚고
마무리에 수고·감사 문구. '최종 정리'가 아니라 '현황 공유'가 제목·목적.

데이터 소스(점검 GAS · CHECK_API · 실측·지어내기 0):
  - 지원부: ?action=today_live&dept=support
      → done/total/pct · uncheckedByShift(미체크 회차×성별 항목명) · allIssues(이슈)
  - 시설부 회수·시각: ?action=board&key=FACILITY_CHECK_YYYY-MM-DD
      → board.store.submissions(리스트) = 실제 제출 회수(페이지 'N회 완료'와 일치·오늘 키라 stale 아님).
      각 submission의 seq·startHHMM·endHHMM·inspector로 회수·시각·점검자를 표출한다.
      (monthly의 sessionCount는 '라운드종류=1 고정'이라 항상 1 → 회수로 쓰지 않는다, GM 2026-07-15)
  - 시설부 기준이탈: ?action=monthly_report&dept=facility&month=YYYY-MM
      → outOfRange.list에서 오늘 날짜 항목(name/value/min/max)만 필터.
      작업사항/지시사항: facility today_live 응답에 있으면 포함, 없으면 정직히 생략.
  - 주차: weekly/monthly 데이터 있으면 포함, 없으면 '자체점검 준비 중' 정직 표기.
  값이 없으면 그 줄을 생략(지어내기 금지).

카톡 발송(재사용):
  scripts/kakao_report_sender.py 의 텍스트 전송을 subprocess로 호출:
    python scripts/kakao_report_sender.py --message "<본문>" --only-room "웰페리온 운영+시설+지원"
  --dry-run 시 렌더 본문만 출력하고 발송 스크립트를 호출하지 않는다.

절대 제약:
  - 발송 대상 방 = '웰페리온 운영+시설+지원' 하나뿐(--only-room 고정). 다른 방·회장님방 금지.
  - GAS 조회 실패해도 크래시 금지(부분 정보라도 발송 or 정직 안내).

사용법:
  python scripts/kakao_daily_check_share.py --dry-run   # 본문 렌더만(카톡 미발송)
  python scripts/kakao_daily_check_share.py             # 실발송(23:00 예약 진입점)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Windows 콘솔(cp949) 한글 깨짐 방지
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SENDER = ROOT / "scripts" / "kakao_report_sender.py"

# 점검 GAS(CHECK_API · monthly_check_report.py와 동일 배포 URL)
GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec"
)

# 발송 대상 방(단일·고정 — 절대 다른 방 금지)
TARGET_ROOM = "★운영+시설+지원+주차"

_DOW_KO = ["월", "화", "수", "목", "금", "토", "일"]
_SHIFT_KO = {"am": "오전", "pm": "오후", "close": "마감", "night": "야간"}
_GENDER_KO = {"m": "남", "f": "여"}

MAX_OUT_OF_RANGE = 6      # 기준이탈 표시 최대 줄
MAX_UNCHECKED = 6         # 미체크 항목 표시 최대 개수
MAX_ISSUES = 3            # 이슈 표시 최대 개수
MAX_FACILITY_DETAIL = 4   # 시설부 회차별 시각을 한 줄씩 상세 표시할 최대 회수(초과 시 콤팩트 나열)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _fmt_num(n) -> str:
    """정수면 '32', 소수면 '32.2' (%g 스타일 — 불필요한 .0 제거)."""
    try:
        f = float(n)
    except (TypeError, ValueError):
        return str(n)
    return str(int(f)) if f.is_integer() else str(f)


def fetch_gas(params: dict, timeout: float = 20.0) -> dict | None:
    """GAS GET 호출 → dict(ok=true)만 반환. 실패·ok=false는 None(정직 — 지어내기 금지)."""
    url = GAS_URL + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        log(f"[GAS] 조회 실패({params}): {type(e).__name__}: {e}")
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        log(f"[GAS] 응답 ok=false({params}): {str(data)[:200]}")
        return None
    return data


# ══════════════════════════════════════════════════════════════════════════
#  섹션 빌더 — 각 부서 데이터 dict → 카톡 본문 라인 리스트(값 없으면 빈 리스트)
# ══════════════════════════════════════════════════════════════════════════
def _fetch_facility_board(today: str) -> dict:
    """시설부 오늘 board 한 번 호출 → 실제 제출 회수·각 회차 시각·점검자.
    daily_scheduler.py::_fetch_facility_board와 동일 패턴(?action=board&key=FACILITY_CHECK_{today}).
    회수 = len(board.store.submissions) — monthly sessionCount(라운드종류=1 고정, 항상 1)가 아닌
    실제 제출 건수(페이지 'N회 완료'와 일치·오늘 키라 stale 없음, GM 2026-07-15).
    반환: {"sessions": int, "submissions": list}."""
    out = {"sessions": 0, "submissions": []}
    data = fetch_gas({"action": "board", "key": f"FACILITY_CHECK_{today}"})
    if not isinstance(data, dict):
        return out
    store = ((data.get("board") or {}).get("store") or {})
    subs = store.get("submissions")
    if isinstance(subs, list):
        out["submissions"] = subs
        out["sessions"] = len(subs)
    return out


def build_facility_lines(today: str) -> tuple[list[str], dict]:
    """시설부: board에서 실제 회수·회차별 시각(정직 소스) + monthly outOfRange로 기준이탈.
    GM 2026-07-13 결정(이벤트 중심 — 회수·이상 유무 중심, % 부차) + GM 2026-07-15 회수·시각 정직화.
    today_live로 작업/지시 있으면 덧붙임."""
    filled = {"facility_status": False, "facility_outofrange": 0, "facility_worknote": False}

    # 회수·시각·점검자 = board 실데이터(정본)
    board = _fetch_facility_board(today)
    sessions = board["sessions"]

    # 기준이탈(오늘분만) = monthly_report outOfRange.list(항목·값·기준). 회수 소스와 분리.
    month = today[:7]
    monthly = fetch_gas({"action": "monthly_report", "dept": "facility", "month": month})
    today_oor = []
    if isinstance(monthly, dict):
        oor = ((monthly.get("outOfRange") or {}).get("list")) or []
        today_oor = [x for x in oor if str(x.get("date")) == today]
    filled["facility_outofrange"] = len(today_oor)

    lines: list[str] = []
    if sessions:
        filled["facility_status"] = True
        ooc_n = len(today_oor)
        head = f"🏗 시설부 {sessions}회 점검"
        head += f" · 이상 {ooc_n}건" if ooc_n else " · 이상 없음"
        lines.append(head)

        # 회차별 시각·점검자 — seq 순. 회수 많으면(초과 시) 시각만 콤팩트 나열(모바일 가독성).
        subs = sorted(board["submissions"], key=lambda s: (s.get("seq") or 0))
        if sessions <= MAX_FACILITY_DETAIL:
            for i, s in enumerate(subs, 1):
                seq = s.get("seq") or i
                st = str(s.get("startHHMM") or "").strip()
                en = str(s.get("endHHMM") or "").strip()
                insp = str(s.get("inspector") or "").strip()
                span = f"{st}~{en}" if st and en else (st or en or "시각미상")
                insp_s = f" ({insp})" if insp else ""
                lines.append(f"  · {seq}회 {span}{insp_s}")
        else:
            times = [str(s.get("startHHMM") or "").strip() for s in subs
                     if str(s.get("startHHMM") or "").strip()]
            insps = list(dict.fromkeys(
                str(s.get("inspector") or "").strip() for s in subs
                if str(s.get("inspector") or "").strip()))
            insp_s = f" · {', '.join(insps)}" if insps else ""
            lines.append("  · 점검 시각: " + "·".join(times) + insp_s)
    else:
        lines.append("🏗 시설부: 오늘 점검 입력 없음")

    # 기준이탈 상세(오늘분만) — 개선 필요
    if today_oor:
        lines.append(f"⚠ 기준이탈 {len(today_oor)}건 (개선 필요)")
        for x in today_oor[:MAX_OUT_OF_RANGE]:
            name = str(x.get("name", "")).split("(")[0].strip() or str(x.get("name", ""))
            val = _fmt_num(x.get("value"))
            lo, hi = _fmt_num(x.get("min")), _fmt_num(x.get("max"))
            lines.append(f"  · {name} {val} (기준 {lo}~{hi})")
        if len(today_oor) > MAX_OUT_OF_RANGE:
            lines.append(f"  · 외 {len(today_oor) - MAX_OUT_OF_RANGE}건")

    # 작업/지시사항 — facility today_live 응답에 있으면 포함(현재 미가동 시 자동 생략)
    tl = fetch_gas({"action": "today_live", "dept": "facility"})
    if isinstance(tl, dict):
        notes = []
        for key in ("worknote", "workNote", "작업사항", "instruction", "지시사항"):
            v = tl.get(key)
            if isinstance(v, str) and v.strip():
                notes.append(v.strip())
        if notes:
            filled["facility_worknote"] = True
            lines.append("📝 작업/지시: " + " / ".join(notes[:3]))

    return (lines, filled)


def build_support_lines() -> tuple[list[str], dict]:
    """지원부: today_live done/total/pct + 미체크(uncheckedByShift) + 이슈(allIssues)."""
    data = fetch_gas({"action": "today_live", "dept": "support"})
    filled = {"support_status": False, "support_unchecked": 0, "support_issues": 0}
    if data is None:
        return (["🛠 지원부: 데이터 조회 실패(정직 표기)"], filled)

    lines: list[str] = []
    total = data.get("total")
    if isinstance(total, (int, float)) and total:
        filled["support_status"] = True
        lines.append(f"🛠 지원부 {data.get('done', 0)}/{total}({data.get('pct', 0)}%)")
    else:
        lines.append("🛠 지원부: 오늘 점검 입력 없음")

    # 미체크 항목(회차×성별) 평탄화 — 개선 유도
    unchecked = data.get("uncheckedByShift") or {}
    flat: list[str] = []
    for shift, by_gender in unchecked.items():
        if not isinstance(by_gender, dict):
            continue
        shift_ko = _SHIFT_KO.get(shift, shift)
        for gender, items in by_gender.items():
            g_ko = _GENDER_KO.get(gender, gender)
            for it in (items or []):
                flat.append(f"[{shift_ko}{g_ko}] {it}")
    filled["support_unchecked"] = len(flat)
    if flat:
        shown = flat[:MAX_UNCHECKED]
        tail = f" 외 {len(flat) - MAX_UNCHECKED}건" if len(flat) > MAX_UNCHECKED else ""
        lines.append(f"❗ 미체크 {len(flat)}건 — " + ", ".join(shown) + tail)

    # 이슈 요약(allIssues)
    issues = data.get("allIssues") or []
    filled["support_issues"] = len(issues)
    if issues:
        lines.append(f"🗒 이슈 {len(issues)}건")
        for x in issues[:MAX_ISSUES]:
            txt = " ".join(str(x.get("issue", "")).split()).strip()
            if len(txt) > 40:
                txt = txt[:40] + "…"
            by = str(x.get("by", "")).strip()
            by_s = f" ({by})" if by else ""
            lines.append(f"  · {txt}{by_s}")
        if len(issues) > MAX_ISSUES:
            lines.append(f"  · 외 {len(issues) - MAX_ISSUES}건")

    return (lines, filled)


def build_parking_lines(today: str) -> tuple[list[str], dict]:
    """주차: weekly에서 오늘 행 데이터 있으면 포함, 없으면 '자체점검 준비 중' 정직 표기."""
    filled = {"parking": False}
    data = fetch_gas({"action": "weekly", "dept": "parking"})
    if isinstance(data, dict):
        for d in data.get("data") or []:
            if str(d.get("date")) == today and isinstance(d.get("total"), (int, float)) and d.get("total"):
                filled["parking"] = True
                return ([f"🅿 주차 {d.get('done', 0)}/{d.get('total')}({d.get('pct', 0)}%)"], filled)
    return (["🅿 주차: 자체점검 준비 중"], filled)


# ══════════════════════════════════════════════════════════════════════════
#  본문 조립
# ══════════════════════════════════════════════════════════════════════════
def build_body(now: datetime | None = None) -> tuple[str, dict]:
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    title_date = f"{now.strftime('%m-%d')}({_DOW_KO[now.weekday()]})"
    bar = "━" * 12

    fac_lines, fac_fill = build_facility_lines(today)
    sup_lines, sup_fill = build_support_lines()
    par_lines, par_fill = build_parking_lines(today)

    body_lines = [f"📋 일일 점검 현황 공유 — {title_date}", bar]
    body_lines += fac_lines
    body_lines += sup_lines
    body_lines += par_lines
    body_lines += [bar, "오늘도 수고 많으셨습니다. 감사합니다 🙏"]

    filled = {**fac_fill, **sup_fill, **par_fill}
    return ("\n".join(body_lines), filled)


# ══════════════════════════════════════════════════════════════════════════
#  발송(kakao_report_sender.py 텍스트 전송 재사용)
# ══════════════════════════════════════════════════════════════════════════
# 카톡 실행파일(무인 발송 신뢰성 — env로 오버라이드 가능)
KAKAO_EXE = os.environ.get(
    "KAKAOTALK_EXE", r"C:\Program Files (x86)\Kakao\KakaoTalk\KakaoTalk.exe"
)


def ensure_kakao_foreground(wait: float = 6.0) -> None:
    """무인 발송 전 카톡 메인창 띄우기 — 2026-07-13 밤 실패 원인(앱이 트레이로 내려가
    'kakao 메인창 못 찾음') 방지. KakaoTalk은 단일 인스턴스라 exe를 다시 실행하면 이미
    떠 있는 인스턴스의 메인창이 앞으로 나온다. 실패해도 발송은 계속(비치명)."""
    try:
        if not os.path.exists(KAKAO_EXE):
            log(f"[kakao] 실행파일 없음({KAKAO_EXE}) — 자동 띄우기 생략(설치경로 확인 필요)")
            return
        subprocess.Popen([KAKAO_EXE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"[kakao] 메인창 자동 띄우기 시도(무인 신뢰성) — {wait:.0f}s 대기")
        time.sleep(wait)
    except Exception as e:
        log(f"[kakao] 자동 띄우기 실패(무시하고 발송 시도): {type(e).__name__}: {e}")


def send_via_kakao(body: str, dry_run: bool) -> int:
    """kakao_report_sender.py --message ... --only-room TARGET_ROOM 호출(단일 방 고정)."""
    if not dry_run:
        ensure_kakao_foreground()  # 무인 발송 신뢰성 — 발송 직전 카톡 메인창 확보
    cmd = [
        sys.executable, str(SENDER),
        "--message", body,
        "--only-room", TARGET_ROOM,
    ]
    if dry_run:
        cmd.append("--dry-run")
    log(f"[send] 호출: {sys.executable} {SENDER.name} --message <본문> --only-room {TARGET_ROOM!r}"
        f"{' --dry-run' if dry_run else ''}")
    try:
        proc = subprocess.run(cmd, timeout=300)
        return proc.returncode
    except Exception as e:
        log(f"[send] 발송 스크립트 호출 실패: {type(e).__name__}: {e}")
        return 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="일일 점검 현황 공유 — 카톡 '웰페리온 운영+시설+지원' 방 자동 발송")
    ap.add_argument("--dry-run", action="store_true",
                    help="본문 렌더만 출력(카톡 미발송·발송 스크립트 미호출)")
    args = ap.parse_args()

    log("일일 점검 현황 공유 시작 — GAS 조회...")
    body, filled = build_body()

    print("\n" + "=" * 60)
    print(body)
    print("=" * 60 + "\n")
    log(f"[데이터] 채워진 필드: {filled}")

    if args.dry_run:
        log("DRY-RUN: 본문 렌더만 완료 — 카톡 미발송(발송 스크립트 미호출).")
        print("DONE: DRY-RUN 렌더 완료(카톡 미발송)")
        return 0

    rc = send_via_kakao(body, dry_run=False)
    if rc == 0:
        print(f"DONE: 카톡 '{TARGET_ROOM}' 방 발송 완료")
        return 0
    print(f"BLOCKED: 카톡 발송 실패(rc={rc}) — 본문은 위에 렌더됨")
    return 1


if __name__ == "__main__":
    sys.exit(main())
