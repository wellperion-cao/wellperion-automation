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

# 휴관일 인지(2026-07-27 시토, 배10303) — 단일 판정 재사용, 새 판정 함수 신설 금지(약속 L21)
from close_days import is_closed  # noqa: E402
from kakao_auto_daily_report import build_holiday_notice  # noqa: E402

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

# ── 항로 보드 — G1과 동일 엔진 소비 (2026-07-22 GM 지시: 항로↔G1 정합) ─────────
# SSOT: scripts/hangro_board.py build_board() — 08:00 항로 블록의 자체 재구현 금지.
# 08:00 build_telegram_report()가 이 함수 결과를 그대로 렌더해, G1 웹보드와
# 동일 출처·동일 3섹터 분류(🚢진행중/⚓대기중/🏁입항완료)·동일 결재판정을 쓴다.
# _md_table/_item_to_row 는 '입항완료' 접기(텔레그램 길이 제약)에도 동일 행 포맷을
# 쓰기 위한 재사용 — 새 표 렌더러 중복 구현 금지.
from hangro_board import (  # noqa: E402
    fetch_gas_items as hangro_fetch_gas_items,
    fetch_queue_items as hangro_fetch_queue_items,
    build_board as hangro_build_board,
    _md_table as hangro_md_table,
    _item_to_row as hangro_item_to_row,
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
        today_tasks = list(g1["today_tasks"])

        # ── _queue.json 활성 배 머지 (2026-07-10 시토 — INC 진단·수리) ──────
        # 왜: G1 API 성공 시 today_tasks가 시트(GAS)만 반영해, _queue.json에만
        # 있는 C-Level 자동등록 배(시트엔 존재 안 함)가 '오늘 항로'에서 매일
        # 통째로 누락됐다(08:00 보고 '오늘 항로 0건' 버그). 정본 머지 로직은
        # hangro_board.py(GAS+큐 머지, CLAUDE.md §3-1 SSOT)를 그대로 재사용
        # — 새 병합 로직 중복 구현 금지. 중복키는 queue_integrity_check._core_key()
        # 로 시트 항목과 대조해 이중계상을 막는다.
        try:
            from hangro_board import fetch_queue_items as _fetch_queue_items
            from queue_integrity_check import _core_key as _ck
            _sheet_keys = {
                _ck(it.get("title", ""))
                for it in (gm_decision + today_tasks
                           + g1["done_today"] + g1["done_yesterday"])
            }
            for qit in _fetch_queue_items():
                st = str(qit.get("status", "")).upper()
                if st not in ("PENDING", "IN_PROGRESS"):
                    continue
                if str(qit.get("board", "")) == "자율현황":
                    continue  # 자율화 미션 — 항로 제외, 자율현황行 (GM 2026-07-15)
                if _ck(qit.get("title", "")) in _sheet_keys:
                    continue  # 시트에 이미 같은 배 존재 — 이중계상 방지
                today_tasks.append({
                    "title": qit.get("title", ""),
                    "task_id": qit.get("id", ""),
                    "owner": qit.get("owner", ""),
                    "status": qit.get("status", ""),
                    "start_date": "",
                    # 담당 식별번호(약속 L16: 담당=닉네임+ship_no) — _queue 배만 보유
                    "ship_no": qit.get("ship_no", ""),
                    "source": "queue",
                })
        except Exception as exc:
            print(f"[WARN] _queue.json 항로 머지 실패: {exc} — 시트 데이터만 사용", file=sys.stderr)

        # 자율화 미션(board='자율현황')이 시트 경로로 새어 들어오면 항로에서 제거(방어) — 자율현황行 (GM 2026-07-15)
        try:
            from hangro_board import fetch_queue_items as _fqi_b
            from queue_integrity_check import _core_key as _ck_b
            _board_keys = {_ck_b(x.get("title", "")) for x in _fqi_b() if str(x.get("board", "")) == "자율현황"}
            if _board_keys:
                today_tasks = [t for t in today_tasks if _ck_b(t.get("title", "")) not in _board_keys]
        except Exception:
            pass

        # today_tasks는 전부 AUTONOMOUS (결재 대기는 이미 gm_decision에 분리됨)
        autonomous: list[dict] = []
        deep_interview: list[dict] = []
        for it in today_tasks:
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
        if str(q.get("board", "")) == "자율현황":
            continue  # 자율화 미션 — 항로 제외, 자율현황行 (GM 2026-07-15)
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
                        "terminal": q.get("terminal", False),  # 표류 판정 보존
                        "next": q.get("next", ""),             # 표류 판정 보존
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


# 종결·후속 마커 — terminal/next 필드 기반 표류 제외 판정용
_SETTLED_MARKERS_RE = re.compile(r"입항완료|입항 완료|다음 불필요|다음 불요|🏁|루틴")


def _is_settled_or_bridged(d: dict) -> bool:
    """
    완료 배가 명시적으로 종결/후속 처리됐으면 True → 표류 아님.
    1) terminal=True       → 명시적 최종 종결
    2) next에 종결 마커    → 정상 입항(다음 불필요)
    3) next에 후속 신호    → 🔗 항로점(다음 있음)
    note 필드만 보던 기존 로직의 next·terminal 누락 버그 보완.
    """
    if d.get("terminal") is True:
        return True
    nxt = str(d.get("next") or "").strip()
    if nxt:
        if _SETTLED_MARKERS_RE.search(nxt):
            return True
        if "🔗" in nxt or "다음=" in nxt:
            return True
        if _FOLLOWUP_RE.search(nxt):
            return True
    return False


# ── 08:00 흡수 섹션 (2026-07-18 GM 승인 — GM DM 알림 홍수 축소) ─────────────────
# 폐지된 GM DM 슬롯의 핵심값을 08:00 통합브리프로 접어 넣는다(값 유실 0).
#   · 07시(어제결산·직원 공유카드) · 09시(매출 1줄) · 06:30(북극성 top 추천).
# 소스는 전부 기존 것 재사용 — 새 채널·새 SSOT·새 스크립트 없음.
QUOTES_PATH = STATUS_DIR / "quotes.json"
NORTHSTAR_PENDING_PATH = STATUS_DIR / "northstar_pending.json"
# home_kpi = 09시 _fetch_cfo_finance_block과 동일 소스(ERP home과 수치 일치). _G1_API와 같은 GAS 배포.
_HOME_KPI_API = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7"
    "/exec?action=home_kpi"
)


