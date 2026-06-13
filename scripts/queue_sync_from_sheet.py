#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/queue_sync_from_sheet.py — 구글시트(AI 배) → status/_queue.json 단방향 미러 생성기 (NEW)

배경 (한 줄)
    GM 결정: "AI C레벨 배를 구글시트로 일원화 → G1에서 GM 일처럼 편집."
    채택 아키텍처: **구글시트 = AI 배 SSOT / _queue.json = 시트에서 자동 생성되는 캐시(미러).**
    이 스크립트가 그 '자동 생성' 한 방향(one-way: 시트 → _queue.json)을 담당한다.

왜 비파괴(non-breaking)인가
    기존 READER(8시 보고·21시 마무리·daily_scheduler·hangro_board·ceo_watcher·G1 HTML)는
    전부 status/_queue.json 을 "있는 그대로" 계속 읽는다. 이 스크립트는 그 파일을
    **현행 스키마와 100% 동일한 모양**으로 재생성할 뿐이라 readers 무수정.
    기존 WRITER(clevel_post_action / bot 결재 라우터 / ceo_watcher / queue_archive)는
    1단계에서 손대지 않는다(2단계 과제). → 1단계는 '읽어서 만들어 보여주기'가 핵심.

시트 매핑 (todo_list 컬럼 → _queue.json 필드)
    AI 배 행 식별: 카테고리 == AI_CATEGORY ('[7]AI배(C레벨)'). GM/실무진 행과 시각적 구분.
    기본 매핑:
        업무명   → title
        담당자   → clevel  (예: 'AI CTO' / '시토' / 'cto' → 'cto')
        상태     → status  (시트 한글/영문 → _queue 표준값 PENDING/IN_PROGRESS/DONE/폐기/ON_HOLD)
        종료일   → deadline
        난이도   → priority (하/중/상 → NORMAL/HIGH/P0 매핑은 보수적; 영문 우선)
        수정일   → processed_at (status 가 DONE 일 때만)
        내용     → 본문 + ===AI_QUEUE=== JSON 블록(부족 필드 인코딩)
    부족 필드 인코딩(신규 컬럼 없이): '내용' 셀 안에 아래 센티넬 블록을 둔다.
        ===AI_QUEUE===
        {"task_id":"CTO-...","depends_on":null,"terminal":true,"brief":"...","next":"...",
         "from":"cto","origin":"bridge","artifact":"...","note":"...","enqueued_at":"..."}
        ===END===
    이 블록은 BUDGET 마커(===BUDGET===)와 동일한 '내용 셀 임베드' 패턴 — GAS 재배포 불필요.
    블록이 없으면 시트 컬럼만으로 최대한 복원하고, task_id 는 id 컬럼(또는 행 추정)으로 폴백.

산출
    기본: 생성된 _queue.json 배열을 stdout 에 출력(미리보기 — 실파일 미변경).
    --diff: 현재 status/_queue.json 과 줄 단위 비교(동등성 검증).
    --write: 실제 status/_queue.json 갱신(원자적 .tmp→replace). **1단계 검증 단계에선 사용 금지 권장.**
    --mock <파일>: GAS 대신 모의 todo_list 응답(JSON: {"data":[...]} 또는 [...]) 사용.
                   실제 시트에 아직 AI 행이 없을 때 "있다면 이렇게 생성된다"를 시연.

CLI 예
    python scripts/queue_sync_from_sheet.py                 # 시트에서 읽어 미리보기(stdout)
    python scripts/queue_sync_from_sheet.py --mock sample.json
    python scripts/queue_sync_from_sheet.py --diff          # 현재 _queue.json 과 비교
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

# ── 콘솔 인코딩(Windows cp949 한글 깨짐 방지) ──────────────────────────────
try:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 경로 ─────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent          # scripts/
_REPO = _HERE.parent                             # welperion-automation/
QUEUE_PATH = _REPO / "status" / "_queue.json"

# todo_list GAS 엔드포인트 — hangro_board.py 와 동일 SSOT
# v@53 (2026-06-08): todo_add/todo_delete sheet 파라미터 + ai_list/ai_sheet_create 추가
GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxwXMJ4ghYcJ6NR1mXnBi0CFBVMxfwKK0SvXsJkJlGG_t8aeJb4HXmiP4GL0HG2pTYa/exec"
)

