# -*- coding: utf-8 -*-
"""AI 번역가 — 실시간 통역 · 배 12804 · 2026-09-18 시보.

erp/admin/translator.html 이 문장 하나(원문+방향)를 보내면 번역문 하나를 돌려준다. 대화 기록·SSOT
반영 없음 — meeting_note 와 달리 이 화면은 그 순간 통역만 한다.

모델 호출 = api_chat.py 의 Bedrock 클라이언트를 그대로 재사용(새 클라이언트 금지) · 모델은 그 파일의
대체(Sonnet 계열) 상수 COUNSEL_MODEL_FALLBACK 그대로 — 번역도 판단이 아니라 정리 작업이라 가벼운 모델.

자체점검: python api_translate.py --selftest (네트워크 없음 · 입력 검증만 검사)
"""
import sys

from fastapi import APIRouter, Request

import api_assistant
import api_chat

router = APIRouter(prefix="/api/translate")

MAX_TEXT_CHARS = 1000

_LANG_NAMES = {"ko": "한국어", "en": "영어", "ja": "일본어", "zh": "중국어"}


def _validate(body: dict):
    """입력 검증 — 통과하면 (text, source, target), 아니면 (None, None, error)."""
    text = str((body or {}).get("text") or "").strip()
    source = str((body or {}).get("source") or "").strip()
    target = str((body or {}).get("target") or "").strip()
    if not text:
        return None, None, None, "번역할 글이 비어 있습니다."
    if len(text) > MAX_TEXT_CHARS:
        return None, None, None, "글이 너무 길습니다(%d자 넘음)." % MAX_TEXT_CHARS
    if not source or not target:
        return None, None, None, "원본·번역 언어가 없습니다."
    return text, source, target, None


def _system_prompt(source: str, target: str) -> str:
    src_name = _LANG_NAMES.get(source, source)
    tgt_name = _LANG_NAMES.get(target, target)
    return ("너는 통역가다. %s 문장을 %s 로 번역한다. 번역문만 출력한다 — 설명·인사말·따옴표·"
            "원문 반복 금지." % (src_name, tgt_name))


@router.post("")
def translate(request: Request, body: dict):
    text, source, target, err = _validate(body)
    if err:
        return {"error": err}

    client = api_chat._anthropic_client()
    if not client:
        return {"error": "번역 엔진에 지금 닿지 않습니다 — 잠시 후 다시 시도해 주세요."}

    try:
        resp = client.messages.create(
            model=api_chat.COUNSEL_MODEL_FALLBACK,
            max_tokens=500,
            system=_system_prompt(source, target),
            messages=[{"role": "user", "content": text}],
        )
        translation = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    except Exception as e:
        return {"error": "번역 실패: %s" % type(e).__name__}

    api_assistant.log_usage(request, "translate", len(text), source=source, target=target, out=translation)
    return {"translation": translation}


def _selftest():
    text, source, target, err = _validate({"text": "안녕하세요", "source": "ko", "target": "en"})
    assert err is None and text == "안녕하세요" and source == "ko" and target == "en", (text, source, target, err)

    _, _, _, err = _validate({"text": "", "source": "ko", "target": "en"})
    assert err, "빈 문자열은 거절해야 한다"

    _, _, _, err = _validate({"text": "a" * (MAX_TEXT_CHARS + 1), "source": "ko", "target": "en"})
    assert err, "길이 상한을 넘으면 거절해야 한다"

    _, _, _, err = _validate({"text": "hi", "source": "", "target": "en"})
    assert err, "언어가 없으면 거절해야 한다"

    print("api_translate selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
