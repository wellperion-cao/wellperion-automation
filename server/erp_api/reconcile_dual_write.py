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
    # 접수(reception)는 이 대조에서 뺐다 (2026-09-09 시토·시우). 배984(GM 지시 2026-09-05)로 접수는
    # 서버 원장에 직접 적고 시트에는 신규분을 안 넘긴다 — 시트 도달을 증거로 삼는 이 대조가 그 영역에서는
    # 영원히 '도달 못 증명'만 낸다. 못 재는 것을 계속 재는 척하면 계측기가 매일 거짓 신호를 준다(오늘
    # 그 신호가 「접수 0건」·「표본 부족」 두 번의 오판을 만들었다). 대신 시우가 15분 점검에 서버 원장
    # 기준 계측을 붙였다 — 통로 살아있나(OPTIONS+POST) · 접수가 실제로 들어오나(원장 최신 접수일).
    # ▸되살릴 때 = 시트가 다시 신규 접수를 받게 되면 이 줄을 되돌린다.
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


NOT_APPLICABLE_STATUSES = ("sheet-missing",)   # 원천이 이미 서버로 넘어간 표(INC-056 이후 접수) — 대조 실패로 안 센다


def reconcile_by_action(rows, ok_statuses=("ok",)):
    """write_log 액션 하나(예: save=점검저장 · reg_update=접수)만의 날짜별 판정. 미러 없이 gas_status 만 본다.
    sheet-missing 행은 날짜 버킷을 안 건드리고 na 로만 센다 — '대조 대상 아님'이라 행 0 인 날과 같게
    streak_ok_days 에서 건너뛴다(폼(action)별 분리 · 시우 실측 2026-09-07)."""
    days, na = {}, 0
    for ts, _payload, status in rows:
        if status in NOT_APPLICABLE_STATUSES:
            na += 1
            continue
        day = str(ts)[:10]
        d = days.setdefault(day, {"server": 0, "sheet": 0, "mismatch": 0, "ok": True})
        d["server"] += 1
        if status in ok_statuses:
            d["sheet"] += 1
        else:
            d["mismatch"] += 1
            d["ok"] = False
    return days, na


RARE_MIN_ROWS = 3     # 거래가 드문 갈래는 '최근 N건 연속 무결'로 대신 잰다
RARE_MAX_DAYS = 3     # 대조 창에서 행이 있던 날이 이보다 적으면 '거래가 드문 갈래'로 본다


def recent_ok_rows(days, today):
    """가장 최근 날부터 거꾸로, ok 인 날이 이어지는 동안 쌓인 서버 행 수. 오늘은 아직 쌓이는 중이라 뺀다."""
    cut = today.isoformat()
    total = 0
    for day in sorted((d for d in days if d < cut), reverse=True):
        if not days[day]["ok"]:
            break
        total += days[day].get("server", 0)
    return total


def qualification(days, today):
    """전환해도 되는가 — (연속일수, 무엇으로 통과했나, 통과여부).

    왜 규칙이 둘인가 (2026-09-09 시토 · GM 지시 「막히는 것을 뚫어라」):
    종전 규칙은 '3일 연속 무결' 하나뿐이었다. 그런데 그 3일은 **행이 있었던 날만** 센다.
    강사 접수·일요일 접수·회원 보류처럼 한 달에 몇 건인 기능은 사흘치 거래가 영영 안 쌓여
    이 규칙으로는 **원리상 절대 전환되지 않는다**(실측 2026-09-09: 그 부류 5갈래 전부 streak=0,
    대조한 날 0일). 거래가 없다는 것과 품질이 나쁘다는 것은 다른데, 한 자로 재고 있었다.

    그래서 거래가 드문 갈래에는 시간 대신 건수로 잰다 — 최근 접수 3건이 연속으로 무결이면
    그 배관은 증명된 것이다. 잣대를 느슨하게 한 게 아니라, 잴 수 없는 것을 잴 수 있게 바꾼 것이다.
    어느 규칙으로 통과했는지는 출력에 그대로 남는다 — 사람이 전환을 판단할 때 봐야 한다.
    """
    sd = streak_ok_days({"_": days}, today)
    if sd >= 3:
        return sd, "3일 연속 무결", True
    cut = today.isoformat()
    had_days = len([d for d, v in days.items() if (v.get("server") or 0) > 0 and d < cut])
    if had_days < RARE_MAX_DAYS:
        rows = recent_ok_rows(days, today)
        if rows >= RARE_MIN_ROWS:
            return sd, "거래가 드문 갈래 — 최근 %d건 연속 무결" % rows, True
    return sd, None, False


def summarize_form(days, today, na=0):
    """days = {날짜: {server,sheet,mismatch,ok,...}} → by_form 한 칸(ok/total/streak_ok_days/last_fail)."""
    bad_days = [day for day, v in days.items() if not v["ok"]]
    sd, by, ok = qualification(days, today)
    return {
        "ok": sum(v["sheet"] for v in days.values()),
        "total": sum(v["server"] for v in days.values()),
        "not_applicable": na,
        "streak_ok_days": sd,
        "recent_ok_rows": recent_ok_rows(days, today),
        "qualified": ok,
        "qualified_by": by,
        "last_fail": max(bad_days) if bad_days else None,
    }


