# scripts/cta_utm.py
# 웰페리온 문의 CTA 출처 딱지(utm_source) 자동 부착 — 채널 발행 직전 본문 URL에 채널 출처를 붙인다.
# 문의페이지(wp_inquiry_block.html)가 ?utm_source 를 읽어 클릭로그에 기록 → 대시보드 '유입 출처' 채널별 집계.
import re
from pathlib import Path

# 문의 CTA 카드 자산 (생성기 scripts/compose_cta_card.py) — 4채널(블로그·카페·당근·카카오) 마지막 이미지.
# IG는 제외(슬라이드/캡션/bio가 담당). 회사 공식 콘텐츠용. ⚠️ 이미지=시각강조(클릭불가).
CTA_CARD_PATH = (Path(__file__).resolve().parent.parent / "instagram" / "_assets" / "cta_card.jpg")


def append_cta_card(image_paths):
    """발행 이미지 리스트 끝에 문의 CTA 카드를 마지막 이미지로 첨부(블로그·카페·당근·카카오 전용).
    - 카드 자산이 없거나 이미 포함돼 있으면 원본 그대로(안전·멱등).
    - IG 업로더는 이 함수를 호출하지 않는다."""
    try:
        imgs = list(image_paths or [])
        if CTA_CARD_PATH.exists() and not any(Path(p).resolve() == CTA_CARD_PATH for p in imgs):
            imgs.append(CTA_CARD_PATH)
        return imgs
    except Exception:
        return image_paths


# 채널 키 → utm_source 코드 (대시보드 UTM_LABELS와 정합)
CHANNEL_UTM = {
    "naver_blog": "naver_blog",
    "naver_cafe": "naver_cafe",
    "danggn":     "danggn",
    "kakao":      "kakao",
    "instagram":  "instagram",
}

# wellperion.com/ko/inquiry (http(s):// 선택, 끝 슬래시 선택) — 뒤에 쿼리/추가경로 없을 때만
_INQ_RE = re.compile(r"((?:https?://)?wellperion\.com/ko/inquiry)/?(?![\w./?=#-])")


def apply_cta_utm(text: str, channel: str) -> str:
    """본문 text 안의 문의 CTA URL에 채널 utm_source 부착.
    - 이미 utm_source= 가 있으면 그대로 둠(중복 방지).
    - 매핑 없는 채널이면 원문 반환.
    - 결과 형태: wellperion.com/ko/inquiry/?utm_source=<code> (원래 scheme 보존)."""
    if not text:
        return text
    code = CHANNEL_UTM.get(channel)
    if not code:
        return text
    if "utm_source=" in text:
        return text
    return _INQ_RE.sub(lambda m: m.group(1) + "/?utm_source=" + code, text)
