#!/usr/bin/env python3
"""주간 AI 자기정리·학습 — Before/After 체감 카드 (weekly_self_review.py)

설계: docs/superpowers/specs/2026-07-10-weekly-ai-self-review-before-after-design.md
GM 범위 확대(2026-07-10): 3파트 통합 —
  ① 메모리 정리  ② AI 트렌드 학습 → 우리 적용  ③ C-Level 컨텍스트(_queue) 정리.

원칙(카드): 모든 줄이 "전 → 후" 숫자 대비 아니면 출력 금지(추상 요약 금지). ⏱30초 요약 먼저.

일요일 릴레이(10:30 본 스크립트):
  일 09:00  Education-Archive           (기존 유지)
  일 09:30  ai_education_auto_learner --no-send (기존, 발송만 OFF — 수집·요약은 카드 원료)
  일 10:00  ai_learning_proposer --no-send        (기존, 트리거 월→일 이동 + 발송만 OFF)
  일 10:30  weekly_self_review.py (본 스크립트) — 메모리+큐 정리 + 카드 조립·발송

안전(배237 가역=자율 원칙):
  - 메모리 스냅샷(zip, 4주 보관) 없이는 병합·갱신 실행 안 함.
  - 메모리 완전 삭제는 절대 자율 금지 — 후보만 status/self_review_delete_queue.json 적재,
    --approve-delete <file> 로만 실제 삭제(그 직전 재스냅샷).
  - 큐 정리(완료 아카이브)는 기존 queue_archive_sweep.py 재사용(신규 아카이브 로직 없음·net-zero).
  - 실제 텔레그램 발송은 게이트 WEEKLY_REVIEW_LIVE_SEND=1 일 때만(기본 OFF·GM go 시 ON).
    OFF여도 스캔·정리·카드조립·로그기록은 전부 정상 실행(콘솔로 매주 검증 가능).

사용법:
  python scripts/weekly_self_review.py                   # 실행(게이트 OFF면 발송만 생략)
  python scripts/weekly_self_review.py --dry-run          # 전부 읽기전용 — 스냅샷·변경·발송 0
  python scripts/weekly_self_review.py --list-delete-queue
  python scripts/weekly_self_review.py --approve-delete <file.md>
"""
from __future__ import annotations

import argparse
import difflib
import io
import json
import os
import re
import subprocess
import sys
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
ENV_FILE = BASE_DIR / "telegram_bot" / ".env"
STATUS_DIR = BASE_DIR / "status"
SCRIPTS_DIR = BASE_DIR / "scripts"

MEMORY_DIR = Path(r"C:\Users\jjky0\.claude\projects\C--Users-jjky0-welperion-automation\memory")
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"

SNAPSHOT_DIR = STATUS_DIR / "_memory_snapshots"
SNAPSHOT_RETAIN_WEEKS = 4

LOG_FILE = STATUS_DIR / "self_review_log.jsonl"
DELETE_QUEUE_FILE = STATUS_DIR / "self_review_delete_queue.json"

PROPOSALS_FILE = STATUS_DIR / "learning_proposals.json"
QUEUE_FILE = STATUS_DIR / "_queue.json"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SCRIPTS_DIR / "aide_detectors") not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR / "aide_detectors"))

# ── 라이브 발송 게이트 (기본 OFF · GM go 시에만 ON — 다른 게이트와 절대 공유 금지) ──
LIVE_SEND_ENV = "WEEKLY_REVIEW_LIVE_SEND"
_ON_VALUES = {"1", "true", "yes", "on"}


def live_send_enabled() -> bool:
    return os.environ.get(LIVE_SEND_ENV, "").strip().lower() in _ON_VALUES


# ── 자율 실행 한도 (한 회차 비용·리스크 상한) ──
MAX_MERGE_CLUSTERS_PER_RUN = 3
MAX_UPDATE_FILES_PER_RUN = 3
STALE_DAYS = 90
DUP_SIMILARITY_THRESHOLD = 0.55

