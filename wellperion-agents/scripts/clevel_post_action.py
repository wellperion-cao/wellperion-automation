#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
C-Level .bat 종료 직전 표준 post-action 훅 (hook) 모듈

복원 경위: git에 한 번도 커밋된 적 없던 소스가 소실(.pyc만 잔존)되어
clevel.bat 파이프라인이 죽어 있었음 — .pyc 바이트코드 상수에서 원본 인터페이스를
복원하고, 외부 DB(2026-05-29 폐기) 의존성을 제거한 채 status json + 텔레그램 1줄
보고만 남겨 재작성(2026-06-01, AI CTO).

역할(R/R): AI CTO -- IT 인프라 표준화

사용법:
    python scripts/clevel_post_action.py
        --clevel CTO
        --task-id CTO-002
        --status 완료
        --summary "PC 자동 ON/OFF v1.0 가동"
        --version v1.0
        --changelog "2026-04-26 가동 시작"

    # 실제 발송 없이 페이로드만 확인 (안전 검증)
    python scripts/clevel_post_action.py --dry-run
        --clevel CTO --task-id CTO-002 --status 완료
        --summary "테스트" --version v1.0 --changelog "변경 없음"
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── 콘솔 인코딩(Windows cp949 한글 깨짐 방지) ────────────────────────────────
try:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 경로 ─────────────────────────────────────────────────────────────────────
_BASE = Path(__file__).resolve().parent          # wellperion-agents/scripts
_PACKAGE_ROOT = _BASE.parent                      # wellperion-agents
_REPO_ROOT = _PACKAGE_ROOT.parent                 # welperion-automation (repo root)
_STATUS_DIR = _REPO_ROOT / "status"
_QUEUE_PATH = _STATUS_DIR / "_queue.json"   # 중앙 큐(일의 브릿지 단일 진실)

# ── GAS(구글시트) 동기화 — 2단계 AI 배 SSOT 이관 (2026-06-07) ───────────────
# GAS URL: hangro_board.py / queue_sync_from_sheet.py 와 동일 SSOT
_GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)
_AI_CATEGORY = "[7]AI배(C레벨)"
_EMBED_RE = re.compile(r"===AI_QUEUE===\s*(.+?)\s*===END===", re.DOTALL)

# clevel → 시트 담당자 표시명
_CLEVEL_DISPLAY = {
    "ceo": "AI CEO(웰리)", "cfo": "AI CFO(시뽀)", "chro": "AI CHRO(시로)",
    "cmo": "AI CMO(시모)", "coo": "AI COO(시우)", "cpo": "AI CPO(시포)",
    "cto": "AI CTO(시토)",
}
# _queue status → 시트 상태
_STATUS_TO_SHEET = {
    "DONE": "완료", "IN_PROGRESS": "진행중", "PENDING": "대기",
    "ON_HOLD": "보류", "폐기": "완료",
}


def _gas_post(payload: dict, timeout: int = 15) -> dict:
    """GAS POST. 응답 dict 반환. 실패 시 {"ok": False, "error": ...}."""
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            _GAS_URL, data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _gas_get_sheet_id(task_id: str) -> str | None:
    """
    시트에서 task_id 임베드를 가진 AI배 행의 GAS id 반환. 없으면 None.
    best-effort: 실패 시 None(폴백 경로가 처리).
    """
    try:
        req = urllib.request.Request(_GAS_URL + "?action=todo_list")
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        rows = data.get("data", [])
        for row in rows:
            if _AI_CATEGORY not in str(row.get("카테고리", "")):
                continue
            m = _EMBED_RE.search(str(row.get("내용", "")))
            if m:
                try:
                    embed = json.loads(m.group(1))
                    if embed.get("task_id") == task_id:
                        return str(row.get("id", ""))
                except Exception:
                    pass
    except Exception as e:
        print("[WARN] GAS 시트 조회 실패: " + str(e), file=sys.stderr)
    return None


