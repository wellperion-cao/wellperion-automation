# scripts/ship_classify.py
# 항해 세계관 — 배 분류 공유 모듈 (2026-06-07)
# SSOT: ceo_morning_pipeline.py + daily_scheduler.py 공용
# 중복 구현 금지 — 이 파일이 단일 출처.

from __future__ import annotations
import re
from datetime import datetime

# ── 배 이모지 분류 기준 (명시적 정의) ───────────────────────────────────────
# 🛳️ 크루즈   — priority=HIGH  OR  북극성 키워드 + (마감≤3일 OR 구축·파이프라인 등 upgrade키워드)
# ⛴️ 여객선   — priority=NORMAL (기본값), 명확한 up/downgrade 조건 없는 일반 업무
# ⛵ 돛단배   — priority=LOW   OR  NORMAL이지만 수정·확인·정리 등 downgrade키워드 + 마감 없음 + 북극성 아님
# 🚢 긴급/미분류 — fallback (ship_classify 임포트 실패 시 기본값, 정상 경로에서는 미사용)
SHIP_BY_WEIGHT = {
    "HIGH":   {"icon": "🛳️", "tier": "크루즈"},
    "NORMAL": {"icon": "⛴️", "tier": "여객선"},
    "LOW":    {"icon": "⛵", "tier": "돛단배"},
}

SHIP_WEIGHT_RANK = {"HIGH": 0, "NORMAL": 1, "LOW": 2}

NORTHSTAR_KEYWORDS = [
    "ERP", "erp", "자동화", "수익", "매출", "문의", "파이프라인",
    "전환", "가입", "북극성", "항로", "모듈", "상품화",
]

SHIP_UPGRADE_KEYWORDS = [
    "이관", "구축", "셋업", "프로젝트", "상품화", "파이프라인", "자동화", "통합",
]

SHIP_DOWNGRADE_KEYWORDS = [
    "수정", "교체", "정리", "색", "글씨", "링크", "오타", "확인", "반영",
]

# 식별자 패턴: [시모-08], [시로-03], [웰리-01] 등 '[역할-번호]' 형태
_ID_PATTERN = re.compile(r"\[[\w가-힣]+-\d+\]")


def has_clevel_id(title: str) -> bool:
    """제목에 '[역할-번호]' 형태 식별자가 있으면 True (담당 suffix 생략 기준)."""
    return bool(_ID_PATTERN.search(title))


def classify_ship(task: dict, urgent_titles: set | None = None) -> dict:
    """
    할일(task)을 항해 세계관의 '배'로 분류한다.

    task 키 (유연하게 처리):
      title / 업무명  — 업무 제목
      priority        — HIGH / NORMAL / LOW (없으면 NORMAL)
      note / 내용     — 부가 설명 (북극성 키워드 탐색용)
      deadline / 종료일 / due — 마감일 (urgent 판정용)

    반환: {icon, tier, urgent(bool), northstar(bool)}
    """
    title = str(task.get("title") or task.get("업무명") or "")
    note = str(task.get("note") or task.get("내용") or "")
    hay = f"{title} {note}"

    pri = str(task.get("priority") or "NORMAL").upper()

    northstar = any(kw in hay for kw in NORTHSTAR_KEYWORDS)
    has_deadline = bool(task.get("deadline") and str(task.get("deadline", ""))[:4].isdigit())

    if pri == "HIGH":
        ship = SHIP_BY_WEIGHT["HIGH"]
    elif pri == "LOW":
        ship = SHIP_BY_WEIGHT["LOW"]
    else:
        has_upgrade = any(kw in title for kw in SHIP_UPGRADE_KEYWORDS)
        has_downgrade = any(kw in title for kw in SHIP_DOWNGRADE_KEYWORDS)
        if northstar and (has_deadline or has_upgrade):
            ship = SHIP_BY_WEIGHT["HIGH"]
        elif has_downgrade and not has_deadline and not northstar:
            ship = SHIP_BY_WEIGHT["LOW"]
        else:
            ship = SHIP_BY_WEIGHT["NORMAL"]

    urgent = False
    if urgent_titles and title in urgent_titles:
        urgent = True
    if not urgent:
        dl = task.get("deadline") or task.get("종료일") or task.get("due")
        if isinstance(dl, str) and len(dl) >= 10:
            try:
                d = datetime.strptime(dl[:10], "%Y-%m-%d").date()
                if 0 <= (d - datetime.now().date()).days <= 3:
                    urgent = True
            except ValueError:
                pass

    return {"icon": ship["icon"], "tier": ship["tier"],
            "urgent": urgent, "northstar": northstar}


def render_ship_line(title: str, owner: str, ship: dict, due: str = "") -> str:
    """
    배 한 줄 포맷:
      {icon} {title} [{owner}] {badges}  — 식별자 있으면 [owner] 생략
    badges: 🌟 (northstar) / 🔴 (urgent)

    예)
      🛳️ [시모-08] 카카오채널 발행 확정 🌟
      ⛴️ 다이슨 대안 제품군 재검토 [GM] 🌟
    """
    icon = ship["icon"]
    badges = ""
    if ship.get("northstar"):
        badges += " 🌟"
    if ship.get("urgent"):
        badges += " 🔴"
    due_part = f" · ~{due}" if due else ""

    if has_clevel_id(title):
        return f"{icon} {title}{badges}{due_part}"
    else:
        owner_part = f" [{owner}]" if owner else ""
        return f"{icon} {title}{owner_part}{badges}{due_part}"