def _kr_amt(n) -> str:
    """한국식 금액 표기: 271488886 → '2억 7,148만'. ERP home krAmt와 동일 규칙."""
    try:
        n = round(float(n))
    except (TypeError, ValueError):
        return "—"
    sign = "-" if n < 0 else ""
    n = abs(n)
    eok = n // 100000000
    man = (n % 100000000) // 10000
    if eok > 0 and man > 0:
        return f"{sign}{eok}억 {man:,}만"
    if eok > 0:
        return f"{sign}{eok}억"
    if man > 0:
        return f"{sign}{man:,}만"
    return f"{sign}{n:,}원"


def fetch_sales_oneline() -> str:
    """매출·지출 1줄 (구 09시 흡수 · 상세는 카톡 09:30 담당). ERP home과 동일 소스(home_kpi).
    실패·데이터없음 시 ''(줄 생략)."""
    try:
        req = urllib.request.Request(
            _HOME_KPI_API, headers={"User-Agent": "Mozilla/5.0 (CEO-morning-pipeline)"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"[WARN] 매출 1줄 조회 실패: {exc}", file=sys.stderr)
        return ""
    if not isinstance(data, dict) or not data.get("ok"):
        return ""
    sales = data.get("sales") or {}
    expense = data.get("expense") or {}
    s_month, e_month = sales.get("month"), expense.get("month")
    if s_month is None and e_month is None:
        return ""
    return f"💰 이달 매출 {_kr_amt(s_month)} · 지출 {_kr_amt(e_month)}  (상세는 카톡 09:30)"


def fetch_northstar_top() -> str:
    """북극성 top 추천 1건 (구 06:30 카드 흡수). status/northstar_pending.json 재사용.
    반환: 렌더 블록 또는 ''(파일 없음·후보 없음)."""
    try:
        data = json.loads(NORTHSTAR_PENDING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ""
    # 오늘자 추천만 표시 — 06:30이 안 돌아 어제 것이 남았으면 생략(오해 방지).
    if str(data.get("date", "")) != datetime.now().strftime("%Y-%m-%d"):
        return ""
    cands = data.get("candidates") or []
    if not cands:
        return ""
    c = cands[0]
    title = summarize_title(str(c.get("title", "")), limit=54)
    fa = str(c.get("first_action", "")).strip()
    diff = str(c.get("difficulty", "")).strip()
    who = str(c.get("owner", "")).strip()
    tag = " ✅승인됨" if str(data.get("status", "")) == "approved" else ""
    head = f" {diff} {title}".rstrip() + (f" [{who}]" if who else "")
    lines = [f"🧭 웰리의 오늘의 북극성 한 수{tag}", head]
    if fa:
        lines.append(f"   👉 첫 행동: {fa[:70]}")
    return "\n".join(lines)


def _staff_quote() -> str:
    """직원 공유 카드용 06시대 명언 1건(활성). 실패 시 기본 문구."""
    try:
        data = json.loads(QUOTES_PATH.read_text(encoding="utf-8"))
        active = [q.get("text", "") for q in data.get("06", []) if q.get("active") and q.get("text")]
        if active:
            import random
            return random.choice(active)
    except Exception:
        pass
    return "오늘 하루도 한 걸음씩, 꾸준함이 곧 실력입니다."


def build_staff_share_card() -> str:
    """직원 공유용 복붙 카드 (구 07시 직원카드 흡수) — 북극성 미션 + 오늘의 한 마디."""
    now = datetime.now()
    wd = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    quote = _staff_quote()
    return (
        "✂️ ───── 직원 공유용 (아래부터 카톡 복붙) ─────\n"
        f"🌟 {now.strftime('%Y-%m-%d')} ({wd}) 북극성\n"
        "회원 한 사람의 건강한 하루를 완성한다\n\n"
        "💬 오늘의 한 마디\n"
        f"\"{quote}\""
    )


def build_yesterday_done_line(yday_items: list[dict]) -> list[str]:
    """어제 완료 요약 1~2줄 (구 07시 결산 흡수). 건수 + 대표 최대 2건. 없으면 []."""
    n = len(yday_items)
    if n == 0:
        return []
    out = [f"🔗 지나온 항로 — 어제 입항 {n}건"]
    reps = [plainify(summarize_title(str(d.get("title", "")))) for d in yday_items[:2]]
    reps = [r for r in reps if r]
    if reps:
        out.append("  " + " · ".join(reps) + (f"  외 {n - len(reps)}건" if n > len(reps) else ""))
    return out


# ── 텔레그램 길이 제약 (2026-07-22 GM 지시: 항로↔G1 정합 검증 중 실측 발견) ────
# G1 항로 보드 전량 텍스트는 하루 완료가 많은 날(실측 2026-07-22 84건) 14KB+로,
# 텔레그램 sendMessage 4096자 한도를 진행중·대기중 구간만으로도 넘는다(실측 6.7KB).
# ① 입항완료 표만 상위 N건+건수 요약으로 접고(3섹터 분류·건수 자체는 불변),
# ② 그래도 넘치면 문단 경계에서 여러 메시지로 분할 발송한다(표 행 안 끊김).
TELEGRAM_MSG_LIMIT = 4096
_DONE_SECTION_HEADER = "### 🏁 입항 완료 (오늘)"
_DONE_FOLD_MAX_ROWS = 10


def _fold_board_done_section(board_text: str, secs: dict, max_rows: int = _DONE_FOLD_MAX_ROWS) -> str:
    """
    hangro_board.build_board() 결과의 '🏁 입항 완료 (오늘)' 표만 상위 max_rows건 +
    '총 N건' 요약으로 접는다. 3섹터 분류·건수(상단 요약 표)·진행중/대기중/결재판정은
    100% 그대로 — G1 웹보드는 전량, 08:00 텔레그램은 요약(둘 다 secs 동일 출처).
    """
    done_all = secs.get("done", []) + secs.get("drift", [])
    if len(done_all) <= max_rows:
        return board_text  # 접을 필요 없음 — 원문 그대로

    head, sep, _rest = board_text.partition(_DONE_SECTION_HEADER)
    if not sep:
        return board_text  # 마커 미검출 — 크래시 방지, 원문 유지(fallback)

    rows = [
        hangro_item_to_row(it, ship_col_extra="🔗" if str(it.get("next") or "").strip() else "")
        for it in secs.get("done", [])[:max_rows]
    ]
    n_appr = len(secs.get("appr", []))
    n_inflight = len(secs.get("appr_inflight", []))

    tail_lines = [
        sep,
        f"총 {len(done_all)}건 — 상위 {len(rows)}건만 표시(전량은 G1 웹보드/`hangro_board.py`)",
        hangro_md_table(rows) if rows else "_(없음)_\n",
    ]
    if n_appr:
        tail_lines.append(f"🔴 GM 결재 {n_appr}건 — 결재 현황 SSOT에서 확인·결재")
    if n_inflight:
        tail_lines.append(f"⏳ 결재 진행 중 {n_inflight}건 (타 결재자 대기) — 결재 현황 SSOT")
    tail_lines.append("")
    tail_lines.append("━" * 36)
    tail_lines.append("_본 보드는 자동 생성입니다._")

    return head + "\n".join(tail_lines)


def split_for_telegram(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> list[str]:
    """
    긴 보고를 텔레그램 4096자 한도에 맞춰 문단(빈 줄) 경계에서 분할.
    (scripts/report_stream_3_impl.py _chunk_blocks 와 동일 원리 — 표 행 중간에서
    끊기지 않게 문단 단위로 자르고, 문단 자체가 한도를 넘으면 줄 단위로 추가 분할.)
    """
    blocks = text.split("\n\n")
    messages: list[str] = []
    current = ""
    for b in blocks:
        candidate = f"{current}\n\n{b}" if current else b
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            messages.append(current)
            current = ""
        if len(b) <= limit:
            current = b
            continue
        # 문단 자체가 한도 초과 — 줄 단위로 추가 분할
        sub = ""
        for line in b.split("\n"):
            cand2 = f"{sub}\n{line}" if sub else line
            if len(cand2) <= limit:
                sub = cand2
            else:
                if sub:
                    messages.append(sub)
                sub = line[:limit]
        current = sub
    if current:
        messages.append(current)
    return messages


def _board_text_and_secs(gas_items: list[dict], queue_items: list[dict]) -> tuple[str, dict]:
    """hangro_board.build_board() 호출 + 텔레그램 길이 접기(공유 헬퍼).
    build_telegram_report / build_split_reports 양쪽이 동일 조립을 재사용(중복 구현 금지)."""
    board_text, secs = hangro_build_board(gas_items, queue_items)
    board_text = _fold_board_done_section(board_text, secs)
    return board_text, secs


def _board_item_count(secs: dict) -> int:
    """항로 3섹터(+긴급·결재) 표시 항목 총합. 0이면 '빈 표' — 발신 금지 판정에 사용
    (자율화 미션 secs['autonomy']은 애초 항로 제외 대상이라 카운트에서 뺀다)."""
    return sum(len(secs.get(k, [])) for k in
               ("urgent", "today", "appr", "appr_inflight", "done", "drift"))


def _build_appendix_lines() -> list[str]:
    """항로 블록 뒤 '── 부록 ──' — 매출·운영점검·북극성 한 수·직원카드 (구 06:30/07/09시 흡수).
    build_telegram_report / build_split_reports(업무보고방) 공유 — 부가내용 삭제 없음."""
    lines = ["", "━" * 14 + " 부록 " + "━" * 14]

    # ── 💰 매출·지출 1줄 (구 09시 GM DM 흡수 · 상세는 카톡 09:30) ──
    _sales_line = fetch_sales_oneline()
    if _sales_line:
        lines.append(_sales_line)
        lines.append("")

    # COO 모듈 자동보고 합류 (레지스트리 구동 — 점검현황 등 daily_join 모듈)
    try:
        import sys as _sys, os as _os
        _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", "..", "scripts"))
        from coo_report_line import build_coo_daily_lines
        _coo_lines = build_coo_daily_lines(heartbeat=True)
        if _coo_lines:
            lines.append("🏢 <b>운영 점검</b>")
            lines.extend(_coo_lines)
            lines.append("")
    except Exception as _e:
        lines.append(f"🏢 운영 점검: (합류 실패 — {type(_e).__name__})")
        lines.append("")

    # ── 🧭 웰리의 북극성 한 수 (구 06:30 추천 카드 흡수 · northstar_pending.json) ──
    _ns_top = fetch_northstar_top()
    if _ns_top:
        lines.append(_ns_top)
        lines.append("")

    # ── 직원 공유용 복붙 카드 (구 07시 직원카드 흡수) — 부록 맨 아래 배치 ──
    lines.append(build_staff_share_card())
    return lines


def _yesterday_holiday_line() -> str:
    """어제가 휴관일이면 08:00 보고 맨 위에 붙일 한 줄(배10303 · GM 확정 2026-07-27).
    새 문구 생성 함수를 만들지 않고 kakao_auto_daily_report.build_holiday_notice()가
    이미 만드는 첫 문장만 재사용한다(약속 L21). 어제가 정상 영업일이면 빈 문자열."""
    yesterday = datetime.now() - timedelta(days=1)
    if not is_closed(yesterday):
        return ""
    notice = build_holiday_notice(yesterday, datetime.now())
    first_sentence = notice.split(". ", 1)[0].rstrip(".") + "."
    return f"어제 {first_sentence}"


def build_telegram_report(s1: dict, assigned: list[dict], orch: dict) -> str:
    """
    GM 아침 보고 — '오늘의 항로' 레이아웃.

    2026-07-22 GM 지시(항로 ↔ G1 정합): 항로 블록은 더 이상 이 함수가 자체
    재구현하지 않는다. scripts/hangro_board.py의 build_board() 결과를 그대로
    소비해 렌더한다 — 08:00과 G1 웹보드가 동일 출처(GAS todo_list + _queue.json)·
    동일 3섹터 분류(🚢진행중/⚓대기중/🏁입항완료)·동일 결재판정(_next_approver)을
    쓴다. 기존에는 이 함수가 fetch_g1_ssot 결과를 flat 리스트로 재분류하고
    SECURITY_SIGNALS 키워드('토큰'·'PIN' 등)로 GM결재를 오탐(6건)했으며
    입항완료 섹션도 없었다 — 그 자체 재구현을 폐기한다.

    s1/assigned/orch(3분류·배정·오케스트레이션 계획)는 stage1~3의 산출물로
    save_plan()의 로컬 감사 JSON에는 계속 쓰이지만, 이 렌더 함수에는 더 이상
    관여하지 않는다(시그니처는 run_pipeline 호출부 호환을 위해 유지).

    부가내용(매출·운영점검·북극성 한 수·직원카드)은 삭제하지 않고 항로 블록
    뒤 '── 부록 ──' 아래로 명확히 분리해 GM이 항로/부가를 혼동하지 않게 한다.

    [2026-07-26 웰리 지시 배10244] 08:00 분리 발신(업무보고방/AI 진행현황방)의
    폴백 안전판 — 이 함수·send_reports()는 원본 그대로 보존한다. 분리 시도가
    실패(방 해소·분류 예외)하면 run_pipeline이 이 함수로 되돌아가 기존처럼
    통째 1회 발송한다(정보 손실 0).
    """
    gas_items = hangro_fetch_gas_items()
    queue_items = hangro_fetch_queue_items()
    board_text, _secs = _board_text_and_secs(gas_items, queue_items)
    holiday_line = _yesterday_holiday_line()
    lines = ([holiday_line, ""] if holiday_line else []) + [board_text] + _build_appendix_lines()
    return "\n".join(lines)


# ── 08:00 분리 발신 — 업무보고방 / AI 진행현황방 (2026-07-26 웰리 지시 배10244) ──────
# 웰리가 정한 경계(2026-07-26 실측으로 1차안 폐기 후 확정 · 임의 변경 금지):
#   AI 진행현황방(자동화현황방) = 기계가 스스로 만든 배만(_AI_ROOM_ORIGINS)
#   업무보고방(8254867551)     = 그 밖의 전부 — S3(GAS todo_list) 배 + 나머지 _queue 배
# ★1차안(‘origin=="gm" 만 업무보고방, 나머지 전부 AI 방’)은 dry-run 실측에서 폐기했다.
#   실무진 피드백 처리·GM 직접 지시 배가 AI 방으로 숨고 업무보고방이 비었다 — 지금보다 나쁘다.
#   큐에 '누구를 위한 일인가' 칸이 생기기 전까지는 덜 덜어내는 쪽이 맞다(배10292 후속).
# 새 판별 함수·새 파일·새 필드 생성 금지(약속 L21) — origin 필드(이미 존재)와
# module_reporter.resolve_chat_id() 단일 경로만 재사용한다.

def _queue_origin_map() -> dict[str, str]:
    """_queue.json 원본에서 task_id → origin(소문자) 맵. origin은 이미 존재하는 필드 —
    hangro_board.fetch_queue_items()가 렌더용으로 골라낸 필드셋에는 없어 원본에서 직독한다."""
    m: dict[str, str] = {}
    for q in load_queue():
        tid = str(q.get("task_id") or "").strip()
        if tid:
            m[tid] = str(q.get("origin") or "").strip().lower()
    return m


def _queue_audience_map() -> dict[str, str]:
    """_queue.json 원본에서 task_id → audience(소문자) 맵. audience는 queue_dispatch.py의
    build_ship()이 이미 써 넣는 필드(배10300 웰리 결정 · 배10301) — 배 작성자의 선언을
    origin 낱말 추정보다 먼저 믿는다. 값 없음/공백은 빈 문자열(폴백 대상 표시)."""
    m: dict[str, str] = {}
    for q in load_queue():
        tid = str(q.get("task_id") or "").strip()
        if tid:
            m[tid] = str(q.get("audience") or "").strip().lower()
    return m


def _count_unspecified_audience(queue_items: list[dict]) -> int:
    """audience 필드가 office/ai 어느 쪽도 아닌(미표기) 배 수 — 소급 미표기 안전판(배10301
    웰리 수정 ④). 이 수치가 안 줄면 웰리가 required 승격을 재판단한다."""
    audience_map = _queue_audience_map()
    n = 0
    for it in queue_items:
        tid = str(it.get("id") or "").strip()
        if audience_map.get(tid, "") not in ("office", "ai"):
            n += 1
    return n


# AI 진행현황방으로 보낼 자격이 있는 origin — '기계가 스스로 만든 배'만 확실히 여기 해당한다.
# bridge   = 완료 훅이 '다음'으로 자동 생성한 포인터 배
# self-audit = 아침 자가점검(약속 L20)이 스스로 띄운 배
# ★incident·gm 은 넣지 않는다: 실측(2026-07-26) 결과 origin=='gm' 12척 대부분이 시토의
#   내부 정비 배였고, 실무진 피드백 처리 배는 origin 이 비어 있었다 — origin 은 '누구를
#   위한 일인가'를 담은 칸이 아니다. 그래서 이 집합 밖은 전부 업무보고방에 남긴다(아래).
_AI_ROOM_ORIGINS = ("bridge", "self-audit")


def _split_queue_items_for_rooms(queue_items: list[dict]) -> tuple[list[dict], list[dict]]:
    """hangro_fetch_queue_items() 결과를 업무보고방/AI 진행현황방 배로 가른다.

    [2026-07-27 시토 배10301 — 웰리 결정 배10300 반영] audience 필드(선언값)를 먼저
    믿는다: audience=="office" → 업무보고방 / audience=="ai" → AI 진행현황방.
    값이 없는 배만 기존 origin 폴백을 탄다(퇴화 0·정보 손실 0 — 아래는 원본 그대로 보존).

    ★기존 폴백(origin 기반) — 배10244: 큐에 '이 일이 누구를 위한 것인가'를 담은 칸이
    없던 시절의 안전장치. 확실히 기계가 만든 배(_AI_ROOM_ORIGINS)만 AI 방으로 덜어내고,
    판단이 안 서는 배는 전부 업무보고방에 남긴다. 잘못 덜어내면 실무진 일이 GM 시야에서
    사라지지만, 안 덜어내면 그냥 지금과 같을 뿐이라 두 오류의 무게가 다르다.
    """
    origin_map = _queue_origin_map()
    audience_map = _queue_audience_map()
    office, ai = [], []
    for it in queue_items:
        tid = str(it.get("id") or "").strip()
        audience = audience_map.get(tid, "")
        if audience == "office":
            office.append(it)
        elif audience == "ai":
            ai.append(it)
        else:
            (ai if origin_map.get(tid, "") in _AI_ROOM_ORIGINS else office).append(it)
    return office, ai


def build_split_reports(s1: dict, assigned: list[dict], orch: dict) -> tuple[str, str | None]:
    """
    08:00 보고를 업무보고방/AI 진행현황방 2건으로 분리 조립.
    반환: (office_report, ai_report). ai_report는 AI 방으로 갈 배가 0건이면
    None(빈 표 발신 금지). 업무보고방은 기존 build_telegram_report와 동일 양식
    (항로 3섹터 표 + 부록) — 제목·부록 구성 변경 없음.
    """
    gas_items = hangro_fetch_gas_items()
    all_queue_items = hangro_fetch_queue_items()
    office_queue, ai_queue = _split_queue_items_for_rooms(all_queue_items)

    office_board, _office_secs = _board_text_and_secs(gas_items, office_queue)
    holiday_line = _yesterday_holiday_line()
    office_report = "\n".join(
        ([holiday_line, ""] if holiday_line else []) + [office_board] + _build_appendix_lines()
    )

    ai_board, ai_secs = _board_text_and_secs([], ai_queue)
    ai_report = ("🤖 AI C레벨 진행현황\n" + ai_board) if _board_item_count(ai_secs) > 0 else None
    # 배10301 안전판(웰리 수정) — audience 미지정 배가 남아 있으면 AI방 표 맨 아래 1줄로 노출.
    # 0척이면 줄을 붙이지 않는다(새 리포트 강제 생성 금지 — 0건 발신 억제 원칙 유지).
    unspecified_n = _count_unspecified_audience(all_queue_items)
    if unspecified_n and ai_report:
        ai_report += f"\n\naudience 미표기 {unspecified_n}척"

    return office_report, ai_report


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


def _resolve_ai_room_chat_id() -> int | None:
    """AI 진행현황방(자동화현황방) chat_id 해소. status/telegram_rooms.json +
    module_reporter.resolve_chat_id() 단일 경로 재사용(약속 L01 — 판정 로직 복제 금지).
    해소 실패(파일·모듈·키 없음) 시 None → 호출부가 분리 발신을 포기하고 폴백."""
    try:
        rooms = json.loads((STATUS_DIR / "telegram_rooms.json").read_text(encoding="utf-8"))
        from module_reporter import resolve_chat_id  # noqa: PLC0415
        return resolve_chat_id("자동화현황방", rooms)
    except Exception as exc:
        print(f"[WARN] AI 진행현황방 chat_id 해소 실패: {exc}", file=sys.stderr)
        return None


def send_split_reports(office_report: str, ai_report: str | None, ai_chat_id, dry_run: bool) -> bool:
    """
    08:00 분리 발신 — 업무보고방(기존 TelegramNotifier 경로) + AI 진행현황방
    (기존 notify.telegram_send.send 범용 발신기, notify_gm_progress.py와 동일 경로).
    새 발신 경로 생성 금지 — 둘 다 이미 있는 발신기를 그대로 재사용한다.
    ai_report가 None이면 AI 진행현황방은 아예 호출하지 않는다(빈 표 발신 금지).
    """
    office_chunks = split_for_telegram(office_report)
    ai_chunks = split_for_telegram(ai_report) if ai_report else []

    if dry_run:
        print(f"\n========== [DRY-RUN] 업무보고방(8254867551) 「🧭 오늘의 항로」 "
              f"({len(office_chunks)}통, 발송 안 함) ==========")
        for i, chunk in enumerate(office_chunks, 1):
            print(f"---------- 메시지 {i}/{len(office_chunks)} ({len(chunk)}자) ----------")
            print(chunk)
        if ai_chunks:
            print(f"\n========== [DRY-RUN] AI 진행현황방(chat_id={ai_chat_id}) 「🤖 AI C레벨 진행현황」 "
                  f"({len(ai_chunks)}통, 발송 안 함) ==========")
            for i, chunk in enumerate(ai_chunks, 1):
                print(f"---------- 메시지 {i}/{len(ai_chunks)} ({len(chunk)}자) ----------")
                print(chunk)
        else:
            print("\n[DRY-RUN] AI 진행현황방 — 배정된 배 0건, 발송 스킵(빈 표 발신 금지)")
        print("========== [DRY-RUN] 끝 ==========\n")
        return True

    ok1 = True
    try:
        from telegram_notifier import TelegramNotifier
        tg = TelegramNotifier()
        for chunk in office_chunks:
            r1 = tg.send(chunk)
            ok1 = ok1 and (bool(r1.get("ok")) if isinstance(r1, dict) else False)
    except Exception as exc:
        print(f"[FAIL] 업무보고방 발송 실패: {exc}", file=sys.stderr)
        ok1 = False

    ok2 = True
    if ai_chunks:
        try:
            from notify.telegram_send import send as _tg_send  # noqa: PLC0415
            for chunk in ai_chunks:
                ok2 = ok2 and bool(_tg_send(ai_chat_id, chunk))
        except Exception as exc:
            print(f"[FAIL] AI 진행현황방 발송 실패: {exc}", file=sys.stderr)
            ok2 = False

    print(f"[OK] 텔레그램 분리 발송 — 업무보고방={ok1}({len(office_chunks)}통) "
          f"AI진행현황방={ok2}({len(ai_chunks)}통, 배정 {'있음' if ai_chunks else '없음'})")
    return ok1 and ok2


def send_reports(report: str, question_card: str, dry_run: bool) -> bool:
    # 항로 블록(hangro_board)이 커지면 본 보고가 텔레그램 4096자 한도를 넘는 날이
    # 있다(실측 2026-07-22) — 문단 경계에서 여러 메시지로 분할 발송(표 안 끊김).
    report_chunks = split_for_telegram(report)
    if dry_run:
        print(f"\n========== [DRY-RUN] 텔레그램 본 보고 "
              f"({len(report_chunks)}통, 발송 안 함) ==========")
        for i, chunk in enumerate(report_chunks, 1):
            print(f"---------- 메시지 {i}/{len(report_chunks)} ({len(chunk)}자) ----------")
            print(chunk)
        if question_card:
            print("\n---------- [DRY-RUN] 질문 카드 (발송 안 함) ----------")
            print(question_card)
        print("========== [DRY-RUN] 끝 ==========\n")
        return True
    try:
        from telegram_notifier import TelegramNotifier
        tg = TelegramNotifier()
        ok1 = True
        for chunk in report_chunks:
            r1 = tg.send(chunk)
            ok1 = ok1 and (bool(r1.get("ok")) if isinstance(r1, dict) else False)
        ok2 = True
        if question_card:
            r2 = tg.send(question_card)
            ok2 = bool(r2.get("ok")) if isinstance(r2, dict) else False
        print(f"[OK] 텔레그램 발송 — 본보고={ok1}({len(report_chunks)}통) 질문카드={ok2}")
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

    # [2026-07-27 시토 배10303 · GM 확정] 당일이 휴관일이면 08:00 항로 보고 전체를
    # 휴관 안내문으로 대체한다. 문구는 새로 짓지 않고 kakao_auto_daily_report.py에
    # 이미 있는 build_holiday_notice() 로직을 그대로 재사용(약속 L21).
    _now = datetime.now()
    if is_closed(_now):
        notice = build_holiday_notice(_now, _now)
        print(f"[HOLIDAY] 오늘({_now.strftime('%Y-%m-%d')})은 휴관일 — "
              f"08:00 항로 보고를 휴관 안내문으로 대체: {notice!r}")
        sent = send_reports(notice, "", dry_run)
        print(f"[STAGE 4] 보고 {'(dry-run 출력)' if dry_run else '발송'} — "
              f"휴관 안내문 대체 {'OK' if sent else 'FAIL'}")
        print(f"=== 파이프라인 종료 — {'성공' if sent else '실패'} (휴관 안내문) ===")
        return 0 if sent else 1

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
    # [2026-06-23 GM] 아침 선장 결정카드 중복 폐지 — '오늘의 항로' 보고 안에
    # 🔴 선장(GM) 결정 목록이 이미 인라인 포함됨. 별도 카드는 같은 내용 2번째
    # 텔레그램이라 중복 → 발송 안 함. (build_question_card 함수는 보존)
    question_card = ""

    # [2026-07-26 웰리 지시 배10244] 업무보고방/AI 진행현황방 분리 발신 시도.
    # 방 해소·분리 조립 중 무엇이든 실패하면 즉시 폴백 — 기존 단일 발신(통째 1회,
    # 업무보고방)으로 되돌아간다(정보 손실 0). 실무진 방으로는 절대 보내지 않는다.
    ai_chat_id = _resolve_ai_room_chat_id()
    split_ok = False
    office_report = ai_report = None
    if ai_chat_id is not None:
        try:
            office_report, ai_report = build_split_reports(s1, assigned, orch)
            split_ok = True
        except Exception as exc:
            print(f"[WARN] 분리 발신 조립 실패({exc}) — 기존 단일 발신으로 폴백", file=sys.stderr)
            split_ok = False

    plan_path = save_plan(s1, assigned, orch, dry_run)
    if split_ok:
        sent = send_split_reports(office_report, ai_report, ai_chat_id, dry_run)
        print(f"[STAGE 4] 보고 {'(dry-run 출력)' if dry_run else '발송'} — 분리(업무보고방+AI진행현황방) "
              f"{'OK' if sent else 'FAIL'}")
    else:
        report = build_telegram_report(s1, assigned, orch)
        sent = send_reports(report, question_card, dry_run)
        print(f"[STAGE 4] 보고 {'(dry-run 출력)' if dry_run else '발송'} — 단일 폴백 "
              f"{'OK' if sent else 'FAIL'}")

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
