#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
precommit_queue_guard.py — 커밋 전 status 배열 JSON '활성 항목 소멸' 차단 가드

배경 ①(2026-06-15 AI CTO):
  cmo 세션이 스테일 33척 _queue 기반으로 커밋(ecfa0f0f)해 최신 59척을 덮어써
  26척이 유실. → 배열형 status JSON(_queue.json·review_queue.json)의 급감을 차단.

배경 ②(2026-07-21 · 이번 정밀화 이유):
  11:25 커밋 fe9be3f9d 가 「AI하루」 10편을 review_queue.json 에 추가했는데,
  4분 뒤 11:29 무관한 커밋 b96cac0ea 가 스테일 사본으로 덮어써 10건 전량 소실.
  그때 가드는 **AND 조건**이라 침묵했다:
      dropped(10) >= 8  ✓   BUT   ratio(10/160=6.3%) >= 15%  ✗  → 통과
  즉 파일이 커질수록 방어가 약해지는 구조였다(비율 기반의 근본 결함).

새 규칙 (2026-07-23):
  판정 대상 = **활성(비종결) 항목만**. 항목을 id 로 식별해 집합 비교한다.
    - HEAD 에서 활성이던 항목이 staged 에서 **근거 없이 사라지면 1건이라도 차단.**
      → 비율 무관. 파일이 100건이든 10,000건이든 방어력이 안 떨어진다.
    - 다음은 '근거 있음'으로 보고 통과(정상 운영 흐름):
        (a) 종결 상태로 전환 — 같은 id 가 staged 에 DONE·발행완료·폐기 등으로 남아있음
        (b) 아카이브 이관 — 같은 id 가 짝 아카이브 파일(_queue_archive.json /
            review_queue_archive.json, staged 우선·없으면 HEAD)에 들어가 있음
            → 매일 05:56 queue_archive_sweep(DONE 200건+ 이동)이 오탐 차단되지 않는다.
  종결 상태값은 실제 파일 실측 기준(status/_queue.json·_queue_archive.json ·
  review_queue.json·review_queue_archive.json + archive 스크립트 정의)으로 정의.

감시 대상: _queue.json · review_queue.json (경로 무관 basename 매칭 — 발행루트 미러 포함)

안전 규칙 (fail-open):
  - 신규 파일(HEAD에 없음)            → 통과
  - 전체 삭제(staged 에서 제거됨)      → 통과(의도적)
  - JSON 파싱 실패 / top-level 비배열  → 통과(이 가드 범위 아님)
  - 가드 자체 오류                     → 통과(exit 0)
  - 의도적 활성 삭제 우회              → git commit --no-verify

  ※ exit 1 = 차단(활성 항목 소멸). exit 0 = 통과(정상/에러 fail-open).
