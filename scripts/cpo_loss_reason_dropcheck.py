# -*- coding: utf-8 -*-
"""LOSS/미등록 사유 17종이 **조용히 버려지는지** 전수 시험.

GM 2026-08-21: "일단 미등록사유(=LOSS사유) 날라가지만 않게 해줘 제발 부탁이야"

왜 필요한가 — 이 시스템은 값을 못 쓰면 오류를 내지 않고 조용히 건너뛴 뒤 ok:true 를 돌려준다.
  · 방문완료: 시트에 칸이 없어 714건 전부 유실(2026-08-21 발견)
  · LOSS 사유: 화면 17종 vs 시트 드롭다운 11종 불일치로 6종이 거부되던 시기가 있었다(~2026-08-20)
그래서 "저장했다" 는 응답을 믿지 않고, 17종을 실제로 하나씩 넣어 보고 되읽어 대조한다.

안전장치
  · 대상 행의 원래 값을 먼저 읽어 두고, 무슨 일이 있어도 마지막에 되돌린다(finally).
  · 같은 행에 직렬로만 쓴다(병렬 금지 — 순서가 뒤집히면 옛 값이 이긴다).
  · --apply 없이는 대상만 찍고 아무것도 쓰지 않는다.

쓰는 법
  python scripts/cpo_loss_reason_dropcheck.py            # 대상 확인만
  python scripts/cpo_loss_reason_dropcheck.py --apply    # 17종 전수 시험 후 원복
"""
from __future__ import annotations

import os
import re
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cpo_report as C  # noqa: E402

APPLY = "--apply" in sys.argv
URL = C.FUNNEL_EXEC_URL
ASSET = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "3. 웰페리온 가이드", "_assets", "loss_reasons.js",
)


def options() -> list[str]:
    """화면이 실제로 보여 주는 17종 — 정본 파일에서 읽는다(여기 하드코딩 금지)."""
    src = open(ASSET, encoding="utf-8").read()
    m = re.search(r"LOSS_REASON_OPTIONS\s*=\s*\[(.*?)\]", src, re.S)
    if not m:
        raise SystemExit("loss_reasons.js 에서 목록을 못 읽었습니다")
    return re.findall(r"'([^']+)'", m.group(1))


def col(r, *names):
    for n in names:
        if n in r:
            return r[n]
    return ""


def ledger_write(row, value):
    return requests.get(URL, params={
        "action": "member_active_update", "rowIndex": str(col(row, "rowIndex")),
        "col": "미등록사유", "value": value,
        "keyPhone": str(col(row, "휴대폰 번호")), "rowKey": str(col(row, "rowKey") or ""),
    }, timeout=90).json()


def ledger_read(name):
    for r in (C.fetch_active_members("ended") or []):
        if str(col(r, "회원명")).strip() == name:
            return str(col(r, "미등록사유") or "").strip()
    return None


def inquiry_write(row, value):
    return requests.get(URL, params={
        "action": "member_inquiry_update", "rowIndex": str(row.get("rowIndex")),
        "name": row.get("name"), "keyPhone": row.get("phone"),
        "rowKey": str(row.get("rowKey") or ""), "lossReason": value,
    }, timeout=90).json()


def inquiry_read(row_index):
    for r in (C.fetch_member_inquiries() or []):
        if r.get("rowIndex") == row_index:
            return str(r.get("lossReason") or "").strip()
    return None


def sweep(label, opts, write, read, restore_to):
    """17종을 하나씩 넣고 되읽어 대조. 살아남지 못한 값을 돌려준다."""
    dropped, ok_n = [], 0
    try:
        for i, v in enumerate(opts, 1):
            res = write(v)
            time.sleep(1.2)
            got = read()
            good = (got == v)
            ok_n += good
            if not good:
                dropped.append((v, got, res.get("ok"), res.get("error")))
            print(f"   {i:>2}/{len(opts)} {v:<12} {'OK' if good else '✗ 남은값=' + repr(got)}")
    finally:
        write(restore_to)
        time.sleep(1.5)
        back = read()
        print(f"   ↩ 원복 {restore_to!r} → 확인 {back!r} {'✅' if back == restore_to else '❌ 수동 확인 필요'}")
    print(f"  ▶ {label}: 살아남음 {ok_n}/{len(opts)} · 버려진 값 {len(dropped)}개")
    return dropped


def main():
    opts = options()
    print(f"화면 사유 목록 {len(opts)}종: {opts}\n")

    ended = C.fetch_active_members("ended") or []
    lrow = next((r for r in ended if str(col(r, "회원명")).strip() == "김현수1"), None)
    inq = C.fetch_member_inquiries() or []
    irow = next((r for r in inq if r.get("rowIndex") == 440), None)
    if not lrow or not irow:
        raise SystemExit("시험 대상 행을 못 찾았습니다")

    lorig = str(col(lrow, "미등록사유") or "").strip()
    iorig = str(irow.get("lossReason") or "").strip()
    print(f"① 원장 미등록사유 — {col(lrow,'회원명')} row{col(lrow,'rowIndex')} 원래값 {lorig!r}")
    print(f"② 문의 LOSS 사유 — {irow.get('name')} row{irow.get('rowIndex')} 원래값 {iorig!r}")
    if not APPLY:
        print("\n(미적용 — --apply 를 붙이면 17종 전수 시험 후 원래 값으로 되돌립니다)")
        return 0

    print("\n① 원장 미등록사유 전수 시험")
    d1 = sweep("원장", opts, lambda v: ledger_write(lrow, v), lambda: ledger_read("김현수1"), lorig)
    print("\n② 문의 LOSS 사유 전수 시험")
    d2 = sweep("문의", opts, lambda v: inquiry_write(irow, v), lambda: inquiry_read(440), iorig)

    print("\n=== 판정 ===")
    if not d1 and not d2:
        print("✅ 17종 전부 저장되고 살아남는다 — 조용히 버려지는 값 없음")
        return 0
    print("❌ 조용히 버려지는 값이 있다")
    for lab, dd in (("원장", d1), ("문의", d2)):
        for v, got, ok, err in dd:
            print(f"   [{lab}] {v!r} → 남은값 {got!r} · 서버응답 ok={ok} error={err}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
