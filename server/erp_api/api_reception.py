# -*- coding: utf-8 -*-
"""종합접수처 미러 API (배 922 AWS 전환 1호 · 배 984 쓰기 서버화 · 2026-09-05).

읽기: sync_reception.py 가 5분마다 떠온 reception_items·lost_found·hold_items 미러를 종합접수처_현황.html 이
쓰는 GAS 응답 모양 그대로 돌려준다 — 화면 코드는 주소만 바꾼다.
쓰기(배 984 · GM 지시 "GAS 승인 단계 자체를 없앤다"): reg_submit·lf_submit 은 이제 GAS 를 거치지 않고 이 서버가
원장(reception_items·lost_found)에 직접 적는다 — GAS 외부호출 승인(텔레그램) 이 막혀도 접수·습득물 등록이 죽지 않는다.
  ★ID 연속성: RECEPTION-N·LF-N 번호는 배포 시 GAS ScriptProperties 값(RECEPTION_SEQ·LF_SEQ)을 1회 seed 해
    이어받는다(reception_seq·lost_found_seq 시퀀스) — 이후 서버가 유일한 발급자. GAS 쪽 reg_submit/lf_submit 은
    더 이상 호출하지 않는다(같은 번호를 두 곳이 각자 매기면 충돌 — origin_switch.py NO_SERVER 가 경고하던 바로 그 문제).
    시트는 이 전환 시점 이후로는 갱신되지 않는다(읽기 전용 과거 기록으로 동결) — 후속 과제로 남긴다.
  app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.
  GET  /api/reception/board            reg_board 와 같음 {ok,count,data} + by_status·by_category
  GET  /api/reception/lost             lf_list 와 같음 {ok,count,data}
  GET  /api/reception/hold             member_hold_intake_list 와 같음 + 행마다 done(hold_done_keys 조인)
  GET  /api/reception/scoreboard?period=all|week|month   reg_scoreboard 와 같음 {ok,board}
  GET  /api/reception/health           행 수·마지막 동기화
  POST /api/reception/submit           reg_submit 대체(공개·무인증 — nginx erp-locations 에서 auth 제외) · 종합접수처 6종 폼
  POST /api/reception/lost             lf_submit 대체(로그인 뒤 · 습득물 등록 — 사진 필수)
  POST /api/reception/update           reg_update 대체(배 1039-C · 2026-09-05) — 서버 원장 직접 갱신, GAS 는 안 부른다.
    위 ★ID 연속성 메모대로 시트가 동결돼 있어, 배984 이후 새로 접수된 건은 GAS reg_update 가 시트에서 못 찾아
    "해당 접수ID를 찾을 수 없습니다" 로 실패한다(상태·담당·메모 저장이 조용히 안 먹는 실사고) — 이 엔드포인트가 그 갭을 메운다.
    화면 배선(종합접수처_현황.html _update() 가 이 주소를 쓰게 바꾸는 것)은 COO 담당 — 여기서는 API만 연다.
  POST /api/reception/photo            사진만 저장하고 URL 반환(단독 호출용 · submit/lost 는 내부에서 직접 저장한다)
자체점검: python3 api_reception.py --selftest   (DB·네트워크 없음 — 부서 배정·사진 디코딩 판정만)
"""
import base64
import hashlib
import json
import os
import sys
import time
import urllib.request

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402  — DB 를 여는 유일한 자리 · 모든 조회는 tenant_id 로 거른다

SOURCE = "sheet-mirror"
PERIODS = ("all", "week", "month")
router = APIRouter(prefix="/api/reception")

