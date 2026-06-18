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
from datetime import timezone
import io
import json
import re
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
# ※ sys 싱글톤에 가드 — __main__ 실행 뒤 모듈로 재import돼도 두 번 감싸지 않게.
#   이중래핑하면 먼저 만든 wrapper가 GC되며 버퍼를 닫아 'closed file' 버그가 난다.
if hasattr(sys.stdout, "buffer") and not getattr(sys, "_welp_stdout_wrapped", False):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys._welp_stdout_wrapped = True

# ── 상수 ──────────────────────────────────────────────────────────────────
GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)
QUEUE_PATH = _REPO / "status" / "_queue.json"

# 상태 아이콘 — 아이콘 표준 A안 (ssot/약속.json L16 · CLAUDE.md §3-1 정본과 동일값).
#   대기/정박=⚓ · 진행중=난이도별 배(_render_line이 ship 아이콘으로 덮음) · 완료=🏁
#   ★⚓ 뜻이 '완료'→'대기/정박'으로 바뀜. 완료는 🏁.
STATUS_ICON = {
    "완료":   "🏁",   # 완료 = 입항·도착
    "DONE":   "🏁",
    "진행중": "🚢",   # 진행중 — 실제 표시는 난이도별 배로 _render_line이 ship 아이콘 사용(fallback만 이 값)
    "IN_PROGRESS": "🚢",
    "대기":   "⚓",   # 대기/정박 = 출항 전(닻)
    "PENDING": "⚓",
    "보류":   "⚓",   # 보류 = 멈춰 다시 정박 → 대기/정박(닻)
    "ON_HOLD": "⚓",
}
# 진행중 = 난이도별 배(ship 아이콘으로 표시) — st_icon을 ship 아이콘으로 덮는 대상
STATUS_INPROGRESS = {"진행중", "IN_PROGRESS"}
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


# ── 텍스트 정제 헬퍼 ──────────────────────────────────────────────────────────
_RE_META_BRACKET = re.compile(r"^\s*\[[^\]]*\]\s*")   # 맨 앞 대괄호 메타 (연속 반복 제거)
_RE_NOISE_EMOJI  = re.compile(r"[🔄🌟]\s*")            # 잡음 이모지


def _clean_summary(text: str) -> str:
    """summary/note 날것 → 메타 제거·정제된 텍스트.

    1) 맨 앞 대괄호 메타 반복 제거: [이관 …], [2026-06-16 GM], [INC-002 …] 등
    2) 잡음 이모지 제거: 🔄 🌟
    3) 연속 공백·개행 → 한 칸, strip
    """
    s = str(text or "").strip()
    # 대괄호 메타 반복 제거
    while True:
        s2 = _RE_META_BRACKET.sub("", s)
        if s2 == s:
            break
        s = s2.strip()
    # 잡음 이모지 제거
    s = _RE_NOISE_EMOJI.sub("", s)
    # 연속 공백·개행 정리
    s = re.sub(r"[\r\n]+", " ", s)
    s = re.sub(r" {2,}", " ", s)
    return s.strip()


def _first_sentence(text: str) -> str:
    """정제된 텍스트의 첫 문장(. ! 。 — 또는 개행 기준)."""
    m = re.search(r"[.!。—\n]", text)
    return text[: m.start()].strip() if m else text.strip()


