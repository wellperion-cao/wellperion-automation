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
# naver_place = 자동 업로더가 없는 '수동 배치' 채널(네이버 스마트플레이스 업체정보의 홈페이지/예약 링크).
#   2026-07-20 시모 실측 근거: 문의 자기신고 네이버 204건 중 197건(96.6%)이 중분류 'N-플레이스(검색)'
#   단일값 — 플레이스와 검색이 한 버킷에 묶여 분리 불가. 자동 UTM 칸은 628건 중 5건(0.8%)만 채워져
#   플레이스 유입을 링크 레벨에서 구분할 수단이 현재 0. 이 코드를 플레이스 관리자 링크에 1회 심으면
#   그 이후 유입부터 '플레이스 경유'가 자동 UTM 칸에 남는다(소급 불가).
CHANNEL_UTM = {
    "naver_blog":  "naver_blog",
    "naver_cafe":  "naver_cafe",
    "naver_place": "naver_place",
    "danggn":      "danggn",
    "kakao":       "kakao",
    "instagram":   "instagram",
}

# 채널 키 → utm_medium 코드
CHANNEL_MEDIUM = {
    "naver_blog":  "blog",
    "naver_cafe":  "cafe",
    "naver_place": "place",
    "danggn":      "community",
    "kakao":       "messaging",
    "instagram":   "social",
}

# wellperion.com/ko/inquiry (http(s):// 선택, 끝 슬래시 선택) — 뒤에 쿼리/추가경로 없을 때만
_INQ_RE = re.compile(r"((?:https?://)?wellperion\.com/ko/inquiry)/?(?![\w./?=#-])")


# ─────────────────────────────────────────────────────────────
# ★ CTA 단일화 설계 — 채널별 CTA(문의 링크) 규칙의 정본(SSOT), 이 블록 하나뿐
#   (2026-07-09 GM 재정립 · 2026-07-20 GM 승인으로 "정본=코드" 공식화, 브랜드 문서는
#   이 블록을 가리키는 포인터만 두고 재서술하지 않는다 — 약속 L01 "한 곳만 본다")
#   ① 글당 CTA는 정확히 1개.
#   ② 원시 UTM URL(?utm_source=…)은 절대 본문 텍스트로 노출 금지 — UTM은 링크카드 href에만.
#   ③ 카드형 채널(블로그·카페): 링크카드가 유일 CTA → 발행 직전 본문 '문의' 줄 제거
#      (strip_inquiry_cta_lines). 카드 삽입 실패 시 반드시 CLEAN_CTA_TEXT 1줄 폴백 삽입
#      (F1 카페 '문의 링크 통째 소실' 재발 방지 — 링크는 어떤 경우에도 1개 남는다).
#   ④ 텍스트 채널(카카오·당근): 깨끗한 '문의' 줄 1개만(ensure_single_clean_cta) —
#      UTM 부착 금지(사람 눈에 보이는 텍스트가 곧 링크라 숨길 곳이 없음. 추적보다 깨끗함 우선).
#   ⑤ 인스타그램(IG): 본문에 CTA 링크 줄 없음(게시물 링크는 클릭 불가) — 유일한 클릭 경로인
#      프로필 bio 링크로 유도한다. IG 업로더는 append_cta_card·ensure_single_clean_cta 둘 다 호출하지 않는다.
#      ⑤-1 bio 링크 = build_ig_bio_url(계정) — 이것만이 IG 기여의 측정 지점이다.
#           bio 링크에 UTM이 없으면 IG를 보고 온 사람도 네이버 검색을 거쳐 '네이버'로 집계된다(과소집계).
#           utm_source=instagram(채널 집계) + utm_medium=bio + utm_content=official|namuk(계정 구분).
#           계정 구분을 utm_source에 섞지 않는다 — 섞으면 채널 버킷이 둘로 갈라진다.
#      ⑤-2 캡션 유도 문구 = IG_BIO_CTA_TEXT 1줄. 압박 없이 알리는 톤 — 링크 URL을 캡션에 쓰지 않는다.
# ─────────────────────────────────────────────────────────────

