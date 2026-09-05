# -*- coding: utf-8 -*-
"""쓰기 이중기록 대조 — 서버 원장 ↔ 시트 미러 (배 960 · 2026-09-04 시토).

이전 계획(docs/superpowers/specs/2026-09-03-gas-to-server-migration-plan.md)의 전환 규칙:
  "이중기록 시작일부터 3일 연속 대조 무결(날짜별 서버 행수 = 시트 행수 · 본문 키 대조 불일치 0) → 서버 원본"
이 스크립트는 그 3일을 **세기만** 한다 — 전환은 사람이 한다.

무엇을 대조하나 (폼별 · 날짜별)
  서버 원장  intake_log(inquiry·instructor·sunday·reception) · write_log(write · 로그인 화면 쓰기 전체)
  시트 쪽    ① 미러 표에 그 행이 실제로 들어왔나(강한 증거) ② 미러가 없으면 GAS 접수증(gas_status)
  본문 키    전화 뒤 4자리. 종합접수처 미러는 이름·전화를 가려서(`차**` `010-****-5691`) 싣기 때문에
             이름은 열쇠로 못 쓴다 — 두 미러에 공통으로 남는 건 뒤 4자리뿐이다.

미러가 받는 범위 (문의 폼)
  WP 문의 폼 category 중 시트로 라우팅되는 건 membership·adult·youth 셋뿐이다(wp_inquiry_form.html 머리말 ·
  여름특강·공간렌트·비즈니스는 GAS 후속 배선 대기). 나머지 category 는 미러에 없는 게 정상이라 GAS 접수증으로 센다.

무결 판정
  mismatch = 그 날 서버에 남은 행 중 시트 도달을 증명 못 한 건수. 0 이면 그 날은 ok.
  streak_ok_days = 어제부터 거꾸로, **행이 있었던 날만** 세어 연속 ok 인 날수. 접수 0건인 날은 무결의 증거가
  아니므로 세지 않는다(건너뛴다 · 끊지도 않는다). 3 이 되면 사람이 서버 원본 전환을 판단한다.

실행: python3 /srv/erp/api/reconcile_dual_write.py   (cron 06:10 KST · /etc/cron.d/erp-reconcile)
결과: /srv/erp/status/dual_write_reconcile.json  ·  읽기 API GET /api/intake/reconcile
자체점검: python3 reconcile_dual_write.py --selftest   (DB·네트워크 없음 — 판정 로직만)
"""
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WINDOW_DAYS = 7                       # 3일 연속을 보려면 여유 포함 일주일이면 넉넉하다
STATUS_DIR = os.environ.get("ERP_STATUS_DIR", "/srv/erp/status")
OUT_FILE = os.path.join(STATUS_DIR, "dual_write_reconcile.json")

# 폼 → (원장 표, 시트 도달로 치는 gas_status, 미러 표). 미러가 None 이면 GAS 접수증만으로 센다.
FORMS = {
    "inquiry":    {"ledger": "intake_log", "ok": ("200",), "mirror": "inquiries"},
    "instructor": {"ledger": "intake_log", "ok": ("200",), "mirror": None},
    "sunday":     {"ledger": "intake_log", "ok": ("200",), "mirror": None},
    "reception":  {"ledger": "intake_log", "ok": ("200",), "mirror": "reception_items"},
    "write":      {"ledger": "write_log",  "ok": ("ok",),  "mirror": None},
}
# 문의 폼 category → 미러(inquiries) 유형. 여기 없는 category 는 시트 라우팅 자체가 없다.
CAT_MIRROR = {"membership": "멤버십", "adult": "성인강습", "youth": "유소년강습"}


def kst_now():
    return datetime.now(timezone(timedelta(hours=9)))


def phone4(*vals):
    """전화 뒤 4자리. 가린 번호(010-****-5691)에서도 뽑힌다. 못 뽑으면 ''."""
    for v in vals:
        digits = re.sub(r"\D", "", str(v or ""))
        if len(digits) >= 4:
            return digits[-4:]
    return ""


def row_key(payload):
    return phone4(payload.get("phone"), payload.get("contact"), payload.get("tel"))


