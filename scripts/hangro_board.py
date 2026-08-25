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
import functools
import io
import json
import os
import re
import subprocess
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
from worklog import GM_AREA, GM_AREAS  # noqa: E402  — 정본=worklog.py(값 복사 금지·약속 L01)

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
WORKLOG_PATH = _REPO / "status" / "worklog.jsonl"
KPI_PATH = _REPO / "ssot" / "kpi.json"
GM_PROFILE_PATH = _REPO / "status" / "gm_profile.md"
MONTHLY_OPS_PLAN_PATH = _REPO / "status" / "monthly_ops_plan.json"
MIDMGR_ARCHIVE_DIR = _REPO / "1. AI자료_아카이브" / "11_카카오톡" / "★중간관리자"

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


def _is_sentence_period(text: str, i: int) -> bool:
    """text[i] 가 '.' 일 때, 그것이 정말 문장 끝인가.

    2026-07-31 — 아니면 문장이 엉뚱한 자리에서 잘린다. 그날 08:00 GM 보고에서 실제로 두 번 났다:
    「접수 2026. 7. 28」이 '2026' 에서 잘려 날짜가 두 칸으로 쪼개졌고, 「각 강사(P.T·수영」이
    '(P' 에서 잘렸다. GM 이 반복해 지적한 '문장·단어 중간 잘림'이 여기서 만들어지고 있었다.
    한국어 업무 기록에는 날짜·약어·소수점이 마침표를 그대로 쓰기 때문에 '.' 만으로는 문장을
    가를 수 없다. 아래 두 경우는 문장 끝이 아니다:
      · 마침표 뒤가 공백이 아님 — P.T · 1.5 · v2.0
      · 마침표 앞뒤가 숫자 — 2026. 7. 28
    """
    nxt = text[i + 1:i + 2]
    if nxt and not nxt.isspace():
        return False
    prev = text[i - 1:i] if i else ""
    if prev.isdigit():
        after = text[i + 1:].lstrip()
        if after[:1].isdigit():
            return False
    return True


def _first_sentence(text: str) -> str:
    """정제된 텍스트의 첫 문장(. ! 。 — 또는 개행 기준).
    '.' 는 진짜 문장 끝일 때만 경계로 본다(_is_sentence_period — 날짜·약어 중간 잘림 방지)."""
    for i, ch in enumerate(text):
        if ch in "!。—\n":
            return text[:i].strip()
        if ch == "." and _is_sentence_period(text, i):
            return text[:i].strip()
    return text.strip()


# 자를 수 있는 자리 — 여기서만 끊는다. 한국어 업무 제목은 공백 없이 길게 이어지는 구간이 많아
# 공백 하나만 보면 결국 글자 한가운데를 자르게 된다(2026-07-31 GM 지적 "문장 중간에서 끊긴다").
_CUT_BOUNDARIES = (" ", "—", "·", ",", "(", "[", ":", "/", "→")


def _truncate_word(text: str, max_len: int, suffix: str = "…") -> str:
    """자연스러운 경계에서 max_len 이하로 자르기. **중간 글자 잘림 금지.**

    ★2026-07-31 — 예전엔 공백만 찾았고, 못 찾으면 max_len 자리에서 그냥 끊었다. 그래서
    「…게이트 17일…」 「…단순화하던데 우린…」 「…웰리 배…」 처럼 뜻이 사라진 채 끝나는 줄이
    08:00 GM 보고에 여럿 나왔다. 이제 ①경계 후보를 넓히고 ②쓸 만한 경계가 앞쪽밖에 없으면
    (=자르면 뜻이 안 남으면) **자르지 않고 통째로 둔다.** 조금 긴 줄이 끊긴 뜻보다 낫다.
    """
    if len(text) <= max_len:
        return text
    window = text[:max_len]
    cut = max(window.rfind(c) for c in _CUT_BOUNDARIES)
    if cut < max_len // 2:
        return text
    return window[:cut].rstrip("".join(_CUT_BOUNDARIES)) + suffix


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


