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
  python ceo_morning_pipeline.py --once-per-day      # 오늘 이미 돌았으면 스킵 (세션시작 훅용)

하루 1회 가드(--once-per-day):
  오늘자 계획 파일 status/morning_plans/YYYY-MM-DD.json 이 이미 있으면 즉시 스킵(exit 0).
  같은 날 CLI 세션을 여러 번 띄워도 아침 파이프라인은 1회만 실가동된다.
  (dry-run 은 실제 파일을 만들지 않으므로 가드를 소모하지 않는다.)

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

# ── 분류 SSOT (2026-05-30 GM 지시: 3분류) ────────────────────────────────────
# 한 항목을 아래 3개 중 하나로 라벨한다. 이 함수가 아침·저녁 두 보고의 단일 기준(SSOT).
#   ① GM_DECISION  : 보안값(PIN·토큰·GitHub 키)·결재 — GM 직접 결재 영역. 자동·deep-interview 아님.
#   ② AUTONOMOUS   : 명확 — AI CEO가 담당 C-Level에 위임해 스스로 진행.
#   ③ DEEP_INTERVIEW: 모호(정보 부족·방향 미정) — deep-interview로 명확화 후 진행.
DISP_GM_DECISION = "GM_DECISION"
DISP_AUTONOMOUS = "AUTONOMOUS"
DISP_DEEP_INTERVIEW = "DEEP_INTERVIEW"

# ① 보안값·결재 신호 → GM 직접 결재 (최우선). 있으면 무조건 GM_DECISION.
SECURITY_SIGNALS = [
    ("🔒", "보안값(PIN·토큰·키)은 GM 직접 설정"),
    ("PIN", "PIN 값 설정·재배포는 GM 결재"),
    ("토큰", "토큰 발급은 GM 결재"),
    ("token", "토큰 발급은 GM 결재"),
    ("github 토큰", "GitHub 쓰기 키는 GM 결재"),
    ("github 키", "GitHub 키는 GM 결재"),
    ("github 쓰기", "GitHub 쓰기 권한은 GM 결재"),
    ("api 키", "API 키는 GM 결재"),
    ("api key", "API 키는 GM 결재"),
    ("비밀번호", "비밀번호는 GM 직접 전달"),
    ("결제", "💰 결제는 GM 직접 결재"),
    ("💰", "💰 결제는 GM 직접 결재"),
]

