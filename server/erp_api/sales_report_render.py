# -*- coding: utf-8 -*-
"""매출보고서 서버 판 렌더 (읽기 전용 · 배1061 · 시토 · 2026-09-05 · 시포 22칸 정의 짝).

원칙 = 기존 경로(시트 → GAS → 09:00 텔레그램 · 09:30 카톡 3방) 무접촉. 이 모듈은 이미 5분마다
sync_sales.py 가 떠 둔 deptrep/dump 시트 미러(H2:S21)를 그대로 읽어 22칸 대부분은 그 값 그대로
쓰고, 회원 수 5칸(N2~N6)만 members 평면 컬럼(reg_date/end_date/loss_date/kind/reg_class · 같은
서버·같은 DB)으로 기준일 시점 재계산해 바꿔치기한다. 정의·검산 표 =
status/briefs/CPO-2026-09-05-매출보고서-22칸-정의.md 정본.

22칸 = 총매출·회원권·옵션·팀별강습 8줄(11칸, I 금일값) + 회원현황 5칸(N2~N6) + 신규/재등록/환불/
로스자 6칸(N7~N12) = 22. 회원현황 5칸만 서버 독립 계산이라 대조 대상이고, 나머지 17칸은 서버 판도
시트 미러를 그대로 쓰므로(1단계) 항상 일치 — 브로제이 결제 데이터가 들어오면 그 칸들도 하나씩
독립 계산으로 바뀐다(정의서 "브로제이 뒤" 열).

기준일 규칙(정의서 §기준일 · 2026-09-05 확정) — 인원 5칸의 기준일 = 보고 날짜(어제, KST).
대상 = members(valid+ended 합침) 중 등록일자<=기준일 AND 종료일>=기준일 AND (LOSS일자 빈칸
또는 >기준일). 회원구분(kind)으로 중단기·법인 분류, 대기=등록분류(reg_class) '대기'. '지금'
스냅샷이 아니라 '기준일 시점'이라 그 사이 종료·등록으로 scope 가 바뀌어도 흔들리지 않는다.

자체점검: python3 sales_report_render.py --selftest (네트워크·DB 없음 — 순수 파싱·대조·기준일 로직만)
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
HERE = Path(__file__).resolve()
ERP_API_DIR = HERE.parent
# 로컬 repo 클론(server/erp_api/이 파일)이면 parents[1]=repo root. 서버 배포본(/srv/erp/api/이 파일 ·
# scp 로 이 폴더 하나만 옮겨 server/ 트리 자체가 없다)이면 폰트는 항상 켜져 있는 /srv/erp/repo(sparse-
# checkout에 "3. 웰페리온 가이드"/ 포함됨)에서 찾는다.
_DEPLOYED_REPO = Path("/srv/erp/repo")
REPO_ROOT = _DEPLOYED_REPO if _DEPLOYED_REPO.is_dir() else ERP_API_DIR.parents[1]
FONT_DIR = REPO_ROOT / "3. 웰페리온 가이드" / "_assets" / "profile"

sys.path.insert(0, str(ERP_API_DIR))
from sync_sales import db, key_of, load_env  # noqa: E402

SOURCE = "server-panel"

# (셀, 라벨) — 정의서 표 그대로. TEAM_ROWS 는 (시트행, 라벨) — I<행>=금일, J<행>=누적.
TEAM_ROWS = [(8, "수영팀"), (9, "P.T팀"), (10, "골프팀"), (11, "스쿼시팀"),
             (12, "체조팀"), (13, "P.L팀"), (14, "뮤지컬팀"), (15, "GXE(파트너팀)")]
MEMBER_ROWS = [("N2", "총 회원수"), ("N3", "정회원 수"), ("N4", "중단기 회원 수"),
               ("N5", "법인 회원 수"), ("N6", "대기 회원 수")]                          # 서버 독립 계산(대조 대상)
OTHER_ROWS = [("N7", "신규 등록 매출"), ("N8", "신규등록자"), ("N9", "재등록 매출"),
              ("N10", "재등록자"), ("N11", "환불 매출"), ("N12", "로스자")]              # 시트 미러 그대로
TOTAL_CELLS = 3 + len(TEAM_ROWS) + len(MEMBER_ROWS) + len(OTHER_ROWS)                    # = 22


def _strip_emoji(s):
    return re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", s or "").strip()


def _num(s):
    """'1,027명' → 1027 · '  - ' → 0 · None → 0 (사람이 손으로 채운 셀이라 폭넓게 받는다)."""
    if s is None:
        return 0
    m = re.sub(r"[^\d-]", "", str(s))
    return int(m) if m not in ("", "-") else 0


def compare(mirror_cells, final_cells):
    """MEMBER_ROWS 5칸만 실제 대조(서버 독립 계산) — 나머지 17칸은 서버 판=시트 미러라 항상 일치.
    반환: (matched, total, mismatches=["라벨(시트값→서버값)", ...])."""
    mismatches = []
    for k, label in MEMBER_ROWS:
        mv, sv = _num(mirror_cells.get(k)), _num(final_cells.get(k))
        if mv != sv:
            mismatches.append("%s(%d→%d)" % (label, mv, sv))
    return TOTAL_CELLS - len(mismatches), TOTAL_CELLS, mismatches


def fetch_mirror():
    """sync_sales.py 가 5분마다 채우는 deptrep/dump(보고탭 H2:S21 · 파라미터 없음) 거울 1행.
    없으면 (None, None) — 지어내지 않는다."""
    load_env()
    conn = db.connect(readonly=True)
    try:
        r = conn.execute("SELECT data, synced_at FROM sales_cache WHERE tenant_id=%s AND gas='deptrep'"
                         " AND action='dump' AND params=%s", (db.TENANT, key_of({}))).fetchone()
    finally:
        conn.close()
    if not r:
        return None, None
    return json.loads(r["data"]), r["synced_at"]


def _row_active_asof(reg, end, loss, ref_date):
    """정의서 §기준일 규칙 — 등록일자<=기준일 AND 종료일>=기준일 AND (LOSS일자 빈칸 또는 >기준일)."""
    reg, end, loss = (reg or "")[:10], (end or "")[:10], (loss or "")[:10]
    return bool(reg) and reg <= ref_date and bool(end) and end >= ref_date and (not loss or loss > ref_date)


def _classify(rows, ref_date):
    """rows = [(kind, reg_class, reg_date, end_date, loss_date), ...] members 평면 컬럼(scope=valid+ended 풀).
    반환 = (총회원, 중단기, 대기) — 법인은 별도 풀(scope=corp · 실측: kind 가 법인/단체 두 갈래라 kind 로
    안 가르고 scope 전체를 그대로 센다 · _corp_count 참고)."""
    total = mid = wait = 0
    for kind, reg_class, reg, end, loss in rows:
        if not _row_active_asof(reg, end, loss, ref_date):
            continue
        total += 1
        if kind == "중단기":
            mid += 1
        if reg_class == "대기":
            wait += 1
    return total, mid, wait


def _corp_count(rows, ref_date):
    """법인 회원 수 = scope='corp' 전체(법인·단체 kind 안 가림 — 실측 2026-09-05 그대로) 중 기준일 필터 통과."""
    return sum(1 for reg, end, loss in rows if _row_active_asof(reg, end, loss, ref_date))


def compute_overrides(ref_date):
    """회원현황 5칸의 서버 독립 계산 — members 평면 컬럼을 기준일로 직접 조회한다(정의서 §기준일 규칙).
    member_active_summary 류의 '지금' 스냅샷은 쓰지 않는다 — scope(valid/ended)가 그 사이 바뀌어도 안 흔들린다.
    총회원=일반 풀(valid+ended)+법인 풀(corp) 합산 — 기존 member_active_summary/cpo_today_stats 구조 그대로,
    카운트 기준만 '지금'에서 '기준일'로 바꿨다."""
    load_env()
    conn = db.connect(readonly=True)
    try:
        general = conn.execute(
            "SELECT kind, reg_class, reg_date, end_date, loss_date FROM members"
            " WHERE tenant_id=%s AND scope IN ('valid','ended')", (db.TENANT,)).fetchall()
        corp = conn.execute(
            "SELECT reg_date, end_date, loss_date FROM members"
            " WHERE tenant_id=%s AND scope='corp'", (db.TENANT,)).fetchall()
    finally:
        conn.close()
    total, mid, wait = _classify(
        [(r["kind"], r["reg_class"], r["reg_date"], r["end_date"], r["loss_date"]) for r in general], ref_date)
    corp_n = _corp_count([(r["reg_date"], r["end_date"], r["loss_date"]) for r in corp], ref_date)
    return {"N2": total + corp_n, "N3": total - mid - wait, "N4": mid, "N5": corp_n, "N6": wait}


def build_report(ref_date=None):
    """시트 미러 + 회원현황 서버 override(기준일=어제 KST 기본) → 최종 22칸 + 대조 결과. 미러가 없으면 None."""
    if ref_date is None:
        ref_date = (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")
    data, synced = fetch_mirror()
    if not data:
        return None
    cells = dict(data.get("cells") or {})
    overrides = compute_overrides(ref_date)
    final = dict(cells)
    for k in ("N2", "N3", "N4", "N5", "N6"):
        final[k] = "%s명" % format(overrides[k], ",")
    matched, total, mismatches = compare(cells, final)
    return {"cells": cells, "final": final, "synced_at": synced, "overrides": overrides, "ref_date": ref_date,
            "matched": matched, "total": total, "mismatches": mismatches,
            "report_title": _strip_emoji(cells.get("H2", "")) or "매출 및 운영사항 보고"}


# ── PNG 렌더 (Pillow — 서버에 playwright/chromium 없어 표 직접 그림 · 기존 대형 의존성 추가 없음) ──

def render_png(report, out_path):
    from PIL import Image, ImageDraw, ImageFont

    def font(name, size):
        return ImageFont.truetype(str(FONT_DIR / name), size)

    cells = report["final"]
    title_f, head_f, body_f, small_f = (font("Pretendard-Bold.otf", 26), font("Pretendard-SemiBold.otf", 16),
                                        font("Pretendard-Medium.otf", 15), font("Pretendard-Medium.otf", 13))
    sales_rows = [("총 매출 합계", cells.get("I4", ""), cells.get("J4", "")),
                  ("회원권 매출", cells.get("I6", ""), cells.get("J6", "")),
                  ("옵션 매출", cells.get("I7", ""), cells.get("J7", ""))]
    sales_rows += [(name, cells.get("I%d" % r, ""), cells.get("J%d" % r, "")) for r, name in TEAM_ROWS]
    detail_rows = [(label, cells.get(k, "")) for k, label in MEMBER_ROWS + OTHER_ROWS]

    W, pad, row_h = 900, 24, 30
    H = pad * 2 + 44 + row_h * (len(sales_rows) + 2) + 30 + row_h * (len(detail_rows) + 1) + 60
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y = pad
    d.text((pad, y), report["report_title"] + " (서버 판)", font=title_f, fill=(20, 20, 20))
    y += 44
    d.text((pad, y), "구분", font=head_f, fill=(90, 90, 90))
    d.text((pad + 440, y), "금일", font=head_f, fill=(90, 90, 90))
    d.text((pad + 660, y), "누적", font=head_f, fill=(90, 90, 90))
    y += row_h
    d.line((pad, y, W - pad, y), fill=(210, 210, 210))
    for label, v1, v2 in sales_rows:
        y += row_h
        d.text((pad, y), label, font=body_f, fill=(30, 30, 30))
        d.text((pad + 440, y), str(v1).strip(), font=body_f, fill=(30, 30, 30))
        d.text((pad + 660, y), str(v2).strip(), font=body_f, fill=(30, 30, 30))
    y += row_h + 10
    d.line((pad, y, W - pad, y), fill=(210, 210, 210))
    y += 20
    d.text((pad, y), "회원 현황 · 등록/이탈", font=head_f, fill=(90, 90, 90))
    for label, v in detail_rows:
        y += row_h
        d.text((pad, y), label.split("\n")[0], font=body_f, fill=(30, 30, 30))
        d.text((pad + 440, y), str(v).split("\n")[0].strip(), font=body_f, fill=(30, 30, 30))
    y += row_h + 16
    d.text((pad, y), "서버 판(병행) · 기준일 %s · 시트 미러 %s" % (report["ref_date"], report["synced_at"] or ""),
           font=small_f, fill=(150, 150, 150))
    img = img.crop((0, 0, W, min(H, y + 40)))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return str(out_path)


# ── 자체점검 (순수 파싱·대조 로직 — DB·네트워크 없음) ──────────────────────────

def selftest():
    assert _num("1,027명") == 1027 and _num("  - ") == 0 and _num(None) == 0 and _num("0명") == 0
    assert _strip_emoji("📅 26년 9월 4일 보고") == "26년 9월 4일 보고"
    mirror = {"N2": "1,027명", "N3": "988명", "N4": "3명", "N5": "31명", "N6": "5명"}
    same = dict(mirror)
    matched, total, mm = compare(mirror, same)
    assert (matched, total, mm) == (22, 22, []), (matched, total, mm)
    drifted = dict(mirror, N4="2명")                    # 9/5 실측처럼 중단기만 어긋난 경우
    matched, total, mm = compare(mirror, drifted)
    assert matched == 21 and mm == ["중단기 회원 수(3→2)"], (matched, mm)

    # 기준일 규칙 — 일반 풀 rows = (kind, reg_class, reg_date, end_date, loss_date)
    ref = "2026-09-04"
    rows = [
        ("멤버십", "", "2026-01-01", "2099-12-31", ""),            # 유효 · 정회원
        ("중단기", "", "2026-08-01", "2026-12-31", ""),            # 중단기
        ("멤버십", "대기", "2026-01-01", "2099-12-31", ""),         # 대기
        ("멤버십", "대기", "2026-09-10", "2099-12-31", ""),         # 등록일자가 기준일 뒤 → 대상 제외
        ("멤버십", "", "2025-01-01", "2026-09-04", "2026-09-04"),  # LOSS 일자=기준일(경계) → 제외
        ("멤버십", "", "2025-01-01", "2026-09-05", "2026-09-05"),  # LOSS 일자>기준일 → 포함
        ("멤버십", "", "2025-01-01", "2026-08-01", ""),            # 종료일<기준일 → 제외
    ]
    total, mid, wait = _classify(rows, ref)
    assert (total, mid, wait) == (4, 1, 1), (total, mid, wait)

    # 법인 풀(scope=corp) — kind 는 안 가리고 필터만 통과하면 센다(실측: 법인/단체 두 kind 섞여 있음)
    corp_rows = [
        ("2020-01-01", "2099-12-31", ""),           # 포함
        ("2020-01-01", "2026-07-21", "2026-07-21"),  # LOSS<=기준일 → 제외
    ]
    assert _corp_count(corp_rows, ref) == 1
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 2)
