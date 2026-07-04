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
_HTTP_TIMEOUT = 20


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
    소스: 점검 GAS get_today_summary?date=YYYY-MM-DD
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
    cpo 문의→가입 전환율 실측 — .deploy-funnel/Survey.js:3176-3297 funnel_conversion action.
    동일 CPO GAS(_CPO_GAS) — PII 없음, 집계 수치만(전화번호 등 개인정보 미포함).
    ⚠️ convBasis=누적 전화매칭 기준(등록일 미사용) — 기간별 부정확·과소집계 가능(GAS 응답 정본 참조).
    반환: {"문의_가입_전환율": float(%) 또는 null, "전환_문의수": int, "전환_가입수": int, "_전환_note": str}
    ⚠️ 키명 "_note"는 _cpo_loss_rate()가 이미 점유(cpo 블록 병합 시 dict.update로 덮어써짐) — 별도 "_전환_note" 사용(무손상).
    """
    result: dict = {
        "문의_가입_전환율": None,
        "전환_문의수": None,
        "전환_가입수": None,
        "_전환_note": "누적 전화매칭 기준(기간별 부정확 가능) · funnel_conversion 실측",
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
