# scripts/cta_utm.py
# 웰페리온 문의 CTA 출처 딱지(utm_source+medium+campaign) 자동 부착 — 채널 발행 직전 본문 URL에 부착.
# 문의페이지(wp_inquiry_block.html)가 파라미터를 읽어 클릭로그에 기록 → 대시보드 '유입 출처' 집계.
import re
import urllib.parse
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

# 채널 키 → utm_medium 코드
CHANNEL_MEDIUM = {
    "naver_blog": "blog",
    "naver_cafe": "cafe",
    "danggn":     "community",
    "kakao":      "messaging",
    "instagram":  "social",
}

# wellperion.com/ko/inquiry (http(s):// 선택, 끝 슬래시 선택) — 뒤에 쿼리/추가경로 없을 때만
_INQ_RE = re.compile(r"((?:https?://)?wellperion\.com/ko/inquiry)/?(?![\w./?=#-])")


def slugify_campaign(path_or_name: str) -> str:
    """경로 또는 폴더명에서 campaign 슬러그 생성.
    - YYMMDD 숫자 + ASCII 영숫자 토큰만 추출해 '_'로 연결(한글 제거).
    - 날짜(YYMMDD)가 포함된 경로 컴포넌트에서만 ASCII 토큰 추출(구조 단어 오염 방지).
    - 경로에 epN(ep1~ep9) 있으면 끝에 _epN 추가.
    - ASCII 토큰 없으면 날짜만, 그것도 없으면 빈 문자열."""
    import re as _re
    # 경로를 '/' 또는 '\\' 로 분리
    parts = _re.split(r'[/\\]', path_or_name)

    # ep 패턴: 경로 컴포넌트 중 ep1~ep9 단독 컴포넌트 우선, 없으면 전체 검색
    ep_suffix = ""
    for part in reversed(parts):
        m = _re.fullmatch(r'ep([1-9])', part.strip(), _re.IGNORECASE)
        if m:
            ep_suffix = f"_ep{m.group(1)}"
            break
    if not ep_suffix:
        m2 = _re.search(r'(?<![A-Za-z0-9])ep([1-9])(?![A-Za-z0-9])', path_or_name, _re.IGNORECASE)
        if m2:
            ep_suffix = f"_ep{m2.group(1)}"

    # 날짜(YYMMDD)가 들어있는 컴포넌트 찾기
    date_token = ""
    name_part = ""
    for part in parts:
        dm = _re.search(r'(?<!\d)(\d{6})(?!\d)', part)
        if dm:
            date_token = dm.group(1)
            name_part = part
            break

    # 날짜 컴포넌트에서 ASCII 영숫자 토큰 추출 (ep 제외)
    if name_part:
        ascii_tokens = _re.findall(r'[A-Za-z][A-Za-z0-9]*', name_part)
        ascii_tokens = [t for t in ascii_tokens if not _re.fullmatch(r'ep[1-9]', t, _re.IGNORECASE)]
    else:
        ascii_tokens = []

    if ascii_tokens:
        slug = (date_token + "_" if date_token else "") + "_".join(ascii_tokens) + ep_suffix
    elif date_token:
        slug = date_token + ep_suffix
    else:
        slug = ""
    return slug


# ─────────────────────────────────────────────────────────────
# 본문 정규화 — 업로드 직전 자동 적용 (누가 본문을 쓰든 매번 동일 결과)
# ─────────────────────────────────────────────────────────────

# 인라인 CTA 줄 제거 패턴: wellperion.com/ko/inquiry 포함 줄
_INLINE_CTA_RE = re.compile(r"^.{0,30}wellperion\.com/ko/inquiry.{0,60}$", re.MULTILINE)

# 해시태그 줄 감지: # 로 시작하는 단어가 2개 이상인 줄
_HASHTAG_LINE_RE = re.compile(r"^(#\S+\s*){2,}$", re.MULTILINE)

# 고정 꼬리 태그 (항상 마지막에 이 순서로)
_TAIL_TAGS = ["#종합스포츠클럽", "#웰페리온", "#WELLPERION"]
# #스포츠클럽 → #종합스포츠클럽 치환 (단독 태그만, #종합스포츠클럽은 건드리지 않음)
_SPORT_CLUB_RE = re.compile(r"(?<!\S)#스포츠클럽(?!\S)")

# 소제목 줄: ▍로 시작
_SUBHEADING_RE = re.compile(r"^(▍.+)$", re.MULTILINE)


