# -*- coding: utf-8 -*-
"""
northstar_reach.py  --  북극성 도달율 하이브리드 계산 엔진 (2026-07-02)

입력:
  - 3. 웰페리온 가이드/coo/bootsetup_matrix.json  (role.nsmap.reach 설정)
  - status/kpi_values.json                        (실측 KPI · kpi_collector 산출)
  - status/home_kpi.json                          (있으면 매출 폴백 · 없으면 무시)

출력: status/northstar_reach.json
  역할별 { reach_pct(0~100) 또는 null, mode, basis, updated_at,
          (milestone) milestones_done / milestones_total }

규칙(정직 · ssot/약속 L05 · M4-METRIC-HONESTY):
  - measured: 실측/목표. 실측 미측정=null("측정 개통 전"). 가짜 % 금지.
  - milestone: 완료 마일스톤/전체 (제안본 · done=수동 결재 플래그).
  - 순수 집계 · 파일쓰기만. 라이브 부작용 0.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = ROOT / "3. 웰페리온 가이드" / "coo" / "bootsetup_matrix.json"
KPI_PATH = ROOT / "status" / "kpi_values.json"
# ★2026-07-31 시토 — 없는 파일을 가리키고 있었다(죽은 포인터). 실제 매출 스냅샷은
#   erp_status_publisher.py 가 30분마다 쓰는 status/home_kpi_snapshot.json 이다.
#   status/home_kpi.json 은 저장소 어디에서도 만들어지지 않는다(생산자 0곳 · 실측 확인).
#   그래서 매출을 원천으로 삼는 계산은 조용히 아무 값도 못 받고 있었다 — 실패가 아니라
#   '없으면 무시' 로 설계돼 있어 아무도 몰랐다.
HOME_KPI_PATH = ROOT / "status" / "home_kpi_snapshot.json"
OUT_PATH = ROOT / "status" / "northstar_reach.json"

KST = timezone(timedelta(hours=9))


def _load_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _resolve_source(source: str, kpi: dict | None, home: dict | None, role_id: str) -> dict:
    """reach.source 문자열 → 값 딕셔너리(없으면 {})."""
    kpi = kpi or {}
    if source == "kpi_values.global":
        return (kpi.get("global") or {}) if isinstance(kpi, dict) else {}
    if source.startswith("kpi_values.roles."):
        rid = source.split(".", 2)[2] or role_id
        return ((kpi.get("roles") or {}).get(rid) or {}) if isinstance(kpi, dict) else {}
    if source == "home_kpi":
        return home or {}
    return {}


def _check_ok(val: object, rule: str | None) -> bool:
    """indicator ok 규칙 판정. 값 미측정(None/부재)=미달성(정직)."""
    if rule == "eq0":
        return isinstance(val, (int, float)) and not isinstance(val, bool) and val == 0
    if isinstance(rule, str) and rule.startswith("eq:"):
        return str(val) == rule[3:]
    return False


def _measured_indicators(reach: dict, src: dict) -> tuple[int | None, str]:
    """4지표류 measured — 달성개수/전체×100 + 세부(라벨✓/✗)."""
    inds = reach.get("indicators") or []
    if not inds:
        return None, "지표 정의 없음"
    achieved, details = 0, []
    for ind in inds:
        val = src.get(ind.get("key"))
        ok = _check_ok(val, ind.get("ok"))
        achieved += 1 if ok else 0
        details.append(f"{ind.get('label', '?')}{'✓' if ok else '✗'}")
    total = len(inds)
    pct = round(achieved / total * 100)
    return pct, f"{achieved}/{total} 달성 · " + " ".join(details)


def _measured_target(reach: dict, src: dict) -> tuple[int | None, str]:
    """목표값 대비 실측 measured — min(100, 실측/목표×100). 미측정=null."""
    vk = reach.get("value_key")
    target = reach.get("target")
    val = src.get(vk) if isinstance(src, dict) else None
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        return None, f"{vk} 미측정 — 측정 개통 전"
    if not isinstance(target, (int, float)) or not target:
        return None, "목표값 없음"
    pct = min(100, round(val / target * 100))
    return pct, f"실측 {val} / 목표 {target}"


def _milestone(reach: dict) -> tuple[int | None, str, int, int]:
    """마일스톤 진척 — 완료/전체×100 (제안본)."""
    ms = reach.get("milestones") or []
    total = len(ms)
    if not total:
        return None, "마일스톤 정의 없음", 0, 0
    done = sum(1 for m in ms if m.get("done") is True)
    pct = round(done / total * 100)
    return pct, f"마일스톤 {done}/{total} (제안본 · GM 조정)", done, total


def compute() -> dict:
    matrix = _load_json(MATRIX_PATH) or {}
    kpi = _load_json(KPI_PATH)
    home = _load_json(HOME_KPI_PATH)

    now = datetime.now(KST)
    updated_at = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")

    roles_out: dict[str, dict] = {}
    for role in (matrix.get("roles") or []):
        rid = role.get("id")
        reach = (role.get("nsmap") or {}).get("reach")
        if not rid or not isinstance(reach, dict):
            continue
        mode = reach.get("mode")
        entry: dict = {"mode": mode, "updated_at": updated_at}
        if mode == "measured":
            src = _resolve_source(reach.get("source", ""), kpi, home, rid)
            if reach.get("indicators"):
                pct, basis = _measured_indicators(reach, src)
            else:
                pct, basis = _measured_target(reach, src)
            entry["reach_pct"] = pct
            entry["basis"] = basis
        elif mode == "milestone":
            pct, basis, done, total = _milestone(reach)
            entry["reach_pct"] = pct
            entry["basis"] = basis
            entry["milestones_done"] = done
            entry["milestones_total"] = total
        else:
            entry["reach_pct"] = None
            entry["basis"] = f"알 수 없는 mode: {mode}"
        roles_out[rid] = entry

    return {
        "_doc": (
            "북극성 도달율(하이브리드). 산출: northstar_reach.py. "
            "measured=실측/목표 · milestone=마일스톤 완료/전체. 측정 불가=null(가짜 % 금지)."
        ),
        "generated_at": updated_at,
        "generated_at_kst": now.strftime("%Y-%m-%d %H:%M KST"),
        "roles": roles_out,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 북극성 대비 위치 블록 — 모든 보고가 같은 이 함수 하나를 쓴다 (GM 확정 2026-07-31)
#
# GM: "콘텐츠 제작·검수·발행도, 점검 현황도, 전사 업무·결재도, 문의 라이프사이클도,
#      자동화 현황도, 매출·운영·인사 현황보고도 — 그냥 현황만 던진 것 같다."
# → 보고 맨 위를 '지금 무엇이 있나'에서 **'목표 대비 어디쯤이고, 어디가 벌어졌나'** 로 바꾼다.
#   GM 이 세 안 중 이 모양을 고르셨다(2026-07-31 선택 카드).
#
# ★한 곳에서만 만든다(약속 L01·L21) — 새 렌더 모듈을 만들지 않고, 숫자를 이미 갖고 있는
#   이 파일에 붙인다. 여섯 군데 보고는 전부 build_northstar_block() 을 import 해 쓴다.
#   블록을 고칠 일이 생기면 여기만 고친다.
# ★거짓 숫자 금지 — 못 잰 값은 막대를 그리지 않고 '미측정'이라고 적는다. 이 파일의 기존
#   원칙(measured/milestone/null)과 같다. 채워 보이게 만들지 않는다.
# ══════════════════════════════════════════════════════════════════════════════

HISTORY_PATH = ROOT / "status" / "northstar_reach_history.jsonl"

_ROLE_LABEL = {
    "ceo": "웰리 전사", "coo": "시우 운영", "cto": "시토 기술",
    "cmo": "시모 마케팅", "cpo": "시포 회원", "cfo": "시뽀 재무", "chro": "시로 인사",
}
# 시로·시뽀는 사람(나우열M)이 운영하는 영역이라 AI 보고에 올리지 않는다(kpi.json _배제역할_2026_07_28).
_BLOCK_EXCLUDED = ("chro", "cfo")


def _trim(text: str, limit: int) -> str:
    """길면 줄이되 낱말·문장 중간에서 자르지 않는다(GM 반복 지적 '문장 중간 잘림').
    자연스러운 경계가 앞쪽밖에 없으면 자르지 않고 통째로 둔다 — 뜻이 끊기는 것보다 낫다."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    window = text[:limit]
    cut = max(window.rfind(c) for c in (" ", "—", "·", ",", "(", "[", ":", "/", "→", "+"))
    if cut < limit // 2:
        return text
    return window[:cut].rstrip(" —·,([:/→+") + "…"


