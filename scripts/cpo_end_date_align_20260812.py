# -*- coding: utf-8 -*-
"""
종료회원 「종료 일자」를 「LOSS 일자」에 맞춰 통일하는 1회성 마이그레이션 (2026-08-12 GM 지시).

배경:
  회원 시트는 매일 「잔여일」 오름차순으로 자동 정렬된다(Survey.js member_active_sort_by_remaining_).
  잔여일은 종료일자로 계산되므로, LOSS 일자와 종료 일자가 다른 회원은 시트에서 LOSS 순서가 어긋난다.
  GM 지시(2026-08-12): "LOSS일자를 기준으로 종료일자를 맞춰줘" + 범위는 "나" = 두 날짜가 다른 전건.

실측(2026-08-12 · 종료회원 699명):
  종료일자 == LOSS일자 178명 / 다름 521명
    - LOSS가 종료일보다 늦음 511명 (만료 다음 날 자동 도장 — 하루 차이가 대부분)
    - LOSS가 종료일보다 이름  10명 (중도 해지 추정)
  ★그중 4명(한경만·이종훈1·한솔솔·김대순1)은 종료일이 아직 오지 않았는데 LOSS 가 찍힌 건이다.
    맞추면 계약이 107~202일 남은 실고객의 종료일이 과거로 당겨진다. GM 이 이 사실을 보고 "나"(전건)를
    선택했으므로 그대로 진행하되, 아래 백업으로 한 명 단위 되돌리기가 가능하게 남긴다.

되돌리기:
  python scripts\\cpo_end_date_align_20260812.py --restore                  # 백업 전건 원복
  python scripts\\cpo_end_date_align_20260812.py --restore --name 한경만    # 특정 회원만 원복

사용:
  python scripts\\cpo_end_date_align_20260812.py --dry-run   # 대상만 출력(쓰기 없음)
  python scripts\\cpo_end_date_align_20260812.py             # 실제 정렬 맞춤
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

FUNNEL_EXEC_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)
BACKUP = REPO / "status" / "backups" / "member_end_date_20260812.json"

END_COL = "종료일자"      # 실헤더 '종료\n일자' — GAS 가 공백 제거 후 정확일치로 찾는다
END_KEY = "종료\n일자"
LOSS_KEY = "LOSS\n일자"


def _d(v: str) -> str:
    return str(v or "").strip()[:10]


def _write(row_index: int, row_key: str, phone: str, value: str, dry: bool) -> tuple[bool, str]:
    if dry:
        return True, "DRY"
    params = {
        "action": "member_active_update",
        "rowIndex": str(row_index),
        "col": END_COL,
        "value": value,
        "keyPhone": phone,
        "rowKey": row_key,
    }
    try:
        r = requests.get(FUNNEL_EXEC_URL, params=params, timeout=40, allow_redirects=True)
        r.encoding = "utf-8"
        data = r.json()
        return bool(data.get("ok")), str(data.get("error") or "")
    except Exception as e:  # 네트워크·파싱 실패는 실패로 센다(성공으로 뭉개지 않는다)
        return False, str(e)


def collect() -> list[dict]:
    import cpo_report as c

    rows = c.fetch_active_members("ended") or []
    out = []
    for r in rows:
        end, loss = _d(r.get(END_KEY)), _d(r.get(LOSS_KEY))
        if not end or not loss or end == loss:
            continue
        out.append({
            "rowIndex": r.get("rowIndex"),
            "rowKey": r.get("rowKey") or "",
            "name": r.get("회원명"),
            "phone": r.get("휴대폰 번호") or "",
            "end_before": end,
            "loss": loss,
        })
    return out


def run_align(dry: bool) -> int:
    targets = collect()
    print(f"대상 {len(targets)}건 {'[DRY-RUN]' if dry else ''}")
    if not dry:
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        # ★덮어쓰기 금지(2026-08-12 시포 · 실사고). 처음엔 매 실행마다 같은 파일에 썼는데, 실패 82건을
        #   재시도하려고 두 번째로 돌리는 순간 그 시점 대상(17건)이 원본 521건 백업을 통째로 덮었다.
        #   되돌릴 값을 잃는 것은 마이그레이션 자체보다 위험하다 — 재시도 회차는 별도 파일로 남긴다.
        path = BACKUP
        n = 1
        while path.exists():
            n += 1
            path = BACKUP.with_name(f"{BACKUP.stem}_retry{n}{BACKUP.suffix}")
        path.write_text(json.dumps(targets, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"백업 저장 → {path}")
    ok = fail = 0
    fails = []
    for i, t in enumerate(targets, 1):
        good, err = _write(t["rowIndex"], t["rowKey"], t["phone"], t["loss"], dry)
        if good:
            ok += 1
        else:
            fail += 1
            fails.append((t["name"], t["rowIndex"], err))
        if i % 50 == 0 or i == len(targets):
            print(f"  {i}/{len(targets)} · 성공 {ok} 실패 {fail}")
        if not dry:
            time.sleep(0.4)
    print(f"완료 — 성공 {ok} / 실패 {fail} / 전체 {len(targets)}")
    for f in fails[:20]:
        print("  실패:", f)
    return fail


def run_restore(name_filter: str | None) -> int:
    if not BACKUP.exists():
        print(f"백업 없음 — {BACKUP}")
        return 1
    rows = json.loads(BACKUP.read_text(encoding="utf-8"))
    if name_filter:
        rows = [r for r in rows if str(r.get("name") or "").strip() == name_filter.strip()]
    print(f"원복 대상 {len(rows)}건")
    ok = fail = 0
    for r in rows:
        good, err = _write(r["rowIndex"], r["rowKey"], r["phone"], r["end_before"], False)
        print(f"  {r['name']} → {r['end_before']} {'OK' if good else 'FAIL ' + err}")
        ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
        time.sleep(0.4)
    print(f"원복 완료 — 성공 {ok} / 실패 {fail}")
    return fail


def _selftest() -> None:
    assert _d("2026-08-06T00:00:00") == "2026-08-06"
    assert _d(None) == ""
    assert _d("  2026-08-06  ") == "2026-08-06"
    print("[OK] _d selftest 통과")


def main() -> int:
    p = argparse.ArgumentParser(description="종료일자를 LOSS일자에 맞춤 (2026-08-12 GM 지시)")
    p.add_argument("--dry-run", action="store_true", help="쓰기 없이 대상만 출력")
    p.add_argument("--restore", action="store_true", help="백업으로 원복")
    p.add_argument("--name", help="--restore 와 함께 — 특정 회원만 원복")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    if a.selftest:
        _selftest()
        return 0
    if a.restore:
        return run_restore(a.name)
    return run_align(a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
