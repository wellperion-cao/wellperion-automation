# -*- coding: utf-8 -*-
"""review_queue.json(179건) → publish_ledger 적재 (배 925).

정본 = status/briefs/CMO-유입경로-발행원장-정의서-20260903.md §3(표B)·§4(이사 규칙).
기본 = --dry-run(적재 안 함, 매핑 통계 + 정의서 빈도표 대조만 출력). 실제 적재 = --apply
(server/common/db.py 로 서버 PostgreSQL publish_ledger 에 upsert — 서버 접근 없으면 사유만 출력).

실행: C:/Python314/python.exe scripts/publish_ledger_import.py            (드라이런)
      C:/Python314/python.exe scripts/publish_ledger_import.py --apply    (실제 적재)
      C:/Python314/python.exe scripts/publish_ledger_import.py --selftest (매핑 로직 자체점검)
"""
import argparse
import json
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_PATH = os.path.join(REPO_ROOT, "3. 웰페리온 가이드", "cmo", "review", "review_queue.json")

# 정의서 §4 — channel/account 변환 매핑. IG 는 account 로, 나머지는 channel 문자열 그대로 갈린다.
IG_ACCOUNT_MAP = {
    "namuk.wellperion": "ig_personal",
    "wellperion": "ig_official",
    "wellperion 비즈(cao)": "ig_official",
}
SIMPLE_CHANNEL_MAP = {
    "네이버 블로그": "naver_blog",
    "네이버 카페 (동부이촌동)": "naver_cafe",
    "당근채널": "danggn",
    "카카오 채널": "kakao",
}
# 정의서 §3 — 1회성 값이라 원장에 안 넣고 note 에 한 줄만 남기고 버리는 칸.
DISCARD_KEYS = ("digest_title", "digest_intro", "url", "review_artifact", "writer")
# 정의서 §3 — 핵심 스키마 밖 부속 메타(제작·검수 파이프라인용). 버리지 않고 meta 한 칸에 통째로.
META_KEYS = (
    "folder", "preview", "slides", "caption", "location", "collaborators", "mentions",
    "image_glob", "image_dir", "body_file", "body", "menuid", "scheduled_date",
    "publish_at", "card_sent_at", "qc_flags", "info_lines",
)
# 정의서 §3 표B 실측 빈도(오른쪽 열) — 드라이런에서 이 숫자와 실제 파일을 대조한다.
EXPECTED_FREQ = {
    "id": 179, "title": 179, "channel": 179, "account": 177, "post_url": 177,
    "status": 179, "published_at": 162, "note": 173,
    "digest_title": 1, "digest_intro": 1, "url": 1, "review_artifact": 1, "writer": 1,
}


IG_CHANNEL_MAP = {
    "인스타그램 (namuk.wellperion)": "ig_personal",
    "인스타그램 (wellperion 공식)": "ig_official",
    "인스타그램 (wellperion)": "ig_official",
}


def map_channel_code(channel, account):
    """정의서 §4 변환 규칙. 매핑 성공 시 channel_code, 실패 시 None(호출부가 unknown 폴백).
    IG 는 channel 문자열 자체에 계정이 박혀 있어(예: "인스타그램 (namuk.wellperion)") 이걸 먼저 보고,
    account 칸이 따로 있으면(179건 중 177건) 그걸로 보강 확인한다 — account 가 없는 2건도 이걸로 풀린다."""
    channel = (channel or "").strip()
    account = (account or "").strip()
    if channel in IG_CHANNEL_MAP:
        return IG_CHANNEL_MAP[channel]
    if channel.startswith("인스타그램"):
        return IG_ACCOUNT_MAP.get(account)
    return SIMPLE_CHANNEL_MAP.get(channel)


def build_row(item):
    """review_queue.json 1건 → publish_ledger 1행. (row, 변환성공여부, 버린칸목록) 반환."""
    note = (item.get("note") or "").strip()
    discarded = [k for k in DISCARD_KEYS if item.get(k)]
    if discarded:
        note = (note + " | [이관 폐기] " + ", ".join("%s=%s" % (k, item[k]) for k in discarded)).strip(" |")
    mapped = map_channel_code(item.get("channel"), item.get("account"))
    row = {
        "post_id": item.get("id"),
        "title": item.get("title"),
        "channel_code": mapped or "unknown",
        "format": "unknown",  # 정의서 §4 — 과거 179건엔 표기 없어 지어내지 않음
        "external_url": item.get("post_url"),
        "status": item.get("status"),
        "published_at": item.get("published_at"),
        "note": note,
        "meta": {k: item[k] for k in META_KEYS if k in item},
    }
    return row, mapped is not None, discarded


