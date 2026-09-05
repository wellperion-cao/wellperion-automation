# -*- coding: utf-8 -*-
"""상담봇 백엔드 (배1018 시토 → 배1036 구조전환 · 모델 = cbo/model/상담봇_기획설계_v1.0.html §3-1·§3-2).

POST /api/chat/{tenant}            공개(로그인 없음) — 질문 1개 → 정본 학습형 컨시어지 모델(주 엔진) 또는
    FAQ 매칭(백업 · 키 없음·모델 오류·한도일 때만) → 답 또는 고정 문구('상담 예약').
GET  /api/chat/{tenant}/unanswered 관문 뒤(로그인) — 최근 N일 미답 질문 목록(시보가 아침 학습 회로로 읽는다).
PUT  /api/chat/{tenant}/faq · GET .../stats · POST .../feedback · GET .../profile — 배1036 관리자 API 4개.

주 엔진 = 업체 정본 11구역+FAQ+오늘 운영 상태를 시스템 프롬프트로 준 컨시어지 모델(스트리밍). 3단 전환(GM 확정):
  주(env COUNSEL_MODEL_PRIMARY 기본 opus-4-6) → 오류·첫 글자 3초 초과·한도(429)면 대체(FALLBACK 기본 sonnet-4-6)
  → 그래도 실패하면 백업(문장 겹침 매칭·모델 호출 0). 지어내기 차단은 프롬프트가 아니라 출력검사 코드
(_grounded·_forbidden_hit)가 한다. 클라이언트 자체가 없으면(키·Bedrock 둘 다 없음) 바로 백업(회귀 0).
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
import time
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
LOG_ROTATE_BYTES = 20 * 1024 * 1024   # 검수 M4 — 크기 넘으면 회전(삭제 아님 · 배1036 GM 추가② "테스트 데이터=자산")
UNANSWERED_TAIL_BYTES = 300 * 1024    # unanswered 는 전량 스캔 대신 로그 꼬리만 본다(검수 M4)
_PHONE_RE = re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(r"https?://\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|co\.kr|kr|net|org)(?:/\S*)?", re.I)
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
# 배1074 공통 학습층 — 컨셉 프리셋·공통 금지어·질문 유형(사실 값·개인정보 없음 · never_here). 서버 배포 경로가
# 없으면(로컬 자체점검) 저장소 상대경로로 폴백 — 그것도 없으면 빈 dict(서비스 안 죽게).
SHARED_DIR = os.environ.get(
    "ERP_COUNSELBOT_SHARED",
    "/srv/erp/counselbot/shared" if os.path.isdir("/srv/erp/counselbot/shared") else
    os.path.join(os.path.dirname(os.path.dirname(_HERE)), "server", "counselbot", "shared"))
FEEDBACK_LOG_PATH = os.environ.get("ERP_CHAT_FEEDBACK_LOG", "/srv/erp/chat_feedback.jsonl")
WARN_WORDS = tuple(MONEY_WORDS) + MEDICAL_WORDS + PRICE_QUESTION_WORDS   # 관리자 저장 시 경고(막지 않음) — 배1036 요청⑤
# close_days.json 정본 = 저장소 status/(공휴일 목록도 여기) — 서버는 /srv/erp/www 가 git 5분 동기화라 그 경로를
# 그대로 읽는다(별도 배포 불필요). 로컬 자체점검은 저장소 상대경로로 폴백.
CLOSE_DAYS_PATH = os.environ.get(
    "ERP_CLOSE_DAYS",
    "/srv/erp/www/status/close_days.json" if os.path.isdir("/srv/erp/www") else
    os.path.join(os.path.dirname(os.path.dirname(_HERE)), "status", "close_days.json"))
# 주 모델 = Opus 4.6(GM 확정 "성능 좋은 걸로") · 대체 = Sonnet 4.6(주 모델 오류·첫 글자 3초 초과·한도 시 자동).
# 옛 COUNSEL_MODEL 은 PRIMARY 별칭(하위호환) — 새 배포는 PRIMARY/FALLBACK 두 이름을 쓴다.
COUNSEL_MODEL_PRIMARY = os.environ.get("COUNSEL_MODEL_PRIMARY") or os.environ.get("COUNSEL_MODEL") or "global.anthropic.claude-opus-4-6-v1"
COUNSEL_MODEL_FALLBACK = os.environ.get("COUNSEL_MODEL_FALLBACK", "global.anthropic.claude-sonnet-4-6")
COUNSEL_MODEL = COUNSEL_MODEL_PRIMARY   # 하위호환 별칭
FIRST_CHAR_TIMEOUT_S = 3.0   # 주 모델 첫 글자가 이 안에 안 오면 대체로 전환
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


def _load_shared(name: str) -> dict:
    """배1074 — server/counselbot/shared/{name} 읽기. 없으면 빈 dict(서비스 안 죽게)."""
    try:
        return json.loads((Path(SHARED_DIR) / name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


_ACCOUNT_NUM_RE = re.compile(r"\d{2,6}-\d{2,6}(?:-\d{2,6})?")   # guards_common '-' 항목 = 계좌번호형 패턴(배1074②)


def _common_guard_phrases() -> list:
    return [p for rule in _load_shared("guards_common.json").get("rules", [])
            for p in (rule.get("phrases") or []) if p != "-"]


def _forbidden_hit(q: str, tenant: str = None) -> bool:
    """질문 관문 — 공통 금지 phrases(guards_common.json 전부) + 테넌트 추가 phrases(guards.phrases · 배1074②)
    + 계좌번호형 패턴 + 의료 안전목록(MEDICAL_WORDS · guards_common 이 아직 다 못 덮어 유지). 가격·계약 같은
    낱말 자체는 더 안 막는다 — 이제 컨시어지 모델이 세일즈 원칙③(숫자 아님)으로 안전하게 다루고, 지어낸
    숫자·확정 문구는 출력검사(_grounded·_output_unsafe)가 뒷단에서 잡는다."""
    q = q or ""
    if _ACCOUNT_NUM_RE.search(q):
        return True
    phrases = _common_guard_phrases()
    if tenant:
        phrases = phrases + ((_load_profile(tenant).get("guards") or {}).get("phrases") or [])
    return any(w in q for w in phrases) or any(w in q for w in MEDICAL_WORDS)


# 모델 답(출력) 전용 위험 검사 — 질문 관문(_forbidden_hit)과 다르다. 실측(시보): "환불 되나요"에 대한
# 안전한 미루기 답("계약 조건은 담당자가 안내드립니다")이 MONEY_WORDS 의 "계약"에 걸려 핸드오프로 잘못
# 떨어졌다 — 근본 원인은 _grounded 가 아니라 이 함수(질문용 낱말을 답에도 그대로 썼다)였다. 답에서는
# 확정형 약속 문구(가격 숫자를 실제로 부르거나 "무료로/할인해" 약속)만 막는다 — 낱말 자체 언급은 안 막는다.
OUTPUT_UNSAFE_WORDS = ("원 드리", "원에 드리", "할인해", "무료로 드리")


def _output_unsafe(text: str) -> bool:
    return any(w in text for w in MEDICAL_WORDS) or any(w in text for w in OUTPUT_UNSAFE_WORDS)


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


def _match_question_type(q: str):
    """공통 질문 유형 매칭(배1074③) — FAQ 매칭(_best_match)과 같은 2-gram 겹침 방식이되, 교집합 최소 1개로
    완화했다(유형 태깅은 답 선택과 달리 오분류 비용이 낮다 · _best_match 의 2자 이하 통짜 차단은 "주차 되나요"
    처럼 정규화하면 2자로 줄어드는 흔한 질문까지 막아서 그대로는 못 썼다). 반환 = type_id|None."""
    types = _load_shared("question_types.json").get("types", [])
    nq = _normalize_q(q)
    qb = _bigrams(nq)
    if not qb:
        return None
    best_id, best_score = None, 0.0
    for t in types:
        for ex in (t.get("examples") or []):
            fb = _bigrams(_normalize_q(ex))
            if not fb or not (qb & fb):
                continue
            score = len(qb & fb) / min(len(qb), len(fb))
            if score >= 0.5 and score > best_score:
                best_id, best_score = t.get("type_id"), score
    return best_id


def _fact_present(prof: dict, path: str) -> bool:
    """needs_facts 표기(facts.hours · offerings[].price_policy · policies[topic=환불] 등)가 채워졌는지 본다.
    배열·topic 필터 표기는 대충(그 구역에 하나라도 있으면 있다고 봄) · 단순 점(.) 경로는 그 칸까지 실제로
    내려가서 본다 — 처음엔 최상위 구역만 봐서 "_note"·"_source" 같은 메타 문구 때문에 옆 칸(예: parking)이
    비었는데도 '있다'고 오판했다(실측으로 잡음 · 배1074③)."""
    if "[topic=" in path:
        base, rest = path.split("[topic=", 1)
        topic = rest.rstrip("]")
        items = (prof or {}).get(base) or []
        return any(topic in (it.get("topic") or "") for it in items)
    if "[]" in path:
        items = (prof or {}).get(path.split("[", 1)[0]) or []
        return bool(items)
    node = prof or {}
    for part in path.split("."):
        if not isinstance(node, dict):
            return False
        node = node.get(part)
    if isinstance(node, dict):
        return any(v not in (None, "", "미수령", []) for k, v in node.items() if not k.startswith("_"))
    return node not in (None, "", "미수령")


def _needs_facts_missing(prof: dict, type_id: str) -> list:
    """type_id 가 답하는 데 필요한 정본 칸 중 비어 있는 것만(배1074③) — 미답 목록에 같이 기록된다."""
    if not type_id:
        return []
    types = _load_shared("question_types.json").get("types", [])
    t = next((x for x in types if x.get("type_id") == type_id), None)
    if not t:
        return []
    return [p for p in (t.get("needs_facts") or []) if not _fact_present(prof, p)]


def _mask_pii(q: str) -> str:
    """로그에 남기기 전 전화번호·이메일 마스킹(검수 M5) — 상담 문의는 대개 "010-...로 연락 주세요" 형태로 온다."""
    return _EMAIL_RE.sub("[이메일]", _PHONE_RE.sub("[전화번호]", q or ""))


def _rotate_log_keep(path: str) -> None:
    """크기 넘으면 타임스탬프 이름으로 옮겨 보관 — 삭제 0(GM "테스트 데이터=자산" · 배1036 GM 추가②).
    옛 방식(고정 ".1")은 두 번째 회전에서 그 파일을 덮어써 사실상 삭제였다 — 매번 새 이름이라 안 겹친다."""
    if os.path.exists(path) and os.path.getsize(path) > LOG_ROTATE_BYTES:
        stamp = _kst_now().replace("-", "").replace(":", "").replace("T", "")
        os.replace(path, path + "." + stamp)


def _log(tenant: str, q: str, answered: bool, faq_id, type_id: str = None, needs_facts: list = None):
    row = {"ts": _kst_now(), "tenant": tenant, "q": _mask_pii(q), "answered": answered, "faq_id": faq_id}
    if type_id:
        row["type_id"] = type_id   # 배1074③ — 공통 질문 유형 태깅
    if needs_facts:
        row["needs_facts"] = needs_facts   # 배1074③ — 못 답한 이유(어느 정본 칸이 비었나)
    try:
        os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
        _rotate_log_keep(LOG_PATH)
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
    type_id = _match_question_type(q) if q else None   # 배1074③ — 공통 질문 유형 태깅(사실 값·개인정보 없음)
    # 못 답했든 모델이 둘러 답했든 "이 유형에 필요한 정본 칸이 비었다"는 신호는 똑같이 값지다(돈 버는 층) —
    # 답변 성공 여부와 상관없이 항상 같이 기록한다(배1074③).
    missing = _needs_facts_missing(_load_profile(tenant), type_id) if type_id else []

    if not q or _forbidden_hit(q, tenant):
        _log(tenant, q, False, None, type_id, missing)
        out = {"ok": True, "answered": False, "answer": fallback, "faq_id": None, "tenant": tenant}
        return Response(json.dumps(out, ensure_ascii=False), media_type="application/json; charset=utf-8", headers=CORS)

    # 주 엔진(배1036 GM 구조전환) — 정본 학습형 컨시어지 모델. 실패/키없음/일일한도 = "error"(레거시 매칭 백업으로).
    text, status = (None, "error") if _over_daily_limit(tenant) else _concierge_answer(tenant, q, session_id)
    if status == "ok":
        _log(tenant, q, True, None, type_id, missing)
        out = {"ok": True, "answered": True, "answer": text, "faq_id": None, "tenant": tenant}
    elif status == "invalid":
        # 모델은 답했지만 출력검사 탈락(금지어·근거밖 숫자) — 레거시로 재시도하지 않고 바로 핸드오프(§3-1④).
        _log(tenant, q, False, None, type_id, missing)   # ⑤ 핸드오프 = 미답 기록(관리자 페이지·아침 회로가 읽는다)
        out = {"ok": True, "answered": False, "answer": fallback, "faq_id": None, "tenant": tenant}
    else:
        # 백업(§3-1⑥) — 키 없음·모델 오류·한도(429) 때만. 오늘 운영 질문은 모델 없이도 코드로 바로 답한다(배1036 GM⑥).
        today_line = _today_hours_line(tenant)
        if today_line and _is_hours_question(q):
            _log(tenant, q, True, "today_hours", type_id, missing)
            out = {"ok": True, "answered": True, "answer": today_line, "faq_id": "today_hours", "tenant": tenant}
        else:
            item, score = _best_match(q, data.get("faq") or [])
            if item and score >= MATCH_THRESHOLD:
                _log(tenant, q, True, item.get("id"), type_id, missing)
                out = {"ok": True, "answered": True, "answer": item.get("a", ""), "faq_id": item.get("id"), "tenant": tenant}
            else:
                _log(tenant, q, False, None, type_id, missing)
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
                    item = {"q": row.get("q", ""), "ts": row.get("ts", "")}
                    if row.get("type_id"):
                        item["type_id"] = row["type_id"]   # 배1074③
                    if row.get("needs_facts"):
                        item["needs_facts"] = row["needs_facts"]   # 배1074③ — 어느 정본 칸이 비었나
                    out.append(item)
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
        _rotate_log_keep(FEEDBACK_LOG_PATH)
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
    """모델 출력에 근거(정본)에 없는 숫자가 새로 등장하면 False(배1036 GM① 근거 밖 숫자 차단).
    URL·이메일·전화는 먼저 지운다(식별자 숫자는 비교 대상 아님) · 앞자리 0 은 없는 셈 치고 비교한다
    ("08:00"의 08 과 자연어 "8시"의 8 을 같은 숫자로 봄 — 시각·날짜 표기 차이 오탐 수리, 시보 실측)."""
    def _nums(s: str) -> set:
        s = _URL_RE.sub("", s or "")
        s = _EMAIL_RE.sub("", s)
        s = _PHONE_RE.sub("", s)
        return {n.lstrip("0") or "0" for n in _DIGITS_RE.findall(s)}
    return _nums(text).issubset(_nums(source))


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
    "6)마무리도 사람처럼(자연스러운 다음 제안) 7)업체 톤 위에 컨시어지를 얹는다. "
    "그 위에 세일즈 원칙 5도 지킵니다 — "
    "1)목적을 한 번 되묻는다(질문 하나로 니즈를 잡는다·설문처럼 여러 개 안 묻는다) "
    "2)정본 안의 상품 하나를 콕 짚는다(정본에 없는 상품·효과는 지어내지 않는다) "
    "3)가치 한 줄로 말하되 숫자는 아니다(가격·할인·보장은 절대 말하지 않는다) "
    "4)부드러운 다음 행동으로 잇는다(체험·예약·방문 제안 · '지금 아니면'·'마감 임박' 같은 압박 문구 금지) "
    "5)거절·망설임엔 대안을 하나 준다(같은 제안을 반복하거나 재촉하지 않는다)."
)   # 설계 §3-2 원칙 7 + §3-3 세일즈 5원칙 그대로


def _concept_preset(prof: dict) -> dict:
    """identity.concept_preset 로 고른 프리셋 1개(배1074① · 없으면 빈 dict — persona 값만 쓴다).
    persona(counselor_persona)가 프리셋보다 우선(schema.md "네 가지가 안 맞으면 직접 적는다")."""
    preset_id = (prof.get("identity") or {}).get("concept_preset")
    if not preset_id:
        return {}
    presets = _load_shared("concept_presets.json").get("presets", [])
    return next((p for p in presets if p.get("id") == preset_id), {}) or {}


def _shared_prompt_sections() -> str:
    """배1074 공통 학습층 — guards_common(전부)·question_types(전부)를 프롬프트에 얹는다. 사실 값·개인정보는
    여기 없다(never_here) — 규칙 문장·유형·답 뼈대뿐. 파일이 없으면(폴백) 빈 문자열."""
    parts = []
    guards = _load_shared("guards_common.json").get("rules", [])
    if guards:
        lines = ["- %s → \"%s\"" % (g.get("rule", ""), g.get("say_instead", "")) for g in guards]
        parts.append("[공통 금지 규칙]\n" + "\n".join(lines))
    qtypes = _load_shared("question_types.json").get("types", [])
    if qtypes:
        lines = ["- %s: %s" % (t.get("type_id", ""), t.get("answer_skeleton", "")) for t in qtypes]
        parts.append("[질문 유형 답 뼈대 — {facts.*} 는 위 업체 정본 값으로 채운다]\n" + "\n".join(lines))
    return ("\n\n" + "\n\n".join(parts)) if parts else ""


def _concierge_system_block(tenant: str, prof: dict, persona: dict) -> str:
    """system 프롬프트 = 업체 정본 11구역 전부 + FAQ 전체 + 오늘 상태 한 줄(배1036 GM 구조전환①·설계 §3-1①·⑦)
    + 공통 학습층 3파일(배1074). cache_control 로 캐싱 — 정본이 바뀌기 전까진 매 질문 동일해 재사용된다."""
    faq = _load_faq(tenant).get("faq") or []
    faq_lines = "\n".join("- id=%s Q:%s A:%s" % (it.get("id"), it.get("q", ""), it.get("a", "")) for it in faq)
    preset = _concept_preset(prof)
    name = persona.get("name") or preset.get("name") or tenant
    tone = persona.get("emoji") or preset.get("emoji") or "적당히"
    handoff = persona.get("handoff") or preset.get("handoff") or "그 부분은 제가 확인해서 알려드릴게요 🙏 상담 예약을 남겨 주시면 연락드립니다."
    preset_line = (" 컨셉은 '%s'(%s)." % (preset.get("name"), preset.get("one_liner"))) if preset else ""
    service_concept = (prof.get("identity") or {}).get("service_concept") or ""
    sales_style = (prof.get("identity") or {}).get("sales_style") or ""   # null(스포짐)이면 생략(배1036 GM 추가①)
    sales_line = (" 세일즈 결(업체별) — %s" % sales_style) if sales_style else ""
    today_line = _today_hours_line(tenant)
    return (
        "%s 당신은 '%s' 상담원입니다(%s).%s%s 이모지는 '%s' 수준으로 씁니다. "
        "아래 [업체 정본]·[FAQ]에 적힌 사실·상품·규정만 사실로 말하세요 — 없는 것은 지어내지 말고 "
        "\"%s\" 라고 답하세요. 금액 숫자·의료 판단은 말하지 않습니다. "
        "질문이 영어면 영어로, 한국어면 한국어로 답하세요. 답변 문장만 출력하세요(설명·따옴표 없이). "
        "이 화면은 카카오톡 대화창처럼 평문만 보입니다 — 마크다운 금지(**굵게**·목록 기호·제목 기호 쓰지 않는다).\n\n"
        "[오늘] %s\n\n[업체 정본]\n%s\n\n[FAQ]\n%s%s"
        % (_CONCIERGE_PRINCIPLES, name, service_concept, preset_line, sales_line, tone, handoff, today_line or "미확인",
           json.dumps(prof, ensure_ascii=False), faq_lines, _shared_prompt_sections())
    )


def _stream_once(client, model: str, system: list, messages: list, read_timeout: float = None):
    """스트리밍 1회 호출(설계 §3-1② "속시원함" · GM 확정 스트리밍 필수) — 첫 글자까지 걸린 시간을 반환한다.
    read_timeout 을 주면 청크 사이 대기(사실상 첫 글자 대기 포함)가 그 초를 넘길 때 타임아웃 예외를 던진다
    (SDK/httpx 표준 기능 재사용 — 직접 스레드·타이머 안 짠다)."""
    call_client = client
    if read_timeout:
        from anthropic import Timeout
        call_client = client.with_options(timeout=Timeout(60.0, read=read_timeout, write=30.0, connect=5.0))
    t0 = time.time()
    first_char_t = None
    chunks = []
    with call_client.messages.stream(model=model, max_tokens=500, system=system, messages=messages) as stream:
        for text in stream.text_stream:
            if first_char_t is None:
                first_char_t = time.time()
            chunks.append(text)
    return "".join(chunks), (round(first_char_t - t0, 2) if first_char_t else None)


def _concierge_answer(tenant: str, q: str, session_id: str):
    """정본 학습형 주 엔진(배1036 GM 구조전환 · 설계 §3-1·§3-2) — 반환 (답|None, status).
    status: 'ok'(그대로 응답) · 'invalid'(출력검사 탈락 → 호출부가 핸드오프) ·
    'error'(키 없음·모델 오류·한도 → 호출부가 레거시 FAQ 매칭 백업으로 · §3-1⑥).
    주 모델(Opus 4.6) 오류·첫 글자 3초 초과·한도(429)면 대체(Sonnet 4.6)로 자동 전환한다 — 둘 다
    실패해야 비로소 백업(문장겹침 매칭)으로 내려간다(GM 확정 3단 — 이 함수가 위 두 단만 맡는다)."""
    client = _anthropic_client()
    if not client:
        return None, "error"
    persona = _persona_of(tenant)
    prof = _load_profile(tenant)
    system_text = _concierge_system_block(tenant, prof, persona)
    system = [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}]
    lang_hint = " (질문이 영어이니 영어로 답하세요)" if _is_english_q(q) else ""
    messages = _session_history(session_id) + [{"role": "user", "content": q + lang_hint}]

    text = None
    for model, timeout in ((COUNSEL_MODEL_PRIMARY, FIRST_CHAR_TIMEOUT_S), (COUNSEL_MODEL_FALLBACK, None)):
        try:
            text, first_char_s = _stream_once(client, model, system, messages, read_timeout=timeout)
            print("[concierge] tenant=%s model=%s first_char_s=%s" % (tenant, model, first_char_s), flush=True)
            break
        except Exception as e:
            print("[concierge] tenant=%s model=%s FAILED %s: %s"
                  % (tenant, model, type(e).__name__, str(e)[:200]), flush=True)
            if model == COUNSEL_MODEL_FALLBACK:
                # 주·대체 둘 다 실패 — Bedrock 쪽 문제일 가능성이 커서 알린다(하루 1회).
                _tg_alert_bedrock_once("⚠️ 상담봇 주엔진·대체 모두 실패 — FAQ 백업으로 전환 중. %s: %s"
                                        % (type(e).__name__, str(e)[:200]))
    if text is None:
        return None, "error"
    if not text or _output_unsafe(text) or not _grounded(text, system_text):
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
    # 배1074② 이후 — 가격·계약 낱말 자체는 더 안 막는다(모델이 세일즈③으로 안전하게 다룸 · 출력검사가 뒷단).
    assert _forbidden_hit("치료 효과가 있나요") is True   # 의료는 그대로 막음(MEDICAL_WORDS 유지)
    assert _forbidden_hit("운영 시간이 궁금해요") is False
    assert _forbidden_hit("결제는 어떻게 하나요") is False   # 구 동작(가격 낱말 차단)에서 의도적으로 바뀜
    assert _forbidden_hit("가격이 어떻게 되나요") is False
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

    # 배1036 GM 추가② — 로그 회전은 삭제가 아니라 보관(타임스탬프 이름 · 옛 고정 ".1"은 두 번째 회전에서 덮어써 삭제였다).
    import tempfile
    tmp_dir = tempfile.mkdtemp()
    tmp_log = os.path.join(tmp_dir, "t.jsonl")
    with open(tmp_log, "w", encoding="utf-8") as f:
        f.write("x" * (LOG_ROTATE_BYTES + 1))
    _rotate_log_keep(tmp_log)
    _rotate_log_keep(tmp_log)   # 파일이 사라져 두 번째는 아무 일도 안 함(존재 검사 통과 못 함) — 회전 파일 보존 확인
    rotated = [f for f in os.listdir(tmp_dir) if f != "t.jsonl"]
    assert len(rotated) == 1, rotated   # 회전분 1개가 안 지워지고 그대로 있어야 한다
    assert not os.path.exists(tmp_log)   # 원본은 회전돼 이름이 바뀌었다(새 글은 여기 다시 생김 · _log 가 open("a") 로 새로 만든다)

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

    # 배1036 시보 오탐 신고 수리 — "환불 되나요"에 대한 안전한 미루기 답이 잘못 핸드오프로 떨어진 건 원인이
    # _grounded 가 아니라 _forbidden_hit(질문용 낱말을 답에도 그대로 씀)였다(재현 확인). 실제 로그 원문으로 검증.
    real_answer = ("안녕하세요 🙂 웰페리온 멤버십 상담실입니다. 오늘은 저희가 정상 운영하는 날이에요(주말 08:00~20:00).\n\n"
                   "환불 관련 규정은 상담 시 정확히 안내드리는 부분이라, 제가 이 자리에서 단정해 드리기보다 확인해서 "
                   "정확히 안내드릴게요 🙏 문의 페이지(wellperion.com/ko/inquiry)에 상담 예약을 남겨 주시면 담당자가 "
                   "환불·계약 조건을 자세히 도와드립니다. 혹시 더 궁금한 점 있으실까요?")
    assert _output_unsafe(real_answer) is False, "안전한 미루기 답인데 '계약' 낱말만으로 막히면 안 된다"
    real_system = _concierge_system_block("1_wellperion", _load_profile("1_wellperion"), _persona_of("1_wellperion"))
    assert _grounded(real_answer, real_system) is True
    # 회귀 — 진짜 위험한 확정 문구·지어낸 숫자는 여전히 막힌다.
    assert _output_unsafe("치료 효과가 확실히 있어요") is True
    assert _output_unsafe("이번 달만 특별히 할인해 드릴게요") is True
    assert not _grounded("월 15만원이에요", "정본 안에 이 금액은 없습니다")
    assert _grounded("오전 8시부터 오후 8시까지예요", "평일 08:00~20:00 운영")   # 앞자리 0 표기차 오탐 수리
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

    # 배1074 — 공통 학습층 3파일 배선.
    assert _load_shared("guards_common.json").get("rules"), "shared/guards_common.json 못 읽음"
    assert _load_shared("존재안함.json") == {}, "없는 파일은 빈 dict 로 폴백해야 서비스가 안 죽는다"
    assert _forbidden_hit("완치가 되나요") is True    # 공통 금지어(no_medical phrases)
    assert _forbidden_hit("계좌번호 123-456-7890 로 입금") is True   # '-' 항목 = 계좌번호형 정규식
    assert _forbidden_hit("아무 문제 없는 질문입니다") is False
    d_with_extra = {"guards": {"phrases": ["업체전용금지어"]}}
    import unittest.mock as _mock
    with _mock.patch.object(sys.modules[__name__], "_load_profile", return_value=d_with_extra):
        assert _forbidden_hit("업체전용금지어 테스트", "1_wellperion") is True   # 테넌트 추가 phrases 합집합
    assert _match_question_type("주차 되나요") == "parking"
    assert _match_question_type("환불 되나요") == "refund"
    assert _match_question_type("아무 상관없는 문장입니다") is None
    assert _fact_present({"facts": {"hours": {"weekday": "06:00~22:30"}}}, "facts.hours") is True
    assert _fact_present({"facts": {"hours": None}}, "facts.hours") is False
    assert _needs_facts_missing({"facts": {}}, "parking") == ["facts.parking"]
    assert _needs_facts_missing({"facts": {"parking": "무료 30대"}}, "parking") == []
    # 실측으로 잡은 버그 — "_note" 처럼 밑줄로 시작하는 메타 칸이 옆의 진짜 빈 칸(parking)을 가리면 안 된다.
    assert _fact_present({"facts": {"parking": None, "_note": "미수령 — 안내 문구"}}, "facts.parking") is False
    real_dc = _load_profile("2_dietcamp")
    assert _needs_facts_missing(real_dc, "parking") == ["facts.parking"], "다캠 facts.parking 은 null 이어야 함"
    print("api_chat selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