def _dedupe_advice(desc: str, advice: str) -> str:
    """핵심조언이 간단설명과 같은 문장으로 시작하면 겹치는 앞부분을 걷어내고
    다른 각도만 남긴다(웰리 결정 2026-07-27 — 한 줄에서 같은 말 두 번 읽지 않게).
    걷어내고 남는 게 없으면 빈 문자열 — 억지로 채우지 않는다(빈 칸 > 중복)."""
    d = str(desc or "").strip()
    a = str(advice or "").strip()
    if not d or not a:
        return a
    if a == d:
        return ""
    if a.startswith(d):
        rest = a[len(d):].lstrip()
        rest = re.sub(r"^[.·\-,:]+\s*", "", rest)
        return rest
    # ★잘린 문장까지 잡는다 (2026-08-13 · GM "고도화된 부분을 단순화").
    #   위 startswith 판정은 두 칸이 **같은 note 를 서로 다른 길이로 자른** 경우를 못 잡는다
    #   (한쪽이 '…' 로 끝나면 접두 일치가 깨진다). 실측 — 설명·조언이 둘 다 있는 55줄 중
    #   22줄이 앞 20자가 같은 같은 문장이었다. 같은 말을 두 번 읽는 것이고, 창마다 그만큼
    #   맥락을 먹는다. 앞 30자가 같으면 같은 출처로 보고 조언 칸을 비운다 —
    #   30자면 우연히 겹칠 길이가 아니다(제목·머리기호가 아니라 본문 첫 문장 수준).
    _n = lambda s: re.sub(r"\s+", "", s)[:30]
    if len(_n(d)) >= 20 and _n(a) == _n(d):
        return ""
    return a


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
def _gm_key() -> str:
    """GM 행 열쇠 — 환경변수 우선, 없으면 telegram_bot/.env(저장소 밖·gitignore 실측 확인) 한 줄.
    값은 저장소에 두지 않는다(배326 — 그게 GM1_PW='1234' 가 만든 문제였다).
    열쇠를 아는 프로세스는 여기 하나뿐 — 08:00 보고·G1 머지가 전부 이 함수를 지난다."""
    k = os.environ.get("GM_TODO_KEY", "").strip()
    if k:
        return k
    try:
        for line in (_HERE.parent / "telegram_bot" / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("GM_TODO_KEY="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def fetch_gas_items() -> list[dict]:
    """GAS todo_list → GM·AI C레벨 전체 항목(완료 포함)."""
    # 열쇠 없으면 GM 행이 안 온다 — 조용히 비면 GM 할 일이 사라져도 아무도 모른다. 반드시 남긴다.
    _k = _gm_key()
    if not _k:
        print("[WARN] GM_TODO_KEY 미설정 — GM 행 제외된 채로 집계합니다(배326). "
              "telegram_bot/.env 에 GM_TODO_KEY= 한 줄을 넣으세요.", file=sys.stderr)
    try:
        req = urllib.request.Request(
            GAS_URL + "?action=todo_list"
            + (f"&include_gm=1&gmkey={urllib.parse.quote(_k)}" if _k else "")
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        rows = data.get("data", [])
    except Exception as e:
        print(f"[WARN] GAS fetch 실패: {e}", file=sys.stderr)
        rows = []

    # 열쇠를 붙였는데도 GM 행이 0건 = GAS 스크립트 속성값과 불일치. 미설정만 잡으면
    # '틀린 열쇠'가 조용히 통과해 GM 할 일이 통째로 사라져도 아무도 모른다(0 위장).
    if _k and rows and not any("김남욱GM" in str(r.get("담당자", "")) for r in rows):
        print("[WARN] GM_TODO_KEY 불일치 추정 — 열쇠를 붙였는데 GM 행이 0건입니다(배326). "
              "GAS 스크립트 속성 GM_TODO_KEY 와 telegram_bot/.env 값이 같은지 확인하세요.",
              file=sys.stderr)

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


def _queue_row_to_item(q: dict) -> dict | None:
    """_queue.json / _queue_archive.json 한 줄 → 보드 항목. 대상 아니면 None."""
    st = str(q.get("status", ""))
    if "폐기" in st:
        return None
    if st.upper() not in {"PENDING", "IN_PROGRESS", "ON_HOLD", "DONE", "완료", "진행중", "대기"}:
        return None
    title = str(q.get("title", "")).strip()
    if not title:
        return None
    return _build_item(q, st, title)


def fetch_queue_items() -> list[dict]:
    """_queue.json → PENDING·IN_PROGRESS AI 배 + 보관함의 '오늘 입항' 배.

    ★보관함을 같이 보는 이유(2026-07-29 시토 · 배10369): 완료한 배는 곧
      status/_queue_archive.json 으로 옮겨진다. 살아있는 큐만 보면 **오늘 끝낸 배가
      보관되는 순간 사라져** 🏁 칸이 사실상 항상 0이 된다 — 일한 사람에게 '오늘 한 게 없다'고
      말하는 거짓 0이다(아침 자가점검 #7 '0 위장'과 같은 부류). 상태줄(wellperion_hud.mjs)은
      같은 이유로 이미 보관함을 함께 본다 — 여기만 안 보고 있었다.
      비용 방어: 보관함 파일이 **오늘 바뀌었을 때만** 연다(오늘 보관된 게 없으면 열 이유가 없다).
    """
    if not QUEUE_PATH.exists():
        return []
    try:
        rows = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] _queue.json 읽기 실패: {e}", file=sys.stderr)
        return []
    items = [it for it in (_queue_row_to_item(q) for q in rows if isinstance(q, dict)) if it]

    today = dt.datetime.now().strftime("%Y-%m-%d")
    arc_path = _REPO / "status" / "_queue_archive.json"
    try:
        if arc_path.exists() and dt.datetime.fromtimestamp(
                arc_path.stat().st_mtime).strftime("%Y-%m-%d") == today:
            seen = {str(q.get("task_id", "")) for q in rows if isinstance(q, dict)}
            for q in json.loads(arc_path.read_text(encoding="utf-8")):
                if not isinstance(q, dict) or str(q.get("task_id", "")) in seen:
                    continue
                if str(q.get("status", "")).upper() not in {"DONE", "완료"}:
                    continue
                stamp = str(q.get("processed_at") or q.get("done_at") or q.get("updated_at") or "")
                if not stamp.startswith(today):
                    continue
                it = _queue_row_to_item(q)
                if it:
                    items.append(it)
    except Exception as e:   # 보관함이 없거나 깨져도 살아있는 큐 기준으로는 정상 동작한다
        print(f"[WARN] _queue_archive.json 읽기 건너뜀: {e}", file=sys.stderr)

    return items


def _build_item(q: dict, st: str, title: str) -> dict:
    """큐 한 줄 → 보드 항목(칸 매핑 단일 지점 — 큐·보관함이 같은 잣대를 쓰게)."""
    return {
            "id":       str(q.get("task_id", "")),
            "title":    title,
            "owner":    str(q.get("clevel", "")).upper(),
            "status":   st,
            "end_date": str(q.get("deadline") or ""),
            # 완료일 — processed_at 이 정확하지만 배마다 칸이 제각각이라 done_at·updated_at 까지
            # 차례로 본다(2026-07-29 배10369). 안 그러면 완료 도장은 찍혔는데 날짜 칸이 비어
            # 🏁 섹션에서 조용히 빠진다. 상태줄이 이미 쓰는 것과 같은 우선순위다.
            "mod_date": str(q.get("processed_at") or q.get("done_at") or q.get("updated_at") or ""),
            "priority": str(q.get("priority", "NORMAL")),
            "needs_gm_appr": False,
            "terminal": bool(q.get("terminal", False)),
            "next":     str(q.get("next") or "").strip(),
            # '봤다' 한 줄(무엇을 보고 됐다고 했나) — 있으면 ✅, 없으면 🔍미확인 배지(막지 않음).
            "saw":      str(q.get("saw") or "").strip(),
            # 선택 필드 간단설명·핵심조언 override (향후 배 등록 시 직접 채움)
            "간단설명": str(q.get("간단설명") or "").strip(),
            "핵심조언": str(q.get("핵심조언") or "").strip(),
            # 정제 원본 보존 — _derive_desc/_derive_advice가 파생 시 사용
            "_raw_summary": str(q.get("note") or q.get("summary") or "").strip(),
            # 담당 구분(office=실무진·GM이 볼 일 / ai=AI 내부 살림). AI 배는 항로에서 빼고
            # 자율현황行으로 보낸다 — 화면(자율현황)과 **같은 기준**이어야 표면이 안 어긋난다.
            # (2026-08-14: G1 은 2026-08-05 부로 AI 배를 안 그린다 — 옛 표기를 지웠다 · 규약 부칙 1)
            # ★구 'board' 칸 폐기(2026-08-03 시토): 판정을 board=='자율현황' 으로 했는데 그 칸이
            #   열린 배 67척 **전부 비어** 있어 한 건도 안 걸러졌다 — 아침 보고는 AI 배까지 다 싣고,
            #   화면은 빼고 있었다. 아무도 안 채우는 칸으로 판정하던 것이 원인이라 칸째로 뺀다.
            "audience": str(q.get("audience") or "").strip(),
            # 끝이 있는 일인가(빈칸) / 매일·매주 도는가(routine) / 사건이 와야 시작되나(trigger).
            # routine·trigger 는 완료 도장을 찍을 수 있는 일이 아니라 진행대기 숫자 밖으로 뺀다
            # (GM 지시 2026-08-16 — 위 _classify 분기 주석 참조). 빈칸 = 평범한 배(항로에 남는다).
            "cadence": str(q.get("cadence") or "").strip(),
            # 🎯 오늘 반드시 끝낼 것(GM 2026-08-10) — C-Level이 스스로 지목한 날짜(YYYY-MM-DD).
            # 지목 수단 = queue_dispatch.py --must-finish (build_ship/dup-absorb 양쪽에서 채움).
            "must_finish_on": str(q.get("must_finish_on") or "").strip(),
            # 담당 식별번호(약속 L16: 담당=닉네임+ship_no·배마다 고정). _queue 배만 보유.
            # 배를 띄운 날 — _open_days('안 닫힌 지 며칠')의 1차 근거. ★이 칸이 여기 없어서
            # (배540 수리 중 2026-08-13 발견) 지금까지 _open_days 가 전부 폴백(note 안 최소 날짜
            # 훑기)으로 떨어졌다. 그래서 배39는 22일째인데 101일째로, 배236은 14일째인데 16일째로
            # 찍혔다 — note 에 인용된 옛 날짜를 '뜬 날'로 오인한 것이다. 꼬리표·정렬이 쓰는 숫자라
            # 여기서 한 줄 넘기는 것이 뿌리 수리다.
            "enqueued_at": str(q.get("enqueued_at") or "")[:10],
            "ship_no":  q.get("ship_no", ""),
            # 화면표시 전용 짧은 번호(배10012 2단계) — 내부 조인은 위 ship_no 그대로,
            # _owner_label만 이 값을 우선 표시(없으면 ship_no 폴백).
            "short_no": q.get("short_no", ""),
            "source":   "queue",
            # 보낸 역할(queue_dispatch.py build_ship의 "from" 그대로) — "쿵짝: 내가 넘긴 배"
            # 판정 단일 지점(2026-08-04 GM 지시). GAS 항목엔 이 칸이 없다(= "").
            "_from":    str(q.get("from", "")).strip().lower(),
            # ❓ 안 물어봄 판정용(2026-08-13) — 키 유무로 "실무진 릴레이 채널을 쓰는 배인지"를 가른다.
            "_has_staff_field": "staff_message" in q,
            "staff_message": str(q.get("staff_message") or "").strip(),
            # ✉️ 발신 대기 판정용(2026-08-24) — 채워졌으면 이미 사람 방에 나간 것.
            "staff_message_sent_at": str(q.get("staff_message_sent_at") or "").strip(),
    }


# ── 섹션 분류 ──────────────────────────────────────────────────────────────
def _must_finish_days_late(item: dict) -> int | None:
    """must_finish_on(YYYY-MM-DD)이 오늘보다 며칠 지났나. 못 지웠으면 None."""
    raw = str(item.get("must_finish_on") or "")[:10]
    try:
        d = dt.datetime.strptime(raw, "%Y-%m-%d").date()
    except Exception:
        return None
    return (dt.date.today() - d).days


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
        "autonomy": [],  # 🤖 자율화 미션 (board='자율현황') — 항로 제외, 자율현황 보드行 (GM 2026-07-15)
        "routine": [],   # 🔁 반복 루틴 (cadence=routine) — 매일·매주 도는 일, 완료 도장이 없다 (GM 2026-08-16)
        "trigger": [],   # 🪝 조건 대기 (cadence=trigger) — 사건이 와야 시작된다 (GM 2026-08-16)
        "must_finish_today":   [],  # 🎯 오늘 반드시 끝낼 것 (must_finish_on == 오늘, 미완료)
        "must_finish_overdue": [],  # 🔴 어제 못 지킴 (must_finish_on < 오늘, 미완료 · 조용히 안 사라짐)
    }
    # ── 🎯 오늘 반드시 끝낼 것 (GM 2026-08-10 "놓치지 않게") ──
    #   audience(office/ai) 무관하게 지목된 배는 전부 잡는다 — AI 배도 자율현황行으로 안 빠지고
    #   여기 뜬다(아래 audience=='ai' continue보다 먼저 본다). DONE은 자동으로 빠진다(요구사항 그대로).
    for item in items:
        if str(item.get("status", "")) in STATUS_DONE:
            continue
        if not str(item.get("must_finish_on") or "").strip():
            continue
        if "_ship" not in item:
            item["_ship"] = classify_ship({
                "title": item["title"], "priority": item["priority"], "deadline": item["end_date"]})
        late = _must_finish_days_late(item)
        if late is None or late < 0:  # 미래 날짜(아직 안 옴)는 조용히 건너뛴다 — 오늘 되면 자동으로 뜬다
            continue
        (sections["must_finish_overdue"] if late > 0 else sections["must_finish_today"]).append(item)
    sections["must_finish_overdue"].sort(key=lambda it: -(_must_finish_days_late(it) or 0))

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

        # AI 배는 항로 전 섹터에서 제외 → 자율현황 보드로 (GM 2026-07-15 · 기준 교정 2026-08-03)
        #   미지정은 AI 가 아니다 = 항로에 남는다(화면과 동일한 안전측 판정).
        if item.get("audience") == "ai":
            sections["autonomy"].append(item)
            continue

        # ★2026-08-16 GM 지시 — '애초에 닫힐 수 없는 배'를 진행대기 숫자에서 뺀다.
        #   GM: "진행대기배가 88척은 너무많네" → 실측해 보니 그중 15척은 끝이 없는 종류였다:
        #   ①매일·매주 도는 반복 루틴(cadence=routine) ②사건이 와야 시작되는 조건 대기
        #   (cadence=trigger). 둘 다 완료 도장을 찍을 수 있는 일이 아니라, 배로 세면
        #   숫자만 영원히 부푼다 — 그러면 진짜 밀린 일이 그 안에 묻힌다.
        #   ▸지우지 않는다. AI 배(audience=ai)를 자율현황行으로 빼는 것과 같은 방식으로
        #     별도 칸에 모아 그대로 보여 준다(위 분기와 같은 구조 — 새 장치 아님).
        #   ▸미지정은 여기 안 걸린다 = 항로에 남는다(안전측 판정, 위 audience 와 동일).
        cadence = str(item.get("cadence") or "").strip()
        if cadence in ("routine", "trigger") and item["status"] not in STATUS_DONE:
            # 이 두 칸은 표로 그리므로 배 아이콘이 필요하다(자율화 미션은 포인터 한 줄이라 없어도 됐다).
            item["_ship"] = classify_ship({
                "title": item["title"], "priority": item["priority"], "deadline": item["end_date"]})
            sections["routine" if cadence == "routine" else "trigger"].append(item)
            continue

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
                # '다음' 없는 완료도 그냥 완료다 (GM 확정 2026-08-19 · 약속 L11).
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


def _owner_label(it: dict) -> str:
    """담당 칸 = 닉네임+번호 (약속 L16·배마다 고정 식별번호).
    표시는 short_no 우선(배10012 2단계 — 화면표시 전용 짧은 번호), 없으면 기존
    ship_no로 폴백(옛 닫힌 배·GAS 시트항목 등), 둘 다 없으면 닉네임만."""
    nick = _nick(str(it.get("owner", "")))
    sn = str(it.get("short_no") or it.get("ship_no") or "").strip()
    return f"{nick} {sn}" if sn else nick


def _md_table(rows: list[tuple[str, str, str, str, str]]) -> str:
    """마크다운 5칸 표: 배 | 담당 | 진행명 | 간단설명 | 본질에 대한 핵심조언"""
    if not rows:
        return "| — | — | (없음) | | |\n"
    header = "| 배 | 담당 | 진행명 | 간단설명 | 본질에 대한 핵심조언 |"
    sep    = "|---|---|---|---|---|"
    body   = "\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in rows)
    return f"{header}\n{sep}\n{body}\n"


def _saw_badge(it: dict) -> str:
    """완료 배 표시용 — 'saw'(무엇을 보고 됐다고 했나)가 있으면 ✅, 없으면 🔍미확인.
    막지 않는다 — 표시만(웰리)."""
    return "✅" if str(it.get("saw") or "").strip() else "🔍미확인"


def _item_to_row(it: dict, ship_col_extra: str = "", brief: bool = False,
                 brief_note: str = "↓ 아래 본 섹터에") -> tuple[str, str, str, str, str]:
    """아이템 dict → 5-tuple for _md_table.
    ship_col_extra: 꼬리표 (예: '보류', '🔗', '🌀') — 배 칸 아이콘 뒤에 붙음.
    brief=True: 간단설명·핵심조언을 접는다 — **아래 3섹터(진행중/대기중/입항)에 같은 배가
    또 나오는 경우**에만 쓴다(위 진단 표들은 '이 배가 이런 상태다'만 말하면 되고, 설명·조언은
    본 섹터 한 곳에서 읽으면 된다).

    ★왜 (2026-08-13 · GM "고도화된 부분을 단순화"):
      실측 — 시토 항로 출력 14,121자 중 표 줄 57개가 서로 다른 배 34척을 그렸다. 같은 배가
      최대 4번(303·338·464) 실렸고 중복으로 더 실린 줄이 23줄이었다. 진단 층이 쌓이며
      같은 설명·조언이 배마다 2~4벌 복사되고 있었다 — 읽는 사람에겐 같은 말 반복이고,
      부팅 맥락에는 매 창마다 그만큼이 실린다."""
    ship  = it["_ship"]
    icon  = ship["icon"]
    nick  = _owner_label(it)
    title = str(it.get("title", ""))
    badges = ("🔴" if ship.get("urgent") else "") + ("🌟" if ship.get("northstar") else "")
    due   = it.get("end_date", "")
    due_s = f" ~{due[5:10]}" if due and len(due) >= 10 else ""
    title_col  = f"{title}{badges}{due_s}".strip()
    desc       = _derive_desc(it)
    advice     = _dedupe_advice(desc, _derive_advice(it))
    ship_col   = f"{icon} {ship_col_extra}".strip() if ship_col_extra else icon
    if brief:
        return (ship_col, nick, title_col, brief_note, "")
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
# ── 정체 추적 (2026-07-31 GM 지시) ──────────────────────────────────────────
# "업무 및 진행 안 된 건에 대해서는 집요하게 체크해서 완료할 수 있도록 서포트해줘."
# ▸며칠째 움직임이 없는지 잰다. 큐에 `updated_at` 은 32척 중 9척에만 있어(실측 2026-07-31)
#   그것만으로는 못 잰다 → **기록(note)에 붙는 날짜 마커**를 마지막 움직임으로 본다.
#   이 저장소는 모든 역할이 note 에 `[… 2026-07-31]` 형태로 덧붙이는 관례라 이게 가장 정확하다.
#   마커가 하나도 없으면 배를 띄운 날(enqueued_at)을 쓴다.
# ▸단계로 집요해진다: 3일=담당 차례 · 7일=웰리가 본다 · 14일=GM께 올린다.
#   같은 줄에 단계가 보여야 "언제까지 방치할 것인가"가 스스로 드러난다.
_STALL_MIN_DAYS = 3
_RE_DATE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")


def _last_touch(item: dict) -> dt.date | None:
    """그 배가 마지막으로 움직인 날(기록에 남은 가장 늦은 날짜)."""
    blob = " ".join(str(item.get(k) or "") for k in ("note", "_raw_summary", "updated_at"))
    best = None
    for y, m, d in _RE_DATE.findall(blob):
        try:
            cand = dt.date(int(y), int(m), int(d))
        except ValueError:
            continue
        if cand <= dt.date.today() and (best is None or cand > best):
            best = cand
    if best:
        return best
    raw = str(item.get("enqueued_at") or "")[:10]
    try:
        return dt.datetime.strptime(raw, "%Y-%m-%d").date()
    except Exception:
        return None


def _stall_days(item: dict) -> int | None:
    last = _last_touch(item)
    return None if last is None else (dt.date.today() - last).days


def _stall_tag(item: dict, days: int | None = None) -> str:
    """꼬리표 기준 = _open_days(안 닫힌 지 며칠) — 배540.
    _stall_days(마지막 기록일)로 재면 note 한 줄만 붙어도 0으로 돌아가, 22일째 열려 있는
    배가 '1일🟡담당'으로 찍힌다(2026-08-10 실측). 축은 _open_days 하나로 통일하되,
    기록 공백도 정보이므로 버리지 않고 괄호처럼 뒤에 함께 적는다 — 축 하나, 표시 둘."""
    d = (_open_days(item) or 0) if days is None else days
    if d >= 14:
        tag = f"{d}일째🔴GM"
    elif d >= 7:
        tag = f"{d}일째🟠웰리"
    else:
        tag = f"{d}일째🟡담당"
    quiet = _stall_days(item) or 0
    return f"{tag}·기록{quiet}일전" if quiet >= _STALL_MIN_DAYS else tag


_RE_PERMANENT = re.compile(r"^\[[^\]]+\]\s*상설\b")


def _is_permanent(item: dict) -> bool:
    """제목이 '[닉네임] 상설 …'인 배 — 아침 자가점검을 계속 흡수하는 그릇이라 원래 안 닫힌다.
    큐 스키마에 별도 표식(kind 등) 없어 제목이 가장 얇은 판별선(배591 후속·2026-08-13).
    ⚓ 대기중 등 다른 목록에서는 그대로 보인다 — 여기서만(안 닫힌 배) 뺀다."""
    return bool(_RE_PERMANENT.match(str(item.get("title") or "")))


def _stalled(items: list[dict], min_days: int = _STALL_MIN_DAYS) -> list[dict]:
    """안 닫힌 지 오래된 배 — 오래된 순. 기준=_open_days(배540에서 _stall_days 에서 옮김).
    옛 기준은 마지막 기록일만 봐서, 매일 한 줄씩 적히기만 하고 끝나지 않는 배를
    목록에서 조용히 뺐다. 이 함수가 그 축을 흡수했으므로 별도 '오래 걸리는 배' 표는
    없앴다(약속 L21 net-zero).
    상설 배(_is_permanent)는 뺀다 — 영원히 열려 있는 게 정상이라 매번 맨 위를 차지해
    진짜 방치된 배를 묻는다(GM 지적 2026-08-13)."""
    out = [it for it in items if (_open_days(it) or 0) >= min_days and not _is_permanent(it)]
    return sorted(out, key=lambda it: -(_open_days(it) or 0))


# ── '안 닫힌 날수' 축 (2026-08-07 GM 지시 "문제·진행이 반복되고 처리가 안 되면 서포트해라") ──
# 옛 _stalled 는 **마지막으로 기록이 붙은 날**을 봤다. note 는 오늘 날짜만 스쳐도 갱신된 것으로
# 보여서, 실측(2026-08-07) '멈춘 배 0척'인데 **열린 지 14일 넘은 배가 21척**이었다. 매일 한 줄씩
# 적히기만 하고 끝나지 않는 배가 감지기를 통째로 빠져나갔다.
# 그래서 2026-08-07 에 두 번째 표('오래 걸리는 배')를 나란히 뒀는데, 두 표가 같은 배를 다른
# 숫자로 보여 GM 이 어느 쪽이 사실인지 되짚어야 했다. 2026-08-13(배540) 에 축을 이것 하나로
# 통일하고 두 번째 표를 없앴다 — 기록 공백은 꼬리표 뒤에 함께 적어 정보 손실 0.
_REPO_EPOCH = dt.date(2026, 1, 1)   # 이보다 이른 날짜는 오타·기본값(2000-01-01 등) — 나이 계산에서 뺀다


def _open_days(item: dict) -> int | None:
    """그 배가 처음 뜬 뒤 지난 날수. 날짜를 못 찾으면 None."""
    raw = str(item.get("enqueued_at") or "")[:10]
    first = None
    try:
        cand = dt.datetime.strptime(raw, "%Y-%m-%d").date()
        if _REPO_EPOCH <= cand <= dt.date.today():
            first = cand
    except Exception:
        pass
    if first is None:
        blob = " ".join(str(item.get(k) or "") for k in ("note", "_raw_summary"))
        for y, m, d in _RE_DATE.findall(blob):
            try:
                cand = dt.date(int(y), int(m), int(d))
            except ValueError:
                continue
            if _REPO_EPOCH <= cand <= dt.date.today() and (first is None or cand < first):
                first = cand
    return None if first is None else (dt.date.today() - first).days


# ── 🔔 쿵짝 회수 (2026-08-04 GM 지시 "작업 1개당 답변 1개" — 배를 띄우고 끝내지 마라.
#   넘긴 배는 답이 올 때까지 내가 쥐고 있는다. 답이 없으면 그것부터 보고한다("N일째").
#   지금까지 웰리에게만 걸려 있던 규칙을 역할과 무관하게(약속 L01) 여기 한 곳에 얹는다. ──
def _sent_unanswered(items: list[dict], role: str) -> list[dict]:
    """role이 다른 역할에게 띄운 배 중 아직 열려 있는(답 없는) 것. 오래된 순.
    1일 미만(오늘 띄운 배)은 뺀다 — 매일 뜨면 아무도 안 본다.
    기준=_open_days(배를 넘긴 날부터, 배540) — _stall_days(마지막 기록일)를 쓰면
    메모 한 줄만 붙어도 날짜가 초기화돼 실제로 오래 답 없는 배가 목록에서 빠진다."""
    role = (role or "").strip().lower()
    if not role:
        return []
    open_status = {"PENDING", "IN_PROGRESS", "ON_HOLD", "보류", "대기", "진행중"}
    out = [it for it in items
           if it.get("_from") == role
           and str(it.get("owner", "")).lower() != role
           and str(it.get("status", "")).upper() in open_status
           and (_open_days(it) or 0) >= 1]
    return sorted(out, key=lambda it: -(_open_days(it) or 0))


def _received_unanswered(items: list[dict], role: str) -> list[dict]:
    """쿵짝의 받는 쪽 짝(2026-08-06 배397 — 남이 나에게 띄운 배는 대기중 섹터에 자기
    배와 섞여 있어 눈에 안 띈다는 실측 지적). role이 남에게서 받아 아직 열려 있는 것.
    오래된 순, 1일 미만은 뺀다(위와 동일 기준). AI 내부 배(audience=='ai')는 자율현황行이라 제외."""
    role = (role or "").strip().lower()
    if not role:
        return []
    open_status = {"PENDING", "IN_PROGRESS", "ON_HOLD", "보류", "대기", "진행중"}
    out = [it for it in items
           if str(it.get("owner", "")).lower() == role
           and it.get("_from") and it.get("_from") != role
           and it.get("audience") != "ai"
           and str(it.get("status", "")).upper() in open_status
           and (_open_days(it) or 0) >= 1]
    return sorted(out, key=lambda it: -(_open_days(it) or 0))


# ── 📨 GM 요청 짝맞추기 (2026-08-05 GM 지시 — status/worklog.jsonl area=="GM지시" 미완
#   적발. 실사고: 대표님 보고건(GM-20260804-05, 21:03)이 접수만 되고 안 끝났는데 부팅
#   점검은 "미완 0"이라 아무도 못 집었다. ref 가 하루 안에서 3~6회 재사용되는데 판정을
#   "ref 하나에 ok 가 있으면 끝난 것"으로 잘못 봐 09:23 ok 가 21:03 warn 을 덮었다. 게다가
#   이 짝맞추기가 부팅 지시문(prose)에만 있어 세션마다 즉석으로 다시 짜다 보니 함정이
#   안 걸러졌다 — 그래서 이미 전 역할이 지나가는 이 보드에 코드로 박는다(약속 L02·L21).
#   판정 = ref 별 건수 대조: warn 개수 - ok 개수 = 미완 건수. 미완으로 보일 건 = 그
#   ref 의 warn 중 가장 나중 것들(오래된 것부터 ok 개수만큼은 닫힌 것으로 친다).
#   ★시간순 스택이 아니라 건수인 이유(2026-08-13 배506 수리): 같은 ref 에 ok 가 warn
#   보다 먼저 찍히는 레이스가 실측에서 나왔다(GM-20260807-23 — ok 16:37 · warn 16:38,
#   1분 역전). ts 오름차순 스택은 이 역전에서 ok 를 빈 대기열에 버리고 뒤이은 warn 을
#   영원히 못 닫았다. 건수만 세면 순서가 역전돼도 정확히 닫힌다. ──
def _pair_gm_directives(entries: list[dict]) -> list[dict]:
    """area 가 GM_AREAS(GM요청·GM지시) 인 로그 목록을 ref 별로 모아 (warn 개수 - ok 개수)만큼만 미완으로 반환
    (오래된 순). 파일 I/O 없음 — 순수 함수(테스트용으로 분리, _gm_directive_unresolved 가
    파일을 읽어 넘김)."""
    by_ref: dict[str, list[dict]] = {}
    for d in entries:
        by_ref.setdefault(str(d.get("ref", "")), []).append(d)

    today = dt.date.today()
    out: list[dict] = []
    for group in by_ref.values():
        warns = sorted((d for d in group if str(d.get("result", "")) == "warn"),
                        key=lambda d: str(d.get("ts", "")))
        # 같은 GM 발화 하나가 warn 두 줄로 남는다 — UserPromptSubmit 훅이 자동으로 한 줄,
        # C-Level 이 손으로 또 한 줄. 건수 대조라 이 중복이 영영 못 닫는 유령 미완이 된다
        # (2026-08-25 시포 실측: 전역 미완 6건이 전부 이 형태였다). 손기록이 같이 있으면
        # 자동 접수 줄은 세지 않는다. 자동 줄만 있는 ref 는 그대로 둔다 — 진짜 미착수다.
        manual = [d for d in warns if not _is_auto_intake(d)]
        if manual:
            warns = manual
        n_ok = sum(1 for d in group if str(d.get("result", "")) == "ok")
        for d in warns[n_ok:]:          # 오래된 것부터 n_ok 개는 닫힌 것으로 치고 나머지만 미완
            ts = str(d.get("ts", ""))
            try:
                days = (today - dt.datetime.strptime(ts[:10], "%Y-%m-%d").date()).days
            except Exception:
                days = 0
            out.append({"days": days, "ts": ts, "event": str(d.get("event", "")),
                        "ref": str(d.get("ref", ""))})
    out.sort(key=lambda x: x["ts"])
    return out


def _is_auto_intake(d: dict) -> bool:
    """UserPromptSubmit 훅이 자동으로 남긴 접수 줄인가 (사람이 손으로 남긴 접수와 구분)."""
    return "자동 접수" in str(d.get("detail", ""))


def _is_gm_directive_log(d: dict) -> bool:
    """이 로그 줄이 GM 요청 짝맞추기 대상인가 — ref 가 GM- 로 시작하면 접수든 완료든 대상이다."""
    return str(d.get("ref", "")).startswith("GM-")


def _gm_directive_unresolved(role: str = "") -> list[dict]:
    """status/worklog.jsonl 을 읽어(읽기 전용 — 절대 쓰지 않는다, 다른 세션이 쓰는 중일 수
    있다) GM 요청 ref(GM-…) 를 가진 항목을 걸러 _pair_gm_directives 로 미완을 판정한다.
    role 지정 시 그 role 이 남긴 로그만 본다.

    ★거르는 기준 = area 가 아니라 ref (2026-08-12 시토 실측 수리). 접수(warn)는 area 가
    GM_AREAS(GM요청·GM지시) 로 들어오지만 **완료(ok)는 그 일의 도메인 area 로 적힌다**(자동화·회원·강습·작업…).
    area 로 거르면 완료 기록이 통째로 안 보여 이미 끝난 지시가 계속 미완으로 남았다 —
    실측 당시 전역 미완 28건 중 11건(39%)이 이 오탐이었고, 부팅 화면이 매일 거짓을 냈다.
    쿵짝표(kungjjak_board)는 처음부터 ref 로만 짝을 맞춰 두 화면 숫자가 어긋나 있었다."""
    entries: list[dict] = []
    try:
        with WORKLOG_PATH.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if not _is_gm_directive_log(d):
                    continue
                if role and str(d.get("role", "")).strip().lower() != role.strip().lower():
                    continue
                entries.append(d)
    except Exception:
        return []
    return _pair_gm_directives(entries)


def _selftest_gm_directives() -> None:
    """3줄(warn·ok·warn 같은 ref) 넣으면 미완 1건(가장 나중 warn)만 남는지 확인.
    GM-20260804-05 실사고(09:20 warn/09:23 ok/21:03 warn) 재현 — 21:03 만 남아야 한다."""
    sample = [
        {"ts": "2026-08-04T09:20:00+09:00", "role": "ceo", "area": GM_AREA,
         "event": "발화기록 오늘 것부터 체크", "result": "warn", "ref": "GM-TEST-01"},
        {"ts": "2026-08-04T09:23:00+09:00", "role": "ceo", "area": GM_AREA,
         "event": "오늘 기록으로 즉시 점검", "result": "ok", "ref": "GM-TEST-01"},
        {"ts": "2026-08-04T21:03:00+09:00", "role": "ceo", "area": GM_AREA,
         "event": "대표님 보고건 4가지 접수", "result": "warn", "ref": "GM-TEST-01"},
    ]
    result = _pair_gm_directives(sample)
    assert len(result) == 1, f"기대 미완 1건, 실제 {len(result)}건: {result}"
    assert result[0]["event"] == "대표님 보고건 4가지 접수", f"엉뚱한 건이 남음: {result[0]}"

    # 완료(ok)는 그 일의 도메인 area 로 적힌다 — 거르는 기준이 area 로 되돌아가면 여기서 걸린다.
    cross = [
        {"ts": "2026-08-10T18:22:00+09:00", "area": GM_AREA, "result": "warn",
         "event": "접수", "ref": "GM-TEST-02"},
        {"ts": "2026-08-10T18:30:00+09:00", "area": "자동화", "result": "ok",
         "event": "완료", "ref": "GM-TEST-02"},
    ]
    assert all(_is_gm_directive_log(d) for d in cross), "ref=GM- 인 줄이 대상에서 빠졌다"
    assert _pair_gm_directives([d for d in cross if _is_gm_directive_log(d)]) == [], \
        "도메인 area 로 적힌 완료가 접수를 못 닫는다"

    # 자동 접수 + 손 접수 중복(2026-08-25 시포 실측 — 전역 미완 6건이 전부 이 형태).
    dup = [
        {"ts": "2026-08-08T14:31:00+09:00", "area": GM_AREA, "result": "warn",
         "event": "접수", "detail": "받음 · 자동 접수(UserPromptSubmit)", "ref": "GM-TEST-04"},
        {"ts": "2026-08-08T14:32:00+09:00", "area": GM_AREA, "result": "warn",
         "event": "확인요청 8건 답변", "detail": "GM 이 회신", "ref": "GM-TEST-04"},
        {"ts": "2026-08-08T14:52:00+09:00", "area": "회원", "result": "ok",
         "event": "확인요청 8건 답변", "detail": "반영 4건", "ref": "GM-TEST-04"},
    ]
    assert _pair_gm_directives(dup) == [], "자동 접수 중복이 유령 미완을 만든다"
    # 자동 줄만 있고 완료가 없으면 진짜 미완 — 숨기면 안 된다.
    auto_only = [dup[0]]
    assert len(_pair_gm_directives(auto_only)) == 1, "자동 접수만 있는 진짜 미완이 사라졌다"

    # ok 가 warn 보다 먼저 찍히는 레이스(배506 실사고 — GM-20260807-23: ok 16:37·warn 16:38).
    # 건수 대조라면 순서와 무관하게 닫혀야 한다.
    race = [
        {"ts": "2026-08-07T16:37:00+09:00", "area": GM_AREA, "result": "ok",
         "event": "완료", "ref": "GM-TEST-03"},
        {"ts": "2026-08-07T16:38:00+09:00", "area": GM_AREA, "result": "warn",
         "event": "접수", "ref": "GM-TEST-03"},
    ]
    assert _pair_gm_directives(race) == [], "ok 가 warn 보다 먼저 찍히면 못 닫는다(배506)"

    print("[OK] _gm_directive selftest 통과 — 건수 대조(순서 역전 포함) + area 다른 완료도 짝으로 인정")


# ── 🤔 큐 자기정합 (2026-08-04 GM 지시 "줄기 3 큐 자기정합부터") ──────────────
#   오늘 하루에만 '이미 끝난 일을 안 끝난 줄 알고 다시 판' 게 7건(1건은 GM 시간 낭비).
#   원인 3가지를 여기 한 곳(부팅 때 항상 지나가는 이 보드)에서 표면화한다.
#   ★새 감시기·새 상태파일 금지(약속 L21) — 판정만 하고 **자동으로 닫지 않는다.**
#   ★판정은 의심형이다 — "끝났다"가 아니라 "끝난 듯, 확인 필요". 오탐이 나는 게 정상,
#     사람이 최종 판단한다.
try:
    from queue_dispatch import EXCLUDED_ROLES as _SELFCHECK_EXCLUDED_ROLES  # {"chro","cfo"}
except Exception:
    _SELFCHECK_EXCLUDED_ROLES = {"chro", "cfo"}  # 폴백 — import 실패해도 판정 대상은 계속 뺀다


def _is_excluded_role(owner: str) -> bool:
    """★시로(CHRO)·시뽀(CFO) 관련은 건드리지도 목록에 올리지도 않는다(GM 지시).
    코드 정본은 queue_dispatch.EXCLUDED_ROLES — 여기서 복제하지 않고 그대로 가져다 쓴다."""
    o = str(owner or "").strip()
    return o.lower() in _SELFCHECK_EXCLUDED_ROLES or _nick(o) in {"시로", "시뽀"}


_RE_NOTE_ENTRY = re.compile(r"\[20\d{2}-\d{2}-\d{2}[^\]]{0,40}\]")


def _tail_note(item: dict) -> str:
    """note의 **마지막** 날짜기록 이후만(가장 최신 항목). 옛 기록 속 '이미 끝남' 같은
    문구로 오탐나지 않게 — 실측(CTO-2026-07-22 배)에서 중간에 '이미 끝남'을 써도
    같은 기록 끝에 '진짜 남은 것'이 붙어 있으면 전체는 안 끝난 거라 오탐이면 안 된다."""
    # note 원문은 큐 항목엔 "note", 보드 항목(_build_item)엔 "_raw_summary"로 담긴다
    # (_last_touch와 동일 관례 — line ~650) — 하나만 보면 큐 항목에서 항상 빈다.
    note = str(item.get("note") or item.get("_raw_summary") or "")
    marks = list(_RE_NOTE_ENTRY.finditer(note))
    return note[marks[-1].start():] if marks else note


_OPEN_STATUSES = {"PENDING", "IN_PROGRESS", "보류", "대기", "ON_HOLD"}


def _is_open_status(item: dict) -> bool:
    st = str(item.get("status", ""))
    return st.upper() in _OPEN_STATUSES or st in _OPEN_STATUSES


def _is_new_today(item: dict) -> bool:
    """오늘 새로 뜬 배는 제외 — 아직 끝났을 리 없다."""
    today = dt.date.today().strftime("%Y-%m-%d")
    return str(item.get("enqueued_at") or "")[:10] == today


# ⚪ 실무진·GM·외부 이벤트 대기 배 — 정상 오픈이다. "끝난 듯"·"중복" 판정에서만 뺀다
#   (③note↔status 불일치는 오히려 이런 배를 잡는 게 목적이라 여기서 빼지 않는다).
_RE_EXTERNAL_WAIT = re.compile(
    r"(실무진.{0,6}(회신|응답|확인).{0,2}대기|GM.{0,4}(회신|결정|승인|확인|go).{0,2}대기|"
    r"외부.{0,6}(응답|대기)|회신\s*대기|응답\s*대기|결과\s*대기|승인\s*대기)"
)


def _is_external_wait(item: dict) -> bool:
    blob = str(item.get("next") or "") + " " + _tail_note(item)
    return bool(_RE_EXTERNAL_WAIT.search(blob))


# ①「끝난 듯」— note 자기증언(마지막 기록에 완료류 단어) ─────────────────────
_RE_SELF_DONE = re.compile(
    r"(이미\s*(수리|처리|완료|반영|배포|해결|고침)|처리\s*완료|배포\s*완료|해소\s*완료|"
    r"완료로\s*재확인)"
)


def _self_testimony_evidence(item: dict) -> str:
    tail = _tail_note(item)
    if not _RE_SELF_DONE.search(tail):
        return ""
    return "note 자기증언(완료류) — " + _truncate_word(_clean_summary(tail), 55)


# ①「끝난 듯」— note가 스스로 인용한 커밋해시가 실제 존재 + 그 커밋 제목이 '끝냈다'는
# 근거로 쓸 만함 ────────────────────────────────────────────────────────────
# ponytail: 파일명·함수명 자유텍스트 대조는 안 한다 — 실측(2026-08-04)으로 "배147"
#   같은 번호가 무관한 자동커밋 문구에 고정 인용되는 걸 확인했다(scripts/post_commit_push.py
#   의 정형 문구). note가 직접 인용한 커밋해시만 존재 검증한다 — 오탐이 낮은 신호만 쓴다.
#   더 정밀하게(파일 diff 대조)는 이 신호로 오탐이 실측되면 확장한다.
# ★2026-08-04 실측 보정: 커밋이 존재하기만 해도 다 근거는 아니다 — ship_no 300 실측에서
#   인용된 커밋이 "GM 지시 배 등록"(그 배를 **만든** 커밋)이었다. 배를 만든 커밋은 끝냈다는
#   근거가 아니라서 뺀다.
_RE_COMMIT_REGISTER_ONLY = re.compile(r"배\s*(등록|생성)")


def _cited_commit_evidence(item: dict) -> str:
    tail = _tail_note(item)
    m = re.search(r"커밋\s*([0-9a-f]{7,12})", tail)
    if not m:
        return ""
    h = m.group(1)
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%s", h], cwd=_REPO,
                            capture_output=True, text=True, timeout=5,
                            encoding="utf-8", errors="replace")
        if r.returncode != 0 or not r.stdout.strip():
            return ""
        subject = r.stdout.strip()
    except Exception:
        return ""
    if _RE_COMMIT_REGISTER_ONLY.search(subject):
        return ""  # 배를 만든 커밋이지 끝냈다는 근거가 아니다
    return f"note가 인용한 커밋 {h} 실재 확인({_truncate_word(subject, 35)}) — " \
        + _truncate_word(_clean_summary(tail), 35)