# ─── 카테고리·부서 배정 — apps_script_reception.js REG_CATEGORIES·REG_LOC_DEPT·_regDeptFor 이식 (배 984) ───
#   dept 변경 시 원본(GAS)도 같이 고쳐야 하던 것을, 이제 이 표 한 곳만 고치면 된다(GAS 쪽은 더 이상 안 쓴다).
REG_CATEGORIES = {
    "lost":       {"label": "분실물 접수",           "dept": "운영부", "photo": True,  "extra": ("itemName", "lostWhen")},
    "facility":   {"label": "시설물 고장 접수",       "dept": "시설부", "photo": True,  "extra": ()},
    "clean":      {"label": "청결 이슈 접수",         "dept": "",       "photo": True,  "extra": ()},
    "praise":     {"label": "직원·강사 칭찬합니다",   "dept": "운영부", "photo": False, "extra": ()},
    "voice":      {"label": "직원·강사 쓴소리합니다", "dept": "운영부", "photo": False, "extra": ()},
    "complaint":  {"label": "컴플레인 접수",          "dept": "운영부", "photo": True,  "extra": ()},
}
REG_LOC_DEPT = {
    "헬스장": "P.T팀", "수영장": "수영팀", "남자사우나": "지원부(남)", "여자사우나": "지원부(여)",
    "락커": "", "골프장": "골프팀", "스쿼시장": "스쿼시팀", "체조장": "체조팀", "G.X룸": "G.X팀",
    "주차장": "주차관리부", "리셉션": "운영부", "카페": "카페", "기타": "운영부",
}
LF_CATEGORIES = ("consumable", "general", "valuable")
# apps_script_reception.js LEGACY_RECEPTION_STATUSES 와 같은 값 — 갱신 시 status 는 이 셋만 받는다.
REG_STATUSES = ("접수", "처리중", "완료")
# reg_update(GAS·_regUpdate) 가 받던 갱신칸 그대로 — 화면 _update() 가 보내는 필드와 1:1(배 1039-C).
REG_UPDATE_FIELDS = ("memo", "memberReply", "handler", "reporter", "name", "targetStaff",
                     "dept", "dueDate", "policyFix")
# 사진 저장 — nginx erp-locations 새 파일이 /uploads/ 를 무인증 정적 서빙한다(배 984). 시트 대신 서버 디스크.
UPLOAD_DIR = os.environ.get("ERP_UPLOAD_DIR", "/srv/erp/uploads")
UPLOAD_URL_BASE = "/uploads"
# 제출 토큰 게이트(2026-09-05 검수 H3) — 구 GAS _vSubmitGateOk_ 가 보던 것과 같은 값. 폼(reception_block.html /
# wp_reception_block_en.html)이 이미 이 이름으로 보내던 상수를 그대로 서버 쪽 기본값에도 둔다 — env 로 바꿀 수 있다.
RECEPTION_SUBMIT_TOKEN = os.environ.get("RECEPTION_SUBMIT_TOKEN", "wlp_voc_7b3f9a2e6c1d4085")
DUP_WINDOW_SEC = 90   # 재시도 큐 자동 재전송 창(rcqBackoff 최대 30초×attempts) — 그 안의 같은 내용은 중복 제출로 본다


def _open():
    try:
        return db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


def _openw():
    try:
        return db.connect()
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


def _kst_now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def _next_id(conn, seq, prefix):
    n = conn.execute("SELECT nextval(%s::regclass)", (seq,)).fetchone()[0]
    return "%s%d" % (prefix, n)


def dept_for(cat_key, loc):
    """접수 건의 담당 부서 — 장소가 정한다(GAS _regDeptFor 와 동일 규칙). 빈 문자열 = 사람이 배정한다는 뜻."""
    cat = REG_CATEGORIES.get(cat_key)
    if not cat:
        return ""
    loc = (loc or "").strip()
    if cat_key in ("complaint", "clean"):
        if "여자" in loc or "여성" in loc:
            return "지원부(여)"
        if "남자" in loc or "남성" in loc:
            return "지원부(남)"
        if cat_key == "clean" and loc == "기타":
            return ""
        d = REG_LOC_DEPT.get(loc)
        return cat["dept"] if d is None else d
    return cat["dept"]


def save_photo(photo, file_name, mime, subdir):
    """base64(옵션 data: 접두) -> 서버 디스크 저장, 공개 URL 반환. 실패하면 빈 문자열(접수 자체는 계속 진행)."""
    if not photo:
        return ""
    try:
        b64 = photo.split(",", 1)[1] if str(photo).startswith("data:") else photo
        raw = base64.b64decode(b64, validate=False)
        if not raw:
            return ""
        # 확장자는 mime 표 값으로만 — fileName 폴백은 무인증 통로에서 .html/.svg 를 ERP 오리진에 심는 저장 XSS 통로였다
        # (2026-09-05 검수 C3). 표에 없으면 저장하지 않는다. 파일 머리 바이트로 실제 그림인지도 본다.
        ext = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime)
        magic_ok = raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n" or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")
        if not ext or not magic_ok:
            return ""
        # subdir 는 화이트리스트 — '../..' 로 업로드 폴더 밖에 쓰이던 것 차단(검수 C2)
        subdir = subdir if subdir in ("reception", "lost-found") else "reception"
        name = hashlib.sha256(raw).hexdigest()[:24] + ext
        month = time.strftime("%Y%m", time.gmtime(time.time() + 9 * 3600))
        d = os.path.join(UPLOAD_DIR, subdir, month)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "wb") as f:
            f.write(raw)
        return "%s/%s/%s/%s" % (UPLOAD_URL_BASE, subdir, month, name)
    except Exception:
        return ""