def _truncate_word(text: str, max_len: int, suffix: str = "…") -> str:
    """어절(공백) 경계에서 max_len 이하로 자르기. 중간 글자 잘림 금지."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    # 마지막 공백 위치에서 자르기
    sp = cut.rfind(" ")
    if sp > max_len // 2:
        cut = cut[:sp]
    return cut.rstrip() + suffix


def _derive_desc(item: dict) -> str:
    """간단설명 파생: 명시 필드 우선, 없으면 정제 summary 첫 문장 45자 컷."""
    # 선택 필드 간단설명·핵심조언 override (향후 배 등록 시 직접 채움)
    explicit = str(item.get("간단설명") or "").strip()
    if explicit:
        return explicit
    raw = str(item.get("_raw_summary") or "").strip()
    if not raw:
        return ""
    cleaned = _clean_summary(raw)
    first = _first_sentence(cleaned)
    return _truncate_word(first, 45)


def _derive_advice(item: dict) -> str:
    """핵심조언 파생: 명시 필드 우선, 없으면 정제 summary 전체 70자 컷. 날것 덤프·중간 잘림 절대 금지."""
    # 선택 필드 간단설명·핵심조언 override (향후 배 등록 시 직접 채움)
    explicit = str(item.get("핵심조언") or "").strip()
    if explicit:
        return explicit
    raw = str(item.get("_raw_summary") or "").strip()
    if not raw:
        return ""
    cleaned = _clean_summary(raw)
    return _truncate_word(cleaned, 70)


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
        _req = str(row.get("결재요청", "")).strip()
        _nxt = _next_approver(row)
        _apr_pending = _req != "" and apr != "결재완료" and "반려" not in apr
        needs_gm = _apr_pending and _nxt == "GM"
        # 결재 진행 중인데 GM 차례 아님(부서장·대표 대기) → 오늘 항로 제외 + 'N건 진행중' 집계 (GM 2026-06-07)
        appr_inflight = _apr_pending and _nxt is not None and _nxt != "GM"
        items.append({
            "id":        str(row.get("id", "")),
            "title":     title,
            "owner":     owner,
            "status":    st,
            "end_date":  end_kst,
            "mod_date":  _to_kst_date(str(row.get("수정일", "") or "")),
            "priority":  str(row.get("난이도", "") or "NORMAL"),
            "needs_gm_appr": needs_gm,
            "appr_inflight": appr_inflight,
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
            "terminal": bool(q.get("terminal", False)),
            "next":     str(q.get("next") or "").strip(),
            # 선택 필드 간단설명·핵심조언 override (향후 배 등록 시 직접 채움)
            "간단설명": str(q.get("간단설명") or "").strip(),
            "핵심조언": str(q.get("핵심조언") or "").strip(),
            # 정제 원본 보존 — _derive_desc/_derive_advice가 파생 시 사용
            "_raw_summary": str(q.get("note") or q.get("summary") or "").strip(),
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
        kst_today = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
        delta = (kst_today - d).days
        return 0 <= delta <= days
    except Exception:
        return False


def _classify(items: list[dict]) -> dict[str, list[dict]]:
    sections: dict[str, list[dict]] = {
        "urgent":  [],   # 🔴 급한 입항 (마감임박 ≤3일, 미완료)
        "today":   [],   # 🧭 오늘의 항로 (진행·대기)
        "appr":    [],   # 🔴 GM 결재 대기 (GM 차례)
        "appr_inflight": [],  # ⏳ 결재 진행 중 (타 결재자 대기)
        "done":    [],   # 🏁 완료 (입항·도착)
        "drift":   [],   # 🌀 표류 (완료인데 '다음' 없는 건 — "👉 다음 정하기" 촉구 동반)
    }
    # ── 후속 브릿지 인덱스 (표류 판정 보조) ──
    #   브릿지 메커니즘(project_bridge_mechanized): 완료 시 post_action --next/--terminal로
    #   후속 PENDING이 _queue에 자동 등록된다. 그 후속이 원건 task_id를 참조하면 '다리 놓임'.
    #   _queue 항목이 id 교차참조를 항상 갖진 않으므로(보수적 기준) → '다음 없음' 판정은
    #   ① terminal!=true 이고 ② 그 건을 잇는 후속 PENDING(_queue)이 없을 때.
    #   후속 존재 = 같은 owner의 PENDING/IN_PROGRESS가 있거나 item['next'] 브릿지 문구가 있을 때.
    _pending_owners: set[str] = {
        str(it.get("owner", "")) for it in items
        if str(it.get("status", "")).upper() in {"PENDING", "IN_PROGRESS", "진행중", "대기"}
    }
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()

    for item in items:
        iid = item["id"]
        if iid in seen_ids:
            continue
        seen_ids.add(iid)
        # 제목 기준 중복 차단 안전망 — 같은 AI배가 시트(GAS)와 _queue 양쪽에 있어도 1회만.
        #   (시트행 id ≠ _queue task_id 라 id 중복검사만으론 못 잡힘. AI배 시트 이관 대비, 2026-06-07)
        _tkey = re.sub(r"\s+", " ", str(item.get("title", "")).strip()).lower()
        if _tkey:
            if _tkey in seen_titles:
                continue
            seen_titles.add(_tkey)

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

        inflight = item.get("appr_inflight", False)
        if appr and not done:
            sections["appr"].append(item)
        elif inflight and not done:
            sections["appr_inflight"].append(item)   # 결재 진행 중(타 결재자 대기) — 오늘 항로서 제외
        elif urgent_flag:
            sections["urgent"].append(item)
        elif done:
            # 완료는 최근(오늘·어제) 완료만 — 옛 완료건은 이력이라 보드서 제외
            if _is_recent(item.get("mod_date", "")):
                # 🌀 표류 판정 (보수적): 완료인데 '다음'을 안 남긴 것.
                #   = terminal!=true 이고 next(브릿지 문구) 비었고, 그 owner의 후속 PENDING도 없음.
                #   판정 모호 시(terminal·next 정보 없는 GAS 시트 항목 등)는 표류로 몰지 않고 완료로 둔다(안전).
                is_terminal = bool(item.get("terminal", False))
                has_next = bool(str(item.get("next") or "").strip())
                has_follow_pending = str(item.get("owner", "")) in _pending_owners
                if (item.get("source") == "queue" and not is_terminal
                        and not has_next and not has_follow_pending):
                    sections["drift"].append(item)
                else:
                    sections["done"].append(item)
        else:
            sections["today"].append(item)

    # 무거운 배 먼저 정렬
    _rank = {"🛳️": 0, "⛴️": 1, "⛵": 2}
    for key in ("urgent", "today", "appr"):
        sections[key].sort(key=lambda x: _rank.get(x["_ship"]["icon"], 1))

    return sections


# ── 닉네임 매핑 (clevel 필드 → 닉네임, 약속 L16) ──────────────────
CLEVEL_NICK: dict[str, str] = {
    "CEO": "웰리",   "AI CEO": "웰리",
    "CMO": "시모",   "AI CMO": "시모",
    "COO": "시우",   "AI COO": "시우",
    "CTO": "시토",   "AI CTO": "시토",
    "CPO": "시포",   "AI CPO": "시포",
    "CFO": "시뽀",   "AI CFO": "시뽀",
    "CHRO": "시로",  "AI CHRO": "시로",
}


def _nick(owner: str) -> str:
    """clevel 필드 → 닉네임. 이미 닉네임이거나 GM이면 그대로."""
    u = owner.strip().upper()
    for k, v in CLEVEL_NICK.items():
        if k in u:
            return v
    if "김남욱" in owner or "GM" in owner.upper():
        return "GM"
    return owner[:4] if owner else "?"


def _md_table(rows: list[tuple[str, str, str, str, str]]) -> str:
    """마크다운 5칸 표: 배 | 담당 | 진행명 | 간단설명 | 본질에 대한 핵심조언"""
    if not rows:
        return "| — | — | (없음) | | |\n"
    header = "| 배 | 담당 | 진행명 | 간단설명 | 본질에 대한 핵심조언 |"
    sep    = "|---|---|---|---|---|"
    body   = "\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in rows)
    return f"{header}\n{sep}\n{body}\n"


def _item_to_row(it: dict, ship_col_extra: str = "") -> tuple[str, str, str, str, str]:
    """아이템 dict → 5-tuple for _md_table.
    ship_col_extra: 꼬리표 (예: '보류', '🔗', '🌀') — 배 칸 아이콘 뒤에 붙음."""
    ship  = it["_ship"]
    icon  = ship["icon"]
    nick  = _nick(str(it.get("owner", "")))
    title = str(it.get("title", ""))
    badges = ("🔴" if ship.get("urgent") else "") + ("🌟" if ship.get("northstar") else "")
    due   = it.get("end_date", "")
    due_s = f" ~{due[5:10]}" if due and len(due) >= 10 else ""
    title_col  = f"{title}{badges}{due_s}".strip()
    desc       = _derive_desc(it)
    advice     = _derive_advice(it)
    ship_col   = f"{icon} {ship_col_extra}".strip() if ship_col_extra else icon
    return (ship_col, nick, title_col, desc, advice)


# ── 박스표 (요약 카운터용) ────────────────────────────────────────────────
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


# ── 메인 렌더 (3섹터 마크다운 표, 약속 L16) ─────────────────────
def build_board(gas_items: list[dict], queue_items: list[dict]) -> tuple[str, dict]:
    """보드 텍스트 + 섹션 dict 반환.
    3섹터: 🚢 진행중 / ⚓ 대기중 / 🏁 입항 완료 (오늘)
    표 칼럼(5개): 배 | 담당 | 진행명 | 간단설명 | 본질에 대한 핵심조언
    배 칸=난이도 배 아이콘만 · 상태는 섹터 제목에만 · 담당=닉네임."""
    all_items = gas_items + queue_items
    secs = _classify(all_items)

    today  = dt.date.today().strftime("%Y-%m-%d")
    wd_kor = ["월", "화", "수", "목", "금", "토", "일"][dt.date.today().weekday()]

    n_urgent   = len(secs["urgent"])
    n_appr     = len(secs["appr"])
    n_inflight = len(secs["appr_inflight"])
    n_done     = len(secs["done"])
    n_drift    = len(secs["drift"])

    inprog  = [it for it in secs["today"] if it["status"] in STATUS_INPROGRESS or it["status"].upper() in STATUS_INPROGRESS]
    waiting = [it for it in secs["today"] if it not in inprog]
    n_total = n_urgent + len(inprog) + len(waiting) + n_appr

    _cnt_rows = [
        ("🚢 진행중",              str(len(inprog))),
        ("⚓ 대기중",               str(len(waiting))),
        ("🏁 입항 완료 (오늘)", str(n_done + n_drift)),
        ("🔴 급한 입항 (마감임박)", str(n_urgent)),
        ("🔴 GM 결재 대기",        str(n_appr)),
    ]
    if n_inflight:
        _cnt_rows.append(("⏳ 결재 진행 중 (타 결재자)", str(n_inflight)))
    if n_drift:
        _cnt_rows.append(("🌀 표류 (다음 미정)",          str(n_drift)))
    _cnt_rows.append(("진행 합계",                    str(n_total)))
    summary_table = _box_table(_cnt_rows)

    lines: list[str] = []
    lines.append(f"🧭 오늘의 항로  {today} ({wd_kor})")
    lines.append("━" * 36)
    lines.append(summary_table)

    # 항로 정합경고
    try:
        from queue_integrity_check import board_banner
        _bn = board_banner(gas_items=gas_items)
        if _bn:
            lines.append(_bn)
    except Exception:
        pass

    # ── 🔴 급한 입항 (별도 알림) ──
    if secs["urgent"]:
        lines.append("")
        lines.append("🔴 급한 입항 (마감임박 ≤3일)")
        lines.append(_md_table([_item_to_row(it) for it in secs["urgent"]]))

    # ── 🚢 진행중 섹터 ──
    lines.append("")
    lines.append("### 🚢 진행중")
    if inprog:
        lines.append(_md_table([_item_to_row(it) for it in inprog]))
    else:
        lines.append("_(없음)_\n")

    # ── ⚓ 대기중 섹터 ──
    lines.append("### ⚓ 대기중")
    if waiting:
        wait_rows = []
        for it in waiting:
            st  = str(it.get("status", ""))
            tag = "보류" if st in {"보류", "ON_HOLD"} else ""
            wait_rows.append(_item_to_row(it, ship_col_extra=tag))
        lines.append(_md_table(wait_rows))
    else:
        lines.append("_(없음)_\n")

    # ── 🏁 입항 완료 (오늘) 섹터 ──
    lines.append("### 🏁 입항 완료 (오늘)")
    done_all = secs["done"] + secs["drift"]
    if done_all:
        done_rows = []
        for it in secs["done"]:
            has_next = bool(str(it.get("next") or "").strip())
            tag = "🔗" if has_next else ""
            done_rows.append(_item_to_row(it, ship_col_extra=tag))
        for it in secs["drift"]:
            # 표류: 🌀 꼬리표, 핵심조언에 👉 촉구 반드시 포함 (약속 L16)
            advice = _derive_advice(it)
            advice_col = f"{advice} — 👉 다음 뭐 할지 정하세요" if advice else "👉 다음 뭐 할지 정하세요"
            ship  = it["_ship"]
            icon  = ship["icon"]
            nick  = _nick(str(it.get("owner", "")))
            title = str(it.get("title", ""))
            badges = ("🔴" if ship.get("urgent") else "") + ("🌟" if ship.get("northstar") else "")
            title_col = f"{title}{badges}".strip()
            desc  = str(it.get("간단설명") or "").strip()
            done_rows.append((f"{icon} 🌀", nick, title_col, desc, advice_col))
        lines.append(_md_table(done_rows))
    else:
        lines.append("_(없음)_\n")

    # ── 결재 포인터 ──
    if secs["appr"]:
        lines.append("")
        lines.append(f"🔴 GM 결재 {n_appr}건 — 결재 현황 SSOT에서 확인·결재")
        lines.append("    https://wellperion-cao.github.io/wellperion-automation/coo/todo/%EA%B2%B0%EC%9E%AC%20%ED%98%84%ED%99%A9%20SSOT.html")

    if secs["appr_inflight"]:
        lines.append("")
        lines.append(f"⏳ 결재 진행 중 {n_inflight}건 (타 결재자 대기) — 결재 현황 SSOT")

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