# ── DB 에서 원장·미러를 읽어 오는 자리 (판정 로직은 위, 여기는 조회만) ────────────────────
def _load(conn, db, since):
    # gas_status='test' 행은 뺀다(2026-09-05) — 격리된 테스트 페이로드는 GAS 로 안 보내 미러에도 없다 —
    # 대조에 넣으면 매번 "시트 도달 못 증명"으로 잡혀 3일 무결 스트릭을 헛되이 끊는다.
    intake = {}
    for r in conn.execute("SELECT form, received_at, payload, gas_status FROM intake_log"
                          " WHERE tenant_id=%s AND received_at >= %s AND gas_status != 'test'",
                          (db.TENANT, since)).fetchall():
        intake.setdefault(r["form"], []).append((r["received_at"], r["payload"] or {}, r["gas_status"]))
    write_rows = conn.execute("SELECT at, action, payload, gas_status FROM write_log WHERE tenant_id=%s"
                              " AND at >= %s AND gas_status != 'test'", (db.TENANT, since)).fetchall()
    writes = [(r["at"], r["payload"] or {}, r["gas_status"]) for r in write_rows]
    writes_by_action = {}   # 폼별 스트릭 분리(시우 실측 2026-09-07) — write_log 는 한 표에 여러 액션이 섞여 있다
    for r in write_rows:
        writes_by_action.setdefault(r["action"], []).append((r["at"], r["payload"] or {}, r["gas_status"]))
    inq, rec = {}, {}
    for r in conn.execute("SELECT timestamp, phone FROM inquiries WHERE tenant_id=%s AND type = ANY(%s)"
                          " AND timestamp >= %s", (db.TENANT, list(CAT_MIRROR.values()), since)).fetchall():
        inq.setdefault(str(r["timestamp"])[:10], Counter())[phone4(r["phone"])] += 1
    for r in conn.execute("SELECT created_at, data FROM reception_items WHERE tenant_id=%s AND created_at >= %s",
                          (db.TENANT, since)).fetchall():
        d = json.loads(r["data"]) if isinstance(r["data"], str) else (r["data"] or {})
        rec.setdefault(str(r["created_at"])[:10], Counter())[phone4(d.get("contact"), d.get("phone"))] += 1
    return intake, writes, {"inquiries": inq, "reception_items": rec}, writes_by_action


# 회원 담당자 5칸 필드→서버 컬럼 (api_members_write.FIELD_TO_COL 과 같은 값 — 대조 전용 사본, 순환 임포트
# 방지. 필드가 늘면 두 파일을 같이 고친다). members 미러 열쇠는 (member_no, scope) 라 시트 매치는 못 쓰고,
# members.data(JSON, sync_members.py 가 GAS 원문을 그대로 싣는 칸)의 같은 헤더값과 대조한다(배1050 · 2026-09-05).
MEMBER_OWNER_FIELDS = ("PT 담당자", "골프 담당자", "P.L 담당자", "스쿼시 담당자", "수영 담당자")
# member_hold_transition(배1054 2단계) 대조용 — api_members_write.HOLD_FIELD_LABEL 과 같은 값(사본).
MEMBER_HOLD_FIELD = "휴회접수상태"


def _member_no_by_phone(conn, db, phone):
    """전화번호로 회원번호를 찾는다. 못 찾으면 None(종전대로 대조 불가로 센다).

    뒤 4자리로만 찾지 않는다 — 4자리는 겹치는 사람이 나온다. 숫자만 남긴 전체 번호가
    같은 회원이 **정확히 한 명일 때만** 돌려준다. 두 명 이상이면 누구인지 못 정하므로 None.
    """
    digits = re.sub(r"\D", "", str(phone or ""))
    if len(digits) < 10:
        return None
    rows = conn.execute(
        "SELECT member_no FROM members WHERE tenant_id=%s AND scope='valid'"
        " AND regexp_replace(COALESCE(phone,''), '[^0-9]', '', 'g') = %s"
        " GROUP BY member_no LIMIT 2", (db.TENANT, digits)).fetchall()
    return rows[0]["member_no"] if len(rows) == 1 else None


