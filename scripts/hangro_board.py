#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/hangro_board.py — 🧭 오늘의 항로 보드 자동 생성기 (2026-06-07)

입력:
  - GAS todo_list API (GM·AI C레벨 배만 — 실무진 제외)
  - status/_queue.json (AI C레벨 진행배)

엔진:
  - scripts/ship_classify.py 재사용 (무게 이모지 + has_clevel_id)

출력:
  - 터미널 텍스트 (웰리 '현황' 시 그대로 사용 · 텔레그램 호환)
  - --json 플래그: JSON도 추가 출력

사용:
  python scripts/hangro_board.py
  python scripts/hangro_board.py --json
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# ── 경로 설정 ─────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent           # scripts/
_REPO = _HERE.parent                              # welperion-automation/
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from ship_classify import classify_ship, has_clevel_id  # noqa: E402

# stdout 한글 안전 처리 (Windows CP949 대응)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 상수 ──────────────────────────────────────────────────────────────────
GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)
QUEUE_PATH = _REPO / "status" / "_queue.json"

# 상태 아이콘 — 상수로 분리해 한 줄로 교체 가능
STATUS_ICON = {
    "완료":   "⚓",   # 입항
    "DONE":   "⚓",
    "진행중": "🌊",   # 진행
    "IN_PROGRESS": "🌊",
    "대기":   "대기중",
    "PENDING": "대기중",
    "보류":   "⏸",
    "ON_HOLD": "⏸",
}
STATUS_DONE  = {"완료", "DONE", "폐기"}
STATUS_OPEN  = {"진행중", "대기", "IN_PROGRESS", "PENDING", "보류", "ON_HOLD"}

# ── G1 오너 필터 (G1 규칙 재사용) ─────────────────────────────────────────
def _is_g1_owner(owner: str) -> bool:
    o = str(owner)
    if "김남욱GM" in o:
        return True
    if any(x in o for x in ["웰리", "시모", "시토", "시우", "시뽀", "시포", "시로"]):
        return True
    if any(x in o for x in ["AI CEO", "AI CMO", "AI CTO", "AI COO", "AI CFO", "AI CPO", "AI CHRO"]):
        return True
    return False


# ── 날짜 유틸 ──────────────────────────────────────────────────────────────
def _to_kst_date(v: str) -> str:
    """GAS ISO datetime → KST YYYY-MM-DD (off-by-one 없이)."""
    if not v:
        return ""
    s = str(v)
    if len(s) == 10 and s[4] == "-":
        return s
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        kst = d + dt.timedelta(hours=9)
        return kst.strftime("%Y-%m-%d")
    except Exception:
        return s[:10]


def _days_left(date_str: str) -> int | None:
    if not date_str or len(date_str) < 10:
        return None
    try:
        d = dt.datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (d - dt.date.today()).days
    except ValueError:
        return None


# ── 결재 '다음 서명자' 판정 — 결재현황 SSOT nextApprover와 1:1 동일 (2026-06-07 웰리) ──
_DEPT_HEADS = ["이경연 실장", "이정헌 소장", "나우열M"]
_CAT_DEPT_HEAD = {
    "[1] 매출 및 영업": "이경연 실장",
    "[3] 운영 정책": "이경연 실장",
    "[4] 시설 및 환경": "이정헌 소장",
    "[2] 인사 & 파트너": "나우열M",
}


def _next_approver(row: dict):
    """결재선의 '지금 서명할 차례' 반환('부서장'/'GM'/'대표님'/None)."""
    approval = [s.strip() for s in str(row.get("결재요청", "")).split(",") if s.strip()]
    if not approval:
        return None
    owners = [s.strip() for s in str(row.get("담당자", "")).split(",")]
    owner_is_gm = "김남욱GM" in owners
    mid = next((m for m in approval if m in _DEPT_HEADS), None) \
        or next((o for o in owners if o in _DEPT_HEADS), None) \
        or _CAT_DEPT_HEAD.get(str(row.get("카테고리", "")), "")
    mid_explicit = bool(mid) and mid in approval
    skip_mid = bool(mid) and mid in owners and not mid_explicit
    route = []
    if mid and not owner_is_gm and not skip_mid:
        route.append("부서장")
    if not owner_is_gm:
        route.append("GM")
    route.append("대표님")
    sign = {"부서장": row.get("부서장싸인"), "GM": row.get("GM싸인"), "대표님": row.get("대표싸인")}
    for r in route:
        if not sign.get(r):
            return r
    return None


