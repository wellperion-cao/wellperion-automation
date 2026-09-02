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

# telegram_notifier 가 wellperion-agents/ 에 있으므로 import 경로 추가
# (ceo_morning_pipeline.py 와 동일 패턴)
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))
# queue_archive(끝난 일 자동 정리) 등 동일 폴더 sibling 모듈 import 보장
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))
# scripts/notify_gm_progress.is_routine 재사용(루틴/자동 완료 스팸 필터 — 2026-07-13)
_SCRIPTS_ROOT = _REPO_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))
try:
    from notify_gm_progress import is_routine
except Exception:
    def is_routine(*_texts: str) -> bool:
        return False

# 브릿지가 만드는 배도 queue_dispatch 가 만드는 배와 같은 모양이어야 한다(배10290).
# 판정·계산 로직 복제 금지(약속 L01) — 단일 지점을 import 로 재사용한다.
try:
    from assign_short_no import next_short_no as _next_short_no
except Exception:
    def _next_short_no(_queue):  # 폴백: 짧은 번호 없이 진행(동작은 유지)
        return None
try:
    from queue_dispatch import (ROLES as _ROLE_NICK, _norm as _norm_title,
                                _strip_role_tag, EXCLUDED_ROLES as _EXCLUDED_ROLES,
                                excluded_role_notice as _excluded_notice)
except Exception:
    _ROLE_NICK = {"ceo": "웰리", "cfo": "시뽀", "chro": "시로", "cmo": "시모",
                  "coo": "시우", "cpo": "시포", "cto": "시토", "cbo": "시보"}

    def _norm_title(s: str) -> str:
        return re.sub(r"\s+", "", s or "").lower()

    def _strip_role_tag(s: str) -> str:
        return re.sub(r"^\[[^\]]*\]\s*", "", s or "")

    _EXCLUDED_ROLES = {"chro", "cfo"}

    def _excluded_notice(role: str) -> str:
        return ("%s 는 나우열M 관할이라 AI 큐에서 배제합니다(GM 확정 2026-07-28)." % role)

# 부서 색동그라미 정본(단일 딕셔너리) — scripts/clevel_colors.py. 복사 금지, import 만.
try:
    from clevel_colors import labeled as clevel_labeled