def _reconcile_member_col_writes(conn, db, since, action, value_key, gas_field_for):
    """member_owner_save·member_hold_transition 공통 뼈대 — write_log 에 적힌 (member_no, 값) 을 그 시각
    **이후** 처음 돈 sync_members 배치의 members.data JSON 같은 칸 값과 대조한다(시포 스펙 §3 검증 방법
    그대로). 아직 그 시각 이후 배치가 한 번도 안 돈 회원번호는 mismatch 로 센다(시트 도달 증명 전이라 무결이
    아니다). gas_field_for(payload)가 None 이면(화이트리스트 밖 등) 대조 불가로 mismatch.
    반환 = ({날짜: {server,sheet,mismatch,ok}}, 표본 20건) — reconcile() 출력과 같은 모양이라 streak_ok_days
    가 그대로 먹는다."""
    rows = conn.execute(
        "SELECT at, payload FROM write_log WHERE tenant_id=%s AND action=%s"
        " AND gas_status='ok' AND at >= %s ORDER BY at", (db.TENANT, action, since)).fetchall()
    days, unmatched = {}, []
    for r in rows:
        p = r["payload"] or {}
        no, value = p.get("_member_no"), p.get(value_key)
        if not no:
            # 회원번호를 안 실은 쓰기 — 화면이 전화번호(keyPhone)를 열쇠로 보내는 경우가 있다.
            # 종전에는 그런 행을 전부 '시트 도달 증명 못 함'으로 세어 무결 스트릭을 끊었는데,
            # 실측해 보니 gas_status 는 ok 이고 열쇠도 멀쩡한 정상 쓰기였다(2026-09-06 회원 수정 6건).
            # 잴 수 있는 열쇠가 있는데 못 잰 것이라, 미러에서 전화로 회원번호를 찾아 같은 대조를 이어간다.
            no = _member_no_by_phone(conn, db, p.get("keyPhone") or p.get("phone"))
        gas_field = gas_field_for(p)
        day = str(r["at"])[:10]
        d = days.setdefault(day, {"server": 0, "sheet": 0, "mismatch": 0, "ok": True})
        d["server"] += 1
        hit = False
        if gas_field and no:
            row = conn.execute(
                "SELECT data::jsonb->>%s AS v FROM members WHERE tenant_id=%s AND member_no=%s"
                " AND scope='valid' AND synced_at > %s ORDER BY synced_at LIMIT 1",
                (gas_field, db.TENANT, no, r["at"])).fetchone()
            hit = bool(row) and (row["v"] or "") == (value or "")
        if hit:
            d["sheet"] += 1
        else:
            d["mismatch"] += 1
            d["ok"] = False
            if len(unmatched) < 20:
                unmatched.append({"date": day, "at": r["at"], "member_no": no, "field": p.get("field") or gas_field, "form": action})
    return days, unmatched


def reconcile_member_owner_writes(conn, db, since):
    """member_owner_save(1단계) 서버 쓰기 전수 대조 — 필드가 화이트리스트(MEMBER_OWNER_FIELDS) 밖이거나
    member_no 를 못 실은 옛 요청(v1 전 데이터)이면 mismatch."""
    return _reconcile_member_col_writes(
        conn, db, since, "member_owner_save", "value",
        lambda p: p.get("field") if p.get("field") in MEMBER_OWNER_FIELDS else None)


def reconcile_member_hold_writes(conn, db, since):
    """member_hold_transition(2단계 · 배1054) 서버 쓰기 전수 대조 — write_log 의 (member_no, status) 를
    members.data JSON '휴회접수상태' 칸과 대조한다. 이 칸은 hold_status 실컬럼과 달리 아직 sync_members.py
    되채움이 없지만(schema.sql 주석 참조 — 화면 진입점이 죽은 코드라 드리프트 위험 없음) data JSON 원문은
    매 sync 마다 항상 갱신되므로 대조엔 지장 없다(member_owner_save 도 컬럼이 아니라 이 JSON 과 대조)."""
    return _reconcile_member_col_writes(
        conn, db, since, "member_hold_transition", "status", lambda p: MEMBER_HOLD_FIELD)


def _norm_mirror_key(k):
    """시트 머리글 줄바꿈·공백 정규화 — sync_members.py::_norm_row 와 같은 규칙(대조 양쪽 키를 같은
    모양으로 맞춰야 한다 · 배1054 검토⑤)."""
    return re.sub(r"\s+", "", str(k or ""))


def reconcile_member_active_writes(conn, db, since):
    """member_active_update(3단계 · 배1054) 서버 쓰기 전수 대조 — 앞의 owner_save·hold_transition 과 달리
    한 쓰기가 여러 칸을 동시에 바꿀 수 있어(fields 다중 저장) _reconcile_member_col_writes(칸 1개 전용)를
    못 쓴다. write_log 의 payload._saved(api_members_write._member_active_update_one 이 실어 둔, 실제로
    저장한 모든 칸 이름→값)를 그 시각 이후 처음 돈 sync_members 배치의 members.data JSON 같은 칸들과
    한 번에 비교한다 — 그 쓰기가 바꾼 칸 전부가 일치해야 그 행이 무결(부분 일치는 무결이 아니다).
    반환 = ({날짜: {server,sheet,mismatch,ok}}, 표본 20건) — reconcile() 출력과 같은 모양."""
    rows = conn.execute(
        "SELECT at, payload FROM write_log WHERE tenant_id=%s AND action='member_active_update'"
        " AND gas_status='ok' AND at >= %s ORDER BY at", (db.TENANT, since)).fetchall()
    days, unmatched = {}, []
    for r in rows:
        p = r["payload"] or {}
        no, saved = p.get("_member_no"), p.get("_saved") or {}
        if not no:
            # 회원번호를 안 실은 쓰기 — 화면이 전화번호를 열쇠로 보낸 경우. 미러에서 찾아 이어간다.
            no = _member_no_by_phone(conn, db, p.get("keyPhone") or p.get("phone"))
        if not saved:
            # `_saved`(그 쓰기가 실제로 바꾼 칸 목록)는 배1054 부터 실린다. 그 전 형식으로 적힌 행은
            # **무엇을 바꿨는지 자체를 모른다** — 못 재는 것이지 틀린 것이 아니다. 실패로 세면 형식이
            # 바뀐 날 이전이 통째로 실패가 되어 무결 스트릭이 영영 안 찬다(실측 2026-09-09: 회원 수정
            # 09-04·06·07 의 56건이 전부 이 부류였고 gas_status 는 모두 ok 였다). 시트 도달을 못 따진
            # 행은 날짜 버킷을 아예 건드리지 않는다 — 행 0 인 날과 같게 건너뛴다(끊지도, 세지도 않는다).
            continue
        day = str(r["at"])[:10]
        d = days.setdefault(day, {"server": 0, "sheet": 0, "mismatch": 0, "ok": True})
        d["server"] += 1
        hit = False
        if no and saved:
            row = conn.execute(
                "SELECT data FROM members WHERE tenant_id=%s AND member_no=%s AND scope='valid'"
                " AND synced_at > %s ORDER BY synced_at LIMIT 1",
                (db.TENANT, no, r["at"])).fetchone()
            if row:
                try:
                    mirror = json.loads(row["data"]) if isinstance(row["data"], str) else (row["data"] or {})
                except Exception:
                    mirror = {}
                mirror_norm = {_norm_mirror_key(k): v for k, v in mirror.items()}
                hit = all((mirror_norm.get(_norm_mirror_key(f)) or "") == (v or "") for f, v in saved.items())
        if hit:
            d["sheet"] += 1
        else:
            d["mismatch"] += 1
            d["ok"] = False
            if len(unmatched) < 20:
                unmatched.append({"date": day, "at": r["at"], "member_no": no,
                                  "fields": list(saved.keys()), "form": "member_active_update"})
    return days, unmatched