def _selftest():
    r, ok, disc = build_row({
        "id": "X-1", "title": "t", "channel": "인스타그램 (namuk.wellperion)", "account": "namuk.wellperion",
        "post_url": "u", "status": "발행완료", "published_at": "2026-01-01", "note": "n",
        "folder": "f", "writer": "누군가",
    })
    assert ok and r["channel_code"] == "ig_personal", r
    assert r["meta"] == {"folder": "f"}, r
    assert disc == ["writer"] and "[이관 폐기]" in r["note"], r

    r2, ok2, _ = build_row({"id": "X-2", "channel": "당근채널", "account": "wellperion"})
    assert ok2 and r2["channel_code"] == "danggn", r2

    r3, ok3, _ = build_row({"id": "X-3", "channel": "모르는채널"})
    assert not ok3 and r3["channel_code"] == "unknown", r3
    print("[selftest] OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제 서버 DB publish_ledger 에 upsert(기본=드라이런)")
    ap.add_argument("--selftest", action="store_true", help="매핑 로직만 자체점검(파일·DB 안 건드림)")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return 0

    with open(QUEUE_PATH, encoding="utf-8") as f:
        items = json.load(f)

    freq_actual = {k: 0 for k in EXPECTED_FREQ}
    rows, n_converted, unresolved, n_discarded_items = [], 0, [], 0
    for item in items:
        for k in EXPECTED_FREQ:
            if item.get(k):
                freq_actual[k] += 1
        row, resolved, discarded = build_row(item)
        rows.append(row)
        n_converted += 1 if resolved else 0
        if not resolved:
            unresolved.append(item.get("id"))
        n_discarded_items += 1 if discarded else 0

    print("[dry-run] 총 %d건 · 1:1 매핑 %d건 · 변환(channel_code) 성공 %d건 · 미해결(unknown 폴백) %d건 · 버림칸 존재 %d건"
          % (len(items), len(items), n_converted, len(unresolved), n_discarded_items))
    if unresolved:
        print("  미해결 id: %s" % ", ".join(unresolved))

    mismatches = []
    for k, expected in EXPECTED_FREQ.items():
        actual = freq_actual[k]
        mark = "OK" if actual == expected else "MISMATCH"
        if mark == "MISMATCH":
            mismatches.append("%s(정의서 %d/실측 %d)" % (k, expected, actual))
        print("  필드 %-14s 정의서=%3d 실측=%3d %s" % (k, expected, actual, mark))
    print("[정의서 대비] %s" % ("전부 일치" if not mismatches else "불일치: " + ", ".join(mismatches)))

    if not args.apply:
        print("[dry-run 종료] --apply 없이 실제 적재는 하지 않음")
        return 0

    sys.path.insert(0, os.path.join(REPO_ROOT, "server", "common"))
    try:
        import db  # noqa: E402
    except Exception as e:
        print("[적재 불가] server/common/db import 실패: %s" % e)
        return 0
    try:
        conn = db.connect()
    except Exception as e:
        print("[적재 불가] DB 연결 실패(서버 접근 없음으로 보임): %s: %s" % (type(e).__name__, str(e)[:160]))
        return 0
    db.init_schema(conn)
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))
    with conn:
        for row in rows:
            conn.execute(
                "INSERT INTO publish_ledger"
                " (tenant_id,post_id,title,channel_code,format,external_url,status,published_at,note,meta,synced_at)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (tenant_id,post_id) DO UPDATE SET"
                "  title=EXCLUDED.title, channel_code=EXCLUDED.channel_code, format=EXCLUDED.format,"
                "  external_url=EXCLUDED.external_url, status=EXCLUDED.status, published_at=EXCLUDED.published_at,"
                "  note=EXCLUDED.note, meta=EXCLUDED.meta, synced_at=EXCLUDED.synced_at",
                (db.TENANT, row["post_id"], row["title"], row["channel_code"], row["format"],
                 row["external_url"], row["status"], row["published_at"], row["note"],
                 json.dumps(row["meta"], ensure_ascii=False), now))
    conn.close()
    print("[적재 완료] %d건 → publish_ledger" % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