def _bar(pct: float | int | None, width: int = 9) -> str:
    """도달율 막대. 못 잰 값은 막대 대신 빈칸(가짜로 채우지 않는다)."""
    if not isinstance(pct, (int, float)):
        return " " * width
    filled = max(0, min(width, round(width * float(pct) / 100.0)))
    return "▓" * filled + "░" * (width - filled)


def _row(label: str, pct: float | int | None, tail: str = "") -> str:
    label = f"{label:<9}"
    if not isinstance(pct, (int, float)):
        # 비율은 못 내지만 실제 값이 있으면 그 값만 적는다('미측정 · 5.8억' 같은 겹말 방지).
        return f"{label} {tail}" if tail else f"{label} 미측정"
    return f"{label} {_bar(pct)} {round(pct):>3}%{(' ' + tail) if tail else ''}"


PLAN_PATH = ROOT / "status" / "monthly_ops_plan.json"


def _plan_month_target(plan: dict | None, mkey: str) -> float | None:
    """그 달 운영계획이 잡아 둔 월 매출 목표(원). 계획에 없으면 None — 지어내지 않는다.

    ★연 72억 ÷ 12 = 6억이 아니다. 상반기 부족분을 하반기에 얹어 계획이 6.5~6.6억으로 잡혀
    있다(GM 2026-07-31 '부족분이 있으니 더 채워야겠지'). 그 판단은 이미 월간 운영계획에
    들어 있으므로 여기서 다시 계산하지 않고 **계획을 읽는다**(약속 L01).
    """
    try:
        for o in ((plan or {}).get("months") or {}).get(mkey, {}).get("objectives") or []:
            met = o.get("metric") or {}
            if str(met.get("name") or "").replace(" ", "") in ("월매출", "매출") \
                    and isinstance(met.get("target"), (int, float)):
                return float(met["target"])
    except Exception:
        pass
    return None


