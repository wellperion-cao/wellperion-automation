#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ceo_morning_pipeline.py - AI CEO 아침 자동 파이프라인 (디스패처 오케스트레이터)
v1.0 (2026-05-30)

GM 결정(2026-05-30, 가이드허브 g10 "CEO = 상시 대기 디스패처"):
  CEO 메인 세션 1개만 떠도, 다른 C-Level .bat 창을 켜지 않고 CEO가
  서브에이전트로 전 과정을 자동 수행한다. CEO는 직접 작업하지 않고
  위임·검증·기록·발신만 한다.

4단계 파이프라인:
  ① 수집+분류  : status/_queue.json + status/{clevel}.json + git log 를 긁어
                 미결 할일을 모으고, 각 항목을 '명확' / '모호(GM 답 필요)'로 분류
  ② 명확화+배정 : 명확한 항목을 R/R 매핑대로 담당 C-Level에 배정 (표)
  ③ 지시+검증   : 명확·배정 항목을 CEO가 서브에이전트로 병렬 실행하는 구조 생성
                 - 같은 파일/SSOT 동시 수정 충돌을 직렬화 (conflict serialization)
                 - 작성(write)과 검증(verify)을 분리 (ceo_verify_watcher가 검증)
                 ※ 이번 구현은 오케스트레이션 로직·충돌 규칙만 완성.
                   실제 LLM(claude) 호출은 dry-run에서 막고 계획만 출력.
  ④ 완료→보고   : 기존 텔레그램 모듈(telegram_notifier.TelegramNotifier)로 결과 발송.
                 "무엇을 어디에 기록했는지 / 앞으로 진행이 어떻게 되는지"를
                 GM이 쉽게 이해하게 일상어로. 모호 항목은 자동 처리 금지 —
                 텔레그램 '질문 카드'로 묶어 GM께 발송.

실행:
  python ceo_morning_pipeline.py --dry-run     # 4단계 끝까지 (텔레그램·파일 수정 막고 로그만)
  python ceo_morning_pipeline.py               # 실제 가동 (텔레그램 발송 + 계획 기록)
  python ceo_morning_pipeline.py --dry-run --json   # 계획을 JSON으로도 출력

보안: PIN/토큰 등 하드코딩 금지. .env(HardLink → telegram_bot/.env) / 환경변수만 참조.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows 한글 안전 출력
try:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 경로 ─────────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent          # wellperion-agents/scripts
PACKAGE_ROOT = BASE.parent                       # wellperion-agents
REPO = PACKAGE_ROOT.parent                       # welperion-automation (repo root)
STATUS_DIR = REPO / "status"
QUEUE_PATH = STATUS_DIR / "_queue.json"
PLAN_DIR = STATUS_DIR / "morning_plans"          # 산출물: 일자별 계획 JSON

# telegram_notifier import 경로
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

# ── R/R 매핑 (CLAUDE.md §1 + project_ai_clevel_to_practitioner_mapping) ───────
CLEVEL_DOMAIN = {
    "CFO": "재무",
    "CHRO": "인사",
    "CMO": "마케팅",
    "COO": "운영",
    "CPO": "회원·CS",
    "CTO": "시설·기술",
}
# AI C-Level → 실무진(최종 책임자) 사람 매핑
CLEVEL_OWNER = {
    "CEO": "김남욱 GM",
    "CMO": "김남욱 GM",
    "CTO": "김남욱 GM",
    "CFO": "나우열M",
    "CHRO": "나우열M",
    "COO": "최준용M",
    "CPO": "임정은M",
}
CLEVEL_ORDER = ["CFO", "CHRO", "CMO", "COO", "CPO", "CTO"]