def reconcile_member_hold_approve_writes(conn, db, since):
    """member_hold_approve(4단계 · 배1054) 서버 쓰기 전수 대조 — reconcile_member_active_writes 와 같은
    다중칸 비교(payload._saved ↔ members.data JSON)를 쓰되, reject 행(회원 원장 무변경 · _member_no 자체가
    없다)은 대상에서 뺀다 — approve 만 members 미러와 대조할 재료가 있다."""
    rows = conn.execute(
        "SELECT at, payload FROM write_log WHERE tenant_id=%s AND action='member_hold_approve'"
        " AND gas_status='ok' AND payload->>'decision'='approve' AND at >= %s ORDER BY at",
        (db.TENANT, since)).fetchall()
    days, unmatched = {}, []
    for r in rows:
        p = r["payload"] or {}
        no, saved = p.get("_member_no"), p.get("_saved") or {}
        if not no:
            # 회원번호를 안 실은 쓰기 — 화면이 전화번호를 열쇠로 보낸 경우. 미러에서 찾아 이어간다.
            no = _member_no_by_phone(conn, db, p.get("keyPhone") or p.get("phone"))
        if not saved:
            # `_saved`(그 쓰기가 실제로 바꾼 칸 목록)는 배1054 부터 실린다. 그 전 형식으로 적힌 행은
            # **무엇을 바꿨는지 자체를 모른다** — 못 재는 것이지 틀린 것이 아니다. 실패로 세면 형식이
            # 바뀐 날 이전이 통째로 실패가 되어 무결 스트릭이 영영 안 찬다(실측 2026-09-09: 회원 수정
            # 09-04·06·07 의 56건이 전부 이 부류였고 gas_status 는 모두 ok 였다). 시트 도달을 못 따진
            # 행은 날짜 버킷을 아예 건드리지 않는다 — 행 0 인 날과 같게 건너뛴다(끊지도, 세지도 않는다).
            continue
        day = str(r["at"])[:10]
        d = days.setdefault(day, {"server": 0, "sheet": 0, "mismatch": 0, "ok": True})
        d["server"] += 1
        hit = False
        if no and saved:
            row = conn.execute(
                "SELECT data FROM members WHERE tenant_id=%s AND member_no=%s AND scope='valid'"
                " AND synced_at > %s ORDER BY synced_at LIMIT 1",
                (db.TENANT, no, r["at"])).fetchone()
            if row:
                try:
                    mirror = json.loads(row["data"]) if isinstance(row["data"], str) else (row["data"] or {})
                except Exception:
                    mirror = {}
                mirror_norm = {_norm_mirror_key(k): v for k, v in mirror.items()}
                hit = all((mirror_norm.get(_norm_mirror_key(f)) or "") == (v or "") for f, v in saved.items())
        if hit:
            d["sheet"] += 1
        else:
            d["mismatch"] += 1
            d["ok"] = False
            if len(unmatched) < 20:
                unmatched.append({"date": day, "at": r["at"], "member_no": no,
                                  "fields": list(saved.keys()), "form": "member_hold_approve"})
    return days, unmatched


