#!/usr/bin/env python3
"""점검 현황 핵심요약 — 텔레그램 점검관리방 · 카톡 23시 공유방 공용 모듈 (단일 진실).

GM 2026-07-19 지시: 두 채널이 **동일한 3섹션 핵심요약**(🏗 시설부 / 🛠 지원부 / 🅿 주차부)을
내보내게 렌더 로직을 이 한 모듈로 단일화한다. 기존 daily_scheduler.py·kakao_daily_check_share.py에
복붙돼 갈라져 있던 로직을 통합 — 이제 양쪽이 이 모듈을 import 하므로 두 번 다시 갈라지지 않는다.

핵심요약(GM 원안 "이 정도로만"):
  🏗 시설부 = N회 점검 · 이상 유무(+기준이탈 최대 3건)
  🛠 지원부 = 종일 완료율 + 남/여 + 회차분해(요일 반영) + 짚을 점(독려 필요 회차)
  🅿 주차부 = 이슈/현황(없으면 정직 표기)

회차분해 요일 반영(문제1 근본해결):
  서버 today_live는 주말(토·일)이면 pm(오후조) 분모·분자를 0으로 반환한다
  (.deploy-check/지원팀 일일점검.js, 배173·2026-07-04 시우). 따라서 이 모듈은
  **분모(total)>0 회차만 렌더** — 주말이면 오전조·마감조 2회차, 평일이면 오전조·오후조·마감조
  3회차가 자동 정합된다(요일 하드코딩 분기 불필요·서버 스케줄을 단일 진실로 신뢰).
  홈 화면 parseGenderKpi(main.html)와 동일한 total>0 렌더 규칙과도 일치.

데이터 소스(점검 GAS · 실측·지어내기 0):
  지원부: ?action=today_live&dept=support&date=YYYY-MM-DD
  시설부: ?action=board&key=FACILITY_CHECK_YYYY-MM-DD (회수) + ?action=monthly_report&dept=facility (기준이탈)
  주차부: ?action=weekly&dept=parking

사용(라이브 미발송 · 렌더 확인용):
  python scripts/support_check_summary.py --date 2026-07-18   # 주말 렌더 확인
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# 반복 미완료 감지기(원장 기반) — soft import(없어도 무동작 폴백). GM 2026-07-19 지시3.
_scr_dir = os.path.dirname(os.path.abspath(__file__))
if _scr_dir not in sys.path:
    sys.path.insert(0, _scr_dir)
try:
    import check_incomplete_detector as _cid
    _CID_OK = True
except Exception:
    _cid = None
    _CID_OK = False

# 반복 미완료 누적 원장(지원부 v1) — daily_scheduler가 23시에 적재. status/check_incomplete_ledger.json.
CHECK_INCOMPLETE_LEDGER = Path(_scr_dir).parent / "status" / "check_incomplete_ledger.json"

# 점검 GAS(CHECK_API) — daily_scheduler.py·kakao_daily_check_share.py와 동일 배포 URL(단일 소스)
DEFAULT_GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec"
)

# 회차 표준(순서 고정) — 라벨은 실제 운영 명칭(오전조/오후조/마감조). 주말은 오후조 미운영(서버가 total=0).
_SHIFTS = [("am", "오전조"), ("pm", "오후조"), ("close", "마감조")]

# ── 회차수 신뢰 게이트 (2026-07-22 시토) ──
# 근본원인 수리 완료: saveBoard()가 store.submissions[]를 seq 기준 union 병합한다
# (.deploy-check/지원팀 일일점검.js). ★ 라이브 /exec 재배포 완료·검증됨(2026-07-22, deployment
# AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1 @170) —
# 테스트 키(FACILITY_CHECK_TEST_MERGE_20260722)로 7건 저장 후 2건 재저장해도 7건 보존됨을
# 라이브 런타임에서 실증(테스트 키는 검증 후 자가청소함). ScriptProperties 500KB 하드리밋
# 초과분(캐시 프루닝, 5일 유지)도 해소 확인(410,732B, 하드리밋 512,000B 대비 여유 확보).
# sessions=len(submissions) 신뢰 가능 → 게이트 True 전환.
FACILITY_SESSIONS_TRUSTED = True



def _num(n) -> str:
    """정수면 '32', 소수면 '32.2' (%g 스타일 — 불필요한 .0 제거)."""
    try:
        f = float(n)
    except (TypeError, ValueError):
        return str(n)
    return str(int(f)) if f.is_integer() else str(f)


FETCH_FAILED = "조회 실패"   # '진짜 0' 과 '못 읽음' 을 가르는 표식(아래 주석 참조)


def fetch_gas(params: dict, url: str = DEFAULT_GAS_URL, timeout: float = 20.0,
              tries: int = 3, require_ok: bool = True) -> dict | None:
    """GAS GET → dict(ok=true)만 반환. 끝까지 실패하면 None(정직 — 지어내기 금지).

    ★2026-08-06 GM 지적으로 재시도를 붙였다. GM 원문: "실무진들이 더 집중할 수 있게
      백엔드에서 실수가 있으면 안 돼… 실무진 힘나게 해야지 힘빠지게 하면 안 돼."
      그날 실측: 시설부가 7회차(04:23~18:35) 실제로 다 돌았는데 19:13 조회가 빈 응답을
      돌려줘 '오늘 점검 입력 없음' 으로 렌더됐고, 11분 뒤 같은 조회는 7회차를 정상으로
      읽었다. **사람은 제대로 했는데 화면이 안 했다고 말한 것** — 가장 나쁜 종류다.
      한 번 실패로 '없음' 을 만들지 않는다: 짧게 쉬며 세 번까지 다시 묻는다.
    """
    params = {**params, "_pv": int(time.time())}   # 캐시 버스트(no-store 정합)
    for attempt in range(1, max(1, tries) + 1):
        full = url + "?" + urllib.parse.urlencode({**params, "_pv": int(time.time())})
        try:
            with urllib.request.urlopen(urllib.request.Request(full), timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            # 액션에 따라 ok 를 안 싣는 응답이 있다(조별 원장 조회가 그렇다 — 최상위가
            # date/rows/checkedLedger 로 바로 온다). 그 경우만 require_ok=False 로 받는다.
            if isinstance(data, dict) and (data.get("ok") or not require_ok):
                return data
        except Exception:
            pass
        if attempt < tries:
            time.sleep(1.5 * attempt)   # 1.5s · 3s — 짧은 일시 장애를 넘긴다
    return None


# ── 지원부 ────────────────────────────────────────────────────────────────
def support_issues(d: dict) -> list[str]:
    """미점검·미달 회차를 **빠짐없이** 짚음(1개만 X). GM 2026-07-19 피드백1.
    한 구역(남/여) 전체가 0%면 "여성구역 전체 미점검(오전조·마감조)"처럼 통으로 직관 표기.
    부분 미달이면 회차별로 "여성구역 마감조 3/13(23%)". 전부 완료면 [](이상 없음)."""
    g = d.get("byGender", {}) or {}
    out: list[str] = []
    for gk, glabel in (("m", "남성구역"), ("f", "여성구역")):
        part = g.get(gk, {}) or {}
        shifts = [(lbl, int(part.get(k, 0) or 0), int(part.get(k + "Total", 0) or 0))
                  for k, lbl in _SHIFTS if int(part.get(k + "Total", 0) or 0) > 0]
        incomplete = [(lbl, dn, tt) for lbl, dn, tt in shifts if dn < tt]
        if not incomplete:
            continue
        # 구역 전체 미점검(전 회차 0) → 통으로
        if len(incomplete) == len(shifts) and all(dn == 0 for _, dn, _ in shifts):
            out.append(f"{glabel} 전체 미점검({'·'.join(l for l, _, _ in shifts)})")
        else:
            for lbl, dn, tt in incomplete:
                p = round(dn / tt * 100) if tt else 0
                out.append(f"{glabel} {lbl} {dn}/{tt}({p}%)")
    return out


def merged_unchecked_names(live: dict, shift: str) -> list[str]:
    """today_live 응답의 uncheckedByShift[shift] — m+f 미체크 항목명 병합. **정본**.
    daily_scheduler.py._merged_unchecked_names 이 이 함수를 위임(soft import) 사용한다 —
    두 곳에서 갈라지지 않도록 여기가 단일 출처. 필드 없음/빈값 → 빈 리스트(호출부가 안전하게
    줄 생략). GM go 2026-07-09(배선: 지원팀 일일점검.js handleTodayLive) ·
    22:30 보고 통합 GM 2026-07-23(시토)."""
    bucket = (live.get("uncheckedByShift") or {}).get(shift) or {}
    names = list(bucket.get("m") or []) + list(bucket.get("f") or [])
    return [str(n).strip() for n in names if str(n or "").strip()]


_MAX_UNCHECKED_NAMES = 8  # 회차당 미체크 항목명 표시 최대 개수(초과 시 '외 N')


def support_nudge_lines(d: dict) -> list[str]:
    """🔔 독려 대상 — **아직 미완인 회차만** 회차별 남/여 진행 + 미체크 항목명(있으면).
    GM 2026-07-23 지시(시토): 17시·22시 개별 독려 알림에만 있던 미체크 항목명을
    22:30 하루정리 보고에도 상시 반영(두 채널이 같은 정보를 보게). 미완 회차가 하나도
    없으면 빈 리스트(블록 자체 생략). uncheckedByShift 없음/빈값이면 그 회차는
    '— 미체크:' 부분만 조용히 생략(지어내기 금지)."""
    g = d.get("byGender", {}) or {}
    m = g.get("m", {}) or {}
    f = g.get("f", {}) or {}
    out: list[str] = []
    for key, label in _SHIFTS:
        mT, mD = int(m.get(key + "Total", 0) or 0), int(m.get(key, 0) or 0)
        fT, fD = int(f.get(key + "Total", 0) or 0), int(f.get(key, 0) or 0)
        total, done = mT + fT, mD + fD
        if total <= 0 or done >= total:
            continue
        line = f"    · {label} 남 {mD}/{mT} · 여 {fD}/{fT}"
        names = merged_unchecked_names(d, key)
        if names:
            shown = names[:_MAX_UNCHECKED_NAMES]
            extra = len(names) - len(shown)
            tail = f" 외 {extra}" if extra > 0 else ""
            line += " — 미체크: " + ", ".join(shown) + tail
        out.append(line)
    if not out:
        return []
    return ["  🔔 독려 대상 — 아직 안 된 항목"] + out


def _pct_str(done: int, total: int) -> str:
    return f"{round(done / total * 100)}%" if total else "-"


def gender_shift_breakdown(part: dict) -> list[tuple[str, int, int, int]]:
    """byGender.{m|f} → [(라벨, done, total, pct)] — 분모>0 회차만(요일 자동 반영)."""
    out = []
    for key, label in _SHIFTS:
        total = int(part.get(key + "Total", 0) or 0)
        if total <= 0:
            continue
        done = int(part.get(key, 0) or 0)
        out.append((label, done, total, round(done / total * 100) if total else 0))
    return out


def shift_submits(today: str, url: str = DEFAULT_GAS_URL) -> dict | None:
    """구역별·조별 '제출' 여부 — {'m': {'am': ('김종현 차장', '09:56')}, 'f': {}}.

    ★어디를 읽나 (2026-08-25 GM 지적 "남자는 제출했는데? 정신차려"):
      행 데이터의 submitted_am 계열은 **성별이 섞여 온다** — 같은 날 남·여를 각각 조회해도
      같은 값이 돌아온다(그날 실측). 그걸 근거로 '여성 미제출'을 판정하면 틀린다.
      화면이 실제로 믿는 곳은 회차원장(checkedLedger.sub)이고, 그건 성별로 갈린다.
      실측 2026-08-25: 남성 sub={'am': '김종현 차장'} · 여성 sub={} — 화면 표기와 일치.
    ★조회가 실패하면 None 을 돌려준다. '미제출'로 단정하지 않는다(못 읽음 ≠ 안 함).
    """
    out: dict = {}
    for g in ("m", "f"):
        d = fetch_gas({"date": today, "dept": "support", "gender": g}, url, require_ok=False)
        if not isinstance(d, dict) or "checkedLedger" not in d:
            return None
        ledger = d.get("checkedLedger") or {}
        sub = ledger.get("sub") or {}
        sub_at = ledger.get("subAt") or {}
        got = {}
        for shift, who in sub.items():
            who = str(who or "").strip()
            if not who:
                continue
            stamp = str(sub_at.get(shift) or "").strip()
            got[shift] = (who, stamp[11:16] if len(stamp) >= 16 else stamp)
        out[g] = got
    return out


def recurring_issue_lines(today: str, max_items: int = 3) -> list[str]:
    """반복 미완료(원장 기반) → '이슈사항'으로 승격. 1회성 특이점과 구분(반복만). GM 2026-07-19 지시3.
    콜드스타트·원장부족·0건이면 [](정직 — 가짜 이슈 금지)."""
    if not _CID_OK:
        return []
    try:
        ledger = _cid.load_ledger(CHECK_INCOMPLETE_LEDGER)
        recurring = _cid.detect_recurring(ledger, today)
    except Exception:
        return []
    if not recurring:
        return []
    win = getattr(_cid, "WINDOW_DAYS", 7)
    lines = [f"  🔁 반복 이슈 {len(recurring)}건 (일정 조율 검토)"]
    for r in recurring[:max_items]:
        lines.append(
            f"    · '{r['item']}' ({r['shift_label']}) 최근 {win}일 中 {r['days']}일 미완료")
    if len(recurring) > max_items:
        lines.append(f"    · 외 {len(recurring) - max_items}건")
    return lines


_MAX_ISSUE_DETAIL = 8   # 이슈 상세 표시 최대 건수(초과 시 '외 N건')


def _shift_label_from_roundkey(rk) -> str:
    """roundKey(예 'pm1'·'close1'·'am1') → 회차 라벨(오전조/오후조/마감조). 미상 접두면 원문 그대로."""
    m = re.match(r"([a-zA-Z]+)", str(rk or ""))
    prefix = m.group(1) if m else str(rk or "")
    return dict(_SHIFTS).get(prefix, prefix or "?")


def support_issue_detail_lines(d: dict, max_items: int = _MAX_ISSUE_DETAIL) -> list[str]:
    """today_live.allIssues → 이슈 상세 라인(구역·회차·내용·작성자). GM 2026-07-22 근본수리.
    완료율 기반 '짚을 점'(미달 회차 %)과 별개 — 체크리스트에 실제 적힌 이슈 원문을 그대로 보이게
    (지어내기 금지 — 소스에 없는 필드는 생략)."""
    items = d.get("allIssues")
    if not isinstance(items, list) or not items:
        return []
    glabel = {"m": "남", "f": "여"}
    lines = [f"  📝 이슈 상세 {len(items)}건"]
    for it in items[:max_items]:
        g = glabel.get(str(it.get("gender")), str(it.get("gender") or "?"))
        shift = _shift_label_from_roundkey(it.get("roundKey"))
        text = str(it.get("issue") or "").strip()
        if len(text) > 40:
            text = text[:40] + "…"
        by = str(it.get("by") or "").strip()
        tag = f" ({by})" if by else ""
        lines.append(f"    · [{g}/{shift}] {text}{tag}")
    if len(items) > max_items:
        lines.append(f"   · 외 {len(items) - max_items}건")
    return lines


def build_support_section(today: str, url: str = DEFAULT_GAS_URL,
                          data: dict | None = None) -> tuple[list[str], dict]:
    """지원부 핵심요약: 종일 완료율 + **남성구역·여성구역 각각**(회차분해 요일반영) +
    오늘 짚을 점(1회성) + 반복 이슈(원장). GM 2026-07-19 지시2·3.
    data 미지정 시 today_live 직접 조회(공용). 지정 시 그대로 사용(중복 호출 방지)."""
    filled = {"support_status": False, "support_recurring": 0}
    d = data if data is not None else fetch_gas(
        {"action": "today_live", "dept": "support", "date": today}, url)
    if not isinstance(d, dict):
        return (["🛠 지원부 현황: 데이터 조회 실패(정직 표기)"], filled)

    total = int(d.get("total", 0) or 0)
    done = int(d.get("done", 0) or 0)
    if total <= 0:
        return (["🛠 지원부 현황: 오늘 점검 입력 없음"], filled)

    filled["support_status"] = True
    lines = [f"🛠 지원부 현황 {done}/{total}({_pct_str(done, total)})"]

    # 남성구역·여성구역 각각(합산 아님) — 각 구역 완료율 + 회차분해(요일반영·분모>0만·한 줄 콤팩트)
    submits = shift_submits(today, url)   # None = 못 읽음(미제출로 단정 금지)
    unsubmitted: list[str] = []
    g = d.get("byGender", {}) or {}
    for gk, glabel in (("m", "남성구역"), ("f", "여성구역")):
        part = g.get(gk, {}) or {}
        g_t = sum(int(part.get(k + "Total", 0) or 0) for k, _ in _SHIFTS)
        g_d = sum(int(part.get(k, 0) or 0) for k, _ in _SHIFTS)
        br = gender_shift_breakdown(part)
        # ★조별로 '몇 개 중 몇 개' 와 '제출했나' 를 함께 적는다 (GM 지시 2026-08-25 —
        #   "오전조/오후조/마감조 점검 했는지 안 했는지 몇 개 중에 몇 개를 했는지 정확하게").
        #   체크 개수와 제출은 다른 것이다 — 20/27 을 채워 놓고 제출을 안 하면 그 조는 안 끝난 것이다.
        parts = []
        for lb, dn, tt, _ in br:
            key = next((k for k, l in _SHIFTS if l == lb), "")
            if submits is None:
                mark = ""                                   # 못 읽었으면 아무 말도 안 한다
            elif key in (submits.get(gk) or {}):
                who, at = submits[gk][key]
                mark = f" ✅제출({who}{(' ' + at) if at else ''})"
            else:
                mark = " ⛔미제출"
                unsubmitted.append(f"{glabel} {lb} {dn}/{tt}")
            parts.append(f"{lb} {dn}/{tt}{mark}")
        detail = " — " + " · ".join(parts) if parts else ""
        lines.append(f"  {glabel} {g_d}/{g_t}({_pct_str(g_d, g_t)}){detail}")

    if submits is None:
        lines.append("  ⚠ 제출 여부는 지금 확인이 안 됩니다(조회 실패) — 안 했다는 뜻이 아닙니다")
    elif unsubmitted:
        lines.append("  ⛔ 아직 제출 안 된 조 " + str(len(unsubmitted)) + "개 — " + " · ".join(unsubmitted))
    else:
        lines.append("  ✅ 전 조 제출 완료")

    # ── 이슈사항(현황과 함께) — 미점검 회차 전부 + 반복 이슈. GM 2026-07-19 피드백1·2 ──
    issues = support_issues(d)          # 1회성 미점검(빠짐없이)
    rec = recurring_issue_lines(today)  # 반복(원장) — 이미 " " 들여쓰기 리스트
    filled["support_recurring"] = max(0, len(rec) - 1) if rec else 0
    if issues:
        lines.append("  ❗ 짚을 점: " + ", ".join(issues) + " — 독려 필요")
    elif not rec:
        lines.append("  ✅ 이상 없음 — 전 회차 완료")
    lines += rec

    # 독려 대상(미체크 항목명) — 17·22시 개별 독려에만 있던 정보를 22:30 보고에도 상시 반영.
    # GM 2026-07-23 지시(시토). 미완 회차 없으면 support_nudge_lines가 빈 리스트 반환(생략).
    lines += support_nudge_lines(d)

    # 이슈 상세(체크리스트 원문) — 완료율 짚을 점과 별개, allIssues 그대로 노출. GM 2026-07-22 지시3.
    lines += support_issue_detail_lines(d)
    return (lines, filled)


_MAX_WORKLOG = 12  # 회차별 일지 표시 최대 회차(초과 시 '외 N회차').
                   # 누적 반복을 걷어내 회차당 1줄로 짧아졌으므로 전 회차가 다 보이도록 상향
                   # (기존 8이면 9회차 날 마지막 회차가 잘려 '외 1회차'로 숨었다 — GM 2026-07-23).

# 시설부 측정값 라벨(store.rounds[*] / store.daily 원본 키 → 한글 표기). GM 2026-07-22 렌더심화.
_ROUND_LABELS = {
    "sauna_ontang_a": "온탕A", "sauna_ontang_b": "온탕B",
    "sauna_yeoltang_a": "열탕A", "sauna_yeoltang_b": "열탕B",
    "sauna_dry_a": "건식A", "sauna_dry_b": "건식B",
    "sauna_wet_a": "습식A", "sauna_wet_b": "습식B",
    "sauna_jjim_a": "찜질A", "sauna_jjim_b": "찜질B",
    "pool_ph": "수영장pH", "pool_temp": "수영장온도", "pool_cl": "수영장염소",
    "tank_k2": "탱크K2", "tank_k3": "탱크K3", "tank_k4": "탱크K4",
    "ahu_AHU1": "AHU1", "ahu_AHU2": "AHU2", "ahu_AHU3": "AHU3", "ahu_AHU4": "AHU4",
}
_DAILY_LABELS = {
    "fc_eq_night": "심야전기", "fc_eq_tank1": "1번탱크", "fc_eq_gas": "가스검침",
    "fc_eq_hotw": "고온수기", "fc_eq_pump": "연동펌프",
}

# 설비(기계실 가동값) 표시 보강 — GM 2026-07-23 "설비도 가독성 + 무얼 목표하는지".
# 이름·단위·기준 시각은 전부 시설부 체계 페이지의 EQUIP 정의에서 그대로 가져왔다
# (3. 웰페리온 가이드/coo/check/시설부 체계.html — 심야전기 A · 1번 탱크온도 ℃ ·
#  가스검침 ㎥ · 고온수기 ok/x · 연동펌프 ok/x, 전부 05:00 · 분류 'E 기계실 가동값').
# 값·단위를 새로 지어내지 않는다. 목표 문구도 같은 페이지의 '표준 가동 시각(작업일지
# 기준) · 일일 가동·정지 기록'에서 벗어나지 않게 적는다.
_DAILY_UNITS = {
    "fc_eq_night": "A", "fc_eq_tank1": "℃", "fc_eq_gas": "㎥",
}
_DAILY_DISPLAY = {"fc_eq_tank1": "1번 탱크온도"}
# 가동 여부(ok/x)와 계측값(수치)은 성격이 달라 줄을 나눈다 — 한 줄에 섞이면 안 읽힌다.
_DAILY_STATE_KEYS = ("fc_eq_hotw", "fc_eq_pump")
_DAILY_METER_KEYS = ("fc_eq_night", "fc_eq_tank1", "fc_eq_gas")
_DAILY_PURPOSE = "매일 05:00 기계실 가동값 — 급탕이 끊기지 않는지 · 사용량이 튀지 않는지"


def _lines(v) -> list[str]:
    return [ln.strip() for ln in str(v or "").replace("\r", "").split("\n") if ln.strip()]


# ── 회차별 측정값 한 줄 요약 (GM 2026-07-23 "회차별 일지도 같이") ──────────────
# 제출 1건(=1회차)마다 items[].measure 에 그 회차에서 실제로 잰 값이 들어 있다
# (온탕 38.4 → 39.0 → 38.2 처럼 회차마다 다르다). 그런데 보고는 store.rounds 의
# 한 벌만 보여줘 나머지 8회차 측정이 통째로 안 보였다 — 회차 줄에 붙여 되살린다.
_INLINE_PAIRS = (
    ("sauna_ontang", "온탕"), ("sauna_yeoltang", "열탕"), ("sauna_dry", "건식"),
    ("sauna_wet", "습식"), ("sauna_jjim", "찜질"),
)
_INLINE_POOL = (("pool_ph", "pH"), ("pool_temp", "수온"), ("pool_cl", "염소"))


def submission_measures(sub: dict) -> dict:
    """제출 1건의 items[].measure(JSON 문자열)들을 하나의 {필드: 값} 으로 펼친다."""
    out: dict = {}
    for it in sub.get("items") or []:
        raw = it.get("measure")
        if not raw:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if isinstance(parsed, dict):
            for k, v in parsed.items():
                if str(v).strip():
                    out[k[3:] if k.startswith("fc_") else k] = v
    return out


def compact_measures(m: dict) -> str:
    """회차 줄에 붙일 한 줄 요약. 값은 그대로, 없는 항목은 건너뛴다(지어내기 금지)."""
    if not m:
        return ""
    parts: list[str] = []
    for base, label in _INLINE_PAIRS:
        ab = [m[f"{base}_{s}"] for s in ("a", "b") if f"{base}_{s}" in m]
        if ab:
            parts.append(f"{label} {'/'.join(str(v) for v in ab)}")
    pool = [f"{lbl} {m[k]}" for k, lbl in _INLINE_POOL if k in m]
    if pool:
        parts.append("수영장 " + "·".join(pool))
    tanks = [f"{k.replace('tank_', '').upper()} {m[k]}" for k in sorted(m) if k.startswith("tank_")]
    if tanks:
        parts.append("탱크 " + "·".join(tanks))
    ahu = [k for k in sorted(m) if k.startswith("ahu_")]
    if ahu:
        vals = {str(m[k]) for k in ahu}
        parts.append(f"공조기 전부 {vals.pop()}" if len(vals) == 1
                     else "공조기 " + "·".join(f"{k.replace('ahu_', '')} {m[k]}" for k in ahu))
    return " · ".join(parts)


def facility_worklog(subs: list, oor_fields: set[str] | None = None) -> tuple[list[list[str]], list[str]]:
    """board submissions → (회차별 일지 라인 리스트, 특이사항 리스트). GM 2026-07-22 근본수리.
    이전엔 work 최다 '대표 제출 1건'만 썼음(다른 회차 작업내용 유실) — seq 순 전체 회차를 루프해
    "N회차 HH:MM~HH:MM(소요 M분) · 점검자 · 작업요약" 라인으로 전부 가시화(데이터 없는 회차는 시간만).
    note=전 회차 유니크(기존 로직 유지 — 이미 전체 순회라 손상 아님)."""
    if not isinstance(subs, list) or not subs:
        return ([], [])

    ordered = sorted(subs, key=lambda s: s.get("seq") if isinstance(s.get("seq"), (int, float)) else 0)
    work_items: list[str] = []
    seen_work: set[str] = set()   # 앞 회차에 이미 나온 작업 — 반복 출력 차단
    for i, s in enumerate(ordered, start=1):
        start, end = s.get("startHHMM"), s.get("endHHMM")
        time_part = f"{start}~{end}" if start and end else (str(s.get("at") or "").split(" ")[-1] or "?")
        dur = s.get("durMin")
        dur_part = f"({dur}분)" if dur not in (None, "") else ""
        insp = s.get("inspector") or "?"
        head = f"{i}회차 {time_part}{dur_part} · {insp}"

        # work 는 '그 회차까지의 누적 작업목록'으로 들어온다(현장 입력 방식).
        # 그대로 찍으면 뒤 회차일수록 앞 내용을 통째로 반복해 8회차엔 9줄이 겹쳤다
        # → 화면이 길어져 정작 '오늘 새로 한 일'이 안 보인다(GM 2026-07-23 지적).
        # 그래서 앞 회차에 없던 항목만 남긴다. 데이터는 손대지 않고 표시만 줄인다.
        fresh = [w for w in _lines(s.get("work")) if w not in seen_work]
        seen_work.update(fresh)
        marker = "" if i == 1 else "+ "
        block = [f"{head} · {marker}{' / '.join(fresh)}" if fresh
                 else f"{head} · (추가 작업 없음)"]

        # ※ 2026-07-23: 회차 줄 아래에 그 회차 측정값·특이사항을 붙여 봤으나(개선본4)
        # GM 이 묶음 표시(개선본3)를 더 낫다고 판단 — 회차 줄은 '언제·누가·무슨 작업'만
        # 담고, 측정은 아래 🌡 묶음 블록이 담당한다. 회차별 측정 조립 함수
        # (submission_measures/compact_measures)는 지우지 않고 남겨 둔다 — 필요할 때
        # 다시 붙일 수 있고, 지웠다 다시 쓰는 왕복이 더 비싸다.
        work_items.append(block)

    # 특이사항(note)·기준이탈조치(oocAction) — 전 회차에서 유니크 수집(순서 보존)
    notes: list[str] = []
    seen = set()
    for s in subs:
        for f in ("note", "oocAction"):
            for ln in _lines(s.get(f)):
                if ln not in seen:
                    seen.add(ln)
                    notes.append(ln)
    return (work_items, notes)


# ── 측정값 묶음 표시 (GM 2026-07-23 "측정 부분 가독성 살려줘") ──────────────
# 이전엔 19개 값이 한 줄에 쭉 나열돼 무엇이 어느 설비 값인지 눈으로 못 좇았다.
# 필드 이름이 이미 설비별로 접두가 나뉘어 있으므로(ahu_/pool_/sauna_/tank_)
# 그 접두로만 묶는다 — 값·단위를 새로 만들어 붙이지 않는다(지어내기 금지).
_MEASURE_GROUPS = (
    ("공조기", ("ahu_",)),
    ("수영장", ("pool_",)),
    ("사우나", ("sauna_dry", "sauna_wet", "sauna_jjim")),
    ("탕", ("sauna_ontang", "sauna_yeoltang")),
    ("탱크", ("tank_",)),
)
# 묶음 안에서 쓸 짧은 이름(앞에 붙은 설비명은 묶음 제목이 대신하므로 뗀다)
_MEASURE_SUBLABEL = {
    "sauna_dry": "건식", "sauna_wet": "습식", "sauna_jjim": "찜질",
    "sauna_ontang": "온탕", "sauna_yeoltang": "열탕",
    "pool_cl": "염소", "pool_ph": "pH", "pool_temp": "온도",
}
_POOL_ORDER = ("pool_cl", "pool_ph", "pool_temp")


def _measure_group_lines(vals: dict, oor: set[str]) -> list[str]:
    """측정값 dict → 설비 묶음별 한 줄씩. A/B 짝은 '건식 A 80.0 / B 82.0' 으로 합친다."""
    norm = {(k[3:] if k.startswith("fc_") else k): v for k, v in vals.items()}

    def cell(key: str, label: str) -> str:
        mark = "❗" if key in oor else ""
        return f"{mark}{label} {norm[key]}"

    used: set[str] = set()
    lines: list[str] = []
    for title, prefixes in _MEASURE_GROUPS:
        keys = [k for k in norm if any(k.startswith(p) for p in prefixes)]
        if not keys:
            continue
        used.update(keys)
        parts: list[str] = []
        if title == "수영장":
            for k in _POOL_ORDER:
                if k in norm:
                    parts.append(cell(k, _MEASURE_SUBLABEL.get(k, k)))
        elif title == "탱크":
            for k in sorted(keys):
                parts.append(cell(k, k.replace("tank_", "").upper()))
        elif title == "공조기":
            for k in sorted(keys):
                parts.append(cell(k, _ROUND_LABELS.get(k, k)))
        else:
            # 사우나·탕 — 같은 설비의 A/B 를 한 덩어리로 묶어 줄 수를 줄인다.
            # 현장에서 부르는 순서로 고정(알파벳순이면 건식·찜질·습식처럼 뒤섞인다)
            order = [p for p in prefixes]
            bases: list[str] = []
            for k in sorted(keys, key=lambda x: order.index(
                    next((p for p in order if x.startswith(p)), order[0]))):
                base = k[:-2] if k.endswith(("_a", "_b")) else k
                if base not in bases:
                    bases.append(base)
            for base in bases:
                sub = _MEASURE_SUBLABEL.get(base, _ROUND_LABELS.get(base, base))
                ab = [(suffix.upper(), f"{base}_{suffix}")
                      for suffix in ("a", "b") if f"{base}_{suffix}" in norm]
                if ab:
                    inner = " / ".join(cell(k, s) for s, k in ab)
                    parts.append(f"{sub} {inner}")
                elif base in norm:
                    parts.append(cell(base, sub))
        if parts:
            lines.append(f"    · {title}  " + " · ".join(parts))

    leftovers = [k for k in sorted(norm) if k not in used]
    if leftovers:
        lines.append("    · 기타  " + " · ".join(
            cell(k, _ROUND_LABELS.get(k, k)) for k in leftovers))
    return lines


def facility_measurements(store: dict, today_oor_fields: set[str]) -> list[str]:
    """store.rounds[*]·store.daily(장비값) → 측정값 요약 라인. GM 2026-07-22 렌더심화 지시2.
    소스에 있는 값만 그대로 표기(창작 금지) · today_oor_fields에 든 필드는 ❗ 표시(기존 기준이탈 판정 재사용)."""
    out: list[str] = []

    rounds = store.get("rounds") if isinstance(store.get("rounds"), dict) else {}
    for rk in sorted(rounds.keys()):
        vals = rounds.get(rk) or {}
        if not isinstance(vals, dict) or not vals:
            continue
        tag = f" [{rk}]" if len(rounds) > 1 else ""
        group_lines = _measure_group_lines(vals, today_oor_fields)
        if not group_lines:
            continue
        out.append(f"  🌡 측정{tag}")
        out += group_lines

    daily = store.get("daily") if isinstance(store.get("daily"), dict) else {}

    def eq_cell(k: str) -> str:
        label = _DAILY_DISPLAY.get(k, _DAILY_LABELS[k])
        return f"{label} {daily[k]}{_DAILY_UNITS.get(k, '')}"

    state_parts = [eq_cell(k) for k in _DAILY_STATE_KEYS if daily.get(k) not in (None, "")]
    meter_parts = [eq_cell(k) for k in _DAILY_METER_KEYS if daily.get(k) not in (None, "")]
    # 위 두 묶음에 안 든 항목(나중에 늘어난 칸)도 빠뜨리지 않는다.
    known = set(_DAILY_STATE_KEYS) | set(_DAILY_METER_KEYS)
    etc_parts = [eq_cell(k) for k in _DAILY_LABELS
                 if k not in known and daily.get(k) not in (None, "")]

    if state_parts or meter_parts or etc_parts:
        out.append(f"  ⚙ 설비  ({_DAILY_PURPOSE})")
        if state_parts:
            out.append("    · 가동  " + " · ".join(state_parts))
        if meter_parts:
            out.append("    · 계측  " + " · ".join(meter_parts))
        if etc_parts:
            out.append("    · 기타  " + " · ".join(etc_parts))
    return out


# ── 시설부 ────────────────────────────────────────────────────────────────
def build_facility_section(today: str, url: str = DEFAULT_GAS_URL) -> tuple[list[str], dict]:
    """시설부 핵심요약: 회차별 일지(submissions 전체) + 측정값(rounds·daily) +
    이슈사항(기준이탈·특이사항note). GM 2026-07-22 근본수리(렌더심화·회차수 정직표기).
    회차수(sessions=len(submissions))는 GAS saveBoard union 병합 수리·라이브 배포·런타임 검증
    완료(FACILITY_SESSIONS_TRUSTED=True) — 신뢰 가능."""
    filled = {"facility_status": False, "facility_outofrange": 0, "facility_worklog": False}

    board = fetch_gas({"action": "board", "key": f"FACILITY_CHECK_{today}"}, url)
    store = (((board or {}).get("board") or {}).get("store") or {})
    subs = store.get("submissions")
    sessions = len(subs) if isinstance(subs, list) else 0

    monthly = fetch_gas({"action": "monthly_report", "dept": "facility", "month": today[:7]}, url)
    today_oor = []
    if isinstance(monthly, dict):
        oor = ((monthly.get("outOfRange") or {}).get("list")) or []
        today_oor = [x for x in oor if str(x.get("date")) == today]
    filled["facility_outofrange"] = len(today_oor)

    lines: list[str] = []
    if not sessions:
        # ★'못 읽음' 과 '진짜 0' 을 가른다(2026-08-06 GM 지적).
        #   board 조회 자체가 실패하면(None) 점검을 안 한 게 아니라 우리가 못 본 것이다.
        #   그걸 '점검 입력 없음' 으로 적으면 제대로 일한 사람을 안 했다고 적는 셈이 된다.
        if board is None:
            lines.append("🏗 시설부 현황: 지금 확인이 안 됩니다(조회 실패) — 점검 여부는 알 수 없습니다")
            filled["facility_fetch_failed"] = True
        else:
            lines.append("🏗 시설부 현황: 오늘 점검 입력 없음")
        return (lines, filled)

    filled["facility_status"] = True
    # 회차수 표기 — FACILITY_SESSIONS_TRUSTED=False(기본)면 GAS 재배포 전이라 '(확인중)' 꼬리표
    # 유지(거짓 확정 금지). GM이 라이브 배포 검증 후 플래그를 True로 바꾸면 정확 회차수로 전환.
    if FACILITY_SESSIONS_TRUSTED:
        head = f"🏗 시설부 현황 {sessions}회차"
    else:
        head = f"🏗 시설부 현황 board 기록 {sessions}건(회차 확인중)"
    head += f" · 이상 {len(today_oor)}건" if today_oor else " · 이상 없음"
    lines.append(head)

    # 회차별 일지(전 회차 개별 라인) — 실데이터(work). 없으면 정직히 시간만(지어내기 금지).
    today_oor_fields = {str(x.get("field")) for x in today_oor if x.get("field")}
    work_items, notes = facility_worklog(subs, today_oor_fields)
    if work_items:
        filled["facility_worklog"] = True
        lines.append("  📋 회차별 일지 (새로 추가된 작업만 · 앞 회차 반복 생략)")
        for block in work_items[:_MAX_WORKLOG]:
            lines.append(f"    · {block[0]}")
            for extra in block[1:]:
                lines.append(f"       {extra}")
        if len(work_items) > _MAX_WORKLOG:
            lines.append(f"    · 외 {len(work_items) - _MAX_WORKLOG}회차")
    else:
        lines.append("  📋 회차별 일지: 데이터 없음")

    # 측정값(사우나·수영장·탱크·공조기·설비) — store.rounds/store.daily 원본. 기준이탈 필드는 ❗.
    meas_lines = facility_measurements(store, today_oor_fields)
    lines += meas_lines

    # 이슈사항 = 기준이탈(인라인 압축) + 특이사항(note)
    if today_oor:
        parts = []
        for x in today_oor[:2]:
            name = str(x.get("name", "")).split("(")[0].strip() or str(x.get("name", ""))
            parts.append(f"{name} {_num(x.get('value'))}(기준 {_num(x.get('min'))}~{_num(x.get('max'))})")
        extra = f" 외 {len(today_oor) - 2}건" if len(today_oor) > 2 else ""
        lines.append(f"  ❗ 기준이탈 {len(today_oor)}건: " + " · ".join(parts) + extra)
    if notes:
        note_txt = " / ".join(notes[:2])
        if len(note_txt) > 90:
            note_txt = note_txt[:90] + "…"
        lines.append("  📝 특이사항: " + note_txt)
    return (lines, filled)


# ── 주차부 ────────────────────────────────────────────────────────────────
def build_parking_section(today: str, url: str = DEFAULT_GAS_URL) -> tuple[list[str], dict]:
    """주차부: weekly 오늘 행 있으면 현황, 없으면 '자체점검 준비 중' 정직 표기."""
    filled = {"parking": False}
    data = fetch_gas({"action": "weekly", "dept": "parking"}, url)
    if isinstance(data, dict):
        for row in data.get("data") or []:
            t = row.get("total")
            if str(row.get("date")) == today and isinstance(t, (int, float)) and t:
                filled["parking"] = True
                return ([f"🅿 주차부 이슈사항: 없음 · 점검 {row.get('done', 0)}/{t}({row.get('pct', 0)}%)"], filled)
    if data is None:
        # ★'못 읽음' 을 '준비 중' 으로 적지 않는다(2026-08-06 GM 지적 · 시설부와 같은 부류).
        filled["parking_fetch_failed"] = True
        return (["🅿 주차부: 지금 확인이 안 됩니다(조회 실패) — 점검 여부는 알 수 없습니다"], filled)
    # 2026-08-25 시우: '준비 중'은 이제 사실이 아니다. 일일 8항목 제출 화면은 2026-08-18(배672)에 열렸고
    # 지원부·시설부와 같은 점검 GAS 를 쓴다. 오늘 행이 없다는 건 준비가 안 된 게 아니라 **오늘 제출이 없다**는 뜻이다.
    # 옛 문구를 그대로 두면 GM·실무진이 "아직 만드는 중"으로 읽어 제출 화면을 찾지 않는다(2026-08-25 GM 지적).
    return (["🅿 주차부: 오늘 일일점검 제출 없음 — "
             "https://wellperion-cao.github.io/wellperion-automation/coo/check/주차관리부 체계.html#check"], filled)


# ── 통합 3섹션 핵심요약(두 채널 공용 본문 코어) ─────────────────────────────
def build_summary_lines(now: datetime | None = None, date: str | None = None,
                        url: str = DEFAULT_GAS_URL,
                        support_data: dict | None = None) -> tuple[list[str], dict]:
    """3섹션 핵심요약 본문 라인(헤더·푸터 제외 — 채널이 각자 감싼다).
    date 지정 시 그 날짜로 조회(테스트·과거 스냅샷 재현). support_data 지정 시 지원부 재조회 생략."""
    now = now or datetime.now()
    today = date or now.strftime("%Y-%m-%d")

    fac_lines, fac_f = build_facility_section(today, url)
    sup_lines, sup_f = build_support_section(today, url, data=support_data)
    par_lines, par_f = build_parking_section(today, url)

    # 섹션 사이 빈 줄 1칸(가시성) — 🏗 시설부 → 🛠 지원부 → 🅿 주차부. GM 2026-07-19 지시1. 양 채널 동일.
    lines = fac_lines + [""] + sup_lines + [""] + par_lines
    return (lines, {**fac_f, **sup_f, **par_f})


def zero_zones(today: str, url: str = DEFAULT_GAS_URL, data: dict | None = None):
    """오늘 **한 건도 안 된 구역**만 골라낸다 — [(구역라벨, 예정건수), …].

    2026-07-31 GM 지시("실무진에서 매일 돌아가야 하는 부분이 안 돌아가면 알림 줘야 할 것 같은데
    — 오늘은 여자 지원부 점검을 안 했는데"). 그날 실측이 정확히 그 모습이었다:
    남성구역 17/53, **여성구역 0/52(오전·오후·마감 전부 0)** — 덜 한 게 아니라 통째로 빠졌다.

    ▸'덜 됨'은 여기서 잡지 않는다. 부분 미완은 하루가 흘러가며 채워지는 정상 흐름이고,
      그걸 낮에 알리면 매일 떠서 소음이 된다(2026-07-23 GM 이 17시·22시 고정 독려를 없앤 이유).
      **하루 종일 손도 안 댄 구역**만이 진짜 이상이고, 그때만 알린다.
    ▸판정은 여기 한 곳에서만 한다 — 22:30 보고와 낮 알림이 각자 세면 숫자가 갈라진다(약속 L01).
    """
    return shift_gaps(today, "am", url, data) + shift_gaps(today, "pm", url, data)


def shift_gaps(today: str, shift_key: str, url: str = DEFAULT_GAS_URL,
               data: dict | None = None):
    """그 회차에서 **제출이 0건인 구역**을 회차 단위로 짚는다.

    반환: [{zone, shift, total, likely}] — likely 는 무슨 일이 일어난 것 같은지.
      · "제출누락"  = 같은 회차에 **다른 구역은 됐는데** 이 구역만 0건.
                      사람은 출근해 그 회차를 돌았다는 뜻이라, 안 한 게 아니라 **입력만 빠진** 쪽이 유력하다.
      · "미시작"    = 그 회차가 양쪽 구역 모두 0건. 아직 시작 전일 수 있다.

    ★2026-07-31 GM 지시로 구역 합계(52건 중 0건)에서 회차 단위로 바꿨다:
      "여성구역 52건 중 0건이 아니라, 오전 회차가 진행되었는데 제출이 안 된 것 같다고
       진짜 사람이 짚어준 것처럼 옆에서 짚어줘야 해."
      합계로 뭉치면 받는 사람이 무엇을 해야 하는지 모른다 — 현장이 일하는 단위가 회차다.
    """
    d = data if data is not None else fetch_gas(
        {"action": "today_live", "dept": "support", "date": today}, url)
    if not isinstance(d, dict):
        return []
    label = dict(_SHIFTS).get(shift_key, shift_key)
    g = d.get("byGender", {}) or {}
    stat = {}
    for gk, glabel in (("m", "남성구역"), ("f", "여성구역")):
        part = g.get(gk, {}) or {}
        stat[glabel] = (int(part.get(shift_key, 0) or 0),
                        int(part.get(shift_key + "Total", 0) or 0))
    any_done = any(dn > 0 for dn, tt in stat.values())
    # ★체크는 했는데 제출을 안 한 조도 잡는다 (GM 지시 2026-08-25 "제출 안한조를 자동으로 알려줘").
    #   종전에는 체크가 0건인 구역만 봤다 — 20/27 을 채워 놓고 제출을 안 한 조는 통과했고,
    #   그날 GM 이 화면에서 직접 발견하셨다. 사람이 다 돌고 마지막 한 번을 안 누른 경우라
    #   오히려 가장 아깝다. 조회 실패(None)면 이 판정을 건너뛴다 — 못 읽은 것을 안 한 것으로 만들지 않는다.
    subs = shift_submits(today, url)
    out = []
    for glabel, (dn, tt) in stat.items():
        if tt <= 0:
            continue
        if dn == 0:
            out.append({"zone": glabel, "shift": label, "total": tt,
                        "likely": "제출누락" if any_done else "미시작"})
            continue
        gk = "m" if glabel == "남성구역" else "f"
        if subs is not None and shift_key not in (subs.get(gk) or {}):
            out.append({"zone": glabel, "shift": label, "total": tt, "done": dn,
                        "likely": "제출만 빠짐"})
    return out


def facility_gap(today: str, url: str = DEFAULT_GAS_URL) -> dict | None:
    """시설부가 오늘 **통째로 0건**이면 알림 재료를 돌려준다. 아니면 None.

    2026-08-06 실사고의 짝 문제(배436 잔여 2번): 0건 경보가 지원부 남/여 구역만 봐서
    시설부가 통째로 0건이어도 아무도 모른다. 판정은 build_facility_section 과 같은
    원천(board.store.submissions)을 쓴다 — 두 곳에서 갈라지면 숫자가 어긋난다(약속 L01).

    ★조회 실패(board is None)는 0으로 치지 않는다 — '못 읽음'을 '안 했음'으로 적으면
      제대로 일한 사람을 안 했다고 적는 셈이다(2026-08-06 GM 지적). 그때는 None(무알림).
    """
    board = fetch_gas({"action": "board", "key": f"FACILITY_CHECK_{today}"}, url)
    if board is None:
        return None
    subs = (((board or {}).get("board") or {}).get("store") or {}).get("submissions")
    if isinstance(subs, list) and len(subs) > 0:
        return None
    return {"zone": "시설부", "shift": "오늘", "total": 0, "likely": "미시작"}


def _weekday_kor(date: str) -> str:
    try:
        return ["월", "화", "수", "목", "금", "토", "일"][datetime.strptime(date, "%Y-%m-%d").weekday()]
    except Exception:
        return "?"


def main() -> int:
    # 콘솔 한글 깨짐 방지 — 스탠드얼론 실행 시에만(import 경로에선 전역 스트림 불건드림)
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="점검 3섹션 핵심요약 렌더(라이브 미발송)")
    ap.add_argument("--date", help="조회 날짜 YYYY-MM-DD(생략 시 오늘). 주말 렌더 확인용.")
    args = ap.parse_args()
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    lines, filled = build_summary_lines(date=date)
    print("=" * 56)
    print(f"[{date}({_weekday_kor(date)}) 점검 핵심요약]")
    print("\n".join(lines))
    print("=" * 56)
    print(f"채워진 필드: {filled}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
