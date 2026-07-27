#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
회원 도메인(멤버십) 담당자 월간 점수 축 3종 계산 — 배10328(시토), 정본 = 시포 브리프
status/briefs/시포_회원업무_점수축_20260727.md (§2 축 정의 그대로, 여기서 재정의하지 않는다).

배경: GM 지시(배104) '직무 영역별 한 달 100점' 점수판에서 임정은M(회원 도메인)의 축이
아예 없어 영원히 0점이 될 상황이었다. 시포가 축 3개와 분자/분모를 확정했고(배10234
종결), 본 스크립트는 그 계산·표시 배선만 담당한다. **배점(무엇에 몇 점)은 시로 소관
(배104, 아직 DRAFT — `3. 웰페리온 가이드/chro/업무점수판_배점기준_초안.json`)이라
이 스크립트가 임의로 정하지 않는다.** 여기 출력은 "축 계산 결과"이지 최종 인사평가
점수가 아니다.

축 3개 (브리프 §2):
  Axis1 신규 문의 전환      = 판정월 종결 중 SUC계열 / 판정월 종결 전체
  Axis2 활성 문의 컨택 이행률 = 연락기록 있음 / 활성 전체
  Axis3 갱신임박 회원 컨택 처리율 = 재등록상담 기록 있음 / 익월 만기 전체

데이터 재사용(신규 수집기 금지 — 약속 L21):
  Axis1·2 = status/inquiry_snapshot_member.json — cpo_inquiry_snapshot.py 가 3분마다
            member_inquiry_list(GAS)를 갱신해두는 기존 스냅샷을 그대로 읽는다.
            (여기서 또 GAS 를 호출하지 않는다 — 이미 떠 있는 파일 재사용)
  Axis3   = scripts/member_expiry_alert.py 의 fetch_next_month_expiring · _is_contacted ·
            _normalize_owner 를 그대로 호출한다(로직 복제 금지 — 판정 기준이 두 곳에서
            갈리면 사고, 약속 L01과 동일 사상).

★함정1 — 축3 시점 규칙(코드에 박음): 재등록 컨택 알림 발송 주기가 '월 1회(4주차
월요일)'로 이미 설계돼 있다(member_expiry_alert.py). 이 날짜 이전에 실측하면 담당자가
아직 컨택을 시작·완료하지 못한 게 정상이라 값이 낮게 나온다 — 이걸 그 달의 최종
점수로 박제하면 실제로는 일을 하고 있는 담당자가 '일을 안 한 것'처럼 보인다. 그래서
4주차 월요일(트리거일) 이전에는 axis3 를 '데이터 없음'(gate 닫힘, 참고용 raw 값만
별도 노출)으로 표시하고, 트리거일 이후에만 계산값을 확정치로 낸다.

★함정2 — 축1 연도 스코프: 2026년 접수분만 센다(GM 확정 2026-07-27 — 2021~2025년
누적 약 3,162건은 owner/status 필드 자체가 비어 있는 과거 레거시 데이터라 애초에
측정 대상 밖이라는 **정의**이지, 나중에 고쳐야 할 결함이 아니다). member_inquiry_list
스냅샷은 현재도 전부 2026년만 반환하므로 지금은 이 필터가 사실상 no-op 이지만,
과거 데이터가 섞여 분모가 부풀려지는 회귀를 막기 위해 명시적으로 박아둔다.

★함정3 — 축1 코호트 성숙도: 문의 '종결 확정 시각'을 구조화 필드로 기록하는 곳이
시트 어디에도 없다(브리프 §2·§4 — memo의 '등록일:' 텍스트는 과거 재등록/최초가입일이
섞여 있어 부적합). 그래서 접수월(timestamp) 코호트로 잠정 대체 집계하되, 접수 후
2개월 미만 경과한 코호트(가장 최근 달들)는 미결 비율이 높아 저평가되므로 판정에서
제외한다(브리프: "2개월 이상 경과 코호트만 사용").

사용:
  python scripts\\member_axis_scores.py                 # 임정은 기본, 콘솔 출력만
  python scripts\\member_axis_scores.py --owner 임정은 --write   # status/member_axis_scores.json 갱신(파일만, 커밋은 별도)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "status" / "inquiry_snapshot_member.json"
OUT_PATH = REPO_ROOT / "status" / "member_axis_scores.json"

# 기존 판정 상수 재사용(cpo_report.py 가 이미 검증해 쓰고 있는 정의 — 새로 만들지 않는다)
from cpo_report import _SUCCESS_STATUSES  # noqa: E402  {"SUC", "단기SUC"}