CLEVEL_ROLES = ["ceo", "cfo", "chro", "cmo", "coo", "cpo", "cto"]
ROLE_NICK = {"ceo": "웰리", "cfo": "시뽀", "chro": "시로", "cmo": "시모",
             "coo": "시우", "cpo": "시포", "cto": "시토"}

# 알려진 폐기 시스템(모순 탐지용) — CLAUDE.md 명시 폐기 항목. 새 폐기건 추가는 여기 1줄.
RETIRED_MARKERS = [
    ("Notion AI 조직 DB", "폐기 진행 중·호출 금지(CLAUDE.md §2)"),
    ("CEO 인박스 DB", "폐기 — 호출 금지(CLAUDE.md §3)"),
    ("ceo_morning_brief_08.py", "구버전 폐기·미존재(정본=ceo_morning_pipeline.py, CLAUDE.md §3)"),
    ("카카오 오픈채팅봇", "R&D 종결(비즈채널은 정상 — project_kakao_bot_rd_closed)"),
]


# ═══════════════════════════════════════════
#  유틸
# ═══════════════════════════════════════════
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_env() -> dict:
    out = {}
    if not ENV_FILE.exists():
        return out
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# ═══════════════════════════════════════════
#  파트 A — 메모리 스냅샷 + 스캔 + 자율 정리
# ═══════════════════════════════════════════
def _prune_snapshots():
    cutoff = datetime.now() - timedelta(weeks=SNAPSHOT_RETAIN_WEEKS)
    for f in SNAPSHOT_DIR.glob("*.zip"):
        try:
            d = datetime.strptime(f.stem, "%Y-%m-%d")
        except ValueError:
            continue
        if d < cutoff:
            try:
                f.unlink()
            except Exception:
                pass


def snapshot_memory(dry_run: bool) -> Path | None:
    """정리 전 메모리 폴더 전체를 zip 백업(가역화 장치). dry-run 은 완전 무행동."""
    if dry_run:
        return None
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    _prune_snapshots()
    if not MEMORY_DIR.exists():
        return None
    dest = SNAPSHOT_DIR / f"{today_str()}.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in MEMORY_DIR.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(MEMORY_DIR))
    return dest


def list_memory_files() -> list[Path]:
    if not MEMORY_DIR.exists():
        return []
    return sorted(p for p in MEMORY_DIR.glob("*.md") if p.name != "MEMORY.md")


def _category(name: str) -> str:
    return name.split("_", 1)[0] if "_" in name else name


def _find_duplicate_pairs(files: list[Path]) -> list[tuple[Path, Path, float]]:
    """카테고리(feedback_/project_/reference_) 내 본문 유사도 기반 병합 후보 쌍."""
    by_cat: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        by_cat[_category(f.name)].append(f)

    contents: dict[Path, str] = {}

    def _content(f: Path) -> str:
        if f not in contents:
            try:
                contents[f] = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                contents[f] = ""
        return contents[f]

    pairs = []
    for group in by_cat.values():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                ta, tb = _content(a), _content(b)
                if not ta or not tb:
                    continue
                shorter, longer = sorted((len(ta), len(tb)))
                if longer > 2 * max(shorter, 1):
                    continue  # 길이 2배+ 차이 — 저유사 확정, 비교 생략(성능)
                ratio = difflib.SequenceMatcher(None, ta, tb).ratio()
                if ratio >= DUP_SIMILARITY_THRESHOLD:
                    pairs.append((a, b, ratio))
    return pairs


