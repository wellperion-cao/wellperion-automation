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


def _role_stats(ships: list[dict], role: str) -> dict:
    """role별 완료/활성/완결률 계산. 완결률 = DONE / (DONE + ACTIVE)."""
    role_ships = [s for s in ships if isinstance(s, dict) and s.get("clevel") == role]
    done   = sum(1 for s in role_ships if s.get("status") in DONE)
    active = sum(1 for s in role_ships if s.get("status") in ACTIVE)
    total  = done + active
    rate   = round(done / total, 4) if total > 0 else None
    return {"완결률": rate, "완료": done, "활성": active}


def _unpushed_count() -> int | None:
    """origin/master..HEAD 미푸시 커밋 수. 실패 시 None."""
    try:
        r = subprocess.run(
            ["git", "rev-list", "origin/master..HEAD", "--count"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30,
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
# 회원 문의/이탈 GAS (문의회원.html과 동일 정본 — cpo_churn_stats 등)
_CPO_GAS = (
    "https://script.google.com/macros/s/"
    "AKfycbzdwSCCSSJ6JXLDoWuo7HG0JmBM2iy10TujFQ_O5JbTjnWaN7gOk-ddA4IAvsNfelg0xA/exec"
)
# 매출·업무 메가 GAS (.deploy-todo/업무&결재 현황.js — 월간운영계획.html·헌법한장.html과 동일 정본)
# action=sales_monthly → '26년 매출 분석' AV3:AV14 미러(회사 전체 월별 마감 총매출). cao 인증 배포 완료(배354 phase1, 커밋 859a6bfa) — 신규 배포 불필요.
_CFO_GAS = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)
_HTTP_TIMEOUT = 20
SALES_TARGETS_PATH = ROOT / "status" / "sales_targets.json"


def _http_get_json(url: str) -> object:
    """GET → 파싱된 JSON 객체. 예외는 호출부에서 처리."""
    sep = "&" if "?" in url else "?"
    busted = f"{url}{sep}_cb={int(time.time())}"
    req = urllib.request.Request(
        busted, headers={"Cache-Control": "no-cache"}
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _coo_check_rate() -> dict:
    """
    지원부 일일 점검완료율 (오늘 기준).
    소스: 점검 GAS today_live?dept=support&date=YYYY-MM-DD (분모 정합 통로 · 배239)
    반환: {"지원부_점검완료율": 0~1 또는 null, "지원부_완료": int, "지원부_전체": int,
           "4부서_점검완료율": null, "_note": str}
    — 4부서 전체 완료율은 이 GAS로 측정 불가(지원부 데이터만 제공) → null 유지.
    """
    result: dict = {
        "지원부_점검완료율": None,
        "지원부_완료": None,
        "지원부_전체": None,
        "4부서_점검완료율": None,
        "_note": "4부서전체=미측정(GAS가지원부한정)",
    }
    try:
        today_str = datetime.now(KST).strftime("%Y-%m-%d")
        # today_live = 분모 정합 통로(주말 오후조 제외·전체 스케줄 기대치 기준, 배239 라이브).
        # 구 get_today_summary(스냅샷 rows 25/25=100% 버그) 폐기 — 소스별 분모 불일치 원인.
        url = f"{_CHECK_GAS}?action=today_live&dept=support&date={today_str}"
        data = _http_get_json(url)
        if not isinstance(data, dict) or not data.get("total"):
            result["_note"] = "today_live 분모 0/응답없음(점검 미시작 또는 GAS 오류)"
            return result
        total = data.get("total")
        done  = data.get("done") or 0
        rate  = round(done / total, 4) if total > 0 else None
        result["지원부_점검완료율"] = rate
        result["지원부_완료"]       = done
        result["지원부_전체"]       = total
        result["_note"] = "4부서전체=미측정(GAS가지원부한정) · 지원부=today_live 분모정합 통로(진행중 당일 포함)"
    except Exception as e:
        result["_note"] = f"fetch 실패({type(e).__name__}): {str(e)[:80]}"
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
        "_전환_note": "누적=전화매칭 기준(기간별 부정확 가능) · 이번달=등록일 기준 정밀(numerator=registered, 강습원장 시드 이전 등록자는 과소집계 가능) · funnel_conversion 실측",
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
        mdata = _http_get_json(murl)
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
    return result


def _cmo_channel_clicks() -> dict:
    """
    cmo 채널별 유입 클릭수 실측 — .deploy-funnel/Survey.js:2072 click_stats action(클릭로그 시트).
    동일 GAS(_CPO_GAS)가 서빙 — PII 없음(집계 수치만).
    ⚠️ 이것은 '노출→문의 전환율'의 분모(노출)가 아니라 분자측 신호(채널 귀속 클릭수)만 실측.
    문의페이지 도달 후 클릭(폼 진입·소셜 아이콘)을 UTM소스별로 집계한 값 — 콘텐츠 자체 노출(IG 도달수 등)은
    Meta Graph API 토큰 필요(🔒 GM 결재) → 미측정 유지(가짜 분모 금지 · ssot/약속.json L05).
    반환: {"채널별_클릭수": {utm_source: count}|None, "총_클릭수": int|None, "_클릭_note": str}
    """
    result: dict = {
        "채널별_클릭수": None,
        "총_클릭수": None,
        "_클릭_note": "노출(분모) 미측정 — IG Graph API 토큰 필요(GM 결재). 채널귀속 클릭(분자)만 실측 · click_stats 실측",
    }
    try:
        data = _http_get_json(f"{_CPO_GAS}?action=click_stats")
        if not isinstance(data, dict) or not data.get("ok"):
            result["_클릭_note"] = "GAS 응답 오류(ok=false 또는 형식 불일치)"
            return result
        by_src = data.get("byUtmSource")
        if isinstance(by_src, dict):
            result["채널별_클릭수"] = by_src
        total = data.get("total")
        if isinstance(total, (int, float)) and not isinstance(total, bool):
            result["총_클릭수"] = total
    except Exception as e:
        result["_클릭_note"] = f"fetch 실패({type(e).__name__}): {str(e)[:80]}"
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


def _cmo_channel_conversion() -> dict:
    """
    cmo 채널별 클릭→문의(→가입) 전환율 — click_stats(byUtmSource) × funnel_conversion(byChannel) 조합(배 신규).
    ⚠️ 정직 한계(대시보드 동일 문구 병기):
       ① 노출(분모) 미측정 — 이 값은 '클릭 대비 문의' 채널레벨 비율일 뿐 도달수 기준 전환율 아님.
       ② 개별 클릭↔문의 1:1 조인 아님(둘 다 채널 단위 집계 합산 비율).
       ③ 클릭·문의 모두 전체 누적(기간 무필터, 각 GAS 기본 응답 기준).
       ④ _UTM_TO_CANON_CHANNEL 매핑 밖 자유텍스트 유입(소개·오프라인 등)은 클릭 쪽 대응 불가 → 집계 제외.
       ⑤ 비율>100%(문의가 클릭보다 많음) = 네이버·당근 등은 문의 bucket에 검색·플레이스·자기신고 등
          UTM 미태깅 유입이 함께 섞여 클릭(UTM만) 대비 문의가 부풀어 보이는 것 — 전환율 미산출(measurable=False),
          클릭≤문의(즉 비율≤100%)·클릭>0인 채널(예: 인스타그램=양방향 UTM 귀속)만 실제 %로 표기.
    반환: {"채널별_클릭문의전환": {채널명: {클릭, 문의, 가입, 클릭_문의_전환율, measurable, 상태,
           문의_가입_전환율}}|None, "_채널전환_note": str}
    """
    result: dict = {
        "채널별_클릭문의전환": None,
        "_채널전환_note": (
            "노출(분모) 미측정 · 클릭 대비 문의 채널레벨 비율(1:1 조인 아님) · "
            "클릭·문의 전체 누적(기간무필터) · UTM코드 매핑 채널만(instagram/naver_blog/naver_cafe/danggn/kakao) · "
            "비율>100%=클릭(UTM) 외 자기신고·플레이스/검색 유입이 문의 bucket에 섞여 전환율 미산출(measurable=False) · "
            "인스타그램 등 클릭·문의 양쪽 UTM 귀속 채널만 실% 표기"
        ),
    }

    clicks_by_channel: dict[str, float] = {}
    try:
        click_data = _http_get_json(f"{_CPO_GAS}?action=click_stats")
        if not isinstance(click_data, dict) or not click_data.get("ok"):
            result["_채널전환_note"] = "click_stats 응답 오류(ok=false 또는 형식 불일치)"
            return result
        by_utm = click_data.get("byUtmSource")
        if not isinstance(by_utm, dict):
            result["_채널전환_note"] = "click_stats byUtmSource 없음"
            return result
        for utm_key, cnt in by_utm.items():
            channel = _UTM_TO_CANON_CHANNEL.get(str(utm_key))
            if channel is None or not isinstance(cnt, (int, float)) or isinstance(cnt, bool):
                continue
            clicks_by_channel[channel] = clicks_by_channel.get(channel, 0) + cnt
    except Exception as e:
        result["_채널전환_note"] = f"click_stats fetch 실패({type(e).__name__}): {str(e)[:80]}"
        return result

    inquiries_by_channel: dict[str, dict] = {}
    try:
        funnel_data = _http_get_json(f"{_CPO_GAS}?action=funnel_conversion")
        if not isinstance(funnel_data, dict) or not funnel_data.get("ok"):
            result["_채널전환_note"] += " · funnel_conversion 응답 오류(ok=false 또는 형식 불일치)"
            return result
        by_channel_arr = funnel_data.get("byChannel")
        if not isinstance(by_channel_arr, list):
            result["_채널전환_note"] += " · funnel_conversion byChannel 없음"
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
        result["_채널전환_note"] += f" · funnel_conversion fetch 실패({type(e).__name__}): {str(e)[:80]}"
        return result

    combined: dict[str, dict] = {}
    for channel in set(list(clicks_by_channel.keys()) + list(inquiries_by_channel.keys())):
        clicks = clicks_by_channel.get(channel)
        inq_info = inquiries_by_channel.get(channel, {})
        inquiries = inq_info.get("문의")

        has_clicks = isinstance(clicks, (int, float)) and clicks > 0
        has_inq = isinstance(inquiries, (int, float))
        # measurable = 클릭>0 이고 문의≤클릭(비율≤100%)일 때만 — 그 외(클릭 없음/0 또는 문의>클릭)는
        # UTM 미태깅 자기신고·검색·플레이스 유입이 문의 bucket에 섞여 신뢰 불가(비고 ⑤ 참조).
        measurable = bool(has_clicks and has_inq and inquiries <= clicks)
        rate = round(inquiries / clicks * 100, 1) if measurable else None
        상태 = "실측" if measurable else "추적밖유입우세"
        combined[channel] = {
            "클릭": clicks,
            "문의": inquiries,
            "가입": inq_info.get("가입"),
            "클릭_문의_전환율": rate,
            "measurable": measurable,
            "상태": 상태,
            "비고": (
                None if measurable
                else "추적 밖 유입 우세(자기신고·플레이스/검색) — 전환율 측정 불가"
            ),
            "문의_가입_전환율": inq_info.get("문의_가입_전환율"),
        }

    if not combined:
        result["_채널전환_note"] += " · 매핑된 채널 클릭·문의 데이터 없음"
        return result

    result["채널별_클릭문의전환"] = combined
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
        data = _http_get_json(f"{_CFO_GAS}?action=sales_monthly")
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
            # 채널별 유입 클릭수 병합 (click_stats 실측 · 노출 분모는 미측정 유지 · null 안전)
            stats.update(_cmo_channel_clicks())
            # 채널별 클릭→문의(→가입) 전환율 병합 (click_stats × funnel_conversion 조합 · 노출분모 없이 채널레벨 · null 안전)
            stats.update(_cmo_channel_conversion())
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
            extra = f"  지원부점검완료율={v['지원부_점검완료율']}({v['지원부_완료']}/{v['지원부_전체']})"
        if role == "cpo" and v.get("월_LOSS율") is not None:
            extra = f"  월_LOSS율={v['월_LOSS율']}(역방향·낮을수록좋음, {v['월_LOSS건수']}건/{v['유효회원수']}명)"
        if role == "cpo" and v.get("문의_가입_전환율") is not None:
            extra += f"  전환율={v['문의_가입_전환율']}%({v['전환_가입수']}/{v['전환_문의수']})"
        if role == "cfo" and v.get("sales_month") is not None:
            extra = f"  sales_month={v['sales_month']}({v.get('sales_month_label')}) target={v.get('sales_month_target')}"
        if role == "cmo" and v.get("총_클릭수") is not None:
            extra = f"  총클릭수={v['총_클릭수']}  채널별={v.get('채널별_클릭수')}"
        if role == "cmo" and v.get("채널별_클릭문의전환") is not None:
            extra += f"  채널별_클릭문의전환={v['채널별_클릭문의전환']}"
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
