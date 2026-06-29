#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ceo_morning_pipeline.py - AI CEO 아침 자동 파이프라인 (디스패처 오케스트레이터)
v1.0 (2026-05-30)

GM 결정(2026-05-30, 웰페리온 ERP S2 "CEO = 상시 대기 디스패처"):
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
import urllib.request
from datetime import datetime, timezone, timedelta
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

# 공유 모듈 (ship_classify) 경로
_SCRIPTS_ROOT = str(REPO / "scripts")
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

# ── C-Level 닉네임 (spec ③ — 모든 항목 끝에 [닉네임] 부착) ─────────────────────
CLEVEL_NICK = {
    "CEO": "웰리",
    "CFO": "시뽀",
    "CHRO": "시로",
    "CMO": "시모",
    "COO": "시우",
    "CPO": "시포",
    "CTO": "시토",
    "GM": "GM",
    "GM1": "GM",
}

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


# ── G1 SSOT API (웰페리온 ERP gm1FetchSsot 동일 로직) ─────────────────────────
# URL은 웰페리온 ERP SSOT_API_URL 상수와 동일. stdout/텔레그램 노출 금지.
_G1_API = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7"
    "/exec?action=todo_list"
)

# 담당자 필드에서 G1 합류 대상 판정용 패턴 (웰페리온 ERP gm1FetchSsot 100% 동일)
_OWNER_GM_RE = re.compile(r"김남욱\s*GM")
_OWNER_CLEVEL_RE = re.compile(r"AI\s+(CEO|CMO|CTO|COO|CFO|CPO|CHRO)")
_OWNER_NICK_RE = re.compile(r"웰리|시모|시토|시우|시뽀|시포|시로")


def _ssot_date_local(v: object) -> str:
    """Apps Script ISO datetime → KST YYYY-MM-DD 변환 (웰페리온 ERP ssotDateLocal 동일)."""
    if not v:
        return ""
    s = str(v)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        kst = dt.astimezone(timezone(timedelta(hours=9)))
        return kst.strftime("%Y-%m-%d")
    except Exception:
        return s[:10]