# 텍스트 CTA 표준 1줄 (UTM 없음 — 사람 눈에 깨끗한 도메인만)
CLEAN_CTA_TEXT = "문의 : wellperion.com/ko/inquiry"

# IG 캡션 표준 유도 1줄 (원칙 ⑤-2) — URL 없이 프로필 링크만 가리킨다
IG_BIO_CTA_TEXT = "프로필 링크로 편하게 문의해 주세요."

# IG 계정명(profiles/instagram/{account} 와 동일 키) → utm_content 코드(계정 식별자).
# 채널(utm_source)은 두 계정 모두 'instagram' — 집계는 '인스타그램' 한 버킷, 계정 구분은 utm_content.
IG_ACCOUNT_CONTENT = {
    "wellperion":       "official",   # @wellperion (공식)
    "namuk.wellperion": "namuk",      # @namuk.wellperion (개인)
}


def build_ig_bio_url(account: str) -> str:
    """IG 프로필 bio 링크 URL의 정본 (원칙 ⑤-1).
    account: 'wellperion'(공식) | 'namuk.wellperion'(개인).
    미등록 계정이면 utm_content 없이(계정 미상) 반환 — 없는 계정을 지어내지 않는다."""
    url = f"{build_inquiry_utm_url('instagram')}"
    url = url.replace("utm_medium=social", "utm_medium=bio")   # bio 링크는 medium=bio
    code = IG_ACCOUNT_CONTENT.get(account)
    return f"{url}&utm_content={code}" if code else url


def build_inquiry_utm_url(channel: str, campaign: str | None = None) -> str:
    """링크카드 href 전용 UTM 추적 URL 생성 — 본문 텍스트로 삽입 금지(원칙 ②).
    채널 매핑 없으면 UTM 없는 깨끗한 URL 반환."""
    base = "http://wellperion.com/ko/inquiry/"
    code = CHANNEL_UTM.get(channel)
    if not code:
        return base
    params = f"utm_source={code}"
    medium = CHANNEL_MEDIUM.get(channel)
    if medium:
        params += f"&utm_medium={medium}"
    if campaign:
        params += f"&utm_campaign={urllib.parse.quote(campaign, safe='')}"
    return f"{base}?{params}"


def _collapse_blank_lines(lines: list[str]) -> str:
    """연속 빈 줄 1개로 압축 + 후행 공백 줄 제거."""
    collapsed: list[str] = []
    prev_blank = False
    for ln in lines:
        is_blank = not ln.strip()
        if is_blank and prev_blank:
            continue
        collapsed.append(ln)
        prev_blank = is_blank
    while collapsed and not collapsed[-1].strip():
        collapsed.pop()
    return "\n".join(collapsed)


def strip_inquiry_cta_lines(body: str) -> tuple[str, bool]:
    """본문에서 문의 CTA 줄(wellperion.com/ko/inquiry 포함 줄) 전부 제거 (원칙 ③ 전반부).
    카드형 채널(블로그·카페) 발행 직전 호출 — 링크카드가 유일 CTA가 되도록.
    ⚠ 호출 측 의무: 링크카드 삽입 실패 시 CLEAN_CTA_TEXT 1줄을 반드시 폴백 삽입할 것.
    반환: (제거된 본문, 제거 발생 여부)."""
    if not body:
        return body, False
    lines = body.split("\n")
    kept = [ln for ln in lines if "wellperion.com/ko/inquiry" not in ln]
    if len(kept) == len(lines):
        return body, False
    return _collapse_blank_lines(kept), True


