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
로그 = /srv/erp/chat_log.jsonl 한 줄(시각·tenant·질문·매칭 여부·faq_id) — 이름·전화 저장 안 함.
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

TENANTS = {"1_wellperion", "2_dietcamp"}
FAQ_DIR = os.environ.get("ERP_FAQ_DIR", "/srv/erp/faq")
LOG_PATH = os.environ.get("ERP_CHAT_LOG", "/srv/erp/chat_log.jsonl")
MATCH_THRESHOLD = 0.45   # ponytail: overlap coefficient 고정값 — 다캠 첫 달 실측 뒤 조정(모델 문서 §6)
# 다캠 에이전트엔 없던 의료 관문 — 최소 목록(늘어나면 이 튜플만 고친다)
MEDICAL_WORDS = ("진단", "처방", "치료", "질환", "질병", "의약", "부작용", "수술", "임신", "약물", "합병증")
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"}


def _kst_now() -> str:
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%dT%H:%M:%S")


def _bigrams(s: str) -> set:
    """한글 2-gram(글자 단위) — 한글·영문·숫자만 남기고 공백·기호는 버린다."""
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s or "")
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _load_faq(tenant: str) -> dict:
    path = Path(FAQ_DIR) / tenant / "faq.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"meta": {}, "faq": []}
    data.setdefault("meta", {})
    data.setdefault("faq", [])
    return data


def _forbidden_hit(q: str) -> bool:
    return any(w in q for w in MONEY_WORDS) or any(w in q for w in MEDICAL_WORDS)


def _best_match(q: str, faq: list):
    """(faq_item|None, score) — overlap coefficient(짧은 쪽 bigram 수 기준)."""
    qb = _bigrams(q)
    if not qb:
        return None, 0.0
    best, best_score = None, 0.0
    for item in faq:
        fb = _bigrams(item.get("q", ""))
        if not fb:
            continue
        score = len(qb & fb) / min(len(qb), len(fb))
        if score > best_score:
            best, best_score = item, score
    return best, best_score


def _fallback_text(meta: dict) -> str:
    url = (meta or {}).get("reservation_url") or ""
    base = "정확한 안내를 위해 상담 예약을 도와드릴게요."
    return f"{base} 예약: {url}" if url else base


def _log(tenant: str, q: str, answered: bool, faq_id):
    row = {"ts": _kst_now(), "tenant": tenant, "q": q, "answered": answered, "faq_id": faq_id}
    try:
        os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
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
    fallback = _fallback_text(data.get("meta"))
    if not q or _forbidden_hit(q):
        _log(tenant, q, False, None)
        out = {"ok": True, "answered": False, "answer": fallback, "faq_id": None, "tenant": tenant}
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
        with open(LOG_PATH, encoding="utf-8") as f:
            for line in f:
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
    print("api_chat selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