def reconcile_member_archive_restore_writes(conn, db, since):
    """member_archive_restore(6단계 · 배1054) 서버 쓰기 전수 대조 — 뒷정리(cleaned)·복귀(restored) 두 경로
    다 최종 상태는 같다: 그 회원번호가 scope='valid' 로 정확히 1건 남고 scope='archive' 에는 0건이어야
    한다(서버는 scope UPDATE 한 번뿐이라 새 채번이 없다 — 회원번호는 write_log 시점 그대로). 경로 B(복귀)는
    scope 존재만으론 값 자체가 잘못 인계돼도 못 잡아 payload._saved(종료일자·등록회차)를 members.data
    JSON 과 추가로 대조한다(배1054 검토⑤). passThrough(서버 미러에 보관 행이 없어 GAS 로만 넘긴 건 ·
    _member_no 자체가 없다)는 대조 재료 자체가 없어 서버 카운트에서도 뺀다(배1054 검토⑧ — 예전엔 항상
    mismatch 로 잡혀 이 폼의 무결 스트릭이 이 알려진 한계 하나로 매번 끊겼다 · 다른 폼처럼 대조 대상
    자체가 아닌 것으로 뺀다)."""
    rows = conn.execute(
        "SELECT at, payload FROM write_log WHERE tenant_id=%s AND action='member_archive_restore'"
        " AND gas_status='ok' AND at >= %s ORDER BY at", (db.TENANT, since)).fetchall()
    days, unmatched = {}, []
    for r in rows:
        p = r["payload"] or {}
        no = p.get("_member_no")
        if not no:   # passThrough — 대조 재료 자체가 없다 · 서버 카운트에서도 뺀다(배1054 검토⑧)
            continue
        saved = p.get("_saved") or {}
        day = str(r["at"])[:10]
        d = days.setdefault(day, {"server": 0, "sheet": 0, "mismatch": 0, "ok": True})
        d["server"] += 1
        valid_row = conn.execute(
            "SELECT data FROM members WHERE tenant_id=%s AND member_no=%s AND scope='valid'"
            " AND synced_at > %s LIMIT 1", (db.TENANT, no, r["at"])).fetchone()
        archive_row = conn.execute(
            "SELECT 1 FROM members WHERE tenant_id=%s AND member_no=%s AND scope='archive'"
            " AND synced_at > %s LIMIT 1", (db.TENANT, no, r["at"])).fetchone()
        hit = bool(valid_row) and not archive_row
        if hit and saved:   # 경로 B(복귀) — scope 뿐 아니라 인계값도 맞는지(배1054 검토⑤)
            try:
                mirror = json.loads(valid_row["data"]) if isinstance(valid_row["data"], str) else (valid_row["data"] or {})
            except Exception:
                mirror = {}
            mirror_norm = {_norm_mirror_key(k): v for k, v in mirror.items()}
            hit = all((mirror_norm.get(_norm_mirror_key(f)) or "") == (v or "") for f, v in saved.items())
        if hit:
            d["sheet"] += 1
        else:
            d["mismatch"] += 1
            d["ok"] = False
            if len(unmatched) < 20:
                unmatched.append({"date": day, "at": r["at"], "member_no": no, "form": "member_archive_restore"})
    return days, unmatched


def _area_rollup(writes_by_action, today):
    """액션별 행을 origin_switch 영역으로 합쳐 영역 단위 자격을 잰다.

    전환 스위치의 단위가 영역(write_todo·write_proc…)이라 자격도 같은 단위여야 한다. 액션별로만 재면
    한 해 두어 번 쓰는 액션(notice_delete 1건 등)이 '최근 3건 연속' 문턱을 영영 못 넘어 그 영역 전체를
    붙잡는다. 목적지(GAS URL)가 같으면 같은 스위치로 켜지고 꺼지므로 합치는 것이 맞다.
    """
    from api_write import _gas_key  # noqa: PLC0415 — selftest 는 서버 모듈 없이 돌아야 한다
    import origin_switch  # noqa: PLC0415

    merged = {}
    for action, rows in writes_by_action.items():
        area = origin_switch.WRITE_AREA.get(_gas_key(action))
        if not area:                      # 목적지를 못 정하는 액션(오타·폐기)은 영역에 안 싣는다
            continue
        merged.setdefault(area, []).extend(rows)
    out = {}
    for area, rows in merged.items():
        days, na = reconcile_by_action(sorted(rows, key=lambda r: str(r[0])))
        summary = summarize_form(days, today, na)
        summary["mode"] = origin_switch.mode(area)
        summary["actions"] = sorted({a for a, rs in writes_by_action.items()
                                     if origin_switch.WRITE_AREA.get(_gas_key(a)) == area})
        out[area] = summary
    return out


