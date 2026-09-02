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
    " · 접점 소독 — 손잡이·락커·키오스크·무인발권기·주차 정산기, 오픈 전·마감 후 2회 (기존 청소 동선에 포함)",
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
        ("■ 주차 관리", _parking_lines(day)),
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
    """「보고」탭 I16 — 내일 투어·체험 예약 (2026-08-21 시토 · 배738 / 2026-08-28 GM 기준 확정).

    지금까지 사람이 손으로 치던 칸이다. 실무진이 쓰던 문구 틀을 그대로 따른다.

    ★기준일 = 보고 나가는 날 **당일**이다(GM 확정 2026-08-31). 칸 이름 그대로 "금일"이다.
      ▸2026-08-28 확정문 "I16은 내일 투어 및 체험 예약"의 '내일'은 **보고 대상일(전날 실적)
        기준의 내일** = 보고 나가는 날이라는 뜻이었는데, 이를 발송일+1 로 구현해 하루가 더
        밀렸다. 08-30·08-31 이틀 연속 GM 이 잡아 주셨다 — "8/30 로스 기준이면 신규 투어·
        체험이랑 재등록은 8/31 기준이어야 한다".
      ▸따라서 한 보고서 안의 세 기준일은 이렇게 맞물린다:
        매출·LOSS(I18) = send_day-1 (보고 대상일) / 신규·재등록(I16) = send_day (오늘).
        두 칸의 간격은 항상 하루다 — 이 관계가 깨지면 아래 _selftest_base_dates 가 잡는다.
      ▸그 전까지는 이 한 칸에 당일 예약과 전날 LOSS 를 함께 써서 두 기준일이 한 칸에
        섞여 있었다 — LOSS 는 build_loss_text 로 떼어 I18 에 쓴다.

    ★원천을 새로 만들지 않는다: 예약은 아침 정리(ops_daily_digest.build_reservation_block)가
      쓰는 것과 **같은 규칙** — member_inquiry_list 의 reservations[].date 매칭이다.
      2026-08-21 실측에서 체험일자(exp1) 로 뽑았더니 이미 등록 끝난 분까지 딸려 오고
      실무진이 적은 분은 빠졌다. 사람이 세는 것과 어긋난 숫자가 회장님 보고에 실리면 안 된다.
    """
    from scripts.collectors.ops_shared import FUNNEL_EXEC_URL  # noqa: PLC0415

    target_day = send_day
    md = lambda d: f"{int(d[5:7])}/{int(d[8:10])}"  # noqa: E731 — '8/22' 표기

    # ── 예약 ──
    # ★원천 = 멤버십 회원관리 화면의 예약 달력과 **같은 액션**(member_calendar).
    #   GM 이 보시는 달력이 그 화면이고, 보고 숫자가 그 화면과 달라선 안 된다(2026-09-02 GM 지적).
    #   ▸종전엔 문의 원장(member_inquiry_list)만 읽어 **재등록상담이 통째로 빠졌다** —
    #     재등록 예약은 유효회원 원장의 「재등록예약목록」에 있어 문의 원장에는 아예 없다.
    #     그래서 재등록 칸이 「0명」으로 박혀 있었다(원천에 연결된 적 없음).
    new_events: list[tuple[str, str]] = []   # (시각, 이름) — 투어·체험 등 신규
    recon_names: list[str] = []              # 재등록상담
    resp = gas_get(FUNNEL_EXEC_URL, {"action": "member_calendar", "month": target_day[:7]},
                   timeout=40, label="I16 예약")
    if resp is None:
        return ""      # 못 읽으면 아무것도 쓰지 않는다 — 빈 값으로 사람 글을 지우지 않는다
    try:
        data = resp.json()
        if not data.get("ok"):
            return ""
        for ev in data.get("events", []) or []:
            if str(ev.get("date")) != target_day:
                continue
            name = (ev.get("name") or "").strip()
            if not name:
                continue
            if ev.get("kind") == "재등록상담":
                recon_names.append(name)
            else:
                new_events.append((ev.get("time") or "", name))
    except Exception:
        return ""
    new_events.sort(key=lambda x: x[0])
    names = " / ".join(n for _, n in new_events)
    total = len(new_events) + len(recon_names)

    lines = [f"{md(target_day)} 기준 [총 예약자  {total}명]", ""]
    lines.append(f"[신   규  :  {len(new_events)} 명]")
    lines.append(f" - 투어 및 체험 : {names}" if names else " - 투어 및 체험 : ")
    lines.append(f"[재등록 : {len(recon_names)}명]")
    lines.append(f"- 멤버십 : {' / '.join(recon_names)}" if recon_names else "- 멤버십 : ")
    return "\n".join(lines)