# ── AI 배 식별 ────────────────────────────────────────────────────────────
# 시트의 카테고리 컬럼이 이 값이면 'AI C레벨 배'로 본다(GM/실무진과 분리).
# GAS CATEGORIES 에는 아직 없는 신규 카테고리 — '내용' 임베드와 마찬가지로 GAS 재배포 없이
# 시트 셀에 직접 입력하면 동작(드롭다운만 없을 뿐 값은 자유 입력 가능).
AI_CATEGORY = "[7]AI배(C레벨)"
AI_CATEGORY_ALIASES = {"[7]ai배(c레벨)", "[7]ai배", "ai배", "ai_clevel", "ai c레벨"}

# ── 새 탭 설계 (GM 결정 2026-06-08) ──────────────────────────────────────
# GM 결정: AI 배를 실무진 todo_list 탭과 분리 → 같은 스프레드시트의 전용 탭으로 이관.
# 신규 탭명 상수 — 코드는 준비, 실제 탭 생성·GAS 배포는 GM 게이트 후 진행.
AI_SHEET_NAME = "AI배(C레벨)"

# 신규 탭용 GAS 액션명 (GAS 재배포 후 사용 가능, 현재는 준비 상태).
# GAS 에 'ai_list' 액션이 배포되면 이 액션으로 전용 탭 행을 조회한다.
AI_LIST_ACTION = "ai_list"

# 내용 셀 임베드 센티넬 — BUDGET 마커와 동일한 발상.
_EMBED_RE = re.compile(r"===AI_QUEUE===\s*(.+?)\s*===END===", re.DOTALL)

# ── 담당자 → clevel 정규화 ────────────────────────────────────────────────
_CLEVEL_BY_TOKEN = {
    "웰리": "ceo", "ceo": "ceo", "ai ceo": "ceo",
    "시뽀": "cfo", "cfo": "cfo", "ai cfo": "cfo",
    "시로": "chro", "chro": "chro", "ai chro": "chro",
    "시모": "cmo", "cmo": "cmo", "ai cmo": "cmo",
    "시우": "coo", "coo": "coo", "ai coo": "coo",
    "시포": "cpo", "cpo": "cpo", "ai cpo": "cpo",
    "시토": "cto", "cto": "cto", "ai cto": "cto",
}

# ── 상태 정규화 (시트 표현 → _queue 표준값) ───────────────────────────────
# readers 가 기대하는 표준값: PENDING / IN_PROGRESS / DONE / 폐기 / ON_HOLD.
_STATUS_NORM = {
    "진행중": "IN_PROGRESS", "in_progress": "IN_PROGRESS", "inprogress": "IN_PROGRESS",
    "대기": "PENDING", "pending": "PENDING",
    "완료": "DONE", "done": "DONE",
    "보류": "ON_HOLD", "on_hold": "ON_HOLD", "hold": "ON_HOLD",
    "폐기": "폐기", "cancelled": "폐기", "canceled": "폐기",
}

# ── 난이도 → priority (보수적) ────────────────────────────────────────────
_PRIORITY_NORM = {
    "하": "NORMAL", "중": "NORMAL", "상": "HIGH",
    "normal": "NORMAL", "high": "HIGH", "p0": "P0",
}


def _norm_clevel(owner: str) -> str:
    o = str(owner or "").strip().lower()
    for token, cl in _CLEVEL_BY_TOKEN.items():
        if token in o:
            return cl
    return o or "ceo"


def _norm_status(raw: str) -> str:
    s = str(raw or "").strip()
    return _STATUS_NORM.get(s, _STATUS_NORM.get(s.lower(), s or "PENDING"))


def _norm_priority(raw: str) -> str:
    p = str(raw or "").strip()
    if not p:
        return "NORMAL"
    return _PRIORITY_NORM.get(p, _PRIORITY_NORM.get(p.lower(), p.upper()))


def _is_ai_row(row: dict) -> bool:
    cat = str(row.get("카테고리", "") or "").strip()
    return cat == AI_CATEGORY or cat.lower() in AI_CATEGORY_ALIASES