# Axis3 재사용 대상(member_expiry_alert.py) — 로직 복제 없이 그대로 호출
from member_expiry_alert import (  # noqa: E402
    fetch_next_month_expiring,
    _is_contacted,
    _normalize_owner,
    OWNER_KEY,
)

# 브리프 §2 Axis1 "종결" 정의 = SUC계열 + LOSS + 재문의로 종결 (가망/컨택중은 미결=분모 제외)
_AXIS1_CLOSED_EXTRA = {"LOSS", "재문의로 종결"}
_AXIS1_CLOSED_STATUSES = _SUCCESS_STATUSES | _AXIS1_CLOSED_EXTRA
# 브리프 §2 Axis2 "활성" 정의
_AXIS2_ACTIVE_STATUSES = {"가망", "컨택중"}

_LEGACY_YEAR_GUARD_PREFIX = "2026"  # ★함정2 — GM 확정(2026-07-27) 연도 스코프


# ── 공용: 스냅샷 로드·owner/연도 필터 (Axis1·2 공유) ──────────────────────────
def _load_snapshot() -> dict | None:
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _owner_rows(rows: list[dict], owner: str) -> list[dict]:
    """owner 셀 앞뒤 공백만 trim 후 정확일치(브리프 §1: "임정은"은 변형 없이 정확 표기 —
    단, 실측 결과 앞에 공백 붙은 변형 1건이 존재해 strip 은 하되 그 이상의 정규화는 하지 않는다)."""
    return [r for r in rows if str(r.get("owner") or "").strip() == owner]


def _year_scoped(rows: list[dict]) -> list[dict]:
    """★함정2 — 지정 연도 접수분만. 현재는 no-op(전부 2026)이지만 회귀 방지용 명시 필터."""
    return [r for r in rows if str(r.get("timestamp") or "").startswith(_LEGACY_YEAR_GUARD_PREFIX)]


def _cohort_month(row: dict) -> str:
    return str(row.get("timestamp") or "")[:7]


def _shift_month(y: int, m: int, delta: int) -> tuple[int, int]:
    total = y * 12 + (m - 1) + delta
    return total // 12, total % 12 + 1


def _mature_cutoff_month(today: date) -> str:
    """★함정3 — 접수 후 2개월 이상 경과한 코호트만 성숙 취급(오늘 기준 이번달·직전달 제외)."""
    y, m = _shift_month(today.year, today.month, -2)
    return f"{y:04d}-{m:02d}"


def _has_contact(row: dict) -> bool:
    for c in row.get("contacts") or []:
        if str(c.get("note") or "").strip():
            return True
    return False


# ── Axis1. 신규 문의 전환 성과 ────────────────────────────────────────────────
def compute_axis1(owner: str, today: date | None = None) -> dict:
    today = today or datetime.now().date()
    snap = _load_snapshot()
    if snap is None or not isinstance(snap.get("rows"), list):
        return {"status": "데이터 없음", "reason": "inquiry_snapshot_member.json 로드 실패"}

    owner_rows = _owner_rows(snap["rows"], owner)
    scoped = _year_scoped(owner_rows)  # 함정2
    cutoff = _mature_cutoff_month(today)  # 함정3
    all_cohort_months = sorted({_cohort_month(r) for r in scoped if _cohort_month(r)})
    excluded_cohorts = [m for m in all_cohort_months if m > cutoff]
    mature = [r for r in scoped if _cohort_month(r) and _cohort_month(r) <= cutoff]

    closed = [r for r in mature if str(r.get("status") or "").strip() in _AXIS1_CLOSED_STATUSES]
    success = [r for r in closed if str(r.get("status") or "").strip() in _SUCCESS_STATUSES]
    denom, numer = len(closed), len(success)

    return {
        "status": "확정" if denom else "데이터 없음",
        "numerator": numer,
        "denominator": denom,
        "rate_pct": round(numer / denom * 100, 1) if denom else None,
        "mature_cohort_cutoff_month": cutoff,
        "excluded_recent_cohort_months": excluded_cohorts,
        "note": "판정월 확정 필드 부재 — 접수월(timestamp) 코호트 대체, 2개월 미만 경과 코호트는 판정 제외(브리프 §2)",
        "year_scope_guard": _LEGACY_YEAR_GUARD_PREFIX,
        "snapshot_generated_at": snap.get("generated_at_kst"),
    }