def fetch_g1_ssot() -> dict | None:
    """
    웰페리온 ERP gm1FetchSsot()와 동일한 필터로 G1 SSOT 데이터를 수집한다.

    반환: {
        "gm_decision":   [{"title", "task_id", "owner", "disposition_reason"}],  # 결재 대기
        "today_tasks":   [{"title", "task_id", "owner", "status", "start_date"}], # 오늘 할 일
        "done_today":    [{"title", "task_id", "owner"}],  # 오늘 완료 (수정일=오늘)
        "done_yesterday":[{"title", "task_id", "owner"}],  # 어제 완료 (수정일=어제)
    }
    네트워크/파싱 실패 시 None 반환 → 호출부에서 fallback.
    """
    try:
        req = urllib.request.Request(
            _G1_API,
            headers={"User-Agent": "Mozilla/5.0 (CEO-morning-pipeline)"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        if not data.get("ok") or not isinstance(data.get("data"), list):
            print("[WARN] G1 SSOT API 응답 형식 이상 — fallback", file=sys.stderr)
            return None
    except Exception as exc:
        print(f"[WARN] G1 SSOT API 호출 실패: {exc} — fallback", file=sys.stderr)
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    gm_decision: list[dict] = []
    today_tasks: list[dict] = []
    done_today: list[dict] = []
    done_yesterday: list[dict] = []

    for row in data["data"]:
        owner = str(row.get("담당자") or "")
        title = str(row.get("업무명") or "").strip()
        if not title:
            continue

        apr = str(row.get("결재상태") or "")
        gm_sign = row.get("GM싸인")
        sd = _ssot_date_local(row.get("시작일"))
        mod = _ssot_date_local(row.get("수정일"))
        st = str(row.get("상태") or "")
        task_id = str(row.get("id") or "")

        # ① 결재 대기(GM 차례만): GM싸인 없음 AND 반려/결재완료 아님 AND
        #    (결재요청이 GM 지정 OR 결재상태='부서장 완료'(부서장 끝→GM 차례))
        #    ⚠️ 결재요청이 부서장(실장/소장/파트너)인 대기건은 GM 결재함에서 제외 —
        #    안 그러면 락커 등 부서장 결재건이 GM 결재함으로 샌다 (2026-06-07 시토 수정).
        req_str = str(row.get("결재요청") or "")
        req_is_gm = bool(re.search(r"GM", req_str))  # "GM"/"김남욱GM" 등
        needs_gm = (
            (not gm_sign)
            and apr
            and ("반려" not in apr)
            and apr != "결재완료"
            and (req_is_gm or "부서장 완료" in apr)
        )
        if needs_gm:
            # 제목 앞에 이미 붙은 [결재] 중복 제거(🔴 GM 결정 섹션이 맥락 전달).
            title_clean = re.sub(r"^\s*\[결재\]\s*", "", title)
            # "왜" 문구를 실제 결재 단계로 채움(4건 동일 문구 방지). 카테고리 앞 [N] 번호 제거.
            cat = re.sub(r"^\s*\[\d+\]\s*", "", str(row.get("카테고리") or "").strip())
            if "부서장" in apr:
                reason = "부서장 검토 끝 → GM 최종 결재 차례"
            else:
                reason = "결재 첫 단계 → GM 승인 필요"
            if cat and "결재" not in cat:   # 카테고리가 '결재'면 '결재·결재' 중복 방지
                reason = f"{cat} · {reason}"
            gm_decision.append({
                "title": title_clean,
                "task_id": task_id,
                "owner": owner,
                "disposition": "GM_DECISION",
                "disposition_reason": reason,
                "source": "g1_ssot",
            })
            continue

        # ② G1 합류 조건: 담당자에 김남욱GM / AI C레벨 / 닉네임 포함
        is_target = (
            bool(_OWNER_GM_RE.search(owner))
            or bool(_OWNER_CLEVEL_RE.search(owner))
            or bool(_OWNER_NICK_RE.search(owner))
        )
        if not is_target:
            continue

        base_item = {
            "title": title,
            "task_id": task_id,
            "owner": owner,
            "status": st,
            "start_date": sd,
            "source": "g1_ssot",
        }

        if st == "완료":
            # 완료일 기준: 결재완료시각 > 수정일 순서로 우선 적용
            done_date = _ssot_date_local(row.get("결재완료시각")) or mod
            if done_date == today:
                done_today.append(base_item)
            elif done_date == yesterday:
                done_yesterday.append(base_item)
            # 그 외 완료는 보고 대상 아님 (오염 방지)
            continue

        if st == "보류":
            continue

        # ③ 오늘 할 일: 시작일=오늘 OR 상태=진행중 (완료·보류 제외)
        if sd == today or st == "진행중":
            # 담당자에서 C레벨 닉네임 추출 (CLEVEL_NICK 매핑용 clevel 키 추가)
            cl = _infer_clevel_from_owner(owner, title)
            today_tasks.append({**base_item, "clevel": cl})

    return {
        "gm_decision": gm_decision,
        "today_tasks": today_tasks,
        "done_today": done_today,
        "done_yesterday": done_yesterday,
    }


def _infer_clevel_from_owner(owner: str, title: str = "") -> str:
    """담당자 문자열에서 AI C레벨 코드 추출 (없으면 키워드 폴백)."""
    m = re.search(r"AI\s+(CEO|CMO|CTO|COO|CFO|CPO|CHRO)", owner)
    if m:
        return m.group(1)
    nick_map = {"웰리": "CEO", "시모": "CMO", "시토": "CTO",
                "시우": "COO", "시뽀": "CFO", "시포": "CPO", "시로": "CHRO"}
    for nick, cl in nick_map.items():
        if nick in owner:
            return cl
    if "김남욱" in owner or "GM" in owner:
        return "GM1"
    # 키워드 폴백 (제목 기반)
    hay = title.lower()
    kw = {
        "CMO": ["마케팅", "인스타", "블로그", "카페", "콘텐츠", "슬라이드", "광고", "ig", "시모"],
        "CTO": ["인프라", "스크립트", "자동화", "github", "apps script", "배포", "코드", "watcher", "시토"],
        "COO": ["운영", "시설", "공지", "체크리스트", "점검", "ssot", "리셉션", "시우"],
        "CFO": ["지출", "재무", "비용", "예산", "정산", "시뽀"],
        "CHRO": ["인사", "채용", "취업규칙", "근태", "교육", "시로"],
        "CPO": ["회원", "cs", "컴플레인", "예약", "상담", "시포"],
    }
    for c, words in kw.items():
        if any(w in hay for w in words):
            return c
    return "CEO"


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


def summarize_title(title: str, limit: int = 45) -> str:
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


# GM 대면 보고는 일상어 의무(전문용어·약어 금지). 자주 새는 용어를 쉬운 말로 치환.
_JARGON = [
    ("GAS Notion 쓰기", "구글서버에 노션 자료 저장"),
    ("Notion", "노션"),
    ("GAS", "구글서버"),
    ("SSOT", "기준자료"),
    ("DOM", "화면요소"),
    ("API", "연동"),
    ("watcher", "감시기"),
    ("dry-run", "예행연습"),
    ("퍼널", "유입경로"),
    ("핫픽스", "긴급수정"),
]


def plainify(s: str) -> str:
    """렌더 직전 제목 정리 — 앞머리 [결재] 태그 제거 + 전문용어·약어를 쉬운 말로 치환(GM 일상어 의무)."""
    out = (s or "").strip()
    out = re.sub(r"^\s*\[결재\]\s*", "", out)   # 식별자(시모-08 등)는 보존, [결재]만 제거
    for k, v in _JARGON:
        out = out.replace(k, v)
    return out


def recent_done(days: int = 3) -> list[dict]:
    """
    큐 + 보관소에서 최근 days 일 내 완료(DONE) 항목 — '어제 마무리'가 0건일 때 보강.
    (완료가 새벽/오늘로 기록돼 '어제'에 안 잡히면 빈칸처럼 보이는 문제 방지.)
    """
    today = datetime.now().date()
    out: list[dict] = []
    seen: set = set()
    for path in (QUEUE_PATH, QUEUE_PATH.with_name("_archive.json")):
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict) or str(it.get("status", "")).upper() != "DONE":
                continue
            ds = it.get("processed_at") or it.get("completed_at") or it.get("updated_at")
            if not (isinstance(ds, str) and len(ds) >= 10):
                continue
            try:
                d = datetime.strptime(ds[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if 0 <= (today - d).days <= days:
                k = it.get("task_id") or it.get("title")
                if k and k not in seen:
                    seen.add(k)
                    out.append(it)
    return out


def urgent_deadlines(within_days: int = 3) -> list[dict]:
    """
    status/_queue.json 의 열린 항목 중 deadline 이 오늘~within_days 일 이내인 임박 마감 추출.
    (시트 기반 G1 SSOT 에는 마감일이 없어, 마감 가시화는 큐의 deadline 필드에서 보강.)
    """
    try:
        items = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    today = datetime.now().date()
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        if str(it.get("status", "")).upper() in ("DONE", "REJECTED"):
            continue
        dl = it.get("deadline")
        if not (isinstance(dl, str) and len(dl) >= 10):
            continue
        try:
            d = datetime.strptime(dl[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if 0 <= (d - today).days <= within_days:
            out.append({
                "title": it.get("title", ""),
                "deadline": dl[:10],
                "owner": it.get("owner") or it.get("clevel", ""),
            })
    out.sort(key=lambda x: x["deadline"])
    return out


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


# ── 항해 세계관 — 배 분류 (공유 모듈 위임, 2026-06-07) ──────────────────────────
# SSOT: scripts/ship_classify.py — 중복 구현 금지.
from ship_classify import (  # noqa: E402
    SHIP_BY_WEIGHT, SHIP_WEIGHT_RANK,
    NORTHSTAR_KEYWORDS, SHIP_UPGRADE_KEYWORDS, SHIP_DOWNGRADE_KEYWORDS,
    classify_ship, has_clevel_id, render_ship_line,
)


def stage1_collect_classify() -> dict:
    """
    전체 미결 할일 수집 + 명확/모호 분류. dict 반환.

    데이터 소스 우선순위 (2026-06-02 G1 SSOT 재배선):
      1) G1 SSOT API (웰페리온 ERP gm1FetchSsot와 동일 엔드포인트·필터)
      2) fallback: status/_queue.json + status/{clevel}.json (네트워크 실패 시)
    """
    git_done = set(git_recent_done())

    g1 = fetch_g1_ssot()
    if g1 is not None:
        # ── G1 SSOT 경로 ────────────────────────────────────────────────────
        print("[STAGE 1] 데이터 소스: G1 SSOT API")
        gm_decision = g1["gm_decision"]
        # today_tasks는 전부 AUTONOMOUS (결재 대기는 이미 gm_decision에 분리됨)
        autonomous: list[dict] = []
        deep_interview: list[dict] = []
        for it in g1["today_tasks"]:
            # 보안 신호가 제목에 포함된 경우 GM_DECISION으로 상향
            disp, reason = classify_disposition({"title": it.get("title", ""), "note": ""})
            it["disposition"] = disp
            it["disposition_reason"] = reason
            it.setdefault("priority", "NORMAL")
            if disp == DISP_GM_DECISION:
                gm_decision.append(it)
            elif disp == DISP_DEEP_INTERVIEW:
                deep_interview.append(it)
            else:
                autonomous.append(it)

        items_all = gm_decision + autonomous + deep_interview
        return {
            "collected": len(items_all),
            "gm_decision": gm_decision,
            "autonomous": autonomous,
            "deep_interview": deep_interview,
            "clear": autonomous,
            "git_done_excluded": sorted(git_done),
            # G1 완료 항목 — build_telegram_report 에서 참조
            "_g1_done_today": g1["done_today"],
            "_g1_done_yesterday": g1["done_yesterday"],
            "_source": "g1_ssot",
        }

    # ── fallback: 기존 _queue.json + status/{clevel}.json 경로 ────────────
    print("[STAGE 1] 데이터 소스: fallback (_queue.json)", file=sys.stderr)
    raw: list[dict] = []
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
    for t in load_clevel_active():
        t.setdefault("priority", "NORMAL")
        raw.append(t)

    seen: set[str] = set()
    items: list[dict] = []
    for it in raw:
        tid = it.get("task_id", "")
        if tid and tid in seen:
            continue
        if tid:
            seen.add(tid)
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

    return {
        "collected": len(items),
        "gm_decision": gm_decision,
        "autonomous": autonomous,
        "deep_interview": deep_interview,
        "clear": autonomous,
        "git_done_excluded": sorted(git_done),
        "_g1_done_today": [],
        "_g1_done_yesterday": [],
        "_source": "fallback",
    }


# ── STAGE 2: 명확화 + 담당 배정 ───────────────────────────────────────────────

def infer_clevel(item: dict) -> str:
    """clevel 미지정 시 task_id prefix / 키워드로 추론."""
    cl = (item.get("clevel") or "").upper()
    # CEO / GM 계열 먼저 처리 (결함 A: CLEVEL_DOMAIN 에 없어서 폴백 오작동 방지)
    if cl in ("CEO",):
        return "CEO"
    if cl in ("GM1", "GM"):
        return "GM1"
    if cl in CLEVEL_DOMAIN:
        return cl
    tid = (item.get("task_id") or "").upper()
    # CEO- 또는 GM- prefix 직접 확인
    if tid.startswith("CEO-") or tid.startswith("CEO"):
        return "CEO"
    if tid.startswith("GM1-") or tid.startswith("GM-"):
        return "GM1"
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
    ("업무현황 SSOT / 결재 현황 SSOT (웰페리온 ERP + Apps Script)",
     ["s4", "s3", "ssot", "결재 현황", "업무현황", "업무 현황", "gcoo-todo", "apps script", "결재"]),
    ("웰페리온 ERP 메인 HTML (wellperion_guide(main).html)",
     ["웰페리온 ERP", "guide(main)", "guidehub", "g10", "g19", "s2", "t2"]),
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

# 어제 완료 → 오늘 이어서 할 일 후속 신호 키워드 (spec ⑤)
FOLLOWUP_SIGNALS = ["내일", "오늘 .*예정", "실측 예정", "재요청", "후속", "다음 단계", "예정", "재개"]
_FOLLOWUP_RE = re.compile("|".join(FOLLOWUP_SIGNALS))


def _circled(i: int) -> str:
    return CIRCLED[i - 1] if 1 <= i <= len(CIRCLED) else f"{i}."


def yesterday_done() -> tuple[list[str], list[dict]]:
    """
    어제(로컬 날짜-1) 완료 항목 수집 (spec ①).
    반환: (git_commits, queue_items)
      git_commits: 어제자 git 커밋 제목 목록 (auto(changelog) 제외) — 건수 집계용 아님, 참고용
      queue_items: _queue.json 에서 processed_at=어제인 DONE 항목 — 건수·대표·후속 추출 기준
    결함 C: 어제 마무리 건수·대표는 queue_items 만 사용 (git 커밋 다중 = 무의미).
    결함 B: extract_followups 는 queue_items 만 받는다.
    """
    from datetime import timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    git_commits: list[str] = []
    queue_items: list[dict] = []

    # git 커밋 (어제자) — 참고용으로만 수집
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO), "log",
             f"--since={yesterday} 00:00:00", f"--until={yesterday} 23:59:59",
             "--format=%s"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("auto(changelog)"):
                continue
            git_commits.append(line)
    except Exception:
        pass

    # _queue.json processed_at 어제 DONE 항목 — 건수·후속 기준
    if QUEUE_PATH.exists():
        try:
            data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
            for q in data if isinstance(data, list) else []:
                st = (q.get("status") or "").upper()
                proc_at = str(q.get("processed_at") or "")
                if st == "DONE" and proc_at.startswith(yesterday):
                    queue_items.append({
                        "title": q.get("title", ""),
                        "clevel": (q.get("clevel") or "").upper(),
                        "task_id": q.get("task_id", ""),
                        "note": q.get("note", ""),
                    })
        except Exception:
            pass

    return git_commits, queue_items


# conventional-commit prefix 제거 정규식 (결함 B 이중 안전장치)
_CC_PREFIX_RE = re.compile(r"^(?:feat|fix|chore|refactor|style|test|docs|perf|ci|build|revert)"
                            r"(?:\([^)]*\))?!?:\s*", re.IGNORECASE)


def extract_followups(queue_items: list[dict]) -> list[dict]:
    """
    어제 큐 완료 항목의 note 에서 후속 신호를 추출 (spec ⑤).
    결함 B: git 커밋 메시지 완전 제외 — queue note 만 검색.
    매칭된 문장(80자 이내)을 인용 — task 자동 생성 금지, 리마인드만.
    conventional-commit prefix(feat(...):, chore(...): 등)는 제거 후 표시.
    반환: [{"quote": str, "clevel": str, "task_id": str}]
    """
    results = []
    for item in queue_items:
        note = (item.get("note") or "").strip()
        if not note:
            continue
        cl_raw = (item.get("clevel") or "").upper()
        tid = (item.get("task_id") or "")
        # clevel 직접 값 우선, 없으면 task_id prefix 추론
        cl = cl_raw
        if not cl:
            for prefix in ["CEO", "CFO", "CHRO", "CMO", "COO", "CPO", "CTO"]:
                if tid.upper().startswith(prefix):
                    cl = prefix
                    break

        # note 를 문장 단위로 분리해 후속 신호 검색
        sentences = re.split(r"[.\n。]", note)
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if _FOLLOWUP_RE.search(sent):
                # conventional-commit prefix 제거 (이중 안전장치)
                quote = _CC_PREFIX_RE.sub("", sent).strip()
                quote = quote[:80].strip()
                results.append({
                    "quote": quote,
                    "clevel": cl,
                    "task_id": tid,
                })
                break  # 항목당 첫 매칭 1건만

    return results


def _next_waypoint(item: dict) -> str:
    """
    어제 완료한 배가 남긴 '다음 항로점'(🔗)을 도출.
      - note 의 후속 신호 문장(_FOLLOWUP_RE) 우선 — 어제가 남긴 '다음'.
      - 없으면 '입항(종결)' (= 표류 아님, 정상 종결).
    depends_on 역참조는 G1 SSOT 완료 항목엔 note 기반이 더 신뢰도 높아 note 우선 사용.
    """
    note = str(item.get("note") or "").strip()
    if note:
        for sent in re.split(r"[.\n。]", note):
            sent = sent.strip()
            if sent and _FOLLOWUP_RE.search(sent):
                quote = _CC_PREFIX_RE.sub("", sent).strip()[:60].strip()
                if quote:
                    return quote
    return "입항(종결)"


def build_telegram_report(s1: dict, assigned: list[dict], orch: dict) -> str:
    """
    GM 아침 보고 — '오늘의 항로' 레이아웃 (2026-06-05 GM 재설계).
    항해 세계관(아이콘 표준 A안): 🌟북극성=목적지 · 🚢배=할일 · ⚓닻=대기/정박 · 🏁완료 · 🔗항로점=완료하며 남긴 다음 · 🌀표류=완료인데 다음없음.
    무게(priority)=배종류(🛳️크루즈/⛴️여객선/⛵돛단배) · 🔴마감임박 · 🌟북극성직결.
    ※ 데이터 수집·집계 변수(today_tasks/assigned/done_*/gm_decision/urgent)는 그대로 재사용.

    G1 SSOT 경로: s1["_g1_done_yesterday"] 를 '지나온 항로'로 사용.
    fallback 경로: yesterday_done() 큐 기반 유지.
    """
    gm_dec = s1["gm_decision"]
    auto = s1["autonomous"]
    deep = s1["deep_interview"]

    # 어제 마무리 — G1 SSOT(시트) 완료 + 큐 완료를 합산(둘 중 한쪽만 잡혀 '완료 없음'으로
    # 잘못 보이던 문제 해결). task_id/제목으로 중복 제거.
    if s1.get("_source") == "g1_ssot":
        yday_items = list(s1.get("_g1_done_yesterday", []))
        _yg, yday_queue = yesterday_done()
        seen = {(d.get("task_id") or d.get("title")) for d in yday_items}
        for q in yday_queue:
            k = q.get("task_id") or q.get("title")
            if k and k not in seen:
                yday_items.append(q)
                seen.add(k)
        followups = extract_followups([
            {"title": d.get("title", ""), "note": d.get("note", ""), "clevel": d.get("clevel", ""),
             "task_id": d.get("task_id", "")}
            for d in yday_items
        ])
    else:
        _yday_git, yday_queue = yesterday_done()
        yday_items = yday_queue
        followups = extract_followups(yday_queue)

    # ── 항해 분류 준비 — 임박 마감 제목 셋(🔴 판정용) ──
    urg = urgent_deadlines()
    urgent_titles = {u.get("title", "") for u in urg if u.get("title")}

    # 오늘의 항로 = 배정된 today 항목을 classify_ship 으로 분류
    today_ships: list[dict] = []
    for a in assigned:
        ship = classify_ship(a, urgent_titles)
        today_ships.append({**a, "_ship": ship})

    # 🌟 북극성 침로 = today 중 northstar 인 것
    northstar_today = [s for s in today_ships if s["_ship"]["northstar"]]

    # 🌀 표류 = 어제/오늘 완료 중 다음 항로점이 '입항(종결)' 도 후속신호도 아닌 것
    #   (note 에 후속 신호가 없으면 다음 항로점이 비어 끊김 — '입항(종결)'은 정상 종결이라 표류 아님)
    drift_pool = list(yday_items) + list(s1.get("_g1_done_today", []))
    drift_seen: set = set()
    drift: list[dict] = []
    for d in drift_pool:
        k = d.get("task_id") or d.get("title")
        if k in drift_seen:
            continue
        drift_seen.add(k)
        if _next_waypoint(d) == "입항(종결)" and not str(d.get("note") or "").strip():
            drift.append(d)

    lines = []
    lines.append(f"🧭 오늘의 항로 — {today_kr()}")
    lines.append("   북극성을 향해, 어제 항로에서 이어서")
    lines.append("")

    # ── 상단: 한눈 표 (선장 결정 · 오늘 항로 · 표류) ──
    lines += count_table([
        ("선장 결정", len(gm_dec)),
        ("오늘 항로", len(today_ships)),
        ("표류", len(drift)),
    ])
    lines.append("")

    # 항로 정합경고 — 큐↔시트 불일치(유령·중복·상태·형식) 있으면 08:00 보고 상단에 1줄(다같이 봄). fail-open.
    try:
        import sys as _sys
        from pathlib import Path as _P
        _sc = _P(__file__).resolve().parent.parent.parent / "scripts"
        if str(_sc) not in _sys.path:
            _sys.path.insert(0, str(_sc))
        from queue_integrity_check import board_banner as _bb
        _bn = _bb()
        if _bn:
            lines.append(_bn)
            lines.append("")
    except Exception:
        pass

    # ── 🔴 급한 입항 (마감 임박 — 큐 deadline 기반, 항상 표 바로 아래 고정) ──
    if urg:
        lines.append("🔴 급한 입항  (마감 임박)")
        for u in urg:
            mmdd = u["deadline"][5:].replace("-", "/")
            who = f" [{u['owner']}]" if u.get("owner") else ""
            lines.append(f" · {plainify(summarize_title(u['title']))} ({mmdd} 마감){who}")
        lines.append("")

    # ── 🔗 '지나온 항로(어제 완료)'는 07시 결산이 전담 — 08시는 '오늘 항로'만 (역할분담·중복제거, GM 2026-06-29) ──

    # ── 🧭 오늘의 항로 (배 종류로 묶음: 크루즈→여객선→돛단배) ──
    lines.append("🧭 오늘의 항로  (무거운 배부터 · 🔴급함 🌟북극성)")
    if today_ships:
        # 배 무게(tier rank) 큰 순, 같은 무게 내 급함🔴 먼저
        tier_rank = {"크루즈": 0, "여객선": 1, "돛단배": 2}
        ordered = sorted(
            today_ships,
            key=lambda s: (
                tier_rank.get(s["_ship"]["tier"], 1),
                0 if s["_ship"]["urgent"] else 1,
            ),
        )
        for s in ordered:
            ship = s["_ship"]
            cl = s.get("assigned_clevel", "")
            who = CLEVEL_NICK.get(cl, cl) if cl else ""
            who_s = f" [{who}]" if who else ""
            flags = ("🔴" if ship["urgent"] else "") + ("🌟" if ship["northstar"] else "")
            title = plainify(summarize_title(s.get("title", "")))
            lines.append(f" {ship['icon']} {title}{who_s} {flags}".rstrip())
    else:
        lines.append(" · 오늘 띄울 배 없음")
    if deep:
        lines.append(f" ⚓ 명확화 대기 {len(deep)}건 — 항로 확정 후 출항")

    # ── 🌟 북극성 침로 (없으면 섹션 생략) ──
    if northstar_today:
        lines.append("")
        lines.append("🌟 북극성 침로  (오늘 별에 가까워지는 일)")
        for s in northstar_today:
            lines.append(f" · {plainify(summarize_title(s.get('title', '')))}")

    # ── 🌀 표류 주의 (완료했는데 다음 항로점 없음) ──
    lines.append("")
    lines.append("🌀 표류 주의  (입항 완료인데 다음 항로점 없음)")
    if drift:
        for d in drift[:5]:
            lines.append(f" · {plainify(summarize_title(d.get('title', '')))}")
            # 핵심조언: note 또는 summary 중 채워진 것 (A안 — 표류는 핵심조언+다음정하기 둘 다)
            _advice = str(d.get("note") or d.get("summary") or "").strip()
            if _advice:
                lines.append(f"   💡 핵심조언: {plainify(_advice[:80])}")
            lines.append("   👉 다음 뭐 할지 정하세요")
    else:
        lines.append(" 없음 ✓")

    # ── 🔴 선장(GM) 결정 (제목 + 카테고리 한 줄 — 순환사유 제거) ──
    lines.append("")
    if gm_dec:
        lines.append("🔴 선장(GM) 결정")
        for i, a in enumerate(gm_dec, 1):
            title_clean = plainify(summarize_title(a.get("title", "")))
            # 카테고리를 사유에서 추출 — "X · 결재 첫 단계…" 형태면 X만 취함
            raw_reason = a.get("disposition_reason", "")
            # "카테고리 · 결재 단계" 에서 카테고리만 추출 (뒤 결재 설명 제거)
            cat = raw_reason.split("·")[0].strip() if "·" in raw_reason else ""
            suffix = f" — {cat}" if cat else ""
            lines.append(f"{_circled(i)} {title_clean}{suffix}")
    else:
        lines.append("🔴 선장(GM) 결정: 없음")

    return "\n".join(lines)


def build_question_card(gm_decision: list[dict]) -> str:
    """GM 결정 필요(보안·결재) 항목 전용 카드 — 본보고와 별도 발송. 제목 잘림 없음."""
    if not gm_decision:
        return ""
    lines = ["🔴 선장 결정 카드 (아침)"]
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
    # [2026-06-23 GM] 아침 선장 결정카드 중복 폐지 — '오늘의 항로' 보고 안에
    # 🔴 선장(GM) 결정 목록이 이미 인라인 포함됨. 별도 카드는 같은 내용 2번째
    # 텔레그램이라 중복 → 발송 안 함. (build_question_card 함수는 보존)
    question_card = ""
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
