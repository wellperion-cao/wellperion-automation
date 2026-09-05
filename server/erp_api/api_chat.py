# -*- coding: utf-8 -*-
"""상담봇 백엔드 (배1018 시토 → 배1036 구조전환 · 모델 = cbo/model/상담봇_기획설계_v1.0.html §3-1·§3-2).

POST /api/chat/{tenant}            공개(로그인 없음) — 질문 1개 → 정본 학습형 컨시어지 모델(주 엔진) 또는
    FAQ 매칭(백업 · 키 없음·모델 오류·한도일 때만) → 답 또는 고정 문구('상담 예약').
GET  /api/chat/{tenant}/unanswered 관문 뒤(로그인) — 최근 N일 미답 질문 목록(시보가 아침 학습 회로로 읽는다).
PUT  /api/chat/{tenant}/faq · GET .../stats · POST .../feedback · GET .../profile — 배1036 관리자 API 4개.

주 엔진(ANTHROPIC_API_KEY 있을 때) = 업체 정본 11구역+FAQ+오늘 운영 상태를 시스템 프롬프트로 준 컨시어지 모델
(claude-sonnet-5 · env COUNSEL_MODEL 로 교체 가능) — 지어내기 차단은 프롬프트가 아니라 출력검사 코드
(_grounded·_forbidden_hit)가 한다. 키 없으면 백업(문장 겹침 매칭·모델 호출 0)으로 자동 전환(회귀 0).
FAQ 저장 = /srv/erp/faq/{tenant}/faq.json (tenant = "1_wellperion" | "2_dietcamp" — 서버에 이미 있는 실제
    센터 구분 이름 그대로 재사용. GM 지시는 "1_웰페리온/2_다이어트캠프 구분" 이지만, 서버는 이미 이 ASCII 이름으로
    구분해 뒀다(deploy_dietcamp.sh). 저장 위치는 /srv/www 가 아니라 /srv/erp/faq 다 — /srv/www/1_wellperion 은
    /srv/erp/www 를 거쳐 git 저장소 체크아웃(/srv/erp/repo)을 그대로 가리키는 링크라, 그 안에 파일을 쓰면
    서버 쪽 git 워처와 충돌한다(약속: 임시인덱스·동시커밋 손상 전례). FAQ 는 그 트리 밖의 전용 폴더에 둔다.
    {"meta": {"reservation_url": "..."}, "faq": [{"id": "...", "q": "...", "a": "..."}, ...]}
로그 = /srv/erp/chat_log.jsonl 한 줄(시각·tenant·질문·매칭 여부·faq_id) — 이름 입력칸은 없다. 질문 자유텍스트에
    실린 전화번호·이메일은 저장 전에 마스킹한다(원문 그대로는 안 남긴다 · 검수 M5). 20MB 넘으면 .1 로 회전(검수 M4).
금지어(금액·계약) 관문 = scripts/diet_camp_agent.FORBIDDEN 그대로 재사용(이 파일도 같이 서버에 올린다 —
    다캠 에이전트는 GM PC 전용 스크립트라 나머지 의존 모듈은 없고, FORBIDDEN 은 stdlib 만으로 끝나는 상수라 이 파일 하나만 옮기면 된다).
의료 표현은 다캠 에이전트에 목록이 없어 이 파일에 최소로 새로 둔다(둘 다 "금액·의료" 관문 하나로 합쳐 검사).
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                                    # 서버 배포 뒤(같은 폴더에 diet_camp_agent.py 도 올린다)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_HERE)), "scripts"))  # 로컬 저장소 실행용
from diet_camp_agent import FORBIDDEN as MONEY_WORDS  # noqa: E402 — 배1018 요청④ 금지어 관문 재사용
try:
    from close_days import is_closed as _is_closed_day  # noqa: E402 — 배1036 GM⑥ 오늘 운영 상태(코드 계산 · 기존 규칙 재사용)
except ImportError:
    _is_closed_day = None  # 서버에 아직 안 올렸으면(deploy_chat.sh 가 같이 올린다) 오늘 상태 줄만 빈 문자열

router = APIRouter(prefix="/api/chat")

TENANTS = {"1_wellperion", "2_dietcamp", "3_spogym"}   # 배1036 요청④ — 스포짐 폴더는 비어 있어도(FAQ 0) 라우트는 연다
FAQ_DIR = os.environ.get("ERP_FAQ_DIR", "/srv/erp/faq")
SEED_FAQ_DIR = os.path.join(_HERE, "seed_faq")   # /srv/erp/faq 에 없을 때 폴백 — 개발 PC 자체점검용(검수 L4)
LOG_PATH = os.environ.get("ERP_CHAT_LOG", "/srv/erp/chat_log.jsonl")
LOG_ROTATE_BYTES = 20 * 1024 * 1024   # 검수 M4 — welly_auto_runner._append_log 와 같은 방식(.1 로 밀고 두 세대만)
UNANSWERED_TAIL_BYTES = 300 * 1024    # unanswered 는 전량 스캔 대신 로그 꼬리만 본다(검수 M4)
_PHONE_RE = re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
MATCH_THRESHOLD = 0.5   # ponytail: overlap coefficient 고정값 — 다캠 첫 달 실측 뒤 조정(모델 문서 §6)
# 배1018 후속(2026-09-05): 어미·조사만 겹쳐 오답 매칭되는 사고("주차 되나요"→멤버십 FAQ) 차단 —
# _best_match 가 어미 정규화 + 교집합 2개 이상을 함께 요구한다.
_Q_ENDINGS = ("습니까", "되나요", "인가요", "있나요", "하나요", "어떻게", "얼마", "는지", "가요", "나요", "까", "요")
_Q_ENDING_RE = re.compile("|".join(re.escape(w) for w in sorted(_Q_ENDINGS, key=len, reverse=True)))
# 다캠 에이전트엔 없던 의료 관문 — 최소 목록(늘어나면 이 튜플만 고친다)
MEDICAL_WORDS = ("진단", "처방", "치료", "질환", "질병", "의약", "부작용", "수술", "임신", "약물", "합병증")
# MONEY_WORDS(FORBIDDEN)는 AI 가 '보내는' 문장을 막던 목록이라 손님이 '묻는' 가격 질문은 못 거른다(검수 L3) —
# 받는 질문 전용 최소 목록. 가격 문의는 FAQ 로만 답하고(있으면) 없으면 상담 예약 안내로 보낸다.
PRICE_QUESTION_WORDS = ("가격", "요금", "회비", "비용", "얼마")
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"}

# 배1036(관리자 API 4개) — FAQ 정본은 이제 서버 파일(FAQ_DIR/{tenant}/faq.json)이다. deploy_dietcamp.sh 는
# 이미 있는 서버 faq.json 을 덮지 않도록 고쳤다(관리자 편집이 다음 배포에 지워지지 않게 · 정본 한 곳).
# 프로필(테넌트 이름·색·예약 링크)도 같은 폴더에 profile.json 으로 둔다(배포가 counselbot/tenants/*.json 을 그대로 복사).
PROFILE_FILENAME = "profile.json"
TENANTS_SEED_DIR = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "server", "counselbot", "tenants")
FEEDBACK_LOG_PATH = os.environ.get("ERP_CHAT_FEEDBACK_LOG", "/srv/erp/chat_feedback.jsonl")
WARN_WORDS = tuple(MONEY_WORDS) + MEDICAL_WORDS + PRICE_QUESTION_WORDS   # 관리자 저장 시 경고(막지 않음) — 배1036 요청⑤
# close_days.json 정본 = 저장소 status/(공휴일 목록도 여기) — 서버는 /srv/erp/www 가 git 5분 동기화라 그 경로를
# 그대로 읽는다(별도 배포 불필요). 로컬 자체점검은 저장소 상대경로로 폴백.
CLOSE_DAYS_PATH = os.environ.get(
    "ERP_CLOSE_DAYS",
    "/srv/erp/www/status/close_days.json" if os.path.isdir("/srv/erp/www") else
    os.path.join(os.path.dirname(os.path.dirname(_HERE)), "status", "close_days.json"))
COUNSEL_MODEL = os.environ.get("COUNSEL_MODEL", "global.anthropic.claude-sonnet-4-6")   # sonnet-5 는 이 계정 아직 승인 전(실측) — 계약 완료된 4.6 로. 한 줄로 교체(Bedrock 크로스리전 id)
_SESSION_TURNS = 6     # 배1036 GM 구조전환② — 대화 문맥(최근 N턴)
_SESSION_MAX = 2000    # ponytail: 세션 상한 없으면 메모리 누수 — 오래된 세션 정리는 재시작뿐(필요해지면 TTL 추가)
_SESSIONS: dict = {}   # session_id -> [{"role":..,"content":..}, ...] · 프로세스 메모리(재시작하면 비워짐 · FAILS 패턴과 동일)
# "오늘 운영하나요"·"지금 영업해요?" 처럼 시간말(오늘·지금)+상태말(영업·운영·휴관…) 둘 다 있어야 매칭 —
# 시간말만(예: "오늘 저녁 메뉴 추천해 주세요") · 상태말만("운영 시간은 어떻게 되나요" = 일반 FAQ f04 몫)은 여기서 뺀다.
_HOURS_TEMPORAL_WORDS = ("오늘", "지금", "현재")
_HOURS_STATUS_WORDS = ("영업", "휴관", "운영", "문 여", "문여", "여나요", "닫나요", "여는지", "닫는지", "몇 시까지", "몇시까지")


def _kst_now() -> str:
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%dT%H:%M:%S")


def _bigrams(s: str) -> set:
    """한글 2-gram(글자 단위) — 한글·영문·숫자만 남기고 공백·기호는 버린다."""
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s or "")
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _normalize_q(s: str) -> str:
    """매칭 전용 정규화 — 공백·기호 제거 뒤 조사·어미·물음 표현을 지운다("주차 되나요"→"주차").
    원문(로그·답변)은 그대로 두고 매칭 판단에만 쓴다."""
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s or "")
    return _Q_ENDING_RE.sub("", s)


def _load_faq(tenant: str) -> dict:
    path = Path(FAQ_DIR) / tenant / "faq.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # /srv/erp/faq 는 서버 전용 경로 — 개발 PC 엔 없어서 자체점검이 못 돌았다(검수 L4). 저장소에 같이
        # 딸려 오는 seed_faq 를 폴백으로 쓴다(서버에선 /srv/erp/faq 가 항상 먼저 있으니 동작 그대로).
        try:
            data = json.loads((Path(SEED_FAQ_DIR) / (tenant + ".json")).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"meta": {}, "faq": []}
    data.setdefault("meta", {})
    data.setdefault("faq", [])
    return data


def _forbidden_hit(q: str) -> bool:
    return (any(w in q for w in MONEY_WORDS) or any(w in q for w in MEDICAL_WORDS)
            or any(w in q for w in PRICE_QUESTION_WORDS))


def _best_match(q: str, faq: list):
    """(faq_item|None, score) — 정규화 뒤 overlap coefficient(짧은 쪽 bigram 수 기준).
    교집합 2-gram 2개 이상 AND 비율 0.5 이상만 매칭 후보 — 어미 한두 글자만 겹쳐 확신 있게
    엉뚱한 FAQ 로 답하는 사고(배1018 후속) 차단. 정규화 길이 2자 이하면 무조건 미매칭.
    item.alt(선택, 동의어 문구 목록 — 예: "골프 레슨"↔"골프 트레이닝")도 q 와 같은 자격으로 후보에 넣는다."""
    nq = _normalize_q(q)
    if len(nq) <= 2:
        return None, 0.0
    qb = _bigrams(nq)
    if not qb:
        return None, 0.0
    best, best_score = None, 0.0
    for item in faq:
        item_score = 0.0
        for cand in [item.get("q", "")] + list(item.get("alt") or []):
            fb = _bigrams(_normalize_q(cand))
            if not fb:
                continue
            inter = qb & fb
            if len(inter) < 2:
                continue
            score = len(inter) / min(len(qb), len(fb))
            if score >= 0.5 and score > item_score:
                item_score = score
        if item_score > best_score:
            best, best_score = item, item_score
    return best, best_score


def _fallback_text(tenant: str, meta: dict) -> str:
    """못 답할 때 문구 — 테넌트 페르소나(identity.counselor_persona.handoff)가 있으면 그걸 쓴다(사람 상담원
    말투 · 배1036 GM 지시). 없으면 옛 고정 문구 + 예약 링크(스포짐처럼 페르소나 미수령인 테넌트 폴백)."""
    persona = _persona_of(tenant)
    handoff = persona.get("handoff")
    if handoff:
        return handoff
    url = (meta or {}).get("reservation_url") or ""
    base = "정확한 안내를 위해 상담 예약을 도와드릴게요."
    return f"{base} 예약: {url}" if url else base


def _mask_pii(q: str) -> str:
    """로그에 남기기 전 전화번호·이메일 마스킹(검수 M5) — 상담 문의는 대개 "010-...로 연락 주세요" 형태로 온다."""
    return _EMAIL_RE.sub("[이메일]", _PHONE_RE.sub("[전화번호]", q or ""))


def _log(tenant: str, q: str, answered: bool, faq_id):
    row = {"ts": _kst_now(), "tenant": tenant, "q": _mask_pii(q), "answered": answered, "faq_id": faq_id}
    try:
        os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
        # 20MB 넘으면 .1 로 밀어 두 세대만 남긴다(검수 M4 — welly_auto_runner._append_log 와 같은 방식).
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_ROTATE_BYTES:
            os.replace(LOG_PATH, LOG_PATH + ".1")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass  # ponytail: 로그 실패가 고객 답변을 막으면 안 된다


@router.options("/{tenant}")
def preflight(tenant: str):
    return Response(status_code=204, headers=CORS)


@router.post("/{tenant}")
async def chat(tenant: str, request: Request):
    if tenant not in TENANTS:
        raise HTTPException(404, "모르는 센터: %s" % tenant)
    try:
        body = json.loads((await request.body()).decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError:
        body = {}
    q = str((body or {}).get("q") or "").strip()
    session_id = str((body or {}).get("session_id") or "")[:128]   # 배1036 GM 구조전환② — 클라이언트가 만든 임의 문자열
    data = _load_faq(tenant)
    fallback = _fallback_text(tenant, data.get("meta"))
    if not q or _forbidden_hit(q):
        _log(tenant, q, False, None)
        out = {"ok": True, "answered": False, "answer": fallback, "faq_id": None, "tenant": tenant}
        return Response(json.dumps(out, ensure_ascii=False), media_type="application/json; charset=utf-8", headers=CORS)

    # 주 엔진(배1036 GM 구조전환) — 정본 학습형 컨시어지 모델. 실패/키없음/일일한도 = "error"(레거시 매칭 백업으로).
    text, status = (None, "error") if _over_daily_limit(tenant) else _concierge_answer(tenant, q, session_id)
    if status == "ok":
        _log(tenant, q, True, None)
        out = {"ok": True, "answered": True, "answer": text, "faq_id": None, "tenant": tenant}
    elif status == "invalid":
        # 모델은 답했지만 출력검사 탈락(금지어·근거밖 숫자) — 레거시로 재시도하지 않고 바로 핸드오프(§3-1④).
        _log(tenant, q, False, None)   # ⑤ 핸드오프 = 미답 기록(관리자 페이지·아침 회로가 읽는다)
        out = {"ok": True, "answered": False, "answer": fallback, "faq_id": None, "tenant": tenant}
    else:
        # 백업(§3-1⑥) — 키 없음·모델 오류·한도(429) 때만. 오늘 운영 질문은 모델 없이도 코드로 바로 답한다(배1036 GM⑥).
        today_line = _today_hours_line(tenant)
        if today_line and _is_hours_question(q):
            _log(tenant, q, True, "today_hours")
            out = {"ok": True, "answered": True, "answer": today_line, "faq_id": "today_hours", "tenant": tenant}
        else:
            item, score = _best_match(q, data.get("faq") or [])
            if item and score >= MATCH_THRESHOLD:
                _log(tenant, q, True, item.get("id"))
                out = {"ok": True, "answered": True, "answer": item.get("a", ""), "faq_id": item.get("id"), "tenant": tenant}
            else:
                _log(tenant, q, False, None)
                out = {"ok": True, "answered": False, "answer": fallback, "faq_id": None, "tenant": tenant}
    return Response(json.dumps(out, ensure_ascii=False), media_type="application/json; charset=utf-8", headers=CORS)


@router.get("/{tenant}/unanswered")
def unanswered(tenant: str, days: int = 7):
    if tenant not in TENANTS:
        raise HTTPException(404, "모르는 센터: %s" % tenant)
    cutoff = datetime.now(timezone(timedelta(hours=9))) - timedelta(days=days)
    out = []
    try:
        # 전량 스캔 대신 로그 꼬리만 본다(검수 M4) — 회전(20MB)으로 크기는 이미 눌러뒀고, 아침 학습 회로가
        # 보는 창은 최근 며칠뿐이라 꼬리 300KB 로 충분하다. ponytail: 정확히 days 일치 안 되면(꼬리 밖 과거
        # 행 누락) 회전 세대(.1)까지 볼 것 — 지금은 그 정도로 못 미친다.
        with open(LOG_PATH, "rb") as fb:
            fb.seek(0, os.SEEK_END)
            size = fb.tell()
            start = max(0, size - UNANSWERED_TAIL_BYTES)
            fb.seek(start)
            tail_text = fb.read().decode("utf-8", errors="replace")
        lines = tail_text.splitlines()
        if start > 0 and lines:
            lines = lines[1:]   # 꼬리 시작점이 줄 중간이면 그 첫 줄은 잘려 있다 — 버린다
        for line in lines:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("tenant") != tenant or row.get("answered"):
                    continue
                try:
                    ts = datetime.strptime(row["ts"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone(timedelta(hours=9)))
                except (KeyError, ValueError):
                    continue
                if ts >= cutoff:
                    out.append({"q": row.get("q", ""), "ts": row.get("ts", "")})
    except OSError:
        pass
    return {"ok": True, "tenant": tenant, "days": days, "count": len(out), "questions": out}


# ── 배1036 관리자 API 4개 ──────────────────────────────────────────────────
def _faq_path(tenant: str) -> Path:
    return Path(FAQ_DIR) / tenant / "faq.json"


def _profile_path(tenant: str) -> Path:
    return Path(FAQ_DIR) / tenant / PROFILE_FILENAME


def _save_faq(tenant: str, data: dict) -> None:
    p = _faq_path(tenant)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _warn_words(text: str) -> list:
    """저장 전 금액·의료 낱말 경고(막지 않음 · GM 판단) — 배1036 요청⑤."""
    return sorted({w for w in WARN_WORDS if w in (text or "")})


def _apply_faq_edit(data: dict, body: dict) -> dict:
    """PUT .../faq 의 순수 로직(비동기·Request 없이 테스트 가능하게 분리) — 미답→FAQ 승격도 이 함수 하나로
    (id 없이 q·a 만 보내면 새 항목, id 를 보내면 그 항목 수정). data 는 in-place 로 바뀐다."""
    q = str(body.get("q") or "").strip()
    a = str(body.get("a") or "").strip()
    if not q or not a:
        raise ValueError("q·a 는 필수입니다")
    faq = data.setdefault("faq", [])
    fid = str(body.get("id") or "").strip()
    alt = [str(x).strip() for x in (body.get("alt") or []) if str(x).strip()]
    verified = bool(body.get("verified", False))
    source = str(body.get("source") or "관리자").strip()
    today = _kst_now()[:10]
    existing = next((it for it in faq if it.get("id") == fid), None) if fid else None
    if existing is not None:
        existing.update({"q": q, "a": a, "alt": alt, "verified": verified, "source": source, "updated": today})
        item = existing
    else:
        existing_ids = {it.get("id") for it in faq}
        new_id = fid or ("m%02d" % (len(faq) + 1))
        if new_id in existing_ids:
            new_id = "m" + today.replace("-", "") + ("%02d" % (len(faq) + 1))
        item = {"id": new_id, "q": q, "a": a, "alt": alt, "verified": verified, "source": source, "updated": today}
        faq.append(item)
    return item


@router.put("/{tenant}/faq")
async def edit_faq(tenant: str, request: Request):
    """FAQ 추가·수정 (관문 뒤 · nginx chat.conf 가 auth_request) — 미답 질문 옆에 답 한 줄 써서 넣으면
    이 API 로 승격된다(§4②). 저장 = 서버 faq.json(정본 · deploy_dietcamp.sh 는 이미 있으면 안 덮는다)."""
    if tenant not in TENANTS:
        raise HTTPException(404, "모르는 센터: %s" % tenant)
    try:
        body = json.loads((await request.body()).decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "잘못된 JSON")
    data = _load_faq(tenant)
    try:
        item = _apply_faq_edit(data, body or {})
    except ValueError as e:
        raise HTTPException(400, str(e))
    _save_faq(tenant, data)
    return {"ok": True, "tenant": tenant, "item": item, "warn": _warn_words(item.get("a", ""))}


@router.get("/{tenant}/stats")
def stats(tenant: str, days: int = 30):
    """질문 수·자력 답변 비율·미답 상위 — chat_log.jsonl 만 읽는다(이름·전화 없음 · §4④)."""
    if tenant not in TENANTS:
        raise HTTPException(404, "모르는 센터: %s" % tenant)
    cutoff = datetime.now(timezone(timedelta(hours=9))) - timedelta(days=days)
    total = answered = 0
    unanswered_count: dict = {}
    try:
        # ponytail: 전량 스캔(회전 전 세대 .1 은 안 봄) — 관리자 화면이 여는 통계라 자주 안 불리고,
        # 20MB 회전 전이면 30일 창 정도는 현재 파일에 다 있다. 부족해지면 unanswered 처럼 꼬리로 바꾼다.
        with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("tenant") != tenant:
                    continue
                try:
                    ts = datetime.strptime(row["ts"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone(timedelta(hours=9)))
                except (KeyError, ValueError):
                    continue
                if ts < cutoff:
                    continue
                total += 1
                if row.get("answered"):
                    answered += 1
                else:
                    key = row.get("q", "")
                    unanswered_count[key] = unanswered_count.get(key, 0) + 1
    except OSError:
        pass
    top_unanswered = sorted(unanswered_count.items(), key=lambda kv: -kv[1])[:10]
    return {"ok": True, "tenant": tenant, "days": days, "total": total, "answered": answered,
            "answer_ratio": round(answered / total, 3) if total else None,
            "top_unanswered": [{"q": q, "count": c} for q, c in top_unanswered]}


@router.options("/{tenant}/feedback")
def feedback_preflight(tenant: str):
    return Response(status_code=204, headers=CORS)


@router.post("/{tenant}/feedback")
async def feedback(tenant: str, request: Request):
    """👍👎 한 번 (공개 · 개인정보 0 · §3⑤) — 저장 = faq_id·vote 만."""
    if tenant not in TENANTS:
        raise HTTPException(404, "모르는 센터: %s" % tenant)
    try:
        body = json.loads((await request.body()).decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError:
        body = {}
    vote = str((body or {}).get("vote") or "").strip()
    if vote not in ("up", "down"):
        raise HTTPException(400, "vote 는 up|down 만")
    row = {"ts": _kst_now(), "tenant": tenant, "faq_id": (body or {}).get("faq_id"), "vote": vote}
    try:
        os.makedirs(os.path.dirname(FEEDBACK_LOG_PATH) or ".", exist_ok=True)
        if os.path.exists(FEEDBACK_LOG_PATH) and os.path.getsize(FEEDBACK_LOG_PATH) > LOG_ROTATE_BYTES:
            os.replace(FEEDBACK_LOG_PATH, FEEDBACK_LOG_PATH + ".1")
        with open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass  # ponytail: 로그 실패가 고객 응답을 막으면 안 된다(_log 와 같은 원칙)
    return Response(json.dumps({"ok": True}, ensure_ascii=False), media_type="application/json; charset=utf-8", headers=CORS)


def _load_profile(tenant: str) -> dict:
    try:
        return json.loads(_profile_path(tenant).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # 서버에 아직 배포 전(로컬 자체점검) — 저장소 정본 tenants/*.json 을 폴백으로 읽는다(검수 L4 와 같은 원칙).
        try:
            return json.loads((Path(TENANTS_SEED_DIR) / (tenant + ".json")).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}


def _persona_of(tenant: str) -> dict:
    return (_load_profile(tenant).get("identity") or {}).get("counselor_persona") or {}


# ── L2 클라이언트 — AWS Bedrock 우선(배1036 GM · 계정 cao 통일 · 키 대신 EC2 IAM 역할) ──────
# 우선순위: Bedrock(AnthropicBedrock 표준 · 키 0) → 1P(ANTHROPIC_API_KEY 있으면 대안) → None(백업).
# AnthropicBedrockMantle 은 오진(bedrock-mantle.*.api.aws 도메인 자체가 없는 제품) — 시보 지적으로 표준 클래스로 교체.
_ANTHROPIC_CLIENT = (None, False)   # (client|None, tried) — 최초 1회만 만들고 재사용(요청마다 새 client 금지)
_DIGITS_RE = re.compile(r"\d+")
BEDROCK_REGION = os.environ.get("ERP_BEDROCK_REGION", "ap-northeast-2")
BEDROCK_ALERT_FLAG = os.environ.get("ERP_BEDROCK_ALERT_FLAG", "/srv/erp/bedrock_alert.txt")
DAILY_QUESTION_LIMIT = 300   # 테넌트당 하루 이 수를 넘으면 백업 매칭으로 자동 전환(가드①)
_DAILY_COUNTS: dict = {}     # (tenant, "YYYY-MM-DD") -> count · 프로세스 메모리(재시작하면 리셋 — ponytail: 하루살이라 문제없음


def _anthropic_client():
    global _ANTHROPIC_CLIENT
    client, tried = _ANTHROPIC_CLIENT
    if tried:
        return client
    try:
        from anthropic import AnthropicBedrock
        client = AnthropicBedrock(aws_region=BEDROCK_REGION)
    except Exception:
        client = None   # boto3·SDK 없음 등 — 1P 로 대안
    if client is None and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic()
        except ImportError:
            client = None   # ponytail: SDK 미설치 — 키가 와도 이 계층은 그냥 스킵(회귀 0 유지)
    _ANTHROPIC_CLIENT = (client, True)
    return client


def _tg_alert_bedrock_once(text: str) -> None:
    """Bedrock 접근 오류(AccessDenied 등) 하루 1회만 업무보고방 경고 — 매 요청마다 스팸 금지."""
    today = _kst_now()[:10]
    try:
        if Path(BEDROCK_ALERT_FLAG).read_text(encoding="utf-8").strip() == today:
            return
    except OSError:
        pass
    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("TG_CHAT_ID")
    if token and chat:
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://api.telegram.org/bot%s/sendMessage" % token,
                data=json.dumps({"chat_id": chat, "text": text}).encode(),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=8)
        except Exception:
            pass   # 알림 실패해도 서비스는 계속(이미 백업으로 넘어간 뒤다)
    try:
        Path(BEDROCK_ALERT_FLAG).write_text(today, encoding="utf-8")
    except OSError:
        pass


def _over_daily_limit(tenant: str) -> bool:
    """테넌트당 하루 질문 300건 넘으면 백업 매칭으로(가드① · 배1036 GM 3중 가드)."""
    key = (tenant, _kst_now()[:10])
    _DAILY_COUNTS[key] = _DAILY_COUNTS.get(key, 0) + 1
    return _DAILY_COUNTS[key] > DAILY_QUESTION_LIMIT


def _is_english_q(q: str) -> bool:
    """한글이 하나도 없고 영문자가 있으면 영어 질문으로 본다(1차 한·영만 · 배1036 GM②)."""
    return not re.search(r"[가-힣]", q or "") and bool(re.search(r"[A-Za-z]", q or ""))


def _grounded(text: str, source: str) -> bool:
    """모델 출력에 근거(FAQ 원문)에 없는 숫자가 새로 등장하면 False(배1036 GM① 근거 밖 숫자 차단)."""
    src_nums = set(_DIGITS_RE.findall(source or ""))
    return all(n in src_nums for n in _DIGITS_RE.findall(text or ""))


def _today_hours_line(tenant: str) -> str:
    """오늘 운영 상태 한 줄(코드 계산 · 모델 없음) — 배1036 GM⑥·설계 §3-1⑦. facts.hours 없는 테넌트
    (다캠·스포짐 지금)는 빈 문자열 — 호출부가 핸드오프로 넘어간다. 휴관 판정은 scripts/close_days.is_closed
    그대로 재사용(기존 지원부 체계.html getDayInfo 와 같은 2·4째 일요일 규칙 · 새로 안 만든다)."""
    hours = (_load_profile(tenant).get("facts") or {}).get("hours")
    if not isinstance(hours, dict) or not hours.get("weekday") or _is_closed_day is None:
        return ""
    today = datetime.now(timezone(timedelta(hours=9))).date()

    def _fmt(d):
        return "%d/%d(%s)" % (d.month, d.day, "월화수목금토일"[d.weekday()])

    def _next(d, want_closed):
        for _ in range(60):
            d = d + timedelta(days=1)
            if _is_closed_day(d) == want_closed:
                return d
        return d
    if _is_closed_day(today):
        return "오늘 %s · 휴관 · 다음 영업일 %s" % (_fmt(today), _fmt(_next(today, False)))
    try:
        public_holidays = set(json.loads(Path(CLOSE_DAYS_PATH).read_text(encoding="utf-8")).get("public_holidays", []))
    except (OSError, json.JSONDecodeError):
        public_holidays = set()
    is_holiday = today.strftime("%Y-%m-%d") in public_holidays
    is_weekend = today.weekday() >= 5
    today_hours = hours.get("holiday") if is_holiday else (hours.get("weekend") if is_weekend else hours.get("weekday"))
    return "오늘 %s · %s · 휴관 아님 · 다음 휴관 %s" % (_fmt(today), today_hours or "", _fmt(_next(today, True)))


def _is_hours_question(q: str) -> bool:
    """오늘 운영 여부를 묻는 질문인가(배1036 GM⑥) — 백업(모델 없음) 경로에서 코드로 바로 답할 때 쓴다."""
    q = q or ""
    return any(t in q for t in _HOURS_TEMPORAL_WORDS) and any(s in q for s in _HOURS_STATUS_WORDS)


def _session_history(session_id: str) -> list:
    return list(_SESSIONS.get(session_id, [])[-_SESSION_TURNS * 2:]) if session_id else []


def _session_append(session_id: str, q: str, a: str) -> None:
    if not session_id:
        return
    hist = _SESSIONS.setdefault(session_id, [])
    hist.append({"role": "user", "content": q})
    hist.append({"role": "assistant", "content": a})
    del hist[:len(hist) - _SESSION_TURNS * 2]   # 최근 N턴만
    if len(_SESSIONS) > _SESSION_MAX:
        _SESSIONS.pop(next(iter(_SESSIONS)), None)   # ponytail: 삽입순 dict 맨 앞 제거 — 정교한 LRU 아님(세션 늘면 TTL)


_CONCIERGE_PRINCIPLES = (
    "당신은 호텔 컨시어지처럼 응대하는 상담원입니다. 다음 7원칙을 지킵니다 — "
    "1)먼저 맞이한다(인사+오늘 상황을 먼저 건넨다) 2)답 먼저, 이유는 짧게(첫 문장에 결론) "
    "3)'안 됩니다'로 끝내지 않는다(항상 대안 하나) 4)기억한다(같은 대화에서 앞서 말한 걸 다시 안 묻는다) "
    "5)모르면 확인해서 연락(지어내지 않고 '확인해서 알려드릴게요' + 예약 제안) "
    "6)마무리도 사람처럼(자연스러운 다음 제안) 7)업체 톤 위에 컨시어지를 얹는다."
)   # 설계 §3-2 원칙 7 그대로


def _concierge_system_block(tenant: str, prof: dict, persona: dict) -> str:
    """system 프롬프트 = 업체 정본 11구역 전부 + FAQ 전체 + 오늘 상태 한 줄(배1036 GM 구조전환①·설계 §3-1①·⑦).
    cache_control 로 캐싱 — 정본이 바뀌기 전까진 매 질문 동일해 그대로 재사용된다."""
    faq = _load_faq(tenant).get("faq") or []
    faq_lines = "\n".join("- id=%s Q:%s A:%s" % (it.get("id"), it.get("q", ""), it.get("a", "")) for it in faq)
    name = persona.get("name") or tenant
    tone = persona.get("emoji") or "적당히"
    handoff = persona.get("handoff") or "그 부분은 제가 확인해서 알려드릴게요 🙏 상담 예약을 남겨 주시면 연락드립니다."
    service_concept = (prof.get("identity") or {}).get("service_concept") or ""
    today_line = _today_hours_line(tenant)
    return (
        "%s 당신은 '%s' 상담원입니다(%s). 이모지는 '%s' 수준으로 씁니다. "
        "아래 [업체 정본]·[FAQ]에 적힌 사실·상품·규정만 사실로 말하세요 — 없는 것은 지어내지 말고 "
        "\"%s\" 라고 답하세요. 금액 숫자·의료 판단은 말하지 않습니다. "
        "질문이 영어면 영어로, 한국어면 한국어로 답하세요. 답변 문장만 출력하세요(설명·따옴표 없이). "
        "이 화면은 카카오톡 대화창처럼 평문만 보입니다 — 마크다운 금지(**굵게**·목록 기호·제목 기호 쓰지 않는다).\n\n"
        "[오늘] %s\n\n[업체 정본]\n%s\n\n[FAQ]\n%s"
        % (_CONCIERGE_PRINCIPLES, name, service_concept, tone, handoff, today_line or "미확인",
           json.dumps(prof, ensure_ascii=False), faq_lines)
    )


def _concierge_answer(tenant: str, q: str, session_id: str):
    """정본 학습형 주 엔진(배1036 GM 구조전환 · 설계 §3-1·§3-2) — 반환 (답|None, status).
    status: 'ok'(그대로 응답) · 'invalid'(출력검사 탈락 → 호출부가 핸드오프) ·
    'error'(키 없음·모델 오류·한도 → 호출부가 레거시 FAQ 매칭 백업으로 · §3-1⑥)."""
    client = _anthropic_client()
    if not client:
        return None, "error"
    persona = _persona_of(tenant)
    prof = _load_profile(tenant)
    system = _concierge_system_block(tenant, prof, persona)
    history = _session_history(session_id)
    lang_hint = " (질문이 영어이니 영어로 답하세요)" if _is_english_q(q) else ""
    try:
        resp = client.messages.create(
            model=COUNSEL_MODEL, max_tokens=500,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=history + [{"role": "user", "content": q + lang_hint}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        # 종류를 미리 안 가린다(권한·DNS·한도 등 원인이 다양 — 실측에서 "AccessDenied 예상"이 실제로는
        # bedrock-mantle.{region}.api.aws DNS 미응답으로 나왔다) — 뭐가 됐든 주 엔진이 안 됐다는 신호라 알린다.
        _tg_alert_bedrock_once("⚠️ 상담봇 주 엔진(Bedrock) 호출 실패 — FAQ 백업으로 자동 전환 중. %s: %s"
                                % (type(e).__name__, str(e)[:200]))
        return None, "error"
    if not text or _forbidden_hit(text) or not _grounded(text, system):
        return None, "invalid"
    _session_append(session_id, q, text)
    return text, "ok"


@router.options("/{tenant}/profile")
def profile_preflight(tenant: str):
    return Response(status_code=204, headers=CORS)


@router.get("/{tenant}/profile")
def profile(tenant: str, full: bool = False):
    """센터 이름·봇 이름·예약 링크·FAQ 칩 6개 — 고객 상담봇 페이지가 첫 화면에 그린다(공개 · §3·§5).
    full=1 이면 faq[] 전체(id·q·a·alt·verified)도 같이 준다 — 관리자 페이지 FAQ 표가 이걸로 그린다(새 GET
    엔드포인트를 안 늘리려고 이 API 하나에 얹는다 · FAQ 는 원래 공개 콘텐츠라 로그인 없이 봐도 된다)."""
    if tenant not in TENANTS:
        raise HTTPException(404, "모르는 센터: %s" % tenant)
    prof = _load_profile(tenant)
    faq_data = _load_faq(tenant)
    faq = faq_data.get("faq") or []
    # q·a 를 같이 준다 — 고객 페이지가 칩을 FAQPage JSON-LD(AEO)에 그대로 심는다(질문만으론 근거 없는 답이 된다).
    chips = [{"q": it.get("q", ""), "a": it.get("a", ""), "verified": bool(it.get("verified"))}
             for it in sorted(faq, key=lambda it: not it.get("verified"))[:6] if it.get("q")]
    tenant_info, identity, channels, facts, meta = (prof.get("tenant") or {}, prof.get("identity") or {},
                                                     prof.get("channels") or {}, prof.get("facts") or {},
                                                     prof.get("meta") or {})
    name = tenant_info.get("name") or tenant
    persona = identity.get("counselor_persona") or {}

    def _v(x):
        # "미수령" 같은 자리표시자·빈 값은 고객 화면에 안 보낸다 — 있는 채널만 조용히 표시(검수 L4 원칙과 같은 방향).
        s = str(x or "").strip()
        return s if s and s != "미수령" else ""

    reservation_url = _v(channels.get("reservation_url")) or _v((faq_data.get("meta") or {}).get("reservation_url"))
    out = {
        "ok": True, "tenant": tenant, "name": name,
        # persona = 진짜 상담원처럼(배1036 GM · 시보 커밋 21bfe89f3) — name·greeting·handoff·typing_ms·emoji.
        # 미수령(스포짐)이면 이름은 테넌트 이름으로 폴백, 인사말 없음(고객 화면이 정중히 생략).
        "persona": {"name": persona.get("name") or name, "greeting": _v(persona.get("greeting")),
                    "handoff": _v(persona.get("handoff")), "typing_ms": persona.get("typing_ms") or 0,
                    "emoji": persona.get("emoji") or ""},
        "reservation_url": reservation_url if reservation_url.startswith("http") else "",
        "contact": {"phone": _v(facts.get("phone")), "kakao": _v(channels.get("kakao")),
                    "naver_place": _v(channels.get("naver_place"))},
        "status": meta.get("status") or "",
        "chips": chips, "faq_count": len(faq), "verified_count": sum(1 for it in faq if it.get("verified")),
    }
    if full:
        out["faq"] = faq
    return Response(json.dumps(out, ensure_ascii=False), media_type="application/json; charset=utf-8", headers=CORS)


def _selfcheck() -> None:
    assert _bigrams("운영시간") == {"운영", "영시", "시간"}
    item, score = _best_match("운영시간이 어떻게 되나요", [
        {"id": "q1", "q": "운영 시간은 어떻게 되나요?", "a": "평일 06:00~22:30"},
        {"id": "q2", "q": "위치가 어디인가요?", "a": "한남동"},
    ])
    assert item and item["id"] == "q1" and score >= MATCH_THRESHOLD, (item, score)
    item2, score2 = _best_match("전혀 상관없는 질문입니다", [{"id": "q1", "q": "운영 시간은?", "a": "x"}])
    assert score2 < MATCH_THRESHOLD
    assert _forbidden_hit("결제는 어떻게 하나요") is True
    assert _forbidden_hit("치료 효과가 있나요") is True
    assert _forbidden_hit("운영 시간이 궁금해요") is False
    assert _forbidden_hit("가격이 어떻게 되나요") is True   # 검수 L3 — 받는 질문 관문
    assert _mask_pii("010-1234-5678 로 연락 주세요") == "[전화번호] 로 연락 주세요"   # 검수 M5
    assert _mask_pii("문의는 abc@wellperion.com 으로") == "문의는 [이메일] 으로"

    # 배1018 후속 — FAQ 매칭 오답 수리(주차→정원제) 실사례. FAQ = 실제 tenant(1_wellperion) 14문답.
    faq = _load_faq("1_wellperion").get("faq") or []
    assert faq, "FAQ 없음 — /srv/erp/faq/1_wellperion/faq.json 확인"
    cases = [
        ("가입은 어떻게 하나요", "f03"),
        ("운영 시간이 어떻게 되나요", "f04"),
        ("주차 되나요", None),          # 정규화 길이 2자("주차") → 무조건 미매칭
        ("오늘 날씨", None),
        ("수영 강습 가격", None),       # 금지어 아님·FAQ 자체에 가격 문답 없음 → 정상 미매칭
        ("예약 없이 가도 되나요", "f01"),
    ]
    for q, expect_id in cases:
        m, s = _best_match(q, faq)
        got_id = m.get("id") if m else None
        assert got_id == expect_id, f"{q!r} 기대={expect_id} 실제={got_id}(score={s})"

    # 다캠(2_dietcamp) 실측 — 시보 요청 2건. "골프 레슨"은 FAQ 원문("골프 트레이닝")과 동의어라
    # item.alt 로 매칭 후보에 넣는다(d08 에 "alt": ["골프 레슨"] 필요 — 없으면 이 assert 로 바로 드러난다).
    dc_faq = _load_faq("2_dietcamp").get("faq") or []
    if not dc_faq:
        # seed_faq/2_dietcamp.json 은 아직 빈 콘텐츠(시보 콘텐츠 입력 전 자리표시자) — 검수 L4 는 로컬에서
        # api_chat.py 를 돌릴 수 있게 하는 게 목적이지 콘텐츠를 대신 지어내는 게 아니다. 콘텐츠가 채워지면
        # 이 매칭 검증이 그대로 발동한다(ponytail: 콘텐츠 입력 전까지는 이 두 케이스만 skip).
        print("api_chat selfcheck: 다캠 FAQ 콘텐츠 미입력 — d08/d09 매칭 점검 skip")
    else:
        for q, expect_id in [("골프 레슨도 하나요", "d08"), ("처음 가면 뭐 해요", "d09")]:
            m, s = _best_match(q, dc_faq)
            got_id = m.get("id") if m else None
            assert got_id == expect_id, f"{q!r} 기대={expect_id} 실제={got_id}(score={s})"
    # 배1036 관리자 API — 순수 로직 3종(비동기 없이).
    d = {"meta": {}, "faq": [{"id": "f01", "q": "old", "a": "old a"}]}
    it = _apply_faq_edit(d, {"q": "새 질문", "a": "새 답 010-1234-5678"})   # id 없음 → 추가
    assert it["id"] not in ("f01",) and len(d["faq"]) == 2, d
    it2 = _apply_faq_edit(d, {"id": "f01", "q": "old", "a": "고친 답", "verified": True})   # id 있음 → 수정
    assert it2["a"] == "고친 답" and it2["verified"] is True and len(d["faq"]) == 2, d
    try:
        _apply_faq_edit(d, {"q": "", "a": "x"})
        raise AssertionError("q 없이 통과하면 안 된다")
    except ValueError:
        pass
    assert _warn_words("결제는 상담 시 안내드려요") == ["결제"]
    assert _warn_words("평일 06:00~22:30 운영합니다") == []

    # 배1036 GM 구조전환 — L2 주 엔진(키 유무와 무관하게 결정적으로 검증).
    assert _is_hours_question("오늘 운영하나요") and _is_hours_question("지금 영업해요?")
    assert not _is_hours_question("가입은 어떻게 하나요")
    assert not _is_hours_question("오늘 저녁 메뉴 추천해 주세요")   # 시간말만 — 상태말 없음(실측 오발동 잡음)
    assert not _is_hours_question("운영 시간은 어떻게 되나요")     # 상태말만 — 일반 FAQ(f04) 몫, 가로채면 안 됨
    today_line = _today_hours_line("1_wellperion")
    assert today_line and ("휴관" in today_line), today_line   # 1_wellperion 은 facts.hours 있음 — 항상 한 줄 나온다
    assert _today_hours_line("2_dietcamp") == "", "다캠은 facts.hours 없음 — 빈 문자열이어야 핸드오프로 넘어간다"
    assert not _grounded("100원 할인해드려요", "이 문서엔 숫자가 전혀 없습니다")   # 근거 밖 숫자 → 탈락
    assert _grounded("06:00부터 22:30까지 운영해요", "평일 06:00~22:30 운영")      # 근거 안 숫자만 → 통과
    global _ANTHROPIC_CLIENT
    saved = _ANTHROPIC_CLIENT
    _ANTHROPIC_CLIENT = (None, True)   # 강제로 "키 없음(시도 완료)" 상태 — 폴백 경로 결정적 검증
    text, status = _concierge_answer("1_wellperion", "테스트 질문", "")
    assert text is None and status == "error", (text, status)
    _ANTHROPIC_CLIENT = saved

    # 배1036 GM 3중 가드 — ① 일일 한도(가짜 테넌트 키로 실 카운터 안 건드림).
    key_tenant = "__selfcheck__"
    for _ in range(DAILY_QUESTION_LIMIT):
        assert _over_daily_limit(key_tenant) is False
    assert _over_daily_limit(key_tenant) is True   # 301번째 — 한도 초과
    _DAILY_COUNTS.pop((key_tenant, _kst_now()[:10]), None)   # 자체점검 잔여 제거
    print("api_chat selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