# ── Axis2. 활성 문의 컨택 이행률 ──────────────────────────────────────────────
def compute_axis2(owner: str) -> dict:
    snap = _load_snapshot()
    if snap is None or not isinstance(snap.get("rows"), list):
        return {"status": "데이터 없음", "reason": "inquiry_snapshot_member.json 로드 실패"}

    owner_rows = _owner_rows(snap["rows"], owner)
    scoped = _year_scoped(owner_rows)
    active = [r for r in scoped if str(r.get("status") or "").strip() in _AXIS2_ACTIVE_STATUSES]
    contacted = [r for r in active if _has_contact(r)]
    denom, numer = len(active), len(contacted)

    return {
        "status": "확정" if denom else "데이터 없음",
        "numerator": numer,
        "denominator": denom,
        "rate_pct": round(numer / denom * 100, 1) if denom else None,
        "judgment_point_note": "월말 스냅샷 권장(누적성 지표라 월중 차이는 작음 — 브리프 §2)",
        "snapshot_generated_at": snap.get("generated_at_kst"),
    }


# ── Axis3. 갱신임박 회원 컨택 처리율 (★함정1 — 월말 시점 게이트) ───────────────
def _nth_monday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    days_until_monday = (0 - d.weekday()) % 7  # weekday(): Mon=0
    first_monday = d + timedelta(days=days_until_monday)
    return first_monday + timedelta(weeks=n - 1)


def _fourth_monday(year: int, month: int) -> date:
    """재등록 컨택 알림 발송일(월 1회, 4주차 월요일) — member_expiry_alert.py 주석의
    발송 주기와 동일 정의. 이 날짜가 axis3 의 '월말 시점' 판정 기준선이다."""
    return _nth_monday(year, month, 4)


def compute_axis3(owner: str, today: date | None = None) -> dict:
    today = today or datetime.now().date()
    trigger = _fourth_monday(today.year, today.month)
    gate_open = today >= trigger  # ★함정1 — 이 날짜 이전엔 확정치로 쓰지 않는다

    fetched = fetch_next_month_expiring(today.strftime("%Y-%m-%d"))
    if fetched is None:
        return {
            "status": "데이터 없음",
            "reason": "GAS(member_active_list) 조회 실패",
            "trigger_date": trigger.isoformat(),
            "gate_open": gate_open,
        }
    next_month, rows = fetched
    owner_rows = [r for r in rows if _normalize_owner(r.get(OWNER_KEY)) == owner]
    total = len(owner_rows)
    contacted = sum(1 for r in owner_rows if _is_contacted(r))
    rate_pct = round(contacted / total * 100, 1) if total else None

    if not gate_open:
        # 월초/월중 — 참고용 raw 값은 남기되 '점수'로는 노출하지 않는다(함정1 핵심).
        return {
            "status": "데이터 없음",
            "reason": f"판정 시점(4주차 월요일 {trigger.isoformat()}) 도달 전 — 월초 값을 그 달 점수로 쓰지 않는다",
            "provisional_raw_not_a_score": {"numerator": contacted, "denominator": total, "rate_pct": rate_pct},
            "trigger_date": trigger.isoformat(),
            "gate_open": False,
            "target_expiry_month": next_month,
        }
    return {
        "status": "확정",
        "numerator": contacted,
        "denominator": total,
        "rate_pct": rate_pct,
        "trigger_date": trigger.isoformat(),
        "gate_open": True,
        "target_expiry_month": next_month,
    }


# ── 통합 ──────────────────────────────────────────────────────────────────────
def compute_member_axes(owner: str, today: date | None = None) -> dict:
    today = today or datetime.now().date()
    return {
        "owner": owner,
        "domain": "membership",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "as_of_date": today.isoformat(),
        "axis1_new_inquiry_conversion": compute_axis1(owner, today),
        "axis2_active_contact_rate": compute_axis2(owner),
        "axis3_renewal_contact_rate": compute_axis3(owner, today),
        "scoring_note": "배점(가중치)은 시로 소관(배104, DRAFT) — 본 파일은 축 계산 결과일 뿐 최종 점수가 아니다. 축이 아직 100점 배점판에 연결되지 않은 동안 회원 칸은 '데이터 없음' 유지(0점 금지).",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="회원 도메인 담당자 월간 점수 축 3종 계산(임정은 기본).")
    parser.add_argument("--owner", default="임정은")
    parser.add_argument("--write", action="store_true", help="status/member_axis_scores.json 갱신(파일 쓰기만, 커밋은 별도 safe_commit)")
    args = parser.parse_args()

    result = compute_member_axes(args.owner)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.write:
        OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[기록] {OUT_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