def _gas_sync_bridge(
    task_id: str,
    clevel: str,
    queue_after: list,
    appended_id: str | None,
    appended_item: dict | None,
    next_desc: str | None,
) -> None:
    """
    브릿지 완료를 GAS 시트에 동기화(best-effort — 실패해도 브릿지 미영향).

    1) 기존 task_id 행을 todo_update(상태=완료, 내용=임베드 재생성).
    2) next_desc 있으면 다음 항목을 todo_add(카테고리=[7]AI배(C레벨)).

    _queue.json 직접쓰기가 이미 완료된 뒤 호출되므로 queue_after = 갱신된 큐.
    """
    # ① 기존 행 상태 업데이트
    gas_id = _gas_get_sheet_id(task_id)
    if gas_id:
        # 완료된 항목의 최신 dict를 큐에서 찾아 임베드 재생성
        done_item = next((t for t in queue_after
                          if isinstance(t, dict) and t.get("task_id") == task_id), None)
        if done_item:
            omit = {"title", "clevel", "status", "deadline", "priority"}
            embed = {k: v for k, v in done_item.items()
                     if k not in omit and v is not None
                     and not (isinstance(v, str) and not v.strip())}
            embed_str = "===AI_QUEUE===\n" + json.dumps(embed, ensure_ascii=False) + "\n===END==="
            note_body = str(done_item.get("note", ""))
            content = (note_body + "\n" if note_body else "") + embed_str

            resp = _gas_post({
                "action": "todo_update",
                "id": gas_id,
                "status": "완료",
                "content": content,
            })
            if resp.get("ok"):
                print("[GAS] 시트 완료 업데이트 — " + task_id)
            else:
                print("[WARN] GAS 시트 업데이트 실패: " + str(resp.get("error", "")),
                      file=sys.stderr)
    else:
        print("[WARN] GAS 시트에서 " + task_id + " 행을 찾지 못함 — 시트 동기 스킵",
              file=sys.stderr)

    # ② 다음 항목 추가(브릿지 next)
    if next_desc and appended_id and appended_item:
        nclevel = str(appended_item.get("clevel", clevel)).lower()
        owner = _CLEVEL_DISPLAY.get(nclevel, "AI " + nclevel.upper())
        omit2 = {"title", "clevel", "status", "deadline", "priority"}
        embed2 = {k: v for k, v in appended_item.items()
                  if k not in omit2 and v is not None
                  and not (isinstance(v, str) and not v.strip())}
        embed_str2 = "===AI_QUEUE===\n" + json.dumps(embed2, ensure_ascii=False) + "\n===END==="
        note2 = str(appended_item.get("note", ""))
        content2 = (note2 + "\n" if note2 else "") + embed_str2

        resp2 = _gas_post({
            "action": "todo_add",
            "title": next_desc,
            "category": _AI_CATEGORY,
            "owner": owner,
            "status": "대기",
            "content": content2,
        })
        if resp2.get("ok"):
            print("[GAS] 시트 다음 항목 추가 — " + appended_id)
        else:
            print("[WARN] GAS 다음 항목 추가 실패: " + str(resp2.get("error", "")),
                  file=sys.stderr)


def _trigger_mirror_refresh() -> None:
    """
    queue_sync_from_sheet --write 로 _queue.json 미러를 시트 기준으로 재생성.
    best-effort: 실패해도 무시(직접쓰기로 이미 _queue.json 갱신됨).
    시트 동기화 직후 호출 — GAS 캐시 지연(수 초) 고려해 임포트만 하고 즉시 실행하지 않음.
    실제 재생성은 다음 8시 파이프라인 실행 전(Task Scheduler 또는 수동)에 별도 실행 권장.
    """
    # NOTE: 미러 재생성을 여기서 즉시 실행하면 GAS 캐시가 아직 반영 전일 수 있어
    # 방금 추가한 행이 미러에서 누락됨 → 즉시 실행 생략, WARN 없음.
    pass


