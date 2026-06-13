# scripts/cta_utm.py
# 웰페리온 문의 CTA 출처 딱지(utm_source) 자동 부착 — 채널 발행 직전 본문 URL에 채널 출처를 붙인다.
# 문의페이지(wp_inquiry_block.html)가 ?utm_source 를 읽어 클릭로그에 기록 → 대시보드 '유입 출처' 채널별 집계.
import re

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
