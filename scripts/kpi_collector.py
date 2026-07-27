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


# 점검 GAS (지원팀 일일점검 · 4부서 공용 GAS이나 데이터는 지원부만 — 정직 표기)
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
        return {
            "rate": rate, "done": sum_done, "total": sum_total,
            "month": month_str, "active_days": active_days,
        }
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
           "지원부_점검완료율_당일라이브": 0~1|null(참고), "지원부_당일라이브_완료"/"_전체": int|null,
           "4부서_점검완료율": null, "_note": str}
    — 4부서 전체 완료율은 이 GAS로 측정 불가(지원부 데이터만 제공) → null 유지.
    """
    result: dict = {
        "지원부_점검완료율": None,
        "지원부_완료": None,
        "지원부_전체": None,
        "지원부_점검완료율_기준": None,
        "지원부_점검완료율_당일라이브": None,
        "지원부_당일라이브_완료": None,
        "지원부_당일라이브_전체": None,
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


def main() -> None:
    data = collect()
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    g = data["global"]
    print(f"[kpi_collector] {data['generated_at_kst']}")
    print(f"  global: unpushed={g['unpushed']}  mirror={g['mirror_ok']}  health={g['health']}")
    for role, v in data["roles"].items():
        extra = ""
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
        print(f"  {role:5s}: 완결률={v['완결률']}  완료={v['완료']}  활성={v['활성']}{extra}")
    print(f"  -> {OUT_PATH}")

    # 북극성 도달율 재산출(best-effort · 실패해도 collector 성공 유지). kpi_values 갱신 직후 물림.
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "northstar_reach.py")],
            cwd=str(ROOT), timeout=60,
        )
    except Exception as e:
        print(f"  [northstar_reach 재산출 스킵] {type(e).__name__}: {str(e)[:80]}")


if __name__ == "__main__":
    main()