def scan_memory() -> dict:
    files = list_memory_files()
    index_text = MEMORY_INDEX.read_text(encoding="utf-8") if MEMORY_INDEX.exists() else ""
    total_kb = round(sum(f.stat().st_size for f in files) / 1024, 1)

    linked_names = set(re.findall(r"\]\(([\w\-]+\.md)\)", index_text))
    orphans = [f for f in files if f.name not in linked_names]
    dead_links = sorted(n for n in linked_names if not (MEMORY_DIR / n).exists())

    now = datetime.now()
    stale = []
    for f in files:
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
        except Exception:
            continue
        if (now - mtime).days > STALE_DAYS and f.name not in linked_names:
            stale.append(f)

    contradictions = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for term, note in RETIRED_MARKERS:
            if term in text and "폐기" not in text and "종결" not in text:
                contradictions.append((f, term, note))

    dup_pairs = _find_duplicate_pairs(files)

    return {
        "files": files, "file_count": len(files), "total_kb": total_kb,
        "orphans": orphans, "dead_links": dead_links, "stale": stale,
        "contradictions": contradictions, "dup_pairs": dup_pairs,
        "index_text": index_text,
    }


def _cluster_pairs(pairs: list[tuple[Path, Path, float]]) -> list[list[Path]]:
    """유사쌍을 union-find 로 병합 클러스터(2개 이상)로 묶는다."""
    parent: dict[Path, Path] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b, _ in pairs:
        union(a, b)

    clusters: dict[Path, set[Path]] = defaultdict(set)
    for a, b, _ in pairs:
        clusters[find(a)].add(a)
        clusters[find(a)].add(b)

    out = [sorted(members, key=lambda p: p.name) for members in clusters.values()]
    return [c for c in out if len(c) >= 2]


def _llm_merge(files: list[Path]) -> str | None:
    try:
        from model_router import run_claude
    except ImportError:
        return None
    bodies = []
    for f in files:
        try:
            bodies.append(f"### {f.name}\n{f.read_text(encoding='utf-8', errors='replace')}")
        except Exception:
            continue
    if len(bodies) < 2:
        return None
    prompt = (
        f"아래는 웰페리온 AI 메모리 파일 {len(bodies)}개다(같은 주제 중복 후보). "
        "모든 사실·수치·날짜를 보존하면서 한 파일로 병합하라. "
        "형식은 기존 메모리 파일과 동일한 짧은 압축 불릿(마크다운) 스타일 유지, 설명문 금지. "
        "출력은 병합된 파일 본문만(다른 텍스트 없이).\n\n" + "\n\n".join(bodies)
    )
    text, _model = run_claude(prompt, label="weekly-self-review-merge")
    return text


def _llm_update(f: Path, term: str, note: str) -> str | None:
    try:
        from model_router import run_claude
    except ImportError:
        return None
    try:
        body = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    prompt = (
        f"아래 웰페리온 AI 메모리 파일이 폐기된 항목 '{term}'을 현행처럼 언급한다. "
        f"현재 사실: {note}. 이 사실을 반영해 파일을 현행화하라(다른 내용은 보존). "
        "형식은 기존과 동일한 압축 불릿 스타일, 출력은 갱신된 파일 본문만.\n\n" + body
    )
    text, _model = run_claude(prompt, label="weekly-self-review-update")
    return text


