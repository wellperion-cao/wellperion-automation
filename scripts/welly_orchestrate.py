"""
welly_orchestrate.py — 웰리(AI CEO) 자율 대상 선별기 + 검증 규칙 1개.
정본 계획: docs/superpowers/plans/2026-07-09-clevel-autonomous-execution-loop.md (Task 4).
순수 함수만 제공 — 라이브 부작용 0 (status/_queue.json·module_registry.json을 직접 읽지 않고
호출부가 queue·registry를 인자로 전달한다).
"""

import sys

from module_registry import get_modules_by_role

# ── 비가역 신호 키워드(계획 명시: 보수적으로 명시 비가역 키워드 있으면 제외) ──
IRREVERSIBLE_KEYWORDS = (
    "발행",
    "배포",
    "삭제",
    "외부전송",
    "결제",
    "보안",
    "전략",
    "공식값",
)

ACTIVE_STATUSES = ("PENDING", "IN_PROGRESS")

# ── 신규 생성 낱말 폴백(work_type 미선언 시만 사용) ──
# 실측(2026-08-02): 열린 배 44척 중 35척이 work_type 미선언 → 게이트를 그냥 통과.
# 바로 '신규'를 쓰면 "신규저장"(매뉴얼 재저장)·"신규 등록"(등록 건수) 같은 무관한
# 문맥까지 걸린다(실측 오탐 2건) — 그래서 배 생성을 가리키는 구체 표현만 쓴다.
NEW_SHIP_KEYWORDS = (
    "신설",
    "배신규",
    "신규 생성",
    "신규 개설",
    "새로 만들",
    "새 페이지",
    "새 모듈",
    "새 화면",
)


def _is_reversible(ship):
    """
    배(dict)의 priority·title·next를 훑어 비가역 키워드가 없으면 가역으로 간주.
    보수적 판단: 하나라도 매치되면 비가역(제외).
    """
    # 판정은 설명글이 아니라 배 작성자의 선언을 먼저 믿는다(2026-07-27 GM 지적·오탐 45척 실측).
    # 선언이 없을 때만 낱말 스캔으로 폴백.
    reversible = ship.get("reversible")
    if reversible is True:
        return True
    if reversible is False:
        return False
    # 낱말 스캔 대상 = note 제외, title+next(2026-07-27 2차 지적·오탐 재실측).
    # note는 맥락·경위·전례·타인 인용이 길게 쌓이는 곳이라 위험을 "경고하는" 문장·
    # 남의 도메인 인용까지 위험 신호로 오인한다(실측: 삭제 경고문·타 clevel 인용·고유명사
    # '전략로드맵'까지 오탐). title은 작업 성격을 압축하고, next는 실제로 할 일을 담아
    # 앞으로 손댈 것을 더 정확히 반영한다 — note 전체보다 좁고 title보다 구체적이다.
    fields = (
        ship.get("priority") or "",
        ship.get("title") or "",
        ship.get("next") or "",
    )
    text = " ".join(fields)
    return not any(keyword in text for keyword in IRREVERSIBLE_KEYWORDS)


def _is_new_ship(ship):
    """
    work_type=="new"(신규 생성)로 선언된 배는 가역이어도 자율 후보에서 제외한다
    (2026-08-01 GM 아침 루틴 공통 규약 — 신규 생성은 항상 GM 승인: 프론트=웰리 / 백엔드=시토).

    판정은 선언을 먼저 믿는다(_is_reversible과 동일 패턴 · 2026-07-27 정답 재사용).
    work_type이 선언돼 있으면 그 값이 항상 이긴다("update" 선언 배는 낱말이 있어도
    스캔에 안 걸린다). 미선언(None)일 때만 title+next 낱말 스캔으로 폴백한다 —
    실측 84%(38/45척)가 미선언이라 게이트를 그냥 통과하던 구멍(2026-08-02 웰리 지적).
    """
    work_type = ship.get("work_type")
    if work_type is not None:
        return work_type == "new"

    fields = (ship.get("title") or "", ship.get("next") or "")
    text = " ".join(fields)
    return any(keyword in text for keyword in NEW_SHIP_KEYWORDS)


def select_autonomous_ships(clevel, queue, registry=None):
    """
    queue(=_queue.json 리스트)에서 다음을 모두 만족하는 배만 반환한다:
      1) status가 PENDING 또는 IN_PROGRESS
      2) clevel 일치
      3) 신규 생성(work_type=="new")이 아님
      4) 가역(비가역 키워드 없음)
      5) 해당 clevel의 등록부 모듈이 존재(get_modules_by_role)
      6) 끝이 있는 일(cadence 가 routine·trigger 가 아님 · 2026-08-16 GM 지시)
    """
    if not get_modules_by_role(clevel, registry=registry):
        return []

    selected = []
    for ship in queue:
        if ship.get("status") not in ACTIVE_STATUSES:
            continue
        if ship.get("clevel") != clevel:
            continue
        if _is_new_ship(ship):
            # 조용한 탈락 금지(2026-08-01 GM 지시) — 왜 빠졌는지 흔적을 남긴다.
            print(
                "[select_autonomous_ships] 제외(신규 생성 · GM 승인 필요): %r"
                % ship.get("task_id"),
                file=sys.stderr,
            )
            continue
        if not _is_reversible(ship):
            continue
        # ★2026-08-16 GM 지시 — '의미없거나 중복되었거나 진행완료된 것들은 더 이상 작업 안 하게'.
        #   cadence=routine(매일·매주 도는 일)·trigger(사건이 와야 시작)는 지금 집어도 할 일이
        #   없다. 러너가 집으면 매 사이클 헛돌면서 진짜 밀린 배의 처리 자리를 뺏는다.
        #   빈칸(=대부분의 기존 배)은 그대로 통과한다 — 회귀 0.
        if str(ship.get("cadence") or "").strip() in ("routine", "trigger"):
            print(
                "[select_autonomous_ships] 제외(끝이 없는 일 · 반복 루틴/조건 대기): %r"
                % ship.get("task_id"),
                file=sys.stderr,
            )
            continue
        selected.append(ship)
    return selected


