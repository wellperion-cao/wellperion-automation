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
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Request

import api_assistant
import api_chat

router = APIRouter(prefix="/api/meeting")

MAX_TRANSCRIPT_CHARS = 20000

_KST = timezone(timedelta(hours=9))
_WEEKDAY_KR = "월화수목금토일"


def _today_kst() -> date:
    return datetime.now(_KST).date()


def _system_prompt(today: date) -> str:
    """오늘 날짜를 프롬프트에 박아 준다 — 모델이 훈련 시점 연도로 기한을 지어내는 것 방지(시토 실측 결함)."""
    today_str = today.strftime("%Y-%m-%d")
    weekday = _WEEKDAY_KR[today.weekday()]
    return """너는 회의록 요약 비서다. 오늘 = %s(%s요일). 입력된 회의 제목과 받아쓴 녹취록을 읽고
반드시 아래 모양의 JSON 객체 하나만 출력한다(설명·코드블록·다른 글자 금지):

{"summary": ["핵심 한 줄", ...], "tasks": [{"title": "업무명", "body": "내용", "owner": "담당자 후보(모르면 빈 문자열)", "due": "기한 후보 YYYY-MM-DD(모르면 빈 문자열)"}]}

summary 는 5줄 이내. tasks 는 회의에서 나온 할 일만 담고, 없으면 빈 배열. due 는 반드시 오늘(%s) 기준
오늘이거나 그 뒤 날짜로 잡는다 — 지난 연도를 쓰지 않는다.""" % (today_str, weekday, today_str)


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _fix_due(due: str, today: date) -> str:
    """오늘보다 앞선 기한은 연도만 오늘 연도로 보정 — 그래도 앞이면 지어내지 않고 빈칸(시토 실측:
    모델이 2024년을 오늘로 착각해 기한이 전부 과거로 나온 결함)."""
    due = (due or "").strip()
    m = _DATE_RE.match(due)
    if not m:
        return due  # 날짜 모양이 아니면(자유 텍스트일 수 있음) 손대지 않는다
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        dt = date(y, mo, d)
    except ValueError:
        return due
    if dt >= today:
        return due
    try:
        dt2 = date(today.year, mo, d)
    except ValueError:
        return ""
    return dt2.strftime("%Y-%m-%d") if dt2 >= today else ""


def _parse_summary_json(text: str, today: date = None) -> dict:
    """모델 출력에서 JSON 객체를 뽑는다. 실패하면 summary 만 원문으로 채운 폴백을 돌려준다."""
    today = today or _today_kst()
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
                    "due": _fix_due(str(t.get("due") or ""), today),
                })
            if summary or tasks:
                return {"summary": summary, "tasks": tasks}
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    return {"summary": [(text or "").strip()[:500]], "tasks": []}


MAX_TITLE_CHARS = 200


def _mark_truncated(result: dict, input_truncated: bool, output_truncated: bool) -> dict:
    """녹취록이 상한(MAX_TRANSCRIPT_CHARS)으로 잘렸거나 모델 응답이 토큰 상한(stop_reason=max_tokens)
    으로 끊겼으면 truncated:true 를 얹는다 — 화면이 「일부만 요약됐다」를 알 수 있게."""
    if input_truncated or output_truncated:
        result["truncated"] = True
    return result


@router.post("/summarize")
def summarize(request: Request, body: dict):
    title = str((body or {}).get("title") or "").strip()[:MAX_TITLE_CHARS]
    transcript = str((body or {}).get("transcript") or "").strip()
    if not transcript:
        return {"error": "받아쓴 글이 비어 있습니다."}
    input_truncated = len(transcript) > MAX_TRANSCRIPT_CHARS
    transcript = transcript[:MAX_TRANSCRIPT_CHARS]

    client = api_chat._anthropic_client()
    if not client:
        return {"error": "요약 엔진에 지금 닿지 않습니다 — 잠시 후 다시 시도해 주세요."}
    client = client.with_options(timeout=60, max_retries=1)

    today = _today_kst()
    user_text = "제목: %s\n\n녹취록:\n%s" % (title or "(제목 없음)", transcript)
    try:
        resp = client.messages.create(
            model=api_chat.COUNSEL_MODEL_FALLBACK,
            max_tokens=4000,
            system=_system_prompt(today),
            messages=[{"role": "user", "content": user_text}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        output_truncated = getattr(resp, "stop_reason", "") == "max_tokens"
    except Exception as e:
        return {"error": "요약 실패: %s" % type(e).__name__}

    result = _mark_truncated(_parse_summary_json(text, today), input_truncated, output_truncated)
    api_assistant.log_usage(request, "summary", len(transcript), title=title, out=result)
    return result


def _selftest():
    today = date(2026, 9, 18)
    ok = _parse_summary_json('앞뒤 잡담\n{"summary": ["a", "b"], "tasks": [{"title": "청소", "body": "화장실", "owner": "", "due": ""}]}', today)
    assert ok == {"summary": ["a", "b"], "tasks": [{"title": "청소", "body": "화장실", "owner": "", "due": ""}]}, ok
    bad = _parse_summary_json("그냥 문장일 뿐 JSON 아님", today)
    assert bad["tasks"] == [] and bad["summary"][0].startswith("그냥"), bad
    empty = _parse_summary_json('{"summary": [], "tasks": []}', today)
    assert empty["tasks"] == [] and empty["summary"], empty  # summary·tasks 둘 다 비면 폴백(원문)으로

    # 시토 실측 결함 — 모델이 오늘을 2024년으로 착각해 기한이 전부 과거로 나옴.
    # 2024-09-06 → 연도만 오늘 연도로 고치면 2026-09-06, 그래도 오늘(9/18)보다 앞이라 빈칸.
    # 2024-10-07 → 2026-10-07 은 오늘보다 뒤라 그대로 채택.
    due = _parse_summary_json(
        '{"summary": ["s"], "tasks": ['
        '{"title": "a", "body": "", "owner": "", "due": "2024-09-06"},'
        '{"title": "b", "body": "", "owner": "", "due": "2024-10-07"}]}', today)
    assert due["tasks"][0]["due"] == "", due
    assert due["tasks"][1]["due"] == "2026-10-07", due
    assert _fix_due("자유텍스트", today) == "자유텍스트"  # 날짜 모양 아니면 손대지 않는다

    r1 = _mark_truncated({"summary": ["a"], "tasks": []}, True, False)
    assert r1.get("truncated") is True, r1
    r2 = _mark_truncated({"summary": ["a"], "tasks": []}, False, True)
    assert r2.get("truncated") is True, r2
    r3 = _mark_truncated({"summary": ["a"], "tasks": []}, False, False)
    assert "truncated" not in r3, r3

    print("api_meeting selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