def apply_memory_maintenance(scan: dict, dry_run: bool) -> dict:
    """병합·갱신·인덱스 정리(가역=자율). 완전 삭제는 이 함수에서 절대 하지 않음."""
    result = {"merged": 0, "updated": 0, "index_fixed": 0,
              "merge_detail": None, "update_detail": None}
    if dry_run:
        return result

    index_text = scan["index_text"]

    # ① 병합 — 클러스터당 LLM 1회, 상한 MAX_MERGE_CLUSTERS_PER_RUN
    clusters = _cluster_pairs(scan["dup_pairs"])[:MAX_MERGE_CLUSTERS_PER_RUN]
    for cluster in clusters:
        merged_text = _llm_merge(cluster)
        if not merged_text or not merged_text.strip():
            continue
        keep, drop = cluster[0], cluster[1:]
        keep.write_text(merged_text.strip() + "\n", encoding="utf-8")
        for d in drop:
            try:
                d.unlink()
            except Exception:
                continue
            index_text = index_text.replace(f"]({d.name})", f"]({keep.name})")
        result["merged"] += 1
        if result["merge_detail"] is None:
            result["merge_detail"] = f"{len(cluster)}개 파일 → 1개 병합 ({keep.name})"

    # ② 갱신 — 모순 후보, 파일 단위 dedup, 상한 MAX_UPDATE_FILES_PER_RUN
    seen_update: set[str] = set()
    for f, term, note in scan["contradictions"]:
        if len(seen_update) >= MAX_UPDATE_FILES_PER_RUN:
            break
        if f.name in seen_update or not f.exists():
            continue
        updated_text = _llm_update(f, term, note)
        if not updated_text or not updated_text.strip():
            continue
        f.write_text(updated_text.strip() + "\n", encoding="utf-8")
        seen_update.add(f.name)
        result["updated"] += 1
        if result["update_detail"] is None:
            result["update_detail"] = f"{f.name} 낡은 값 → 현행화({term})"

    # ③ 인덱스 정리 — 죽은 링크(참조는 있으나 파일 없음) 라인 제거
    fixed = 0
    if scan["dead_links"]:
        new_lines = []
        for line in index_text.splitlines():
            refs = re.findall(r"\]\(([\w\-]+\.md)\)", line)
            if refs and any(n in scan["dead_links"] and not (MEMORY_DIR / n).exists() for n in refs):
                fixed += 1
                continue
            new_lines.append(line)
        index_text = "\n".join(new_lines)
        if not index_text.endswith("\n"):
            index_text += "\n"
    result["index_fixed"] = fixed

    if result["merged"] or result["updated"] or fixed:
        MEMORY_INDEX.write_text(index_text, encoding="utf-8")

    return result


