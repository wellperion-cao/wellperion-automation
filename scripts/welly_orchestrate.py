"""
welly_orchestrate.py — 웰리(AI CEO) 자율 대상 선별기 + 검증 규칙 1개.
정본 계획: docs/superpowers/plans/2026-07-09-clevel-autonomous-execution-loop.md (Task 4).
순수 함수만 제공 — 라이브 부작용 0 (status/_queue.json·module_registry.json을 직접 읽지 않고
호출부가 queue·registry를 인자로 전달한다).
"""

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


def select_autonomous_ships(clevel, queue, registry=None):
    """
    queue(=_queue.json 리스트)에서 다음을 모두 만족하는 배만 반환한다:
      1) status가 PENDING 또는 IN_PROGRESS
      2) clevel 일치
      3) 가역(비가역 키워드 없음)
      4) 해당 clevel의 등록부 모듈이 존재(get_modules_by_role)
    """
    if not get_modules_by_role(clevel, registry=registry):
        return []

    selected = []
    for ship in queue:
        if ship.get("status") not in ACTIVE_STATUSES:
            continue
        if ship.get("clevel") != clevel:
            continue
        if not _is_reversible(ship):
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