def _strip_embed(content: str) -> str:
    """'내용' 셀에서 ===AI_QUEUE=== 블록을 제거한 사람용 본문만 반환."""
    return _EMBED_RE.sub("", str(content or "")).strip()


def _parse_embed(content: str) -> dict:
    """'내용' 셀의 ===AI_QUEUE===...===END=== JSON 블록 파싱(없으면 빈 dict)."""
    m = _EMBED_RE.search(str(content or ""))
    if not m:
        return {}
    try:
        obj = json.loads(m.group(1))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


# ── 핵심: 시트 행 → _queue 항목 ───────────────────────────────────────────
def row_to_queue_item(row: dict) -> dict:
    """
    시트 1행(todo_list 객체) → _queue.json 항목(dict).
    우선순위: 임베드 블록(명시값) > 시트 컬럼(파생값). 현행 스키마/필드명 그대로 유지.
    None/빈값 필드는 키를 넣지 않아(omit) 기존 _queue.json 의 '필요 키만 존재' 형태와 일치.
    """
    embed = _parse_embed(row.get("내용", ""))
    body = _strip_embed(row.get("내용", ""))

    status = _norm_status(row.get("상태"))

    item: dict = {}

    # task_id: 임베드 우선 → id 컬럼 폴백
    tid = embed.get("task_id") or str(row.get("id", "")).strip()
    if tid:
        item["task_id"] = tid

    item["clevel"] = embed.get("clevel") or _norm_clevel(row.get("담당자"))
    item["title"] = str(row.get("업무명", "") or "").strip()
    item["status"] = status

    # 선택 필드 — 값이 있을 때만 키 추가(omit-empty)
    def _set(key, value):
        if value is None:
            return
        if isinstance(value, str) and not value.strip():
            return
        item[key] = value

    # 선택 필드 전체를 임베드 키 순서대로 삽입한다.
    # 이유: 현행 _queue.json 은 항목마다 키 순서가 제각각이라 고정 순서로는
    # 줄단위 round-trip 동등 불가. 임베드 블록에 원본 키 순서를 그대로 인코딩하면
    # 생성기가 임베드 순서대로 item 을 재구성하여 줄단위 동등이 보장됨.
    #
    # 처리 우선순위:
    #   depends_on  — None 도 의도값(명시 'in' 판정, 값 없이 키만 보존)
    #   priority    — 시트 난이도 컬럼 우선, 없으면 임베드, 둘 다 없으면 NORMAL
    #   deadline / enqueued_at — 임베드 우선 → 시트 컬럼 폴백
    #   processed_at — DONE 계열에만, 임베드 우선 → 시트 수정일 폴백
    #   나머지 전체 — 임베드에 존재하는 키 순서대로 삽입(note_progress 포함)
    #   note        — 임베드 note 우선, 없으면 사람용 본문

    # ── 임베드의 모든 선택 필드를 순서 보존하며 처리 ─────────────────────────
    # 고정 4개 (task_id·clevel·title·status) 이외 전부를 임베드 순서대로.
    _FIXED = {"task_id", "clevel", "title", "status"}
    # 시트 컬럼 파생값(임베드 없을 때 폴백)
    _col_priority = _norm_priority(row.get("난이도")) if row.get("난이도") else None
    _col_deadline = str(row.get("종료일", "") or "")[:10] or None
    _col_enqueued = str(row.get("생성일", "") or "")[:10] or None
    _col_processed = str(row.get("수정일", "") or "")[:10] or None

    _handled: set[str] = set(_FIXED)

    for key, val in embed.items():
        if key in _FIXED:
            continue
        # depends_on: None 도 의도값 → 항상 삽입(empty 필터 없이)
        if key == "depends_on":
            item["depends_on"] = val
        elif key == "priority":
            resolved = _col_priority or (_norm_priority(str(val)) if val else "NORMAL")
            item["priority"] = resolved
        elif key == "deadline":
            v = val or _col_deadline
            if v:
                item["deadline"] = v
        elif key == "enqueued_at":
            v = val or _col_enqueued
            if v:
                item["enqueued_at"] = v
        elif key == "processed_at":
            v = val or (_col_processed if status == "DONE" else None)
            if v:
                item["processed_at"] = v
        elif key == "note":
            # note 도 임베드 순서 그대로 제자리에 삽입
            note_val = val or body
            if note_val:
                item["note"] = note_val
            _handled.add("note")
        else:
            # 그 외 모든 임베드 필드(terminal, brief, next, next_missing, from, origin,
            # artifact, commit_sha, remind_on, disposed_at, owner, tech,
            # note_progress, approval, approved_at, approval_comment, archived_at 등)
            if val is None:
                pass  # None 은 omit(readers 기대값과 일치)
            elif isinstance(val, str) and not val.strip():
                pass
            else:
                item[key] = val
        _handled.add(key)

    # 임베드에 없던 시트 컬럼 파생 필드 보완(임베드에 키가 아예 없을 때만)
    if "priority" not in item:
        item["priority"] = _col_priority or "NORMAL"
    if "depends_on" not in item and "depends_on" in embed:
        item["depends_on"] = embed["depends_on"]
    if "deadline" not in item and _col_deadline:
        item["deadline"] = _col_deadline
    if "enqueued_at" not in item and _col_enqueued:
        item["enqueued_at"] = _col_enqueued
    if "processed_at" not in item and status == "DONE" and _col_processed:
        item["processed_at"] = _col_processed

    # note: 임베드에 note 키가 없었던 경우에만 사람용 본문으로 보완
    if "note" not in item:
        note_val = embed.get("note") or body
        if note_val:
            item["note"] = note_val

    return item