def verify_reversible_meta(ship):
    """
    코드화한 검증 규칙 1개: DONE 주장 배에 아티팩트 증거가 있는지 확인.
    ship.get('artifact') 또는 ship.get('artifact_url')이 비어있지 않아야 통과.
    아티팩트 없는 DONE = passed False(거짓 완료 차단).
    반환: {"passed": bool, "evidence": str}
    """
    artifact = ship.get("artifact") or ""
    artifact_url = ship.get("artifact_url") or ""
    evidence = artifact or artifact_url

    if not evidence:
        return {
            "passed": False,
            "evidence": f"아티팩트 없음(거짓 완료 의심): task_id={ship.get('task_id')!r}",
        }

    return {"passed": True, "evidence": evidence}


if __name__ == "__main__":
    # 자기검사(assert 기반, 프레임워크 없음) — work_type 게이트 3케이스(2026-08-01)
    # + 낱말 폴백 3케이스(2026-08-02, 배290).
    _reg = {"modules": [{"owner_role": "cto"}]}
    _base = {"clevel": "cto", "status": "PENDING", "priority": "⛴️여객선",
             "title": "테스트", "next": "테스트"}

    _new = {**_base, "task_id": "T-NEW", "work_type": "new"}
    _update = {**_base, "task_id": "T-UPDATE", "work_type": "update"}
    _unset = {**_base, "task_id": "T-UNSET"}  # 미선언 배(기존 큐 다수가 이 상태)

    _out = select_autonomous_ships("cto", [_new, _update, _unset], registry=_reg)
    _ids = {s["task_id"] for s in _out}
    assert "T-NEW" not in _ids, "work_type=new 이 자율 후보에서 제외되지 않음"
    assert "T-UPDATE" in _ids, "work_type=update 이 통과하지 않음(회귀)"
    assert "T-UNSET" in _ids, "미선언 배가 통과하지 않음(회귀)"
    print("OK — work_type 게이트 3케이스(new 제외 · update/미선언 통과) 통과")

    # cadence 게이트 3케이스(2026-08-16, GM 지시 — 끝이 없는 일은 자율 후보에서 뺀다)
    _rout = {**_base, "task_id": "T-ROUTINE", "cadence": "routine"}
    _trig = {**_base, "task_id": "T-TRIGGER", "cadence": "trigger"}
    _ids2 = {s["task_id"] for s in
             select_autonomous_ships("cto", [_rout, _trig, _unset], registry=_reg)}
    assert "T-ROUTINE" not in _ids2, "반복 루틴이 자율 후보에서 제외되지 않음"
    assert "T-TRIGGER" not in _ids2, "조건 대기가 자율 후보에서 제외되지 않음"
    assert "T-UNSET" in _ids2, "cadence 빈칸 배가 통과하지 않음(회귀)"
    print("OK — cadence 게이트 3케이스(routine/trigger 제외 · 빈칸 통과) 통과")

    # 낱말 폴백: 미선언 + 신규 생성 낱말 → new 로 간주(제외).
    _unset_new_word = {**_base, "task_id": "T-UNSET-NEW", "title": "새 페이지 신설"}
    # 낱말 폴백: 미선언 + 무관 낱말("신규 등록" 등) → 통과(오탐 방지, 2026-08-02 실측).
    _unset_irrelevant = {**_base, "task_id": "T-UNSET-IRRELEVANT",
                          "next": "이번 달 신규 등록 몇 건인지 화면에서 바로 답한다"}
    # 선언 우선: work_type=update 면 낱말이 있어도 통과(회귀 없음).
    _declared_wins = {**_base, "task_id": "T-DECLARED-WINS", "work_type": "update",
                       "title": "페이지 신설"}

    _out2 = select_autonomous_ships(
        "cto", [_unset_new_word, _unset_irrelevant, _declared_wins], registry=_reg
    )
    _ids2 = {s["task_id"] for s in _out2}
    assert "T-UNSET-NEW" not in _ids2, "미선언+신규 낱말이 걸러지지 않음"
    assert "T-UNSET-IRRELEVANT" in _ids2, "무관 낱말('신규 등록')에 오탐"
    assert "T-DECLARED-WINS" in _ids2, "선언값이 낱말 스캔에 밀림(선언 우선 회귀)"
    print("OK — work_type 낱말 폴백 3케이스(신규 낱말 제외 · 무관낱말 통과 · 선언 우선) 통과")