# 모호성 키워드: 제목/노트에 이런 신호가 있으면 GM 답이 필요 → 자동 처리 금지
AMBIGUOUS_SIGNALS = [
    ("🔒", "보안값(PIN·토큰 등) GM 직접 설정 필요"),
    ("PIN", "PIN 값 설정·재배포는 GM 보안 결재"),
    ("토큰", "토큰 발급은 GM 보안 결재"),
    ("token", "토큰 발급은 GM 보안 결재"),
    ("결재 대기", "GM 결재 대기"),
    ("GM 결재", "GM 결재 필요"),
    ("GM 대기", "GM 응답 대기"),
    ("GM 승인", "GM 승인 필요"),
    ("결정 후", "방향 결정 후 재개"),
    ("보류 결재", "GM 보류 — 재개 결정 필요"),
]

# 명확하지 않은(미결) 큐 상태 — 처리 대상
OPEN_STATUSES = {"PENDING", "IN_PROGRESS", "ASSIGNED", "TODO", "BLOCKED", "ON_HOLD"}
# 종결 상태 — 수집에서 제외
DONE_STATUSES = {"DONE", "REJECTED", "CANCELLED", "ARCHIVED"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_kr() -> str:
    wk = ["월", "화", "수", "목", "금", "토", "일"][datetime.now().weekday()]
    return datetime.now().strftime("%Y-%m-%d") + f" ({wk})"


# ── STAGE 1: 수집 + 모호성 분류 ───────────────────────────────────────────────

def load_queue() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    try:
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"[WARN] _queue.json 파싱 실패: {exc}", file=sys.stderr)
        return []


def load_clevel_active() -> list[dict]:
    """status/{clevel}.json 의 active_tasks 중 미종결 항목 수집."""
    out = []
    for cl in CLEVEL_ORDER:
        p = STATUS_DIR / f"{cl.lower()}.json"
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for t in data.get("active_tasks", []):
            st = (t.get("status") or "").upper()
            if st in DONE_STATUSES:
                continue
            out.append({
                "task_id": t.get("task_id", ""),
                "clevel": cl,
                "title": t.get("title", ""),
                "status": st or "TODO",
                "note": t.get("note", ""),
                "depends_on": t.get("depends_on"),
                "source": f"status/{cl.lower()}.json",
            })
    return out


