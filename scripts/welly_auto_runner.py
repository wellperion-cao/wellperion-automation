"""
welly_auto_runner.py — 예약 Claude 러너 MVP (배237 phase3, GM 승인 2026-07-13).
정본 계획: docs/superpowers/specs/2026-07-13-welly-auto-runner-design.md

목표: 스케줄에 headless claude 세션을 자동으로 띄워, 가역·저위험 배 1척을
     실제 실행→검증→커밋까지 관통시킨다("웰리가 시켜서 완료까지"를 실제로 가능케).

★안전모델(기본 OFF)★
  1) 선별: welly_orchestrate.select_autonomous_ships(가역·담당 clevel·등록부 존재) +
     저위험 추가 필터(EXTRA_LOW_RISK_EXCLUDE_KEYWORDS) + 구체 작업 배 필터(_is_concrete_ship —
     origin=="bridge"·task_id "NEXT-"접두·priority 없음인 자동생성 '다음 참고' 포인터 배 제외) +
     쿨다운 배 제외. 난이도(priority) 오름차순 정렬 후 **1척만** 반환.
  2) 게이트: env RUNNER_LIVE(기본 미설정=OFF)="1"일 때만 실제 claude 호출.
     OFF면 dry-run — 배 선택 + 띄울 프롬프트 생성 + 로그만. claude 미호출·커밋 0·
     _queue.json 무변경.
  3) 재귀 폭주 방지: LIVE 실행 시 자식 프로세스 env에 WELLY_AUTO_RUNNER_ACTIVE=1을
     심는다. 이 env가 이미 켜져 있으면(=러너가 띄운 세션이 러너를 다시 부르려는 시도)
     즉시 guard-blocked로 거부(큐 로드조차 안 함).
  4) 폭주·비용 가드: 1회 1척(선별기 구조상 보장) · 실패 배는 COOLDOWN_HOURS 동안
     재선택 금지(status/welly_auto_runner_state.json) · claude 호출 타임아웃.
  5) 역롤백: LIVE 실행 전후 git HEAD 커밋 해시를 로그(status/welly_auto_runner_log.jsonl)에
     남긴다 — 문제 시 `git revert <commit>` 한 줄로 되돌릴 수 있다.
  6) 클린트리 베이스라인 + 사후 스코프 검증(2026-07-20 재설계, 배1307 실행): LIVE 실행 직전
     워킹트리를 점검해 allowlist(NOISE_PATH_PATTERNS) 밖 진짜 미커밋 작업을 "베이스라인
     foreign 파일"로만 기록한다(더 이상 사전 차단하지 않음 — 이 리포는 여러 세션이 동시에
     문서·콘텐츠를 남기는 구조라 완전히 클린한 순간이 드물어, 전면 차단은 러너를 상시 헛돌게
     했다 — 실측 33회 중 23회(70%) skip, 그 dirty 파일 전량이 CPO 스냅샷·heartbeat 같은
     이미 allowlist된 노이즈가 아니라 타 clevel이 남긴 채 며칠째 방치된 진짜 콘텐츠였음).
     대신 LIVE 실행·커밋 뒤 실제 커밋에 포함된 파일(changed_files)을 베이스라인 foreign
     파일 집합과 대조한다(_check_sweep_violation) — 겹치면 "이 세션이 남의 미커밋 작업을
     자기 커밋에 쓸어담았다"는 확정 증거이므로 즉시 `git revert --no-edit`로 되돌리고
     (충돌 시 --abort로 중간상태 방치 없이 원복) 배를 실패·쿨다운 처리한다. 사전 차단
     대신 사후 확정 검증으로 바꿔 같은 보호를 더 정확하게 준다(2026-07-13 관측 결함
     대응은 유지 — 무인 세션이 방치된 무관 작업을 자기 커밋에 쓸어담는 사고는 여전히 막힘).
     git status 자체가 실패하면(안전 확인 불가) 기존대로 fail-closed 차단한다.

라이브 부작용 0 함수(순수) — select_one_low_risk_ship, build_orchestration_prompt.
run_once만 게이트에 따라 실제 I/O(파일 읽기/쓰기·subprocess) 수행.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from welly_orchestrate import select_autonomous_ships  # noqa: E402  (기존 선별기 재사용)
from module_registry import load_registry  # noqa: E402

# ── 경로 상수 ──
DEFAULT_QUEUE_PATH = os.path.join(_PROJECT_ROOT, "status", "_queue.json")
DEFAULT_STATE_PATH = os.path.join(_PROJECT_ROOT, "status", "welly_auto_runner_state.json")
DEFAULT_LOG_PATH = os.path.join(_PROJECT_ROOT, "status", "welly_auto_runner_log.jsonl")

# ── 게이트·가드 env 이름(기존 게이트들과 별도) ──
LIVE_ENV_VAR = "RUNNER_LIVE"
GUARD_ENV_VAR = "WELLY_AUTO_RUNNER_ACTIVE"

# ── 저위험 추가 제외 키워드(welly_orchestrate.IRREVERSIBLE_KEYWORDS 위에 보강) ──
# 배 지시문 명시: 발행·배포·삭제·외부전송·결제·보안·전략·공식값(기존)
#              + 라이브GAS·시트쓰기 관련(신규, 아래 3종으로 코드화).
EXTRA_LOW_RISK_EXCLUDE_KEYWORDS = (
    "라이브",
    "GAS",
    "시트쓰기",
    "시트 쓰기",
)

COOLDOWN_HOURS = 24
MAX_SHIPS_PER_RUN = 1  # 선별기 구조가 항상 1척만 반환하므로 이 상수는 문서화 목적

# ── 전 C-Level 순회(배237 phase4, 2026-07-14 GM 요구) ──
# 정본: docs/superpowers/specs/2026-07-14-welly-runner-all-clevel-autodrive-design.md
# GM칸(제작 루프)·웰리칸(오케스트레이션)에 이은 매 회차 GM 재승인 부담을 없애기 위해,
# 러너의 선별 대상을 CTO 1개→7 C-Level 전체로 넓힌다. run_once() 자체의 안전 로직은
# 손대지 않는다(재귀 방지·클린트리·모호성 park·쿨다운·1clevel당 1척 전부 그대로) —
# run_cycle()은 그 위에 clevel 순회 + 사이클 총 상한만 얹는 얇은 래퍼.
DEFAULT_CLEVELS = ("cmo", "coo", "cto", "cpo", "ceo", "cfo", "chro")
CLEVEL_NICKS = {
    "ceo": "웰리",
    "cfo": "시뽀",
    "chro": "시로",
    "cmo": "시모",
    "coo": "시우",
    "cpo": "시포",
    "cto": "시토",
}
# 사이클(1회 run_cycle 호출)당 실제 라이브 성공 실행 총 상한. clevel별 1척은 이미
# select_one_low_risk_ship 구조가 보장하므로, 이 상수는 "여러 clevel에 후보가 동시에
# 몰릴 때" 한 사이클에서 너무 많은 척이 한꺼번에 라이브로 나가는 것만 추가로 막는다
# (전면 확산 전 GM go 존중 — 보수적 기본값).
MAX_SHIPS_PER_CYCLE = 3

_PRIORITY_WEIGHT = {"⛵돛단배": 0, "⛴️여객선": 1, "🛳️크루즈": 2}

# ── 모호성 에스컬레이션 (배xxx, 2026-07-13 GM go) ──
# 정본: docs/superpowers/specs/2026-07-13-welly-runner-ambiguity-escalation-design.md
AMBIGUOUS_CRUISE_PRIORITY = "🛳️크루즈"
_VAGUE_MIN_NOTE_LEN = 8  # note가 이 길이 미만이면 산출물·절차 불명확으로 간주(v1 보수적 임계값)
_MULTI_APPROACH_KEYWORDS = ("또는", "혹은", "여러 방법", "여러 방안", "선택지", "A안", "B안", "옵션")
_SCOPE_DECISION_KEYWORDS = ("스코프", "결정 필요", "판단 필요", "범위 결정", "방향 결정")
# 재개 헬퍼 마커: 웰리 세션이 GM 인터뷰 답변을 note에 기록할 때 남기는 표식.
# is_ambiguous는 이 마커 + aide_interview_needed 해제를 함께 보면 원 휴리스틱을
# 재적용하지 않고 통과시킨다("러너는 플래그·기록만 존중" — 무한 park 루프 방지).
INTERVIEW_ANSWER_MARKER = "[GM 인터뷰 답변]"

# ── 텔레그램 핑 2단 게이트(RUNNER_LIVE와 별도) — 기본 OFF ──
PING_LIVE_ENV_VAR = "RUNNER_PING_LIVE"
DEFAULT_PING_STATE_PATH = os.path.join(_PROJECT_ROOT, "status", "welly_auto_runner_ping_state.json")
AMBIGUOUS_PING_DAILY_CAP = 2


def _is_low_risk(ship: dict) -> bool:
    """welly_orchestrate._is_reversible보다 보수적인 저위험 판정(러너 전용 보강)."""
    # 판정은 설명글이 아니라 배 작성자의 선언을 먼저 믿는다(2026-07-27 GM 지적·오탐 45척 실측).
    # 선언이 없을 때만 낱말 스캔(EXTRA 키워드)으로 폴백.
    reversible = ship.get("reversible")
    if reversible is True:
        return True
    if reversible is False:
        return False
    fields = (
        ship.get("priority") or "",
        ship.get("title") or "",
        ship.get("note") or "",
    )
    text = " ".join(fields)
    return not any(keyword in text for keyword in EXTRA_LOW_RISK_EXCLUDE_KEYWORDS)


def _is_concrete_ship(ship: dict) -> bool:
    """
    'bridge' 포인터 배(자동 생성 다음-참고용 배)를 제외하는 품질 게이트.
    러너는 사람이 등록한 구체 작업 배만 자율 실행 대상으로 삼는다:
      - origin == "bridge" 배 제외(자동 생성 포인터)
      - task_id가 "NEXT-"로 시작하는 배 제외(bridge 포인터 관례)
      - priority가 없거나 빈 배 제외(난이도 배 미표기 = 구체 등록이 아님)
    """
    if ship.get("origin") == "bridge":
        return False
    task_id = ship.get("task_id") or ""
    if task_id.startswith("NEXT-"):
        return False
    if not (ship.get("priority") or "").strip():
        return False
    return True


def _priority_rank(ship: dict) -> int:
    return _PRIORITY_WEIGHT.get(ship.get("priority"), 1)  # 미표기 배=중간 취급


# ── 급한정도(urgency) — 무게와 다른 축. GM 결정 2026-07-27 ①안 "급함이면 다른 배보다 먼저 집는다".
#   배경: 실무진 피드백이 급한정도를 무게 칸에 밀어넣어(급함→🛳️크루즈) 오히려 park 되던 것을 고치며
#   ship['urgency'] 별도 칸으로 분리했다(cpo_staff_feedback_watch). 여기서는 그 칸이 '있을 때만' 읽는다.
#   ★기존 배 무영향: urgency 칸이 없으면 전부 '보통'(1)로 같은 값이라 정렬 결과가 종전과 동일하다.
_URGENCY_WEIGHT = {"급함": 0, "보통": 1, "천천히": 2}


def _urgency_rank(ship: dict) -> int:
    return _URGENCY_WEIGHT.get(ship.get("urgency"), 1)  # 미표기 배=보통 취급(종전 동작 보존)


def _sort_key(ship: dict):
    """선별 순서 = ①급한정도 ②무게. 급한정도가 없던 시절 배끼리는 ①이 동률이라 종전과 같은 순서."""
    return (_urgency_rank(ship), _priority_rank(ship))


def select_one_low_risk_ship(clevel, queue, registry=None, cooldown_task_ids=None):
    """
    welly_orchestrate.select_autonomous_ships(가역·해당clevel·활성·등록부존재) 결과에
    저위험 추가 필터 + 쿨다운 배 제외를 적용하고, **①급한정도(urgency) ②난이도(priority)** 순으로
    오름차순 정렬 후 **1척만** 반환한다. 후보 없으면 None.
    급한정도 칸이 없는 배는 전부 '보통'으로 같은 값이라 종전(난이도만 보던 때)과 순서가 같다.
    """
    cooldown_task_ids = cooldown_task_ids or set()
    candidates = select_autonomous_ships(clevel, queue, registry=registry)
    candidates = [s for s in candidates if _is_low_risk(s)]
    candidates = [s for s in candidates if _is_concrete_ship(s)]
    candidates = [s for s in candidates if s.get("task_id") not in cooldown_task_ids]
    # 이미 parked-interview 중인 배(aide_interview_needed=True)는 매 사이클 재선택해
    # 다른 후보를 막지 않도록 제외한다 — GM 답변 기록 시 플래그 해제되면 자연히 재후보군 복귀.
    candidates = [s for s in candidates if not s.get("aide_interview_needed")]
    if not candidates:
        return None
    candidates.sort(key=_sort_key)   # 급한정도 먼저, 그 다음 무게(GM ①안 2026-07-27)
    return candidates[0]


def is_ambiguous(ship: dict) -> dict:
    """
    배 실행 직전 모호성 판정(v1 보수적 — 의심되면 park).

    ★비협상 원칙(GM 2026-07-14, 배237 phase4 확장 지시 — 못박기)★
    모호성이 조금이라도 있으면 무조건 park(GM 인터뷰 대기)한다. 러너는 절대 "임의
    판단·추측으로 진행"하지 않는다 — clevel이 cto든 전체(run_cycle의 7종)든 예외
    없이 이 게이트를 거친다(run_cycle()도 run_once()를 그대로 호출하므로 clevel별
    우회 경로가 없음). 아래 중 하나라도 해당하면 모호로 판정한다:
      - note가 산출물·절차를 구체적으로 담기엔 너무 짧음(_VAGUE_MIN_NOTE_LEN 미만)
      - 접근법이 여러 개임을 시사하는 키워드(_MULTI_APPROACH_KEYWORDS)
      - 스코프·판단 결정이 필요함을 시사하는 키워드(_SCOPE_DECISION_KEYWORDS)
      - 난이도 🛳️크루즈(무거움) — 안전 기본 park
    재개 헬퍼: note에 INTERVIEW_ANSWER_MARKER가 있고 aide_interview_needed가 해제돼 있으면
    (=웰리 세션이 GM 인터뷰 답변을 기록·해소함) 원 휴리스틱을 재적용하지 않고 통과시킨다.
    반환: {"ambiguous": bool, "reasons": list[str]}
    """
    note = (ship.get("note") or "").strip()
    if INTERVIEW_ANSWER_MARKER in note and not ship.get("aide_interview_needed"):
        return {"ambiguous": False, "reasons": []}

    title = (ship.get("title") or "").strip()
    text = f"{title} {note}"
    reasons = []

    if len(note) < _VAGUE_MIN_NOTE_LEN:
        reasons.append("산출물·절차가 note에 구체적으로 안 나옴(무엇을 만들지 불명확)")
    if any(kw in text for kw in _MULTI_APPROACH_KEYWORDS):
        reasons.append("접근법이 여러 개(어느 방향인지 결정 필요)")
    if any(kw in text for kw in _SCOPE_DECISION_KEYWORDS):
        reasons.append("스코프 결정·판단이 필요(러너가 대신 정하면 안 되는 것)")
    if ship.get("priority") == AMBIGUOUS_CRUISE_PRIORITY:
        reasons.append("난이도 🛳️크루즈(무거움) — 안전 기본 park")

    return {"ambiguous": bool(reasons), "reasons": reasons}


def park_ship_for_interview(queue_path: str, task_id: str, reasons: list[str]) -> bool:
    """
    _queue.json에서 task_id 배를 찾아 aide_interview_needed=True + aide_interview_reason
    플래그를 부여한다(가역·note 무손상 — note는 건드리지 않음). 성공 시 True, 배 못 찾으면 False.
    """
    queue = _load_queue(queue_path)
    found = False
    for ship in queue:
        if ship.get("task_id") == task_id:
            ship["aide_interview_needed"] = True
            ship["aide_interview_reason"] = "; ".join(reasons)
            found = True
            break
    if not found:
        return False
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
    return True


def parked_interview_worklist(queue: list) -> list:
    """queue에서 aide_interview_needed=True인 배만 추려 반환(세션 픽업용, 읽기전용 · 큐 뮤테이션 0)."""
    return [s for s in queue if s.get("aide_interview_needed")]


def print_interview_worklist(queue_path: str | None = None) -> None:
    """CLI 진입점(--interview-worklist) — parked-interview 배 목록을 마크다운 표로 stdout 출력.
    run_once()와 독립 경로(선별·게이트·park 전부 미가동) · 큐 읽기전용."""
    queue_path = queue_path or DEFAULT_QUEUE_PATH
    queue = _load_queue(queue_path)
    items = parked_interview_worklist(queue)
    print(f"## 🧭 러너 모호 배(GM 인터뷰 대기) — {len(items)}척\n")
    if not items:
        print("(없음 — parked-interview 배 없음)")
        return
    print("| 배 | 담당 | 제목 | 모호 사유 |")
    print("|---|---|---|---|")
    for s in items:
        print(
            f"| `{s.get('task_id')}` | {s.get('clevel', '').upper()} | "
            f"{s.get('title', '')} | {s.get('aide_interview_reason', '')} |"
        )


# ── 부팅 자율 진행 후보(읽기전용) ──────────────────────────────────────────────
# 배경: GM 2026-07-23 "부팅되자마자 항로 확인해서 웰리 판단하에 자율 진행".
# 예약 러너(headless 07:30)와 **완전히 같은** 선별·모호성 게이트를 쓰되, 어떤 파일도
# 쓰지 않는다(큐 park 미기록·쿨다운 미기록·로그 미기록·claude 미호출). 실제 실행은
# 이 함수를 부른 대화형 C-Level 세션이 자기 손으로 한다 — 그래서 게이트는 한 곳(러너)
# 뿐이고, 부팅 경로가 우회로가 되지 않는다(헌법 불변원리 1: 한 진실 = 한 곳).
def boot_candidate(
    clevel: str = "cto",
    queue_path: str | None = None,
    registry_path: str | None = None,
    state_path: str | None = None,
) -> dict:
    """
    부팅 직후 자율 진행할 배 1척을 판정한다(읽기전용).
    반환: {clevel, ship(dict|None), verdict("go"|"park"|"none"), reasons(list[str])}
      - go   : 가역·저위험·모호성 없음 → 세션이 되묻지 말고 바로 착수
      - park : 후보는 있으나 모호 → 착수 금지, GM 인터뷰 대상으로 보고만
      - none : 후보 0건 → 대기
    """
    queue = _load_queue(queue_path or DEFAULT_QUEUE_PATH)
    registry = load_registry(registry_path)
    state = _load_state(state_path or DEFAULT_STATE_PATH)
    ship = select_one_low_risk_ship(
        clevel, queue, registry=registry, cooldown_task_ids=_active_cooldown_ids(state)
    )
    if ship is None:
        return {
            "clevel": clevel, "ship": None, "verdict": "none",
            "reasons": ["가역·저위험 후보 0건(비가역·타clevel·완료·쿨다운·모호park 제외 후)"],
        }
    ambiguity = is_ambiguous(ship)
    return {
        "clevel": clevel,
        "ship": ship,
        "verdict": "park" if ambiguity["ambiguous"] else "go",
        "reasons": ambiguity["reasons"],
    }


def print_boot_candidate(clevel: str = "cto") -> None:
    """CLI 진입점(--boot-candidate) — 부팅 세션이 읽고 바로 행동할 수 있게 마크다운으로 출력."""
    result = boot_candidate(clevel)
    ship = result["ship"]
    print(f"## 🚀 부팅 자율 진행 후보 — {clevel.upper()}\n")
    if ship is None:
        print(f"판정: **대기** — {result['reasons'][0]}")
        return
    print("| 항목 | 값 |")
    print("|---|---|")
    print(f"| 배 | `{ship.get('task_id')}` (ship_no {ship.get('ship_no')}) |")
    print(f"| 난이도 | {ship.get('priority')} |")
    print(f"| 제목 | {ship.get('title', '')} |")
    verdict_label = {"go": "✅ 착수(되묻지 말 것)", "park": "⚓ 착수 금지 — GM 인터뷰 필요"}
    print(f"| 판정 | {verdict_label.get(result['verdict'], result['verdict'])} |")
    if result["reasons"]:
        print(f"| 사유 | {'; '.join(result['reasons'])} |")


# ── 아침 집계(읽기전용) ────────────────────────────────────────────────────────
# 배경: 약속 L20 — 웰리는 아침에 6역할이 올린 배를 모아 무엇을 어떤 순서로 풀지
# 판단해야 하는데, 모아 보는 창이 없었다(부팅 때 본인 배만 봄). run_once()·
# run_cycle()의 선별·게이트·park 로직은 전혀 건드리지 않는다 — 순수 읽기전용
# 집계일 뿐, 큐·상태·로그 어느 것도 쓰지 않는다(boot_candidate와 같은 성격).
def morning_intake(queue_path: str | None = None, today: str | None = None) -> dict:
    """
    부작용 0(읽기전용) — status/_queue.json에서 오늘(로컬 날짜) enqueued_at인 배 중
    PENDING·IN_PROGRESS만 골라 역할별 판정 결과를 담는다.
      - 기계 자동발행 배 제외: kpi_collector._is_machine_ship()을 그대로 재사용
        (판정 로직 복제 금지 · 약속 L01).
      - 비가역 신호 판정: welly_sweep_classifier.GATE_KEYWORDS + IRREVERSIBLE_KEYWORDS
        (결제·보안·금지·전략·공식값 + 삭제·외부·발송·전송·배포 등)를 title+note에서
        스캔 — 새 키워드 목록을 여기 새로 박지 않고 단일 지점을 재사용한다.
    실패(큐 파일 없음·파싱 실패·재사용 대상 import 실패)는 fail-open —
    {"ok": False, "reason": ...}만 반환하고 예외를 던지지 않는다(부팅을 막지 않음).
    반환: {"ok": bool, "reason": str, "today": str, "ships": list[dict]}
      ships 각 항목: clevel, nick, ship_no, title, priority, next, irreversible(bool),
      irreversible_keyword(str|None).
    """
    queue_path = queue_path or DEFAULT_QUEUE_PATH
    today = today or datetime.now().date().isoformat()
    empty = {"ok": False, "reason": "", "today": today, "ships": []}
    try:
        queue = _load_queue(queue_path)
    except Exception as e:  # noqa: BLE001 — fail-open(파일 없음·파싱 실패 등)
        empty["reason"] = f"큐 로드 실패 — fail-open: {type(e).__name__}: {e}"
        return empty

    try:
        from kpi_collector import _is_machine_ship  # noqa: E402  (지연 import — 판정 재사용, 약속 L01)
        from welly_sweep_classifier import GATE_KEYWORDS, IRREVERSIBLE_KEYWORDS, _scan_keywords  # noqa: E402
    except Exception as e:  # noqa: BLE001 — fail-open(재사용 대상 모듈 import 실패)
        empty["reason"] = f"판정 재사용 모듈 import 실패 — fail-open: {type(e).__name__}: {e}"
        return empty

    gate_scan_keywords = GATE_KEYWORDS + IRREVERSIBLE_KEYWORDS
    role_order = list(CLEVEL_NICKS.keys())

    try:
        ships = []
        for ship in queue:
            if not isinstance(ship, dict):
                continue
            if ship.get("enqueued_at") != today:
                continue
            if ship.get("status") not in ("PENDING", "IN_PROGRESS"):
                continue
            if _is_machine_ship(ship):
                continue
            clevel = ship.get("clevel") or ""
            text = f"{ship.get('title', '') or ''} {ship.get('note', '') or ''}"
            hit = _scan_keywords(text, gate_scan_keywords)
            next_raw = (ship.get("next") or "").strip()
            ships.append({
                "clevel": clevel,
                "nick": CLEVEL_NICKS.get(clevel, clevel.upper() if clevel else "?"),
                "ship_no": ship.get("ship_no"),
                "title": ship.get("title", ""),
                "priority": ship.get("priority") or "—",
                "next": next_raw[:40] if next_raw else "—",
                "irreversible": bool(hit),
                "irreversible_keyword": hit,
            })
        ships.sort(key=lambda s: role_order.index(s["clevel"]) if s["clevel"] in role_order else len(role_order))
    except Exception as e:  # noqa: BLE001 — fail-open(예상 못 한 개별 배 데이터 결함)
        empty["reason"] = f"집계 중 오류 — fail-open: {type(e).__name__}: {e}"
        return empty

    return {"ok": True, "reason": "", "today": today, "ships": ships}


def print_morning_intake(queue_path: str | None = None) -> None:
    """CLI 진입점(--morning-intake) — 오늘 새로 올라온 배(전 역할)를 역할별 표로 출력
    (읽기전용 · 큐·상태·로그 무기록 · 실패해도 경고 1줄로 정상 종료 · fail-open)."""
    result = morning_intake(queue_path)
    print(f"## 🧭 웰리 아침 집계 — 오늘({result['today']}) 새로 올라온 배\n")
    if not result["ok"]:
        print(f"⚠️ {result['reason']}")
        return

    ships = result["ships"]
    if not ships:
        print("(오늘 새로 올라온 배 없음)")
        return

    print("| 역할 | 배 | 제목 | 무게 | 다음 한 걸음 |")
    print("|---|---|---|---|---|")
    for s in ships:
        print(f"| {s['nick']} | {s['ship_no']} | {s['title']} | {s['priority']} | {s['next']} |")

    counts: dict[str, int] = {}
    for s in ships:
        counts[s["nick"]] = counts.get(s["nick"], 0) + 1
    dist = " · ".join(f"{nick} {n}척" for nick, n in counts.items())
    n_irr = sum(1 for s in ships if s["irreversible"])
    n_rev = len(ships) - n_irr
    print(f"\n1. 오늘 올라온 배 총 {len(ships)}척 ({dist})")
    print(f"2. 가역 {n_rev}척 · 비가역 신호 {n_irr}척"
          + (f" ({', '.join(sorted({s['irreversible_keyword'] for s in ships if s['irreversible']}))})" if n_irr else ""))


def _collect_parked_task_ids(queue_path: str) -> list[str]:
    queue = _load_queue(queue_path)
    return [s.get("task_id") for s in parked_interview_worklist(queue) if s.get("task_id")]


def build_ambiguous_ping_text(parked_count: int) -> str:
    return f"🧭 러너 모호 배 {parked_count}건 — 세션 열어 인터뷰 필요"


def _load_ping_state(path: str) -> dict:
    if not os.path.exists(path):
        return {"pinged_task_ids": [], "sent_dates": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_ping_state(state: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _ping_decision(parked_task_ids: list[str], state: dict, now: datetime | None = None,
                    daily_cap: int = AMBIGUOUS_PING_DAILY_CAP) -> dict:
    """PURE — dedup(신규 parked 배 있을 때만) + 하루 cap 판정. 반환: {should_send, new_task_ids, reason}."""
    now = now or datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    pinged = set(state.get("pinged_task_ids", []))
    new_ids = [t for t in parked_task_ids if t not in pinged]
    if not new_ids:
        return {"should_send": False, "new_task_ids": [], "reason": "dedup — 신규 parked 배 없음(이미 전부 핑 보냄)"}
    sent_today = state.get("sent_dates", {}).get(today, 0)
    if sent_today >= daily_cap:
        return {
            "should_send": False, "new_task_ids": new_ids,
            "reason": f"하루 cap({daily_cap}회) 도달 — 오늘 추가 핑 보류",
        }
    return {"should_send": True, "new_task_ids": new_ids, "reason": f"신규 parked {len(new_ids)}건 — 핑 대상"}


def maybe_send_ambiguous_ping(parked_task_ids: list[str], state_path: str | None = None,
                               notifier=None, now: datetime | None = None,
                               daily_cap: int = AMBIGUOUS_PING_DAILY_CAP) -> dict:
    """
    parked 배 목록을 보고 dedup+하루cap을 통과하면 notifier.send(text)로 핑을 보낸다.
    notifier=None이면 실전송 없이 payload(text)만 반환한다(테스트·dry-run 안전장치 — 상태파일도
    건드리지 않음). notifier가 주어지고 should_send가 True일 때만 상태(dedup·cap)를 저장한다.
    반환: {"sent": bool, "text": str, "reason": str}
    """
    state_path = state_path or DEFAULT_PING_STATE_PATH
    now = now or datetime.now(timezone.utc)
    state = _load_ping_state(state_path)
    decision = _ping_decision(parked_task_ids, state, now=now, daily_cap=daily_cap)
    text = build_ambiguous_ping_text(len(parked_task_ids))

    if not decision["should_send"]:
        return {"sent": False, "text": text, "reason": decision["reason"]}
    if notifier is None:
        return {"sent": False, "text": text, "reason": "notifier 미주입 — payload 미리보기만(실전송 없음)"}

    send_result = notifier.send(text)
    today = now.strftime("%Y-%m-%d")
    state["pinged_task_ids"] = sorted(set(state.get("pinged_task_ids", [])) | set(decision["new_task_ids"]))
    state.setdefault("sent_dates", {})
    state["sent_dates"][today] = state["sent_dates"].get(today, 0) + 1
    _save_ping_state(state, state_path)
    return {"sent": True, "text": text, "reason": decision["reason"], "api_result": send_result}


def _ping_live() -> bool:
    return os.environ.get(PING_LIVE_ENV_VAR, "0") == "1"


# ── 증분2: 자동 검수 — 세션 stdout 구조화 검증 결과 파싱(로드맵 1단계) ──
# 정본: docs/superpowers/specs/2026-07-14-welly-runner-all-clevel-autodrive-design.md (증분2 §A).
# 위임 세션이 검증을 마친 뒤 stdout에 VERIFY_MARKER로 시작하는 JSON 한 줄을 남기면
# (build_orchestration_prompt가 지시), 러너가 그 줄을 파싱해 자동 검수 판정에 반영한다.
# 마커 줄이 없거나 파싱 불가면 "검수 결과 애매"로 보고 park한다 —
# ★비협상 park 원칙★: 검수 결과가 애매하면 완료를 신뢰(자동 기록)하지 않고 사람 확인 대기.
VERIFY_MARKER = "WELLY_VERIFY:"
# 스크립트/백엔드류: 로그·테스트·exit code로 완전 자동 검수 가능(정직 꼬리표).
SCRIPT_HONESTY_TAG = "자동 검수 통과 — 실행 로그/테스트로 증명(스크립트류 완전 자동 검수)"
# 프론트/페이지류: 렌더 실측(200·콘솔0·셀렉터)까지만 자동, 디자인·톤 적합성은 자동 불가.
FRONTEND_HONESTY_TAG = (
    "자동 렌더 확인(200·콘솔0·셀렉터 존재) — 디자인·카피 톤 적합성은 미검수(사람 확인 필요)"
)
_FRONTEND_KINDS = ("frontend", "front", "page", "ui")

# ── 증분2 로드맵2: 러너 독립 렌더 실측 ──
# 정본: docs/superpowers/specs/2026-07-14-welly-runner-all-clevel-autodrive-design.md (증분2 로드맵2).
# frontend 배는 세션 자기보고(WELLY_VERIFY)만 믿지 않고, 러너가 라이브 URL을 직접
# headless 렌더해 200·콘솔0·셀렉터를 재확인한다. 세션 주장과 실제 렌더가 어긋나면
# 완료를 신뢰하지 않고 ambiguous→park(사람 확인)로 강등한다.
# ★게이트 기본 OFF★ — RUNNER_RENDER_VERIFY=1일 때만 render_verify_url이 호출된다.
RENDER_VERIFY_ENV_VAR = "RUNNER_RENDER_VERIFY"
DEFAULT_EVIDENCE_DIR = os.path.join(_SCRIPTS_DIR, "poc-evidence")


def parse_verification_result(stdout: str | None) -> dict:
    """
    PURE — 위임 세션 stdout에서 VERIFY_MARKER로 시작하는 마지막 JSON 한 줄을 파싱한다.
    반환 dict 키: found(bool), verified(bool|None), kind(str|None), evidence(str),
    subjective_uncertain(bool), url(str), raw(str), parse_error(str|None).
    url = frontend일 때 세션이 검증한 라이브 URL(없으면 "") — 러너 독립 렌더(로드맵2) 대상.
    마커 미검출 → found=False. 마커는 있으나 JSON 파싱 실패/객체 아님/verified 비불리언 →
    found=True + parse_error 또는 verified=None(둘 다 verdict에서 '애매'로 취급).
    여러 줄이면 마지막 마커 줄을 채택(세션이 재출력했을 때 최종본 우선).
    """
    base = {
        "found": False, "verified": None, "kind": None, "evidence": "",
        "subjective_uncertain": False, "url": "", "raw": "", "parse_error": None,
    }
    if not stdout:
        return base
    marker_payload = None
    for line in stdout.splitlines():
        idx = line.find(VERIFY_MARKER)
        if idx != -1:
            marker_payload = line[idx + len(VERIFY_MARKER):].strip()  # 마지막 것이 이김
    if marker_payload is None:
        return base
    base["found"] = True
    base["raw"] = marker_payload
    try:
        data = json.loads(marker_payload)
    except (ValueError, TypeError) as e:
        base["parse_error"] = f"{type(e).__name__}: {e}"
        return base
    if not isinstance(data, dict):
        base["parse_error"] = "JSON이 객체(dict)가 아님"
        return base
    v = data.get("verified")
    base["verified"] = v if isinstance(v, bool) else None
    base["kind"] = data.get("kind")
    base["evidence"] = str(data.get("evidence", ""))
    base["subjective_uncertain"] = bool(data.get("subjective_uncertain", False))
    base["url"] = str(data.get("url", "") or "")
    return base


def build_auto_review_verdict(parsed: dict, committed: bool) -> dict:
    """
    PURE — 파싱된 검증 결과 + 커밋 발생 여부로 자동 검수 판정을 만든다.
    반환: {passed(bool), ambiguous(bool), honesty_tag(str), reason(str)}.
      - passed=True  : 신뢰 가능한 자동 검수 통과(완료 신뢰 OK).
      - ambiguous=True: 검증 결과 미출력/파싱불가/verified 불명 → 완료 신뢰 금지 → park.
      - passed=False·ambiguous=False: 명확한 실패(검증 false) 또는 커밋 없음 → 쿨다운(park 아님).
    ★비협상 원칙★: 'ambiguous'는 절대 자동 기록으로 신뢰하지 않는다.
    """
    if not committed:
        return {
            "passed": False, "ambiguous": False, "honesty_tag": "",
            "reason": "커밋 없음 — 산출물 미생성(자동 검수 대상 아님)",
        }
    if not parsed.get("found") or parsed.get("parse_error") or parsed.get("verified") is None:
        return {
            "passed": False, "ambiguous": True,
            "honesty_tag": "검증 결과 미출력·파싱 불가 — 자동 검수 불가",
            "reason": "세션이 구조화 검증 결과(WELLY_VERIFY JSON)를 남기지 않음 → 검수 애매 → park",
        }
    if parsed["verified"] is False:
        return {
            "passed": False, "ambiguous": False,
            "honesty_tag": "자동 검수 실패 — 세션이 검증 실패 보고",
            "reason": f"검증 실패: {parsed.get('evidence', '')[:200]}",
        }
    kind = (parsed.get("kind") or "").strip().lower()
    tag = FRONTEND_HONESTY_TAG if kind in _FRONTEND_KINDS else SCRIPT_HONESTY_TAG
    if parsed.get("subjective_uncertain"):
        tag += " · 주관 판단 여지 표기됨(사람 확인)"
    return {
        "passed": True, "ambiguous": False, "honesty_tag": tag,
        "reason": f"자동 검수 통과: {parsed.get('evidence', '')[:200]}",
    }


def audit_completion_in_queue(queue_path: str, task_id: str) -> dict:
    """
    사후 감사(로드맵 3단계 · thin) — 세션이 선언한 완료가 실제 큐에 반영됐는지 가볍게 대조한다.
    러너는 직접 기록하지 않는다(세션이 clevel_post_action.py로 기록) — 여기선 반영 여부만 확인.
    반환: {reflected(bool|None), status(str|None), reason(str)}.
      - ship이 큐에서 사라짐 → reflected=True(아카이브=완료 처리로 간주).
      - status가 DONE/완료 계열 → reflected=True.
      - PENDING/IN_PROGRESS로 잔존 → reflected=False(선언≠반영 불일치 → 경고 대상).
    """
    try:
        queue = _load_queue(queue_path)
    except Exception as e:  # noqa: BLE001
        return {"reflected": None, "status": None, "reason": f"큐 로드 실패: {type(e).__name__}"}
    for ship in queue:
        if ship.get("task_id") == task_id:
            status = (ship.get("status") or "").strip().upper()
            done = status in ("DONE", "완료", "COMPLETE", "COMPLETED")
            return {
                "reflected": done, "status": ship.get("status"),
                "reason": "완료로 반영됨" if done else "큐에 활성 상태로 잔존 — 선언≠반영 불일치",
            }
    return {"reflected": True, "status": None, "reason": "큐에서 제거됨(아카이브=완료 처리로 간주)"}


def _url_slug(url: str) -> str:
    """URL을 스크린샷 파일명용 안전 슬러그로 변환(index/타임스탬프 대신 URL 기반)."""
    slug = "".join(c if c.isalnum() else "_" for c in (url or "render"))
    slug = slug.strip("_") or "render"
    return slug[:120]


def render_verify_url(url, required_selectors=None, evidence_dir=None, timeout_ms=20000) -> dict:
    """
    ★로드맵2 핵심★ — 러너가 프론트 배의 라이브 URL을 세션과 독립적으로 headless 렌더해
    실측 재확인한다(playwright는 함수 내부 지연 import — 단위테스트는 브라우저 없이 돈다).

    headless chromium으로 url 렌더 → main response HTTP status 취득 + 콘솔 error(type=="error")만
    수집 + required_selectors 각 존재 여부 확인 + 스크린샷을 evidence_dir(기본 poc-evidence)에
    URL 슬러그 파일명으로 저장.

    반환: {ok, http_status, console_errors, selectors_found, screenshot, error}.
      ok = (http_status==200) and (모든 required_selectors 발견).
      ★콘솔에러는 참고 정보로만 수집한다(park 트리거 아님).★ 양성 라이브 페이지도 CORS·
      서드파티·analytics 등으로 흔히 콘솔 error를 뱉어(실측: 문의 페이지 200인데 CORS 5건),
      이를 하드 실패로 잡으면 정상 완료된 프론트 배가 무더기로 오탐 park된다. 하드 신호=
      HTTP status(페이지가 안 떴나)·셀렉터(기대 콘텐츠가 렌더됐나)만 park를 좌우한다.

    ★어떤 예외도 밖으로 던지지 않는다★ — 렌더 인프라 실패(브라우저 미기동·타임아웃·네트워크)는
    error 필드에 사유를 담아 반환한다(그때 나머지는 None/빈값). 이 "인프라 실패"(error 있음)와
    "렌더는 됐으나 200 아님/콘솔에러/셀렉터 없음"(error None + ok False)은 fold에서 다르게 취급된다.
    """
    required_selectors = list(required_selectors or [])
    evidence_dir = evidence_dir or DEFAULT_EVIDENCE_DIR
    base_fail = {
        "ok": False, "http_status": None, "console_errors": [],
        "selectors_found": {}, "screenshot": None, "error": None,
    }
    if not url:
        return {**base_fail, "error": "url 비어있음 — 렌더 대상 없음"}
    try:
        from playwright.sync_api import sync_playwright  # noqa: E402  (지연 import — 브라우저 없이 단위테스트 가능)
    except Exception as e:  # noqa: BLE001
        return {**base_fail, "error": f"playwright import 실패: {type(e).__name__}: {e}"}

    console_errors: list[str] = []
    http_status = None
    selectors_found: dict = {}
    screenshot_path = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(
                    viewport={"width": 1280, "height": 900}, ignore_https_errors=True,
                )
                page = ctx.new_page()
                page.on(
                    "console",
                    lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
                )
                response = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                http_status = response.status if response is not None else None
                for sel in required_selectors:
                    try:
                        selectors_found[sel] = page.query_selector(sel) is not None
                    except Exception:  # noqa: BLE001
                        selectors_found[sel] = False
                try:
                    os.makedirs(evidence_dir, exist_ok=True)
                    screenshot_path = os.path.join(evidence_dir, f"render_verify_{_url_slug(url)}.png")
                    page.screenshot(path=screenshot_path)
                except Exception:  # noqa: BLE001
                    screenshot_path = None
            finally:
                browser.close()
    except Exception as e:  # noqa: BLE001  — 렌더 인프라 실패는 예외로 던지지 않고 error로 반환
        return {**base_fail, "error": f"렌더 실패: {type(e).__name__}: {e}"}

    all_selectors_ok = all(selectors_found.get(s) for s in required_selectors)
    # 콘솔에러는 park 트리거 아님(양성 페이지 CORS 등 노이즈 오탐 방지) — 하드 신호만 ok 좌우.
    ok = (http_status == 200) and all_selectors_ok
    return {
        "ok": ok, "http_status": http_status, "console_errors": console_errors,
        "selectors_found": selectors_found, "screenshot": screenshot_path, "error": None,
    }


def fold_render_into_verdict(verdict: dict, verify_parsed: dict, render_result: dict | None,
                             render_enabled: bool) -> dict:
    """
    PURE(playwright 호출 없음 — render_result를 인자로 받음) — 러너 독립 렌더 결과를 자동 검수
    verdict에 접어 넣는다. 원 verdict를 복사해 갱신 후 반환(원본 불변).

    ★비협상 원칙★ 세션이 성공 보고했는데 러너 독립 렌더가 실패(불일치)하면 절대 자동 완료로
    신뢰하지 않고 ambiguous→park로 강등한다.

    분기:
      - render_enabled False → verdict 그대로(변경 0).
      - verdict가 애초에 passed 아님 → 그대로(렌더 검수 대상 아님).
      - kind가 frontend 계열 아님 또는 url 없음 → 그대로 + honesty_tag에 미수행 사유 표기.
      - render_result 인프라 실패(error 있음) → passed 유지 + honesty_tag에 인프라 실패 표기(park 아님).
      - render_result.ok True → passed 유지 + honesty_tag에 러너 독립 렌더 재확인 통과 표기.
      - render_result.ok False & error None(불일치) → passed=False·ambiguous=True로 강등(park), reason 갱신.
    """
    v = dict(verdict)
    if not render_enabled:
        return v
    if not v.get("passed"):
        return v

    kind = (verify_parsed.get("kind") or "").strip().lower()
    url = (verify_parsed.get("url") or "").strip()
    if kind not in _FRONTEND_KINDS or not url:
        v["honesty_tag"] = (v.get("honesty_tag") or "") + " · 독립 렌더 미수행(비프론트/URL없음)"
        return v

    render_result = render_result or {}
    if render_result.get("error"):
        v["honesty_tag"] = (v.get("honesty_tag") or "") + \
            " · 독립 렌더 미수행(렌더 인프라 실패, 세션 자기보고만)"
        return v

    n_console = len(render_result.get("console_errors") or [])
    if render_result.get("ok"):
        tag = " · 러너 독립 렌더 재확인 통과(200·셀렉터 존재)"
        if n_console:
            tag += f" · 콘솔에러 {n_console}건(참고·차단 아님)"
        v["honesty_tag"] = (v.get("honesty_tag") or "") + tag
        return v

    # 렌더는 됐으나 하드 조건 미달(error None + ok False) = 세션 주장과 불일치 → 강등·park.
    # ★콘솔에러는 park 트리거 아님★ — 하드 신호(status!=200 또는 셀렉터 누락)만 불일치로 본다.
    status = render_result.get("http_status")
    v["passed"] = False
    v["ambiguous"] = True
    v["honesty_tag"] = (
        f"세션은 성공 보고했으나 러너 독립 렌더 불일치(status={status}·셀렉터 "
        f"{render_result.get('selectors_found')}) — 완료 신뢰 금지·park"
    )
    v["reason"] = (
        f"러너 독립 렌더 재확인 불일치(status={status}·셀렉터 {render_result.get('selectors_found')}"
        f"·콘솔에러 {n_console}건[참고]) — 세션 성공 주장과 어긋나 자동 완료 신뢰 금지, park"
    )
    return v


def build_orchestration_prompt(ship: dict, clevel: str = "cto", nick: str = "시토") -> str:
    """
    선택된 배 1척을 실행할 headless 세션에 줄 '웰리 오케스트레이션' 프롬프트를 조립한다.
    재귀 폭주 방지 지시를 프롬프트 레벨에서도 명시(코드 가드 WELLY_AUTO_RUNNER_ACTIVE와 이중 방어).
    """
    task_id = ship.get("task_id", "")
    title = ship.get("title", "")
    note = ship.get("note", "")
    priority = ship.get("priority", "")

    return (
        f"너는 웰페리온 AI CEO 웰리다. 아래 배 1척을 담당 C-Level({nick}, {clevel})의 "
        f"도메인 방식으로 실행하라. 이 세션은 예약 러너(welly_auto_runner.py)가 자동으로 "
        f"띄운 것이다.\n\n"
        f"배 ID: {task_id}\n"
        f"난이도: {priority}\n"
        f"제목: {title}\n"
        f"메모: {note}\n\n"
        "절차:\n"
        "1) 이 배를 도메인 방식으로 실행한다(가역 작업만 — 발행·배포·삭제·외부전송·결제·보안·"
        "전략·공식값·라이브 GAS/시트 쓰기는 절대 실행하지 말고 즉시 중단·보고).\n"
        "2) 실행 결과를 검증한다(프론트 변경이면 시크릿 크롬 라이브 렌더로 실측, 스크립트면 "
        "실행 로그/테스트로 증명). 검증을 마친 뒤 반드시 stdout에 아래 형식의 구조화 검증 결과를 "
        "정확히 한 줄로 남겨라 — 러너가 이 줄을 파싱해 자동 검수한다(줄이 없거나 증거 없으면 "
        "완료로 신뢰되지 않고 park된다):\n"
        f"   {VERIFY_MARKER} "
        '{"verified": true, "kind": "script|frontend", '
        '"evidence": "<파일·로그·스크린샷 경로/요약>", "url": "<검증한 라이브 URL>", '
        '"subjective_uncertain": false}\n'
        "   - verified: 검증 성공 여부(불리언). 증거 없이 true 금지.\n"
        "   - kind: 스크립트/백엔드=script, 프론트/페이지=frontend.\n"
        "   - url: frontend면 네가 검증한 라이브 URL을 반드시 담아라(러너가 이 URL을 독립적으로 "
        "재렌더해 200·콘솔0·셀렉터를 재확인한다 — 네 주장과 어긋나면 완료가 park된다). "
        "스크립트류는 url 불필요(빈 문자열 또는 생략).\n"
        "   - frontend는 렌더 실측(200·콘솔0·셀렉터)까지만 자동 검수 대상이며, 디자인·톤 적합성은 "
        "subjective_uncertain=true로 표기해 사람 확인 몫으로 남긴다.\n"
        "3) 반드시 네가 만든/바꾼 파일만 명시 경로로 git add 후 커밋한다. "
        "git add -A · git add . · git commit -a는 절대 금지 — 워킹트리에 이미 있던 "
        "무관한 미커밋 작업(다른 세션이 남긴 코드·콘텐츠)까지 네 커밋에 쓸어담는 사고를 "
        "막기 위함이다. 커밋 메시지 마지막 두 줄:\n"
        "   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>\n"
        "   Claude-Session: https://claude.ai/code/session_01VXU2K3Rd1oemGiF6E2mE6L\n"
        "4) wellperion-agents/scripts/clevel_post_action.py로 status/_queue.json에 완료를 "
        f"기록한다(--clevel {clevel.upper()} --task-id {task_id} --status 완료 "
        "--artifact-url <증거> --next <다음 한 줄 또는 --terminal>).\n\n"
        "절대 규칙(재귀 폭주 방지): 이 세션에서 welly_auto_runner.py를 실행·수정·재호출하거나 "
        "예약 Claude 러너를 새로 기동하지 마라. 위임 범위를 벗어나는 판단·전략·공식값 변경이 "
        "필요하면 실행을 멈추고 GM 결재로 넘겨라.\n"
        "완료 게이트: 아티팩트(파일·로그·스크린샷)와 라이브 링크(가능하면 시크릿 크롬 실측) "
        "없는 완료 보고는 금지한다."
    )


def _is_live() -> bool:
    return os.environ.get(LIVE_ENV_VAR, "0") == "1"


def _guard_active() -> bool:
    return os.environ.get(GUARD_ENV_VAR, "0") == "1"


def _render_verify_enabled() -> bool:
    """로드맵2 러너 독립 렌더 게이트 — 기본 OFF, RUNNER_RENDER_VERIFY=1일 때만 True."""
    return os.environ.get(RENDER_VERIFY_ENV_VAR, "0") == "1"


# ── 클린트리 가드: 상시 자동생성 노이즈 allowlist ──
# 근거(2026-07-13 실측 `git status --porcelain`): status/ 하위 json·jsonl·briefs·
# morning_plans·_memory_snapshots, gm_profile.md, northstar_*, self_review_log*,
# learning_*, telegram_bot의 heartbeat·cache, IG 리뷰 미리보기 png, logs/ 등은
# 자동화가 상시 건드리는 정상 노이즈다. 이 목록 밖의 *.py·*.html·*.js·docs/*.md·
# instagram/*.md 등은 사람이 방치한 진짜 미커밋 작업으로 간주해 가드를 발동시킨다.
NOISE_PATH_PATTERNS = (
    "status/*.json",
    "status/*.jsonl",
    "status/briefs/*",
    "status/morning_plans/*",
    "status/_memory_snapshots/*",
    "status/gm_profile.md",
    "status/northstar_*",
    "status/self_review_log*",
    "status/learning_*",
    "*.log",
    "logs",
    "logs/*",
    "*heartbeat*",
    "*cache*",
    "*.finance_cache*",
    "*preview_*.png",
    "3. 웰페리온 가이드/status/*",
    "3. 웰페리온 가이드/cmo/review/*",
)


def _is_noise_path(path: str) -> bool:
    """git status --porcelain 한 줄의 경로가 상시 자동생성 노이즈 allowlist에 걸리는지."""
    norm = path.replace("\\", "/").strip().strip('"')
    return any(fnmatch.fnmatch(norm, pattern) for pattern in NOISE_PATH_PATTERNS)


def _parse_porcelain_paths(porcelain_stdout: str) -> list[str]:
    paths = []
    for line in porcelain_stdout.splitlines():
        if not line.strip():
            continue
        # 포맷: "XY <path>" (rename 시 "XY <old> -> <new>")
        entry = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        entry = entry.strip().strip('"')
        if entry:
            paths.append(entry)
    return paths


def working_tree_guard(repo_root: str | None = None) -> dict:
    """
    무인(RUNNER_LIVE) 실행 직전 워킹트리를 점검한다.
    상시 자동생성 노이즈(NOISE_PATH_PATTERNS)는 통과시키고, allowlist 밖 진짜 미커밋
    작업(real_work_files)은 "베이스라인 foreign 파일"로만 보고한다 — 2026-07-20 재설계로
    이 함수 자체는 더 이상 실행을 막지 않는다(호출측 run_once()가 이 목록을 기록해 두었다가
    LIVE 커밋 뒤 실제로 그 파일이 커밋에 섞였는지 사후 대조한다 — _check_sweep_violation 참고).
    blocked=True는 오직 git status 자체가 실패한 경우(안전 확인 불가)에만 발생한다(fail-closed).

    반환 dict 키: blocked(bool, git_error일 때만 True), git_error(bool), dirty_files(list[str],
    전체), real_work_files(list[str], 노이즈 제외 진짜 미커밋 작업 = 베이스라인 foreign 목록), reason(str).
    """
    repo_root = repo_root or _PROJECT_ROOT
    try:
        out = subprocess.run(
            # --untracked-files=all: 미추적 디렉토리를 하나로 뭉치지 않고 파일 단위로 펼쳐야
            # allowlist(파일 패턴)가 정확히 매칭된다(디렉토리째 뭉치면 과탐/누락 둘 다 생김).
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
        )
    except Exception as e:  # noqa: BLE001
        return {
            "blocked": True, "git_error": True, "dirty_files": [], "real_work_files": [],
            "reason": f"git status 실행 실패 — 안전 우선 차단: {type(e).__name__}: {e}",
        }
    if out.returncode != 0:
        return {
            "blocked": True, "git_error": True, "dirty_files": [], "real_work_files": [],
            "reason": f"git status 실패(rc={out.returncode}) — 안전 우선 차단: {out.stderr.strip()[:300]}",
        }

    dirty_files = _parse_porcelain_paths(out.stdout)
    real_work_files = [p for p in dirty_files if not _is_noise_path(p)]
    has_foreign = bool(real_work_files)
    reason = (
        f"워킹트리에 노이즈 allowlist 밖 미커밋 작업 {len(real_work_files)}건 — "
        f"베이스라인 foreign 파일로 기록(차단하지 않음, 커밋 뒤 사후 대조): "
        f"{', '.join(real_work_files[:10])}"
        if has_foreign else
        f"워킹트리 클린(노이즈 {len(dirty_files)}건 또는 완전 클린)"
    )
    return {
        "blocked": False, "git_error": False, "dirty_files": dirty_files,
        "real_work_files": real_work_files, "reason": reason,
    }


def _load_queue(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {"cooldown": {}, "run_count": 0}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _active_cooldown_ids(state: dict, now: datetime | None = None) -> set:
    now = now or datetime.now(timezone.utc)
    ids = set()
    for task_id, info in state.get("cooldown", {}).items():
        until = info.get("until")
        try:
            until_dt = datetime.fromisoformat(until)
        except (TypeError, ValueError):
            continue
        if until_dt > now:
            ids.add(task_id)
    return ids


def _mark_cooldown(state: dict, task_id: str, reason: str, hours: int = COOLDOWN_HOURS,
                    now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    until = (now + timedelta(hours=hours)).isoformat()
    state.setdefault("cooldown", {})[task_id] = {"until": until, "reason": reason}


def _git_head(repo_root: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _commit_changed_files(repo_root: str, before: str | None, after: str | None) -> list[str]:
    """
    LIVE 실행 후 best-effort 커밋 범위 점검: before→after 커밋 사이 변경 파일 목록을 반환한다
    (선언 범위 밖 파일 혼입 여부를 로그로 남겨 사후 감사 가능하게 함 — 완벽 판정 아닌 가시성).
    """
    if not before or not after or before == after:
        return []
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", before, after],
            cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
        )
        if out.returncode != 0:
            return []
        return [line.strip() for line in out.stdout.splitlines() if line.strip()]
    except Exception:  # noqa: BLE001
        return []


def _check_sweep_violation(baseline_foreign_files: list[str], changed_files: list[str]) -> list[str]:
    """
    PURE — LIVE 커밋(changed_files)에 베이스라인 foreign 파일(세션 시작 전부터 이미
    미커밋 상태였던, allowlist 밖 무관 파일)이 섞였는지 대조한다. 교집합 = 확정 스코프
    이탈("이 세션이 남의 미커밋 작업을 자기 커밋에 쓸어담았다"). 정렬된 리스트 반환(빈 리스트=위반 없음).
    """
    return sorted(set(baseline_foreign_files) & set(changed_files))


def _attempt_safe_revert(repo_root: str, commit: str) -> dict:
    """
    스코프 이탈 커밋 감지 시 안전 되돌림 시도. git revert는 새 커밋을 만들 뿐 히스토리를
    지우지 않으므로 파괴적 명령이 아니다(reset --hard·강제 푸시 금지 원칙과 무관).
    충돌 등으로 revert 자체가 실패하면 즉시 --abort로 중간상태를 방치하지 않는다
    (공유 워크트리 — 다른 세션이 동시에 작업 중일 수 있음).
    반환: {attempted, ok, revert_commit, stderr}.
    """
    try:
        out = subprocess.run(
            ["git", "revert", "--no-edit", commit],
            cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if out.returncode == 0:
            return {
                "attempted": True, "ok": True,
                "revert_commit": _git_head(repo_root), "stderr": "",
            }
        subprocess.run(
            ["git", "revert", "--abort"], cwd=repo_root,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
        return {
            "attempted": True, "ok": False, "revert_commit": None,
            "stderr": (out.stderr or "").strip()[:300],
        }
    except Exception as e:  # noqa: BLE001
        try:
            subprocess.run(
                ["git", "revert", "--abort"], cwd=repo_root,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            "attempted": True, "ok": False, "revert_commit": None,
            "stderr": f"{type(e).__name__}: {e}",
        }


def _append_log(entry: dict, path: str) -> None:
    entry = dict(entry)
    entry.setdefault("at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_once(
    clevel: str = "cto",
    nick: str = "시토",
    queue_path: str | None = None,
    registry_path: str | None = None,
    state_path: str | None = None,
    log_path: str | None = None,
    live: bool | None = None,
    claude_timeout: int = 1200,
    ping_state_path: str | None = None,
) -> dict:
    """
    러너 1회 실행.
    live=None이면 env RUNNER_LIVE로 판단(기본 OFF=dry-run). 테스트에서는 live=False/True를
    명시해 env에 무관하게 강제할 수 있다.

    반환 dict 키: mode("guard-blocked"|"dry-run"|"live"|"parked"), ship(dict|None),
    prompt(str|None), executed(bool), commit(str|None), reason(str, 있을 때만).
    mode=="parked"일 때만 ambiguous_reasons(list[str])·parked(bool)·ping(dict) 추가.
    LIVE 실행됐을 때만 baseline_foreign_files(list[str], 세션 시작 전 이미 미커밋이던 무관
    파일)·swept_files(list[str], 커밋에 섞인 베이스라인 파일 — 빈 리스트=위반 없음)·
    revert_result(dict|None, swept_files 있을 때만) 추가.
    """
    queue_path = queue_path or DEFAULT_QUEUE_PATH
    state_path = state_path or DEFAULT_STATE_PATH
    log_path = log_path or DEFAULT_LOG_PATH
    ping_state_path = ping_state_path or DEFAULT_PING_STATE_PATH
    live = _is_live() if live is None else live

    # ── 재귀 폭주 방지 가드: 큐 로드 전에 최우선 차단 ──
    if _guard_active():
        result = {
            "mode": "guard-blocked", "ship": None, "prompt": None,
            "executed": False, "commit": None,
            "reason": f"{GUARD_ENV_VAR}=1 — 러너가 띄운 세션 내부에서의 중첩 실행 차단(재귀 폭주 방지)",
        }
        _append_log({"event": "guard_blocked"}, log_path)
        return result

    # ── 클린트리 베이스라인: LIVE 실행 시에만, 선별·실행 전에 워킹트리를 점검한다.
    # 2026-07-20 재설계 — git status 자체가 실패한 경우(안전 확인 불가)에만 fail-closed
    # 차단한다. allowlist 밖 foreign 파일이 있어도 더 이상 여기서 막지 않고 베이스라인으로만
    # 기록해 두었다가, LIVE 커밋 뒤 실제로 그 파일이 섞였는지 사후 대조한다(아래 sweep 검사).
    baseline_foreign_files: list[str] = []
    if live:
        tree_guard = working_tree_guard()
        if tree_guard["git_error"]:
            result = {
                "mode": "live", "ship": None, "prompt": None, "executed": False, "commit": None,
                "reason": tree_guard["reason"],
                "dirty_files": tree_guard["real_work_files"],
            }
            _append_log({"event": "working_tree_git_error", "reason": tree_guard["reason"]}, log_path)
            return result
        baseline_foreign_files = tree_guard["real_work_files"]
        if baseline_foreign_files:
            _append_log(
                {"event": "working_tree_baseline_dirty", "real_work_files": baseline_foreign_files},
                log_path,
            )

    queue = _load_queue(queue_path)
    registry = load_registry(registry_path)
    state = _load_state(state_path)
    cooldown_ids = _active_cooldown_ids(state)

    ship = select_one_low_risk_ship(clevel, queue, registry=registry, cooldown_task_ids=cooldown_ids)
    mode = "live" if live else "dry-run"

    if ship is None:
        result = {
            "mode": mode, "ship": None, "prompt": None, "executed": False, "commit": None,
            "reason": "선별된 가역·저위험 배 없음(비가역/타clevel/DONE/쿨다운 전부 제외 후 0건)",
        }
        _append_log({"event": "no_ship", "mode": mode, "clevel": clevel}, log_path)
        return result

    prompt = build_orchestration_prompt(ship, clevel=clevel, nick=nick)

    # ── 모호성 판정: 실행(라이브)·미리보기(드라이런) 모두 이 게이트를 먼저 통과해야 한다 ──
    ambiguity = is_ambiguous(ship)
    if ambiguity["ambiguous"]:
        reason = "모호 판정 — GM 인터뷰 필요: " + "; ".join(ambiguity["reasons"])
        result = {
            "mode": "parked", "ship": ship, "prompt": prompt, "executed": False, "commit": None,
            "reason": reason, "ambiguous_reasons": ambiguity["reasons"], "live": live, "parked": False,
        }
        if not live:
            # 드라이런: 큐 무변경(기존 dry-run 불변식 유지) — "이대로 LIVE면 park됨" 미리보기만.
            _append_log(
                {"event": "dry_run_would_park_ambiguous", "task_id": ship.get("task_id"),
                 "reasons": ambiguity["reasons"]},
                log_path,
            )
            return result

        # 라이브: 실제 park(큐 플래그 기록) + parked 전체 목록 기준 텔레그램 핑(2단 게이트·dedup·cap).
        parked_ok = park_ship_for_interview(queue_path, ship["task_id"], ambiguity["reasons"])
        result["parked"] = parked_ok
        parked_task_ids = _collect_parked_task_ids(queue_path)
        notifier = None
        if _ping_live():
            _agents_dir = os.path.join(_PROJECT_ROOT, "wellperion-agents")
            if _agents_dir not in sys.path:
                sys.path.insert(0, _agents_dir)
            try:
                from telegram_notifier import TelegramNotifier  # noqa: E402  (지연 임포트 — RUNNER_PING_LIVE=1일 때만)
                notifier = TelegramNotifier()
            except Exception:  # noqa: BLE001
                notifier = None
        ping_result = maybe_send_ambiguous_ping(parked_task_ids, ping_state_path, notifier=notifier)
        result["ping"] = ping_result
        _append_log(
            {"event": "parked_ambiguous", "task_id": ship.get("task_id"), "reasons": ambiguity["reasons"],
             "parked": parked_ok, "ping_sent": ping_result["sent"], "ping_reason": ping_result["reason"]},
            log_path,
        )
        return result

    if not live:
        result = {
            "mode": "dry-run", "ship": ship, "prompt": prompt, "executed": False, "commit": None,
            "reason": f"{LIVE_ENV_VAR}!=1 — dry-run(claude 미호출·커밋0·_queue.json 무변경)",
        }
        _append_log(
            {"event": "dry_run_select", "task_id": ship.get("task_id"), "title": ship.get("title")},
            log_path,
        )
        return result

    # ── LIVE 경로: RUNNER_LIVE=1일 때만 도달 ──
    claude_bin = shutil.which("claude")
    if not claude_bin:
        result = {
            "mode": "live", "ship": ship, "prompt": prompt, "executed": False, "commit": None,
            "reason": "claude CLI 미설치(PATH 미해결) — 실행 불가",
        }
        _append_log({"event": "live_no_claude_cli", "task_id": ship.get("task_id")}, log_path)
        return result

    before_commit = _git_head(_PROJECT_ROOT)
    child_env = dict(os.environ)
    child_env[GUARD_ENV_VAR] = "1"  # 재귀 폭주 방지: 이 세션이 러너를 다시 못 부르게

    cmd = [
        claude_bin, "-p",
        "--model", "claude-sonnet-4-6",
        "--permission-mode", "acceptEdits",
        "--allowedTools", "Read Write Edit Bash(git *) Bash(python*)",
        "--output-format", "text",
    ]
    stdout_text = ""
    try:
        proc = subprocess.run(
            cmd, input=prompt, cwd=_PROJECT_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=claude_timeout, env=child_env,
        )
        stderr_text = (proc.stderr or "").strip()
        stdout_text = proc.stdout or ""
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
        stderr_text = f"타임아웃({claude_timeout}s)"
    except Exception as e:  # noqa: BLE001
        ok = False
        stderr_text = f"{type(e).__name__}: {e}"

    after_commit = _git_head(_PROJECT_ROOT)
    new_commit = after_commit if (after_commit and after_commit != before_commit) else None
    # best-effort 사후 범위 점검(item 4): 세션 커밋이 실제로 건드린 파일 목록을 기록해
    # 선언 범위 밖 파일 혼입 여부를 나중에 감사할 수 있게 남긴다(완전 자동 판정은 아님).
    changed_files = _commit_changed_files(_PROJECT_ROOT, before_commit, new_commit)

    # ── 스코프 이탈(sweep) 확정 검증: 세션 시작 전부터 이미 미커밋 상태였던 베이스라인
    # foreign 파일(baseline_foreign_files)이 이번 커밋(changed_files)에 섞였는지 대조한다.
    # 섞였으면 "무인 세션이 남의 미커밋 작업을 자기 커밋에 쓸어담았다"는 확정 사고이므로
    # 즉시 안전 되돌림(git revert — 비파괴) + 실패·쿨다운 처리한다(6번 항목 참고).
    swept_files: list[str] = []
    revert_result: dict | None = None
    if new_commit:
        swept_files = _check_sweep_violation(baseline_foreign_files, changed_files)
        if swept_files:
            revert_result = _attempt_safe_revert(_PROJECT_ROOT, new_commit)
            _append_log(
                {
                    "event": "sweep_violation", "task_id": ship.get("task_id"),
                    "commit": new_commit, "swept_files": swept_files, "revert": revert_result,
                },
                log_path,
            )

    # ── 증분2: 자동 검수(세션 stdout 구조화 검증 결과 파싱) → 완료 신뢰 판정 ──
    # sweep 위반이 확인되면 검수 결과와 무관하게 실행 자체를 실패로 취급한다(안전이 완료보다 우선).
    execution_ok = ok and bool(new_commit) and not swept_files
    verify_parsed = parse_verification_result(stdout_text)
    verdict = build_auto_review_verdict(verify_parsed, committed=bool(new_commit))

    # ── 로드맵2: 러너 독립 렌더 실측(게이트 RUNNER_RENDER_VERIFY, 기본 OFF) ──
    # frontend 배이고 검수 통과 상태일 때만, 러너가 라이브 URL을 세션과 독립적으로 재렌더해
    # 200·콘솔0·셀렉터를 재확인한다. 세션 주장과 어긋나면 fold가 verdict를 ambiguous→park로 강등.
    # ★게이트 OFF(기본)면 render_verify_url은 절대 호출되지 않는다 — 기존 동작 100% 불변.★
    render_result = None
    if live and _render_verify_enabled() and verdict["passed"]:
        render_result = render_verify_url(verify_parsed.get("url", ""))
        verdict = fold_render_into_verdict(verdict, verify_parsed, render_result, render_enabled=True)

    # success는 이제 '실행+커밋'뿐 아니라 '자동 검수 통과'까지 요구한다(검수 게이트).
    success = execution_ok and verdict["passed"]

    post_audit = None
    review_parked = False
    state["run_count"] = state.get("run_count", 0) + 1
    if not execution_ok:
        if swept_files:
            # 스코프 이탈 확정 — 검수 이전 문제(안전 최우선). revert 성공 여부와 무관하게 실패 처리.
            revert_note = "자동 되돌림 성공" if (revert_result or {}).get("ok") else "자동 되돌림 실패 — GM 수동 확인 필요"
            _mark_cooldown(
                state, ship["task_id"],
                reason=(f"스코프 이탈 — 베이스라인 무관 파일 혼입({revert_note}): "
                        + ", ".join(swept_files[:5]))[:200],
            )
        else:
            # 실행/커밋 자체 실패 — 기존 경로(쿨다운). 검수 이전 문제.
            _mark_cooldown(state, ship["task_id"], reason=(stderr_text or "커밋 생성 안 됨")[:200])
    else:
        # 실행·커밋됨 → 사후감사(로드맵3)로 선언 완료가 큐에 반영됐는지 대조.
        post_audit = audit_completion_in_queue(queue_path, ship["task_id"])
        if verdict["ambiguous"]:
            # ★비협상 park★: 검수 결과 애매 → 자동 기록(완료 신뢰) 금지 · 사람 확인 대기(park).
            _mark_cooldown(state, ship["task_id"], reason="자동 검수 애매 — 재검토 대기")
            review_parked = park_ship_for_interview(
                queue_path, ship["task_id"],
                ["자동 검수 결과 애매(WELLY_VERIFY 미출력/파싱불가) — 사후 확인 필요"],
            )
        elif not verdict["passed"]:
            # 명확한 검증 실패 → 쿨다운(park 아님 · 애매하지 않음).
            _mark_cooldown(state, ship["task_id"], reason=("자동 검수 실패: " + verdict["reason"])[:200])
        elif post_audit.get("reflected") is False:
            # 검수는 통과했으나 선언 완료가 큐에 반영 안 됨(선언≠반영 불일치) → 경고+쿨다운.
            _mark_cooldown(state, ship["task_id"], reason="사후감사 불일치 — 선언 완료가 큐 미반영")
    _save_state(state, state_path)

    render_summary = None
    if render_result is not None:
        render_summary = {
            "ok": render_result.get("ok"),
            "http_status": render_result.get("http_status"),
            "console_errors": len(render_result.get("console_errors") or []),
            "screenshot": render_result.get("screenshot"),
            "error": render_result.get("error"),
        }

    result = {
        "mode": "live", "ship": ship, "prompt": prompt, "executed": True,
        "success": success, "commit": new_commit, "before_commit": before_commit,
        "stderr_tail": stderr_text[-500:] if stderr_text else "",
        "changed_files": changed_files,
        "baseline_foreign_files": baseline_foreign_files,
        "swept_files": swept_files, "revert_result": revert_result,
        "auto_review": verdict, "verify_parsed": verify_parsed,
        "post_audit": post_audit, "review_parked": review_parked,
        "render_verify": render_summary,
    }
    _append_log(
        {
            "event": "live_run", "task_id": ship.get("task_id"), "success": success,
            "commit": new_commit, "before_commit": before_commit, "changed_files": changed_files,
            "swept_files": swept_files,
            "review_passed": verdict["passed"], "review_ambiguous": verdict["ambiguous"],
            "review_parked": review_parked,
            "post_audit_reflected": (post_audit or {}).get("reflected"),
            "render_verify": render_summary,
        },
        log_path,
    )
    return result


def run_cycle(
    clevels: tuple[str, ...] | None = None,
    nicks: dict | None = None,
    queue_path: str | None = None,
    registry_path: str | None = None,
    state_path: str | None = None,
    log_path: str | None = None,
    live: bool | None = None,
    claude_timeout: int = 1200,
    ping_state_path: str | None = None,
    max_total_ships: int = MAX_SHIPS_PER_CYCLE,
) -> dict:
    """
    전 C-Level 순회(배237 phase4) — clevels(기본 DEFAULT_CLEVELS 7종) 각각에 대해
    run_once()를 순서대로 1회씩 호출한다. clevel마다 최대 1척(선별기 구조 보장)이고,
    사이클 전체 라이브 성공 실행이 max_total_ships에 도달하면 남은 clevel은
    "cycle-cap-skipped"로 건너뛴다(신규 안전 로직 추가 없음 — run_once의 기존 가드를
    그대로 clevel별로 재사용하는 얇은 순회 래퍼).

    ★비협상 원칙(GM 2026-07-14)★ 이 함수는 clevel별 우회 경로를 만들지 않는다 — 각
    clevel 호출이 그대로 run_once()의 is_ambiguous() 게이트를 통과해야 하므로, 배
    note·요구가 조금이라도 불명확하면 해당 clevel은 "parked"만 반환하고 절대 실행되지
    않는다(추측 진행 금지). 전 C-Level 확장은 실행 대상 clevel 수만 넓힐 뿐, 안전
    게이트는 clevel마다 100% 동일하게 적용된다.

    큐·상태·로그·핑 경로는 모든 clevel 호출에 동일하게 공유한다(task_id가 clevel
    접두사로 이미 구분되므로 쿨다운·로그 충돌 없음).

    반환: {"results": {clevel: run_once 반환 dict}, "executed_count": int,
           "cycle_order": list[str]}
    """
    clevels = clevels or DEFAULT_CLEVELS
    nicks = nicks or CLEVEL_NICKS
    results: dict = {}
    executed_count = 0

    for clevel in clevels:
        if executed_count >= max_total_ships:
            results[clevel] = {
                "mode": "cycle-cap-skipped", "ship": None, "prompt": None,
                "executed": False, "commit": None,
                "reason": f"사이클 총 상한({max_total_ships}척) 도달 — 이번 사이클 스킵",
            }
            continue

        nick = nicks.get(clevel, clevel.upper())
        result = run_once(
            clevel=clevel, nick=nick, queue_path=queue_path, registry_path=registry_path,
            state_path=state_path, log_path=log_path, live=live, claude_timeout=claude_timeout,
            ping_state_path=ping_state_path,
        )
        results[clevel] = result
        if result.get("executed") and result.get("success"):
            executed_count += 1

    return {"results": results, "executed_count": executed_count, "cycle_order": list(clevels)}


def _print_run_once_result(result: dict, label: str | None = None) -> None:
    """main()의 단일-clevel/사이클 출력 공통 헬퍼(로직 변경 없이 중복 제거용)."""
    prefix = f"[{label}] " if label else ""
    print(f"{prefix}mode={result['mode']} executed={result['executed']}")
    if result.get("reason"):
        print(f"{prefix}사유: {result['reason']}")
    ship = result.get("ship")
    if ship:
        print(f"{prefix}선택 배: {ship.get('task_id')} | {ship.get('priority')} | {ship.get('title')}")
    if result["mode"] == "dry-run" and result.get("prompt"):
        print("-" * 60)
        print(f"{prefix}[LIVE 발효 시 띄울 프롬프트 미리보기]")
        print(result["prompt"])
    if result["mode"] == "parked":
        print(f"{prefix}모호 사유: {'; '.join(result.get('ambiguous_reasons', []))}")
        print(f"{prefix}parked={result.get('parked')}")
        if result.get("ping"):
            print(f"{prefix}핑: sent={result['ping']['sent']} — {result['ping']['reason']}")
    if result.get("auto_review"):
        rv = result["auto_review"]
        state = "통과" if rv.get("passed") else ("애매→park" if rv.get("ambiguous") else "실패")
        print(f"{prefix}자동 검수: {state} — {rv.get('honesty_tag') or rv.get('reason')}")
        if result.get("post_audit"):
            print(f"{prefix}사후감사: reflected={result['post_audit'].get('reflected')} "
                  f"({result['post_audit'].get('reason')})")
    if result.get("render_verify"):
        rr = result["render_verify"]
        print(f"{prefix}러너 독립 렌더: ok={rr.get('ok')} status={rr.get('http_status')} "
              f"콘솔에러={rr.get('console_errors')} screenshot={rr.get('screenshot')} "
              f"error={rr.get('error')}")
    if result.get("commit"):
        print(f"{prefix}커밋: {result['commit']} (역롤백: git revert {result['commit']})")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="예약 Claude 러너 MVP — 가역·저위험 배 1척 자율 실행(게이트: env RUNNER_LIVE)"
    )
    parser.add_argument(
        "--clevel", default="cto",
        help="대상 C-Level role(기본 cto). 'all'이면 전 C-Level(DEFAULT_CLEVELS 7종) 순회(배237 phase4)",
    )
    parser.add_argument("--nick", default="시토", help="대상 C-Level 닉네임(기본 시토, --clevel all에서는 무시)")
    parser.add_argument(
        "--force-dry-run", action="store_true",
        help="RUNNER_LIVE=1이어도 이번 실행만 강제 dry-run(검증용 — env는 건드리지 않음)",
    )
    parser.add_argument(
        "--interview-worklist", action="store_true",
        help="parked-interview 배(모호 판정으로 park된 배) 목록만 마크다운 표로 출력. "
             "run_once()와 독립 경로 · 큐 읽기전용(웰리 부팅·수동 확인용)",
    )
    parser.add_argument(
        "--boot-candidate", action="store_true",
        help="부팅 자율 진행 후보 1척만 판정해 마크다운으로 출력(읽기전용 — 큐·상태·로그 미기록, "
             "claude 미호출). 대화형 C-Level 세션이 부팅 직후 호출하고, 실행은 세션이 직접 한다.",
    )
    parser.add_argument(
        "--morning-intake", action="store_true",
        help="오늘(로컬 날짜) 새로 올라온 배(전 역할 PENDING·IN_PROGRESS, 기계발행 제외)를 "
             "역할별 표로 출력(읽기전용 — 큐·상태·로그 무기록, claude 미호출, 약속 L20 웰리 몫).",
    )
    parser.add_argument(
        "--render-verify-url", default=None,
        help="주어진 URL을 render_verify_url로 단독 헤드리스 렌더해 결과만 출력(run_once 미가동). "
             "실제 ERP 페이지 수동 실측용.",
    )
    args = parser.parse_args()

    if args.interview_worklist:
        print_interview_worklist()
        return 0

    if args.boot_candidate:
        print_boot_candidate(clevel=args.clevel)
        return 0

    if args.morning_intake:
        print_morning_intake()
        return 0

    if args.render_verify_url:
        rr = render_verify_url(args.render_verify_url)
        print("=" * 60)
        print(f"[render_verify_url] {args.render_verify_url}")
        print(f"  ok            : {rr['ok']}")
        print(f"  http_status   : {rr['http_status']}")
        print(f"  console_errors: {len(rr['console_errors'])}건 {rr['console_errors'][:5]}")
        print(f"  selectors     : {rr['selectors_found']}")
        print(f"  screenshot    : {rr['screenshot']}")
        print(f"  error         : {rr['error']}")
        print("=" * 60)
        return 0

    live = False if args.force_dry_run else None

    if args.clevel == "all":
        cycle = run_cycle(live=live)
        print("=" * 60)
        print(f"[welly_auto_runner] --clevel all — 사이클 실행 {cycle['executed_count']}척"
              f"(순회 순서: {', '.join(cycle['cycle_order'])})")
        for clevel in cycle["cycle_order"]:
            print("-" * 60)
            _print_run_once_result(cycle["results"][clevel], label=clevel.upper())
        print("=" * 60)
        return 0

    result = run_once(clevel=args.clevel, nick=args.nick, live=live)

    print("=" * 60)
    _print_run_once_result(result, label="welly_auto_runner")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