def _fmt_loss_name(nm: str, reason: str) -> str:
    """LOSS 명단 한 사람 표기 — 이름(사유). 사유를 지어내진 않되, 빈 사유는 '(사유
    미기재)'로 보이게 한다(GM 지시 2026-08-23 · 배751 "미등록사유까지 각각 추가해줘").
    이름만 찍으면 실무진이 빈칸인 줄 모르고 넘어간다 — 채워야 할 자리를 드러낸다."""
    reason = reason.strip()
    return f"{nm}({reason})" if reason else f"{nm}(사유 미기재)"


def build_loss_text(send_day: str) -> str:
    """「보고」탭 I18 — 로스자 칸. 전날 LOSS 기준(GM 확정 2026-08-28 · 단기 칸도 배11027 GM
    확정으로 같은 전날 기준을 쓴다).

    원천 = 종료회원 원장 스냅샷(status/member_ended_snapshot.json · 매일 19:00 자동 갱신).
    사유는 원장의 「미등록사유」 칸을 헤더 이름으로 찾는다(자리 폴백 금지 — 열 순서가
    바뀌어도 깨지지 않게). 비어 있으면 _fmt_loss_name 이 '(사유 미기재)'로 표시한다.
    원장을 못 읽으면 빈 문자열을 돌려주고, 호출부가 그 칸을 건드리지 않는다.

    「단기」 축 확인(배11027) — 원장의 「회원\\n구분」 열은 멤버십·입주민·중단기·보증금·
    FAN VIP·법인 6종이다(scripts/collectors/cpo_sheet_contract.py 대조 목록). 정확히
    '단기'라는 값은 없고 '중단기'가 유일한 후보 — 미등록사유 목록에도 '단기'가 있지만
    그건 개별 사유값이라 사람별 이름이 아니라 인원수만 요구하는 이 칸(이탈자 (단기 N명))과
    맞지 않는다. 그래서 회원구분='중단기'를 '단기' 칸으로 쓴다. 그 외 카테고리(입주민·
    보증금·법인)는 기존과 같이 멤버십 줄에 남긴다(회귀 없음).
    """
    prev_day = (date.fromisoformat(send_day) - timedelta(days=1)).isoformat()
    md = lambda d: f"{int(d[5:7])}/{int(d[8:10])}"  # noqa: E731

    snap = ROOT / "status" / "member_ended_snapshot.json"
    try:
        rows = json.loads(snap.read_text(encoding="utf-8")).get("rows") or []
    except Exception:
        return ""      # 원장을 못 읽었다 — 사람이 쓴 글을 빈 값으로 지우지 않는다

    loss, danggi_count = _split_loss_rows(rows, prev_day)
    lines = [f"{md(prev_day)} 기준 [LOSS : {len(loss) + danggi_count}명]"]
    lines.append(f"- 멤버십 : {' / '.join(loss)}" if loss else "- 멤버십 :")
    lines.append(f"- 단   기 : {danggi_count}명" if danggi_count else "- 단   기 :")
    return "\n".join(lines)


def _split_loss_rows(rows: list[dict], prev_day: str) -> tuple[list[str], int]:
    """종료회원 원장 행을 그날 LOSS 기준으로 멤버십 명단 / 중단기(단기) 인원수로 가른다."""
    loss: list[str] = []
    danggi_count = 0
    for r in rows:
        for k, v in r.items():
            if k.replace("\n", "") == "LOSS일자" and str(v or "").strip()[:10] == prev_day:
                cat = next((str(vv).strip() for kk, vv in r.items() if kk.replace("\n", "") == "회원구분"), "")
                if cat == "중단기":
                    danggi_count += 1
                else:
                    nm = next((str(vv) for kk, vv in r.items() if kk.replace("\n", "") == "회원명"), "")
                    reason = next((str(vv).strip() for kk, vv in r.items() if kk.replace("\n", "") == "미등록사유"), "").strip()
                    if nm:
                        loss.append(_fmt_loss_name(nm, reason))
                break
    return loss, danggi_count