# ── 데이터 fetch ───────────────────────────────────────────────────────────
def fetch_gas_items() -> list[dict]:
    """GAS todo_list → GM·AI C레벨 전체 항목(완료 포함)."""
    try:
        req = urllib.request.Request(GAS_URL + "?action=todo_list")
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        rows = data.get("data", [])
    except Exception as e:
        print(f"[WARN] GAS fetch 실패: {e}", file=sys.stderr)
        rows = []

    items = []
    for row in rows:
        owner = str(row.get("담당자", ""))
        if not _is_g1_owner(owner):
            continue
        title = str(row.get("업무명", "")).strip()
        if not title:
            continue
        st = str(row.get("상태", ""))
        end_raw = str(row.get("종료일", "") or "")
        end_kst = _to_kst_date(end_raw)
        # 결재요청 GM 여부 → 결재 섹션
        apr = str(row.get("결재상태", ""))
        # '지금 GM 차례'인 건만 결재 카운트 — SSOT nextApprover와 동일(결재요청=GM만 보면 오버카운트)
        needs_gm = bool(apr) and "반려" not in apr and apr != "결재완료" and _next_approver(row) == "GM"
        items.append({
            "id":        str(row.get("id", "")),
            "title":     title,
            "owner":     owner,
            "status":    st,
            "end_date":  end_kst,
            "mod_date":  _to_kst_date(str(row.get("수정일", "") or "")),
            "priority":  str(row.get("난이도", "") or "NORMAL"),
            "needs_gm_appr": needs_gm,
            "source":    "gas",
        })
    return items


def fetch_queue_items() -> list[dict]:
    """_queue.json → PENDING·IN_PROGRESS AI 배만 (DONE·폐기 제외)."""
    if not QUEUE_PATH.exists():
        return []
    try:
        rows = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] _queue.json 읽기 실패: {e}", file=sys.stderr)
        return []
    items = []
    for q in rows:
        st = str(q.get("status", ""))
        if "폐기" in st:
            continue
        if st.upper() not in {"PENDING", "IN_PROGRESS", "ON_HOLD", "DONE", "완료", "진행중", "대기"}:
            continue
        title = str(q.get("title", "")).strip()
        if not title:
            continue
        items.append({
            "id":       str(q.get("task_id", "")),
            "title":    title,
            "owner":    str(q.get("clevel", "")).upper(),
            "status":   st,
            "end_date": str(q.get("deadline") or ""),
            "mod_date": str(q.get("processed_at") or ""),
            "priority": str(q.get("priority", "NORMAL")),
            "needs_gm_appr": False,
            "source":   "queue",
        })
    return items


# ── 섹션 분류 ──────────────────────────────────────────────────────────────
def _is_recent(date_str: str, days: int = 3) -> bool:
    """완료일(수정일)이 KST 오늘~days일 전 이내인가. 입항 섹션 = 최근 완료만(일일 다이제스트, 주말 커버 3일).
    ※ G1 웹 대시보드는 30일 창(영구 보드) — 텔레그램 일일보고와 목적이 달라 창 크기 다름(의도)."""
    if not date_str:
        return False
    try:
        from datetime import datetime, timedelta
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        kst_today = (datetime.utcnow() + timedelta(hours=9)).date()
        delta = (kst_today - d).days
        return 0 <= delta <= days
    except Exception:
        return False


def _classify(items: list[dict]) -> dict[str, list[dict]]:
    sections: dict[str, list[dict]] = {
        "urgent":  [],   # 🔴 급한 입항 (마감임박 ≤3일, 미완료)
        "today":   [],   # 🧭 오늘의 항로 (진행·대기)
        "appr":    [],   # 🔴 GM 결재 대기
        "done":    [],   # ⚓ 입항 (완료)
        "drift":   [],   # 🌀 표류 (완료인데 담당 다음 없는 건 — 미구현, placeholder)
    }
    seen_ids: set[str] = set()

    for item in items:
        iid = item["id"]
        if iid in seen_ids:
            continue
        seen_ids.add(iid)

        st = item["status"]
        done = st in STATUS_DONE
        appr = item.get("needs_gm_appr", False)
        days = _days_left(item["end_date"])
        urgent_flag = (days is not None) and (0 <= days <= 3) and not done

        ship = classify_ship({
            "title":    item["title"],
            "priority": item["priority"],
            "deadline": item["end_date"],
        })
        item["_ship"] = ship

        if appr and not done:
            sections["appr"].append(item)
        elif urgent_flag:
            sections["urgent"].append(item)
        elif done:
            # 입항(완료)은 최근(오늘·어제) 완료만 — 옛 완료건은 이력이라 보드서 제외
            if _is_recent(item.get("mod_date", "")):
                sections["done"].append(item)
        else:
            sections["today"].append(item)

    # 무거운 배 먼저 정렬
    _rank = {"🛳️": 0, "⛴️": 1, "⛵": 2}
    for key in ("urgent", "today", "appr"):
        sections[key].sort(key=lambda x: _rank.get(x["_ship"]["icon"], 1))

    return sections