def _sales_rows(home: dict | None, plan: dict | None, mkey: str) -> list[tuple[str, float | None, str]]:
    """회사 북극성(매출) 줄 — 연 목표·이번 달 목표 대비·남은 달에 필요한 월 매출.

    ★2026-07-31 GM 지적으로 다시 짰다: "연간 72억이면 월은 6억이겠지? 근데 부족분이 있으니
    더 채워야겠지?" — 예전 블록은 월 목표를 못 찾으면 '미설정'이라고만 적고 끝냈다. 목표
    대비가 없으면 그 줄은 그냥 현황 숫자다. 이제 ①계획의 이번 달 목표 대비 ②연 목표까지
    남은 달에 **월 얼마씩 필요한지**를 같이 낸다(부족분이 자동으로 드러난다).
    """
    d = ((home or {}).get("data") or {}).get("sales") or {}
    rows: list[tuple[str, float | None, str]] = []
    year, year_rate, year_target = d.get("year"), d.get("yearRate"), d.get("yearTarget")
    if isinstance(year_rate, (int, float)) and isinstance(year_target, (int, float)):
        amt = f"{year / 100000000:.1f}억 / {year_target / 100000000:.0f}억" if isinstance(year, (int, float)) else ""
        rows.append((f"매출 연{year_target / 100000000:.0f}억", float(year_rate), amt))

    month, cur = d.get("month"), d.get("curMonth")
    m_target = _plan_month_target(plan, mkey) or (d.get("target") if isinstance(d.get("target"), (int, float)) else None)
    if isinstance(month, (int, float)):
        if m_target:
            gap = (month - m_target) / 100000000
            rows.append((f"{cur}월 {m_target / 100000000:.1f}억", month / m_target * 100,
                         f"{month / 100000000:.2f}억 ({gap:+.2f}억)"))
        else:
            rows.append((f"{cur}월 매출", None, f"{month / 100000000:.2f}억 (이번 달 목표가 계획에 없음)"))

    # 남은 달에 월 얼마씩 필요한가 — '부족분을 어디서 메우나'가 한 줄로 보이게.
    if isinstance(year, (int, float)) and isinstance(year_target, (int, float)) and isinstance(cur, int):
        # year(연 누계)가 이번 달분을 아직 안 반영했으면(hasCurMonth False) 이번 달을
        # 남은 달에 포함해야 분자·분모가 짝이 맞는다. 그냥 12-cur 로 되돌리지 말 것 —
        # 8월 1일 GM 지적: 7월까지만 합산된 분자에서 8월을 남은 달에서도 빼면 이중차감.
        left_months = 12 - cur + (0 if d.get("hasCurMonth") else 1)
        if left_months > 0 and year_target > year:
            need = (year_target - year) / left_months / 100000000
            rows.append((f"남은 {left_months}개월", None, f"월 {need:.2f}억씩 필요"))
    return rows