# ③ 모호 신호 → deep-interview (정보 부족·방향 미정). 보안값이 없을 때만 적용.
DEEP_INTERVIEW_SIGNALS = [
    ("방향 결정", "방향이 정해져야 진행 가능"),
    ("결정 후", "방향 결정 후 재개"),
    ("보류 결재", "보류 사유 — 재개 방향 확인 필요"),
    ("미정", "세부가 정해지지 않음"),
    ("불가 —", "현 구조로 불가 — 대안 방향 확인 필요"),
    ("불가-", "현 구조로 불가 — 대안 방향 확인 필요"),
    ("불명확", "요건이 불명확"),
    ("어떻게 할지", "방법이 정해지지 않음"),
    ("정해지면", "선결 조건 미정"),
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


def today_marker() -> Path:
    """오늘자 실가동 계획 파일 경로 = 하루 1회 가드 마커."""
    return PLAN_DIR / (datetime.now().strftime("%Y-%m-%d") + ".json")


def already_ran_today() -> bool:
    """오늘 실가동(비-dry-run) 계획 파일이 이미 있으면 True."""
    return today_marker().exists()


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


def classify_disposition(item: dict) -> tuple[str, str]:
    """
    분류 SSOT — 아침·저녁 두 보고가 공유하는 단일 기준 (2026-05-30 GM 3분류).

    반환: (disposition, reason)
      disposition ∈ {GM_DECISION, AUTONOMOUS, DEEP_INTERVIEW}

    우선순위:
      1) 보안값·결재 신호 → GM_DECISION (GM 직접 결재. 자동·deep-interview 아님)
      2) 모호 신호       → DEEP_INTERVIEW (방향·정보 미정 → 명확화 선행)
      3) 그 외           → AUTONOMOUS (명확 → CEO가 위임해 자율 진행)
    """
    hay = f"{item.get('title','')} {item.get('note','')}".lower()
    for sig, reason in SECURITY_SIGNALS:
        if sig.lower() in hay:
            return DISP_GM_DECISION, reason
    for sig, reason in DEEP_INTERVIEW_SIGNALS:
        if sig.lower() in hay:
            return DISP_DEEP_INTERVIEW, reason
    return DISP_AUTONOMOUS, ""


def summarize_title(title: str, limit: int = 30) -> str:
    """
    원본 task title을 사람이 읽는 짧은 요약으로 가공 (limit자 이내, 중간 '…' 절단 금지).

    규칙:
      - 첫 의미 단위(' + ', ' — ', ':', '(', '．' 등)에서 자연스럽게 끊는다.
      - 그래도 limit를 넘으면 어절(공백) 경계까지만 살리고 뒤는 버린다('…' 안 붙임).
      - 결과는 항상 limit 이하 + 단어 중간이 잘리지 않는다.
    """
    t = (title or "").strip()
    if not t:
        return "(제목 없음)"
    # 1) 의미 구분자에서 1차 컷 (앞 토막만 사용). 가장 먼저(앞쪽) 나오는 구분자 기준.
    cut = len(t)
    for sep in [" + ", " — ", " - ", " → ", "→", "(", "·", ":", "："]:
        idx = t.find(sep)
        if 0 < idx < cut:
            cut = idx
    if cut <= limit:
        t = t[:cut].strip()
    if len(t) <= limit:
        return t.rstrip(" →-·:[")
    # 2) 아직 길면 어절 경계까지만 (단어 중간 절단 방지, '…' 미사용)
    head = t[:limit]
    if " " in head:
        head = head.rsplit(" ", 1)[0]
    return head.strip().rstrip(" →-·:[")


def count_table(rows: list[tuple[str, int]]) -> list[str]:
    """
    텔레그램 고정폭에서 안 깨지는 카운트 표 (좌측 라벨 + 우측 숫자).
    한글 1자=2폭으로 계산해 라벨 칸 폭을 맞춘다.
    """
    def w(s: str) -> int:
        return sum(2 if ord(c) > 0x2500 else 1 for c in s)

    label_w = max((w(lbl) for lbl, _ in rows), default=4)
    num_w = max((len(str(n)) for _, n in rows), default=1)
    bar = "─"
    top = f"┌─{bar * label_w}─┬─{bar * num_w}─┐"
    bot = f"└─{bar * label_w}─┴─{bar * num_w}─┘"
    out = [top]
    for lbl, n in rows:
        pad = " " * (label_w - w(lbl))
        out.append(f"│ {lbl}{pad} │ {str(n).rjust(num_w)} │")
    out.append(bot)
    return out


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

    gm_decision, autonomous, deep_interview = [], [], []
    for it in items:
        disp, reason = classify_disposition(it)
        it["disposition"] = disp
        it["disposition_reason"] = reason
        if disp == DISP_GM_DECISION:
            gm_decision.append(it)
        elif disp == DISP_DEEP_INTERVIEW:
            deep_interview.append(it)
        else:
            autonomous.append(it)

    # 'clear'(자율 진행 가능 = 위임 대상) = autonomous 전용.
    # GM_DECISION·DEEP_INTERVIEW 는 자동 배정/실행 대상이 아님.
    return {
        "collected": len(items),
        "gm_decision": gm_decision,
        "autonomous": autonomous,
        "deep_interview": deep_interview,
        "clear": autonomous,        # stage2 배정 입력 (= 자율 진행)
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

# 동그라미 번호 (제목 잘림 없는 짧은 요약과 함께 사용)
CIRCLED = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]


def _circled(i: int) -> str:
    return CIRCLED[i - 1] if 1 <= i <= len(CIRCLED) else f"{i}."


def build_telegram_report(s1: dict, assigned: list[dict], orch: dict) -> str:
    """
    GM 보고 — 시안1(결정 중심 초간결) + 시안2(한눈 표) 조합 (2026-05-30 GM 지시).
    상단: 한눈 카운트 표 / 본문: GM 결정 필요분만 부각 / 하단: 자율 진행 1줄 + 안내.
    """
    gm_dec = s1["gm_decision"]
    auto = s1["autonomous"]
    deep = s1["deep_interview"]

    lines = []
    lines.append(f"🌅 아침 정리 — {today_kr()}")

    # ── 상단: 한눈 표 (시안2) ──
    lines += count_table([
        ("GM 결정", len(gm_dec)),
        ("자율 진행", len(auto)),
        ("명확화 대기", len(deep)),
    ])
    lines.append("")

    # ── 본문: GM 결정 필요분만 부각 (시안1) ──
    if gm_dec:
        lines.append("▶ GM 결정 필요 (이것만 봐주세요)")
        for i, a in enumerate(gm_dec, 1):
            lines.append(f"{_circled(i)} {summarize_title(a.get('title'))}")
            lines.append(f"   └ 왜: {a.get('disposition_reason','')}")
    else:
        lines.append("▶ GM 결정 필요: 없음 — 봐주실 것 없어요.")
    lines.append("")

    # ── 하단: 자율 진행 + 명확화 안내 ──
    if auto:
        names = "·".join(summarize_title(a.get("title"), 16) for a in auto[:3])
        more = f" 외 {len(auto) - 3}건" if len(auto) > 3 else ""
        lines.append(f"▶ 자율 진행 중: {len(auto)}건 ({names}{more})")
    else:
        lines.append("▶ 자율 진행 중: 없음")
    if deep:
        lines.append(f"▶ 명확화 대기: {len(deep)}건 — deep-interview로 명확화 후 진행")

    return "\n".join(lines)


def build_question_card(gm_decision: list[dict]) -> str:
    """GM 결정 필요(보안·결재) 항목 전용 카드 — 본보고와 별도 발송. 제목 잘림 없음."""
    if not gm_decision:
        return ""
    lines = ["🔒 GM 결정 카드 (아침)"]
    lines.append("아래는 GM 직접 결재 영역이라 자동으로 손대지 않았어요.")
    lines.append("")
    for i, a in enumerate(gm_decision, 1):
        lines.append(f"{_circled(i)} {summarize_title(a.get('title'))}")
        lines.append(f"   사유: {a.get('disposition_reason','')}")
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
            "gm_decision_count": len(s1["gm_decision"]),
            "autonomous_count": len(s1["autonomous"]),
            "deep_interview_count": len(s1["deep_interview"]),
            "gm_decision": [
                {"task_id": a.get("task_id"), "title": a.get("title"),
                 "reason": a.get("disposition_reason")}
                for a in s1["gm_decision"]
            ],
            "deep_interview": [
                {"task_id": a.get("task_id"), "title": a.get("title"),
                 "reason": a.get("disposition_reason")}
                for a in s1["deep_interview"]
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

def run_pipeline(dry_run: bool, as_json: bool, once_per_day: bool = False) -> int:
    # 하루 1회 가드: 오늘 이미 실가동 계획이 있으면 즉시 스킵 (세션 시작 훅 다중 호출 대비).
    # dry-run 은 실제 파일을 만들지 않으므로 마커 점검에서 제외(가드 소모 안 함).
    if once_per_day and not dry_run and already_ran_today():
        print(f"[SKIP] 오늘({datetime.now().strftime('%Y-%m-%d')}) 아침 파이프라인 이미 실행됨 "
              f"→ {today_marker()} (스킵)")
        return 0

    print(f"=== CEO 아침 파이프라인 시작 (dry_run={dry_run}, once_per_day={once_per_day}) ===")

    # ① 수집 + 분류 (3분류: GM 결정 / 자율 / 명확화 대기)
    s1 = stage1_collect_classify()
    print(f"[STAGE 1] 수집 {s1['collected']}건 → GM결정 {len(s1['gm_decision'])} "
          f"/ 자율 {len(s1['autonomous'])} / 명확화대기 {len(s1['deep_interview'])}")

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
    question_card = build_question_card(s1["gm_decision"])
    plan_path = save_plan(s1, assigned, orch, dry_run)
    sent = send_reports(report, question_card, dry_run)
    print(f"[STAGE 4] 보고 {'(dry-run 출력)' if dry_run else '발송'} — {'OK' if sent else 'FAIL'}")

    if as_json:
        print("\n========== PLAN JSON ==========")
        print(json.dumps({
            "collected": s1["collected"],
            "gm_decision": len(s1["gm_decision"]),
            "autonomous": len(s1["autonomous"]),
            "deep_interview": len(s1["deep_interview"]),
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
    ap.add_argument("--once-per-day", action="store_true",
                    help="오늘자 계획 파일이 이미 있으면 즉시 스킵 (세션 시작 훅용 가드)")
    args = ap.parse_args()
    return run_pipeline(dry_run=args.dry_run, as_json=args.json, once_per_day=args.once_per_day)


if __name__ == "__main__":
    sys.exit(main())