except Exception:
    def clevel_labeled(clevel: str) -> str:
        return str(clevel or "").upper()

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
    next_parent: str | None = None,
    summary: str | None = None,
) -> tuple[str, bool]:
    """
    일의 브릿지(Work Bridge): _queue.json(중앙 큐 = 단일 진실)에 완료 + '다음'을 구조로 기록.

    - 완료(DONE)일 때만 동작(진행중/이슈는 비적용).
    - 큐에 task_id가 있으면 DONE 처리 + processed_at + next/terminal 기록.
    - --next 가 있으면 '다음'을 PENDING 작업으로 큐에 append(depends_on=task_id, origin='bridge')
      → 다음 부팅이 자동으로 집을 수 있게(브릿지의 핵심: 완료가 '다음'을 낳는다).
    - --next 도 --terminal 도 없으면 next_missing=True 로 '끊김'을 가시화(차단하진 않음).

    ① 중복배 억제(2026-07-14 시토·배993): --next-parent(umbrella task_id)가 주어지고
       그 umbrella 배가 큐에 있으면, '다음'을 새 배로 append 하지 않고 umbrella 의
       note 에 한 줄 흡수한다(한 기능=한 배 유지). 명시적 parent 필드일 때만 억제 —
       미지정/미발견이면 기존 동작(새 배 append) 그대로(애매하면 현행 유지).

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
            # '봤다' 한 줄(saw) 자동 채움 — --summary 에 숫자나 http 링크가 있으면만.
            # 그 외 추론 없음(추측으로 채우면 배지가 거짓말이 된다). 이미 있으면 덮어쓰지 않음.
            if not t.get("saw") and summary and summary.strip():
                _s = summary.strip()
                if re.search(r"\d", _s) or "http" in _s.lower():
                    t["saw"] = _s
            if next_desc:
                t["next"] = next_desc
                t.pop("next_missing", None)
            elif terminal:
                t["terminal"] = True
                t.pop("next_missing", None)
            else:
                t["next_missing"] = True
            break

    # ① 명시적 parent 지정 시: 새 배 대신 umbrella note 에 흡수(중복배 억제).
    umbrella = None
    if next_desc and next_parent:
        for t in queue:
            if isinstance(t, dict) and t.get("task_id") == next_parent:
                umbrella = t
                break

    appended_id = None
    if next_desc and umbrella is not None:
        prev_note = str(umbrella.get("note") or "")
        line = "- [" + today + "] " + next_desc + " (배 " + str(task_id) + ")"
        if line not in prev_note:  # 멱등
            umbrella["note"] = (prev_note + ("\n" if prev_note else "") + line).strip()
        label = "다음(umbrella " + str(next_parent) + " 흡수)→ " + next_desc
    elif next_desc and (next_clevel or clevel).lower() in _EXCLUDED_ROLES:
        # 인사(시로)·재무(시뽀)는 나우열M 관할 — AI 큐에 배를 만들지 않는다(GM 확정 2026-07-28).
        # 다만 '다음'을 버리지도 않는다: 끝난 배 안에 한 줄로 남겨 사람이 볼 수 있게 한다.
        nclevel = (next_clevel or clevel).lower()
        for t in queue:
            if isinstance(t, dict) and t.get("task_id") == task_id:
                prev_note = str(t.get("note") or "")
                line = ("- [" + today + "] 다음(배 안 만듦 · "
                        + _ROLE_NICK.get(nclevel, nclevel) + "=나우열M 관할): " + next_desc)
                if line not in prev_note:  # 멱등
                    t["note"] = (prev_note + ("\n" if prev_note else "") + line).strip()
                break
        label = "다음(배 배제 · " + _excluded_notice(nclevel) + ")→ " + next_desc

    elif next_desc:
        nclevel = (next_clevel or clevel).lower()
        nick = _ROLE_NICK.get(nclevel, nclevel.upper())
        bare = _strip_role_tag(next_desc).strip()
        key = _norm_title(bare)

        # ② 같은 담당·같은 제목의 열린 배가 이미 있으면 새 배를 만들지 않고 그 배에 한 줄 흡수.
        #    (2026-07-25 같은 문장 5척 도배 재발 방지 — 배10290)
        twin = None
        for t in queue:
            if not isinstance(t, dict):
                continue
            if t.get("status") not in ("PENDING", "IN_PROGRESS"):
                continue
            if (t.get("clevel") or "").lower() != nclevel:
                continue
            if _norm_title(_strip_role_tag(str(t.get("title") or ""))) == key:
                twin = t
                break

        if twin is not None:
            prev_note = str(twin.get("note") or "")
            line = "- [" + today + "] " + next_desc + " (배 " + str(task_id) + " 완료로 재확인)"
            if line not in prev_note:  # 멱등
                twin["note"] = (prev_note + ("\n" if prev_note else "") + line).strip()
            label = "다음(기존 배 " + str(twin.get("ship_no") or twin.get("task_id")) + " 흡수)→ " + next_desc
        else:
            # ③ 새 배는 queue_dispatch 가 만드는 배와 같은 모양으로 만든다(배10290).
            #    담당 머리표·짧은 번호·난이도·설명이 비면 G1 항로에서 '누가 뭘 하는지'가
            #    빈칸으로 뜬다(2026-07-28 GM 지적: "담당자도 없는 것들은 삭제하거나 설명해줘").
            appended_id = "NEXT-" + local_now.strftime("%Y%m%d-%H%M%S")
            nos = [t.get("ship_no") or 0 for t in queue if isinstance(t, dict)]
            parent = next((t for t in queue
                           if isinstance(t, dict) and t.get("task_id") == task_id), None)
            parent_title = _strip_role_tag(str((parent or {}).get("title") or "")) or str(task_id)
            note = (
                "[브릿지 자동 등록 " + today + "] 배 '" + parent_title + "' 을(를) 끝내면서 "
                "남긴 '다음' 이 이 배가 됐다. 담당=" + nick + ".\n"
                "▶할 일: " + bare + "\n"
                "▶왜 떠 있나: 완료가 '다음'을 낳게 해 일이 바다 한복판에 멈추지 않게 하는 "
                "구조다(약속 L11).\n"
                "▶설명이 부족하면 담당이 착수할 때 이 칸을 채운다."
            )
            if summary and summary.strip():
                note += "\n▶끝난 배 요약: " + summary.strip()
            ship = {
                "task_id": appended_id,
                "clevel": nclevel,
                "title": "[" + nick + "] " + bare,
                "status": "PENDING",
                "priority": "⛵돛단배",
                "depends_on": task_id,
                "from": clevel.lower(),
                "origin": "bridge",
                "enqueued_at": now_iso,
                "note": note,
                "next": "담당 확인 후 진행 · 완료 시 1줄 회신",
                "ship_no": (max(nos) + 1) if nos else 1,
                "short_no": _next_short_no(queue),
            }
            # 되돌릴 수 있는지(reversible)·누가 볼 일인지(audience)는 부모 배의 선언을 잇는다.
            # 없으면 비워 둔다 — 지어내면 자율 착수 판정이 거짓 근거로 열린다(2026-07-27).
            if parent is not None:
                if parent.get("audience") is not None:
                    ship["audience"] = parent.get("audience")
                if parent.get("reversible") is not None:
                    ship["reversible"] = parent.get("reversible")
            queue.append(ship)
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
        return (label, True)
    except OSError as e:
        print("[ERROR] _queue.json 브릿지 갱신 실패: " + str(e), file=sys.stderr)
        return (label, False)


def build_telegram_message(
    clevel: str,
    task_id: str,
    status: str,
    summary: str,
    bridge_label: str = "",
    title: str = "",
    version: str = "",
    changelog: str = "",
    artifact_url: str = "",
    next_desc: str = "",
    terminal: bool = False,
) -> str:
    """가독성 재정비 양식 (GM 피드백 2026-07-18) — 결론 먼저·짧은 줄·핵심 굵게·
    불필요 내부값(task_id·버전·changelog) 접기. 부서 색동그라미(clevel_colors) 반영.
    정보 손실 없음 — 접힌 값도 blockquote 안에 그대로 남는다(단지 시각적으로 후순위).

    형식(HTML parse_mode 전제):
        {STATUS_ICON} <b>{색동그라미} {닉네임} · {title}</b>
        {summary}                                    ← title 이 summary 와 다를 때만(중복 줄 생략)
        📍 {기록위치: artifact_url 있으면 그대로, 없으면 status/{clevel}.json}
        👉 다음: {next}                              ← next_desc/terminal/bridge_label 있을 때만
        <blockquote expandable>🆔 {task_id} · 📦 {version}{ · changelog}</blockquote>

    STATUS_ICON: 완료→✅ · 이슈→⚠️ · 진행중→⏳ · 기타→•
    """
    _icon_map = {
        "완료": "✅", "done": "✅", "DONE": "✅",
        "이슈": "⚠️", "issue": "⚠️",
        "진행중": "⏳", "inprogress": "⏳",
    }
    icon = _icon_map.get(status, _icon_map.get(status.lower(), "•"))

    # 결론 먼저: 상태 아이콘 + 부서 색동그라미 + 닉네임 + 제목(굵게)
    display_title = title if title else summary
    lines: list[str] = [
        icon + " <b>" + clevel_labeled(clevel) + " · " + display_title + "</b>",
    ]
    # 한 일 1줄: title 을 별도로 준 경우만 붙인다(title 생략 시 summary==display_title
    # 이라 굵은 제목과 완전 중복 — 접기 취지에 맞춰 중복 줄은 만들지 않는다).
    if summary.strip() != display_title.strip():
        lines.append(summary)

    # 📍 기록위치: 증거 URL 있으면 그대로, 없으면 status 파일 경로(항상 1줄 — 기록위치 알리기 원칙)
    record_loc = artifact_url.strip() if (artifact_url and artifact_url.strip()) \
        else ("status/" + clevel.lower() + ".json")
    lines.append("📍 " + record_loc)

    # 👉 다음: next_desc > terminal > bridge_label 순. 셋 다 없으면 생략
    if next_desc and next_desc.strip():
        lines.append("👉 다음: " + next_desc.strip())
    elif terminal:
        lines.append("👉 다음: 🌀 여기서 종결")
    elif bridge_label and bridge_label.strip():
        lines.append("👉 다음: " + bridge_label.strip())

    # 접기: 내부값(task_id·버전·changelog) — 필요할 때만 펼쳐보는 후순위 정보
    version_str = version if version else "v1.0"
    fold_bits = ["🆔 " + task_id, "📦 " + version_str]
    if changelog and changelog.strip():
        fold_bits.append(changelog.strip())
    lines.append("<blockquote expandable>" + " · ".join(fold_bits) + "</blockquote>")

    return "\n".join(lines)


# ── 완료보고 목적지 = AI 진행현황방 단일 (2026-08-04 GM "두 방 혼선 정리") ──────
# 배 완료·진행·이슈 보고(L18)는 정의상 전부 "AI 가 한 작업의 보고"다 — 규약(ssot/자율화
# 규약.md §4)·wellperion-gm-report SKILL §4-2-1("작업 완료 및 다음 작업 → AI 진행현황방")
# 그대로. 종전엔 배의 audience 칸이 방까지 골랐고(미선언 폴백=업무보고방), 그 탓에 8/1~4
# 실측 26건의 배 보고가 업무보고방을 채웠다. 08-03 "시토만 AI방" 패치는 args.clevel=="cto"
# 소문자 비교였는데 .bat 이 CTO 로 넘겨 한 번도 안 걸렸다(사후 실측: 08-03 11:02 등 계속
# 업무보고방행). 호출측 선택지를 없애고 이 관문 하나가 목적지를 정한다(약속 L21).
# audience 칸은 이제 G1 항로 표시 여부만 가른다(hangro_board.py) — 방 선택에 안 쓴다.
# 발송 실패·게이트 시 notify_or_fallback 이 업무보고방으로 폴백(조용한 소멸 없음 — 종전 유지).


def _split_head_body(title: str, summary: str) -> tuple[str, str]:
    """방 보고를 '제목 한 줄 + 본문 불릿'으로 가른다 (GM 지시 2026-08-06).

    - title 이 있으면 그게 제목이고 summary 전체가 본문이다.
    - title 이 없으면 summary 의 첫 문장을 제목으로 떼고 나머지를 본문으로 쓴다.
    - 본문은 '①②③④⑤' 번호나 ' · ' 로 끊어 '|' 로 잇는다 — notify_gm_progress 의
      _bullets 가 그 구분자로 줄을 나눠 폰에서 한 줄씩 읽히게 만든다.
    왜: 전에는 summary 를 통째로 제목 자리에 넣어 방에 글벽이 남았다("4건 중 3건 해소.
    ①발행 스크립트 타임아웃 — 당월매출 GAS 재시도 3회…" 처럼 한 줄로 200자).
    """
    title = (title or "").strip()
    summary = (summary or "").strip()
    if title:
        head, body = title, summary
    else:
        m = re.search(r"(?<=[.。])\s+|\n", summary)
        head = (summary[:m.start()] if m else summary).strip()
        body = (summary[m.end():] if m else "").strip()
    if body:
        body = re.sub(r"\s*[①②③④⑤⑥⑦⑧⑨]\s*", "|", body)
        body = re.sub(r"\s+·\s+", "|", body)
        body = "|".join(x.strip() for x in body.split("|") if x.strip())
    return head, body


def send_ai_progress_report(
    clevel: str,
    task_id: str,
    status: str,
    summary: str,
    dry_run: bool,
    title: str = "",
    artifact_url: str = "",
    next_desc: str = "",
    terminal: bool = False,
    bridge_label: str = "",
    version: str = "",
    changelog: str = "",
) -> bool:
    """AI 진행현황방 완료보고 — notify_gm_progress.notify_or_fallback() 단일 관문 재사용
    (제목/본문 분리는 _split_head_body 참고)
    (새 발신 함수 신설 금지 · 약속 L21). 모든 배의 L18 보고가 여기로 온다(2026-08-04).

    [2026-07-30 배202 팀리드 지시 — 조용한 소멸 구멍 폐쇄, 폴백 판단은 한 지점(notify_
    gm_progress.notify_or_fallback)에만] gate_off·daily_cap·room_unresolved·send_failed
    는 조용히 사라지지 않게 업무보고방(send_telegram)으로 폴백. dedup 만 소멸이 아니라
    폴백하지 않는다 — 이 구분 로직 자체는 여기서 복제하지 않고 notify_gm_progress.py 에
    한 곳만 둔다(ig_review_publish_watcher.py 도 같은 함수를 쓴다)."""
    try:
        from notify_gm_progress import notify_or_fallback as _notify_or_fallback  # noqa: PLC0415
    except Exception as e:
        print("[ERROR] notify_gm_progress import 실패 — 업무보고방으로 폴백: " + str(e),
              file=sys.stderr)
        return send_telegram(
            clevel=clevel, task_id=task_id, status=status, summary=summary, dry_run=dry_run,
            bridge_label=bridge_label, title=title, version=version, changelog=changelog,
            artifact_url=artifact_url or "", next_desc=next_desc or "", terminal=terminal,
        )

    nick = _ROLE_NICK.get(clevel.lower(), clevel.upper())
    state = "done" if normalize_status(status) == "DONE" else "doing"
    nxt = next_desc or ("🌀 여기서 종결" if terminal else None)

    def _fallback_to_gm_dm(_text: str) -> bool:
        print("[폴백] AI진행현황방 미발송(조용한 소멸 방지) → 업무보고방으로 폴백: " + task_id,
              file=sys.stderr)
        ok = send_telegram(
            clevel=clevel, task_id=task_id, status=status, summary=summary, dry_run=dry_run,
            bridge_label=bridge_label, title=title, version=version, changelog=changelog,
            artifact_url=artifact_url or "", next_desc=next_desc or "", terminal=terminal,
        )
        if not ok:
            print("[ERROR] 폴백(업무보고방)도 실패 — 완료보고가 어디에도 전달되지 않음: " + task_id,
                  file=sys.stderr)
        return ok

    # ★제목 한 줄 + 본문은 섹션으로 나눈다(GM 지시 2026-08-06 "9:00~9:20 사이에 보내준
    #   것들이 이해가 하나도 안 되 · 차라리 우리 쿵짝내용 처럼 정리해서"). 전에는 요약을
    #   통째로 제목 자리에 넣어, 방에 기술 용어를 이어 붙인 한 줄 글벽이 남았다.
    head, body = _split_head_body(title, summary)
    result = _notify_or_fallback(
        head, artifact_url or None,
        ship=nick, state=state, dry_run=dry_run, fix=body or None, nxt=nxt,
        fallback=_fallback_to_gm_dm,
    )
    if dry_run:
        print("[DRY-RUN] would send (AI진행현황방):\n" + result.get("text", ""))
        print("[DRY-RUN] notify_gm_progress reason=" + str(result.get("reason")))
        return True
    if result.get("sent"):
        print("[AI진행현황방] 보고 완료: " + task_id)
        return True
    if result.get("reason") == "dedup":
        print("[AI진행현황방] 중복 억제(dedup) — 같은 내용이 최근에 이미 전달됨(소멸 아님): "
              + task_id)
        return True
    # 위 두 경우가 아니면 notify_or_fallback 이 이미 _fallback_to_gm_dm 을 호출했다.
    return bool(result.get("fallback_ok"))


def send_telegram(
    clevel: str,
    task_id: str,
    status: str,
    summary: str,
    dry_run: bool,
    bridge_label: str = "",
    title: str = "",
    version: str = "",
    changelog: str = "",
    artifact_url: str = "",
    next_desc: str = "",
    terminal: bool = False,
) -> bool:
    """
    @namuki_report_bot 으로 L18 양식 보고 발송 (telegram_notifier.TelegramNotifier 사용).
    --dry-run 이면 발송하지 않고 [DRY-RUN] would send 만 출력.
    토큰/chat_id 원문은 stdout 에 절대 출력하지 않는다.
    """
    msg = build_telegram_message(
        clevel=clevel,
        task_id=task_id,
        status=status,
        summary=summary,
        bridge_label=bridge_label,
        title=title,
        version=version,
        changelog=changelog,
        artifact_url=artifact_url,
        next_desc=next_desc,
        terminal=terminal,
    )

    if dry_run:
        print("[DRY-RUN] would send:\n" + msg)
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


_LEDGER_PATH = _STATUS_DIR / "gm_observation_ledger.jsonl"


def record_gm_signal(clevel: str, signal: str, signal_type: str, dry_run: bool) -> bool:
    """
    세션 중 GM이 남긴 교정·선호 한 줄을 gm_observation_ledger.jsonl 에 append (배 10267).

    배경: 원장 대부분(기존 실측 96%+)이 시스템 자기가동 미러링이라 GM 성향 프로필이
    GM을 관찰하지 못했다 — 세션 교정이 대화에만 존재하다 세션 종료와 함께 사라졌기
    때문. 새 파일·새 감시기를 만들지 않고(약속 L21) 전 C-Level이 이미 반드시 지나가는
    이 관문(post-action)에 흡수한다.

    - 호출자가 --gm-signal 을 주지 않으면 이 함수 자체가 호출되지 않는다
      (기존 호출 100% 무영향 — main() 참고).
    - append-only. 기존 원장 줄은 절대 읽거나 고치지 않는다.
    - source = f"{clevel}_session_{YYYY-MM-DD}" — gm_profile_builder.py 의 세션신호
      판정("_session_" 포함, 예 cmo_session_2026-07-25)과 그대로 맞물린다(집계 코드 추가 0).
    """
    if not signal or not signal.strip():
        return False
    local_now = datetime.now(timezone.utc).astimezone()
    entry = {
        "observed_at": local_now.strftime("%Y-%m-%d %H:%M:%S"),
        "source": clevel.lower() + "_session_" + local_now.strftime("%Y-%m-%d"),
        "signal_type": signal_type or "correction",
        "summary": signal.strip(),
    }
    if dry_run:
        print("[DRY-RUN] gm_observation_ledger.jsonl append 예정:")
        print(json.dumps(entry, ensure_ascii=False))
        return True
    try:
        _STATUS_DIR.mkdir(parents=True, exist_ok=True)
        with open(_LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print("[GM신호] gm_observation_ledger append 완료 — source=" + entry["source"])
        return True
    except OSError as e:
        print("[ERROR] gm_observation_ledger append 실패: " + str(e), file=sys.stderr)
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
    p.add_argument("--next-parent", dest="next_parent", default=None,
                   help="[선택] 이 완료가 기존 umbrella 배의 하위단계면 그 umbrella task_id 를 "
                        "지정한다. 지정 시 '다음'을 새 배로 만들지 않고 umbrella note 에 흡수 "
                        "(한 기능=한 배·중복배 억제, 배993). 미지정이면 기존대로 새 배 생성.")
    p.add_argument("--terminal", action="store_true",
                   help="[완료 시] 다음이 없고 여기서 종결됨을 명시(--next 대체). 빈칸 통과 금지용.")
    p.add_argument("--dry-run", action="store_true",
                   help="실제 발송/파일쓰기 없이 stdout 출력만 (안전 검증 모드)")
    # ── 세션 GM 신호 흡수(배 10267) — 완전 선택 인자, 생략 시 무동작 ──────────
    p.add_argument("--gm-signal", dest="gm_signal", default=None,
                   help="[선택] 이번 세션에서 GM이 직접 남긴 교정·선호 한 줄. 있으면 "
                        "gm_observation_ledger.jsonl 에 세션신호로 append(없으면 아무 일도 "
                        "안 일어남 — 기존 호출 무영향).")
    p.add_argument("--gm-signal-type", dest="gm_signal_type", default="correction",
                   help="--gm-signal 의 유형(correction|preference|missed 등). 기본값: correction")
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
        print("     ③증거(--artifact-url). 빠지면 완료 아님.", file=sys.stderr)
        print("     ※'다음'은 더 이상 필수가 아니다 — 안 적으면 종결이다(GM 지시 2026-08-19).", file=sys.stderr)
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

    # ── 완료 처리 — '다음'은 있을 때만 남긴다 (GM 지시 2026-08-19) ──────────────
    # 종전에는 --next 도 --terminal 도 없으면 "브릿지가 끊긴다"고 경고했다. 그 경고 때문에
    # 담당들이 끝낼 때마다 억지로 후속 한 줄을 지어냈고, 그게 그대로 새 배가 됐다.
    # GM 원문(2026-08-19): "배를 처리하고, 다음에 이어서 뭔가를 계속 하려고 하다보니 어쩔수없이
    # 이어서 배가 늘어난 것 같은데, 이것도 없었으면 좋겠어. 억지로 안만들어도되, 그냥 종결처리해도되."
    # 그래서 기본값을 뒤집는다 — 안 적으면 종결이다. 진짜 이어질 일이 있을 때만 --next 를 쓴다.
    is_done = normalize_status(args.status) == "DONE"
    if is_done and not args.next_desc and not args.terminal:
        args.terminal = True
    # ── GM 신호 누락 알림(배 10267) — 사람이 낀 완료에만, 막지는 않는다 ────────
    # 배경: --gm-signal 흡수 경로는 2026-07-29 발효했는데 저장소 어디에서도 이 인자를
    # 부르지 않아 24시간 동안 실제 기록이 1건뿐이었다(경로는 있고 아무도 몰랐다).
    # 그래서 경로가 이미 지나가는 이 자리에서 한 줄로 알린다. 루틴·기계 완료
    # (welly_auto_runner·ADHOC 등)는 GM 교정이 나올 자리가 아니라 제외 — 스팸 방지.
    if is_done and not args.gm_signal and not is_routine(args.task_id, args.changelog):
        print('[GM신호 알림] 이번 세션에서 GM이 교정·선호를 남겼으면 원장에 함께 남기세요 '
              '— 안 남기면 그 교정은 세션 종료와 함께 사라집니다.')
        print('  → 예: --gm-signal "GM: 완료 보고는 표로만" --gm-signal-type preference')
    bridge_label, _ = update_queue_with_bridge(
        task_id=args.task_id,
        clevel=args.clevel,
        status=args.status,
        next_desc=args.next_desc,
        next_clevel=args.next_clevel,
        terminal=args.terminal,
        artifact_url=args.artifact_url,
        dry_run=args.dry_run,
        next_parent=args.next_parent,
        summary=args.summary,
    )

    # ── 루틴/자동 완료 스팸 필터(2026-07-13, GM 지시) ───────────────────────
    # task_id 또는 changelog 에 ADHOC·auto-log·chore·mirror 류 마커가 있는
    # "완료" 는 실제 딜리버러블이 아닌 기계적 정리성 완료라 GM 채널 보고에서
    # 제외한다(status 파일 기록·큐 브릿지는 그대로 유지 — 텔레그램만 스킵).
    if is_done and is_routine(args.task_id, args.changelog):
        print("[Telegram] 루틴/자동 완료 — GM 채널 보고 스킵(스팸 방지): " + args.task_id)
        ok_telegram = True
    else:
        # 목적지는 이 관문이 정한다 — 배 보고(L18)는 역할·audience 무관 전부 AI 진행현황방
        # (2026-08-04 GM "두 방 혼선 정리" · 근거는 send_ai_progress_report 위 주석).
        print("[라우팅] L18 배 보고 → AI 진행현황방 (실패 시 업무보고방 폴백)")
        ok_telegram = send_ai_progress_report(
            clevel=args.clevel,
            task_id=args.task_id,
            status=args.status,
            summary=args.summary,
            dry_run=args.dry_run,
            title=title,
            artifact_url=args.artifact_url or "",
            next_desc=args.next_desc or "",
            terminal=args.terminal,
            bridge_label=bridge_label,
            version=args.version,
            changelog=args.changelog,
        )

    # ── 세션 GM 신호 흡수(배 10267): --gm-signal 없으면 완전 무동작 ──────────
    if args.gm_signal:
        record_gm_signal(
            clevel=args.clevel,
            signal=args.gm_signal,
            signal_type=args.gm_signal_type,
            dry_run=args.dry_run,
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
