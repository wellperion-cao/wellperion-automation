# -*- coding: utf-8 -*-
"""AEO 채팅봇 백엔드 (배1018 · 2026-09-05 시토 · 모델 = cbo/model/aeo_chatbot_v0.1.html §4).

POST /api/chat/{tenant}            공개(로그인 없음) — 질문 1개 → FAQ 근거 답 또는 고정 문구('상담 예약').
GET  /api/chat/{tenant}/unanswered 관문 뒤(로그인) — 최근 N일 미답 질문 목록(시보가 아침 학습 회로로 읽는다).

모델 호출 없음 — 지어내기 원천 차단은 코드로(매칭 실패=고정 문구), 프롬프트가 아니다.
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
    data = _load_faq(tenant)
    fallback = _fallback_text(tenant, data.get("meta"))
    if not q or _forbidden_hit(q):
        _log(tenant, q, False, None)
        out = {"ok": True, "answered": False, "answer": fallback, "faq_id": None, "tenant": tenant}
    else:
        item, score = _best_match(q, data.get("faq") or [])
        if item and score >= MATCH_THRESHOLD:
            _log(tenant, q, True, item.get("id"))
            answer = _natural_answer(tenant, q, item)   # ANTHROPIC_API_KEY 없으면 item['a'] 그대로(회귀 0 · 배1036 GM③)
            out = {"ok": True, "answered": True, "answer": answer, "faq_id": item.get("id"), "tenant": tenant}
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


# ── 배1036 GM 추가 지시(2026-09-05) — 자연문 재작성 계층(L2) ─────────────────────────────
# ①FAQ 문장 그대로가 아니라 진짜 상담원처럼 말하기 ②질문이 영어면 영어로 ③서버에 ANTHROPIC_API_KEY 가
# 없으면 이 계층 전체를 건너뛰고 item['a'] 그대로(회귀 0 — 지금 서버엔 키가 없다·GM 결재 뒤 시토가 넣는다).
_ANTHROPIC_CLIENT = (None, False)   # (client|None, tried) — 최초 1회만 만들고 재사용(요청마다 새 client 금지)
_DIGITS_RE = re.compile(r"\d+")


def _anthropic_client():
    global _ANTHROPIC_CLIENT
    client, tried = _ANTHROPIC_CLIENT
    if tried:
        return client
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic()
        except ImportError:
            client = None   # ponytail: SDK 미설치 — 키가 와도 이 계층은 그냥 스킵(회귀 0 유지)
    _ANTHROPIC_CLIENT = (client, True)
    return client


def _is_english_q(q: str) -> bool:
    """한글이 하나도 없고 영문자가 있으면 영어 질문으로 본다(1차 한·영만 · 배1036 GM②)."""
    return not re.search(r"[가-힣]", q or "") and bool(re.search(r"[A-Za-z]", q or ""))


def _grounded(text: str, source: str) -> bool:
    """모델 출력에 근거(FAQ 원문)에 없는 숫자가 새로 등장하면 False(배1036 GM① 근거 밖 숫자 차단)."""
    src_nums = set(_DIGITS_RE.findall(source or ""))
    return all(n in src_nums for n in _DIGITS_RE.findall(text or ""))


def _faq_system_block(tenant: str, persona: dict, faq: list) -> str:
    """system 프롬프트 — 테넌트 FAQ 전체(질문마다 안 바뀌는 내용)를 담아 prompt caching 이 먹게 한다(배1036 GM①).
    실제로 어느 FAQ 를 근거로 쓸지는 매 요청 user 메시지의 [근거 FAQ id] 로 지정한다(엉뚱한 근거 차단)."""
    name = persona.get("name") or (tenant + " 상담")
    tone = persona.get("emoji") or "적당히"
    lines = ["- id=%s Q:%s A:%s" % (it.get("id"), it.get("q", ""), it.get("a", "")) for it in faq]
    return ("당신은 '%s' 상담원입니다. 손님에게 짧고 자연스럽게, 진짜 상담원처럼 답합니다(FAQ 문장을 그대로 읽지 않는다). "
            "이모지는 '%s' 수준으로 씁니다. 아래 [FAQ 전체]가 유일한 근거입니다 — 여기 없는 숫자·사실은 만들지 않습니다. "
            "매 요청에서 지정된 FAQ id 하나만 근거로 답하고, 다른 항목은 어투 참고만 합니다.\n\n[FAQ 전체]\n%s"
            % (name, tone, "\n".join(lines)))


def _natural_answer(tenant: str, q: str, item: dict) -> str:
    """FAQ 원문을 상담원 목소리로 재작성 — client 없으면(키 없음) 즉시 원문 그대로. 실패·금지어·근거 밖
    숫자는 전부 원문으로 안전하게 떨어진다(모델 호출이 답을 더 나쁘게 만들 수는 있어도 틀리게 만들진 못한다)."""
    base = item.get("a", "")
    client = _anthropic_client()
    if not client:
        return base
    persona = _persona_of(tenant)
    faq = _load_faq(tenant).get("faq") or []
    system = _faq_system_block(tenant, persona, faq)
    lang_hint = "질문이 영어이니 영어로 답하세요." if _is_english_q(q) else "한국어로 답하세요."
    user = "[근거 FAQ id: %s] 손님 질문: %s\n%s 답변 문장만 출력하세요(설명·따옴표 없이)." % (item.get("id"), q, lang_hint)
    try:
        resp = client.messages.create(
            model="claude-sonnet-5", max_tokens=400,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception:
        return base
    if not text or _forbidden_hit(text) or not _grounded(text, base):
        return base
    return text


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
    print("api_chat selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