# ── 시트 fetch ────────────────────────────────────────────────────────────
def fetch_todo_rows(mock_path: str | None = None) -> list[dict]:
    """todo_list 행 전체(필터 전). --mock 면 파일에서, 아니면 GAS GET."""
    if mock_path:
        raw = json.loads(Path(mock_path).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return list(raw.get("data", []))
        return list(raw) if isinstance(raw, list) else []
    req = urllib.request.Request(GAS_URL + "?action=todo_list")
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    return list(data.get("data", []))


def fetch_ai_sheet_rows(sheet_name: str = AI_SHEET_NAME) -> list[dict]:
    """
    전용 탭(AI배(C레벨))에서 AI 배 행을 직접 조회한다.
    GAS 에 'ai_list' 액션이 배포된 후 사용 가능.
    배포 전 호출 시 GAS 가 unknown action 오류를 반환하므로 ValueError 로 변환.

    이 함수는 코드 준비 단계 — 실제 GAS 배포(GM 게이트)가 선행되어야 동작한다.
    """
    import urllib.parse
    params = urllib.parse.urlencode({"action": AI_LIST_ACTION, "sheet": sheet_name})
    req = urllib.request.Request(GAS_URL + "?" + params)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    if not data.get("ok"):
        msg = data.get("error") or data.get("message") or str(data)
        raise ValueError(f"ai_list GAS 오류(배포 전?): {msg}")
    return list(data.get("data", []))


def build_queue(rows: list[dict], *, all_rows_are_ai: bool = False) -> list[dict]:
    """
    AI 배 행만 골라 _queue 항목 배열 생성.
    all_rows_are_ai=True 이면 _is_ai_row 필터 없이 전 행을 처리한다
    (전용 탭에서 읽은 경우 — 카테고리 컬럼 없이도 동작).
    """
    out: list[dict] = []
    for row in rows:
        if not all_rows_are_ai and not _is_ai_row(row):
            continue
        title = str(row.get("업무명", "") or "").strip()
        if not title:
            continue
        out.append(row_to_queue_item(row))
    return out


# ── 출력/검증 ─────────────────────────────────────────────────────────────
def _dump(items: list[dict]) -> str:
    return json.dumps(items, ensure_ascii=False, indent=2)


def _atomic_write(items: list[dict]) -> None:
    tmp = QUEUE_PATH.with_name(QUEUE_PATH.name + ".tmp")
    tmp.write_text(_dump(items) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(QUEUE_PATH))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="구글시트(AI 배) → status/_queue.json 단방향 미러 생성기 (1단계 비파괴)"
    )
    ap.add_argument("--mock", default=None,
                    help="GAS 대신 모의 todo_list JSON 파일 사용(시연용).")
    ap.add_argument("--diff", action="store_true",
                    help="현재 status/_queue.json 과 줄 단위 비교만(쓰기 없음).")
    ap.add_argument("--write", action="store_true",
                    help="[주의] 실제 status/_queue.json 갱신. 1단계 검증 단계에선 사용 금지 권장.")
    ap.add_argument("--force", action="store_true",
                    help="[위험] 안전가드(유실 방지) 무시하고 --write 강행. 시트가 _queue보다 낡았음을 인지한 경우만.")
    ap.add_argument(
        "--sheet-name",
        default=None,
        metavar="SHEET",
        help=(
            f"전용 탭 이름으로 AI 배를 조회한다 (기본값: None = todo_list 카테고리 필터 방식 유지).\n"
            f"예: --sheet-name '{AI_SHEET_NAME}'\n"
            f"[주의] GAS ai_list 액션 배포(GM 게이트) 전에는 오류 발생."
        ),
    )
    args = ap.parse_args(argv)

    all_rows_are_ai = False
    try:
        if args.sheet_name:
            # 전용 탭 모드 — GAS ai_list 액션 경유(배포 후 사용 가능)
            print(
                f"[INFO] 전용 탭 모드: sheet='{args.sheet_name}' (ai_list 액션)",
                file=sys.stderr,
            )
            rows = fetch_ai_sheet_rows(args.sheet_name)
            all_rows_are_ai = True  # 전용 탭은 AI 배만 존재 → 카테고리 필터 불필요
        else:
            # 기존 방식 — todo_list 카테고리 필터
            rows = fetch_todo_rows(args.mock)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] 시트 수집 실패: {e}", file=sys.stderr)
        return 1

    items = build_queue(rows, all_rows_are_ai=all_rows_are_ai)
    generated = _dump(items)

    if args.diff:
        current = QUEUE_PATH.read_text(encoding="utf-8") if QUEUE_PATH.exists() else ""
        cur_norm = _dump(json.loads(current)) if current.strip() else ""
        if cur_norm == generated:
            print("[DIFF] 동등 — 생성본이 현재 _queue.json 과 일치합니다.")
            return 0
        import difflib
        diff = difflib.unified_diff(
            cur_norm.splitlines(), generated.splitlines(),
            fromfile="current _queue.json", tofile="generated(sheet)", lineterm="",
        )
        print("\n".join(diff))
        print(f"\n[DIFF] AI 배 {len(items)}건 생성됨. 위 차이 검토 필요.")
        return 0

    if args.write:
        # ── 유실방지 안전가드 (2026-06-13 시토) ───────────────────────────────
        # 시트(SSOT 후보)가 _queue보다 낡으면(예: 06-08 전용탭 화석) --write 시
        # 시트에 없는 최신 _queue 항목이 통째로 사라진다(06-07 사고 메커니즘).
        # 현 _queue에만 있고 생성본에 없는 task_id(=유실 대상)가 있으면 거부.
        cur = json.loads(QUEUE_PATH.read_text(encoding="utf-8")) if QUEUE_PATH.exists() else []
        gen_ids = {i.get("task_id") for i in items if i.get("task_id")}
        cur_ids = {i.get("task_id") for i in cur if i.get("task_id")}
        lost = sorted(cur_ids - gen_ids)
        if lost and not args.force:
            print(
                f"[ABORT] --write 거부: 시트에 없어 유실될 _queue 항목 {len(lost)}건.",
                file=sys.stderr,
            )
            print(f"        예: {lost[:8]}", file=sys.stderr)
            print(
                "        시트(SSOT)가 _queue보다 낡았을 수 있습니다(화석). "
                "재seed로 동등화하거나, 의도적이면 --force.",
                file=sys.stderr,
            )
            return 2
        _atomic_write(items)
        print(f"[WRITE] status/_queue.json 갱신 — AI 배 {len(items)}건"
              + (f" (가드 우회 --force, 유실 {len(lost)}건)" if lost else ""))
        return 0

    # 기본: 미리보기
    print(generated)
    print(f"\n[PREVIEW] AI 배 {len(items)}건 (실파일 미변경). 검증: --diff / 적용: --write",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
