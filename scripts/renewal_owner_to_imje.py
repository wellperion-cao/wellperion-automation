# -*- coding: utf-8 -*-
"""
8월 만기 재등록 대상(익월 만기자, member_expiry_alert.py 와 동일 판정 기준) 86명의
멤버십 담당자(A열 '담당자')를 전부 '임정은' 으로 정리 — GM 지시 2026-07-20.

⚠️ 범위 엄수: 대상 = fetch_next_month_expiring() 이 반환하는 익월 만기자 풀만(오늘 기준
2026-08, 86명). 유효회원 전체(1,006명)를 건드리지 않는다 — 범위 밖 행 쓰기는 사고.
⚠️ 컬럼 엄수: A열 '담당자'(멤버십 담당) 하나만. 강습 담당 5칸(PT/골프/P.L/스쿼시/수영
담당자)은 절대 건드리지 않는다 — 이 스크립트는 그 컬럼들을 읽지도 쓰지도 않는다.

쓰기 액션 선택 근거: member_owner_save 의 화이트리스트(mosAllowed, Survey.js:4062)는
['PT 담당자','골프 담당자','P.L 담당자','스쿼시 담당자','수영 담당자'] 뿐 — '담당자'(A열)는
포함되지 않는다. 따라서 member_owner_save 는 이 필드에 사용할 수 없다(GM 지시대로 Survey.js
화이트리스트를 임의로 고치지 않음). 대신 member_active_update(Survey.js:3955)를 쓴다 —
_auFindCol() 이 헤더 '담당자' 를 정확일치로 찾아 그 셀만 쓴다(다른 컬럼 침범 없음),
keyPhone 동봉으로 행 검증까지 포함.

절차: (1) 대상 86명 중 이미 '임정은' 이 아닌 행만 추출(불필요 write 스킵) → (2) 백업
JSON 기록(변경 전 분포 포함) → (3) member_active_update 로 각 건 쓰기 → (4) 재조회로
86명 전원 임정은·전체 인구(1,006명) 기준 범위 밖 변화 0 실측 확인.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import requests

from cpo_report import FUNNEL_EXEC_URL, _gas_get, _today_str
from member_expiry_alert import END_KEY, NAME_KEY, OWNER_KEY, fetch_next_month_expiring

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = REPO_ROOT / "status" / "backups"

TARGET_VALUE = "임정은"
LESSON_KEYS = ["PT 담당자", "골프 담당자", "P.L 담당자", "스쿼시 담당자", "수영 담당자"]


def fetch_all_valid() -> list[dict] | None:
    data = _gas_get("member_active_list", {"scope": "valid"})
    if data is None:
        return None
    return data.get("data", [])


def owner_of(row: dict) -> str:
    return str(row.get(OWNER_KEY) or "").strip()


def owner_distribution(rows: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for r in rows:
        k = owner_of(r) or "(빈값)"
        dist[k] = dist.get(k, 0) + 1
    return dist


def lesson_distribution(rows: list[dict]) -> dict[str, dict[str, int]]:
    """강습 담당 5칸 무변경 확인용(특히 P.L=조영은) — 이 스크립트가 절대 건드리지 않는 컬럼."""
    out: dict[str, dict[str, int]] = {}
    for key in LESSON_KEYS:
        dist: dict[str, int] = {}
        for r in rows:
            v = str(r.get(key) or "").strip() or "(빈값)"
            dist[v] = dist.get(v, 0) + 1
        out[key] = dist
    return out


def owner_update(row_index: int, phone: str, value: str) -> dict:
    payload = {"action": "member_active_update", "rowIndex": row_index, "keyPhone": phone, "fields": {OWNER_KEY: value}}
    resp = requests.post(
        FUNNEL_EXEC_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=30,
        allow_redirects=True,
    )
    try:
        return resp.json()
    except Exception:
        return {"ok": False, "error": f"응답 파싱 실패(http {resp.status_code})"}


def write_backup(pool: list[dict], targets: list[dict], before_dist: dict, before_lessons: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = BACKUP_DIR / f"renewal_owner_to_imje_before_{ts}.json"
    payload = {
        "_comment": "GM 지시 8월 만기 재등록 대상(86명) 멤버십 담당자 일괄 '임정은' 정리 — 실행 전 백업(되돌릴 때 사용)",
        "_purpose": f"{OWNER_KEY} 필드 → '{TARGET_VALUE}' 일괄변경(익월 만기 86명 범위만, 강습 담당 5칸 미포함)",
        "_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "_source": "member_active_list?scope=valid (GAS 경유), fetch_next_month_expiring() 동일 판정기준",
        "field": OWNER_KEY,
        "targetValue": TARGET_VALUE,
        "poolTotal": len(pool),
        "writeTargetCount": len(targets),
        "beforeOwnerDistribution_pool86": before_dist,
        "beforeLessonDistribution_pool86_readonly_untouched": before_lessons,
        "records": [
            {
                "rowIndex": t.get("rowIndex"),
                "회원명": t.get(NAME_KEY),
                "휴대폰 번호": t.get("휴대폰 번호"),
                "종료일자": t.get(END_KEY),
                "field": OWNER_KEY,
                "oldValue": owner_of(t),
                "newValue": TARGET_VALUE,
            }
            for t in targets
        ],
    }
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run(apply: bool) -> int:
    today = _today_str()
    fetched = fetch_next_month_expiring(today)
    if fetched is None:
        print("[중단] 유효회원(익월 만기 풀) 조회 실패(GAS 응답 없음)")
        return 1
    next_month, pool = fetched
    print(f"[조회] 익월({next_month}) 만기 풀 = {len(pool)}명")

    all_rows_before = fetch_all_valid()
    if all_rows_before is None:
        print("[중단] 전체 유효회원 조회 실패 — 범위밖 비교 기준을 잡을 수 없음")
        return 1
    print(f"[조회] 전체 유효회원 = {len(all_rows_before)}명")

    pool_row_indices = {r.get("rowIndex") for r in pool}
    outside_before = [r for r in all_rows_before if r.get("rowIndex") not in pool_row_indices]

    before_dist_pool = owner_distribution(pool)
    before_dist_outside = owner_distribution(outside_before)
    before_lessons_pool = lesson_distribution(pool)
    print(f"[변경 전] 86명 풀 담당자 분포: {before_dist_pool}")
    print(f"[변경 전] 범위 밖({len(outside_before)}명) 담당자 분포: {before_dist_outside}")

    targets = [r for r in pool if owner_of(r) != TARGET_VALUE]
    print(f"[대상] '{TARGET_VALUE}' 아닌 행 = {len(targets)}건 (이미 {TARGET_VALUE}인 {len(pool) - len(targets)}건은 스킵)")
    for t in targets:
        print(f"  - {t.get(NAME_KEY)} (rowIndex={t.get('rowIndex')}) {owner_of(t)} -> {TARGET_VALUE}")

    if not apply:
        print("\n[dry-run] --apply 없이는 쓰기 안 함.")
        return 0

    if not targets:
        print("[완료] 변경 대상 0건 — 이미 전원 임정은.")
        return 0

    backup_path = write_backup(pool, targets, before_dist_pool, before_lessons_pool)
    print(f"[백업] {backup_path}")

    failures = []
    for t in targets:
        phone = str(t.get("휴대폰 번호") or "").strip()
        result = owner_update(t.get("rowIndex"), phone, TARGET_VALUE)
        if not result.get("ok"):
            failures.append((t.get(NAME_KEY), result.get("error") or "알 수 없는 실패"))
        else:
            print(f"[저장] {t.get(NAME_KEY)} -> {TARGET_VALUE} 완료")

    if failures:
        print("\n[실패 발생]")
        for name, err in failures:
            print(f"  - {name}: {err}")
        print(f"백업으로 원복 필요 시: {backup_path}")
        return 1

    # 재조회 검증(전체 + 범위밖 비교)
    all_rows_after = fetch_all_valid()
    if all_rows_after is None:
        print("[검증 실패] 재조회 실패 — 수동 확인 필요")
        return 1
    fetched_after = fetch_next_month_expiring(_today_str())
    if fetched_after is None:
        print("[검증 실패] 재조회(풀) 실패 — 수동 확인 필요")
        return 1
    _, pool_after = fetched_after
    after_dist_pool = owner_distribution(pool_after)
    after_lessons_pool = lesson_distribution(pool_after)

    outside_after = [r for r in all_rows_after if r.get("rowIndex") not in pool_row_indices]
    after_dist_outside = owner_distribution(outside_after)

    print(f"\n[검증] 86풀 담당자 분포(변경후): {after_dist_pool}")
    print(f"[검증] 범위 밖({len(outside_after)}명) 담당자 분포(변경후): {after_dist_outside}")
    print(f"[검증] 범위 밖 분포 변화 0 여부: {before_dist_outside == after_dist_outside}")
    print(f"[검증] 강습 담당 5칸 무변경 여부: {before_lessons_pool == after_lessons_pool}")

    ok_pool = after_dist_pool == {TARGET_VALUE: len(pool)}
    ok_outside = before_dist_outside == after_dist_outside
    ok_lessons = before_lessons_pool == after_lessons_pool

    if ok_pool and ok_outside and ok_lessons:
        print("\n[완료] 전량 정상 반영 확인 — 86풀 전원 임정은, 범위밖 무변화, 강습담당 무변화.")
        return 0

    print("\n[불일치] 기대와 다름 — 백업으로 원복 검토 필요.")
    print(f"백업: {backup_path}")
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="재등록 대상(익월 만기 86명) 멤버십 담당자 일괄 '임정은' 정리")
    parser.add_argument("--apply", action="store_true", help="실제 쓰기 수행(기본은 대상 확인만)")
    raise SystemExit(run(apply=parser.parse_args().apply))