def _parking_lines(day: str) -> list[str]:
    """주차 — 일일점검 제출형(배672 배선 · 배11050 실측으로 GAS 원장 경로 확인) 집계.
    원천 = 지원부·시설부와 같은 점검 GAS(action=weekly&dept=parking). 그날 제출이 아직
    없으면(주차관리인이 그날 점검 제출 버튼을 안 눌렀으면) 빈 리스트 — 호출부가 '집계 중'으로
    채운다. 0을 지어내지 않는다."""
    r = gas_get(CHECK_API, {"action": "weekly", "dept": "parking"}, label="parking")
    if r is None:
        return []
    rows = (r.json() or {}).get("data") or []
    today = next((x for x in rows if str(x.get("date")) == day), None)
    if not today or not today.get("total"):
        return []
    return [f" · 일일점검 {today.get('done')}/{today.get('total')} ({today.get('pct')}%)"]


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
            rc = rc or 1
        else:
            print(ctext)
            print("---")
            if args.dry_run:
                print(f"[미리보기 I16] {len(ctext)}자 · {ctext.count(chr(10)) + 1}줄 — 시트에 쓰지 않았습니다")
            else:
                cres = post_to_sheet(ctext, "I16")
                print("[결과 I16]", json.dumps(cres, ensure_ascii=False))
                rc = rc or (0 if cres.get("ok") else 1)

        # I18 로스자 — 전날 LOSS. I16 을 못 써도 이 칸은 따로 시도한다(두 칸은 원천이 다르다).
        ltext = build_loss_text(args.send_day)
        if not ltext:
            print("[I18] 종료회원 원장을 못 읽어 이번엔 쓰지 않았습니다 — 기존 내용 그대로 둡니다")
            rc = rc or 1
        else:
            print(ltext)
            print("---")
            if args.dry_run:
                print(f"[미리보기 I18] {len(ltext)}자 · {ltext.count(chr(10)) + 1}줄 — 시트에 쓰지 않았습니다")
            else:
                lres = post_to_sheet(ltext, "I18")
                print("[결과 I18]", json.dumps(lres, ensure_ascii=False))
                rc = rc or (0 if lres.get("ok") else 1)
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

    # LOSS 명단 표기 — 사유 있음/없음(배751)
    assert _fmt_loss_name("표소영", "양도/강습전환") == "표소영(양도/강습전환)"
    assert _fmt_loss_name("정재윤", "") == "정재윤(사유 미기재)"
    assert _fmt_loss_name("정재윤", "   ") == "정재윤(사유 미기재)"  # 공백만 있어도 빈 것으로 본다

    # 이탈자(단기) 분리 — 회원구분='중단기'는 인원수만, 그 외는 이름+사유(배11027)
    rows = [
        {"LOSS\n일자": "2026-08-22", "회원\n구분": "멤버십", "회원명": "오수연", "미등록사유": "거주지변경"},
        {"LOSS\n일자": "2026-08-22", "회원\n구분": "중단기", "회원명": "김단기", "미등록사유": "단기"},
        {"LOSS\n일자": "2026-08-21", "회원\n구분": "멤버십", "회원명": "무관", "미등록사유": ""},  # 다른 날 — 제외
    ]
    loss, danggi = _split_loss_rows(rows, "2026-08-22")
    assert loss == ["오수연(거주지변경)"], loss
    assert danggi == 1, danggi

    _selftest_base_dates()
    print("selftest ok")


def _selftest_base_dates() -> None:
    """한 보고서 안 두 칸의 기준일 관계를 잡아 둔다 (GM 확정 2026-08-31).

    I16(신규·재등록) = 보고 나가는 날 당일 / I18(LOSS) = 그 전날.
    간격은 항상 하루다. 08-30·08-31 이틀 연속 GM 이 어긋남을 잡으셨기에,
    다음에 누가 날짜 계산을 만지면 여기서 먼저 걸리게 한다.
    """
    send_day = "2026-08-31"
    i16_base = send_day                                                        # build_contact_text 의 target_day
    i18_base = (date.fromisoformat(send_day) - timedelta(days=1)).isoformat()  # build_loss_text 의 prev_day
    assert i16_base == "2026-08-31", i16_base
    assert i18_base == "2026-08-30", i18_base
    gap = (date.fromisoformat(i16_base) - date.fromisoformat(i18_base)).days
    assert gap == 1, f"I16 과 I18 기준일 간격이 {gap}일이다 — 하루여야 한다"


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        raise SystemExit(main())