# ── 렌더 한 줄 ────────────────────────────────────────────────────────────
def _render_line(item: dict, show_status: bool = True) -> str:
    ship = item["_ship"]
    icon = ship["icon"]
    title = item["title"]
    owner = item["owner"]
    st    = item["status"]
    due   = item["end_date"][:10] if item["end_date"] else ""

    # 상태 아이콘
    st_icon = STATUS_ICON.get(st, STATUS_ICON.get(st.upper(), "?"))

    # 담당 suffix — 식별자 있으면 생략
    if has_clevel_id(title):
        owner_part = ""
    else:
        short = owner.replace("김남욱", "").replace("GM", "GM").strip() or owner[:6]
        owner_part = f" [{short}]" if short else ""

    badges = (" 🌟" if ship.get("northstar") else "") + (" 🔴" if ship.get("urgent") else "")
    due_part = f" ~{due[5:]}" if due else ""  # MM-DD만

    if show_status:
        return f"  {icon} {title}{owner_part}{badges}{due_part}  {st_icon}"
    return f"  {icon} {title}{owner_part}{badges}{due_part}"


# ── 박스표 ─────────────────────────────────────────────────────────────────
def _box_table(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    lw = max(len(r[0]) for r in rows)
    rw = max(len(r[1]) for r in rows)
    top    = "┌" + "─" * (lw + 2) + "┬" + "─" * (rw + 2) + "┐"
    sep    = "├" + "─" * (lw + 2) + "┼" + "─" * (rw + 2) + "┤"
    bot    = "└" + "─" * (lw + 2) + "┴" + "─" * (rw + 2) + "┘"
    lines  = [top]
    for i, (l, r) in enumerate(rows):
        lines.append(f"│ {l:<{lw}} │ {r:>{rw}} │")
        if i < len(rows) - 1:
            lines.append(sep)
    lines.append(bot)
    return "\n".join(lines)


# ── 메인 렌더 ─────────────────────────────────────────────────────────────
def build_board(gas_items: list[dict], queue_items: list[dict]) -> tuple[str, dict]:
    """보드 텍스트 + 섹션 dict 반환."""
    all_items = gas_items + queue_items
    secs = _classify(all_items)

    today = dt.date.today().strftime("%Y-%m-%d")
    wd_kor = ["월", "화", "수", "목", "금", "토", "일"][dt.date.today().weekday()]

    n_urgent = len(secs["urgent"])
    n_today  = len(secs["today"])
    n_appr   = len(secs["appr"])
    n_done   = len(secs["done"])
    n_total  = n_urgent + n_today + n_appr

    table = _box_table([
        ("🔴 급한 입항 (마감임박)",  str(n_urgent)),
        ("🧭 오늘의 항로 (진행·대기)", str(n_today)),
        ("🔴 GM 결재 대기",          str(n_appr)),
        ("⚓ 입항 완료",             str(n_done)),
        ("진행 합계",               str(n_total)),
    ])

    lines: list[str] = []
    lines.append(f"🧭 오늘의 항로  {today} ({wd_kor})")
    lines.append("━" * 36)
    lines.append(table)

    def _section(header: str, items: list[dict], show_status: bool = True) -> None:
        lines.append("")
        lines.append(header)
        if not items:
            lines.append("  (없음)")
        else:
            for it in items:
                lines.append(_render_line(it, show_status=show_status))

    if secs["urgent"]:
        _section("🔴 급한 입항 (마감임박 ≤3일)", secs["urgent"])

    _section("🧭 오늘의 항로", secs["today"])

    if secs["appr"]:
        # 결재는 항로에 개별 표시 안 함 — 카운트+포인터만(실제 결재는 결재현황 SSOT에서). GM 2026-06-07
        lines.append("")
        lines.append(f"🔴 GM 결재 {n_appr}건 — 결재 현황 SSOT에서 확인·결재")
        lines.append("    https://wellperion-cao.github.io/wellperion-automation/coo/todo/%EA%B2%B0%EC%9E%AC%20%ED%98%84%ED%99%A9%20SSOT.html")

    _section("⚓ 입항 (완료)", secs["done"], show_status=False)

    lines.append("")
    lines.append("━" * 36)
    lines.append("_본 보드는 자동 생성입니다._")

    return "\n".join(lines), secs


# ── CLI ───────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="항로 보드 생성기")
    parser.add_argument("--json", action="store_true", help="JSON도 출력")
    parser.add_argument("--dry-run", action="store_true", help="네트워크 없이 _queue만")
    args = parser.parse_args()

    if args.dry_run:
        gas_items = []
    else:
        gas_items = fetch_gas_items()

    queue_items = fetch_queue_items()

    board_text, secs = build_board(gas_items, queue_items)
    print(board_text)

    if args.json:
        print("\n--- JSON ---")
        out = {k: [
            {kk: vv for kk, vv in it.items() if kk != "_ship"}
            for it in v
        ] for k, v in secs.items()}
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