def main():
    from common import db  # noqa: PLC0415 — selftest 는 DB 없이 돌아야 한다
    now = kst_now()
    since = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    conn = db.connect(readonly=True)
    with conn:
        intake, writes, mirrors, writes_by_action = _load(conn, db, since)
        mo_days, mo_bad = reconcile_member_owner_writes(conn, db, since)
        mh_days, mh_bad = reconcile_member_hold_writes(conn, db, since)
        ma_days, ma_bad = reconcile_member_active_writes(conn, db, since)
        mha_days, mha_bad = reconcile_member_hold_approve_writes(conn, db, since)
        mar_days, mar_bad = reconcile_member_archive_restore_writes(conn, db, since)
    conn.close()
    out_forms = {"member_owner_save": mo_days, "member_hold_transition": mh_days,
                 "member_active_update": ma_days, "member_hold_approve": mha_days,
                 "member_archive_restore": mar_days}
    unmatched = list(mo_bad) + list(mh_bad) + list(ma_bad) + list(mha_bad) + list(mar_bad)
    for form, spec in FORMS.items():
        rows = writes if form == "write" else intake.get(form, [])
        days, bad = reconcile(form, rows, mirrors.get(spec["mirror"] or ""))
        out_forms[form] = days
        unmatched += bad
    today_d = now.date()
    # 폼(action)별 스트릭 — write 는 합산본(out_forms["write"])이 액션(save=점검저장 · reg_update=접수 등)을
    # 다 섞어 서로의 실패에 인질로 잡힌다(시우 실측 2026-09-07). by_form 은 액션별로 갈라 따로 센다.
    by_form = {name: summarize_form(days, today_d) for name, days in out_forms.items() if name != "write"}
    for action, rows in writes_by_action.items():
        wdays, na = reconcile_by_action(rows)
        by_form[action] = summarize_form(wdays, today_d, na)
    by_area = _area_rollup(writes_by_action, today_d)
    result = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "window_days": WINDOW_DAYS,
        "forms": out_forms,
        "streak_ok_days": streak_ok_days(out_forms, now.date()),
        "streak_note": ("행이 있었던 날만 센다 — 접수 0건인 날은 무결의 증거가 아니라 건너뛴다. "
                        "전환 자격은 갈래마다 by_form 의 qualified·qualified_by 를 본다: 거래가 잦으면 3일 연속 무결, "
                        "거래가 드문 갈래(대조한 날 3일 미만)는 최근 3건 연속 무결. 전환은 사람이 판단한다."),
        "by_form": by_form,
        "by_form_note": "폼(action)별 분리 스트릭 — write 합산본(forms.write) 대신 액션별로 본다. "
                        "not_applicable(sheet-missing)=원천이 이미 서버로 넘어간 표라 대조 실패로 안 센다.",
        "by_area": by_area,
        "by_area_note": "영역(origin_switch 스위치 단위)별 스트릭. 전환은 액션 하나가 아니라 영역 하나를 통째로 "
                        "켜는 것이라 자격도 같은 단위로 잰다 — 액션별로만 재면 한 해 두어 번 쓰는 액션이 "
                        "'표본 3건 미만'으로 영영 자격을 못 얻어, 그 영역 전체가 무결한데도 전환이 막힌다 "
                        "(2026-09-09 실측: write_todo 41행 전부 무결인데 11갈래 중 4갈래만 자격). "
                        "액션별(by_form)은 어디가 깨졌는지 짚는 진단용으로 그대로 둔다.",
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

    # member_owner_save 서버 대조(배1050) — write_log 값 ↔ members.data JSON 같은 칸, 실 DB 없이 가짜 conn 으로.
    class _MC:
        """execute() 호출 순서 고정: write_log 조회 1회 → 행마다 members.data 조회 1회. 실제 SQL 은 안 본다."""
        def __init__(self, write_rows, member_rows):
            self.write_rows, self.member_rows, self.i = write_rows, member_rows, 0

        def execute(self, sql, args=None):
            if "FROM write_log" in sql:
                self._cur = list(self.write_rows)
                return self
            v = self.member_rows[self.i] if self.i < len(self.member_rows) else None
            self.i += 1
            return _One(v)

        def fetchall(self):
            return self._cur

    class _One:
        def __init__(self, v):
            self.v = v

        def fetchone(self):
            return {"v": self.v} if self.v is not None else None

    class _DB:
        TENANT = "wellperion"

    wl = [
        {"at": "2026-09-01 10:00:00", "payload": {"field": "PT 담당자", "value": "홍길동", "_member_no": "M00001"}},
        {"at": "2026-09-01 11:00:00", "payload": {"field": "골프 담당자", "value": "김철수", "_member_no": "M00002"}},
        {"at": "2026-09-01 12:00:00", "payload": {"field": "P.L 담당자", "value": "이영희", "_member_no": "M00003"}},
    ]
    # M00001: 다음 배치 값이 같음(적중) · M00002: 다음 배치 값이 다름(불일치) · M00003: 아직 배치가 안 돎(불일치)
    days5, bad5 = reconcile_member_owner_writes(_MC(wl, ["홍길동", "김영수", None]), _DB, "2026-09-01")
    assert days5["2026-09-01"] == {"server": 3, "sheet": 1, "mismatch": 2, "ok": False}, days5
    assert {b["member_no"] for b in bad5} == {"M00002", "M00003"}, bad5
    # member_no 를 못 실은 옛 요청(v1 전) = 대조 못 함 → mismatch
    days6, _ = reconcile_member_owner_writes(
        _MC([{"at": "2026-09-02 09:00:00", "payload": {"field": "수영 담당자", "value": "박민서"}}], []), _DB, "2026-09-01")
    assert days6["2026-09-02"]["mismatch"] == 1, days6

    # member_hold_transition 서버 대조(배1054 2단계) — write_log 값(status) ↔ members.data JSON '휴회접수상태'.
    wl2 = [
        {"at": "2026-09-01 10:00:00", "payload": {"status": "진행중", "_member_no": "M00010"}},
        {"at": "2026-09-01 11:00:00", "payload": {"status": "완료", "_member_no": "M00011"}},
    ]
    # M00010: 다음 배치 값이 같음(적중) · M00011: 아직 배치가 안 돎(불일치)
    days7, bad7 = reconcile_member_hold_writes(_MC(wl2, ["진행중", None]), _DB, "2026-09-01")
    assert days7["2026-09-01"] == {"server": 2, "sheet": 1, "mismatch": 1, "ok": False}, days7
    assert {b["member_no"] for b in bad7} == {"M00011"}, bad7

    # member_active_update(3단계 배1054) 대조 — 한 쓰기가 여러 칸(payload._saved)을 동시에 바꾼다.
    # M00020: 저장한 두 칸 다 다음 배치 값과 일치(적중) · M00021: 한 칸만 어긋나도 그 행 전체가 불일치.
    class _DataOne:
        def __init__(self, v):
            self.v = v

        def fetchone(self):
            return {"data": self.v} if self.v is not None else None

    class _MC2:
        def __init__(self, write_rows, member_rows):
            self.write_rows, self.member_rows, self.i = write_rows, member_rows, 0

        def execute(self, sql, args=None):
            if "FROM write_log" in sql:
                self._cur = list(self.write_rows)
                return self
            v = self.member_rows[self.i] if self.i < len(self.member_rows) else None
            self.i += 1
            return _DataOne(v)

        def fetchall(self):
            return self._cur

    wl3 = [
        {"at": "2026-09-01 10:00:00",
         "payload": {"_member_no": "M00020", "_saved": {"주소": "서울시", "비고": "메모"}}},
        {"at": "2026-09-01 11:00:00",
         "payload": {"_member_no": "M00021", "_saved": {"주소": "부산시", "비고": "메모"}}},
    ]
    days8, bad8 = reconcile_member_active_writes(
        _MC2(wl3, [json.dumps({"주소": "서울시", "비고": "메모"}, ensure_ascii=False),
                   json.dumps({"주소": "대구시", "비고": "메모"}, ensure_ascii=False)]),
        _DB, "2026-09-01")
    assert days8["2026-09-01"] == {"server": 2, "sheet": 1, "mismatch": 1, "ok": False}, days8
    assert {b["member_no"] for b in bad8} == {"M00021"}, bad8

    # 대조 키 정규화(배1054 검토⑤) — 미러 data JSON 헤더에 줄바꿈이 섞여도 같은 칸으로 맞춰 대조한다.
    wl4 = [{"at": "2026-09-01 12:00:00", "payload": {"_member_no": "M00030", "_saved": {"재등록상담 날짜": "2026-09-10"}}}]
    days9, bad9 = reconcile_member_active_writes(
        _MC2(wl4, [json.dumps({"재등록상담\n날짜": "2026-09-10"}, ensure_ascii=False)]), _DB, "2026-09-01")
    assert days9["2026-09-01"] == {"server": 1, "sheet": 1, "mismatch": 0, "ok": True}, days9
    assert not bad9

    # 옛 형식(_saved 없음) 쓰기는 '못 잰 것'이지 '틀린 것'이 아니다 — 날짜를 아예 안 만든다(2026-09-09).
    wl4b = [{"at": "2026-09-01 12:00:00", "payload": {"_member_no": "M00030", "col": "주소", "value": "서울시"}}]
    days9b, bad9b = reconcile_member_active_writes(_MC2(wl4b, []), _DB, "2026-09-01")
    assert days9b == {} and not bad9b, (days9b, bad9b)

    # member_hold_approve(4단계 배1054) 대조 — reject 행(decision!='approve')은 SQL WHERE 로 이미 빠지므로
    # _MC2 에는 approve 행만 들어온다(reject 는 write_log 에 decision='reject' 로 남아 이 쿼리에 안 잡힌다).
    wl5 = [{"at": "2026-09-01 13:00:00", "payload": {"_member_no": "M00040", "decision": "approve",
                                                     "_saved": {"휴회횟수": "1", "휴회누적일수": "30"}}}]
    days10, bad10 = reconcile_member_hold_approve_writes(
        _MC2(wl5, [json.dumps({"휴회횟수": "1", "휴회누적일수": "30"}, ensure_ascii=False)]), _DB, "2026-09-01")
    assert days10["2026-09-01"] == {"server": 1, "sheet": 1, "mismatch": 0, "ok": True}, days10
    assert not bad10
    days11, bad11 = reconcile_member_hold_approve_writes(
        _MC2(wl5, [json.dumps({"휴회횟수": "2", "휴회누적일수": "30"}, ensure_ascii=False)]), _DB, "2026-09-01")
    assert days11["2026-09-01"]["mismatch"] == 1 and {b["member_no"] for b in bad11} == {"M00040"}, (days11, bad11)

    # member_archive_restore(6단계 배1054) 대조 — write_log(_member_no) ↔ scope='valid' 1건(+_saved 값 일치)·
    # scope='archive' 0건.
    class _MC3:
        """execute() 순서: write_log 조회 1회 → 회원번호 있는 행마다 (valid data 조회, archive 존재확인) 2회씩."""
        def __init__(self, write_rows, exist_rows):
            self.write_rows, self.exist_rows, self.i = write_rows, exist_rows, 0

        def execute(self, sql, args=None):
            if "FROM write_log" in sql:
                self._cur = list(self.write_rows)
                return self
            v = self.exist_rows[self.i] if self.i < len(self.exist_rows) else None
            self.i += 1
            return _DataOne(v) if "SELECT data FROM members" in sql else _One(v)

        def fetchall(self):
            return self._cur

    wl6 = [
        {"at": "2026-09-01 10:00:00", "payload": {"_member_no": "M00050",   # valid 1건·archive 0건·_saved 일치 → 적중
                                                  "_saved": {"종료일자": "2026-09-30", "등록회차": "2"}}},
        {"at": "2026-09-01 11:00:00", "payload": {"_member_no": "M00051"}},   # valid 아직 없음(배치 전) → 불일치
        {"at": "2026-09-01 12:00:00", "payload": {"_member_no": "M00052"}},   # valid 있는데 archive 도 남음(잔존) → 불일치
        {"at": "2026-09-01 13:00:00", "payload": {"_member_no": "M00053",   # valid·archive 는 맞는데 인계값이 어긋남(경미①) → 불일치
                                                  "_saved": {"종료일자": "2026-09-30", "등록회차": "2"}}},
    ]
    exist6 = [
        json.dumps({"종료일자": "2026-09-30", "등록회차": "2"}, ensure_ascii=False), None,
        None, None,
        json.dumps({"종료일자": "2026-09-15", "등록회차": "1"}, ensure_ascii=False), 1,
        json.dumps({"종료일자": "2026-09-01", "등록회차": "9"}, ensure_ascii=False), None,
    ]
    days13, bad13 = reconcile_member_archive_restore_writes(_MC3(wl6, exist6), _DB, "2026-09-01")
    assert days13["2026-09-01"] == {"server": 4, "sheet": 1, "mismatch": 3, "ok": False}, days13
    assert {b["member_no"] for b in bad13} == {"M00051", "M00052", "M00053"}, bad13
    # passThrough(회원번호 없는 옛 보관 행) — 대조 재료 자체가 없어 서버 카운트에서도 뺀다(배1054 검토⑧ —
    # 예전엔 항상 mismatch 로 잡혀 이 폼 무결 스트릭이 매번 끊겼다).
    days14, bad14 = reconcile_member_archive_restore_writes(
        _MC3([{"at": "2026-09-02 09:00:00", "payload": {}}], []), _DB, "2026-09-01")
    assert days14 == {} and not bad14, (days14, bad14)

    # 가린 번호(010-****-5691)에서도 뒤 4자리가 뽑힌다 — 종합접수처 미러가 이 모양이다
    assert phone4("010-****-5691") == "5691" and phone4("", None, "0104736") == "4736" and phone4("abc") == ""

    # streak — 어제부터 거꾸로, 행 없는 날은 건너뛰고 ok 아닌 날에서 끊는다
    ok, ng = {"server": 1, "ok": True}, {"server": 1, "ok": False}
    today = datetime(2026, 9, 10).date()
    f = {"inquiry": {"2026-09-09": ok, "2026-09-08": ok, "2026-09-06": ok, "2026-09-05": ng}}
    assert streak_ok_days(f, today) == 3, streak_ok_days(f, today)      # 09-07 은 행 0 → 건너뜀
    assert streak_ok_days({"inquiry": {"2026-09-09": ng}}, today) == 0
    assert streak_ok_days({"inquiry": {}}, today) == 0                  # 무입력만으로는 무결이 안 쌓인다

    # 거래가 드문 갈래 — 시간으로는 영영 안 차므로 건수로 잰다(2026-09-09)
    rare = {"2026-09-08": {"server": 2, "ok": True}, "2026-09-02": {"server": 1, "ok": True}}
    sd, by, okq = qualification(rare, today)
    assert sd < 3 and okq and "드문" in by, (sd, by, okq)               # 이틀뿐인데 3건 무결 → 통과
    thin = {"2026-09-08": {"server": 1, "ok": True}}
    assert qualification(thin, today)[2] is False                        # 1건뿐이면 아직 아니다
    rare_ng = {"2026-09-08": {"server": 3, "ok": False}}
    assert qualification(rare_ng, today)[2] is False                     # 최근 날이 실패면 통과 아님
    assert qualification(f["inquiry"], today)[1] == "3일 연속 무결"      # 잦은 갈래는 종전 규칙 그대로
    busy = {"2026-09-%02d" % d: {"server": 1, "ok": True} for d in (5, 6, 7, 8, 9)}
    assert qualification(busy, today) == (5, "3일 연속 무결", True)      # 날이 많으면 드문 규칙을 안 탄다
    assert recent_ok_rows(rare, today) == 3

    # 폼(action)별 분리(시우 실측 2026-09-07) — write_check(save) 무결이 reg_update 실패에 안 묶인다
    save_rows = [("2026-09-07T10:00:00", {}, "ok")] * 3                                 # 점검저장 3/3 ok
    reg_rows = [("2026-09-07T09:00:00", {}, "push-error:404"),                          # 진짜 실패
                ("2026-09-07T09:30:00", {}, "sheet-missing")]                           # 대조 대상 아님(서버 원천)
    d_save, na_save = reconcile_by_action(save_rows)
    d_reg, na_reg = reconcile_by_action(reg_rows)
    assert d_save["2026-09-07"] == {"server": 3, "sheet": 3, "mismatch": 0, "ok": True}, d_save
    assert na_save == 0
    assert d_reg["2026-09-07"] == {"server": 1, "sheet": 0, "mismatch": 1, "ok": False}, d_reg   # sheet-missing 빠짐
    assert na_reg == 1
    tomorrow = datetime(2026, 9, 8).date()
    assert summarize_form(d_save, tomorrow)["streak_ok_days"] == 1                      # save 는 무결 유지
    assert summarize_form(d_reg, tomorrow)["streak_ok_days"] == 0                       # reg_update 만 끊긴다
    # sheet-missing 행뿐인 날은 행 0 인 날과 같게 건너뛴다(날짜 버킷 자체가 안 생긴다)
    d_na_only, na_only = reconcile_by_action([("2026-09-06T10:00:00", {}, "sheet-missing")])
    assert d_na_only == {} and na_only == 1
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