def _plan_rows(plan: dict | None, mkey: str, label: str) -> list[str]:
    """그 달 운영계획의 진척 요약 + 가장 뒤처진 것.

    ★2026-07-31 GM 지적 — "AI C레벨들 % 만들어두면 뭐해? 그건 의미가 없을 것 같은데,
      7월 / 8월 월간계획보고가 반영이 되어야 할 것 같은데."
      역할별 북극성 도달율(웰리 50%·시토 0%…)을 걷어내고 그 자리를 **월간 운영계획 진척**으로
      바꾼다. GM 이 보는 것은 AI 가 몇 % 인지가 아니라 이 달에 하기로 한 일이 어디까지 갔나다.
    """
    m = ((plan or {}).get("months") or {}).get(mkey)
    if not isinstance(m, dict):
        return []
    objs = [o for o in (m.get("objectives") or []) if isinstance(o, dict)]
    if not objs:
        return []
    nick = (plan or {}).get("owner_nick") or {}
    cnt: dict[str, int] = {}
    for o in objs:
        s = str(o.get("status") or "?")
        cnt[s] = cnt.get(s, 0) + 1
    prog = [o["progress"] for o in objs if isinstance(o.get("progress"), (int, float))]
    avg = round(sum(prog) / len(prog)) if prog else None

    head = f"📋 {label} 운영계획 — 목표 {len(objs)}개"
    parts = [f"{k} {v}" for k, v in sorted(cnt.items(), key=lambda x: -x[1])]
    if parts:
        head += " · " + " · ".join(parts)
    if avg is not None:
        head += f" · 평균 {avg}%"
    out = ["", head]
    if m.get("theme"):
        out.append("   " + _trim(str(m["theme"]), 52))

    stalled = [o for o in objs if isinstance(o.get("progress"), (int, float)) and o["progress"] <= 10]
    if stalled:
        stalled.sort(key=lambda o: o["progress"])
        for o in stalled[:2]:
            who = nick.get(str(o.get("owner") or ""), str(o.get("owner") or ""))
            out.append(f"   📉 {o['progress']}% {_trim(str(o.get('title') or ''), 34)} — {who}")
        if len(stalled) > 2:
            out.append(f"   그 외 손 안 댄 것 {len(stalled) - 2}건")
    return out


def _prev_snapshot() -> dict:
    """어제(또는 가장 최근 이전) 도달율 — 이력이 없으면 빈 dict(변화 줄을 안 낸다)."""
    try:
        lines = [l for l in HISTORY_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        today = datetime.now(KST).strftime("%Y-%m-%d")
        for line in reversed(lines):
            rec = json.loads(line)
            if rec.get("date") != today:
                return rec.get("roles") or {}
    except Exception:
        pass
    return {}


def record_history(data: dict) -> None:
    """오늘치 도달율을 하루 1줄로 적립. '가장 좁혀진 곳'은 이 이력이 2일 이상 쌓여야 나온다
    — 없는 이력으로 변화량을 지어내지 않기 위해서다(첫날은 그 줄이 아예 안 보인다)."""
    try:
        today = datetime.now(KST).strftime("%Y-%m-%d")
        roles = {r: v.get("reach_pct") for r, v in (data.get("roles") or {}).items()}
        prev = []
        if HISTORY_PATH.exists():
            prev = [l for l in HISTORY_PATH.read_text(encoding="utf-8").splitlines()
                    if l.strip() and json.loads(l).get("date") != today]
        prev.append(json.dumps({"date": today, "roles": roles}, ensure_ascii=False))
        HISTORY_PATH.write_text("\n".join(prev) + "\n", encoding="utf-8")
    except Exception:
        pass


def build_northstar_block(title: str = "북극성 대비") -> str:
    """모든 보고 맨 위에 붙는 '목표 대비 어디쯤' 블록. 실패해도 빈 문자열(보고를 끊지 않는다)."""
    try:
        home = _load_json(HOME_KPI_PATH)
        plan = _load_json(PLAN_PATH)
        now = datetime.now(KST)
        mkey = now.strftime("%Y-%m")
        nxt = (now.replace(day=1) + timedelta(days=32)).strftime("%Y-%m")

        lines = [f"🌟 {title} — {now.month}/{now.day}"
                 f"({'월화수목금토일'[now.weekday()]})", ""]

        for label, pct, tail in _sales_rows(home, plan, mkey):
            lines.append(_row(label, pct, tail))

        # ★역할별 도달율(웰리 50%·시토 0%…)은 뺐다 — GM 2026-07-31: "AI C레벨들 % 만들어두면
        #   뭐해? 그건 의미가 없을 것 같은데, 7월/8월 월간계획보고가 반영이 되어야 할 것 같은데."
        #   그 자리를 이 달·다음 달 운영계획 진척으로 바꾼다. (역할 도달율 계산 자체는
        #   compute() 에 그대로 살아 있어 다른 화면·집계는 무영향.)
        lines += _plan_rows(plan, mkey, f"{now.month}월")
        lines += _plan_rows(plan, nxt, f"{int(nxt[5:])}월")

        return "\n".join(lines)
    except Exception:
        return ""


def main() -> None:
    data = compute()
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    record_history(data)
    print(f"[northstar_reach] {data['generated_at_kst']}")
    for rid, v in data["roles"].items():
        pct = v.get("reach_pct")
        pct_s = f"{pct}%" if isinstance(pct, (int, float)) else "null(측정 개통 전)"
        print(f"  {rid:5s}: {v['mode']:9s} 도달율={pct_s}  · {v.get('basis', '')}")
    print(f"  -> {OUT_PATH}")


if __name__ == "__main__":
    main()