# ② 중복 배 — 같은 담당의 DONE과 열린 상태가 제목 겹쳐 공존 ───────────────────
_RE_TITLE_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")


def _title_tokens(title: str) -> set[str]:
    t = _RE_META_BRACKET.sub("", str(title or ""))
    t = re.sub(r"^\[[^\]]{1,10}\]\s*", "", t)  # [시토] 역할 태그
    return set(_RE_TITLE_TOKEN.findall(t))


def _duplicate_evidence(item: dict, dones: list[dict]) -> str:
    okeys = _title_tokens(item.get("title", ""))
    if len(okeys) < 2:
        return ""
    owner = item.get("owner")
    for d in dones:
        if d is item or d.get("owner") != owner:
            continue
        dkeys = _title_tokens(d.get("title", ""))
        if len(dkeys) < 2:
            continue
        overlap = okeys & dkeys
        if len(overlap) >= 2 and len(overlap) / min(len(okeys), len(dkeys)) >= 0.5:
            return (f"완료 배 「{str(d.get('title',''))[:30]}…」와 제목 중복 의심 — "
                     f"겹침: {'·'.join(sorted(overlap))[:40]}")
    return ""


# ③ note↔status 어긋남 — note가 '정박 전환'인데 status는 여전히 열린 진행중 ──────
#   ⚓ 세계관(CLAUDE.md §3-1): 정박 = status가 PENDING/ON_HOLD(⚓)여야 한다. note는
#   정박을 선언했는데 status가 그대로 IN_PROGRESS면 기록만 갱신되고 상태 칸이 안 따라간
#   전형(실측: 배206 — "⚓ 정박 전환" note인데 status IN_PROGRESS 그대로).
#   ★_tail_note(마지막 날짜기록만)를 안 쓴다 — 실측(배206)에서 '정박 전환' 선언 뒤에도
#   그날 안에 다른 화제(회장님 지시사항 등) 기록이 이어 붙어, 마지막 기록만 보면
#   정박 선언 자체를 놓친다. 그래서 note 전체에서 '정박' 선언을 찾고, 그 **뒤**에
#   '정박 해제' 가 없으면(=아직 안 풀림) status 와 대조한다.
_RE_NOTE_PARKED = re.compile(r"정박\s*(전환|확정|선언)")
_RE_NOTE_UNPARKED = re.compile(r"정박\s*해제")