"""

import json
import subprocess
import sys

# ── 종결(terminal) 상태값 — 실제 파일 실측 기준 ───────────────────────────
# status/_queue.json  : DONE·PENDING·IN_PROGRESS·STANDBY·BLOCKED
# status/_queue_archive.json : DONE·폐기·완료  (queue_archive_sweep 이관 대상)
# review_queue.json   : 발행완료·검수대기·폐기
# review_queue_archive.json  : 발행완료·폐기
# archive_review_queue.py TERMINAL_STATUSES : 발행완료·폐기·반려·rejected
# queue_archive_sweep.py  TERMINAL_STATUSES : DONE·완료·폐기
TERMINAL_STATUSES = {
    # _queue 계열
    "DONE", "완료", "폐기", "CANCELLED", "취소",
    # review_queue 계열
    "발행완료", "반려", "rejected", "REJECTED",
}

# 항목 식별자 후보 (앞에서부터 먼저 있는 것을 키로 쓴다)
ID_KEYS = ("task_id", "id", "ship_no")

# 파일명(basename) 매칭 — 한글 경로 안전.
WATCH_BASENAMES = ("_queue.json", "review_queue.json")

# 감시 파일 → 짝 아카이브 파일명(같은 디렉토리). 이관은 소멸이 아니다.
ARCHIVE_SIBLING = {
    "_queue.json": "_queue_archive.json",
    "review_queue.json": "review_queue_archive.json",
}


def run(args):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout


def staged_paths():
    """staged 파일 경로(bytes) 목록 — 이름변경은 새 경로만. -z 로 한글 안전."""
    rc, out = run([
        "git", "diff", "--cached", "--name-status", "-z", "--diff-filter=ACMRT",
    ])
    if rc != 0:
        return []
    tokens = out.split(b"\x00")
    paths = []
    i = 0
    while i < len(tokens):
        status = tokens[i].decode("utf-8", "replace") if tokens[i] else ""
        if not status:
            i += 1
            continue
        if status[0] == "R":
            if i + 2 < len(tokens):
                paths.append(tokens[i + 2])
            i += 3
        else:
            if i + 1 < len(tokens):
                paths.append(tokens[i + 1])
            i += 2
    return paths


def blob(ref_prefix, path_bytes):
    rc, out = run(["git", "cat-file", "-p", ref_prefix + path_bytes])
    if rc != 0:
        return None
    return out


def parse_array(blob_bytes):
    """JSON top-level 배열. 배열 아니면 None(가드 범위 밖)."""
    if not blob_bytes:
        return None
    data = json.loads(blob_bytes.decode("utf-8", "replace"))
    return data if isinstance(data, list) else None


def item_id(item):
    """항목 식별자. 없으면 None(→ 개수 기반 폴백 대상)."""
    if not isinstance(item, dict):
        return None
    for k in ID_KEYS:
        v = item.get(k)
        if v not in (None, ""):
            return "%s=%s" % (k, v)
    return None


def is_terminal(item):
    """종결(입항·발행완료·폐기 등) 여부. terminal:true 플래그도 인정."""
    if not isinstance(item, dict):
        return False
    if item.get("terminal") is True:
        return True
    return str(item.get("status") or "") in TERMINAL_STATUSES


def index_items(items):
    """id → item. id 없는 항목 수도 함께 반환."""
    by_id = {}
    anon = 0
    for it in items or []:
        k = item_id(it)
        if k is None:
            anon += 1
            continue
        by_id[k] = it
    return by_id, anon


def archive_ids(path_bytes, base, staged_set):
    """짝 아카이브 파일의 id 집합. staged 되어 있으면 staged 판, 아니면 HEAD 판."""
    sib_name = ARCHIVE_SIBLING.get(base)
    if not sib_name:
        return set()
    disp = path_bytes.decode("utf-8", "replace").replace("\\", "/")
    parent = disp.rsplit("/", 1)[0] if "/" in disp else ""
    sib_disp = (parent + "/" + sib_name) if parent else sib_name
    sib_bytes = sib_disp.encode("utf-8")
    for ref in ((b":", b"HEAD:") if sib_bytes in staged_set else (b"HEAD:",)):
        try:
            arr = parse_array(blob(ref, sib_bytes))
        except Exception:
            arr = None
        if arr is not None:
            ids, _ = index_items(arr)
            return set(ids)
    return set()


def main():
    paths = staged_paths()
    staged_set = set(paths)
    violations = []

    for path_bytes in paths:
        try:
            disp = path_bytes.decode("utf-8", "replace")
            base = disp.replace("\\", "/").rsplit("/", 1)[-1]
            if base not in WATCH_BASENAMES:
                continue

            head = blob(b"HEAD:", path_bytes)
            if head is None:
                continue  # 신규 파일 → 통과
            new = blob(b":", path_bytes)
            if new is None:
                continue  # 전체 삭제 → 통과

            head_items = parse_array(head)
            new_items = parse_array(new)
            if head_items is None or new_items is None:
                continue  # 비배열/파싱불가 → 통과

            head_by_id, head_anon = index_items(head_items)
            new_by_id, new_anon = index_items(new_items)

            # HEAD 에서 '활성'이던 항목만 판정 대상.
            head_active = {k: v for k, v in head_by_id.items() if not is_terminal(v)}
            missing = [k for k in head_active if k not in new_by_id]

            if missing:
                # 아카이브로 이관된 것은 소멸이 아니다(05:56 스윕 통과 경로).
                arch = archive_ids(path_bytes, base, staged_set)
                missing = [k for k in missing if k not in arch]

            # id 없는 활성 항목이 통째로 줄어든 경우(식별 불가) — 개수로만 방어.
            anon_lost = 0
            if head_anon > new_anon:
                head_anon_active = sum(
                    1 for it in head_items if item_id(it) is None and not is_terminal(it)
                )
                new_anon_active = sum(
                    1 for it in new_items if item_id(it) is None and not is_terminal(it)
                )
                anon_lost = max(0, head_anon_active - new_anon_active)

            if missing or anon_lost:
                violations.append((disp, len(head_items), len(new_items),
                                   missing, anon_lost, head_active))
        except Exception:
            continue  # 개별 파일 실패 → 그 파일만 건너뜀(fail-open)

    if violations:
        sys.stderr.write(
            "\n"
            "============================================================\n"
            "[queue-guard] 커밋 차단 — 활성(비종결) 항목이 사라졌습니다\n"
            "------------------------------------------------------------\n"
        )
        for disp, hn, nn, missing, anon_lost, head_active in violations:
            sys.stderr.write(
                "  파일: %s\n"
                "        전체 %d개 → %d개 / 사라진 활성 항목 %d건\n"
                % (disp, hn, nn, len(missing) + anon_lost)
            )
            for k in missing[:30]:
                it = head_active.get(k) or {}
                title = str(it.get("title") or it.get("note") or "")[:40]
                status = str(it.get("status") or "?")
                sys.stderr.write(
                    "        - %s  [%s]  %s\n" % (k, status, title)
                )
            if len(missing) > 30:
                sys.stderr.write("        - … 외 %d건\n" % (len(missing) - 30))
            if anon_lost:
                sys.stderr.write(
                    "        - (식별자 없는 활성 항목 %d건 감소)\n" % anon_lost
                )
        sys.stderr.write(
            "------------------------------------------------------------\n"
            "  종결(DONE·발행완료·폐기…) 전환이나 아카이브 이관은 통과합니다.\n"
            "  위 항목들은 '흔적 없이' 사라졌습니다 — 옛 사본으로 최신을 덮어쓴 것일 수\n"
            "  있습니다(2026-07-21 AI하루 10편 소실 / 2026-06-15 _queue 26척 유실).\n"
            "  먼저 최신을 합쳤는지 확인하세요. 되찾기:\n"
            "      python scripts/review_queue_recover.py --missing\n"
            "  정말 의도한 삭제라면 우회:  git commit --no-verify\n"
            "============================================================\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(
            "[queue-guard][WARN] 가드 내부 오류 — 통과(fail-open): %r\n" % (exc,)
        )
        sys.exit(0)