# telegram_notifier 가 wellperion-agents/ 에 있으므로 import 경로 추가
# (ceo_morning_pipeline.py 와 동일 패턴)
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))
# queue_archive(끝난 일 자동 정리) 등 동일 폴더 sibling 모듈 import 보장
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

# .env 로드(텔레그램 토큰/chat_id). 토큰 원문은 절대 stdout 출력하지 않는다.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── 상수 ─────────────────────────────────────────────────────────────────────
VALID_CLEVELS = ["CEO", "CFO", "CHRO", "CMO", "COO", "CPO", "CTO"]
VALID_STATUSES = ["진행중", "완료", "이슈", "inprogress", "done", "issue"]
# 완료 계열 별칭 → "DONE" 정규화
_DONE_ALIASES = {"완료", "done", "DONE", "complete", "completed"}


def normalize_status(raw_status: str) -> str:
    """
    완료 계열 별칭을 "DONE"으로 정규화.
    그 외 값(예: "진행중", "이슈", "inprogress")은 원문 그대로 반환.
    """
    if raw_status in _DONE_ALIASES or raw_status.lower() in {a.lower() for a in _DONE_ALIASES}:
        return "DONE"
    return raw_status


def write_status_file(
    clevel: str,
    task_id: str,
    title: str,
    status: str,
    artifact_url: str,
    note: str,
    dry_run: bool,
) -> bool:
    """
    status/<clevel>.json 에 듀얼 시그널(dual-signal)용 상태를 기록한다.

    - 기존 파일의 다른 키(clevel, last_task_id, active_tasks 등)는 보존(read-merge).
    - status 는 normalize_status() 로 정규화 후 기록 ("DONE" 또는 원문).
    - active_tasks 에 동일 task_id 가 있으면 status/note/updated_at 갱신, 없으면 append.
    - dry_run=True 이면 기록 예정 JSON을 stdout 에 출력하고 파일 쓰기 생략
      (status/cto.json 등 실파일 오염 방지).
    """
    path = _STATUS_DIR / f"{clevel.lower()}.json"
    norm = normalize_status(status)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 기존 파일 read-merge
    data: dict = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}

    # 최상위 필드 갱신(기존 키 보존)
    data["clevel"] = clevel.lower()
    data["agent"] = clevel.lower()
    data["status"] = norm
    data["task_id"] = task_id
    data["last_task_id"] = task_id
    data["last_pushed_at"] = now
    data["title"] = title
    data["artifact_url"] = artifact_url
    data["commit"] = data.get("commit", "")
    data["note"] = note
    data["updated_at"] = now

    # active_tasks upsert
    tasks = data.get("active_tasks")
    if not isinstance(tasks, list):
        tasks = []
    found = False
    for t in tasks:
        if isinstance(t, dict) and t.get("task_id") == task_id:
            t["status"] = norm
            t["title"] = title
            t["note"] = note
            t["updated_at"] = now
            found = True
            break
    if not found:
        tasks.append({
            "task_id": task_id,
            "title": title,
            "status": norm,
            "note": note,
            "updated_at": now,
            "blocks": [],
        })
    data["active_tasks"] = tasks

    if dry_run:
        print("[DRY-RUN] status 파일 기록 예정 JSON:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        print("[DRY-RUN] 대상 경로: " + str(path))
        return True

    try:
        _STATUS_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("[StatusFile] 기록 완료 — " + path.name + " | status=" + norm)
        return True
    except OSError as e:
        print("[ERROR] status 파일 기록 실패: " + str(e), file=sys.stderr)
        return False


def update_queue_with_bridge(
    task_id: str,
    clevel: str,
    status: str,
    next_desc: str | None,
    next_clevel: str | None,
    terminal: bool,
    artifact_url: str | None,
    dry_run: bool,
) -> tuple[str, bool]:
    """
    일의 브릿지(Work Bridge): _queue.json(중앙 큐 = 단일 진실)에 완료 + '다음'을 구조로 기록.

    - 완료(DONE)일 때만 동작(진행중/이슈는 비적용).
    - 큐에 task_id가 있으면 DONE 처리 + processed_at + next/terminal 기록.
    - --next 가 있으면 '다음'을 PENDING 작업으로 큐에 append(depends_on=task_id, origin='bridge')
      → 다음 부팅이 자동으로 집을 수 있게(브릿지의 핵심: 완료가 '다음'을 낳는다).
    - --next 도 --terminal 도 없으면 next_missing=True 로 '끊김'을 가시화(차단하진 않음).

    반환: (label, changed) — label 은 텔레그램/로그 1줄, changed 는 큐 변경 여부.
    """
    if normalize_status(status) != "DONE":
        return ("", False)

    local_now = datetime.now(timezone.utc).astimezone()
    today = local_now.strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    queue: list = []
    if _QUEUE_PATH.exists():
        try:
            loaded = json.loads(_QUEUE_PATH.read_text(encoding="utf-8"))
            queue = loaded if isinstance(loaded, list) else []
        except Exception:
            queue = []

    # 완료 task 표시(큐에 있으면)
    for t in queue:
        if isinstance(t, dict) and t.get("task_id") == task_id:
            t["status"] = "DONE"
            t.setdefault("processed_at", today)
            # ④증거: 완료 단일 정의 4요건 — DONE 항목에 증거 URL 기록(거짓완료 추적)
            if artifact_url and artifact_url.strip():
                t["artifact"] = artifact_url.strip()
            if next_desc:
                t["next"] = next_desc
                t.pop("next_missing", None)
            elif terminal:
                t["terminal"] = True
                t.pop("next_missing", None)
            else:
                t["next_missing"] = True
            break

    appended_id = None
    appended_item: dict | None = None
    if next_desc:
        nclevel = (next_clevel or clevel).lower()
        appended_id = "NEXT-" + local_now.strftime("%Y%m%d-%H%M%S")
        appended_item = {
            "task_id": appended_id,
            "clevel": nclevel,
            "title": next_desc,
            "status": "PENDING",
            "depends_on": task_id,
            "from": clevel.lower(),
            "origin": "bridge",
            "enqueued_at": now_iso,
        }
        queue.append(appended_item)
        label = "다음→ " + next_desc + " [" + appended_id + "]"
    elif terminal:
        label = "종결(다음 없음)"
    else:
        label = "⚠️ 다음 미입력 — 브릿지 끊김"

    if dry_run:
        print("[DRY-RUN] _queue.json 브릿지 갱신 예정 — " + label)
        return (label, False)

    try:
        tmp = _QUEUE_PATH.with_name(_QUEUE_PATH.name + ".tmp")
        tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(str(tmp), str(_QUEUE_PATH))
        print("[Bridge] _queue.json 갱신 — " + label)
        # 끝난 일 자동 정리: 완료 2일 경과 DONE 을 _archive.json 으로 이동(오늘 완료는 보고용 잔류).
        # 실패해도 브릿지 본 동작에는 영향 없게 best-effort.
        try:
            from queue_archive import sweep_old_done
            sweep_old_done()
        except Exception as _e:  # noqa: BLE001
            print("[WARN] 끝난 일 자동 정리 건너뜀: " + str(_e), file=sys.stderr)
        # ── GAS 시트 동기화(best-effort) — 2단계 AI 배 SSOT 이관 ─────────────
        # _queue.json 직접쓰기가 이미 완료된 뒤 호출 → GAS 실패해도 데이터 유실 없음(폴백 완료).
        try:
            _gas_sync_bridge(
                task_id=task_id,
                clevel=clevel,
                queue_after=queue,
                appended_id=appended_id,
                appended_item=appended_item,
                next_desc=next_desc,
            )
        except Exception as _ge:  # noqa: BLE001
            print("[WARN] GAS 시트 동기화 실패(브릿지 무영향 — _queue.json 이미 갱신됨): "
                  + str(_ge), file=sys.stderr)
        return (label, True)
    except OSError as e:
        print("[ERROR] _queue.json 브릿지 갱신 실패: " + str(e), file=sys.stderr)
        return (label, False)


def build_telegram_message(clevel: str, task_id: str, status: str, summary: str,
                           bridge_label: str = "") -> str:
    """표준 보고 메시지: [{CLEVEL}] {task_id} {status} - {summary} (· 브릿지 라벨)"""
    msg = "[" + clevel.upper() + "] " + task_id + " " + status + " - " + summary
    if bridge_label:
        msg += "\n  ↳ " + bridge_label
    return msg


def send_telegram(clevel: str, task_id: str, status: str, summary: str, dry_run: bool,
                  bridge_label: str = "") -> bool:
    """
    @namuki_report_bot 으로 단일 보고 라인 발송 (telegram_notifier.TelegramNotifier 사용).
    --dry-run 이면 발송하지 않고 [DRY-RUN] would send 만 출력.
    토큰/chat_id 원문은 stdout 에 절대 출력하지 않는다.
    """
    msg = build_telegram_message(clevel, task_id, status, summary, bridge_label)

    if dry_run:
        print("[DRY-RUN] would send: " + msg)
        return True

    try:
        from telegram_notifier import TelegramNotifier
    except ImportError as e:
        print("[ERROR] telegram_notifier import 실패: " + str(e), file=sys.stderr)
        return False

    try:
        tg = TelegramNotifier()
        result = tg.send(msg)
        if result.get("ok"):
            print("[Telegram] 보고 완료: " + task_id)
            return True
        print("[ERROR] 텔레그램(Telegram) 발송 실패(미설정 또는 응답 오류)", file=sys.stderr)
        return False
    except Exception as e:
        print("[ERROR] 텔레그램(Telegram) 발송 예외: " + str(e), file=sys.stderr)
        return False


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="C-Level .bat post-action 표준 훅 (hook) — status json + 텔레그램(Telegram) 보고 (외부 DB 의존 없음)"
    )
    p.add_argument("--clevel", required=True, help="실행 주체 C-Level (예: CTO)")
    p.add_argument("--task-id", required=True,
                   help="업무 식별자 (예: CTO-002)")
    p.add_argument("--status", required=True, help="처리 상태: 진행중 | 완료 | 이슈")
    p.add_argument("--summary", required=True,
                   help='텔레그램(Telegram) 보고 요약 1줄 (예: "PC 자동 ON/OFF v1.0 가동")')
    p.add_argument("--version", default="v1.0", help="버전 문자열 (예: v1.1). 기본값: v1.0")
    p.add_argument("--changelog", default="",
                   help='Changelog 항목 1줄 (예: "2026-04-26 가동 시작") — note 로 기록')
    p.add_argument("--artifact-url", default=None,
                   help="[완료 시 필수] 증거 URL(스크린샷/로그/라이브확인 링크). "
                        "완료의 단일 정의 4요건 중 ④증거 — 없으면 DONE 등록 거부.")
    p.add_argument("--title", default=None,
                   help="작업 제목. 생략 시 --summary 값으로 대체.")
    # ── 일의 브릿지(Work Bridge): 완료 시 '다음'을 구조로 강제 ──────────────
    p.add_argument("--next", dest="next_desc", default=None,
                   help='[완료 시 필수] 이 작업이 낳는 다음 한 줄(브릿지). 예: "M5 검수카드에 발행 결과 동기화"')
    p.add_argument("--next-clevel", dest="next_clevel", default=None,
                   help="다음 작업 담당 C-Level. 생략 시 --clevel 동일.")
    p.add_argument("--terminal", action="store_true",
                   help="[완료 시] 다음이 없고 여기서 종결됨을 명시(--next 대체). 빈칸 통과 금지용.")
    p.add_argument("--dry-run", action="store_true",
                   help="실제 발송/파일쓰기 없이 stdout 출력만 (안전 검증 모드)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.dry_run:
        print("=" * 60)
        print("[DRY-RUN MODE] 실제 텔레그램(Telegram) 발송/status 파일쓰기 없음")
        print("=" * 60)

    # ── 완료의 단일 정의 4요건 중 ④증거 강제 (2026-06-05 GM 결재, AI CTO) ──────
    # status 가 DONE/완료 계열이면 --artifact-url(스크린샷/로그/라이브확인 링크)이
    # 반드시 있어야 한다. 없으면 DONE 등록 거부(거짓완료 차단). 진행중/이슈는 비적용.
    if normalize_status(args.status) == "DONE" and not (args.artifact_url and args.artifact_url.strip()):
        print("=" * 60, file=sys.stderr)
        print("[완료 거부] 완료(DONE)에는 증거 URL이 필수입니다 — 4요건 중 ④증거 누락.", file=sys.stderr)
        print("  → 완료의 단일 정의(4요건): ①커밋 [DONE][clevel][task_id] ②status DONE", file=sys.stderr)
        print("     ③다음(--next/--terminal) ④증거(--artifact-url). 하나라도 빠지면 완료 아님.", file=sys.stderr)
        print('  → 증거 URL을 첨부하세요: --artifact-url "<스크린샷/로그/라이브확인 링크>"', file=sys.stderr)
        print("  → 아직 증거가 없으면 --status 진행중 으로 보고하세요(완료 처리되지 않음).", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        return 2

    title = args.title if args.title else args.summary
    # changelog 는 note(상태 파일 메모) 로 흡수. 별도 변경이력 속성 없음(status json note로 단일화).
    note = args.changelog if args.changelog else args.summary

    ok_status = write_status_file(
        clevel=args.clevel,
        task_id=args.task_id,
        title=title,
        status=args.status,
        artifact_url=args.artifact_url,
        note=note,
        dry_run=args.dry_run,
    )

    # ── 일의 브릿지: 완료 시 '다음'을 구조로 기록(중앙 큐) ──────────────────
    is_done = normalize_status(args.status) == "DONE"
    if is_done and not args.next_desc and not args.terminal:
        print("=" * 60, file=sys.stderr)
        print("[브릿지 경고] 완료인데 --next(다음 한 줄) 또는 --terminal(종결) 미입력.",
              file=sys.stderr)
        print("  → 브릿지가 끊깁니다. 다음 부팅이 0에서 다시 시작합니다.",
              file=sys.stderr)
        print('  → 권장: --next "다음 할 일 한 줄"  또는  --terminal',
              file=sys.stderr)
        print("=" * 60, file=sys.stderr)
    bridge_label, _ = update_queue_with_bridge(
        task_id=args.task_id,
        clevel=args.clevel,
        status=args.status,
        next_desc=args.next_desc,
        next_clevel=args.next_clevel,
        terminal=args.terminal,
        artifact_url=args.artifact_url,
        dry_run=args.dry_run,
    )

    ok_telegram = send_telegram(
        clevel=args.clevel,
        task_id=args.task_id,
        status=args.status,
        summary=args.summary,
        dry_run=args.dry_run,
        bridge_label=bridge_label,
    )

    if args.dry_run:
        print("=" * 60)
        print("[DRY-RUN] 검증 결과: StatusFile "
              + ("OK" if ok_status else "FAIL")
              + " / 텔레그램(Telegram) 메시지 "
              + ("OK" if ok_telegram else "FAIL"))
        print("=" * 60)

    return 0 if (ok_status and ok_telegram) else 1


if __name__ == "__main__":
    sys.exit(main())