def reconcile(form, rows, mirror_by_date):
    """rows = [(타임스탬프문자열, payload dict, gas_status)] · mirror_by_date = {날짜: Counter(전화뒤4)}.
    반환 {날짜: {server, sheet, mismatch, ok, via}} 와 못 맞춘 행 표본."""
    spec = FORMS[form]
    left = {d: Counter(c) for d, c in (mirror_by_date or {}).items()}   # 소비하며 줄인다(같은 4자리 2건도 2건으로 센다)
    days, unmatched = {}, []
    for ts, payload, status in rows:
        day = str(ts)[:10]
        d = days.setdefault(day, {"server": 0, "sheet": 0, "mismatch": 0, "ok": True, "via": {"mirror": 0, "gas": 0}})
        d["server"] += 1
        mirrored = spec["mirror"] and (form != "inquiry" or payload.get("category") in CAT_MIRROR)
        hit, via = False, "gas"
        if mirrored:
            via = "mirror"
            key = row_key(payload)
            bucket = left.get(day)
            if key and bucket and bucket[key] > 0:
                bucket[key] -= 1
                hit = True
        else:
            hit = status in spec["ok"]
        if hit:
            d["sheet"] += 1
            d["via"][via] += 1
        else:
            d["mismatch"] += 1
            d["ok"] = False
            if len(unmatched) < 5:
                unmatched.append({"date": day, "at": ts, "via": via, "gas_status": status, "key": row_key(payload)})
    return days, unmatched


def streak_ok_days(forms, today):
    """어제부터 거꾸로 — 행이 있었던 날만 세어 연속 ok 인 날수. 오늘은 아직 쌓이는 중이라 뺀다."""
    n = 0
    for back in range(1, WINDOW_DAYS + 1):
        day = (today - timedelta(days=back)).isoformat()
        rows = [f.get(day) for f in forms.values() if f.get(day)]
        if not rows:
            continue                                  # 접수 0건인 날 = 증거 없음 → 세지도, 끊지도 않는다
        if not all(r["ok"] for r in rows):
            break
        n += 1
    return n


# ── DB 에서 원장·미러를 읽어 오는 자리 (판정 로직은 위, 여기는 조회만) ────────────────────
def _load(conn, db, since):
    # gas_status='test' 행은 뺀다(2026-09-05) — 격리된 테스트 페이로드는 GAS 로 안 보내 미러에도 없다 —
    # 대조에 넣으면 매번 "시트 도달 못 증명"으로 잡혀 3일 무결 스트릭을 헛되이 끊는다.
    intake = {}
    for r in conn.execute("SELECT form, received_at, payload, gas_status FROM intake_log"
                          " WHERE tenant_id=%s AND received_at >= %s AND gas_status != 'test'",
                          (db.TENANT, since)).fetchall():
        intake.setdefault(r["form"], []).append((r["received_at"], r["payload"] or {}, r["gas_status"]))
    writes = [(r["at"], r["payload"] or {}, r["gas_status"]) for r in
              conn.execute("SELECT at, payload, gas_status FROM write_log WHERE tenant_id=%s AND at >= %s"
                          " AND gas_status != 'test'", (db.TENANT, since)).fetchall()]
    inq, rec = {}, {}
    for r in conn.execute("SELECT timestamp, phone FROM inquiries WHERE tenant_id=%s AND type = ANY(%s)"
                          " AND timestamp >= %s", (db.TENANT, list(CAT_MIRROR.values()), since)).fetchall():
        inq.setdefault(str(r["timestamp"])[:10], Counter())[phone4(r["phone"])] += 1
    for r in conn.execute("SELECT created_at, data FROM reception_items WHERE tenant_id=%s AND created_at >= %s",
                          (db.TENANT, since)).fetchall():
        d = json.loads(r["data"]) if isinstance(r["data"], str) else (r["data"] or {})
        rec.setdefault(str(r["created_at"])[:10], Counter())[phone4(d.get("contact"), d.get("phone"))] += 1
    return intake, writes, {"inquiries": inq, "reception_items": rec}


