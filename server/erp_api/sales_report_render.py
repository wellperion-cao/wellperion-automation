# -*- coding: utf-8 -*-
"""매출보고서 서버 판 렌더 (읽기 전용 · 배1061 · 시토 · 2026-09-05 · 시포 22칸 정의 짝).

원칙 = 기존 경로(시트 → GAS → 09:00 텔레그램 · 09:30 카톡 3방) 무접촉. 이 모듈은 이미 5분마다
sync_sales.py 가 떠 둔 deptrep/dump 시트 미러(H2:S21)를 그대로 읽어 22칸 대부분은 그 값 그대로
쓰고, 회원 수 5칸(N2~N6)만 members_report.py(회원 미러 직접 계산 · 같은 서버·같은 DB)로 바꿔치기
한다. 정의·검산 표 = status/briefs/CPO-2026-09-05-매출보고서-22칸-정의.md 정본.

22칸 = 총매출·회원권·옵션·팀별강습 8줄(11칸, I 금일값) + 회원현황 5칸(N2~N6) + 신규/재등록/환불/
로스자 6칸(N7~N12) = 22. 회원현황 5칸만 서버 독립 계산이라 대조 대상이고, 나머지 17칸은 서버 판도
시트 미러를 그대로 쓰므로(1단계) 항상 일치 — 브로제이 결제 데이터가 들어오면 그 칸들도 하나씩
독립 계산으로 바뀐다(정의서 "브로제이 뒤" 열).

자체점검: python3 sales_report_render.py --selftest (네트워크·DB 없음 — 순수 파싱·대조 로직만)
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ERP_API_DIR = HERE.parent
REPO_ROOT = ERP_API_DIR.parents[1]                       # server/erp_api → server → repo root
FONT_DIR = REPO_ROOT / "3. 웰페리온 가이드" / "_assets" / "profile"

sys.path.insert(0, str(ERP_API_DIR))
from sync_sales import db, key_of, load_env  # noqa: E402
import members_report  # noqa: E402

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


def compute_overrides():
    """회원현황 5칸의 서버 독립 계산 — members_report.py(회원 미러 직접 계산)와 정확히 같은 함수를 부른다.
    공식(정의서 §검산): 총회원=유효+법인 · 정회원=유효−중단기−대기 · 중단기/법인/대기는 그대로."""
    a = members_report.member_active_summary()
    t = members_report.cpo_today_stats()
    mid, wait, corp = a["typeCounts"].get("중단기", 0), a["waitingCount"], t["memberCorp"]
    total = a["validTotal"] + corp
    regular = a["validTotal"] - mid - wait
    return {"N2": total, "N3": regular, "N4": mid, "N5": corp, "N6": wait, "_today_loss": t["todayLoss"]}


def build_report():
    """시트 미러 + 회원현황 서버 override → 최종 22칸 + 대조 결과. 미러가 없으면 None."""
    data, synced = fetch_mirror()
    if not data:
        return None
    cells = dict(data.get("cells") or {})
    overrides = compute_overrides()
    final = dict(cells)
    for k in ("N2", "N3", "N4", "N5", "N6"):
        final[k] = "%d명" % overrides[k]
    matched, total, mismatches = compare(cells, final)
    return {"cells": cells, "final": final, "synced_at": synced, "overrides": overrides,
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
    d.text((pad, y), "서버 판(병행) · 시트 미러 %s" % (report["synced_at"] or ""), font=small_f, fill=(150, 150, 150))
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
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 2)