def _note_status_mismatch(item: dict) -> str:
    note = str(item.get("note") or item.get("_raw_summary") or "")
    matches = list(_RE_NOTE_PARKED.finditer(note))
    if not matches:
        return ""
    last = matches[-1]
    if _RE_NOTE_UNPARKED.search(note[last.end():]):
        return ""  # 이후 '정박 해제' 기록이 있음 — 다시 열린 게 맞음
    if str(item.get("status", "")).upper() in {"PENDING", "ON_HOLD"} \
            or item.get("status") in {"대기", "보류"}:
        return ""  # 이미 정박 상태 — 정합, 문제 없음
    ctx = note[max(0, last.start() - 5):last.end() + 55]
    return (f"note='정박 {last.group(1)}' 기록(이후 해제 없음)인데 status={item.get('status')}(⚓ 아님) — "
            + _truncate_word(_clean_summary(ctx), 45))


def _self_consistency_findings(
    items: list[dict],
) -> tuple[list[tuple[dict, str]], list[tuple[dict, str]], list[tuple[dict, str]]]:
    """3종 판정 — (①끝난 듯, ②중복 의심, ③note↔status 불일치) 각각 (item, evidence) 리스트,
    오래된 순(전체, 캡 없음 — 캡은 렌더에서 건다). 자동으로 닫지 않는다 — 표면화만."""
    dones = [it for it in items if str(it.get("status")) in STATUS_DONE
              or str(it.get("status", "")).upper() in STATUS_DONE]
    looks_done: list[tuple[dict, str]] = []
    dupes: list[tuple[dict, str]] = []
    mismatch: list[tuple[dict, str]] = []
    for it in items:
        if not _is_open_status(it) or _is_new_today(it) or _is_excluded_role(it.get("owner", "")):
            continue
        # ③은 '외부 대기' 배를 잡는 게 목적이라 여기서만 external-wait 필터를 안 건다.
        m3 = _note_status_mismatch(it)
        if m3:
            mismatch.append((it, m3))
        if _is_external_wait(it):
            continue
        ev1 = _self_testimony_evidence(it) or _cited_commit_evidence(it)
        if ev1:
            looks_done.append((it, ev1))
        ev2 = _duplicate_evidence(it, dones)
        if ev2:
            dupes.append((it, ev2))
    key = lambda pair: -(_stall_days(pair[0]) or 0)
    looks_done.sort(key=key)
    dupes.sort(key=key)
    mismatch.sort(key=key)
    return looks_done, dupes, mismatch