def main():
    from common import db  # noqa: PLC0415 — selftest 는 DB 없이 돌아야 한다
    now = kst_now()
    since = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    conn = db.connect(readonly=True)
    with conn:
        intake, writes, mirrors = _load(conn, db, since)
    conn.close()
    out_forms, unmatched = {}, []
    for form, spec in FORMS.items():
        rows = writes if form == "write" else intake.get(form, [])
        days, bad = reconcile(form, rows, mirrors.get(spec["mirror"] or ""))
        out_forms[form] = days
        unmatched += bad
    result = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "window_days": WINDOW_DAYS,
        "forms": out_forms,
        "streak_ok_days": streak_ok_days(out_forms, now.date()),
        "streak_note": "행이 있었던 날만 센다 — 접수 0건인 날은 무결의 증거가 아니라 건너뛴다. 3 이 되면 사람이 서버 원본 전환을 판단한다.",
        "unmatched_samples": unmatched[:20],
    }
    os.makedirs(STATUS_DIR, exist_ok=True)
    tmp = OUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_FILE)
    today = now.date().isoformat()
    print("대조 %s · streak=%d · %s" % (result["generated_at"], result["streak_ok_days"], " ".join(
        "%s %d/%d" % (k, v.get(today, {}).get("sheet", 0), v.get(today, {}).get("server", 0)) for k, v in out_forms.items())))
    return 0


def selftest():
    # 미러가 받는 category = 시트 도달을 미러 행으로 증명 · 나머지 = GAS 접수증
    rows = [
        ("2026-09-01T10:00:00", {"category": "membership", "phone": "010-1111-2222"}, "200"),   # 미러 적중
        ("2026-09-01T11:00:00", {"category": "adult", "phone": "010-3333-4444"}, "200"),        # 미러에 없음 → 불일치
        ("2026-09-01T12:00:00", {"category": "rental", "phone": "010-5555-6666"}, "200"),       # 미러 대상 아님 → 접수증 ok
        ("2026-09-02T09:00:00", {"category": "membership", "phone": "010-7777-8888"}, "200"),
    ]
    mirror = {"2026-09-01": Counter({"2222": 1}), "2026-09-02": Counter({"8888": 1})}
    days, bad = reconcile("inquiry", rows, mirror)
    assert days["2026-09-01"] == {"server": 3, "sheet": 2, "mismatch": 1, "ok": False,
                                  "via": {"mirror": 1, "gas": 1}}, days["2026-09-01"]
    assert days["2026-09-02"]["ok"] and days["2026-09-02"]["via"] == {"mirror": 1, "gas": 0}, days["2026-09-02"]
    assert len(bad) == 1 and bad[0]["key"] == "4444" and bad[0]["via"] == "mirror", bad

    # 같은 뒤 4자리 2건이면 미러에도 2건 있어야 둘 다 맞는다(하나만 있으면 1건 불일치)
    dup = [("2026-09-01T10:00:00", {"category": "adult", "phone": "010-0000-9999"}, "200")] * 2
    d2, _ = reconcile("inquiry", dup, {"2026-09-01": Counter({"9999": 1})})
    assert d2["2026-09-01"]["mismatch"] == 1, d2

    # 미러 없는 폼 = GAS 접수증만 — 200 아니면 불일치
    d3, bad3 = reconcile("instructor", [("2026-09-01T10:00:00", {}, "error:URLError")], None)
    assert d3["2026-09-01"] == {"server": 1, "sheet": 0, "mismatch": 1, "ok": False, "via": {"mirror": 0, "gas": 0}}, d3
    d4, _ = reconcile("write", [("2026-09-01 10:00:00", {"action": "member_owner_save"}, "ok")], None)
    assert d4["2026-09-01"]["ok"] and d4["2026-09-01"]["via"]["gas"] == 1, d4

    # 가린 번호(010-****-5691)에서도 뒤 4자리가 뽑힌다 — 종합접수처 미러가 이 모양이다
    assert phone4("010-****-5691") == "5691" and phone4("", None, "0104736") == "4736" and phone4("abc") == ""

    # streak — 어제부터 거꾸로, 행 없는 날은 건너뛰고 ok 아닌 날에서 끊는다
    ok, ng = {"server": 1, "ok": True}, {"server": 1, "ok": False}
    today = datetime(2026, 9, 10).date()
    f = {"inquiry": {"2026-09-09": ok, "2026-09-08": ok, "2026-09-06": ok, "2026-09-05": ng}}
    assert streak_ok_days(f, today) == 3, streak_ok_days(f, today)      # 09-07 은 행 0 → 건너뜀
    assert streak_ok_days({"inquiry": {"2026-09-09": ng}}, today) == 0
    assert streak_ok_days({"inquiry": {}}, today) == 0                  # 무입력만으로는 무결이 안 쌓인다
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
