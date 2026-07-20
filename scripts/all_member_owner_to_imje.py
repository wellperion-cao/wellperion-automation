# -*- coding: utf-8 -*-
"""
유효회원 시트 전체(scope=valid, 약 1,006명)의 멤버십 담당자(A열 '담당자')를 전부
'임정은' 으로 정리 — GM 지시 2026-07-20(범위 확대, 8월 만기 86명 완료 후 실행).

⚠️ 순차 실행 필수 — scripts/renewal_owner_to_imje.py(86명 범위) 와 동시에 돌리지 않는다
(같은 시트 중복 쓰기 사고 방지). 86명 범위가 먼저 완료·검증된 뒤에만 이 스크립트를 돌린다.

⚠️ 컬럼 엄수: A열 '담당자'(멤버십 담당) 한 칸만. 강습 담당 5칸(PT/골프/P.L/스쿼시/수영
담당자)은 절대 건드리지 않는다 — 이 스크립트는 그 컬럼들을 읽어 '무변경 증명'에만 쓰고
쓰지는 않는다(특히 P.L=조영은 689명 그대로여야 함).

⚠️ '전체' 지시 반영: 빈칸·'담당자 X' 같은 플레이스홀더 행도 스킵하지 않고 '임정은' 으로
채운다(GM 지시 — 미배정 해소 효과). 이미 정확히 '임정은' 인 행만 스킵(불필요 write 축소
+ 재실행 시 자연 멱등).

쓰기 액션: member_active_update(Survey.js:3955) — member_owner_save 화이트리스트
(mosAllowed)에 '담당자' 가 없어 사용 불가(scripts/renewal_owner_to_imje.py 에서 이미 확인).
_auFindCol() 이 헤더 '담당자' 를 정확일치로 찾아 그 셀만 쓴다. keyPhone 동봉으로 행 검증.

배치 쓰기 액션 존재 여부 확인 결과: Survey.js 전체에 bulk/batch/multi/mass 패턴의 액션
없음(grep 확인) — 개별 POST 를 50행 청크로 나눠 청크 사이 대기(_CHUNK_PAUSE_SEC)를 두고,
각 요청 사이에도 소폭 대기(_ROW_PAUSE_SEC)를 둔다. 진행률은 콘솔 + JSONL 로그
(status/backups/all_member_owner_to_imje_progress_<ts>.jsonl, 1건당 1줄 append)로 남겨
중단 시 어디까지 썼는지 즉시 알 수 있게 한다. 실패 시 그 자리에서 멈추고(계속 진행 안 함)
결과를 보고한다 — 되돌릴지 이어갈지는 GM 판단.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from cpo_report import _gas_get

from renewal_owner_to_imje import (
    LESSON_KEYS,
    OWNER_KEY,
    TARGET_VALUE,
    lesson_distribution,
    owner_distribution,
    owner_of,
    owner_update,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = REPO_ROOT / "status" / "backups"
NAME_KEY = "회원명"

_CHUNK_SIZE = 50
_ROW_PAUSE_SEC = 0.3
_CHUNK_PAUSE_SEC = 2.0


def fetch_all_valid() -> list[dict] | None:
    data = _gas_get("member_active_list", {"scope": "valid"})
    if data is None:
        return None
    return data.get("data", [])


def write_backup(all_rows: list[dict], targets: list[dict], before_dist: dict, before_lessons: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = BACKUP_DIR / f"all_member_owner_to_imje_before_{ts}.json"
    payload = {
        "_comment": "GM 지시 유효회원 전체 멤버십 담당자 일괄 '임정은' 정리 — 실행 전 전체 백업(되돌릴 때 유일한 근거)",
        "_purpose": f"{OWNER_KEY} 필드 → '{TARGET_VALUE}' 전체 일괄변경(강습 담당 5칸 미포함, 이미 임정은인 행 제외)",
        "_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "_source": "member_active_list?scope=valid (GAS 경유) 전량",
        "field": OWNER_KEY,
        "targetValue": TARGET_VALUE,
        "totalValidRows": len(all_rows),
        "writeTargetCount": len(targets),
        "beforeOwnerDistribution_full": before_dist,
        "beforeLessonDistribution_full_readonly_untouched": before_lessons,
        "records": [
            {
                "rowIndex": t.get("rowIndex"),
                "회원명": t.get(NAME_KEY),
                "휴대폰 번호": t.get("휴대폰 번호"),
                "field": OWNER_KEY,
                "oldValue": owner_of(t),
                "newValue": TARGET_VALUE,
            }
            for t in targets
        ],
    }
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    # 백업 저장 성공 확인(재읽기 검증) — GM 지시: "백업 저장 성공을 확인한 뒤에야 쓰기 시작"
    readback = path.read_text(encoding="utf-8")
    if readback != text or len(readback) < 100:
        raise RuntimeError(f"백업 파일 재검증 실패 — 쓰기 중단: {path}")
    return path


def run(apply: bool, chunk_size: int = _CHUNK_SIZE) -> int:
    all_rows = fetch_all_valid()
    if all_rows is None:
        print("[중단] 유효회원 전체 조회 실패(GAS 응답 없음)")
        return 1
    print(f"[조회] 유효회원 전체 = {len(all_rows)}명")

    before_dist = owner_distribution(all_rows)
    before_lessons = lesson_distribution(all_rows)
    print(f"[변경 전] 담당자 분포(전체): {before_dist}")
    for k in LESSON_KEYS:
        print(f"[변경 전] {k} 분포: {before_lessons[k]}")

    targets = [r for r in all_rows if owner_of(r) != TARGET_VALUE]
    print(f"\n[대상] '{TARGET_VALUE}' 아닌 행 = {len(targets)}건 (이미 {TARGET_VALUE}인 {len(all_rows) - len(targets)}건은 스킵)")

    if not apply:
        print("\n[dry-run] --apply 없이는 쓰기 안 함.")
        return 0

    if not targets:
        print("[완료] 변경 대상 0건 — 이미 전원 임정은.")
        return 0

    backup_path = write_backup(all_rows, targets, before_dist, before_lessons)
    print(f"[백업 저장 성공 확인] {backup_path} ({backup_path.stat().st_size}bytes)")

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    progress_path = BACKUP_DIR / f"all_member_owner_to_imje_progress_{ts}.jsonl"
    print(f"[진행률 로그] {progress_path}")

    done = 0
    total = len(targets)
    stopped_early = False
    stop_reason = ""
    with open(progress_path, "a", encoding="utf-8") as plog:
        for chunk_start in range(0, total, chunk_size):
            chunk = targets[chunk_start:chunk_start + chunk_size]
            for t in chunk:
                phone = str(t.get("휴대폰 번호") or "").strip()
                result = owner_update(t.get("rowIndex"), phone, TARGET_VALUE)
                rec = {
                    "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                    "rowIndex": t.get("rowIndex"),
                    "회원명": t.get(NAME_KEY),
                    "oldValue": owner_of(t),
                    "newValue": TARGET_VALUE,
                    "ok": bool(result.get("ok")),
                    "error": None if result.get("ok") else (result.get("error") or "알 수 없는 실패"),
                }
                plog.write(json.dumps(rec, ensure_ascii=False) + "\n")
                plog.flush()
                if not result.get("ok"):
                    stopped_early = True
                    stop_reason = f"rowIndex={t.get('rowIndex')} {t.get(NAME_KEY)}: {rec['error']}"
                    print(f"[실패 — 중단] {stop_reason}")
                    break
                done += 1
                time.sleep(_ROW_PAUSE_SEC)
            if stopped_early:
                break
            print(f"[진행] {min(chunk_start + chunk_size, total)}/{total} 완료")
            time.sleep(_CHUNK_PAUSE_SEC)

    if stopped_early:
        print(f"\n[중단됨] {done}/{total} 건 완료 후 실패로 정지. 부분 적용 상태입니다.")
        print(f"실패 사유: {stop_reason}")
        print(f"진행률 로그: {progress_path}")
        print(f"백업: {backup_path}")
        print("되돌릴지 이어갈지는 GM 판단 대기 — 자동 롤백/재시도 없음.")
        return 1

    print(f"\n[쓰기 완료] {done}/{total} 건 전량 성공.")

    # 재조회 검증
    all_rows_after = fetch_all_valid()
    if all_rows_after is None:
        print("[검증 실패] 재조회 실패 — 수동 확인 필요")
        return 1
    after_dist = owner_distribution(all_rows_after)
    after_lessons = lesson_distribution(all_rows_after)
    print(f"\n[검증] 담당자 분포(변경후, 전체): {after_dist}")
    for k in LESSON_KEYS:
        print(f"[검증] {k} 분포(변경후): {after_lessons[k]}")

    row_count_same = len(all_rows) == len(all_rows_after)
    rowset_same = {r.get("rowIndex") for r in all_rows} == {r.get("rowIndex") for r in all_rows_after}
    lessons_same = before_lessons == after_lessons
    owner_ok = after_dist == {TARGET_VALUE: len(all_rows_after)}

    print(f"\n[검증] 총 행수 동일: {row_count_same} ({len(all_rows)} -> {len(all_rows_after)})")
    print(f"[검증] rowIndex 집합 동일(행 추가/삭제 0): {rowset_same}")
    print(f"[검증] 강습 담당 5칸 완전 무변경: {lessons_same}")
    print(f"[검증] 담당자 = 임정은 단독: {owner_ok}")

    if row_count_same and rowset_same and lessons_same and owner_ok:
        print("\n[완료] 전량 정상 반영 확인.")
        return 0

    print("\n[불일치] 기대와 다름 — 백업/진행률 로그로 원인 확인 필요.")
    print(f"백업: {backup_path}")
    print(f"진행률 로그: {progress_path}")
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="유효회원 전체 멤버십 담당자 일괄 '임정은' 정리")
    parser.add_argument("--apply", action="store_true", help="실제 쓰기 수행(기본은 대상 확인만)")
    parser.add_argument("--chunk-size", type=int, default=_CHUNK_SIZE)
    args = parser.parse_args()
    raise SystemExit(run(apply=args.apply, chunk_size=args.chunk_size))