# ── ❓ 안 물어봄 (2026-08-13 웰리 — "실무진 전달 20건" 실측 파생, 배521·578 실사고) ──
#   note/next에 "확인 대기" 류를 적어 놓고 실제로 그 질문을 실무진에게 띄운 적이 없는 배.
#   staff_message 필드 자체가 없는 배(GM전용·AI내부간 확인)는 대상에서 뺀다 — 이 필드는
#   coo·cpo 실무진 카톡 릴레이 배만 쓴다(2026-08-06 배423 짝). 판정 둘 중 하나면 걸린다:
#   ①staff_message가 비어 있다(초안조차 없음) ②채워져 있어도 최근 발신 로그에 제목
#   핵심 단어가 한 번도 안 나온다(써놓고 안 보냄). 로그는 최근 N일치만 본다(전수 스캔 비용).
_RE_WAIT_ASK = re.compile(r"확인\s*대기|회신\s*대기|확인\s*요청|문의드림|여쭤")
_UNASKED_LOG_WINDOW_DAYS = 21  # 실측 최장 사례(배117)가 19일째 — 여유 두고 3주
_UNASKED_STOPWORDS = {"확인", "요청", "대기", "완료", "처리", "실측", "오늘", "여전히",
                       "종합접수처", "중간관리자"}  # 거의 모든 일일묶음 메시지에 등장하는 잡음 단어


@functools.lru_cache(maxsize=1)
def _recent_kakao_entries() -> list[tuple[str, str]]:
    """최근 N일치 카톡 발신 로그 (파일 날짜, 본문) 캐시(프로세스당 1회만 읽는다).
    파일명 kakao_sent-YYYY-MM-DD.log 의 날짜를 그대로 발신일로 쓴다."""
    files = sorted((_REPO / "logs").glob("kakao_sent-*.log"))[-_UNASKED_LOG_WINDOW_DAYS:]
    out = []
    for fp in files:
        date = fp.stem.replace("kakao_sent-", "")
        try:
            for line in fp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    out.append((date, json.loads(line).get("text", "")))
        except Exception:
            continue
    return out


def _recent_kakao_text() -> str:
    return "\n".join(t for _, t in _recent_kakao_entries())


def _last_sent_date(token: str) -> str:
    """token 이 담긴 가장 최근 발신일(YYYY-MM-DD) — 없으면 빈 문자열."""
    dates = [d for d, t in _recent_kakao_entries() if token in t]
    return max(dates) if dates else ""


# ponytail: 토큰[0]에 조사가 붙으면("분류값이") 로그 원문("등록분류")과 안 맞아 간헐
#   오탐/누락이 난다(배356 실측 2026-08-13). 형태소 분석은 과함 — 안 고침. 좁히려면
#   상위 토큰 1개가 아니라 상위 2개가 모두 없을 때만 걸리게. 지금은 오탐이 3~5건대로
#   감당 범위이고, 놓치는 쪽보다 더 잡는 쪽이 안전해 이대로 둔다. 이 한계는 아래
#   「⏳ 답 없음」에도 그대로 물려받는다(같은 토큰 추출을 재사용하므로).
def _top_title_token(item: dict) -> str:
    # 순수 숫자 토큰(날짜 "2026"·"08" 등)은 항상 잡음이라 뺀다. 부분일치로 걸러야
    # "중간관리자에게"처럼 조사가 붙은 형태도 stopword 로 잡힌다(완전일치 set 뺄셈이면 못 잡음).
    tokens = [t for t in _title_tokens(item.get("title", ""))
              if not t.isdigit() and not any(sw in t for sw in _UNASKED_STOPWORDS)]
    tokens.sort(key=lambda t: (-len(t), t))  # 동률이면 사전순 — 실행마다 픽이 안 흔들리게
    return tokens[0] if tokens else ""


def _unasked_evidence(item: dict) -> str:
    if not item.get("_has_staff_field"):
        return ""  # 실무진 릴레이 채널 자체를 안 쓰는 배(GM전용·AI내부) — 대상 아님
    blob = str(item.get("_raw_summary") or "") + " " + str(item.get("next") or "")
    if not _RE_WAIT_ASK.search(blob):
        return ""
    sm = str(item.get("staff_message") or "").strip()
    if not sm:
        return "staff_message 빈 채로 방치 — 질문 초안조차 없음"
    token = _top_title_token(item)
    if token and token not in _recent_kakao_text():
        return f"staff_message는 있는데 최근 {_UNASKED_LOG_WINDOW_DAYS}일 발신 로그에 '{token}' 0건 — 안 보낸 듯"
    return ""


def _unasked_findings(items: list[dict]) -> list[tuple[dict, str]]:
    out = []
    for it in items:
        if not _is_open_status(it) or _is_new_today(it) or _is_excluded_role(it.get("owner", "")):
            continue
        if it.get("audience") == "ai":
            continue
        ev = _unasked_evidence(it)
        if ev:
            out.append((it, ev))
    out.sort(key=lambda pair: -(_stall_days(pair[0]) or 0))
    return out


# ── ⏳ 답 없음 (2026-08-13 웰리 — 「❓ 안 물어봄」의 짝. 물었는지는 위에서 이미 본다,
#   여기는 "물었는데 그 뒤로 배가 안 움직였나"만 본다. 카톡 회신 원문은 안 읽는다 —
#   자유 문장을 기계가 "이건 답이다"로 잘못 판정하면 조용히 틀린다. 그래서 판정은
#   딱 두 가지만: ①실제 발신 기록이 있다(_last_sent_date 재사용 — 같은 계산 두 번 안 함)
#   ②그 뒤로도 여전히 열려 있다("진전 없음" = status 그대로, 이미 findings 필터가 봄).
#   ★mod_date(note 갱신일)는 신호로 안 쓴다 — AI가 내부 정리로 note 만 건드려도 mod_date
#   가 갱신돼, 그 갱신을 "진전"으로 오인하면 실측(배371 등, 08-06 발신·08-07 내부
#   갱신)이 걸러져 놓친다. 오탐(내부 노이즈를 답 없음으로 잘못 잡음)보다 누락(진짜
#   방치된 배를 놓치는 것)이 더 위험해 이대로 둔다 — 오늘 「안 물어봄」과 같은 원칙. ──
_NO_REPLY_MIN_DAYS = 3  # 하루 만에 띄우면 노이즈, 너무 길면 오늘 같은 19일 적체가 또 난다


def _no_reply_evidence(item: dict) -> str:
    if not item.get("_has_staff_field"):
        return ""
    sm = str(item.get("staff_message") or "").strip()
    if not sm:
        return ""  # 초안조차 없는 건 「안 물어봄」 몫
    token = _top_title_token(item)
    if not token:
        return ""
    sent = _last_sent_date(token)
    if not sent:
        return ""  # 발신 기록 자체가 없는 건 「안 물어봄」 몫
    days = (dt.date.today() - dt.datetime.strptime(sent, "%Y-%m-%d").date()).days
    if days < _NO_REPLY_MIN_DAYS:
        return ""
    return f"{sent} 발신 이후 {days}일째 답 없음(배는 여전히 열려 있음)"


def _no_reply_findings(items: list[dict]) -> list[tuple[dict, str]]:
    out = []
    for it in items:
        if not _is_open_status(it) or _is_new_today(it) or _is_excluded_role(it.get("owner", "")):
            continue
        if it.get("audience") == "ai":
            continue
        ev = _no_reply_evidence(it)
        if ev:
            out.append((it, ev))
    out.sort(key=lambda pair: -(_stall_days(pair[0]) or 0))
    return out


