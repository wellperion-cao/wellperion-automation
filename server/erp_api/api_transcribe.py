# -*- coding: utf-8 -*-
"""음성 인식(자동 언어판별) — 배 12832 · GM 2026-09-18 「한국어로 말하면 영어로, 영어로 말하면 한국어로」(번역기 앞단).

브라우저 음성인식(SpeechRecognition)은 언어를 하나로 고정해야 해서 자동판별이 안 된다 — AWS Transcribe
스트리밍의 identify_language 로 대신한다. 모델 호출과 달리 이건 진짜 비동기 I/O(amazon_transcribe 가
asyncio 기반)라 라우트를 async def 로 둬도 이벤트 루프를 막지 않는다(동기 urllib 로 막았던 종합접수처
결함과는 다른 경우 — 시토 실측).

본문 모양 = 16kHz 모노 PCM(s16le) 원시 바이트 그대로(POST body, Content-Type: application/octet-stream).
base64 는 안 쓴다 — 전송량만 33% 늘고 이점이 없다. 15초 상한 — 그 뒤 바이트는 버린다(16kHz*2byte=
32000B/s). 언어 후보 = 쿼리 langs(콤마 구분 · 허용 목록 TRANSCRIBE_LANG_ALLOW 안에서만 · 기본 ko-KR,en-US).

인증 = /api/translate 와 같은 자리 — API_MODULES(app.py) 에 등록하지 않아 로그인만 하면 직원·파트너
전부 연다(등록 안 된 /api/ 접두는 기본 열림 · app.py path_allowed 주석 참고). 새 인증 안 만든다.

쓰임 기록 = api_assistant.log_usage(kind="stt") — 원문 텍스트·음성 저장 금지, 길이(초)·판별 언어만.

자체점검: python api_transcribe.py --selftest (네트워크 없음 · 15초 상한 자르기·langs 검증만 검사)
"""
import asyncio
import sys

from fastapi import APIRouter, Request

import api_assistant

router = APIRouter(prefix="/api/transcribe")

SAMPLE_RATE = 16000
BYTES_PER_SEC = SAMPLE_RATE * 2                  # s16le 모노 = 초당 32000바이트
MAX_SECONDS = 15
MAX_BYTES = BYTES_PER_SEC * MAX_SECONDS
TRANSCRIBE_LANG_ALLOW = ("ko-KR", "en-US")
TRANSCRIBE_REGION = "ap-northeast-2"
_CHUNK = 8000                                     # 250ms 분량씩 스트림에 흘려보낸다


def _langs(raw: str) -> list:
    """쿼리 langs 파싱 — 허용 목록 밖은 버린다. 빈 값·전부 걸러지면 기본값(ko-KR,en-US)."""
    cands = [x.strip() for x in (raw or "").split(",") if x.strip()]
    ok = [x for x in cands if x in TRANSCRIBE_LANG_ALLOW]
    return ok or list(TRANSCRIBE_LANG_ALLOW)


def _cap(body: bytes) -> bytes:
    """15초 상한 — 바이트 수로 자른다(s16le 샘플 경계 깨지지 않게 짝수로)."""
    n = min(len(body), MAX_BYTES)
    return body[: n - (n % 2)]


async def _transcribe(pcm: bytes, langs: list) -> dict:
    from amazon_transcribe.client import TranscribeStreamingClient
    from amazon_transcribe.handlers import TranscriptResultStreamHandler

    client = TranscribeStreamingClient(region=TRANSCRIBE_REGION)
    stream = await client.start_stream_transcription(
        language_code=None,
        media_sample_rate_hz=SAMPLE_RATE,
        media_encoding="pcm",
        identify_language=True,
        language_options=langs,
    )

    texts, detected = [], [""]

    class _Handler(TranscriptResultStreamHandler):
        async def handle_transcript_event(self, transcript_event):
            for result in transcript_event.transcript.results:
                if result.is_partial:
                    continue                       # 확정된 구간만 — 중간 추정치는 버린다
                if result.language_code:
                    detected[0] = result.language_code
                for alt in result.alternatives:
                    texts.append(alt.transcript)

    async def _send():
        for i in range(0, len(pcm), _CHUNK):
            await stream.input_stream.send_audio_event(audio_chunk=pcm[i:i + _CHUNK])
        await stream.input_stream.end_stream()

    handler = _Handler(stream.output_stream)
    await asyncio.gather(_send(), handler.handle_events())
    return {"text": " ".join(texts).strip(), "lang": detected[0]}


@router.post("")
async def transcribe(request: Request, langs: str = ""):
    body = await request.body()
    if not body:
        return {"error": "음성 데이터가 비어 있습니다."}
    pcm = _cap(body)
    lang_opts = _langs(langs)

    try:
        result = await _transcribe(pcm, lang_opts)
    except Exception as e:
        return {"error": "음성 인식 실패: %s" % type(e).__name__}

    seconds = round(len(pcm) / BYTES_PER_SEC, 1)
    api_assistant.log_usage(request, "stt", seconds, lang=result.get("lang", ""))  # 원문 텍스트는 안 남긴다
    return result


def _selftest():
    assert _langs("") == ["ko-KR", "en-US"]
    assert _langs("ko-KR") == ["ko-KR"]
    assert _langs("ko-KR,en-US,ja-JP") == ["ko-KR", "en-US"]     # 허용 밖(ja-JP)은 버려진다
    assert _langs("ja-JP") == ["ko-KR", "en-US"]                 # 전부 걸러지면 기본값

    long_body = b"\x00\x01" * (MAX_BYTES // 2 + 100)             # 15초보다 긺
    capped = _cap(long_body)
    assert len(capped) == MAX_BYTES, len(capped)
    assert len(capped) % 2 == 0

    short_body = b"\x00\x01" * 10
    assert _cap(short_body) == short_body                        # 짧으면 그대로

    print("api_transcribe selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
