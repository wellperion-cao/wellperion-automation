# -*- coding: utf-8 -*-
"""
cpo_sheet_contract.py — 시트 칸 계약(sheet_columns.json) 점검기. 재발방지 A안 0단계(값 규칙 포함).
─────────────────────────────────────────────────────────────────────────────
GM 확정(2026-07-20): "재발방지 값 규칙 넣자" — 칸 이름 계약 + 값 규칙까지.
값 규칙 없이는 오늘 사고 9건 중 3건만 잡히고, 넣으면 8건이 잡힌다.

정본 계약서 = ssot/sheet_columns.json (canon_values.json과 별개 — 그건 레포 문자열
스캔용, 이건 라이브 시트 대조용이라 실행 방식이 다르다. 합치면 divergence_scan.py 오탐).

읽기 경로(재사용, 신규 백엔드 없음):
  - inquiry_2026·lesson_adult·lesson_wsc·lesson_register → gviz 직접 읽기(공개 시트).
  - member_active·member_hold → GAS 경유(cpo_report._gas_get 재사용).
    ⚠️ gviz 직독 금지 — member_expiry_alert.py 경고와 동일 이유(유효회원 탭 숨김열로
    헤더 깨짐, INC-020 계열). 반드시 GAS action(member_active_list·hold_sheet_probe).
  - 헤더 매칭은 항상 정확일치(정규화 없이 리터럴 문자열) — INC-020 재발 방지.

모드:
  (인자 없음)         상시 점검. 어긋남 있으면 dedup 후 텔레그램 1회 알림, 없으면 완전 침묵.
  --seed [--sheets a,b]  라이브 헤더 재취득 → req/allowed/refs/rules 보존 병합(ENRICHMENT_RULES
                         로만 자동 enrich, 사람 손댄 값은 이름 매칭되면 유지).
  --accept <fp|all>   지문(fp) 위반을 승인(재알림 중단). all=현재 활성 위반 전체 승인.
  --dry-run           점검만 하고 로그·상태 기록·발송 없음(콘솔 출력만).
  --test-notify       현재 상태 요약 1건을 [테스트] 태그로 업무보고방에 강제 발송(dedup 무관).

오탐 억제(무시당하면 실패다):
  1) req:true 칸만 🔴(구조 위반). 선택 칸 변경/새칸 등장은 🟡/🟢 — 로그만, 알림 없음.
  2) 같은 위반 재알림 금지 — 지문(sheet+col+유형) 해시를 상태파일에 저장, 해소·--accept 전까지 침묵.
  3) 네트워크 실패는 위반 아님 — 조용히 넘어가고, 3일 연속 실패해야 1회 알림.
  4) 공란율·형식 체크는 "최근 표본"(최대 30~10행) 기준 — 오래된 레거시 공백을 오탐하지 않는다.
  5) 업무 차단 없음 — 읽기 전용. 시트 쓰기·잠금 금지.

기록: status/sheet_contract_log.jsonl(실행 로그, append) · status/sheet_contract_state.json
      (지문 dedup·네트워크 실패 스트릭). 알림: 업무보고방(8254867551).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from collectors.base import make_payload  # noqa: E402
import cpo_report  # noqa: E402 — FUNNEL_EXEC_URL·_gas_get 재사용(신규 GAS 없음)

CONTRACT_PATH = os.path.join(_PROJECT_ROOT, "ssot", "sheet_columns.json")
STATE_PATH = os.path.join(_PROJECT_ROOT, "status", "sheet_contract_state.json")
LOG_PATH = os.path.join(_PROJECT_ROOT, "status", "sheet_contract_log.jsonl")
MEMBERSHIP_HTML = os.path.join(
    _PROJECT_ROOT, "3. 웰페리온 가이드", "cpo", "member", "membership.html"
)

KST = timezone(timedelta(hours=9))
GM_CHAT_ID = 8254867551  # 업무보고방 SSOT(CLAUDE.md §0) — 테스트도 이 방(GM 규칙)

# hold_sheet_probe 내부토큰 — Survey.js INTAKE_SUBMIT_TOKEN 기본값과 동일(읽기전용 진단 액션 전용,
# 비밀키 아님). ScriptProperties 로 교체되면 이 상수도 같이 갱신 필요(재사용 실패 시 --seed가 알려줌).
_INTAKE_TOKEN = "wlp_intake_9f4c1b7e2a63"
_MEMBER_HOLD_GID = 514238773

# 진행현황/LOSS사유 등 값 규칙 — membership.html INQ_LOSS_REASON_OPTIONS 문자 단위 일치 확인
# (2026-07-20, .deploy-funnel-v2/Survey.js loss_reason_setup 주석). 코드에서 매 실행 다시 읽어
# 대조하므로(_read_front_loss_options) 여기 상수는 그 값이 안 읽힐 때의 폴백일 뿐.
_LOSS_OPTIONS_FALLBACK = ["가격", "거리/위치", "시간대 안 맞음", "타업체 선택", "단순 문의(등록의사 없음)", "연락 두절", "기타"]

_RECENT_WINDOW = 30       # 공란율 표본창
_RECENT_TS_WINDOW = 10    # 타임스탬프 형식 표본창
_BLANK_RATE_ALERT = 0.15  # 최근 표본 중 공란 비율 임계(15%)
_MIDNIGHT_ALERT_COUNT = 2 # 최근 표본 중 00:00:00 카운트 임계
_NETWORK_FAIL_ALERT_STREAK = 3  # 연속 실패일수


# ── 시트 소스 정의(읽기 경로 SSOT) ───────────────────────────────────────────
SHEET_SOURCES = {
    "inquiry_2026": {
        "ss_id": "12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U",
        "gid": 1902010032,
        "read_via": "gviz",
    },
    "lesson_adult": {
        "ss_id": "1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw",
        "gid": 111889422,
        "read_via": "gviz",
    },
    "lesson_wsc": {
        "ss_id": "1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw",
        "gid": 268994754,
        "read_via": "gviz",
    },
    "lesson_register": {
        "ss_id": "1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw",
        "gid": None,  # 미확인 — gviz sheet= 이름으로만 조회(2026-07-20 시포). 못 찾으면 이 항목 제외.
        "sheet_name": "강습 등록현황",
        "read_via": "gviz",
    },
    "member_active": {
        "ss_id": "12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U",
        "gid": 259014685,
        "read_via": "gas",
        "gas_action": "member_active_list",
        "gas_params": {"scope": "valid"},
    },
    "member_hold": {
        "ss_id": "1akZLs7ITs3FZWFIzMQvSYrdRucGQglmerOvTC2TLEcQ",
        "gid": _MEMBER_HOLD_GID,
        "read_via": "gas",
        "gas_action": "hold_sheet_probe",
        "gas_params": {"t": _INTAKE_TOKEN},
    },
}

# 사람이 정하는 10~20칸 값 규칙(req/allowed/format/date_col/blank_check) — 부분문자열 매칭으로
# 라이브 헤더에 자동 적용(giant 개인정보 동의 본문을 dict 키로 옮겨적는 사고 방지). --seed가
# 매번 이 규칙으로 재enrich하므로 여기만 고치면 됨(새 레지스트리 파일 신설 금지).
ENRICHMENT_RULES = [
    # (sheet, 헤더에 포함되면 매칭되는 부분문자열, overrides)
    # ★이름·연락처 칸 이름 통일(2026-07-23 실측): 세 시트 모두 '성함\n(Name)'·'연락처\n(Phone Number)'로
    #   표준화됐다(옛 '1. 성함'·'유소년 이름'·'핸드폰 연락처'는 라이브에 없음). 부분일치 '성함'·'연락처'로
    #   잡되, '접수 담당자 혹은 본인/보호자 이름'은 '성함'을 포함하지 않아 오매칭되지 않는다(3시트 실측 확인).
    #   ※ 이 두 칸이 req에서 빠지면 이름·연락처가 사라져도 아무도 못 잡는다 — 감시의 핵심이라 반드시 유지.
    ("inquiry_2026", "타임스탬프", {"req": True, "format": "datetime_hms", "date_col": True}),
    ("inquiry_2026", "성함", {"req": True}),
    ("inquiry_2026", "연락처", {"req": True}),
    ("inquiry_2026", "개인정보", {"req": True, "blank_check": True}),
    ("inquiry_2026", "진행현황", {"req": True, "blank_check": False,
                                  # '신규'=미착수 기본값, '재문의로 종결'=2026-07-20 GM 확정 상태. 둘 다 정상값.
                                  "allowed": ["LOSS", "SUC", "컨택중", "가망", "단기SUC", "신규", "재문의로 종결"]}),
    ("inquiry_2026", "LOSS사유", {"allowed": list(_LOSS_OPTIONS_FALLBACK), "front_check": True}),

    ("lesson_adult", "타임스탬프", {"req": True, "format": "datetime_hms", "date_col": True}),
    ("lesson_adult", "성함", {"req": True}),
    ("lesson_adult", "연락처", {"req": True}),
    ("lesson_adult", "개인정보", {"req": True, "blank_check": True}),
    ("lesson_adult", "진행 상황", {"req": True, "blank_check": False, "allowed": ["컨택중", "LOSS", "SUC", "신규", "가망"]}),
    ("lesson_adult", "LOSS사유", {"allowed": list(_LOSS_OPTIONS_FALLBACK), "front_check": True}),

    ("lesson_wsc", "타임스탬프", {"req": True, "format": "datetime_hms", "date_col": True}),
    ("lesson_wsc", "성함", {"req": True}),
    ("lesson_wsc", "연락처", {"req": True}),
    ("lesson_wsc", "개인정보", {"req": True, "blank_check": True}),
    ("lesson_wsc", "진행 상황", {"req": True, "blank_check": False, "allowed": ["컨택중", "LOSS", "SUC", "신규", "가망", "대기"]}),
    ("lesson_wsc", "LOSS사유", {"allowed": list(_LOSS_OPTIONS_FALLBACK), "front_check": True}),

    ("member_active", "회원명", {"req": True}),
    ("member_active", "휴대폰 번호", {"req": True}),
    ("member_active", "등록\n일자", {"req": True, "date_col": True}),

    ("member_hold", "성명", {"req": True}),
    ("member_hold", "연락처", {"req": True}),
    ("member_hold", "휴회 시작일", {"req": True, "date_col": True}),
    ("member_hold", "진행 상황", {"req": True, "blank_check": False}),
    ("member_hold", "휴회 차수", {"value_rule": {"max": 3}}),
    # 하한 7→1 (2026-07-23 GM 확정): 신규 휴회만 최소 7일, '연장'은 일수 제한 없음. 실측 근거=이 시트의
    # '1회차 연장' 5일 건(김호선). 7일 하한을 연장에도 걸면 실제 운영되던 건이 전부 위반으로 잡힌다.
    # 신규/연장 구분 판정은 Survey.js(_holdMinOnce_)가 단일 출처 — 여기선 상한만 계약으로 지킨다.
    ("member_hold", "휴회 일수", {"value_rule": {"min": 1, "max": 60}}),

    ("lesson_register", "이름", {"req": True}),
    ("lesson_register", "전화", {"req": True}),
    ("lesson_register", "상태", {"req": True}),
    ("lesson_register", "등록일", {"req": True, "date_col": True}),
]

# 금지 칸(refs.forbid) — member_active 시트에 휴회 칸이 생길 뻔한 사고(v28→v29 철회) 재발방지.
# 휴회 진실은 member_hold 시트 하나뿐 — member_active에 "휴회"류 헤더가 생기면 즉시 🔴.
SHEET_REFS = {
    "member_active": {
        "forbid_patterns": ["휴회"],
        "note": "휴회 진실은 member_hold(휴회신청 응답) 시트 하나뿐. 유효회원 시트에 휴회 칸 자동생성 금지"
                "(2026-07-20 v28→v29 철회 사고 재발방지). join=연락처.",
        "join": "연락처",
        "target": "member_hold",
    },
}


# ── HTTP 유틸 ────────────────────────────────────────────────────────────────
def _gviz_fetch(ss_id, gid=None, sheet_name=None, timeout=25):
    """gviz 직접 조회 — headers=1로 헤더 오검출 방지. 반환: (cols, rows_raw, err)."""
    q = "tqx=out:json&headers=1"
    if gid is not None:
        q += "&gid=" + str(gid)
    if sheet_name is not None:
        q += "&sheet=" + urllib.parse.quote(sheet_name)
    url = f"https://docs.google.com/spreadsheets/d/{ss_id}/gviz/tq?{q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        txt = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
        m = re.search(r"setResponse\((.*)\);?\s*$", txt.strip(), re.S)
        if not m:
            return None, None, "gviz 응답 파싱 실패"
        d = json.loads(m.group(1))
        if d.get("status") != "ok" and not d.get("table"):
            return None, None, f"gviz status={d.get('status')}"
        cols = [c.get("label") or "" for c in d["table"]["cols"]]
        rows = d["table"].get("rows", [])
        return cols, rows, None
    except Exception as e:
        return None, None, f"{type(e).__name__}: {str(e)[:120]}"


def _gviz_row_values(cols, rows):
    """gviz row 목록 → [{header: value}] (datetime은 'Date(y,m,d,h,mi,s)' 원문자열 보존,
    포맷 체크에서 직접 파싱한다)."""
    out = []
    for r in rows:
        c = r.get("c") or []
        obj = {}
        for i, name in enumerate(cols):
            if not name:
                continue
            cell = c[i] if i < len(c) else None
            obj[name] = None if cell is None else cell.get("v")
        out.append(obj)
    return out


def fetch_sheet(key):
    """SHEET_SOURCES[key] 정의대로 라이브 (headers, rows[dict]) 조회. 실패 시 (None, None, err)."""
    cfg = SHEET_SOURCES[key]
    if cfg["read_via"] == "gviz":
        cols, rows_raw, err = _gviz_fetch(cfg["ss_id"], cfg.get("gid"), cfg.get("sheet_name"))
        if err:
            return None, None, err
        rows = _gviz_row_values(cols, rows_raw)
        headers = [c for c in cols if c]
        return headers, rows, None
    if cfg["read_via"] == "gas":
        # timeout 30→60·attempts 2→3 (2026-07-23 시포): hold_sheet_probe는 스프레드시트 전 탭을 훑어
        # 30초를 자주 넘긴다. 짧은 timeout이 '네트워크 실패'로 집계돼 3일이면 헛경보가 뜬다(실측 재현).
        data = cpo_report._gas_get(cfg["gas_action"], cfg.get("gas_params"), timeout=60, attempts=3)
        if data is None:
            return None, None, "GAS 응답 없음"
        headers = data.get("headers")
        if headers is None and cfg["gas_action"] == "hold_sheet_probe":
            headers = data.get("headers")  # target 서브키 없이 최상위(hpHdr) — 방어적 재확인
        rows_field = data.get("data")
        if rows_field is None:
            rows_field = data.get("head", []) + data.get("tail", [])
            if isinstance(rows_field, list) and rows_field and isinstance(rows_field[0], list):
                rows_field = [dict(zip(headers, r)) for r in rows_field]
        if headers is None:
            return None, None, "GAS 응답에 headers 없음"
        return headers, rows_field or [], None
    return None, None, f"read_via 미지원: {cfg['read_via']}"


# ── 프론트 선택지 정적 추출(네트워크 불요) ───────────────────────────────────
def read_front_loss_options():
    """membership.html 에서 INQ_LOSS_REASON_OPTIONS 배열 리터럴을 정적 추출.
    실패 시 None(미측정 — 폴백 상수로 대체하지 않고 그대로 알린다)."""
    try:
        with open(MEMBERSHIP_HTML, "r", encoding="utf-8") as f:
            txt = f.read()
        m = re.search(r"INQ_LOSS_REASON_OPTIONS\s*=\s*\[(.*?)\]", txt, re.S)
        if not m:
            return None
        items = re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1))
        return [i.replace("\\'", "'") for i in items]
    except Exception:
        return None


# ── 계약서 로드/저장 ─────────────────────────────────────────────────────────
def load_contract():
    if not os.path.exists(CONTRACT_PATH):
        return None
    with open(CONTRACT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_contract(data):
    os.makedirs(os.path.dirname(CONTRACT_PATH), exist_ok=True)
    with open(CONTRACT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _normalize(name):
    return re.sub(r"\s+", "", str(name or ""))


def _apply_enrichment(sheet_key, col_entry):
    for sk, substr, overrides in ENRICHMENT_RULES:
        if sk == sheet_key and substr in col_entry["name"]:
            col_entry.update(overrides)
    return col_entry


def _known_collisions(headers):
    """헤더 쌍 중 한쪽이 다른 쪽의 부분문자열인 쌍 전부(정규화 공백 무시) — 시드 시점 베이스라인."""
    pairs = []
    norm = [_normalize(h) for h in headers]
    for i in range(len(headers)):
        for j in range(len(headers)):
            if i >= j:
                continue
            a, b = norm[i], norm[j]
            if not a or not b or a == b:
                continue
            if len(a) >= 2 and len(b) >= 2 and (a in b or b in a):
                pairs.append(sorted([headers[i], headers[j]]))
    return pairs


def seed(only_sheets=None, write=True):
    """라이브 헤더 재취득 → req/allowed(ENRICHMENT_RULES)·기존 사람편집값 보존 병합."""
    existing = load_contract() or {
        "_doc": (
            "시트 칸 계약 SSOT — cpo_sheet_contract.py가 매일 07:50 대조. canon_values.json과 "
            "별개(그건 레포 문자열 스캔, 이건 라이브 시트 대조 — 실행 방식이 달라 합치면 "
            "divergence_scan.py가 오탐한다). 90%는 --seed 자동생성(라이브 헤더 그대로), 사람은 "
            "req(필수여부)·allowed(허용값)·refs(시트 관계)·value_rule(숫자 범위)만 편집한다. "
            "자동 갱신 금지 — 헤더가 바뀌어도 계약서는 따라가지 않는다(사고를 추종하게 됨). "
            "변경 시 알림만, 사람이 --accept로 승인해야 갱신된다."
        ),
        "_schema": {
            "sheets.<key>": "{ss_id, gid, read_via, columns[], refs?, known_collisions?}",
            "columns[]": "{name(리터럴 헤더), req, allowed?, format?, blank_check?, date_col?, "
                         "value_rule?, front_check?}",
            "refs": "{forbid_patterns, note, join, target} — 금지 칸·시트 관계",
            "known_collisions": "시드 시점에 이미 있던 부분문자열 충돌 쌍(베이스라인) — 이후 "
                                 "'신규' 충돌만 🔴",
        },
        "sheets": {},
    }
    seed_log = []
    for key, cfg in SHEET_SOURCES.items():
        if only_sheets and key not in only_sheets:
            continue
        headers, rows, err = fetch_sheet(key)
        if err:
            seed_log.append(f"[seed][실패] {key}: {err}")
            continue
        prev_cols = {c["name"]: c for c in existing.get("sheets", {}).get(key, {}).get("columns", [])}
        new_cols = []
        added, kept = 0, 0
        for h in headers:
            if h in prev_cols:
                entry = dict(prev_cols[h])
                kept += 1
            else:
                entry = {"name": h, "req": False}
                added += 1
            entry = _apply_enrichment(key, entry)
            new_cols.append(entry)
        removed = [n for n in prev_cols if n not in headers]

        sheet_entry = existing.setdefault("sheets", {}).setdefault(key, {})
        sheet_entry["ss_id"] = cfg["ss_id"]
        sheet_entry["gid"] = cfg.get("gid")
        sheet_entry["read_via"] = cfg["read_via"]
        if cfg.get("sheet_name"):
            sheet_entry["sheet_name"] = cfg["sheet_name"]
        if cfg.get("gas_action"):
            sheet_entry["gas_action"] = cfg["gas_action"]
            sheet_entry["gas_params"] = cfg.get("gas_params")
        sheet_entry["columns"] = new_cols
        sheet_entry["known_collisions"] = _known_collisions(headers)
        if key in SHEET_REFS:
            sheet_entry["refs"] = SHEET_REFS[key]
        if removed:
            sheet_entry["_removed_pending_review"] = removed
        else:
            sheet_entry.pop("_removed_pending_review", None)

        req_n = sum(1 for c in new_cols if c.get("req"))
        seed_log.append(
            f"[seed][OK] {key}: {len(headers)}칸(신규 {added}·유지 {kept}·제거후보 {len(removed)}) "
            f"req={req_n} known_collisions={len(sheet_entry['known_collisions'])}"
        )

    existing["_seeded_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    if write:
        save_contract(existing)
    for line in seed_log:
        print(line)
    return existing, seed_log


# ── 상태 파일(지문 dedup·네트워크 실패 스트릭) ───────────────────────────────
def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"fingerprints": {}, "network_fail_streak": {}}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _fingerprint(sheet, col, vtype):
    return hashlib.sha1(f"{sheet}|{col}|{vtype}".encode("utf-8")).hexdigest()[:16]


def _append_log(record):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── 타임스탬프 파싱(gviz 'Date(y,m,d,h,mi,s)' 원문자열) ──────────────────────
def _parse_gviz_date(v):
    if not isinstance(v, str) or not v.startswith("Date("):
        return None
    try:
        parts = [int(x) for x in v[5:-1].split(",")]
        while len(parts) < 6:
            parts.append(0)
        return parts  # [y, m(0-based), d, h, mi, s]
    except Exception:
        return None


# ── 시트 1개 점검 ────────────────────────────────────────────────────────────
def check_sheet(key, contract_sheet, headers, rows, front_loss_options, warnings):
    """규칙 위반 목록 반환: [{sheet, col, type, severity, detail}, ...]."""
    violations = []
    contract_cols = {c["name"]: c for c in contract_sheet.get("columns", [])}
    live_set = set(headers)

    # 완전 공백행 제외(2026-07-23 시포) — 시트 하단의 빈 줄은 데이터가 아니다. 이걸 표본에 넣으면
    # 공란율이 실제와 무관하게 치솟는다(member_hold: 20행 중 8행이 빈 줄 → '공란 40%' 오탐 3건 발생).
    # 삭제가 아니라 '세지 않기'다 — 시트는 손대지 않는다(읽기 전용 원칙).
    if isinstance(rows, list):
        rows = [r for r in rows
                if isinstance(r, dict) and any(str(v or "").strip() for v in r.values())]

    # 1) 필수 칸 사라짐/이름변경
    for name, col in contract_cols.items():
        if not col.get("req"):
            continue
        if name in live_set:
            continue
        renamed = _normalize(name) in {_normalize(h) for h in headers}
        vtype = "필수칸_이름변경" if renamed else "필수칸_사라짐"
        violations.append({"sheet": key, "col": name, "type": vtype, "severity": "R",
                            "detail": f"'{name}' 칸이 라이브 헤더에 없음(renamed={renamed})"})

    # 2) 부분일치 충돌 신규 발생
    baseline = {tuple(p) for p in contract_sheet.get("known_collisions", [])}
    live_collisions = {tuple(p) for p in _known_collisions(headers)}
    new_collisions = live_collisions - baseline
    for pair in new_collisions:
        violations.append({"sheet": key, "col": "/".join(pair), "type": "부분일치_충돌_신규",
                            "severity": "R", "detail": f"신규 부분일치 충돌: {pair[0]!r} ↔ {pair[1]!r}"})

    # 3) 금지 칸 생성
    refs = contract_sheet.get("refs")
    if refs and refs.get("forbid_patterns"):
        for h in headers:
            for pat in refs["forbid_patterns"]:
                if pat in h:
                    violations.append({"sheet": key, "col": h, "type": "금지칸_생성", "severity": "R",
                                        "detail": f"{refs.get('note', '')} — 헤더 '{h}'가 금지패턴 '{pat}' 포함"})

    # 값 단위 체크(허용값·공란율·형식) — rows 있을 때만
    n = len(rows)
    for name, col in contract_cols.items():
        if name not in live_set:
            continue
        vals_all = [r.get(name) for r in rows] if isinstance(rows, list) else []

        # 4) 허용값 이탈 + 프론트 선택지 불일치
        allowed = col.get("allowed")
        if allowed:
            eff_allowed = allowed
            if col.get("front_check") and front_loss_options:
                if set(front_loss_options) != set(allowed):
                    violations.append({"sheet": key, "col": name, "type": "허용값_프론트불일치",
                                        "severity": "R",
                                        "detail": f"계약서={allowed} vs 화면 INQ_LOSS_REASON_OPTIONS={front_loss_options}"})
                eff_allowed = front_loss_options
            offenders = set()
            for v in vals_all:
                sv = str(v or "").strip()
                if sv and sv not in eff_allowed:
                    offenders.add(sv)
            if offenders:
                violations.append({"sheet": key, "col": name, "type": "허용값_이탈", "severity": "R",
                                    "detail": f"허용값 밖 값 {sorted(offenders)[:5]} (허용={eff_allowed})"})

        # 5) 필수 칸 공란율 급증(최근 표본만 — 레거시 오탐 방지)
        if col.get("req") and col.get("blank_check", True) and n >= 5:
            recent = vals_all[-_RECENT_WINDOW:]
            blanks = sum(1 for v in recent if not str(v or "").strip())
            rate = blanks / len(recent)
            if rate > _BLANK_RATE_ALERT:
                violations.append({"sheet": key, "col": name, "type": "공란율_급증", "severity": "R",
                                    "detail": f"최근 {len(recent)}행 중 공란 {blanks}건({rate:.0%})"})

        # 6) 값 형식 위반(타임스탬프 시분초)
        if col.get("format") == "datetime_hms" and n >= 3:
            recent = vals_all[-_RECENT_TS_WINDOW:]
            midnight = 0
            for v in recent:
                p = _parse_gviz_date(v)
                if p and p[3] == 0 and p[4] == 0 and p[5] == 0:
                    midnight += 1
            if midnight >= _MIDNIGHT_ALERT_COUNT:
                violations.append({"sheet": key, "col": name, "type": "형식위반_시분초", "severity": "R",
                                    "detail": f"최근 {len(recent)}행 중 {midnight}건이 00:00:00(시분초 유실 의심)"})

        # 7) 값 규칙(숫자 범위) — 휴회 차수/일수
        vr = col.get("value_rule")
        if vr:
            bad = []
            for v in vals_all:
                sv = str(v or "").strip()
                if not sv:
                    continue
                mnum = re.search(r"-?\d+(\.\d+)?", sv)
                if not mnum:
                    continue
                num = float(mnum.group(0))
                if ("min" in vr and num < vr["min"]) or ("max" in vr and num > vr["max"]):
                    bad.append(sv)
            if bad:
                violations.append({"sheet": key, "col": name, "type": "값규칙_이탈", "severity": "R",
                                    "detail": f"규칙 {vr} 이탈 값 {sorted(set(bad))[:5]}"})

    # 8) 최근 7일 저장 0건(직전 30일 평균 대비)
    date_col = next((c["name"] for c in contract_sheet.get("columns", []) if c.get("date_col")), None)
    if date_col and date_col in live_set and n >= 10:
        now = datetime.now(KST)
        dates = []
        for r in rows:
            p = _parse_gviz_date(r.get(date_col))
            if p:
                try:
                    dates.append(datetime(p[0], p[1] + 1, p[2], tzinfo=KST))
                except Exception:
                    pass
        if dates:
            recent7 = sum(1 for d0 in dates if (now - d0).days <= 7)
            recent30 = sum(1 for d0 in dates if (now - d0).days <= 30)
            avg7 = recent30 / (30 / 7)
            if recent7 == 0 and avg7 >= 1:
                violations.append({"sheet": key, "col": date_col, "type": "최근7일_0건", "severity": "R",
                                    "detail": f"최근 7일 저장 0건(직전30일 평균 {avg7:.1f}건/7일)"})

    return violations


# ── 실행 ─────────────────────────────────────────────────────────────────────
def run_check(dry_run=False, test_notify=False):
    contract = load_contract()
    if contract is None:
        print("[check] 계약서 없음 — 먼저 --seed 실행 필요")
        return {"ok": False, "reason": "계약서 없음", "violations": []}

    state = load_state()
    front_loss_options = read_front_loss_options()

    all_violations = []
    per_sheet_status = {}
    now_iso = datetime.now(KST).isoformat()

    for key, sheet_cfg in contract.get("sheets", {}).items():
        headers, rows, err = fetch_sheet(key)
        if err:
            streak = state.setdefault("network_fail_streak", {})
            streak[key] = streak.get(key, 0) + 1
            per_sheet_status[key] = {"ok": False, "err": err, "fail_streak": streak[key]}
            if streak[key] >= _NETWORK_FAIL_ALERT_STREAK:
                all_violations.append({"sheet": key, "col": "-", "type": "네트워크_연속실패",
                                        "severity": "R", "detail": f"{streak[key]}일 연속 조회 실패: {err}"})
            continue
        state.setdefault("network_fail_streak", {})[key] = 0
        warnings = []
        vs = check_sheet(key, sheet_cfg, headers, rows, front_loss_options, warnings)
        per_sheet_status[key] = {"ok": True, "rows": len(rows), "violations": len(vs)}
        all_violations.extend(vs)

    # dedup(지문) — 신규만 알림, 활성 유지, 해소분은 상태에서 제거
    fps = state.setdefault("fingerprints", {})
    active_now = {}
    new_alerts = []
    for v in all_violations:
        fp = _fingerprint(v["sheet"], v["col"], v["type"])
        v["fp"] = fp
        active_now[fp] = v
        prior = fps.get(fp)
        if prior and prior.get("accepted"):
            continue  # 승인됨 — 계속 활성이어도 재알림 안 함
        if not prior:
            new_alerts.append(v)
            fps[fp] = {"first_seen": now_iso, "last_seen": now_iso, "detail": v["detail"], "accepted": False}
        else:
            fps[fp]["last_seen"] = now_iso
    # 해소된 지문 정리(다음에 재발하면 '신규'로 다시 잡히도록)
    for fp in list(fps.keys()):
        if fp not in active_now and not fps[fp].get("accepted"):
            del fps[fp]

    result = {
        "ok": True,
        "ts": now_iso,
        "sheets": per_sheet_status,
        "violations_active": len(active_now),
        "violations_new": len(new_alerts),
        "new_alerts": new_alerts,
    }

    if dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    _append_log({"ts": now_iso, "sheets": per_sheet_status,
                 "violations_active": len(active_now), "violations_new": len(new_alerts),
                 "new_fps": [v["fp"] for v in new_alerts]})
    save_state(state)

    if new_alerts:
        _send_alert(new_alerts)
    if test_notify:
        _send_test(result)

    return result


def _format_alert(violations, test=False):
    head = "🧪[테스트] " if test else "🔴 "
    lines = [f"{head}시트 칸 계약 위반 감지 — {len(violations)}건 (cpo_sheet_contract)"]
    for v in violations[:15]:
        lines.append(f"  · [{v['sheet']}] {v['col']} — {v['type']}: {v['detail']}")
    if len(violations) > 15:
        lines.append(f"  ...외 {len(violations) - 15}건")
    lines.append(f"기록: status/sheet_contract_log.jsonl · 승인=--accept <fp>")
    return "\n".join(lines)


def _send_alert(violations):
    from notify.telegram_send import send  # noqa: PLC0415
    send(GM_CHAT_ID, _format_alert(violations))


def _send_test(result):
    from notify.telegram_send import send  # noqa: PLC0415
    active = result.get("violations_active", 0)
    lines = [
        "🧪[테스트] cpo_sheet_contract 점검기 — 정상 작동 확인용 1회 발송",
        f"현재 활성 위반: {active}건 · 대상 시트 {len(result.get('sheets', {}))}개",
        "정상 가동 시 이 알림은 오지 않습니다(위반 있을 때만 발송·재알림 금지).",
        "기록: status/sheet_contract_log.jsonl",
    ]
    send(GM_CHAT_ID, "\n".join(lines))


def accept(fp_or_all):
    state = load_state()
    fps = state.setdefault("fingerprints", {})
    if fp_or_all == "all":
        n = 0
        for fp, rec in fps.items():
            if not rec.get("accepted"):
                rec["accepted"] = True
                n += 1
        save_state(state)
        print(f"[accept] 활성 위반 {n}건 전체 승인")
        return
    if fp_or_all in fps:
        fps[fp_or_all]["accepted"] = True
        save_state(state)
        print(f"[accept] {fp_or_all} 승인")
    else:
        print(f"[accept] 지문 미발견: {fp_or_all}")


# ── base.py 표준 payload(module_registry 조회용 — notify_wired=false라 자체발송은 없음) ──
def collect(module=None) -> dict:
    log_tail = None
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        if lines:
            log_tail = json.loads(lines[-1])
    except Exception:
        pass

    if log_tail is None:
        return make_payload(
            title="시트 칸 계약 점검", summary_line="미실행(로그 없음)",
            metrics=[], honesty_tag="미측정", link="",
        )

    active = log_tail.get("violations_active", 0)
    metrics = [
        {"label": "활성 위반", "value": active},
        {"label": "신규 위반", "value": log_tail.get("violations_new", 0)},
        {"label": "점검 시트", "value": len(log_tail.get("sheets", {}))},
    ]
    return make_payload(
        title="시트 칸 계약 점검",
        summary_line=f"활성 위반 {active}건" if active else "정상(위반 0건)",
        metrics=metrics,
        honesty_tag="측정",
        link="",
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description="시트 칸 계약 점검기(재발방지 A안 0단계)")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--sheets", default=None, help="--seed 대상 한정(쉼표구분)")
    ap.add_argument("--accept", default=None, help="지문(fp) 또는 all")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-notify", action="store_true")
    args = ap.parse_args(argv)

    if args.seed:
        only = args.sheets.split(",") if args.sheets else None
        seed(only_sheets=only)
        return 0
    if args.accept:
        accept(args.accept)
        return 0

    result = run_check(dry_run=args.dry_run, test_notify=args.test_notify)
    if not args.dry_run:
        print(json.dumps({k: v for k, v in result.items() if k != "new_alerts"},
                          ensure_ascii=False, indent=2))
        for v in result.get("new_alerts", []):
            print(f"  [신규] {v['sheet']}.{v['col']} {v['type']}: {v['detail']} (fp={v['fp']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
