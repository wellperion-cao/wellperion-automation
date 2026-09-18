# -*- coding: utf-8 -*-
"""AI 비서(회의 요약) — 배 12764 · 2026-09-18 시보.

erp/admin/meeting_note.html 이 브라우저 받아쓰기(제목+녹취록)를 보내면 회의 요약 5줄 + 업무 SSOT
행 초안(제목·내용·담당자 후보·기한 후보)을 JSON 으로 돌려준다. SSOT 행 저장은 이 API 가 하지 않는다
— 화면이 erpTodoCall(todo_add) 로 직접 올린다(그래야 GM 세션이 생성자가 된다).

모델 호출 = api_chat.py 의 Bedrock 클라이언트를 그대로 재사용(새 클라이언트 금지) · 모델은 그 파일의
대체(Sonnet 계열) 상수 COUNSEL_MODEL_FALLBACK 그대로 — 요약은 판단이 아니라 정리 작업이라 가벼운 모델.

자체점검: python api_meeting.py --selftest (네트워크 없음 · JSON 파싱만 검사)
"""
import json
import re
import sys

from fastapi import APIRouter

import api_chat

router = APIRouter(prefix="/api/meeting")

MAX_TRANSCRIPT_CHARS = 20000

_SYSTEM_PROMPT = """너는 회의록 요약 비서다. 입력된 회의 제목과 받아쓴 녹취록을 읽고
반드시 아래 모양의 JSON 객체 하나만 출력한다(설명·코드블록·다른 글자 금지):

{"summary": ["핵심 한 줄", ...], "tasks": [{"title": "업무명", "body": "내용", "owner": "담당자 후보(모르면 빈 문자열)", "due": "기한 후보 YYYY-MM-DD(모르면 빈 문자열)"}]}

summary 는 5줄 이내. tasks 는 회의에서 나온 할 일만 담고, 없으면 빈 배열."""

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)


def _parse_summary_json(text: str) -> dict:
    """모델 출력에서 JSON 객체를 뽑는다. 실패하면 summary 만 원문으로 채운 폴백을 돌려준다."""
    m = _JSON_BLOCK_RE.search(text or "")
    if m:
        try:
            d = json.loads(m.group(0))
            summary = [str(s) for s in d.get("summary") or []][:5]
            tasks = []
            for t in d.get("tasks") or []:
                if not isinstance(t, dict) or not t.get("title"):
                    continue
                tasks.append({
                    "title": str(t.get("title") or ""),
                    "body": str(t.get("body") or ""),
                    "owner": str(t.get("owner") or ""),
                    "due": str(t.get("due") or ""),
                })
            if summary or tasks:
                return {"summary": summary, "tasks": tasks}
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    return {"summary": [(text or "").strip()[:500]], "tasks": []}


@router.post("/summarize")
def summarize(body: dict):
    title = str((body or {}).get("title") or "").strip()
    transcript = str((body or {}).get("transcript") or "").strip()
    if not transcript:
        return {"error": "받아쓴 글이 비어 있습니다."}
    transcript = transcript[:MAX_TRANSCRIPT_CHARS]

    client = api_chat._anthropic_client()
    if not client:
        return {"error": "요약 엔진에 지금 닿지 않습니다 — 잠시 후 다시 시도해 주세요."}

    user_text = "제목: %s\n\n녹취록:\n%s" % (title or "(제목 없음)", transcript)
    try:
        resp = client.messages.create(
            model=api_chat.COUNSEL_MODEL_FALLBACK,
            max_tokens=2000,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    except Exception as e:
        return {"error": "요약 실패: %s" % type(e).__name__}

    return _parse_summary_json(text)


def _selftest():
    ok = _parse_summary_json('앞뒤 잡담\n{"summary": ["a", "b"], "tasks": [{"title": "청소", "body": "화장실", "owner": "", "due": ""}]}')
    assert ok == {"summary": ["a", "b"], "tasks": [{"title": "청소", "body": "화장실", "owner": "", "due": ""}]}, ok
    bad = _parse_summary_json("그냥 문장일 뿐 JSON 아님")
    assert bad["tasks"] == [] and bad["summary"][0].startswith("그냥"), bad
    empty = _parse_summary_json('{"summary": [], "tasks": []}')
    assert empty["tasks"] == [] and empty["summary"], empty  # summary·tasks 둘 다 비면 폴백(원문)으로
    print("api_meeting selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