# ── 삭제 큐(비가역 — 제안만, 승인 후 실제 삭제) ──
def load_delete_queue() -> list:
    if not DELETE_QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(DELETE_QUEUE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_delete_queue(items: list):
    DELETE_QUEUE_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def update_delete_queue(stale_files: list[Path], dry_run: bool) -> int:
    existing = load_delete_queue()
    names = {c["file"] for c in existing}
    if dry_run:
        return len(names | {f.name for f in stale_files})
    added = 0
    for f in stale_files:
        if f.name in names:
            continue
        existing.append({"file": f.name, "reason": f"{STALE_DAYS}일+ 미수정 & 인덱스 미참조",
                          "flagged_at": today_str()})
        names.add(f.name)
        added += 1
    if added:
        save_delete_queue(existing)
    return len(existing)


def cmd_approve_delete(filename: str):
    q = load_delete_queue()
    target = next((c for c in q if c["file"] == filename), None)
    if not target:
        print(f"[ERROR] 삭제 대기 목록에 없음: {filename}")
        sys.exit(1)
    snap = snapshot_memory(dry_run=False)  # 삭제 직전 재스냅샷(가역 보장)
    print(f"[스냅샷] {snap}")
    path = MEMORY_DIR / filename
    if path.exists():
        path.unlink()
        print(f"[삭제 완료] {filename} — 되돌리려면 위 스냅샷 zip 에서 복원")
    else:
        print(f"[정보] 파일이 이미 없음: {filename}")
    q = [c for c in q if c["file"] != filename]
    save_delete_queue(q)


def cmd_list_delete_queue():
    q = load_delete_queue()
    if not q:
        print("[정보] 삭제 대기 없음")
        return
    print(f"삭제 대기 {len(q)}건:")
    for c in q:
        print(f"  - {c['file']}  ({c['reason']}, 지정: {c['flagged_at']})")
    print("승인: python scripts/weekly_self_review.py --approve-delete <file>")


# ═══════════════════════════════════════════
#  파트 B — AI 트렌드 학습 → 우리 적용 (기존 proposer/learner 결과 재사용)
# ═══════════════════════════════════════════
def load_proposals() -> list:
    if not PROPOSALS_FILE.exists():
        return []
    try:
        data = json.loads(PROPOSALS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def learning_loop_snapshot() -> dict:
    cards = load_proposals()
    applied = sum(1 for c in cards if c.get("status") == "반영")
    pending = sum(1 for c in cards if c.get("status") == "제안")
    eff_ok = sum(1 for c in cards if c.get("status") == "반영" and c.get("효과") == "효과있음")
    return {"applied": applied, "pending": pending, "eff_ok": eff_ok}


def this_week_trend_proposals() -> list:
    """오늘 생성된 신규 제안(status=제안) — 카드 'AI 트렌드 적용' 원료."""
    today = today_str()
    return [c for c in load_proposals() if c.get("생성일") == today and c.get("status") == "제안"]


# ═══════════════════════════════════════════
#  파트 C — C-Level 컨텍스트(_queue.json) 정리
# ═══════════════════════════════════════════
def load_queue() -> list:
    if not QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _is_drift(item: dict, pending_clevels: set) -> bool:
    """🌀표류 판정(보수적, hangro_board.py 와 동일 기준): 완료(DONE)인데
    terminal=false·next 비었고·같은 clevel 의 후속 PENDING 도 없음."""
    if item.get("status") != "DONE":
        return False
    if item.get("terminal", False):
        return False
    if str(item.get("next") or "").strip():
        return False
    return (item.get("clevel") or "").lower() not in pending_clevels


def _archive_candidates(ships: list) -> list:
    """queue_archive_sweep.py 와 동일 기준(오늘 입항 제외 지난 terminal)."""
    today = today_str()
    out = []
    for it in ships:
        if str(it.get("status") or "") not in ("DONE", "완료", "폐기"):
            continue
        if str(it.get("processed_at") or "")[:10] == today:
            continue
        out.append(it)
    return out


def clevel_snapshot(queue: list) -> dict:
    try:
        import stall_watch  # aide_detectors — 정체 판정 정본 재사용(net-zero)
    except Exception:
        stall_watch = None

    pending_clevels = {(it.get("clevel") or "").lower() for it in queue if it.get("status") == "PENDING"}
    out = {}
    for role in CLEVEL_ROLES:
        ships = [it for it in queue if (it.get("clevel") or "").lower() == role]
        out[role] = {
            "active": sum(1 for it in ships if it.get("status") in ("PENDING", "IN_PROGRESS")),
            "in_progress": sum(1 for it in ships if it.get("status") == "IN_PROGRESS"),
            "pending": sum(1 for it in ships if it.get("status") == "PENDING"),
            "stalled": len(stall_watch.detect_stalled(ships)) if stall_watch else 0,
            "drift": sum(1 for it in ships if _is_drift(it, pending_clevels)),
            "archive_candidates": len(_archive_candidates(ships)),
        }
    return out


def run_queue_archive_sweep(dry_run: bool) -> None:
    """완료 아카이브 정리 — 기존 queue_archive_sweep.py 재사용(신규 로직 없음)."""
    if dry_run:
        return
    try:
        py = sys.executable or "python"
        subprocess.run([py, str(SCRIPTS_DIR / "queue_archive_sweep.py")],
                        cwd=str(BASE_DIR), timeout=60)
    except Exception as e:
        print(f"[WARN] queue_archive_sweep 실행 실패: {type(e).__name__}: {e}")


# ═══════════════════════════════════════════
#  로그
# ═══════════════════════════════════════════
def append_log(record: dict):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_last_log() -> dict | None:
    if not LOG_FILE.exists():
        return None
    lines = [l for l in LOG_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except Exception:
        return None


# ═══════════════════════════════════════════
#  카드 조립 — 모든 줄이 "전 → 후" 아니면 추가하지 않는다(스크립트 강제).
# ═══════════════════════════════════════════
def build_card(mem_before: dict, mem_after: dict, maint: dict, delete_pending: int,
                loop_before: dict, loop_after: dict, trend_proposals: list,
                clevel_before: dict, clevel_after: dict, archived_this_run: int) -> str:
    now = datetime.now()
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    date_label = f"{now.month}/{now.day} {weekday_kr}"

    mem_file_delta = mem_after["file_count"] - mem_before["file_count"]
    dup_before, dup_after = len(mem_before["dup_pairs"]), len(mem_after["dup_pairs"])
    contra_before, contra_after = len(mem_before["contradictions"]), len(mem_after["contradictions"])
    stale_before, stale_after = len(mem_before["stale"]), len(mem_after["stale"])

    active_before = sum(v["active"] for v in clevel_before.values())
    active_after = sum(v["active"] for v in clevel_after.values())
    stalled_before = sum(v["stalled"] for v in clevel_before.values())
    stalled_after = sum(v["stalled"] for v in clevel_after.values())
    drift_before = sum(v["drift"] for v in clevel_before.values())
    drift_after = sum(v["drift"] for v in clevel_after.values())

    no_change = (
        mem_file_delta == 0 and maint["merged"] == 0 and maint["updated"] == 0
        and maint["index_fixed"] == 0 and delete_pending == 0
        and loop_before.get("applied") == loop_after.get("applied")
        and not trend_proposals and archived_this_run == 0
        and stalled_before == stalled_after and drift_before == drift_after
    )
    if no_change:
        return (
            f"🧠 주간 AI 자기정리 — 이번 주 변화 없음 ({date_label})\n"
            f"메모리 {mem_after['file_count']}개 건강 · 큐 정체 {stalled_after}건·표류 {drift_after}건 · 대기 0건\n"
            f"기록: status/self_review_log.jsonl"
        )

    summary_bits = []
    if mem_file_delta != 0:
        summary_bits.append(f"메모리 {abs(mem_file_delta)}개 {'줄고' if mem_file_delta < 0 else '늘고'}")
    if contra_before - contra_after > 0:
        summary_bits.append(f"모순 {contra_before - contra_after}건 고치고")
    loop_delta = loop_after.get("applied", 0) - loop_before.get("applied", 0)
    if loop_delta > 0:
        summary_bits.append(f"개선 {loop_delta}건 반영")
    if trend_proposals:
        summary_bits.append(f"적용 제안 {len(trend_proposals)}건 대기")
    if archived_this_run > 0:
        summary_bits.append(f"완료 {archived_this_run}건 아카이브")
    summary_line = (", ".join(summary_bits) + ".") if summary_bits else "메모리·큐 소폭 정합만 진행."

    lines = [
        f"🧠 주간 AI 자기정리 — 이번 주 이렇게 똑똑해졌습니다 ({date_label})",
        "",
        f"⏱ 30초 요약: {summary_line}",
        "",
        "🧠 메모리 정리  Before → After",
        f"· 파일 {mem_before['file_count']}개 → {mem_after['file_count']}개 "
        f"(병합 {maint['merged']} · 갱신 {maint['updated']} · 인덱스정리 {maint['index_fixed']})",
        f"· 중복 {dup_before}쌍 → {dup_after}  |  모순 {contra_before}건 → {contra_after}  |  "
        f"{STALE_DAYS}일+낡음 {stale_before}건 → {stale_after}건",
    ]
    if maint.get("merge_detail"):
        lines.append(f"· 예) {maint['merge_detail']}")
    elif maint.get("update_detail"):
        lines.append(f"· 예) {maint['update_detail']}")
    if delete_pending > 0:
        lines.append(
            f"🔒 삭제 대기 {delete_pending}건 (비가역 → 승인 필요): "
            f'"python scripts/weekly_self_review.py --approve-delete <file>"'
        )

    lines += [
        "",
        "📡 AI 트렌드 → 우리 적용  Before → After",
        f"· 반영 {loop_before.get('applied', 0)}건 → {loop_after.get('applied', 0)}건 "
        f"· 효과있음 {loop_before.get('eff_ok', 0)}건 → {loop_after.get('eff_ok', 0)}건",
        f"· 승인 대기 {loop_before.get('pending', 0)}건 → {loop_after.get('pending', 0)}건",
    ]
    for i, p in enumerate(trend_proposals[:2], 1):
        what = str(p.get("무엇을", ""))[:60]
        now_txt = str(p.get("현재는", "") or "(미기재)")[:70]
        after_txt = str(p.get("바뀌면", "") or "(미기재)")[:70]
        lines.append(f"{i}. [{p.get('대상_clevel', '?')}] {what}")
        lines.append(f"   현재는: {now_txt}")
        lines.append(f"   바뀌면: {after_txt}")
        lines.append(f"   → 승인: \"python scripts/ai_learning_proposer.py --approve {p.get('id', '')}\"")

    lines += [
        "",
        "🧭 C레벨 컨텍스트 정리  Before → After",
        f"· 활성 {active_before}척 → {active_after}척  |  정체 {stalled_before}건 → {stalled_after}건  |  "
        f"표류 {drift_before}건 → {drift_after}건",
    ]
    for role in CLEVEL_ROLES:
        b, a = clevel_before[role], clevel_after[role]
        if b["active"] == 0 and a["active"] == 0 and b["stalled"] == 0 and b["drift"] == 0:
            continue
        lines.append(
            f"  {ROLE_NICK[role]} 활성 {b['active']}→{a['active']} · "
            f"정체 {b['stalled']}→{a['stalled']} · 표류 {b['drift']}→{a['drift']}"
        )
    if archived_this_run > 0:
        lines.append(f"· 완료 {archived_this_run}건 아카이브 이동(status/_queue_archive.json)")

    lines += ["", "기록: status/self_review_log.jsonl · 상세 G1 'AI 자기학습' 섹션"]
    return "\n".join(lines)


# ═══════════════════════════════════════════
#  텔레그램 발송 (게이트 뒤)
# ═══════════════════════════════════════════
def send_telegram(message: str) -> bool:
    if not live_send_enabled():
        print(f"\n[게이트 OFF] 실제 텔레그램 발송 생략 — {LIVE_SEND_ENV}=1 로 GM 승인 후 활성화")
        return False
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[WARN] 텔레그램 설정 없음 — 발송 생략")
        return False
    if len(message) > 4000:
        message = message[:3990] + "\n...(잘림)"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = json.loads(resp.read().decode()).get("ok", False)
            try:
                from tg_outbound_log import log_outbound
                log_outbound(message, chat_id=chat_id, source="weekly_self_review.send_telegram",
                              ok=ok, kind="sendMessage")
            except Exception:
                pass
            print(f"[텔레그램 {'발송 성공' if ok else '발송 실패'}]")
            return ok
    except Exception as e:
        print(f"[ERROR] 텔레그램 발송 실패: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════
#  메인 파이프라인
# ═══════════════════════════════════════════
def run(dry_run: bool):
    print(f"[시작] 주간 AI 자기정리 ({now_str()})  dry-run={dry_run}\n")

    # ── 파트 A: 메모리 ──
    print("[1/4] 메모리 스캔(정리 전)...")
    mem_before = scan_memory()
    print(f"  파일 {mem_before['file_count']}개 · {mem_before['total_kb']}KB · "
          f"중복후보 {len(mem_before['dup_pairs'])}쌍 · 모순 {len(mem_before['contradictions'])}건 · "
          f"{STALE_DAYS}일+낡음 {len(mem_before['stale'])}건 · "
          f"인덱스불일치(고아 {len(mem_before['orphans'])}/죽은링크 {len(mem_before['dead_links'])})")

    print("[2/4] 스냅샷(가역화) + 자율 정리(병합·갱신·인덱스)...")
    snap_path = snapshot_memory(dry_run)
    print(f"  스냅샷: {snap_path or '(dry-run, 생략)'}")
    maint = apply_memory_maintenance(mem_before, dry_run)
    delete_total = update_delete_queue(mem_before["stale"], dry_run)
    print(f"  병합 {maint['merged']}건 · 갱신 {maint['updated']}건 · 인덱스정리 {maint['index_fixed']}건 · "
          f"삭제대기 누적 {delete_total}건")

    changed = maint["merged"] or maint["updated"] or maint["index_fixed"]
    mem_after = scan_memory() if (changed and not dry_run) else mem_before

    # ── 파트 B: AI 트렌드 ──
    print("[3/4] 자기학습 루프 스냅샷...")
    loop_after = learning_loop_snapshot()
    last_log = load_last_log()
    loop_before = last_log.get("loop_after", loop_after) if last_log else loop_after
    trend_proposals = this_week_trend_proposals()
    print(f"  반영 {loop_before.get('applied',0)}→{loop_after.get('applied',0)} · "
          f"이번주 신규제안 {len(trend_proposals)}건")

    # ── 파트 C: C레벨 컨텍스트 ──
    print("[4/4] C레벨 큐 정리(정체/표류/완료아카이브)...")
    queue_before = load_queue()
    clevel_before = clevel_snapshot(queue_before)
    run_queue_archive_sweep(dry_run)
    queue_after = load_queue() if not dry_run else queue_before
    clevel_after = clevel_snapshot(queue_after)
    archived_this_run = max(0, len(queue_before) - len(queue_after)) if not dry_run else 0
    print(f"  활성 {sum(v['active'] for v in clevel_before.values())}척 · "
          f"완료아카이브 {archived_this_run}건 이동")

    card = build_card(mem_before, mem_after, maint, delete_total,
                       loop_before, loop_after, trend_proposals,
                       clevel_before, clevel_after, archived_this_run)

    print("\n" + "=" * 60)
    print(card)
    print("=" * 60)

    if dry_run:
        print("\n[dry-run] 로그 기록·텔레그램 발송 생략")
        return

    append_log({
        "date": today_str(), "ts": now_str(),
        "mem_before": {"file_count": mem_before["file_count"], "dup": len(mem_before["dup_pairs"]),
                        "contradictions": len(mem_before["contradictions"]), "stale": len(mem_before["stale"])},
        "mem_after": {"file_count": mem_after["file_count"], "dup": len(mem_after["dup_pairs"]),
                       "contradictions": len(mem_after["contradictions"]), "stale": len(mem_after["stale"])},
        "merged": maint["merged"], "updated": maint["updated"], "index_fixed": maint["index_fixed"],
        "delete_pending": delete_total,
        "loop_after": loop_after,
        "archived_this_run": archived_this_run,
        "clevel_after": clevel_after,
    })

    send_telegram(card)
    print(f"\n[완료] ({now_str()})")


# ═══════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="주간 AI 자기정리 — 메모리+AI트렌드+C레벨컨텍스트 Before/After 카드 (일 10:30)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="전부 읽기전용 — 스냅샷·변경·발송 0")
    parser.add_argument("--approve-delete", type=str, metavar="FILE", dest="approve_delete",
                         help="삭제 대기 메모리 파일 실제 삭제(직전 재스냅샷)")
    parser.add_argument("--list-delete-queue", action="store_true", dest="list_delete_queue",
                         help="삭제 대기 목록 조회")
    args = parser.parse_args()

    if args.list_delete_queue:
        cmd_list_delete_queue()
        return
    if args.approve_delete:
        cmd_approve_delete(args.approve_delete)
        return

    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