def _normalize_hashtags(tag_line: str) -> str:
    """해시태그 줄을 정규화:
    1) #스포츠클럽 → #종합스포츠클럽 치환
    2) 꼬리 태그(#종합스포츠클럽 #웰페리온 #WELLPERION) 순서로 정렬 — 선두 태그는 원래 순서 유지
    """
    # #스포츠클럽 치환
    tag_line = _SPORT_CLUB_RE.sub("#종합스포츠클럽", tag_line)
    # 태그 파싱
    tags = re.findall(r"#\S+", tag_line)
    # 꼬리 태그 분리
    tail_set = set(_TAIL_TAGS)
    head_tags = [t for t in tags if t not in tail_set]
    # 꼬리 태그 중 원본에 있던 것만 순서대로 (없는 것도 고정 꼬리로 추가)
    result = head_tags + _TAIL_TAGS
    return " ".join(result)


def normalize_body(body: str, for_cafe: bool = False) -> tuple[str, list[str]]:
    """본문 정규화 — 업로드 직전 호출.
    반환: (정규화된 본문, 추출된 해시태그 리스트)
    for_cafe=True 이면 본문에서 해시태그 줄을 제거하고 태그 리스트만 반환.

    적용 규칙:
    ① 소제목(▍) 다음 빈 줄을 제거해 내용이 '바로 아랫줄'에 오게 (GM 2026-06-25)
    ② 인라인 CTA 줄(wellperion.com/ko/inquiry 포함) 제거 (링크카드가 단일 CTA)
    ③ 해시태그 정렬·#스포츠클럽→#종합스포츠클럽 치환
    ④ 카페: 본문에서 해시태그 줄 제거 + 태그 리스트 반환
    """
    if not body:
        return body, []

    lines = body.split("\n")
    out: list[str] = []

    # ① 소제목 아래 빈 줄 보장 + ② 인라인 CTA 제거
    i = 0
    while i < len(lines):
        ln = lines[i]
        # 인라인 CTA 줄 제거
        if _INLINE_CTA_RE.match(ln.strip()) and "wellperion.com/ko/inquiry" in ln:
            i += 1
            continue
        out.append(ln)
        # 소제목이면 그 다음 빈 줄을 건너뛰어 내용이 '바로 아랫줄'에 오게 (GM 2026-06-25)
        if _SUBHEADING_RE.match(ln):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            i = j
            continue
        i += 1

    # ③ 해시태그 정렬·치환
    extracted_tags: list[str] = []
    result_lines: list[str] = []
    for ln in out:
        if _HASHTAG_LINE_RE.match(ln.strip()):
            normalized = _normalize_hashtags(ln.strip())
            extracted_tags = re.findall(r"#\S+", normalized)
            # 블로그·카페 모두 본문에서 해시태그 제거 → 카페=태그칸 / 블로그=발행 태그칸 (GM 2026-06-25)
            continue
        result_lines.append(ln)

    # 연속 빈 줄 2개 이상 → 1개로 압축 (CTA 줄 제거 후 공백 잔상 방지)
    collapsed: list[str] = []
    prev_blank = False
    for ln in result_lines:
        is_blank = not ln.strip()
        if is_blank and prev_blank:
            continue  # 연속 빈 줄 건너뜀
        collapsed.append(ln)
        prev_blank = is_blank

    # 후행 공백 줄 정리
    while collapsed and not collapsed[-1].strip():
        collapsed.pop()

    return "\n".join(collapsed), extracted_tags


def apply_cta_utm(text: str, channel: str, campaign: str | None = None) -> str:
    """본문 text 안의 문의 CTA URL에 채널 utm_source·medium·campaign 부착.
    - 이미 utm_source= 가 있으면 그대로 둠(중복 방지).
    - 매핑 없는 채널이면 원문 반환.
    - campaign=None(기본)이면 생략(하위호환).
    - 결과 형태: wellperion.com/ko/inquiry/?utm_source=<code>&utm_medium=<medium>[&utm_campaign=<slug>]"""
    if not text:
        return text
    code = CHANNEL_UTM.get(channel)
    if not code:
        return text
    if "utm_source=" in text:
        return text
    medium = CHANNEL_MEDIUM.get(channel)
    params = f"utm_source={code}"
    if medium:
        params += f"&utm_medium={medium}"
    if campaign:
        params += f"&utm_campaign={urllib.parse.quote(campaign, safe='')}"
    return _INQ_RE.sub(lambda m: m.group(1) + "/?" + params, text)
