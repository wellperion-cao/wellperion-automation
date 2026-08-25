# -*- coding: utf-8 -*-
"""매출 보고 시트 「보고」탭 P20 — 시설·청결·주차·밸류업 운영 현황 채우기.

왜 있나
    09:30 매출보고 이미지는 사람이 만든 시트 한 조각(H2:S21)을 그대로 찍어 보낸다.
    그 안 P20 칸에 3부서 현황을 매일 아침 09:00 에 채워 두면, 회장님·관리부·부서장·
    운영부가 매출과 같은 화면에서 운영 현황을 함께 본다(GM 지시 2026-08-18).

무엇을 새로 만들지 않았나
    · 수집기 — 점검·접수 숫자는 scripts/collectors/ops_shared.py 의 기존 함수로 받는다.
    · 발신 관문 — 카톡으로 보내지 않는다. 시트에 쓰는 것뿐이다.
    · 상쇄(약속 L21 net-zero) — 같은 날 18:30 저녁 카톡 재수집(값 0건)을 지웠다.

쓰는 법
    python scripts/sales_report_ops_summary.py --dry-run   # 만들 텍스트만 보기
    python scripts/sales_report_ops_summary.py             # 시트 P20 에 쓰기

    환경변수(telegram_bot/.env 또는 OS 환경):
      SALES_OPS_GAS_URL   시트에 붙인 웹앱 주소(/exec)
      SALES_OPS_GAS_TOKEN 그 웹앱의 TOKEN (기본 wellperion-2026)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.collectors.ops_shared import (  # noqa: E402
    RECEPTION_EXEC_URL,
    gas_get,
    reception_elapsed_days,
)
from scripts.coo_registry import CHECK_API  # noqa: E402

WEEKDAY_KO = "월화수목금토일"


def _env(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if v:
        return v
    envfile = ROOT / "telegram_bot" / ".env"
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default


def facility_line(day: str) -> list[str]:
    """시설 — 오늘 점검 진행과 특이사항. 못 세면 그 줄을 빼고 빈 리스트를 준다(0 위장 금지)."""
    r = gas_get(CHECK_API, {"action": "weekly", "dept": "facility"}, label="facility")
    if r is None:
        return []
    rows = (r.json() or {}).get("data") or []
    today = next((x for x in rows if str(x.get("date")) == day), None)
    if not today:
        return []
    out = [f" · 일일점검 {today.get('done')}/{today.get('total')}"
           + (" · 이상 없음" if not str(today.get("issue") or "").strip() else "")]
    issue = str(today.get("issue") or "").strip()
    if issue:
        out.append(f" · 특이사항 — {issue[:60]}")
    return out


def support_line(day: str) -> list[str]:
    """청결 — 지원부 완료 현황과 남/여 격차."""
    r = gas_get(CHECK_API, {"action": "today_live", "dept": "support", "date": day}, label="support")
    if r is None:
        return []
    d = r.json() or {}
    g = d.get("byGender") or {}
    m, f = g.get("m") or {}, g.get("f") or {}
    out = [f" · 일일점검 {d.get('done')}/{d.get('total')}"
           + (f" (남 {m.get('pct')}% / 여 {f.get('pct')}%)" if m and f else "")]
    # 한쪽이 크게 낮으면 그것만 짚는다 — 매일 같은 문장을 반복하지 않는다.
    try:
        gap = abs(int(m.get("pct", 0)) - int(f.get("pct", 0)))
        if gap >= 20:
            low = "여자구역" if int(m.get("pct", 0)) > int(f.get("pct", 0)) else "남자구역"
            out.append(f" · {low} 완료율 낮음 — 원인 확인 중")
    except (TypeError, ValueError):
        pass
    return out


def reception_line() -> list[str]:
    """미처리 접수 — 시설부 기준 건수와 최장 경과일."""
    r = gas_get(RECEPTION_EXEC_URL, {"action": "reg_list"}, label="reception")
    if r is None:
        return []
    d = r.json()
    rows = d if isinstance(d, list) else (d.get("data") or d.get("items") or [])
    rows = [x for x in rows if isinstance(x, dict)]
    op = [x for x in rows if str(x.get("status")) in ("접수", "처리중")]
    if not op:
        return []
    fac = [x for x in op if str(x.get("dept") or "") == "시설부"]
    if not fac:
        return []
    oldest = max(reception_elapsed_days(x) for x in fac)
    return [f" · 미처리 접수 {len(fac)}건 — 최장 {oldest}일"]


# 감염병 예방 강화 — GM 지시 2026-08-25(중국 코로나 재확산 대비). 3부서가 매일 같은 문장을
# 보고 움직이도록 보고 칸에 고정으로 싣는다. 기존 점검 항목에 얹는 방식이라 새 점검표를 만들지
# 않는다(약속 L21). 상황이 끝나면 이 리스트를 비우면 블록째 사라진다 — 끄는 스위치를 따로 두지
# 않는다. 같은 문안이 부서 화면(지원부·주차관리부·시설부 체계)에도 실려 있다.
INFECTION_PREVENTION: list[str] = [
    " · 접점 소독 — 손잡이·락커·키오스크·발권기, 오픈 전·마감 후 2회 (기존 청소 동선에 포함)",
    " · 환기 — 사우나·수면실·찜질방 회차마다 10분, 창 없는 구역은 배기팬 상시",
    " · 공용 비품 — 바스타올·매트리스·침구, 회차 점검마다 상태 확인 후 교체",
    " · 직원 — 발열·기침 시 근무 제외 후 즉시 보고, 청소 시 마스크·장갑 착용",
    " · 비품 재고 — 손소독제·마스크 주 1회 확인(리셉션·사우나·주차 3곳)",
]


def build_text(day: str, value_up: list[str]) -> str:
    d = datetime.strptime(day, "%Y-%m-%d").date()
    head = f"[운영 현황]  시설 · 지원 · 주차   {d.month}/{d.day}({WEEKDAY_KO[d.weekday()]})"

    blocks: list[tuple[str, list[str]]] = [
        ("■ 시설물 관리", facility_line(day) + reception_line()),
        ("■ 청결 관리", support_line(day)),
        ("■ 주차 관리", _parking_lines()),
        ("■ 내부 환경 개선", value_up),
    ]
    # 이 블록만 '집계 중' 채움 대상이 아니다 — 수집 실패가 아니라 지침이라, 비면 안 싣는다.
    if INFECTION_PREVENTION:
        blocks.append(("■ 감염병 예방 (3부서 공통)", list(INFECTION_PREVENTION)))
    parts = [head]
    for title, lines in blocks:
        if not lines:
            lines = [" · 집계 중"]
        parts.append("")
        parts.append(title)
        parts.extend(lines)
    return "\n".join(parts)


def build_contact_text(send_day: str) -> str:
    """「보고」탭 I16 — 금일 예상 컨택 및 매출 현황 (2026-08-21 시토 · 배738).

    지금까지 사람이 손으로 치던 칸이다. 09:30 보고가 나가는 날(send_day) 기준으로
    ①그날 투어·체험 예약자 ②전날 LOSS 를 적는다. 실무진이 쓰던 문구 틀을 그대로 따른다.

    ★원천을 새로 만들지 않는다: 예약은 아침 정리(ops_daily_digest.build_reservation_block)가
      쓰는 것과 **같은 규칙** — member_inquiry_list 의 reservations[].date 매칭이다.
      2026-08-21 실측에서 체험일자(exp1) 로 뽑았더니 이미 등록 끝난 분까지 딸려 오고
      실무진이 적은 분은 빠졌다. 사람이 세는 것과 어긋난 숫자가 회장님 보고에 실리면 안 된다.
    """
    from scripts.collectors.ops_shared import FUNNEL_EXEC_URL  # noqa: PLC0415

    prev_day = (date.fromisoformat(send_day) - timedelta(days=1)).isoformat()
    md = lambda d: f"{int(d[5:7])}/{int(d[8:10])}"  # noqa: E731 — '8/22' 표기

    # ── 예약 ──
    events: list[tuple[str, str]] = []
    resp = gas_get(FUNNEL_EXEC_URL, {"action": "member_inquiry_list"}, timeout=40,
                   label="I16 예약")
    if resp is None:
        return ""      # 못 읽으면 아무것도 쓰지 않는다 — 빈 값으로 사람 글을 지우지 않는다
    try:
        data = resp.json()
        if not data.get("ok"):
            return ""
        for r in data.get("data", []) or []:
            for res in (r.get("reservations") or []):
                if res.get("date") == send_day:
                    events.append((res.get("time") or "", r.get("name") or ""))
    except Exception:
        return ""
    events.sort(key=lambda x: x[0])
    names = " / ".join(n for _, n in events if n)

    lines = [f"{md(send_day)} 기준 [총 예약자  {len(events)}명]", ""]
    lines.append(f"[신   규  :  {len(events)} 명]")
    lines.append(f" - 투어 및 체험 : {names}" if names else " - 투어 및 체험 : ")
    lines.append("[재등록 : 0명]")
    lines.append("- 멤버십 : ")
    lines.append("")

    # ── 전날 LOSS ── 종료회원 원장 스냅샷(19:00 자동 갱신)에서 센다
    loss: list[str] = []
    snap = ROOT / "status" / "member_ended_snapshot.json"
    try:
        rows = json.loads(snap.read_text(encoding="utf-8")).get("rows") or []
        for r in rows:
            for k, v in r.items():
                if k.replace("\n", "") == "LOSS일자" and str(v or "").strip()[:10] == prev_day:
                    nm = next((str(vv) for kk, vv in r.items() if kk.replace("\n", "") == "회원명"), "")
                    reason = next((str(vv).strip() for kk, vv in r.items() if kk.replace("\n", "") == "미등록사유"), "").strip()
                    if nm:
                        loss.append(f"{nm}({reason})" if reason else nm)
                    break
    except Exception:
        pass
    lines.append(f"{md(prev_day)} 기준 [LOSS : {len(loss)}명]")
    lines.append(f"- 멤버십 : {' / '.join(loss)}" if loss else "- 멤버십 :")
    lines.append("- 단   기 :")
    return "\n".join(lines)


def _parking_lines() -> list[str]:
    """주차 — 지금은 점검이 종이 체크라 셀 숫자가 없다. 없는 숫자를 지어내지 않는다.
    ponytail: 제출형 점검(시토 배672)이 붙으면 여기서 support_line 과 같은 방식으로 센다."""
    return [" · 일일점검 전산화 진행 중"]


LAST_WRITE = ROOT / "status" / "sales_ops_last_write.json"


def _human_edited(prev: dict, current: str | None, today: str) -> bool:
    """같은 날 우리가 쓴 값이 시트에서 달라져 있으면 = 사람이 손을 댔다.

    하루가 바뀌면 내용 자체가 새것이라 판정 대상이 아니다(그 갱신이 이 칸의 본래 일이다).
    현재 값을 못 읽었으면(None) 막지 않는다 — 못 읽은 것을 근거로 아침 기입을 거르면
    조용히 며칠씩 안 채워진다.
    """
    if not prev or prev.get("day") != today or current is None:
        return False
    return current.strip() != str(prev.get("text") or "").strip()


def post_to_sheet(text: str, cell: str = "P20") -> dict:
    url = _env("SALES_OPS_GAS_URL")
    if not url:
        return {"ok": False, "error": "SALES_OPS_GAS_URL 이 없습니다 — 웹앱 배포 후 .env 에 넣어 주세요"}
    token = _env("SALES_OPS_GAS_TOKEN", "wellperion-2026")
    today = date.today().isoformat()

    try:
        seen = json.loads(LAST_WRITE.read_text(encoding="utf-8"))
    except Exception:
        seen = {}

    # ★사람이 고친 칸은 같은 날 다시 덮어쓰지 않는다(GM 지시 2026-08-23 · 배749).
    # 실장이 손으로 넣은 LOSS 사유가 재실행 때 지워지던 경로가 여기다.
    if (seen.get(cell) or {}).get("day") == today:
        resp = gas_get(url, {"token": token, "cell": cell}, timeout=30, label=f"{cell} 현재값")
        current = None
        if resp is not None:
            try:
                data = resp.json()
                current = data.get("value") if data.get("ok") else None
            except Exception:
                current = None
        if _human_edited(seen[cell], current, today):
            return {"ok": True, "skipped": "human-edit", "cell": cell,
                    "note": f"{cell} 은 사람이 고쳐 두었습니다 — 덮어쓰지 않았습니다"}

    body = json.dumps({"token": token, "cell": cell, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "text/plain"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    if res.get("ok"):
        seen[cell] = {"day": today, "text": text}
        LAST_WRITE.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="매출 보고 시트 P20 운영 현황 채우기")
    # ★ 기본은 **어제**다. 09:30 매출보고는 전날 실적을 보고하므로(캡션 "8.16(일) 매출 및
    # 운영사항"), 운영 현황도 같은 날이어야 한 화면에서 앞뒤가 맞는다. 오늘로 잡으면
    # 매출은 전날인데 현황만 당일이 되고, 게다가 09:00 시점의 당일 점검은 아침 회차뿐이라 거의 비어 있다.
    ap.add_argument("--date", default=(date.today() - timedelta(days=1)).isoformat(),
                    help="기준일(기본=어제 · 매출보고와 같은 날)")
    ap.add_argument("--cell", default="P20")
    ap.add_argument("--dry-run", action="store_true", help="만들 텍스트만 보고 시트엔 쓰지 않는다")
    ap.add_argument("--value-up", action="append", default=[],
                    help="내부 환경 개선 줄(여러 번 지정 가능). 없으면 '집계 중'")
    ap.add_argument("--contact", action="store_true",
                    help="I16(금일 예상 컨택 및 매출 현황)도 함께 채운다 — 09:00 예약이 쓰는 길")
    ap.add_argument("--send-day", default=date.today().isoformat(),
                    help="09:30 보고가 나가는 날(기본 오늘). I16 의 '기준' 날짜가 된다")
    ap.add_argument("--only-contact", action="store_true", help="I16 만 채운다(P20 건너뜀)")
    args = ap.parse_args()

    rc = 0
    if not args.only_contact:
        value_up = [f" · {v}" for v in args.value_up]
        text = build_text(args.date, value_up)
        print(text)
        print("---")
        if args.dry_run:
            print(f"[미리보기 P20] {len(text)}자 · {text.count(chr(10)) + 1}줄 — 시트에 쓰지 않았습니다")
        else:
            res = post_to_sheet(text, args.cell)
            print("[결과 P20]", json.dumps(res, ensure_ascii=False))
            rc = rc or (0 if res.get("ok") else 1)

    if args.contact or args.only_contact:
        ctext = build_contact_text(args.send_day)
        if not ctext:
            # ★빈 값으로 사람이 쓴 글을 지우지 않는다. 원천을 못 읽으면 그냥 손대지 않는다.
            print("[I16] 원천(문의 원장)을 못 읽어 이번엔 쓰지 않았습니다 — 기존 내용 그대로 둡니다")
            return rc or 1
        print(ctext)
        print("---")
        if args.dry_run:
            print(f"[미리보기 I16] {len(ctext)}자 · {ctext.count(chr(10)) + 1}줄 — 시트에 쓰지 않았습니다")
        else:
            cres = post_to_sheet(ctext, "I16")
            print("[결과 I16]", json.dumps(cres, ensure_ascii=False))
            rc = rc or (0 if cres.get("ok") else 1)
    return rc


def _selftest() -> None:
    """텍스트 조립만 검사한다(네트워크 없이). 빈 묶음이 '집계 중'으로 채워지는지."""
    out = build_text("2026-08-18", [])
    assert "[운영 현황]" in out
    assert out.count("■") == (4 + (1 if INFECTION_PREVENTION else 0)), out
    assert "집계 중" in out  # value_up 이 비었으니 그 자리는 집계 중
    assert "8/18(화)" in out, out
    # 지침 블록은 '집계 중'으로 채워지지 않는다 — 비면 블록째 빠진다
    saved = list(INFECTION_PREVENTION)
    INFECTION_PREVENTION.clear()
    assert "감염병 예방" not in build_text("2026-08-18", [])
    INFECTION_PREVENTION.extend(saved)
    assert "감염병 예방" in build_text("2026-08-18", [])

    # 사람 손입력 보호 판정
    prev = {"day": "2026-08-24", "text": "자동으로 쓴 값"}
    assert _human_edited(prev, "자동으로 쓴 값 + 실장 추가", "2026-08-24")      # 고쳐졌다 → 막는다
    assert not _human_edited(prev, "자동으로 쓴 값", "2026-08-24")              # 그대로 → 덮어쓴다
    assert not _human_edited(prev, "실장 추가", "2026-08-25")                   # 날이 바뀜 → 덮어쓴다
    assert not _human_edited(prev, None, "2026-08-24")                          # 못 읽음 → 막지 않는다
    assert not _human_edited({}, "무엇이든", "2026-08-24")                      # 기록 없음 → 덮어쓴다
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        raise SystemExit(main())
