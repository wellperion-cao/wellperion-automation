# -*- coding: utf-8 -*-
"""회원등기부 이행 — 0단계 백업 · 1단계 번호 부여 (2026-08-26 GM 승인 · 배801)

설계 정본 = status/briefs/CPO-2026-08-26-회원도메인-이행설계.md

  python scripts/cpo_member_registry_migrate.py --backup    # 0단계: 7탭 전체 덤프(로컬 전용)
  python scripts/cpo_member_registry_migrate.py --assign --dry-run   # 1단계 미리보기
  python scripts/cpo_member_registry_migrate.py --assign             # 1단계 실제 부여

백업은 status/_private/ 에 쓴다 — 그 폴더는 .gitignore 라 회원 실명·전화가 저장소로 안 나간다.
번호 부여는 GAS 액션 member_registry_assign 이 시트에서 직접 한다(여기서는 호출·검증만).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
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
PRIVATE = REPO / "status" / "_private"
SURVEY_OUT = REPO / "status" / "member_registry_progress.json"

FUNNEL_EXEC_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)

# (라벨, action, params) — 설계 §4 이행 순서 그대로. 회원 4벌이 1순위다.
SOURCES = [
    ("유효회원", "member_active_list", {"scope": "valid"}),
    ("종료회원", "member_active_list", {"scope": "ended"}),
    ("법인회원", "member_active_list", {"scope": "corp"}),
    ("LOSS보관", "member_active_list", {"scope": "archive"}),
    ("멤버십문의", "member_inquiry_list", {"scope": "all"}),
    ("강습문의_성인", "lesson_inquiry_list", {"type": "성인강습", "scope": "all"}),
    ("강습문의_유소년", "lesson_inquiry_list", {"type": "유소년강습", "scope": "all"}),
]
MEMBER_LEDGERS = ("유효회원", "종료회원", "법인회원", "LOSS보관")


def _get(action: str, params: dict, timeout: int = 240):
    p = dict(params)
    p["action"] = action
    p["nc"] = "1"          # 캐시 우회 — 백업은 언제나 지금 시트 값이어야 한다
    t = time.time()
    r = requests.get(FUNNEL_EXEC_URL, params=p, timeout=timeout)
    r.encoding = "utf-8"
    try:
        d = r.json()
    except Exception:
        raise RuntimeError(f"{action} 응답이 JSON 이 아니다(HTTP {r.status_code})")
    if not d.get("ok"):
        raise RuntimeError(f"{action} ok=false: {str(d.get('error'))[:120]}")
    return d.get("data") or [], time.time() - t


def _phone(row: dict) -> str:
    v = row.get("휴대폰 번호") or row.get("휴대폰") or row.get("phone") or ""
    return str(v).replace("-", "").replace(" ", "").strip()


def _name(row: dict) -> str:
    return str(row.get("회원명") or row.get("name") or "").strip()


def backup() -> int:
    """0단계 — 7탭 전체를 로컬에 덤프하고 줄 수를 기록한다."""
    PRIVATE.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    counts, total = {}, 0
    for label, action, params in SOURCES:
        rows, el = _get(action, params)
        counts[label] = len(rows)
        total += len(rows)
        out = PRIVATE / f"backup_{stamp}_{label}.json"
        out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        print(f"[백업] {label:12s} {len(rows):>6,}줄 · {el:.1f}초 → {out.name}")
    manifest = {"stamp": stamp, "counts": counts, "total": total}
    (PRIVATE / f"backup_{stamp}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n합계 {total:,}줄 (설계 기준선 11,153 — 그 사이 실무진이 넣고 지운 만큼 달라진다)")
    print(f"백업 위치 {PRIVATE}  ※ .gitignore 라 저장소로 나가지 않는다")
    return 0


def collect_member_rows() -> dict:
    """회원 4벌을 **가장 최근 백업 파일에서** 읽는다.

    라이브를 다시 부르지 않는 이유: 0단계 백업이 방금 받아 온 그 값이 기준선이고,
    여기서 또 조회하면 그 사이 실무진 편집으로 기준선이 흔들린다. 조회 실패 위험도 0이 된다.
    백업이 없으면 그때만 라이브에서 받는다.
    """
    stamps = sorted({p.name.split("_")[1] + "_" + p.name.split("_")[2]
                     for p in PRIVATE.glob("backup_*_manifest.json")})
    if stamps:
        stamp = stamps[-1]
        out = {}
        for label in MEMBER_LEDGERS:
            f = PRIVATE / f"backup_{stamp}_{label}.json"
            out[label] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
            print(f"[백업읽기] {label:8s} {len(out[label]):>5,}줄  ({stamp})")
        return out

    print("[알림] 백업이 없어 라이브에서 받는다 — 먼저 --backup 을 돌리는 것이 안전하다")
    out = {}
    for label, action, params in SOURCES:
        if label not in MEMBER_LEDGERS:
            continue
        rows, el = _get(action, params)
        out[label] = rows
        print(f"[조회] {label:8s} {len(rows):>5,}줄 · {el:.1f}초")
    return out


def build_person_index(ledgers: dict) -> tuple[list, list]:
    """회원 4벌을 사람 단위로 묶는다.

    묶는 키 = (전화, 이름). 전화만으로 묶으면 가족이 한 사람이 되고, 이름만으로 묶으면
    동명이인이 한 사람이 된다 — 설계 §4 '잘못 합치는 것보다 안 합치는 게 안전하다' 원칙.
    이름이 다르면 각자 번호를 받는다. 같은 사람일 가능성은 '후보'로만 표시한다.
    """
    people = collections.OrderedDict()   # (phone, name) -> {rows:[...]}
    for label in MEMBER_LEDGERS:
        for r in ledgers.get(label, []):
            ph, nm = _phone(r), _name(r)
            if not nm:
                continue
            key = (ph, nm)
            people.setdefault(key, {"phone": ph, "name": nm, "rows": []})
            people[key]["rows"].append({"원장": label, "rowIndex": r.get("rowIndex"),
                                        "등록일": str(r.get("등록\n일자") or ""),
                                        "분류": str(r.get("등록 분류") or "")})

    # 같은 전화·다른 이름 = 병합 후보(자동 병합 금지 · 표시만)
    by_phone = collections.defaultdict(list)
    for (ph, nm) in people:
        if ph and ph != "0":
            by_phone[ph].append(nm)
    candidates = []
    for ph, names in by_phone.items():
        if len(names) < 2:
            continue
        kind = _candidate_kind(names)
        candidates.append({"전화뒤4": ph[-4:], "이름들": sorted(names), "유형": kind})
    return list(people.values()), candidates


def _candidate_kind(names: list) -> str:
    """같은 전화에 붙은 이름들이 어떤 종류인지 가른다 — 사람이 볼 때 판정이 빨라진다."""
    base = [n.rstrip("0123456789") for n in names]
    if len(set(base)) == 1 and len(set(names)) > 1:
        return "같은 이름 + 숫자 접미"          # 김혜경 / 김혜경4
    if any("/" in n or "," in n for n in names):
        return "한 칸에 두 사람"                 # 방태오(5세)/방현오(7세)
    if len(names) == 2:
        a, b = sorted(names, key=len)
        if len(a) == len(b) and sum(1 for x, y in zip(a, b) if x != y) == 1:
            return "한 글자 차이(오타 의심)"      # 박초은 / 박초응
    return "다른 사람(가족 공유번호 추정)"


def assign(dry: bool) -> int:
    ledgers = collect_member_rows()
    people, candidates = build_person_index(ledgers)

    # 두 원장 이상에 걸친 사람 = 즉시 판정 대상
    dup = [p for p in people if len({r["원장"] for r in p["rows"]}) > 1]
    # 같은 원장 안에서 같은 (전화,이름) 이 두 줄 이상 = 중복행
    same = [p for p in people if len(p["rows"]) > len({r["원장"] for r in p["rows"]})]

    print(f"\n사람 {len(people):,}명 · 원장 줄 {sum(len(p['rows']) for p in people):,}")
    print(f"두 원장에 걸친 사람 {len(dup)}명 · 같은 원장 중복줄 {len(same)}건")
    print(f"같은 전화 다른 이름(병합 후보·자동병합 안 함) {len(candidates)}건")
    kinds = collections.Counter(c["유형"] for c in candidates)
    for k, v in kinds.most_common():
        print(f"   · {k}: {v}건")

    payload = []
    for i, p in enumerate(people, start=1):
        p["회원번호"] = f"M{i:05d}"
        payload.append({"no": p["회원번호"], "phone": p["phone"], "name": p["name"],
                        "rows": p["rows"]})

    progress = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "단계": "1단계 번호 부여" + ("(미리보기)" if dry else ""),
        "사람수": len(people),
        "원장줄수": sum(len(p["rows"]) for p in people),
        "두원장에걸친사람": len(dup),
        "같은원장중복줄": len(same),
        "병합후보": len(candidates),
        "병합후보_유형별": dict(kinds),
    }
    SURVEY_OUT.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")

    # 사람 판정이 필요한 것만 따로 — 실명이 들어가므로 로컬 전용 폴더에 쓴다
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "registry_judgement_needed.json").write_text(
        json.dumps({"두원장에걸친사람": dup, "같은원장중복줄": same,
                    "병합후보": candidates}, ensure_ascii=False, indent=2), encoding="utf-8")
    (PRIVATE / "registry_numbers.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    print(f"\n번호 부여(안) {len(payload):,}명 → {PRIVATE / 'registry_numbers.json'}")
    print(f"판정 필요 목록 → {PRIVATE / 'registry_judgement_needed.json'}")
    print(f"진척 요약(저장소 공개·PII 없음) → {SURVEY_OUT}")
    if dry:
        print("\n★ 미리보기다. 시트에는 아무것도 쓰지 않았다.")
    return 0


def demo() -> None:
    """자체 점검 — 병합 후보 분류가 실제 사례를 제대로 가르는지만 본다(외부 호출 없음)."""
    assert _candidate_kind(["김혜경", "김혜경4"]) == "같은 이름 + 숫자 접미"
    assert _candidate_kind(["방태오(5세)/방현오(7세)", "조우인"]) == "한 칸에 두 사람"
    assert _candidate_kind(["박초은", "박초응"]) == "한 글자 차이(오타 의심)"
    assert _candidate_kind(["김준수", "최은정"]) == "다른 사람(가족 공유번호 추정)"
    assert _phone({"휴대폰 번호": "010-3837-5107"}) == "01038375107"
    print("demo OK")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup", action="store_true", help="0단계 — 7탭 전체 로컬 덤프")
    ap.add_argument("--assign", action="store_true", help="1단계 — 사람 단위로 묶어 번호 부여(안)")
    ap.add_argument("--dry-run", action="store_true", help="시트 쓰기 없이 미리보기")
    ap.add_argument("--demo", action="store_true", help="자체 점검")
    a = ap.parse_args()
    if a.demo:
        demo()
        return 0
    if a.backup:
        return backup()
    if a.assign:
        return assign(a.dry_run)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