def build_board(gas_items: list[dict], queue_items: list[dict],
                role: str = "", sent_by_role: list[dict] | None = None) -> tuple[str, dict]:
    """보드 텍스트 + 섹션 dict 반환.
    3섹터: 🚢 진행중 / ⚓ 대기중 / 🏁 입항 완료 (오늘)
    표 칼럼(5개): 배 | 담당 | 진행명 | 간단설명 | 본질에 대한 핵심조언
    배 칸=난이도 배 아이콘만 · 상태는 섹터 제목에만 · 담당=닉네임.

    role/sent_by_role: 쿵짝 회수(2026-08-04) — role이 다른 역할에 띄운 배 중 답 없는 것을
    「🔔 멈춰 있는 배」섹션에 얹는다. sent_by_role은 역할 슬라이스(owner==role만 남김) **전**의
    원본 queue_items 스냅샷이어야 한다 — 슬라이스 후엔 내가 보낸 배(owner=남)가 이미 잘려 없다."""
    all_items = gas_items + queue_items
    secs = _classify(all_items)

    today  = dt.date.today().strftime("%Y-%m-%d")
    wd_kor = ["월", "화", "수", "목", "금", "토", "일"][dt.date.today().weekday()]

    n_urgent   = len(secs["urgent"])
    n_appr     = len(secs["appr"])
    n_inflight = len(secs["appr_inflight"])
    n_done     = len(secs["done"])

    inprog  = [it for it in secs["today"] if it["status"] in STATUS_INPROGRESS or it["status"].upper() in STATUS_INPROGRESS]
    waiting = [it for it in secs["today"] if it not in inprog]

    # ★같은 배를 두 번 설명하지 않는다 (2026-08-13 · GM "고도화된 부분을 단순화").
    #   실측: 시토 항로 14,121자 · 표 57줄이 배 34척을 그렸다 — 중복으로 더 실린 줄 23개
    #   (303·338·464 는 4번씩). 진단 표(안 닫힌 배·쿵짝·짝·자기정합)는 '이 배가 이런 상태다'만
    #   말하면 되고, 간단설명·핵심조언은 아래 본 섹터(진행중/대기중/입항)에서 한 번 읽으면 된다.
    #   그래서 본 섹터에도 나오는 배는 진단 표에서 설명·조언 두 칸을 접는다(제목·담당·꼬리표는 유지).
    def _ship_key(it):
        return f"{str(it.get('owner') or it.get('clevel') or '')}|{it.get('short_no') or it.get('ship_no') or it.get('title')}"
    _main_keys = {_ship_key(it) for it in (inprog + waiting + list(secs["done"]))}
    def _brief(it):
        return _ship_key(it) in _main_keys
    n_total = n_urgent + len(inprog) + len(waiting) + n_appr

    _cnt_rows = [
        ("🚢 진행중",              str(len(inprog))),
        ("⚓ 대기중",               str(len(waiting))),
        ("🏁 입항 완료 (오늘)", str(n_done)),
        ("🔴 급한 입항 (마감임박)", str(n_urgent)),
        ("🔴 GM 결재 대기",        str(n_appr)),
    ]
    if n_inflight:
        _cnt_rows.append(("⏳ 결재 진행 중 (타 결재자)", str(n_inflight)))
    if secs["autonomy"]:
        _cnt_rows.append(("🤖 자율화 미션 (자율현황行)", str(len(secs["autonomy"]))))
    if secs["routine"]:
        _cnt_rows.append(("🔁 반복 루틴 (끝이 없는 일)", str(len(secs["routine"]))))
    if secs["trigger"]:
        _cnt_rows.append(("🪝 조건 대기 (사건 오면 시작)", str(len(secs["trigger"]))))
    _cnt_rows.append(("진행 합계",                    str(n_total)))
    summary_table = _box_table(_cnt_rows)

    lines: list[str] = []
    lines.append(f"🧭 오늘의 항로  {today} ({wd_kor})")
    lines.append("━" * 36)
    lines.append(summary_table)

    # ── 🎯 오늘 반드시 끝낼 것 (GM 2026-08-10) — 보드 맨 위. 못 지킨 건 조용히 안 사라진다 ──
    mf_overdue = secs["must_finish_overdue"]
    mf_today   = secs["must_finish_today"]
    if mf_overdue or mf_today:
        lines.append("")
        if mf_overdue:
            lines.append(f"### 🔴 못 지킴 {len(mf_overdue)}척 — 반드시 끝낼 것 지남")
            lines.append(_md_table([
                _item_to_row(it, ship_col_extra=f"{_must_finish_days_late(it)}일 지남")
                for it in mf_overdue]))
        if mf_today:
            lines.append("### 🎯 오늘 반드시 끝낼 것")
            lines.append(_md_table([_item_to_row(it) for it in mf_today]))

    # 항로 정합경고
    try:
        from queue_integrity_check import board_banner
        _bn = board_banner(gas_items=gas_items)
        if _bn:
            lines.append(_bn)
    except Exception:
        pass

    # ── 🔔 멈춰 있는 배 (2026-07-31 GM 지시 "진행 안 된 건은 집요하게 체크해서 완료하게 서포트") ──
    #   새 알림·새 예약을 만들지 않는다(약속 L21) — 모든 표면(부팅 셸·G1 보드·08:00 보고)이 이미
    #   지나가는 이 보드에 얹는다. 한 곳에만 띄우면 그 화면을 안 여는 날 그냥 넘어간다.
    stalled = _stalled(secs["today"])
    sent_unanswered = _sent_unanswered(sent_by_role or [], role)
    received_unanswered = _received_unanswered(sent_by_role or [], role)
    gm_gaps = _gm_directive_unresolved(role)
    for it in sent_unanswered:
        it["_ship"] = classify_ship({
            "title": it["title"], "priority": it["priority"], "deadline": it["end_date"]})
    for it in received_unanswered:
        it["_ship"] = classify_ship({
            "title": it["title"], "priority": it["priority"], "deadline": it["end_date"]})
    # 🤔 큐 자기정합 3종(2026-08-04) — 같은 블록에 붙인다(새 ### 헤더 금지·약속 L21).
    looks_done, dupes, mismatch = _self_consistency_findings(all_items)
    unasked = _unasked_findings(all_items)
    no_reply = _no_reply_findings(all_items)
    _SELFCHECK_CAP = 7
    for pair_list in (looks_done, dupes, mismatch, unasked, no_reply):
        for it, _ev in pair_list:
            it["_ship"] = classify_ship({
                "title": it["title"], "priority": it["priority"], "deadline": it["end_date"]})
    if (stalled or sent_unanswered or received_unanswered
            or looks_done or dupes or mismatch or unasked or no_reply or gm_gaps):
        lines.append("")
        # 표 제목이 무엇을 센 값인지 스스로 말한다(배540) — 옛 제목('마지막 기록 이후')은
        # 실제 기준과 어긋나 있었다. 꼬리표: N일째=안 닫힌 날수 · 기록N일전=note 공백.
        lines.append(f"### 🔔 안 닫힌 배 {len(stalled)}척 "
                     f"— 뜬 지 {_STALL_MIN_DAYS}일 넘게 안 닫힌 순(기록이 3일 이상 없으면 뒤에 함께 적음)")
        if stalled:
            lines.append(_md_table([_item_to_row(it, ship_col_extra=_stall_tag(it), brief=True,
                                                 brief_note=("↓ 아래 본 섹터에" if _brief(it) else ""))
                                    for it in stalled]))
        if sent_unanswered:
            lines.append(f"쿵짝 — 내가 띄우고 답 없는 배 {len(sent_unanswered)}척 "
                          "(보낸이=나 · 담당=받는이 · N일째 오래된 순)")
            lines.append(_md_table([_item_to_row(it, ship_col_extra=_stall_tag(it, _open_days(it)), brief=True,
                                                 brief_note="")
                                    for it in sent_unanswered]))
        if received_unanswered:
            lines.append(f"짝 — 남이 내게 띄우고 내가 답 안 한 배 {len(received_unanswered)}척 "
                          "(보낸이=상대 · 담당=나 · N일째 오래된 순)")
            lines.append(_md_table([_item_to_row(it, ship_col_extra=_stall_tag(it, _open_days(it)), brief=True,
                                                 brief_note=("↓ 아래 본 섹터에" if _brief(it) else ""))
                                    for it in received_unanswered]))
        if gm_gaps:
            lines.append(f"📨 GM 요청 미완 {len(gm_gaps)}건 — 접수(warn)만 있고 완료(ok) 짝 없음, 오래된 순")
            for g in gm_gaps:
                tag = "🔴" if g["days"] >= 1 else "🟡"
                lines.append(f"  - {tag} {g['days']}일째 · {g['ts']} · {g['event']} (ref={g['ref']})")
        for label, pair_list in (
            ("🤔 끝난 듯 — 확인 필요", looks_done),
            ("🔁 중복 의심", dupes),
            ("⚠️ note↔status 불일치", mismatch),
            ("❓ 안 물어봄 — 확인 대기라 적고 질문은 안 나감", unasked),
            ("⏳ 답 없음 — 물었는데 그 뒤로 배가 안 움직임", no_reply),
        ):
            if not pair_list:
                continue
            shown = pair_list[:_SELFCHECK_CAP]
            extra = f" (외 {len(pair_list) - len(shown)}척)" if len(pair_list) > len(shown) else ""
            lines.append(f"{label} {len(shown)}척{extra} — 판정은 의심형·자동 종료 안 함, 사람 확인")
            rows = []
            for it, ev in shown:
                base = _item_to_row(it, ship_col_extra=_stall_tag(it), brief=True, brief_note="")
                rows.append((base[0], base[1], base[2], ev, "👉 status/note 대조 확인"))
            lines.append(_md_table(rows))

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

    # ── 🤖 자율화 미션 포인터 (항로 제외, 자율현황行) ──
    if secs["autonomy"]:
        lines.append(f"🤖 자율화 미션 {len(secs['autonomy'])}건 — 항로 제외, 자율현황 보드에서 관리")
        lines.append("    https://wellperion-cao.github.io/wellperion-automation/%EC%9E%90%EC%9C%A8%ED%98%84%ED%99%A9.html")

    # ── 🔁 반복 루틴 · 🪝 조건 대기 (진행대기 숫자 밖 · GM 2026-08-16) ──
    #   숨기지 않는다 — 제목까지 그대로 보여 주되 '오늘 밀린 일'과 섞지 않는다.
    for _key, _icon, _label, _why in (
        ("routine", "🔁", "반복 루틴", "매일·매주 도는 일 — 완료 도장이 없다"),
        ("trigger", "🪝", "조건 대기", "사건이 와야 시작된다"),
    ):
        if not secs[_key]:
            continue
        lines.append(f"\n### {_icon} {_label} {len(secs[_key])}건 — 진행대기 숫자 밖 ({_why})")
        lines.append(_md_table([_item_to_row(it) for it in secs[_key]]))

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
    done_all = secs["done"]
    if done_all:
        done_rows = []
        for it in secs["done"]:
            has_next = bool(str(it.get("next") or "").strip())
            tag = (("🔗 " if has_next else "") + _saw_badge(it)).strip()
            done_rows.append(_item_to_row(it, ship_col_extra=tag))
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



# ── 부팅 슬라이스: kpi.json / gm_profile.md (배433 · 2026-08-06 시토) ──────────
#   둘 다 파일은 한 벌 그대로(약속 L01) — hangro_board가 이미 부팅마다 --role로
#   불리는 자리라 읽는 순간에만 잘라 준다(큐 슬라이스와 같은 원리 · 배10369).
_RE_HTML_TAG = re.compile(r"<[^>]+>")


def _kpi_slice(role_slug: str) -> str:
    """ssot/kpi.json → roles.{role}.kpi_html 한 줄만(§6 선언표 '담당 KPI' 행 전용).
    실측(2026-08-06): 파일 전체 12,694자 중 한 역할이 쓰는 건 이 필드뿐(297자 수준) —
    나머지는 역할분담 결정 경위(다른 역할 몫)라 부팅에 안 실어도 된다."""
    if not role_slug or not KPI_PATH.exists():
        return ""
    try:
        data = json.loads(KPI_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] kpi.json 슬라이스 실패: {e}", file=sys.stderr)
        return ""
    role = data.get("roles", {}).get(role_slug)
    if not role:
        return ""
    kpi = _RE_HTML_TAG.sub("", str(role.get("kpi_html", ""))).strip()
    if not kpi:
        return ""
    nick = role.get("nickname", "")
    return (f"\n📌 담당 KPI({nick}) — {kpi}\n"
            "※ 역할분담 결정 경위 등 전체는 ssot/kpi.json 파일 자체를 여세요.")


def _page_score_slice(role_slug: str) -> str:
    """status/page_score.json → 내 소유 화면 중 점수 낮은 것 5개 (배478 · GM 지시 2026-08-08).

    GM 원문: "완성도를 말도안되게 높게 잡으니 문제점이 보일리가 없을 것 같은데?" —
    웰리가 배465 로 다시 채점했지만 결과가 화면 안 표로만 있어 **아침 자가점검이 못 읽었다.**
    점수판이 장식이 되면 실패라고 그 배가 스스로 적어 뒀다. 여기서 부팅 화면에 올려
    낮은 점수가 곧 그날 볼 것이 되게 한다. 새 화면을 만들지 않고 이미 매일 지나가는
    이 자리에 얹는다(약속 L21)."""
    path = _REPO / "status" / "page_score.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] page_score.json 슬라이스 실패: {e}", file=sys.stderr)
        return ""
    mine = [p for p in data.get("pages", []) if p.get("role") == role_slug]
    if not mine:
        return ""
    mine.sort(key=lambda p: p.get("score", 100))
    low = [p for p in mine if p.get("score", 100) < 85][:5]
    if not low:
        return (f"\n📉 내 화면 완성도 — {len(mine)}개 전부 85% 이상. "
                "(정본 = status/page_score.json 손 관리 · 재채점은 이 파일을 직접 고친다, "
                "배641 · 구 원천 GM업무.html #sec-erp-score 는 08-15 삭제됨)")
    lines = [f"  {p['score']:3}%  {p['name']} — {p['note'][:52]}" for p in low]
    return (f"\n📉 내 화면 완성도 낮은 순 {len(low)}개 (전체 {len(mine)}개 중 85% 미만)\n"
            + "\n".join(lines)
            + "\n※ 이 줄이 오늘 볼 것이다. 정본 = status/page_score.json 손 관리 · "
              "재채점은 이 파일을 직접 고친다(배641)")


