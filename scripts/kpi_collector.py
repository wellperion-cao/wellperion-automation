# -*- coding: utf-8 -*-
"""
kpi_collector.py  --  KPI 자동집계 (2차 확장 · 2026-06-23)

측정 가능한 지표만 실수치로 기록. 측정 불가 = null.
거짓 숫자 절대 금지 (대시보드 정직 원칙 · ssot/약속.json 참조).

출력: status/kpi_values.json
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
import urllib.error
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / "status" / "_queue.json"
OUT_PATH   = ROOT / "status" / "kpi_values.json"

KST = timezone(timedelta(hours=9))
ACTIVE = {"PENDING", "IN_PROGRESS"}
DONE   = {"DONE"}


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _load_queue() -> list[dict]:
    try:
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _is_machine_ship(ship: dict) -> bool:
    """
    기계 자동발행 배 판별 (2026-07-20 GM 결재 [A]안 · INC-018 후속 · 배9186→배1307).
    완결률(대표 숫자)=사람·AI 실무 배만. 무인 예약 스크립트가 찍어내는 스냅샷/현황
    발행(예: 문의 스냅샷 3분마다·주차매출 등)은 실무 신호가 아니라 분자·분모에서 뺀다
    (건수는 _role_stats 가 "기계발행_건수"로 별도 병기 — 삭제·은폐 아님).

    판별 = 구조적 신호 2개 AND(개별 업무명 하드코딩 금지 · GM 지시):
      ① adhoc_commit 존재 — auto_log_adhoc_to_queue.py 가 git 커밋을 그대로 배로 흡수한
         것(사람/AI가 직접 큐에 적어넣은 배가 아니라, 원본 커밋 주체를 되짚어야 하는 배).
      ② title 에 정확한 문구 "자동 발행" 포함 — 이 문구는 이미 이 저장소의 예약(Task
         Scheduler) 스냅샷/현황 스크립트가 공유하는 커밋 제목 관례다(cpo_inquiry_snapshot.py
         "문의 스냅샷 자동 발행"·parking_revenue_crawler.py "주차 매출 현황 자동 발행"·
         erp_status_publisher.py "시스템 현황 자동 발행" 전부 이 문구로 커밋 — 마지막 것은
         auto_log_adhoc_to_queue.py 스킵규칙에 이미 이 문구가 키워드로 쓰이고 있었음,
         2026-07-20 확인). title 은 adhoc 배 생성 시 커밋 subject 를 그대로 물려받으므로
         (conventional prefix 만 벗김) git 재조회 없이 큐 데이터만으로 판별 가능.
      실측 검증(2026-07-20): 전체 큐+아카이브 2,122배 중 이 조건에 걸리는 배=정확히 292건
      (문의 스냅샷)+28건(주차매출) 뿐 — 오탐 0건(예: "auto(cmo): 검수 승인 — …" 류 실제
      콘텐츠 발행 배·"자동push 경합" 등 "자동"만 들어간 실무 커밋은 전혀 안 걸림).
      새 예약 스크립트도 이 관례(커밋 제목에 "자동 발행")만 따르면 자동 편입 —
      배 이름별 하드코딩 불필요.
    """
    if not isinstance(ship, dict):
        return False
    if not ship.get("adhoc_commit"):
        return False
    return "자동 발행" in (ship.get("title") or "")


def _role_stats(ships: list[dict], role: str) -> dict:
    """
    role별 완료/활성/완결률 계산. 완결률 = DONE / (DONE + ACTIVE) — 사람·AI 실무 배만
    (2026-07-20 GM 결재 [A]안: 기계 자동발행 배는 분자·분모 제외). 기계 배 건수는
    "기계발행_건수"로 별도 병기(가동량 신호 유지 · _is_machine_ship 참조).
    """
    role_ships    = [s for s in ships if isinstance(s, dict) and s.get("clevel") == role]
    machine_ships = [s for s in role_ships if _is_machine_ship(s)]
    human_ships   = [s for s in role_ships if not _is_machine_ship(s)]
    done   = sum(1 for s in human_ships if s.get("status") in DONE)
    active = sum(1 for s in human_ships if s.get("status") in ACTIVE)
    total  = done + active
    rate   = round(done / total, 4) if total > 0 else None
    machine_done = sum(1 for s in machine_ships if s.get("status") in DONE)
    return {"완결률": rate, "완료": done, "활성": active, "기계발행_건수": machine_done}


_STALL_DAYS = 7  # 2026-08-04 GM 재지적 — 3일은 정상 리듬과 섞인다, 7일 넘게 열려 있어야 진짜 신호


def _role_stalled_ships(ships: list[dict], role: str, today=None) -> dict:
    """멈춘 배 — 열린 배(PENDING/IN_PROGRESS) 중 **enqueued_at**(열린 지 며칠) 기준
    _STALL_DAYS일 이상 그대로인 것.
    ⚠️ updated_at 이 아니라 enqueued_at 을 쓴다 — 배117(cpo) 실측(2026-08-04)이
    이유다: enqueued_at=07-25·10일째 방치인데 updated_at 은 08-04(오늘)이었다.
    updated_at 은 스냅샷 자동발행·auto-log 커밋이 큐 파일을 다시 쓸 때마다 같이
    갱신돼 "일을 안 해도 방금 만진 것"처럼 보인다(아침 점검표 #1-b "도는데 결과를
    못 내는 장치"와 같은 함정) — 손대지 말고 그대로 둘 것.
    IN_PROGRESS 인데 오래된 것은 더 나쁜 신호라 최장 배 정보에 status 를 함께
    남긴다(한 숫자에 두 뜻을 안 섞음). 날짜 파싱 실패 건은 개별 스킵(집계 전체를
    죽이지 않음 — 0 위장과는 다름, 파싱 안 되는 값만 빠진다)."""
    today = today or datetime.now(KST).date()
    stalled = []  # (경과일, 배번호, status)
    for s in ships:
        if not isinstance(s, dict) or s.get("clevel") != role or s.get("status") not in ACTIVE:
            continue
        raw = s.get("enqueued_at")
        if not raw:
            continue
        try:
            d = datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        days = (today - d).days
        if days >= _STALL_DAYS:
            stalled.append((days, s.get("short_no") or s.get("task_id"), s.get("status")))
    if not stalled:
        return {"멈춘배_건수": 0, "멈춘배_최장일수": None, "멈춘배_최장배번호": None, "멈춘배_최장상태": None}
    stalled.sort(reverse=True)
    worst_days, worst_id, worst_status = stalled[0]
    return {
        "멈춘배_건수": len(stalled),
        "멈춘배_최장일수": worst_days,
        "멈춘배_최장배번호": worst_id,
        "멈춘배_최장상태": worst_status,
    }


def _unpushed_count() -> int | None:
    """origin/master..HEAD 미푸시 커밋 수. 실패 시 None."""
    try:
        r = subprocess.run(
            ["git", "rev-list", "origin/master..HEAD", "--count"],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if r.returncode == 0:
            return int((r.stdout or "0").strip() or "0")
    except Exception:
        pass
    return None


def _mirror_ok() -> str | None:
    """
    status/_queue.json 와 가이드 미러 비교.
    "ok" / "drift" / None(미러 없음)
    """
    mirror = ROOT / "3. 웰페리온 가이드" / "status" / "_queue.json"
    try:
        if not mirror.exists():
            return None
        return "ok" if QUEUE_PATH.read_bytes() == mirror.read_bytes() else "drift"
    except Exception:
        return None


# 점검 GAS (지원팀 일일점검 · 4부서 공용 — 월간은 지원부만, 운영부·주차부는 weekly로 잠정 측정)
_CHECK_GAS = (
    "https://script.google.com/macros/s/"
    "AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec"
)
# 회원 문의/이탈 GAS (membership.html과 동일 정본 — cpo_churn_stats 등)
_CPO_GAS = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)
# 매출·업무 메가 GAS (.deploy-todo/업무&결재 현황.js — 월간운영계획.html·AI운영한장.html과 동일 정본)
# action=sales_monthly → '26년 매출 분석' AV3:AV14 미러(회사 전체 월별 마감 총매출). cao 인증 배포 완료(배354 phase1, 커밋 859a6bfa) — 신규 배포 불필요.
_CFO_GAS = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)
_HTTP_TIMEOUT = 20
SALES_TARGETS_PATH = ROOT / "status" / "sales_targets.json"
# 배358 — cpo-staff-feedback-watch.py 가 3분마다 이미 재는 '미처리' 재사용(새 조회 0건).
STAFF_FB_HEARTBEAT_PATH = ROOT / "status" / "heartbeats" / "cpo-staff-feedback-watch.json"


def _http_get_json(url: str, timeout: int = _HTTP_TIMEOUT, retries: int = 2) -> object:
    """GET → 파싱된 JSON 객체. GAS 콜드스타트(아침 첫 호출)로 인한 일시 타임아웃·네트워크
    실패는 백오프(2s·4s) 재시도. 마지막 예외는 호출부에서 처리."""
    sep = "&" if "?" in url else "?"
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        busted = f"{url}{sep}_cb={int(time.time())}-{attempt}"
        req = urllib.request.Request(
            busted, headers={"Cache-Control": "no-cache"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise last_exc


def _coo_check_rate_monthly(month_str: str) -> dict | None:
    """
    지원부 월간 점검완료율 조회(1개월). 실패/데이터없음=None.
    소스: 점검 GAS monthly_report?dept=support&month=YYYY-MM (제출된 점검일지 스냅샷 집계).
    """
    try:
        url = f"{_CHECK_GAS}?action=monthly_report&dept=support&month={month_str}"
        data = _http_get_json(url)
        if not isinstance(data, dict) or not data.get("ok"):
            return None
        totals = data.get("monthTotals")
        if not isinstance(totals, dict):
            return None
        sum_total = totals.get("sumTotal")
        sum_done  = totals.get("sumDone")
        avg_pct   = totals.get("avgPct")
        active_days = totals.get("activeDays")
        if not isinstance(sum_total, (int, float)) or sum_total <= 0:
            return None  # 해당 월 활성 데이터 없음(예: 월초)
        rate = (
            round(avg_pct / 100, 4)
            if isinstance(avg_pct, (int, float)) and not isinstance(avg_pct, bool)
            else (round(sum_done / sum_total, 4) if isinstance(sum_done, (int, float)) else None)
        )
        # 제출률·제출분충실도 — 지원부 체계.html:8667 mrSubmitBreakdown 과 동일 산식(복제 아님·같은 필드 재사용).
        # submitted = 제출된 세션에 실제 담긴 항목수(byZone.sumTotal 합) — sum_total(예정 전체)과 다르다.
        zones = data.get("byZone")
        submitted = (
            sum((z.get("sumTotal") or 0) for z in zones if isinstance(z, dict))
            if isinstance(zones, list) else None
        )
        submit_rate = round(submitted / sum_total, 4) if submitted else None
        fill_rate = (
            round(sum_done / submitted, 4)
            if submitted and isinstance(sum_done, (int, float)) else None
        )
        return {
            "rate": rate, "done": sum_done, "total": sum_total,
            "month": month_str, "active_days": active_days,
            "submit_rate": submit_rate, "fill_rate": fill_rate,
        }
    except Exception:
        return None


def _check_weekly(dept: str) -> dict | None:
    """운영부(ops)·주차부(parking) 최근 7일 점검 실측 — 점검 GAS weekly action.
    월간 분기(monthly_report)가 이 두 부서엔 아직 없어(2026-09-01 설계 1·2단계 = 시토 GAS 배선 대기)
    weekly(점검일지_<dept> 스냅샷 7일 집계)로 잠정 측정한다. GAS 분기가 생기면 monthly로 교체.
    반환: {"days": 제출 있었던 날 수(0~7 — 0도 실측값), "done"/"total": 7일 합, "rate": done/total|None}
    조회 실패=None (0 아님 — '진짜 미제출'과 '못 읽음'을 섞지 않는다)."""
    try:
        data = _http_get_json(f"{_CHECK_GAS}?action=weekly&dept={dept}")
        if not isinstance(data, dict) or not data.get("ok"):
            return None
        rows = [r for r in (data.get("data") or []) if isinstance(r, dict)]
        total = sum(int(r.get("total") or 0) for r in rows)
        done = sum(int(r.get("done") or 0) for r in rows)
        days = sum(1 for r in rows if int(r.get("total") or 0) > 0)
        return {"days": days, "done": done, "total": total,
                "rate": round(done / total, 4) if total > 0 else None}
    except Exception:
        return None


def _coo_check_rate() -> dict:
    """
    지원부 점검완료율 — home/북극성 대표값 = 월간(당월 누적) 실측.
    ⚠️ 배890 근본수리(2026-07-13): 구 소스(today_live 당일 값)를 대표값으로 쓰면 매일 아침
    스냅샷 시각(kpi_collector 07:50 실행)에 done=0/total>0 이라 "0.0%로 죽어보임"(측정 실패
    아님·오전 미시작 아티팩트, 실측 근거: 라이브 today_live 확인·월간 데이터엔 매일 실적 존재).
    → 대표값을 monthly_report(당월 누적, 월초라 데이터 없으면 전월 최종)으로 재배선.
    당일 today_live 값은 "_당일라이브" 접미 필드로 참고 병기(대표값 아님).
    반환: {"지원부_점검완료율": 0~1|null(대표=월간), "지원부_완료"/"지원부_전체": 월간 분자/분모,
           "지원부_점검완료율_기준": "YYYY-MM(누적,N일활성)"|"YYYY-MM(전월 최종)"|null,
           "지원부_제출률": 0~1|null(예정 대비 제출), "지원부_제출분충실도": 0~1|null(제출분 안 체크율)
             — 완료율=제출률×제출분충실도 분해(지원부 체계.html mrSubmitBreakdown 과 동일 산식),
           "지원부_점검완료율_당일라이브": 0~1|null(참고), "지원부_당일라이브_완료"/"_전체": int|null,
           "운영부/주차부_주간제출일수·_점검완료율·_기준": weekly 잠정 실측(_check_weekly — 조회실패=null·제출0=실측),
           "4부서_점검완료율": null, "_note": str}
    — 4부서 합성값은 시설부 미수집·산식 미결재라 null 유지(부서별 필드가 실측 정본).
    """
    result: dict = {
        "지원부_점검완료율": None,
        "지원부_완료": None,
        "지원부_전체": None,
        "지원부_점검완료율_기준": None,
        "지원부_제출률": None,
        "지원부_제출분충실도": None,
        "지원부_점검완료율_당일라이브": None,
        "지원부_당일라이브_완료": None,
        "지원부_당일라이브_전체": None,
        "운영부_주간제출일수": None,
        "운영부_점검완료율": None,
        "운영부_점검완료율_기준": None,
        "주차부_주간제출일수": None,
        "주차부_점검완료율": None,
        "주차부_점검완료율_기준": None,
        "4부서_점검완료율": None,
        "_note": "4부서전체=미측정(GAS가지원부한정)",
    }
    now = datetime.now(KST)
    cur_month = now.strftime("%Y-%m")

    # 대표값: 당월 누적 월간 완료율. 당월 데이터 없으면(월초) 전월 최종으로 폴백.
    monthly = _coo_check_rate_monthly(cur_month)
    basis = f"{cur_month}(누적,{monthly['active_days']}일활성)" if monthly else None
    if monthly is None:
        prev_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        monthly = _coo_check_rate_monthly(prev_month)
        basis = f"{prev_month}(전월 최종)" if monthly else None

    if monthly is not None:
        result["지원부_점검완료율"]     = monthly["rate"]
        result["지원부_완료"]           = monthly["done"]
        result["지원부_전체"]           = monthly["total"]
        result["지원부_점검완료율_기준"] = basis
        result["지원부_제출률"]         = monthly.get("submit_rate")
        result["지원부_제출분충실도"]   = monthly.get("fill_rate")
        result["_note"] = (
            "4부서전체=미측정(GAS가지원부한정) · 대표값=월간 누적 실측(monthly_report, "
            f"기준={basis}) · 당일 라이브는 _당일라이브 필드 참고(아침엔 0 정상·측정실패 아님)"
        )
    else:
        result["_note"] = "monthly_report 당월·전월 모두 데이터없음/응답오류"

    # 참고값: 오늘 today_live(진행중 당일 포함·분모정합 통로 · 배239). 실패해도 대표값엔 무영향.
    try:
        today_str = now.strftime("%Y-%m-%d")
        url = f"{_CHECK_GAS}?action=today_live&dept=support&date={today_str}"
        data = _http_get_json(url)
        if isinstance(data, dict) and data.get("total"):
            total = data.get("total")
            done  = data.get("done") or 0
            result["지원부_점검완료율_당일라이브"] = round(done / total, 4) if total > 0 else None
            result["지원부_당일라이브_완료"]       = done
            result["지원부_당일라이브_전체"]       = total
    except Exception:
        pass  # 참고값 실패는 대표값(월간)에 영향 없음(null 안전)

    # 운영부·주차부 — 입력·적재 경로는 살아 있음(2026-09-01 실측: 응답 ok, 최근 7일 제출 0).
    # 완료율은 제출이 있어야 나오므로 제출 0이면 null, 제출일수 0이 실측값이다(조회 실패만 None).
    ext_notes = []
    for dept, label in (("ops", "운영부"), ("parking", "주차부")):
        wk = _check_weekly(dept)
        if wk is None:
            ext_notes.append(f"{label}=조회실패(null·0 아님)")
            continue
        result[f"{label}_주간제출일수"] = wk["days"]
        result[f"{label}_점검완료율"] = wk["rate"]
        result[f"{label}_점검완료율_기준"] = f"주간(최근7일·weekly&dept={dept}·휴관일 미보정)"
        ext_notes.append(f"{label}=주간실측({wk['days']}일 제출)")
    # 4부서 합성값은 억지로 만들지 않는다 — 시설부가 이 수집기에 없고 합성 산식은 공식값(GM 결재) 사안.
    result["_note"] += " · " + " · ".join(ext_notes) + " · 4부서 합성값=미정의(시설부 미수집·산식은 GM 결재 사안)"

    return result


def _cpo_loss_rate() -> dict:
    """
    cpo 당월 회원 이탈률(LOSS) 실측 — 배299 cpo_churn_stats GAS.
    ⚠️ 역방향 지표(낮을수록 좋음) — 유지율로 뒤집거나 도달율%로 과장 금지(약속 L05).
    소스: cpo_churn_stats action (monthLossRate = 이미 % 단위 실측값).
    반환: {"월_LOSS율": "0.9%"(문자열·그대로 표기) 또는 null, "월_LOSS건수": int, "유효회원수": int, "_note": str}
    """
    result: dict = {
        "월_LOSS율": None,
        "월_LOSS건수": None,
        "유효회원수": None,
        "_note": "역방향 지표(낮을수록 좋음) · cpo_churn_stats 실측",
    }
    try:
        data = _http_get_json(f"{_CPO_GAS}?action=cpo_churn_stats")
        if not isinstance(data, dict) or not data.get("ok"):
            result["_note"] = "GAS 응답 오류(ok=false 또는 형식 불일치)"
            return result
        rate = data.get("monthLossRate")
        if isinstance(rate, (int, float)) and not isinstance(rate, bool):
            result["월_LOSS율"] = f"{rate}%"
        result["월_LOSS건수"] = data.get("monthLossCount")
        result["유효회원수"] = data.get("activeCount")
    except Exception as e:
        result["_note"] = f"fetch 실패({type(e).__name__}): {str(e)[:80]}"
    return result


def _cpo_funnel_conversion() -> dict:
    """
    cpo 문의→가입 전환율 실측 — .deploy-funnel/Survey.js:3176-3297+ funnel_conversion action.
    동일 CPO GAS(_CPO_GAS) — PII 없음, 집계 수치만(전화번호 등 개인정보 미포함).
    누적치(문의_가입_전환율)=전화매칭 기준(등록일 미사용) — 기간별 부정확·과소집계 가능.
    이번달치(이번달_전환율)=opt-in 정밀분자(numerator=registered, 2026-07-04 시포) — 등록일이 이번달 1일~오늘인
    건만 전환 인정. 단 강습원장 시드(2026-06-27) 이전 등록자는 기간필터서 제외되는 한계 있음(GAS convBasis 참조).
    반환: {"문의_가입_전환율": float(%)|None, "전환_문의수": int|None, "전환_가입수": int|None,
           "이번달_전환율": float(%)|None, "이번달_전환_문의수": int|None, "이번달_전환_가입수": int|None,
           "_전환_note": str}
    ⚠️ 키명 "_note"는 _cpo_loss_rate()가 이미 점유(cpo 블록 병합 시 dict.update로 덮어써짐) — 별도 "_전환_note" 사용(무손상).
    """
    result: dict = {
        "문의_가입_전환율": None,
        "전환_문의수": None,
        "전환_가입수": None,
        "이번달_전환율": None,
        "이번달_전환_문의수": None,
        "이번달_전환_가입수": None,
        # ── 비교가능 기준선(2026-07-14 시포) — 지표 착시 방지. 아래 짝끼리만 비교할 것. ──
        "이번달_전환율_전화매칭": None,   # 이번달 문의, 전화매칭 분자 → 누적(문의_가입_전환율)과 동일기준·비교가능
        "전월_전환율": None,              # 전월(완결) 정밀 분자 → 이번달_전환율(정밀)과 동일기준·비교가능
        "전월_전환_문의수": None,
        "전월_전환_가입수": None,
        "전월_라벨": None,
        "_전환_note": "⚠️비교금지: 누적_전환율(39.9%류)=전화매칭·전체누적 vs 이번달_전환율(정밀)=등록월 기준 → 서로 다른 지표라 뺄셈=착시(2026-07-14 시포 진단). 동일기준 비교쌍: ①이번달_전환율_전화매칭 vs 문의_가입_전환율 ②이번달_전환율(정밀) vs 전월_전환율(정밀). 정밀=등록일 기준(강습원장 시드 이전 등록자 과소집계 가능) · funnel_conversion 실측",
    }
    try:
        data = _http_get_json(f"{_CPO_GAS}?action=funnel_conversion")
        if not isinstance(data, dict) or not data.get("ok"):
            result["_전환_note"] = "GAS 응답 오류(ok=false 또는 형식 불일치)"
            return result
        total = data.get("total")
        if not isinstance(total, dict):
            result["_전환_note"] = "GAS 응답에 total 없음"
            return result
        rate = total.get("rate")
        if isinstance(rate, (int, float)) and not isinstance(rate, bool):
            result["문의_가입_전환율"] = rate
        inquiries = total.get("inquiries")
        if isinstance(inquiries, (int, float)) and not isinstance(inquiries, bool):
            result["전환_문의수"] = inquiries
        converted = total.get("converted")
        if isinstance(converted, (int, float)) and not isinstance(converted, bool):
            result["전환_가입수"] = converted
    except Exception as e:
        result["_전환_note"] = f"fetch 실패({type(e).__name__}): {str(e)[:80]}"
        return result  # 누적 실패 = GAS 자체 불통 가능성 → 이번달 조회도 스킵(null 안전)

    # 이번달 정밀 전환율(opt-in numerator=registered) — 누적과 독립 실패 허용(부분 성공, null 안전)
    try:
        today = datetime.now(KST)
        month_from = today.strftime("%Y-%m-01")
        month_to = today.strftime("%Y-%m-%d")
        murl = f"{_CPO_GAS}?action=funnel_conversion&numerator=registered&from={month_from}&to={month_to}"
        # 정밀모드(fcPrecise) 캐시미스 시 GAS 서버측 연산(_syncLessonRegistry_ 등)이 실측 27~30초 소요
        # (2026-07-13 시포 실측: 27.7초) — 전역 20초 타임아웃(_HTTP_TIMEOUT)로는 항상 클라이언트측
        # 타임아웃 → null. 이 호출만 45초로 연장(캐시 히트 시 <2초라 상시 지연 아님).
        mdata = _http_get_json(murl, timeout=45)
        if isinstance(mdata, dict) and mdata.get("ok") and isinstance(mdata.get("total"), dict):
            mtotal = mdata["total"]
            mrate = mtotal.get("rate")
            if isinstance(mrate, (int, float)) and not isinstance(mrate, bool):
                result["이번달_전환율"] = mrate
            minq = mtotal.get("inquiries")
            if isinstance(minq, (int, float)) and not isinstance(minq, bool):
                result["이번달_전환_문의수"] = minq
            mconv = mtotal.get("converted")
            if isinstance(mconv, (int, float)) and not isinstance(mconv, bool):
                result["이번달_전환_가입수"] = mconv
    except Exception:
        pass  # 이번달 실패해도 누적치는 이미 확보됨(부분 성공 허용)

    # ── 비교가능 기준선 ① 이번달·전화매칭(누적과 동일기준) — 정밀모드 아님(빠름·null 안전) ──
    try:
        today = datetime.now(KST)
        month_from = today.strftime("%Y-%m-01")
        month_to = today.strftime("%Y-%m-%d")
        purl = f"{_CPO_GAS}?action=funnel_conversion&from={month_from}&to={month_to}"
        pdata = _http_get_json(purl)
        if isinstance(pdata, dict) and pdata.get("ok") and isinstance(pdata.get("total"), dict):
            prate = pdata["total"].get("rate")
            if isinstance(prate, (int, float)) and not isinstance(prate, bool):
                result["이번달_전환율_전화매칭"] = prate
    except Exception:
        pass

    # ── 비교가능 기준선 ② 전월(완결)·등록월 정밀(이번달 정밀과 동일기준) — 완결월이라 서버캐시 정적 ──
    try:
        today = datetime.now(KST)
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        prev_from = last_prev.strftime("%Y-%m-01")
        prev_to = last_prev.strftime("%Y-%m-%d")   # 전월 말일
        result["전월_라벨"] = last_prev.strftime("%Y-%m")
        vurl = f"{_CPO_GAS}?action=funnel_conversion&numerator=registered&from={prev_from}&to={prev_to}"
        vdata = _http_get_json(vurl, timeout=45)
        if isinstance(vdata, dict) and vdata.get("ok") and isinstance(vdata.get("total"), dict):
            vtotal = vdata["total"]
            vrate = vtotal.get("rate")
            if isinstance(vrate, (int, float)) and not isinstance(vrate, bool):
                result["전월_전환율"] = vrate
            vinq = vtotal.get("inquiries")
            if isinstance(vinq, (int, float)) and not isinstance(vinq, bool):
                result["전월_전환_문의수"] = vinq
            vconv = vtotal.get("converted")
            if isinstance(vconv, (int, float)) and not isinstance(vconv, bool):
                result["전월_전환_가입수"] = vconv
    except Exception:
        pass

    return result


# utm_source 코드(cta_utm.py CHANNEL_UTM 발행 태그) → 유입채널 정규 라벨.
# Survey.js _canonicalChannel_() 정규식과 정합 확인됨(naver_blog/naver_cafe 모두 '네이버'로 귀속,
# instagram→인스타그램, danggn→당근마켓, kakao→카카오톡). 매핑 밖 자유텍스트 유입은 집계 제외(날조 금지).
_UTM_TO_CANON_CHANNEL = {
    "instagram":  "인스타그램",
    "naver_blog": "네이버",
    "naver_cafe": "네이버",
    "danggn":     "당근마켓",
    "kakao":      "카카오톡",
}


def _cmo_channel_funnel() -> dict:
    """
    cmo 채널별 문의→가입 전환율 — funnel_conversion(byChannel) 실측(2026-07-15 클릭 지수 제거·GM 결정).
    ⚠️ 문의·가입 모두 전체 누적(기간 무필터, GAS 기본 응답 기준).
    반환: {"채널별_문의전환": {채널명: {문의, 가입, 문의_가입_전환율}}|None, "_채널전환_note": str}
    """
    result: dict = {
        "채널별_문의전환": None,
        "_채널전환_note": (
            "문의·가입 전체 누적(기간무필터) · UTM코드 매핑 채널만(instagram/naver_blog/naver_cafe/danggn/kakao) · "
            "funnel_conversion byChannel 실측"
        ),
    }

    inquiries_by_channel: dict[str, dict] = {}
    try:
        funnel_data = _http_get_json(f"{_CPO_GAS}?action=funnel_conversion")
        if not isinstance(funnel_data, dict) or not funnel_data.get("ok"):
            result["_채널전환_note"] = "funnel_conversion 응답 오류(ok=false 또는 형식 불일치)"
            return result
        by_channel_arr = funnel_data.get("byChannel")
        if not isinstance(by_channel_arr, list):
            result["_채널전환_note"] = "funnel_conversion byChannel 없음"
            return result
        for row in by_channel_arr:
            if not isinstance(row, dict):
                continue
            ch = row.get("channel")
            if ch in _UTM_TO_CANON_CHANNEL.values():
                inquiries_by_channel[ch] = {
                    "문의": row.get("inquiries"),
                    "가입": row.get("converted"),
                    "문의_가입_전환율": row.get("rate"),
                }
    except Exception as e:
        result["_채널전환_note"] = f"funnel_conversion fetch 실패({type(e).__name__}): {str(e)[:80]}"
        return result

    if not inquiries_by_channel:
        result["_채널전환_note"] += " · 매핑된 채널 문의 데이터 없음"
        return result

    result["채널별_문의전환"] = inquiries_by_channel
    return result


def _sales_target_total() -> int | float | None:
    """월 목표매출 총액(고정) — status/sales_targets.json 정본(GM 결재). 실패 시 None."""
    try:
        data = json.loads(SALES_TARGETS_PATH.read_text(encoding="utf-8"))
        total = data.get("monthly_target_total")
        return total if isinstance(total, (int, float)) and not isinstance(total, bool) else None
    except Exception:
        return None


def _cfo_sales_month() -> dict:
    """
    cfo 최근 마감월 매출 실적 실측 — 배354 측정 개통.
    소스: 매출·업무 메가 GAS action=sales_monthly('26년 매출 분석' AV3:AV14 정본 미러).
    ⚠️ 진행중인 이번 달은 부분 실적이라 목표(월 고정)대비 왜곡 → curMonth 직전(마감완료)월을 사용.
    반환: {"sales_month": 실적원 또는 null, "sales_month_label": "YYYY-MM", "sales_month_target": 목표원,
           "_sales_note": str}
    """
    target = _sales_target_total()
    result: dict = {
        "sales_month": None,
        "sales_month_label": None,
        "sales_month_target": target,
        "_sales_note": "측정 개통 전",
    }
    try:
        data = _http_get_json(f"{_CFO_GAS}?action=sales_monthly", timeout=45)
        if not isinstance(data, dict) or not data.get("ok"):
            result["_sales_note"] = "GAS 응답 오류(ok=false 또는 형식 불일치)"
            return result
        cur_month = data.get("curMonth")
        months = data.get("months") or []
        if not isinstance(cur_month, int) or not months:
            result["_sales_note"] = "curMonth/months 없음"
            return result
        closed_m = cur_month - 1
        if closed_m < 1:
            result["_sales_note"] = "연초(1월 진행중) — 마감완료월 없음"
            return result
        row = next((r for r in months if isinstance(r, dict) and r.get("m") == closed_m), None)
        val = row.get("value") if isinstance(row, dict) else None
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            result["_sales_note"] = f"{closed_m}월 마감 실적 미확정(null)"
            return result
        label = (row.get("label") if isinstance(row, dict) else None) or f"{data.get('year')}-{closed_m:02d}"
        result["sales_month"] = val
        result["sales_month_label"] = label
        result["_sales_note"] = f"{label}(최근 마감월) 실적 · sales_monthly GAS 실측"
    except Exception as e:
        result["_sales_note"] = f"fetch 실패({type(e).__name__}): {str(e)[:80]}"
    return result


def _count_gm_unrouted(rows: list) -> int:
    """todo_list 행 중 생성자='김남욱GM'·담당자 공란인 건수 — 아직 아무에게도 안 간
    GM 원본 기록(배324 실측: 접수 자리=생성자 필드, 담당자 필드 아님)."""
    n = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        if str(r.get("생성자", "")).strip() != "김남욱GM":
            continue
        if str(r.get("담당자", "")).strip():
            continue
        n += 1
    return n


def _ceo_gm_record_gap() -> dict:
    """GM기록 미반영 건수(배358 · 2026-08-04). todo_list(_CFO_GAS 재사용, 새 GAS 없음)에서
    생성자='김남욱GM'·담당자 공란 행 = 월간운영계획으로 아직 안 흘러간 GM 원본 기록.
    실패=None(0 위장 금지)."""
    result: dict = {"GM기록_미반영": None, "_GM기록_note": "측정 전"}
    try:
        data = _http_get_json(f"{_CFO_GAS}?action=todo_list")
        if not isinstance(data, dict) or not (data.get("ok") or data.get("success")):
            result["_GM기록_note"] = "todo_list GAS 응답 오류(ok=false 또는 형식 불일치)"
            return result
        rows = data.get("data") or data.get("todos")
        if not isinstance(rows, list):
            result["_GM기록_note"] = "todo_list 응답에 rows 없음"
            return result
        result["GM기록_미반영"] = _count_gm_unrouted(rows)
        result["_GM기록_note"] = "todo_list 생성자='김남욱GM' & 담당자 공란 카운트(배324 실측 방법)"
    except Exception as e:
        result["_GM기록_note"] = f"fetch 실패({type(e).__name__}): {str(e)[:80]}"
    return result


def _count_done_reply_gap(ships: list, by_fid: dict, stage_rank, done_rank: int) -> int:
    """DONE 배 중 **feedback_id 필드로 정확히 연결된 것만** 세되, 시트 처리상태가
    '처리완료' **가 아닌**(rank != done_rank — rank<done_rank 아님. '<' 를 쓰면 구버전
    자동라벨 같은 미인식 문구(rank=99)가 "이미 앞선 단계"로 오판돼 새는 걸 배358 2차
    진단에서 실측했다) 건을 미회신으로 센다.
    note·title 텍스트로 FB…ID 를 찾는 폴백은 쓰지 않는다 — cpo_staff_feedback_watch.
    detect_done_reopen_drift() 의 문서화된 교훈(FB260801-152607 실사고: 무관한 배가
    접수ID를 한 번 언급했다는 이유로 오탐)과 같은 함정이라, 실제로 다시 재현해 확인했다
    (배299·CLI ad-hoc 병합배가 note 안에 FB260725-114820 을 언급만 했을 뿐인데 걸림)."""
    n = 0
    for ship in ships:
        if not isinstance(ship, dict) or ship.get("status") != "DONE":
            continue
        fid = str(ship.get("feedback_id") or "").strip()
        if not fid:
            continue
        row = by_fid.get(fid)
        if row is None:
            continue
        if stage_rank(str(row.get("처리상태") or "")) != done_rank:
            n += 1
    return n


def _ceo_staff_reply_gap() -> dict:
    """실무진 회신 미완료 건수(배358, 2026-08-04 정의 2차 수정 — 팀장 지적: ①오늘 막
    접수된 PENDING 건까지 세면 절대 0이 안 되는 죽은 지표다 ②'<' 비교와 note 텍스트
    폴백은 오탐을 만든다는 걸 재현 확인). **배가 DONE이고 feedback_id 필드로 정확히
    연결된 시트 행이 아직 처리완료가 아닌 것만** 센다.
    새 GAS 없음 — cpo_staff_feedback_watch 의 fetch_feedback·_stage_rank 그대로 재사용.
    ⚠️ feedback_id 필드가 없는 구세대 배(예: 배114/FB260725-114820)는 이 지표가 못 잡는다
    — note 텍스트로 잇는 건 위 도크스트링의 이유로 안전하지 않아 일부러 안 한다. 그런
    배는 배299(시토, 회신 통로 자체 결함) 쪽 실증거로 별도 취급."""
    result: dict = {"실무진_회신_미완료": None, "_실무진회신_note": "측정 전"}
    try:
        sys.path.insert(0, str(ROOT / "scripts" / "collectors"))
        from cpo_staff_feedback_watch import fetch_feedback, _stage_rank, STAFF_STATUS_DONE  # type: ignore
        rows, err = fetch_feedback()
        if rows is None:
            result["_실무진회신_note"] = f"staff_feedback_list 실패: {err}"
            return result
        by_fid = {str(r.get("접수ID") or "").strip(): r for r in rows if r.get("접수ID")}
        archive = json.loads((ROOT / "status" / "_queue_archive.json").read_text(encoding="utf-8"))
        done_rank = _stage_rank(STAFF_STATUS_DONE)
        n = _count_done_reply_gap(_load_queue() + archive, by_fid, _stage_rank, done_rank)
        result["실무진_회신_미완료"] = n
        result["_실무진회신_note"] = (
            "배 DONE & feedback_id 연결 & 시트 처리완료 미도달 카운트"
            "(note 텍스트 폴백 미사용 — feedback_id 없는 구세대 배는 별도 취급, 배299 참조)"
        )
    except FileNotFoundError:
        result["_실무진회신_note"] = "_queue_archive.json 없음"
    except Exception as e:
        result["_실무진회신_note"] = f"읽기 실패({type(e).__name__}): {str(e)[:80]}"
    return result


def _integration_health() -> str | None:
    """
    integration_health.py check_bridges() 결과 요약.
    all_ok=True→"ok" / False→"warn" / 예외→None
    """
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from integration_health import check_bridges  # type: ignore
        results = check_bridges()
        all_ok = all(ok for _, ok, _ in results)
        return "ok" if all_ok else "warn"
    except Exception:
        return None


# ── 메인 집계 ─────────────────────────────────────────────────────────────────

def collect() -> dict:
    ships    = _load_queue()
    unpushed = _unpushed_count()
    mirror   = _mirror_ok()
    health   = _integration_health()

    coo_check = _coo_check_rate()

    roles_data: dict[str, dict] = {}
    for role in ("ceo", "coo", "cfo", "cmo", "cto", "chro", "cpo"):
        stats = _role_stats(ships, role)
        stats.update(_role_stalled_ships(ships, role))  # 멈춘 배(전 역할 공통) — GM 지적 2026-08-04
        if role == "ceo":
            # GM기록 미반영·실무진 회신 미완료 병합 (배358 · 아침 자가점검 두 지표 자동화)
            stats.update(_ceo_gm_record_gap())
            stats.update(_ceo_staff_reply_gap())
        if role == "coo":
            # 점검완료율 병합 (지원부 한정 · 4부서 전체는 null)
            stats.update(coo_check)
        if role == "cpo":
            # 당월 LOSS율 병합 (배299 cpo_churn_stats 실측 · 역방향 지표)
            stats.update(_cpo_loss_rate())
            # 문의→가입 전환율 병합 (배443 funnel_conversion 실측 · null 안전)
            stats.update(_cpo_funnel_conversion())
        if role == "cfo":
            # 최근 마감월 매출 실적 병합 (배354 측정 개통 · sales_monthly GAS 실측 · null 안전)
            stats.update(_cfo_sales_month())
        if role == "cmo":
            # 채널별 문의→가입 전환율 병합 (funnel_conversion byChannel 실측 · null 안전)
            stats.update(_cmo_channel_funnel())
        roles_data[role] = stats

    now_kst = datetime.now(KST)
    return {
        "_doc": (
            "KPI 자동집계 결과. 측정 불가=null(거짓 숫자 금지). "
            "생성: kpi_collector.py | 스케줄: 일 2회"
        ),
        "generated_at":     now_kst.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "generated_at_kst": now_kst.strftime("%Y-%m-%d %H:%M KST"),
        "global": {
            "unpushed":  unpushed,
            "mirror_ok": mirror,
            "health":    health,
        },
        "roles": roles_data,
    }


# ── 대표님·회장님 보고건 스냅샷 (GM 지시 2026-08-06 · 배432) ─────────────────────
# GM: "시트 하루 한 번만 읽는 방식으로 같이 해줘." 웰리 실측 — 라이브 첫 표시까지 회장님 0.2초 ·
# GM 0.7초인데 **대표님 칸만 3.7초**였다. 그 칸만 매번 업무 시트를 새로 조회해서다.
# ▸새 수집기·새 예약작업을 만들지 않는다(약속 L21) — 이미 하루 2회 도는 이 수집기에 얹는다.
# ▸판정을 두 벌로 만들지 않는다: 화면(_owner_directive.js filterRows)과 같은 세 조건
#   (담당자에 '김남욱' 포함 · 상태 진행중/보류 · 내용의 '대표님 보고건' 표식)만 쓰고,
#   표식은 참/거짓으로만 담는다. **내용 본문은 담지 않는다**(스냅샷은 목록용).
# ▸화면은 이 스냅샷을 먼저 그리고 라이브 조회가 끝나면 덮어쓴다(2단) — 결재 상태는 실시간으로
#   바뀌므로 스냅샷만 믿으면 안 된다.
OWNER_SNAPSHOT_PATH = ROOT / "status" / "owner_directive_snapshot.json"
_OWNER_MARK = "대표님 보고건"
_OWNER_FIELDS = ("id", "업무명", "담당자", "상태", "시작일", "종료일",
                 "카테고리", "결재요청", "결재상태", "결재완료시각")


def publish_owner_directive_snapshot() -> dict:
    """대표님·회장님 보고건 목록 스냅샷 발행. 실패해도 수집기 전체를 막지 않는다."""
    out = {"_doc": "대표님·회장님 보고건 목록 스냅샷(배432). 화면은 이 값으로 먼저 그리고 "
                   "라이브 조회로 반드시 덮어쓴다 — 결재 상태는 실시간으로 바뀐다.",
           "generated_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
           "rows": [], "error": None}
    try:
        data = _http_get_json(f"{_CFO_GAS}?action=todo_list&include_gm=1")
        rows = (data or {}).get("data") or (data or {}).get("todos")
        if not isinstance(rows, list):
            out["error"] = "todo_list 응답에 rows 없음"
            return out
        picked = []
        for r in rows:
            if "김남욱" not in str(r.get("담당자") or ""):
                continue
            if str(r.get("상태") or "").strip() not in ("진행중", "보류"):
                continue
            item = {k: r.get(k) for k in _OWNER_FIELDS}
            item["ceo_mark"] = _OWNER_MARK in str(r.get("내용") or "")
            picked.append(item)
        picked.sort(key=lambda x: str(x.get("종료일") or "9999-99-99"))
        out["rows"] = picked
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:100]}"
    OWNER_SNAPSHOT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    return out


def main() -> None:
    data = collect()
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    snap = publish_owner_directive_snapshot()
    ceo_n = sum(1 for r in snap["rows"] if r.get("ceo_mark"))
    print(f"  대표님 보고건 스냅샷: {ceo_n}건(회장님·기타 포함 {len(snap['rows'])}건)"
          + (f" — 실패: {snap['error']}" if snap.get("error") else ""))

    # 배선 수복(배CTO-2026-08-08): 스냅샷 파일을 쓴 뒤 커밋·푸시가 없었다 — 화면은 raw.githubusercontent
    # 를 먼저 그리므로 로컬 갱신만으론 라이브 반영 불가. safe_commit 으로 이 관문에 흡수(약속 L21).
    try:
        _snap_r = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "safe_commit.py"),
             "-m", "chore(cto): 대표님 보고건 스냅샷 자동 발행 (owner_directive_snapshot)",
             "--", "status/owner_directive_snapshot.json"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=180,
        )
        _snap_tail = (_snap_r.stdout or "").strip().splitlines()
        print("  [owner_snapshot] " + (_snap_tail[0] if _snap_tail else "safe_commit 출력 없음"))
        if _snap_r.returncode != 0:
            print(f"  [owner_snapshot] safe_commit rc={_snap_r.returncode} — 파일은 로컬에 남음, 다음 회차 재시도")
    except Exception as _snap_e:
        print(f"  [owner_snapshot] 커밋 실패(무해 — 파일은 로컬에 남음): {type(_snap_e).__name__}: {str(_snap_e)[:120]}")

    g = data["global"]
    print(f"[kpi_collector] {data['generated_at_kst']}")
    print(f"  global: unpushed={g['unpushed']}  mirror={g['mirror_ok']}  health={g['health']}")
    for role, v in data["roles"].items():
        extra = ""
        if role == "ceo" and (v.get("GM기록_미반영") is not None or v.get("실무진_회신_미완료") is not None):
            extra = f"  GM기록_미반영={v.get('GM기록_미반영')}  실무진_회신_미완료={v.get('실무진_회신_미완료')}"
        if role == "coo" and v.get("지원부_점검완료율") is not None:
            extra = (
                f"  지원부점검완료율(월간대표)={v['지원부_점검완료율']}"
                f"({v['지원부_완료']}/{v['지원부_전체']}, 기준={v.get('지원부_점검완료율_기준')})"
                f"  당일라이브={v.get('지원부_점검완료율_당일라이브')}"
                f"({v.get('지원부_당일라이브_완료')}/{v.get('지원부_당일라이브_전체')})"
            )
        if role == "cpo" and v.get("월_LOSS율") is not None:
            extra = f"  월_LOSS율={v['월_LOSS율']}(역방향·낮을수록좋음, {v['월_LOSS건수']}건/{v['유효회원수']}명)"
        if role == "cpo" and v.get("문의_가입_전환율") is not None:
            extra += f"  전환율={v['문의_가입_전환율']}%({v['전환_가입수']}/{v['전환_문의수']})"
        if role == "cfo" and v.get("sales_month") is not None:
            extra = f"  sales_month={v['sales_month']}({v.get('sales_month_label')}) target={v.get('sales_month_target')}"
        if role == "cmo" and v.get("채널별_문의전환") is not None:
            extra = f"  채널별_문의전환={v['채널별_문의전환']}"
        stall = (f"  멈춘배={v['멈춘배_건수']}(최장 {v['멈춘배_최장일수']}일·배{v['멈춘배_최장배번호']}·{v.get('멈춘배_최장상태')})"
                  if v.get("멈춘배_건수") else "  멈춘배=0")
        print(f"  {role:5s}: 완결률={v['완결률']}  완료={v['완료']}  활성={v['활성']}{stall}{extra}")
    print(f"  -> {OUT_PATH}")

    # 북극성 도달율 재산출(best-effort · 실패해도 collector 성공 유지). kpi_values 갱신 직후 물림.
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "northstar_reach.py")],
            cwd=str(ROOT), timeout=60,
        )
    except Exception as e:
        print(f"  [northstar_reach 재산출 스킵] {type(e).__name__}: {str(e)[:80]}")


def _selftest() -> int:
    """자기검사(배358) — GM기록 미반영 카운트 로직만 프레임워크 없이 assert."""
    rows = [
        {"생성자": "김남욱GM", "담당자": ""},
        {"생성자": "김남욱GM", "담당자": "  "},
        {"생성자": "김남욱GM", "담당자": "나우열M"},
        {"생성자": "나우열M", "담당자": ""},
        {"생성자": "김남욱GM"},  # 담당자 필드 자체가 없어도 공란 취급
    ]
    n = _count_gm_unrouted(rows)
    assert n == 3, n

    sys.path.insert(0, str(ROOT / "scripts" / "collectors"))
    from cpo_staff_feedback_watch import _stage_rank, STAFF_STATUS_DONE  # type: ignore
    done_rank = _stage_rank(STAFF_STATUS_DONE)
    by_fid = {
        "FB1": {"처리상태": "처리완료"},        # 이미 회신됨 — 안 셈
        "FB2": {"처리상태": "확인중"},          # DONE인데 회신 못 미침 — 셈
        "FB3": {"처리상태": "진행중"},          # 미인식 구버전 라벨(rank=99) — 회신 아님, 셈
    }
    ships = [
        {"status": "DONE", "feedback_id": "FB1"},
        {"status": "DONE", "feedback_id": "FB2"},
        {"status": "DONE", "feedback_id": "FB3"},
        {"status": "PENDING", "feedback_id": "FB2"},          # 진행중 배 — 애초에 스킵
        {"status": "DONE", "note": "…FB1 언급만…"},           # feedback_id 필드 없음 — 텍스트 폴백 안 써서 스킵
    ]
    gap = _count_done_reply_gap(ships, by_fid, _stage_rank, done_rank)
    assert gap == 2, gap  # FB2·FB3 만 잡혀야 함

    import datetime as _dt
    fixed_today = _dt.date(2026, 8, 4)
    stall_ships = [
        # 배117 실측 그대로 — enqueued_at=07-25(10일)인데 updated_at 은 오늘(자동 재기록).
        # updated_at 을 봤다면 안 잡혔을 것 — 이게 회귀 테스트다.
        {"clevel": "cpo", "status": "IN_PROGRESS", "short_no": 117,
         "enqueued_at": "2026-07-25", "updated_at": "2026-08-04"},
        {"clevel": "cpo", "status": "PENDING", "short_no": 2, "enqueued_at": "2026-08-01"},   # 3일 — 정상(7일 미만)
        {"clevel": "cpo", "status": "DONE", "short_no": 3, "enqueued_at": "2026-07-01"},      # DONE — 대상 아님
        {"clevel": "coo", "status": "IN_PROGRESS", "short_no": 9, "enqueued_at": "2026-07-28"},  # 7일 — 경계값, 멈춤
    ]
    r_cpo = _role_stalled_ships(stall_ships, "cpo", today=fixed_today)
    assert r_cpo == {"멈춘배_건수": 1, "멈춘배_최장일수": 10, "멈춘배_최장배번호": 117, "멈춘배_최장상태": "IN_PROGRESS"}, r_cpo
    r_coo = _role_stalled_ships(stall_ships, "coo", today=fixed_today)
    assert r_coo["멈춘배_건수"] == 1 and r_coo["멈춘배_최장일수"] == 7, r_coo

    print("selftest OK — GM기록_미반영", n, "건 · 실무진_회신_미완료(픽스처)", gap,
          "건 · 멈춘배(cpo, 픽스처)", r_cpo)
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    main()
