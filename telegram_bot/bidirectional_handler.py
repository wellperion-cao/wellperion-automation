"""
텔레그램 양방향 통신 핸들러 v1.0
GM님 메시지 수신 → 분류 → 자동 회신 + 인박스 적재

분류 로직 (Claude API 호출 없음, 순수 Python):
  1. 단순 응답 키워드 → 즉시 자동 회신 (인박스 적재 X)
  2. 결재 키워드 → 기존 route_approval 처리 (bot.py)
  3. 보고 피드백 패턴 → 인박스 적재 + "피드백 접수 완료" 회신
  4. 지시/질문 (기본값) → 인박스 적재 + "접수 완료" 회신

토큰 소비: 0 (Claude API/CLI 호출 없음)
"""
from __future__ import annotations

import re
import logging
from datetime import datetime

logger = logging.getLogger("bidirectional")

_SIMPLE_ACK_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(확인|ㅇㅇ|ㅇㅋ|오케이|ok|okay|넵|네|예|응|ㅇ|알겠|알겠습니다|확인했습니다|확인함)$", re.IGNORECASE),
     "접수 완료"),
    (re.compile(r"^(ㄴㄴ|아니|아니요|no|ㄴ|안됨|안돼|취소)$", re.IGNORECASE),
     "확인했습니다. 취소/반려 처리합니다."),
    (re.compile(r"^승인$"),
     "승인 확인했습니다."),
    (re.compile(r"^(안녕|하이|hi|hello|반가워|좋은\s*(아침|점심|저녁))$", re.IGNORECASE),
     "안녕하세요 GM님. 무엇을 도와드릴까요?"),
    (re.compile(r"^(살아\?|가동\?|상태\?|살아있어\?|작동\?)$", re.IGNORECASE),
     "정상 가동 중입니다."),
    (re.compile(r"^(수고|고마워|감사|ㄳ|ㄱㅅ|잘했어|좋아).*$", re.IGNORECASE),
     "감사합니다. 추가 지시사항 있으시면 말씀해 주세요."),
]

_FEEDBACK_PATTERNS: list[re.Pattern] = [
    re.compile(r"(보고|리포트|report).*?(대해|관련|에서|건)", re.IGNORECASE),
    re.compile(r"^(CMO|CFO|CTO|CPO|COO|CHRO|CEO)\s+", re.IGNORECASE),
    re.compile(r"(결과|산출물|진행|상황).*(피드백|의견|코멘트)", re.IGNORECASE),
    re.compile(r"^(피드백|코멘트|의견)[:\s]", re.IGNORECASE),
]


def classify_message(text: str) -> tuple[str, str]:
    """
메시지를 분류하여 (category, auto_reply) 반환.

Returns
-------
tuple[str, str]
    category: 'simple_ack' | 'feedback' | 'directive'
    auto_reply: 즉시 회신할 텍스트
"""
    stripped = text.strip()

    if not stripped:
        return ("simple_ack", "메시지가 비어 있습니다.")

    for pattern, reply in _SIMPLE_ACK_PATTERNS:
        if pattern.match(stripped):
            return ("simple_ack", reply)

    for pattern in _FEEDBACK_PATTERNS:
        if pattern.search(stripped):
            return ("feedback", "피드백 접수 완료. 해당 C-Level에게 전달합니다.")

    return ("directive", "접수 완료. 다음 CEO 세션에서 처리합니다.")


def build_inbox_title(text: str) -> str:
    """메시지 첫 20자 요약으로 인박스 제목 생성."""
    cleaned = text.strip().replace("\n", " ")
    if len(cleaned) <= 20:
        return cleaned
    return cleaned[:20] + "..."


def build_inbox_payload(text: str, category: str, inbox_db_id: str) -> dict:
    """
CEO 인박스 DB 적재용 Notion API payload 생성.

Properties:
  - 메시지(title): 전문
  - 채널: "텔레그램"
  - 보낸이: "GM님"
  - 처리상태: "미처리"
  - 수신시각: 현재 시각 ISO 8601
"""
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00")

    payload = {
        "parent": {"database_id": inbox_db_id},
        "properties": {
            "메시지": {"title": [{"text": {"content": text[:2000]}}]},
            "채널": {"select": {"name": "텔레그램"}},
            "보낸이": {"rich_text": [{"text": {"content": "GM님"}}]},
            "처리상태": {"select": {"name": "미처리"}},
            "수신시각": {"date": {"start": now_iso}},
        },
    }

    return payload


def push_to_inbox(text: str, category: str, notion_api_key: str, inbox_db_id: str) -> bool:
    """
CEO 인박스 DB에 레코드 생성.
단순 응답(simple_ack)은 적재하지 않음.

Returns
-------
bool
    성공 True, 스킵 또는 실패 False.
"""
    import urllib.request
    import urllib.error
    import json

    if category == "simple_ack":
        logger.debug("simple_ack 분류 — 인박스 적재 스킵")
        return False

    if not notion_api_key or not inbox_db_id:
        logger.warning("NOTION_API_KEY 또는 INBOX_DB_ID 미설정 — 인박스 적재 스킵")
        return False

    payload = build_inbox_payload(text, category, inbox_db_id)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=body,
        headers={
            "Authorization": "Bearer " + notion_api_key,
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
        page_id = result.get("id", "unknown")
        logger.info("인박스 적재 완료: page_id=%s category=%s", page_id, category)
        return True
    except urllib.error.HTTPError as exc:
        body_err = exc.read().decode(errors="replace")[:500]
        logger.error("인박스 Notion POST 오류 %d: %s", exc.code, body_err)
        return False
    except Exception as exc:
        logger.error("인박스 적재 예외: %s", exc)
        return False