def _reception_watch_slice(role_slug: str) -> str:
    """status/reception_watch.json → 접수 정체 요약, COO 부팅화면 전용(GM 지시 2026-08-15
    "놓치지 않게 계속 챙겨줘").

    소유 스크립트(report_stream_2b_reception.py)가 이미 매일 도는 발송 직전 reg_list를
    읽는 자리에 스냅샷만 남기고(약속 L21 — 새 스크립트·새 예약 없음), 여기서는 부팅 때
    읽어 보여주기만 한다. 다른 역할 부팅 화면에는 안 뜬다."""
    if role_slug != "coo":
        return ""
    path = _REPO / "status" / "reception_watch.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] reception_watch.json 슬라이스 실패: {e}", file=sys.stderr)
        return ""
    by_dept = data.get("by_dept") or {}
    if not by_dept and not data.get("lost_items_open"):
        return ""
    parts = [f"{d} {info.get('open', 0)}건(최장 {info.get('max_age_days', 0)}일)"
             for d, info in sorted(by_dept.items(), key=lambda kv: -kv[1].get("open", 0))]
    line1 = "📮 접수 정체 — " + (" · ".join(parts) if parts else "없음")
    # 마감 기준 = 「처리 완료」 도장(GM 확정 2026-08-15). 실무진이 실제로 누르는 것이 그것이고,
    # 직원 신고·익명 접수처럼 회원 안내가 애초에 필요 없는 건도 있다. 회원 안내 공란은 참고로만 뒤에 둔다.
    line2 = (f"   3일 이상 {data.get('overdue_3d', 0)}건 · 7일 이상 {data.get('overdue_7d', 0)}건 · "
             f"(분실물 {data.get('lost_items_open', 0)}건은 따로 셈) "
             f"· 참고: 회원 안내 공란 {data.get('member_reply_open', 0)}건")
    stale = ""
    try:
        age_h = (dt.datetime.now()
                 - dt.datetime.strptime(str(data.get("generated_at", "")), "%Y-%m-%d %H:%M:%S")
                 ).total_seconds() / 3600
        if age_h >= 24:
            stale = f"\n   ⚠️ 스냅샷 {age_h / 24:.1f}일 전 갱신 — 낡았을 수 있음"
    except Exception:
        pass
    # 🧳 습득물 월 사이클(GM 지시 2026-08-15 "습득물 현황도 일정에 맞게끔 정리") — 값이
    # 없으면(구 스냅샷·조회 실패) 이 줄만 조용히 건너뛴다.
    lf = data.get("lost_found") or {}
    lf_line = ""
    if lf:
        lf_line = (f"\n🧳 습득물 — 이번 달 처분 대상 {lf.get('dispose_this_month', 0)}건 · "
                   f"공지 중 {lf.get('notice_this_month', 0)}건 · "
                   f"다음 달 처분 예정 {lf.get('dispose_next_month', 0)}건")
    return (f"\n{line1}\n{line2}{stale}{lf_line}\n"
            "※ 원천 = status/reception_watch.json · "
            "갱신 = python scripts/report_stream_2b_reception.py")


_GM_PROFILE_SECTIONS = {"선호", "습관", "자주 놓치는 것"}
_RE_MD_H2 = re.compile(r"(?m)^## ")


def _gm_profile_slice() -> str:
    """status/gm_profile.md → 선호·습관·자주 놓치는 것 3섹션만(전체 5,854자 중 ~1,700자).
    나머지(표면점검·북극성·루틴준수 등)는 자가점검용 상세라 매 부팅에 안 실어도 된다.
    파일은 gm_profile_builder.py가 매일 통째로 재생성하므로 별도 요약 파일을 만들지
    않고 여기서 읽는 순간에만 자른다."""
    if not GM_PROFILE_PATH.exists():
        return ""
    try:
        text = GM_PROFILE_PATH.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[WARN] gm_profile.md 슬라이스 실패: {e}", file=sys.stderr)
        return ""
    picked = []
    for part in _RE_MD_H2.split(text)[1:]:
        head = part.split("\n", 1)[0].strip()
        if head in _GM_PROFILE_SECTIONS:
            picked.append("## " + part.rstrip())
    if not picked:
        return ""
    return ("\n📋 GM 프로필 요약(부팅 슬라이스) — 선호·습관·자주 놓치는 것\n"
            + "\n\n".join(picked)
            + "\n※ 전체(표면점검·북극성·루틴준수 등)는 status/gm_profile.md 파일 자체를 여세요.")


_MIDMGR_SENDERS = {
    "웰페리온 운영부 이경연 실장님": "이경연 실장",
    "웰페리온 시설부 이정헌 소장님": "이정헌 소장",
    "라우열": "나우열M",
}
_RE_MIDMGR_TAG = re.compile(r"^\[([^\]]+)\] \[(?:오전|오후) \d{1,2}:\d{2}\] ?(.*)$")
_RE_MIDMGR_DATE = re.compile(r"^-+ (\d{4}년 \d{1,2}월 \d{1,2}일.*?) -+$", re.MULTILINE)


def _latest_midmgr_file() -> Path | None:
    if not MIDMGR_ARCHIVE_DIR.exists():
        return None
    files = sorted(MIDMGR_ARCHIVE_DIR.glob("*/★중간관리자_auto_*.txt"))
    return files[-1] if files else None


_RE_MIDMGR_SAVED = re.compile(r"저장한\s*날짜\s*:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})")


def _midmgr_saved_at(text: str) -> tuple[str, str, float | None]:
    """카톡 아카이브 첫머리의 '저장한 날짜'와, 지금으로부터 얼마나 지났는지.

    이 파일은 **만들어진 순간까지**만 담는다 — 그 뒤에 온 회신은 없다. 그 사실을
    화면에 안 적어서 2026-08-13 에 소장님 회신 7건(16:29~18:44)을 '회신 없음'으로
    GM 께 보고했다. 돌려주는 값: (사람이 읽는 저장시각, 제목 뒤에 붙일 경과 꼬리표, 경과시간(h)).
    """
    m = _RE_MIDMGR_SAVED.search(text[:400])
    if not m:
        return "", " · ⚠️ 수집 시각 미상", None
    day, hm = m.group(1), m.group(2)
    stamp = f"{day} {hm}"
    try:
        saved = dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M")
    except ValueError:
        return stamp, "", None
    hours = (dt.datetime.now() - saved).total_seconds() / 3600
    if hours < 1:
        return stamp, "", hours
    if hours < 3:
        return stamp, f" · {int(hours)}시간 전 수집", hours
    return stamp, f" · ⚠️ {int(hours)}시간 전 수집 — 그 뒤 회신은 안 보인다", hours


def _midmgr_reply_slice(role_slug: str) -> str:
    """어제 ★중간관리자 방 회신 원문 — 실장·소장·나우열M 3명만, 웰리(ceo)만 본다(GM 지시 2026-08-13).
    "회신 받으면 웰리가 아침에 파악해서 신뢰할 수 있는 현황을" — 파악은 사람이 한다.
    회신을 자동으로 해석·판정하지 않는다(오늘 배537과 같은 이유 — 자유 문장을 기계가 판정하면
    조용히 틀린다). 이 함수는 모아서 보여주는 것까지만. 새 파일 없음 — 이미 도는 07:30 카톡
    아카이브(1. AI자료_아카이브/11_카카오톡/★중간관리자/)를 읽는다(약속 L21)."""
    if role_slug != "ceo":
        return ""
    # ★못 읽은 것과 회신이 없는 것은 다르다 (배613 · 웰리 실측 2026-08-14).
    #   수집기(kakao_export_chat.py)는 화면이 잠겨 있으면 실패하는데, 실패해도 아무 데도 안 남고
    #   이 칸은 옛 수집본을 그대로 보여 준다. 그래서 "회신 없음"이 두 가지 뜻으로 읽혔다 —
    #   ①정말 아무도 안 남겼다 ②우리가 오늘 것을 못 받아 왔다. 2026-08-13 에 ②를 ①로 읽고
    #   "이정헌 소장 회신 없음"이라고 GM 께 잘못 보고했다(그때 회신 7건이 이미 와 있었다).
    #   여기서는 새 감시기를 만들지 않는다(약속 L21) — 수집본이 오늘 것인지만 보고, 아니면
    #   "회신 없음" 대신 "확인 못 함"이라고 적는다. 없는 정보를 있는 것처럼 만들지 않는다.
    f = _latest_midmgr_file()
    if not f:
        return ("\n📩 실무진 회신 — ❌ 확인 못 함(수집본이 하나도 없다)\n"
                "  회신이 없는 게 아니라 우리가 못 읽은 것이다 — 이 상태로 '회신 없음'이라 보고하지 말 것.\n"
                "  받아오기: C:/Python314/python.exe scripts/kakao_export_chat.py --room-key mgr\n"
                "  (화면이 잠겨 있으면 실패한다 — 잠금 해제 후 다시)")
    try:
        text = f.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[WARN] 중간관리자 아카이브 읽기 실패: {e}", file=sys.stderr)
        return (f"\n📩 실무진 회신 — ❌ 확인 못 함(수집본 파일을 못 열었다: {type(e).__name__})\n"
                "  회신이 없는 게 아니라 우리가 못 읽은 것이다 — '회신 없음'이라 보고하지 말 것.")
    date_marks = list(_RE_MIDMGR_DATE.finditer(text))
    if not date_marks:
        return ""
    last = date_marks[-1]
    collected_date = last.group(1)
    body = text[last.end():]

    msgs: dict[str, list[str]] = {label: [] for label in _MIDMGR_SENDERS.values()}
    cur_label = None
    for line in body.splitlines():
        m = _RE_MIDMGR_TAG.match(line)
        if m:
            cur_label = _MIDMGR_SENDERS.get(m.group(1))  # 우리 3명 아니면 None(다른 사람 줄 안 섞임)
            if cur_label:
                msgs[cur_label].append(m.group(2))
            continue
        if cur_label and line.strip():
            msgs[cur_label].append(line.strip())

    # ★수집본이 언제 뜬 것인지 먼저 밝힌다 (2026-08-13 실사고).
    #   카톡 아카이브는 **그 파일을 만든 순간까지**만 담는다. 오늘 13:05 수집본을 최신으로
    #   착각하고 "이정헌 소장 회신 없음"이라 GM 께 보고했는데, 소장님 회신 7건은 16:29~18:44
    #   에 와 있었다. 파일 첫머리에 "저장한 날짜 : …"가 적혀 있는데 그걸 안 봤다.
    #   그래서 화면에 경과 시간을 박는다 — 낡은 것을 최신으로 읽는 실수는 눈으로 막는다.
    stamp, age_txt, hours = _midmgr_saved_at(text)
    # ★날짜만 보면 놓친다 (웰리 실측 2026-08-17) — 07:30 수집 후 같은 날 저녁까지 그대로면
    #   날짜는 안 바뀌어 "오늘 수집분" 취급을 받지만, 그 사이 온 회신은 여전히 안 보인다.
    #   경과 "시간"으로 판정한다 — 12시간 넘게 낡았으면 날짜가 같아도 낡은 것으로 본다.
    STALE_HOURS = 12
    stale = hours is not None and hours >= STALE_HOURS
    out = [f"\n📩 실무진 회신 — 이 방에 남긴 것 ({collected_date} 대화분{age_txt})"]
    if stale:
        out.append(f"  ❌ 이 수집본은 {int(hours)}시간 전 것이다 — 못 읽은 회신이 있을 수 있다.")
        out.append("     수집이 실패했을 가능성(화면 잠김이면 수집기가 못 돈다). "
                   "먼저 받아오고 나서 판단할 것.")
    if stamp:
        out.append(f"  🕒 이 수집본은 {stamp} 까지만 담고 있다. 그 뒤 회신은 여기 없다.")
        out.append('     최신으로 다시 받기: C:/Python314/python.exe scripts/kakao_export_chat.py --room-key mgr')
    any_reply = False
    for label in _MIDMGR_SENDERS.values():
        joined = " ".join(msgs[label]).strip()
        if joined:
            any_reply = True
            # 100자였던 것을 340자로 넓힌다 (2026-08-13). 실장님이 남긴 회원 환불건(변호사
            # 응대 여부 질문)이 100자 컷에 잘려 나가 화면에선 "사진 매출보고서…"까지만 보였다.
            # 여기는 GM 화면이 아니라 웰리가 판단하려고 읽는 자리다 — 잘라서 얻는 게 없다.
            snippet = joined[:340] + ("…" if len(joined) > 340 else "")
            out.append(f'  · {label} ({len(msgs[label])}줄) — "{snippet}"')
        elif stale:
            out.append(f"  · {label} — 확인 못 함({int(hours)}시간 전 수집 · '회신 없음'과 다르다)")
        else:
            out.append(f"  · {label} — 회신 없음")
    if not any_reply:
        out.append(f"  (수집본이 {int(hours)}시간 전 것이라 확인 못 함 — 회신 없음이라 보고하지 말 것)" if stale
                   else "  (전원 회신 없음 — 없는 걸 있는 것처럼 만들지 않음)")
    out.append("※ 해석·판정 없음 — 원문 그대로. 판단해 현황 갱신하려면: "
                "python scripts/hangro_board.py --daily-status <lee-gy|lee-jh> --done N --note \"...\"")
    # ★회신에 답하는 순서 (GM 지시 2026-08-13). 순서를 바꾸지 않는다 —
    #   감사가 뒤로 밀리면 남은 것 독촉만 남고, 회신할수록 잔소리를 듣는 자리가 된다.
    out.append("┌ 회신에 답하는 순서 (GM 지시 2026-08-13) ─────────────")
    out.append("│ ① 감사·격려 먼저 — 해 주신 것을 이름 붙여 짚는다(뭉뚱그린 '감사합니다' 말고)")
    out.append("│ ② 그래서 무엇이 반영됐는지 — 화면 어디에 올라갔는지까지")
    out.append("│ ③ 못 한 것·회신 없는 것은 빼지 않는다 — 남은 목록으로 다시 올려 계속 받는다")
    out.append("│ ④ 내 목록은 그분 업무의 일부일 뿐 — 목록 밖에서 하고 계신 일을 먼저 짚고,")
    out.append("│    급한 순서가 다르면 그분이 잡은 순서를 따른다(우리 기한을 밀어붙이지 않는다)")
    out.append("└ 실무진 방 발신은 초안 → GM 승인 → 발송")
    return "\n".join(out)