def git_recent_done(limit: int = 30) -> list[str]:
    """최근 git log 에서 [DONE][CL][task_id] 태그 task_id 목록 (이미 끝난 것 식별용)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO), "log", f"-{limit}", "--format=%s"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
    except Exception:
        return []
    done = []
    for line in proc.stdout.splitlines():
        m = re.search(r"\[DONE\]\[[A-Za-z]+\]\[([^\]]+)\]", line)
        if m:
            done.append(m.group(1).strip())
    return done


def classify_ambiguity(item: dict) -> tuple[bool, str]:
    """(is_ambiguous, reason). 제목+노트에서 모호성 신호 탐지."""
    hay = f"{item.get('title','')} {item.get('note','')}"
    for sig, reason in AMBIGUOUS_SIGNALS:
        if sig.lower() in hay.lower():
            return True, reason
    return False, ""


def stage1_collect_classify() -> dict:
    """전체 미결 할일 수집 + 명확/모호 분류. dict 반환."""
    git_done = set(git_recent_done())

    raw: list[dict] = []
    # 1) _queue.json
    for q in load_queue():
        st = (q.get("status") or "").upper()
        if st in DONE_STATUSES:
            continue
        raw.append({
            "task_id": q.get("task_id", ""),
            "clevel": (q.get("clevel") or "").upper(),
            "title": q.get("title", ""),
            "status": st or "PENDING",
            "priority": (q.get("priority") or "NORMAL").upper(),
            "note": q.get("note", ""),
            "depends_on": q.get("depends_on"),
            "brief": q.get("brief"),
            "source": "status/_queue.json",
        })
    # 2) status/{clevel}.json active_tasks
    for t in load_clevel_active():
        t.setdefault("priority", "NORMAL")
        raw.append(t)

    # dedup by task_id (queue 우선 — 먼저 들어온 것 유지)
    seen: set[str] = set()
    items: list[dict] = []
    for it in raw:
        tid = it.get("task_id", "")
        if tid and tid in seen:
            continue
        if tid:
            seen.add(tid)
        # git 에서 이미 DONE 태그된 task_id 는 제외 (status 미반영 잔류 방지)
        if tid in git_done:
            continue
        items.append(it)

    clear, ambiguous = [], []
    for it in items:
        amb, reason = classify_ambiguity(it)
        if amb:
            it["ambiguous_reason"] = reason
            ambiguous.append(it)
        else:
            clear.append(it)

    return {
        "collected": len(items),
        "clear": clear,
        "ambiguous": ambiguous,
        "git_done_excluded": sorted(git_done),
    }


# ── STAGE 2: 명확화 + 담당 배정 ───────────────────────────────────────────────

def infer_clevel(item: dict) -> str:
    """clevel 미지정 시 task_id prefix / 키워드로 추론."""
    cl = (item.get("clevel") or "").upper()
    if cl in CLEVEL_DOMAIN:
        return cl
    tid = (item.get("task_id") or "").upper()
    for c in CLEVEL_ORDER:
        if tid.startswith(c + "-") or tid.startswith(c):
            return c
    # 키워드 기반 폴백
    hay = f"{item.get('title','')} {item.get('note','')}".lower()
    kw = {
        "CMO": ["마케팅", "인스타", "블로그", "카페", "콘텐츠", "슬라이드", "광고", "ig"],
        "CTO": ["인프라", "스크립트", "자동화", "github", "apps script", "배포", "코드", "watcher"],
        "COO": ["운영", "시설", "공지", "체크리스트", "점검", "ssot", "리셉션"],
        "CFO": ["지출", "재무", "비용", "예산", "정산"],
        "CHRO": ["인사", "채용", "취업규칙", "근태", "교육"],
        "CPO": ["회원", "cs", "컴플레인", "예약", "상담"],
    }
    for c, words in kw.items():
        if any(w in hay for w in words):
            return c
    return "CTO"  # 최종 폴백: 기술 인프라


def stage2_assign(clear_items: list[dict]) -> list[dict]:
    """명확 항목에 담당 C-Level + 실무진(사람) + 도메인 배정."""
    assigned = []
    for it in clear_items:
        cl = infer_clevel(it)
        assigned.append({
            **it,
            "assigned_clevel": cl,
            "domain": CLEVEL_DOMAIN.get(cl, "?"),
            "owner": CLEVEL_OWNER.get(cl, "?"),
        })
    # 우선순위: HIGH 먼저, 그다음 clevel 순서
    pri_rank = {"HIGH": 0, "NORMAL": 1, "LOW": 2}
    assigned.sort(key=lambda x: (
        pri_rank.get(x.get("priority", "NORMAL"), 1),
        CLEVEL_ORDER.index(x["assigned_clevel"]) if x["assigned_clevel"] in CLEVEL_ORDER else 9,
    ))
    return assigned


# ── STAGE 3: 지시 + 검증 오케스트레이션 (충돌 직렬화) ─────────────────────────

# 같은 SSOT/파일군을 만지는 작업은 동시에 돌리면 충돌 → 같은 lock 키로 직렬화.
# 키워드 → lock 키. 한 항목이 여러 키에 걸리면 가장 먼저 매칭된 키 1개 사용.
CONFLICT_LOCKS = [
    ("업무현황 SSOT / 결재 현황 SSOT (가이드허브 + Apps Script)",
     ["s4", "ssot", "결재 현황", "업무현황", "업무 현황", "gcoo-todo", "apps script", "결재"]),
    ("가이드허브 메인 HTML (wellperion_guide(main).html)",
     ["가이드허브", "guide(main)", "guidehub", "g10", "g19"]),
    ("인스타/콘텐츠 발행 파이프라인 (review_queue + playwright)",
     ["인스타", "instagram", "ig", "슬라이드", "review_queue", "검수"]),
    ("네이버 블로그/카페 업로드 파이프라인",
     ["블로그", "카페", "naver", "smarteditor"]),
    ("학습 수집 인프라 (learning/ + learner)",
     ["learning", "학습 자료", "교육자료", "collector"]),
    ("status/_queue.json + status/*.json (큐 상태)",
     ["_queue", "status/json", "큐 정리"]),
]


def lock_key_for(item: dict) -> str:
    hay = f"{item.get('title','')} {item.get('note','')}".lower()
    for key, words in CONFLICT_LOCKS:
        if any(w in hay for w in words):
            return key
    # 매칭 없으면 task_id 단독 lock (충돌 없음 = 병렬 가능)
    return f"__solo__:{item.get('task_id','?')}"


def stage3_orchestrate(assigned: list[dict]) -> dict:
    """
    충돌 직렬화 + 병렬 그룹 + 검증 분리 계획 생성.

    규칙:
      - 같은 lock_key 항목들 → 같은 '직렬 체인'(serial chain). 체인 내부는 순차 실행.
      - 서로 다른 lock_key 체인끼리는 병렬(parallel) 실행 가능.
      - depends_on 이 있으면 그 task 가 같은/다른 체인이든 선행되도록 체인 정렬에 반영.
      - 각 작업은 [작성 단계] → [검증 단계]로 분리. 검증은 ceo_verify_watcher 가
        push 신호(커밋 [DONE] 태그 + status DONE)를 받아 별도 수행.
    """
    chains: dict[str, list[dict]] = {}
    for it in assigned:
        key = lock_key_for(it)
        chains.setdefault(key, []).append(it)

    # 각 체인 내부: depends_on 위상정렬(간단), 없으면 우선순위 유지
    def order_chain(items: list[dict]) -> list[dict]:
        by_id = {i.get("task_id"): i for i in items}
        ordered, placed = [], set()

        def place(i):
            tid = i.get("task_id")
            if tid in placed:
                return
            dep = i.get("depends_on")
            if dep and dep in by_id and dep not in placed:
                place(by_id[dep])
            placed.add(tid)
            ordered.append(i)

        for i in items:
            place(i)
        return ordered

    serial_chains = []
    for key, items in chains.items():
        serial_chains.append({
            "lock_key": key,
            "is_solo": key.startswith("__solo__:"),
            "tasks": [
                {
                    "task_id": t.get("task_id", ""),
                    "clevel": t.get("assigned_clevel"),
                    "owner": t.get("owner"),
                    "title": t.get("title", ""),
                    "depends_on": t.get("depends_on"),
                    # 작성/검증 분리: 작성은 서브에이전트, 검증은 워처
                    "write_step": {
                        "executor": "claude 서브에이전트(executor) 위임 — dry-run에서는 호출 안 함",
                        "instruction_ref": t.get("brief") or "status/_queue.json note",
                    },
                    "verify_step": {
                        "by": "ceo_verify_watcher.py (push 신호 수신 후 LAYER1+LAYER2)",
                        "signal": "커밋 [DONE][CL][task_id] + status/{cl}.json status=DONE (이중 신호)",
                    },
                }
                for t in order_chain(items)
            ],
        })

    # 병렬 가능 그룹 수 = 서로 다른 체인 수
    parallel_groups = len(serial_chains)
    serialized_pairs = sum(len(c["tasks"]) - 1 for c in serial_chains if len(c["tasks"]) > 1)

    return {
        "parallel_chains": parallel_groups,
        "serialized_conflicts": serialized_pairs,
        "chains": serial_chains,
    }


# ── STAGE 4: 완료 → 텔레그램 보고 ─────────────────────────────────────────────

def build_telegram_report(s1: dict, assigned: list[dict], orch: dict) -> str:
    """GM 일상어 보고. '무엇을 어디에 기록 / 앞으로 어떻게 진행' 포함."""
    lines = []
    lines.append(f"🌅 AI CEO 아침 자동 파이프라인 — {today_kr()}")
    lines.append("━" * 22)

    # ① 요약
    n_clear = len(assigned)
    n_amb = len(s1["ambiguous"])
    lines.append(f"오늘 미결 할일 {s1['collected']}건을 모았어요.")
    lines.append(f"· 바로 진행 가능: {n_clear}건 (담당별 배정 완료)")
    lines.append(f"· GM 답이 필요한 것: {n_amb}건 (자동 진행 안 함)")
    lines.append("")

    # ② 담당 배정 표 (일상어)
    if assigned:
        lines.append("〈누가 무엇을 — 바로 진행〉")
        by_cl: dict[str, list[dict]] = {}
        for a in assigned:
            by_cl.setdefault(a["assigned_clevel"], []).append(a)
        for cl in CLEVEL_ORDER:
            for a in by_cl.get(cl, []):
                title = (a.get("title") or "")[:42]
                lines.append(f"· [{cl}/{a['owner']}] {title}")
        lines.append("")

    # ③ 충돌 직렬화 안내 (일상어)
    if orch["serialized_conflicts"] > 0:
        lines.append(
            f"〈겹치는 작업 정리〉 같은 문서를 동시에 고치면 꼬이니까, "
            f"{orch['serialized_conflicts']}건은 순서대로(하나 끝나면 다음) 진행해요. "
            f"나머지는 {orch['parallel_chains']}갈래로 동시에 진행돼요."
        )
        lines.append("")

    # ④ 모호 질문 카드 (자동 처리 금지)
    if s1["ambiguous"]:
        lines.append("〈❓ GM 결정이 필요한 것 — 자동으로 손대지 않았어요〉")
        for i, a in enumerate(s1["ambiguous"], 1):
            title = (a.get("title") or "")[:40]
            lines.append(f"{i}. {title}")
            lines.append(f"   → 왜: {a.get('ambiguous_reason','')}")
        lines.append("")

    # ⑤ 기록 위치 + 앞으로 진행
    lines.append("〈어디에 기록했나 / 앞으로 어떻게〉")
    lines.append("· 오늘 계획은 status/morning_plans/ 에 날짜별로 저장돼요.")
    lines.append("· 각 작업은 담당이 끝내면 GitHub에 올리고(커밋), CEO 검증기가")
    lines.append("  자동으로 점검(통과/반려)해서 이 방으로 결과를 알려드려요.")
    lines.append("· 업무 현황은 가이드허브 'S4 업무&결재 현황' 에서 한눈에 보여요.")

    return "\n".join(lines)


def build_question_card(ambiguous: list[dict]) -> str:
    """모호 항목 전용 질문 카드 (별도 발송용)."""
    if not ambiguous:
        return ""
    lines = ["❓ GM 결정 요청 카드 (아침 파이프라인)"]
    lines.append("아래는 자동으로 진행하지 않고 GM 답을 기다리는 것들이에요.")
    lines.append("")
    for i, a in enumerate(ambiguous, 1):
        lines.append(f"{i}. {(a.get('title') or '')[:48]}")
        lines.append(f"   사유: {a.get('ambiguous_reason','')}")
        if a.get("note"):
            lines.append(f"   메모: {(a.get('note') or '')[:80]}")
    return "\n".join(lines)


# ── 산출물 기록 ───────────────────────────────────────────────────────────────

def save_plan(s1: dict, assigned: list[dict], orch: dict, dry_run: bool) -> Path:
    plan = {
        "generated_at": now_iso(),
        "date": today_kr(),
        "stage1_collect_classify": {
            "collected": s1["collected"],
            "clear_count": len(s1["clear"]),
            "ambiguous_count": len(s1["ambiguous"]),
            "ambiguous": [
                {"task_id": a.get("task_id"), "title": a.get("title"),
                 "reason": a.get("ambiguous_reason")}
                for a in s1["ambiguous"]
            ],
            "git_done_excluded": s1["git_done_excluded"],
        },
        "stage2_assign": [
            {"task_id": a.get("task_id"), "clevel": a["assigned_clevel"],
             "owner": a["owner"], "domain": a["domain"],
             "priority": a.get("priority"), "title": a.get("title")}
            for a in assigned
        ],
        "stage3_orchestrate": orch,
    }
    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    fname = datetime.now().strftime("%Y-%m-%d") + ("_dryrun" if dry_run else "") + ".json"
    out = PLAN_DIR / fname
    text = json.dumps(plan, ensure_ascii=False, indent=2)
    if dry_run:
        print(f"[DRY-RUN] 계획 저장 예정 → {out} ({len(text)} bytes, 기록 안 함)")
    else:
        out.write_text(text, encoding="utf-8")
        print(f"[OK] 계획 저장 → {out}")
    return out


def send_reports(report: str, question_card: str, dry_run: bool) -> bool:
    if dry_run:
        print("\n========== [DRY-RUN] 텔레그램 본 보고 (발송 안 함) ==========")
        print(report)
        if question_card:
            print("\n---------- [DRY-RUN] 질문 카드 (발송 안 함) ----------")
            print(question_card)
        print("========== [DRY-RUN] 끝 ==========\n")
        return True
    try:
        from telegram_notifier import TelegramNotifier
        tg = TelegramNotifier()
        r1 = tg.send(report)
        ok1 = bool(r1.get("ok")) if isinstance(r1, dict) else False
        ok2 = True
        if question_card:
            r2 = tg.send(question_card)
            ok2 = bool(r2.get("ok")) if isinstance(r2, dict) else False
        print(f"[OK] 텔레그램 발송 — 본보고={ok1} 질문카드={ok2}")
        return ok1 and ok2
    except Exception as exc:
        print(f"[FAIL] 텔레그램 발송 실패: {exc}", file=sys.stderr)
        return False


# ── 메인 ─────────────────────────────────────────────────────────────────────

def run_pipeline(dry_run: bool, as_json: bool) -> int:
    print(f"=== CEO 아침 파이프라인 시작 (dry_run={dry_run}) ===")

    # ① 수집 + 분류
    s1 = stage1_collect_classify()
    print(f"[STAGE 1] 수집 {s1['collected']}건 → 명확 {len(s1['clear'])} / 모호 {len(s1['ambiguous'])}")

    # ② 명확화 + 배정
    assigned = stage2_assign(s1["clear"])
    print(f"[STAGE 2] 배정 완료 {len(assigned)}건")
    for a in assigned:
        print(f"    - [{a['assigned_clevel']}/{a['owner']}] {a.get('task_id','?')} :: {(a.get('title') or '')[:48]}")

    # ③ 오케스트레이션 (충돌 직렬화 + 검증 분리)
    orch = stage3_orchestrate(assigned)
    print(f"[STAGE 3] 병렬 체인 {orch['parallel_chains']}개 / 직렬화된 충돌 {orch['serialized_conflicts']}건")
    for c in orch["chains"]:
        tag = "SOLO" if c["is_solo"] else "LOCK"
        print(f"    [{tag}] {c['lock_key'][:60]} — {len(c['tasks'])} task(s)")

    # ④ 보고 빌드 + 발송
    report = build_telegram_report(s1, assigned, orch)
    question_card = build_question_card(s1["ambiguous"])
    plan_path = save_plan(s1, assigned, orch, dry_run)
    sent = send_reports(report, question_card, dry_run)
    print(f"[STAGE 4] 보고 {'(dry-run 출력)' if dry_run else '발송'} — {'OK' if sent else 'FAIL'}")

    if as_json:
        print("\n========== PLAN JSON ==========")
        print(json.dumps({
            "collected": s1["collected"],
            "clear": len(assigned),
            "ambiguous": len(s1["ambiguous"]),
            "plan_path": str(plan_path),
            "parallel_chains": orch["parallel_chains"],
            "serialized_conflicts": orch["serialized_conflicts"],
        }, ensure_ascii=False, indent=2))

    ok = sent
    print(f"=== 파이프라인 종료 — {'성공' if ok else '실패'} ===")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="AI CEO 아침 자동 파이프라인 (디스패처)")
    ap.add_argument("--dry-run", action="store_true",
                    help="4단계 전부 돌리되 텔레그램 발송·파일 기록을 막고 로그만 출력")
    ap.add_argument("--json", action="store_true", help="계획 요약을 JSON으로도 출력")
    args = ap.parse_args()
    return run_pipeline(dry_run=args.dry_run, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