def _dup_recent(conn, cat_label, contact, content, loc, now_str):
    """최근 DUP_WINDOW_SEC 안에 같은 내용(카테고리+연락처+내용+장소)이 이미 접수됐으면 그 reg_id 를 돌려준다
    (2026-09-05 검수 H4) — 재시도 큐가 429·5xx 뒤 같은 본문을 자동 재전송해도 두 줄로 안 남게. 스키마 변경 없이
    최근 20건만 비교한다(ponytail: 접수가 몰릴 때 정확도 낮아짐 — 늘리려면 idem 키 컬럼+유니크 인덱스로 승격)."""
    import datetime as _dtm
    try:
        now_t = _dtm.datetime.strptime(now_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    rows = conn.execute(
        "SELECT reg_id, created_at, data FROM reception_items WHERE tenant_id=%s AND category=%s"
        " ORDER BY created_at DESC LIMIT 20", (db.TENANT, cat_label)).fetchall()
    for r in rows:
        try:
            created_t = _dtm.datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            continue
        if (now_t - created_t).total_seconds() > DUP_WINDOW_SEC:
            break   # created_at DESC 순 — 창 밖이면 이후 행도 전부 밖
        try:
            d = json.loads(r["data"])
        except (TypeError, ValueError):
            continue
        if d.get("contact") == contact and d.get("content") == content and d.get("loc") == loc:
            return r["reg_id"]
    return None


def notify(text):
    """텔레그램 즉시 알림 — 서버가 이미 쓰는 방식(erp_auth.tell_gm·sync_members._tell_gm 과 같은 패턴) 그대로,
    새 발신기를 만들지 않는다. 방 = RECEPTION_CHAT_ID(핵심멤버방 · GAS 진단 diag 로 확인한 실제 값, api.env 전용).
    토큰·chat_id 없으면 조용히 스킵(접수 자체는 막지 않는다) — GAS _vNotifyTelegram 과 같은 불변식."""
    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("RECEPTION_CHAT_ID")
    if not token or not chat:
        return False
    try:
        req = urllib.request.Request(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            data=json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
        return True
    except Exception:
        return False


def _rows(conn, table, order):
    rs = conn.execute("SELECT * FROM %s WHERE tenant_id=%%s ORDER BY %s" % (table, order), (db.TENANT,)).fetchall()
    out = []
    for r in rs:
        d = json.loads(r["data"])
        d["_synced_at"] = r["synced_at"]
        if "done" in r.keys():
            d["done"] = bool(r["done"])
        out.append(d)
    return out


@router.get("/board")
def board():
    conn = _open()
    with conn:
        data = _rows(conn, "reception_items", "created_at DESC, reg_id")   # reg_dashboard 와 같은 정렬(createdAt 최근순)
    by_status, by_cat = {}, {}
    for d in data:
        by_status[d.get("status") or ""] = by_status.get(d.get("status") or "", 0) + 1
        by_cat[d.get("category") or ""] = by_cat.get(d.get("category") or "", 0) + 1
    return {"ok": True, "count": len(data), "data": data, "by_status": by_status, "by_category": by_cat, "_source": SOURCE}


@router.get("/lost")
def lost():
    conn = _open()
    with conn:
        data = _rows(conn, "lost_found", "created_at DESC, found_id")
    return {"ok": True, "count": len(data), "data": data, "_source": SOURCE}


@router.get("/hold")
def hold():
    conn = _open()
    with conn:
        data = _rows(conn, "hold_items", "CAST(intake_row AS INTEGER)")     # GAS 와 같은 시트 행 순서
    return {"ok": True, "count": len(data), "done": sum(1 for d in data if d.get("done")), "data": data, "_source": SOURCE}


@router.get("/scoreboard")
def scoreboard(period: str = Query("month")):
    period = period.strip().lower()
    if period not in PERIODS:
        raise HTTPException(400, "period 는 %s 중 하나" % "/".join(PERIODS))
    conn = _open()
    with conn:
        v = db.meta_get(conn, "reception_scoreboard_" + period)
    d = json.loads(v) if v else {"ok": True, "board": []}
    d["_source"] = SOURCE
    return d


@router.get("/health")
def health():
    conn = _open()
    with conn:
        n = {t: conn.execute("SELECT COUNT(*) FROM %s WHERE tenant_id=%%s" % t, (db.TENANT,)).fetchone()[0]
             for t in ("reception_items", "lost_found", "hold_items")}
        hold_done = conn.execute("SELECT COUNT(*) FROM hold_items WHERE tenant_id=%s AND done", (db.TENANT,)).fetchone()[0]
        meta = dict(conn.execute("SELECT k, v FROM sync_meta WHERE tenant_id=%s AND k LIKE 'reception_last%%'", (db.TENANT,)).fetchall())
    return {"ok": True, "rows": n, "hold_done": hold_done, "last_sync_kst": meta.get("reception_last_sync"),
            "last_failed": meta.get("reception_last_failed") or "", "_source": SOURCE}


# ═══════════════════════════════════════════════════════════════════════
#  쓰기 — 배 984 (2026-09-05) · 서버가 원장, GAS 는 더 이상 부르지 않는다
# ═══════════════════════════════════════════════════════════════════════
@router.post("/submit")
async def submit(request: Request):
    """reg_submit 대체 — 종합접수처 6종 폼(분실물·시설고장·청결·칭찬·쓴소리·컴플레인).
    무인증(nginx erp-locations 가 /api/reception/submit 만 auth_request 제외 — 공개 키오스크가 부른다)."""
    try:
        payload = json.loads((await request.body()).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
    except Exception:
        return JSONResponse({"ok": False, "error": "bad-payload"}, status_code=400)

    if str(payload.get("t") or "") != RECEPTION_SUBMIT_TOKEN:   # 제출 토큰 게이트(검수 H3)
        return JSONResponse({"ok": False, "error": "접수 권한 확인에 실패했습니다. 페이지를 새로고침 후 다시 시도해 주세요.",
                             "code": "BAD_TOKEN"}, status_code=400)

    cat_key = str(payload.get("category") or "").strip()
    cat = REG_CATEGORIES.get(cat_key)
    if not cat:
        return {"ok": False, "error": "알 수 없는 카테고리입니다: %s" % cat_key[:60]}

    name = str(payload.get("name") or "").strip()
    contact = str(payload.get("contact") or "").strip()
    is_anon = cat_key == "voice" and str(payload.get("anonymousPref") or "").strip() == "예"
    is_check = str(payload.get("source") or "").strip() == "check"
    if not is_anon and not is_check and (not name or not contact):
        return {"ok": False, "error": "이름과 연락처는 필수입니다."}
    if is_anon:
        name, contact = name or "익명", contact or "익명"
    if is_check:
        name, contact = name or "지원부 점검", contact or "자동접수(점검)"

    loc = str(payload.get("loc") or payload.get("location") or "").strip()
    content = str(payload.get("content") or "").strip()
    photo_input = payload.get("photo") or payload.get("file") or payload.get("base64") or ""
    photo_url = ""
    photo_warning = ""
    if cat["photo"]:
        photo_url = save_photo(photo_input, payload.get("fileName") or "", payload.get("mimeType") or "image/jpeg", "reception")
        if photo_input and not photo_url:   # 사진은 보냈는데 저장 실패 — 접수자에게 알린다(검수 M7)
            photo_warning = "사진 저장에 실패했습니다. 접수는 정상 처리되었습니다."

    dept = dept_for(cat_key, loc)
    now = _kst_now()
    conn = _openw()
    with conn:
        dup_id = _dup_recent(conn, cat["label"], contact, content, loc, now)   # 재시도 큐 중복 접수 방지(검수 H4)
        data = None
        if dup_id:
            reg_id = dup_id
        else:
            reg_id = _next_id(conn, "reception_seq", "RECEPTION-")
            data = {"regId": reg_id, "category": cat["label"], "createdAt": now, "name": name, "contact": contact,
                    "loc": loc, "content": content, "photoUrl": photo_url, "status": "접수", "memo": "", "dept": dept,
                    "handler": "", "reporter": str(payload.get("reporter") or "").strip() or ("자동(점검)" if is_check else "회원"),
                    "memberReply": ""}
            for k in cat["extra"]:
                v = payload.get(k)
                if v not in (None, ""):
                    data[k] = str(v)
            conn.execute("INSERT INTO reception_items (tenant_id, reg_id, category, dept, status, created_at, data, synced_at)"
                         " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                         (db.TENANT, reg_id, cat["label"], dept, "접수", now, json.dumps(data, ensure_ascii=False), now))
    conn.close()

    if dup_id:   # 중복 접수 — 이미 알림도 나갔으니 다시 적지도, 다시 알리지도 않는다(검수 H4)
        return {"ok": True, "id": reg_id, "dept": dept, "photoWarning": photo_warning}

    extra_line = "\n".join("%s: %s" % (k, data[k]) for k in cat["extra"] if data.get(k))
    notify("📋 <b>[종합 접수처]</b> %s\n부서: %s\n이름: %s\n위치: %s\n%s내용: %s\n🕒 %s"
          % (cat["label"], dept or "-", ("익명" if is_anon else name), loc or "-",
             (extra_line + "\n") if extra_line else "", content[:100] if content else "-", now))
    return {"ok": True, "id": reg_id, "dept": dept, "photoWarning": photo_warning}


@router.post("/lost")
async def lost_submit(request: Request):
    """lf_submit 대체 — 직원 습득물 등록(로그인 뒤 · 사진 필수). GAS 는 더 이상 부르지 않는다(원장=서버 DB)."""
    try:
        payload = json.loads((await request.body()).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
    except Exception:
        return JSONResponse({"ok": False, "error": "bad-payload"}, status_code=400)

    found_when = str(payload.get("foundWhen") or "").strip()
    found_loc = str(payload.get("foundLoc") or payload.get("loc") or "").strip()
    item_desc = str(payload.get("itemDesc") or payload.get("content") or "").strip()
    staff = str(payload.get("staff") or "").strip()
    category = str(payload.get("category") or "").strip()
    if category not in LF_CATEGORIES:
        category = "general"
    photo = payload.get("photo") or payload.get("file") or payload.get("base64") or ""
    if not photo:
        return {"ok": False, "error": "습득물 사진은 필수입니다. (갤러리 노출용)"}
    if not found_loc and not item_desc:
        return {"ok": False, "error": "습득장소 또는 설명 중 하나는 입력해 주세요."}

    photo_url = save_photo(photo, payload.get("fileName") or "", payload.get("mimeType") or "image/jpeg", "lost-found")
    if not photo_url:
        return {"ok": False, "error": "사진 저장에 실패했습니다. 다시 시도해 주세요."}

    now = _kst_now()
    conn = _openw()
    with conn:
        found_id = _next_id(conn, "lost_found_seq", "LF-")
        data = {"foundId": found_id, "createdAt": now, "foundWhen": found_when, "foundLoc": found_loc,
                "itemDesc": item_desc, "photoUrl": photo_url, "status": "게시중", "staff": staff, "category": category,
                "keepLoc": str(payload.get("storageLoc") or payload.get("keepLoc") or "").strip(),
                "memo": str(payload.get("memo") or "").strip()}
        conn.execute("INSERT INTO lost_found (tenant_id, found_id, status, created_at, data, synced_at)"
                     " VALUES (%s,%s,%s,%s,%s,%s)",
                     (db.TENANT, found_id, "게시중", now, json.dumps(data, ensure_ascii=False), now))
    conn.close()

    notify("🧳 <b>[습득물 접수]</b> %s\n습득장소: %s\n설명: %s\n%s🕒 %s"
          % (found_id, found_loc or "-", item_desc[:100] if item_desc else "-",
             ("등록: %s\n" % staff if staff else ""), now))
    return {"ok": True, "id": found_id, "photoUrl": photo_url}


@router.post("/update")
async def update(request: Request):
    """reg_update 대체 — 서버 원장(reception_items) 직접 갱신. 배984 이후 접수건은 시트에 없어 GAS reg_update 가
    실패하는 갭을 메운다(배 1039-C · 2026-09-05). GAS 는 부르지 않는다 — 시트는 이미 동결된 과거 기록이다."""
    try:
        payload = json.loads((await request.body()).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
    except Exception:
        return JSONResponse({"ok": False, "error": "bad-payload"}, status_code=400)

    reg_id = str(payload.get("id") or payload.get("접수ID") or "").strip()
    if not reg_id:
        return {"ok": False, "error": "id 필수"}
    new_status = str(payload.get("status") or "").strip()
    if new_status and new_status not in REG_STATUSES:
        return {"ok": False, "error": "상태는 접수|처리중|완료 만 허용"}

    conn = _openw()
    with conn:
        row = conn.execute("SELECT category, dept, status, data FROM reception_items WHERE tenant_id=%s AND reg_id=%s",
                           (db.TENANT, reg_id)).fetchone()
        if not row:
            conn.close()
            return {"ok": False, "error": "해당 접수ID를 찾을 수 없습니다: %s" % reg_id}
        data = json.loads(row["data"])
        for k in REG_UPDATE_FIELDS:
            if k in payload and payload[k] is not None:
                data[k] = str(payload[k])
        if new_status:
            data["status"] = new_status
        status = data.get("status") or row["status"]
        dept = data.get("dept") or row["dept"]
        conn.execute("UPDATE reception_items SET status=%s, dept=%s, data=%s, synced_at=%s WHERE tenant_id=%s AND reg_id=%s",
                     (status, dept, json.dumps(data, ensure_ascii=False), _kst_now(), db.TENANT, reg_id))
    conn.close()
    return {"ok": True, "id": reg_id, "status": status, "message": "접수건이 갱신되었습니다."}


@router.post("/photo")
async def photo_upload(request: Request):
    """사진만 저장 — submit/lost 는 내부에서 직접 save_photo() 를 부르므로 이 경로를 안 거친다.
    다른 화면이 사진만 먼저 올려 URL 을 받아 둘 때 쓰는 단독 통로."""
    try:
        payload = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        return JSONResponse({"ok": False, "error": "bad-payload"}, status_code=400)
    photo = payload.get("photo") or payload.get("file") or payload.get("base64") or ""
    if not photo:
        return {"ok": False, "error": "photo 없음"}
    url = save_photo(photo, payload.get("fileName") or "", payload.get("mimeType") or "image/jpeg",
                     str(payload.get("subdir") or "reception").strip() or "reception")
    if not url:
        return {"ok": False, "error": "저장 실패"}
    return {"ok": True, "url": url}


def selftest():
    assert RECEPTION_SUBMIT_TOKEN == "wlp_voc_7b3f9a2e6c1d4085", "폼(reception_block.html) 상수와 어긋남"  # 검수 H3
    assert REG_STATUSES == ("접수", "처리중", "완료"), "GAS LEGACY_RECEPTION_STATUSES 와 어긋남"  # 배 1039-C
    assert set(REG_UPDATE_FIELDS) == {"memo", "memberReply", "handler", "reporter", "name", "targetStaff",
                                      "dept", "dueDate", "policyFix"}, "GAS _regUpdate 갱신칸과 어긋남"
    assert dept_for("facility", "헬스장") == "시설부"          # 부서 고정 카테고리는 장소 무관
    assert dept_for("clean", "여자사우나") == "지원부(여)"      # 성별 표기 우선
    assert dept_for("clean", "남자") == "지원부(남)"
    assert dept_for("clean", "기타") == ""                     # 청결+기타 = 사람이 배정(GM 2026-08-28)
    assert dept_for("complaint", "기타") == "운영부"           # 컴플레인+기타는 기본 부서로
    assert dept_for("clean", "수영장") == "수영팀"
    assert dept_for("clean", "락커") == ""                     # 표에 있어도 빈 값 = 사람이 배정
    assert dept_for("praise", "아무데나") == "운영부"          # 부서 고정 카테고리
    assert dept_for("nope", "x") == ""
    assert REG_CATEGORIES["lost"]["extra"] == ("itemName", "lostWhen")

    import tempfile
    global UPLOAD_DIR
    with tempfile.TemporaryDirectory() as d:
        UPLOAD_DIR = d
        fake_jpeg = b"\xff\xd8\xff" + b"fake-jpeg-bytes"   # 매직바이트 필요(검수 C3 이후 · 확장자만으론 저장 안 됨)
        b64 = base64.b64encode(fake_jpeg).decode()
        url = save_photo("data:image/jpeg;base64," + b64, "x.jpg", "image/jpeg", "reception")
        assert url.startswith("/uploads/reception/") and url.endswith(".jpg"), url
        path = os.path.join(d, *url[len(UPLOAD_URL_BASE) + 1:].split("/"))
        assert os.path.exists(path) and open(path, "rb").read() == fake_jpeg
        assert save_photo(b64, "x.html", "application/octet-stream", "../../evil") == "", \
            "mime 표에 없으면 저장 안 함(C3) + subdir 화이트리스트(C2)"
        assert save_photo("", "", "image/jpeg", "reception") == ""          # 사진 없음 = 조용히 빈 문자열
        assert save_photo("not-base64-!!!", "", "image/jpeg", "reception") == ""  # 깨진 값도 예외 없이 빈 문자열
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest())