def _daily_status_stale_slice(role_slug: str) -> str:
    """practitioners[].daily_status 가 2일 이상 안 갱신됐으면 경고(GM 지시 2026-08-13 — 안 하면
    티가 나게). 0일이면 아무것도 안 낸다 — 매일 조용히 지나가는 게 정상이다."""
    if role_slug != "ceo" or not MONTHLY_OPS_PLAN_PATH.exists():
        return ""
    try:
        data = json.loads(MONTHLY_OPS_PLAN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ""
    today = dt.date.today()
    stale = []
    for p in data.get("practitioners", []):
        ds = p.get("daily_status")
        if not ds or not ds.get("date"):
            continue
        try:
            age = (today - dt.date.fromisoformat(ds["date"])).days
        except Exception:
            continue
        if age >= 2:
            stale.append((p.get("name", p.get("id")), age))
    if not stale:
        return ""
    lines = [f"  · {name} — {age}일째 안 갱신" for name, age in stale]
    return "\n⚠️ 현황 갱신 밀림\n" + "\n".join(lines)


# ── ✉️ 발신 대기 (2026-08-24 — 웰리·시모 배는 아침 카톡 자동발송(send_ops_digest.py
#   build_relay_message)에서 중복 발신 방지로 일부러 빠진다. 그래서 전달문을 채워도
#   자동으로는 절대 안 나가는데 경보가 없어 2026-08-21~24 실무진 전달문 3통이 조용히
#   멈춰 있었다(GM 실사고). --role ceo·cmo 화면 맨 위에서 짚는다. 새 유틸 없음 —
#   아이콘·담당 칸은 _owner_label, 날수는 _open_days(다른 표가 이미 'N일째'에 쓰는 것) 재사용. ──
def _unsent_relay_alert(items: list[dict]) -> str:
    rows = []
    for it in items:
        if str(it.get("owner", "")).upper() not in {"CEO", "CMO"}:
            continue
        if str(it.get("status", "")).upper() not in {"PENDING", "IN_PROGRESS"}:
            continue
        if not str(it.get("staff_message") or "").strip():
            continue
        if str(it.get("staff_message_sent_at") or "").strip():
            continue
        icon = it.get("_ship", {}).get("icon", "⛵")
        days = _open_days(it)
        day_s = f"{days}일째" if days is not None else "-"
        rows.append(f"| {icon} {_owner_label(it)} | {it.get('title', '')} | {day_s} |")
    if not rows:
        return ""
    out = [f"### ✉️ 발신 대기 — 전달문은 썼는데 아직 안 나간 배 {len(rows)}척",
           "| 배 | 진행명 | 며칠째 |", "|---|---|---|", *rows,
           "※ 웰리·시모 배의 전달문은 아침 자동 발송에 안 실린다 — 직접 보내야 한다."]
    return "\n".join(out)


# ── ⏰ 기한 빈칸·넘김 (배732 · 약속 L20·L26⑤ — 2026-08-24 GM 지시로 배 등록에서
#   부팅 표 전용으로 경로 변경. "자가점검을 토대로 배편을 만들지말고, 전체 정리를해주기만해."
#   판정·집계는 gm_aide_scan.scan_due_hygiene() 그대로 재사용(약속 L01 · 복제 금지) — 여기선
#   그 counts 를 표 모양으로만 그린다. --role ceo 화면 맨 위, ✉️ 발신 대기와 같은 자리·같은 방식. ──
_DUE_HYGIENE_LABELS = {
    "①기한없음": ("기한이 비어 있는 목표", "월간운영계획"),
    "②기한넘김": ("기한이 지난 목표", "월간운영계획"),
    "③체크리스트100%": ("체크리스트 100%인데 완료 이관 안 된 목표", "월간운영계획"),
    "④전사일정담당빈칸": ("전사일정에 담당이 빈 건", "전사일정"),
    "⑤보고완료미이관": ("보고 완료됐는데 목록에 남은 건", "회장님 보고목록"),
    "⑥완료예정일없음": ("체크 항목에 완료예정일(~M/D) 표기 없음", "월간운영계획"),
    "⑦완료예정일지남": ("체크 항목 완료예정일 지남", "월간운영계획"),
}


def _due_hygiene_alert() -> str:
    import gm_aide_scan
    caps = gm_aide_scan.scan_due_hygiene()
    counts = caps[0]["counts"] if caps else {}
    rows = [f"| {what} | {counts[code]}건 | {where} |"
            for code, (what, where) in _DUE_HYGIENE_LABELS.items() if counts.get(code)]
    if not rows:
        return ""
    return "\n".join([
        "### ⏰ 기한 빈칸·넘김 — GM 업무 3곳 이어보기",
        "| 무엇 | 건수 | 어디 |", "|---|---|---|", *rows,
    ])


def _set_daily_status(prac_id: str, done: int, note: str) -> None:
    """--daily-status 한 줄 명령 — practitioners[].daily_status 를 손으로 JSON 안 열고 갱신.
    새 파일 안 만든다(약속 L21) — status/monthly_ops_plan.json 칸 하나 그대로 재사용."""
    if not MONTHLY_OPS_PLAN_PATH.exists():
        print("monthly_ops_plan.json 이 없습니다.")
        return
    data = json.loads(MONTHLY_OPS_PLAN_PATH.read_text(encoding="utf-8"))
    prac = next((p for p in data.get("practitioners", []) if p.get("id") == prac_id), None)
    if prac is None:
        print(f"practitioner id={prac_id} 를 못 찾았습니다.")
        return
    now = dt.datetime.now(tz=timezone(dt.timedelta(hours=9)))
    ds = prac.get("daily_status") or {}
    ds["date"] = now.date().isoformat()
    ds["processed"] = done
    ds["note"] = note
    ds["updated_at"] = now.strftime("%Y-%m-%d %H:%M")  # 갱신일을 못 믿는다 — 오늘 겪은 것, 시각까지 남긴다
    ds["updated_by"] = "웰리"
    prac["daily_status"] = ds
    MONTHLY_OPS_PLAN_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"daily_status 갱신 완료 — {prac_id}: processed={done} note={note!r} "
          f"updated_at={ds['updated_at']}")


def _print_one_ship(num: str) -> None:
    """배 한 척의 전체 기록만 낸다 — 큐 전체를 세션 맥락에 올리지 않기 위한 창구.
    번호는 short_no 우선, 없으면 ship_no 로 찾는다. 못 찾으면 그렇게 말한다(지어내지 않는다)."""
    want = str(num).strip()
    try:
        with open(QUEUE_PATH, encoding="utf-8") as f:
            items = json.load(f)
        if not isinstance(items, list):
            items = items.get("items") or items.get("queue") or []
    except Exception as exc:
        print(f"큐를 못 읽었습니다: {exc}")
        return
    hits = [it for it in items
            if str(it.get("short_no") or "") == want or str(it.get("ship_no") or "") == want]
    if not hits:
        print(f"배 {want} 를 큐에서 못 찾았습니다(보관함으로 옮겨졌을 수 있습니다).")
        return
    for it in hits:
        print(f"■ 배 {it.get('short_no') or it.get('ship_no')} · {it.get('clevel')} · {it.get('status')}")
        print(f"  제목  : {it.get('title')}")
        print(f"  띄운날: {it.get('enqueued_at')}   마지막 기록: {it.get('updated_at') or '-'}")
        print(f"  다음  : {it.get('next') or '-'}")
        if it.get("artifact_url"):
            print(f"  증거  : {it.get('artifact_url')}")
        print("  ── 기록(note) ──")
        print(it.get("note") or "(없음)")
        print()


# ── CLI ───────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="항로 보드 생성기")
    parser.add_argument("--json", action="store_true", help="JSON도 출력")
    parser.add_argument("--dry-run", action="store_true", help="네트워크 없이 _queue만")
    parser.add_argument(
        "--role", default="",
        help="본인 역할 배만 잘라서 출력 (ceo·cmo·coo·cpo·cto). 부팅 슬라이스 — "
             "원본은 한 벌 그대로, 읽을 때만 자른다(배10369).",
    )
    parser.add_argument(
        "--ship", default="", metavar="N",
        help="배 하나만 전체 기록으로 출력(번호=short_no 또는 ship_no). "
             "부팅 지시문이 '배를 착수할 땐 그 배 하나만 큐에서 찾아 끝까지 읽는다'고 하는데 "
             "그 명령이 없어서, 세션마다 1MB 짜리 status/_queue.json 을 통째로 훑고 있었다"
             "(2026-08-13 토큰 감사). 새 스크립트를 만들지 않고 여기 관문에 얹는다(약속 L21).",
    )
    parser.add_argument(
        "--daily-status", default="", metavar="PRAC_ID",
        help="실무진 회신→현황 한 줄 명령(GM 지시 2026-08-13). practitioner id(lee-gy·lee-jh)를 "
             "주면 --done·--note 값으로 monthly_ops_plan.json 의 daily_status 를 갱신하고 끝낸다.",
    )
    parser.add_argument("--done", type=int, default=0, help="--daily-status 와 함께 — 오늘 처리 건수")
    parser.add_argument("--note", default="", help="--daily-status 와 함께 — 판단 근거 한 줄")
    args = parser.parse_args()

    if args.daily_status:
        _set_daily_status(args.daily_status, args.done, args.note)
        return

    if args.ship:
        _print_one_ship(args.ship)
        return

    if args.dry_run:
        gas_items = []
    else:
        gas_items = fetch_gas_items()

    queue_items = fetch_queue_items()

    # 쿵짝 회수(2026-08-04) — 역할 슬라이스로 잘리기 전 원본 스냅샷.
    #   슬라이스는 owner(받는이)==나 만 남기므로, 내가 보낸 배(owner=남)는 슬라이스 후엔
    #   이미 사라져 안 잡힌다 — 반드시 슬라이스 앞에서 떠 둔다.
    role_slug = args.role.strip().lower() if args.role else ""
    sent_by_role = list(queue_items) if role_slug else []

    # ── 역할 슬라이스 (배10369 · 2026-07-29 시토) ────────────────────────────
    #  왜: 부팅 (4)단계가 status/_queue.json 을 통째로 읽어 창 하나당 20만 자를 먹었다.
    #  GM 은 늘 셸 5개로 일하므로 실제로는 그 5배다(웰리 실측 101만 자).
    #  ★파일을 역할별로 쪼개지 않는다 — 진실이 7벌이 되면 약속 L01 위반이다.
    #    원본(_queue.json)은 한 벌 그대로 두고 **읽는 순간에만** 잘라 준다.
    #  ★새 스크립트를 만들지 않는다(약속 L21) — 항로를 뽑는 단일 지점이 이미 여기라 여기에 흡수.
    if args.role:
        target = _nick(args.role.strip())
        gas_items = [it for it in gas_items if _nick(str(it.get("owner", ""))) == target]
        queue_items = [it for it in queue_items if _nick(str(it.get("owner", ""))) == target]

    board_text, secs = build_board(gas_items, queue_items, role=role_slug, sent_by_role=sent_by_role)
    if role_slug in {"ceo", "cmo"}:
        alert = _unsent_relay_alert(queue_items)
        if alert:
            board_text = alert + "\n\n" + board_text
    if role_slug == "ceo":
        due_alert = _due_hygiene_alert()
        if due_alert:
            board_text = due_alert + "\n\n" + board_text
    if args.role:
        # 정보 손실 0 — 잘라 냈다는 사실과 전체를 어디서 보는지 같이 알린다.
        board_text += (
            f"\n※ {target} 배만 잘라 낸 화면입니다(부팅 슬라이스). "
            "전 역할 항로는 `python scripts/hangro_board.py --dry-run`, "
            "특정 배의 전체 기록은 그 배 하나만 status/_queue.json 에서 찾아 읽으세요."
        )
        board_text += _kpi_slice(role_slug)
        board_text += _page_score_slice(role_slug)
        board_text += _reception_watch_slice(role_slug)
        board_text += _gm_profile_slice()
        board_text += _midmgr_reply_slice(role_slug)
        board_text += _daily_status_stale_slice(role_slug)
    print(board_text)

    if args.json:
        print("\n--- JSON ---")
        out = {k: [
            {kk: vv for kk, vv in it.items() if kk != "_ship"}
            for it in v
        ] for k, v in secs.items()}
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest_gm_directives()
    else:
        main()