def ensure_single_clean_cta(body: str) -> str:
    """텍스트 채널(카카오·당근)용 (원칙 ④) — 문의 CTA를 깨끗한 1줄로 강제.
    - 첫 CTA 줄을 CLEAN_CTA_TEXT 로 교체(UTM·장식 제거), 나머지 CTA 줄은 삭제(중복 제거).
    - CTA 줄이 하나도 없으면 본문 끝에 1줄 추가(문의 링크 소실 방지)."""
    if not body:
        return body
    lines = body.split("\n")
    out: list[str] = []
    placed = False
    for ln in lines:
        if "wellperion.com/ko/inquiry" in ln:
            if not placed:
                out.append(CLEAN_CTA_TEXT)
                placed = True
            continue  # 중복 CTA 줄 제거
        out.append(ln)
    if not placed:
        out.extend(["", CLEAN_CTA_TEXT])
    return _collapse_blank_lines(out)


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

# 계정별 고정 선두(앞자리) 해시태그 — 발행 시 항상 이 순서로 맨 앞에 박제 (GM 2026-07-08)
#   개인(namuk.wellperion): 브랜드 축 2개 고정. 3번째부터는 콘텐츠 주제 맞춤 인기태그(기획 단계 리서치).
#   공식(wellperion): 고정 없음 — 앞 3개 전부 콘텐츠 주제별 상위 인기태그를 기획 단계에서 선정(키워드 인기도 기반).
# 구조: [계정 고정 선두] + [주제 맞춤 인기태그(기획)] + … + [_TAIL_TAGS 브랜드 꼬리]
HEAD_TAGS_FIXED = {
    "namuk.wellperion": ["#AI자동화", "#스포츠클럽자동화"],
    "wellperion": [],
}


def apply_head_tags(tags, account: str):
    """계정 고정 선두 태그를 해시태그 리스트 맨 앞에 보장(중복 제거·순서 유지).
    - tags: 기존 해시태그 list[str] (기획 단계에서 적은 주제 맞춤 태그 포함)
    - account: 'namuk.wellperion'(개인) | 'wellperion'(공식) 등
    반환: [고정 선두] + [중복 제외한 기존 태그]. 고정 선두 없으면 원본 순서 유지.
    태그 비교는 '#' 제거 + 소문자 기준(영문 대소문자만 정규화, 한글 불변)."""
    head = HEAD_TAGS_FIXED.get(account, [])
    seen = set()
    result = []
    for t in list(head) + list(tags or []):
        key = t.lstrip("#").lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(t)
    return result
# #스포츠클럽 → #종합스포츠클럽 치환 (단독 태그만, #종합스포츠클럽은 건드리지 않음)
_SPORT_CLUB_RE = re.compile(r"(?<!\S)#스포츠클럽(?!\S)")

# 소제목 줄: ▍로 시작
_SUBHEADING_RE = re.compile(r"^([▍■].+)$", re.MULTILINE)  # ▍(카카오)·■(블로그·카페) 둘 다 소제목 인식 (2026-07-08 — ■ 사각지대 봉합)


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
    ① 소제목(▍·■) 다음 빈 줄을 제거해 내용이 '바로 아랫줄'에 오게 (GM 2026-06-25 · ■ 추가 07-08)
    ② (폐지 2026-07-08) 인라인 CTA 줄 제거 안 함 — 링크카드 실패 시 문의 링크 소실 방지
    ③ 해시태그 정렬·#스포츠클럽→#종합스포츠클럽 치환
    ④ 카페: 본문에서 해시태그 줄 제거 + 태그 리스트 반환
    """
    if not body:
        return body, []

    lines = body.split("\n")
    out: list[str] = []

    # ① 소제목 아래 빈 줄 보장 (② 인라인 CTA 제거는 폐지 — 2026-07-08 GM)
    #   폐지 사유: 링크카드가 라이브에서 삽입 실패하면 본문 문의 CTA도 이미 지워져
    #   '문의 링크 통째 소실' 발생(F1 카페 사고). 문의 텍스트 CTA는 항상 본문에 남긴다.
    i = 0
    while i < len(lines):
        ln = lines[i]
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
