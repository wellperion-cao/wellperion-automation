#!/usr/bin/env python3
# scripts/generate_channel_copy.py
# IG 원고 → 4채널(블로그·카페·카카오·당근) 원고 자동 생성기 (배834-B, 2026-07-20)
#
# 배경: publish_register.py 의 _auto_register_channel_siblings() 는 "채널별 본문 파일이
# 이미 존재하면" 검수 큐에 형제 엔트리를 자동 등록한다(배834-A). 그런데 그 본문 자체를
# 만드는 일은 여전히 수동이었다 — 2026-07-20 필라테스 L4가 IG 산출물만 있고 블로그·카페·
# 카카오·당근 원고가 없어 IG만 발행된 사고가 그 결과. 이 모듈이 그 마지막 구멍을 메운다.
#
# ★ 등록·큐 로직은 절대 중복 작성하지 않는다 — 이 모듈은 "본문 파일 생성"만 담당.
#   검수 큐 등록은 publish_register._auto_register_channel_siblings() 가 그대로 담당.
#
# 두뇌(LLM) 우선순위 = ai_learning_proposer.py 와 동일 SSOT (GM 결정 2026-06-23):
#   1순위: claude CLI(claude -p, model_router.run_claude) — Claude Code 구독 재사용, API 크레딧 0
#   2순위: 규칙기반 폴백 — CLI 불가/실패 시 최소 동작 보장(구조·CTA·해시태그는 정확,
#          문장은 IG 원문을 그대로 재사용 — 새 사실을 지어내지 않는다)
#
# 채널별 형식(2026-07-15~18 L1 수영·L2 PT·L3 골프 5채널 실측 학습 결과 — 발명 금지, 그대로 재현):
#   - 블로그(_blog_body.txt): 격식체(-습니다), IG보다 상세하게 풀어씀(새 사실 추가 아님, 재구성만),
#     CTA 1줄 + 해시태그 줄(IG 해시태그 그대로)
#   - 카페(_cafe_body.txt):  격식체, 블로그보다 압축(2문단 내외), CTA 1줄 +
#     해시태그 줄(과시적 태그 "#프리미엄스포츠클럽" 계열만 제외 — 나머지 IG 태그 유지)
#   - 카카오(kakao_copy.md): 카페 본문과 동일 + 해시태그 줄만 제거
#   - 당근(danggn_copy.md):  제목 줄 + "---" 구분선 + 압축 본문 + CTA 1줄(해시태그 없음)
#     (당근 CTA 포함 = scripts/cta_utm.py 설계 원칙④ 그대로 따름. 과거 브랜드 문서와의
#      중복 서술 상충은 2026-07-20 GM 승인으로 해소 — 정본은 cta_utm.py 하나, 브랜드 문서는
#      포인터만 둔다.)
#
# 절대 금지: IG 원고에 없는 사실·효과·수치를 새로 만들지 않는다(톤 변환·재구성만 허용).
# 브랜드 금지어(scripts/brand_constants.py·ssot/canon_values.json 톤 규칙): "피트니스"→"스포츠클럽",
# "하이엔드 프라이빗"·"사교" 뉘앙스 노출 금지.
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    _reconf = getattr(_stream, "reconfigure", None) if _stream is not None else None
    if _reconf is not None:
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

try:
    from cta_utm import CLEAN_CTA_TEXT  # "문의 : wellperion.com/ko/inquiry" 단일 출처
except Exception:
    CLEAN_CTA_TEXT = "문의 : wellperion.com/ko/inquiry"  # 최후 안전망(정본은 cta_utm.py)

# publish_register._SIBLING_CHANNEL_SPECS 와 동일한 서브폴더/파일명(값은 그쪽이 "존재 확인"에
# 쓰는 것과 동일해야 형제 자동등록이 이 생성기의 산출물을 인식한다 — 로직 중복이 아니라 상수 정합).
CHANNEL_SUBDIR = {
    "blog": "output(블로그)",
    "cafe": "output(카페)",
    "kakao": "output(카카오 채널)",
    "danggn": "output(당근)",
}
CHANNEL_FILENAME = {
    "blog": "_blog_body.txt",
    "cafe": "_cafe_body.txt",
    "kakao": "kakao_copy.md",
    "danggn": "danggn_copy.md",
}

FORBIDDEN_WORDS = ["피트니스", "하이엔드 프라이빗", "사교"]

# 카페 해시태그에서 제외할 과시적 태그(2026-07-17 골프 L3 실측 — 카페=압박 없이 알리는 톤 유지)
_CAFE_EXCLUDE_TAGS = {"#프리미엄스포츠클럽"}


def check_forbidden_words(text: str) -> list[str]:
    """브랜드 금지어 자가점검 — 검출된 금지어 리스트 반환(없으면 빈 리스트)."""
    return [w for w in FORBIDDEN_WORDS if w in text]


def _strip_ig_footer(ig_caption: str) -> tuple[str, list[str]]:
    """IG 캡션에서 해시태그 줄과 '프로필 링크로 문의' 안내줄을 분리해 순수 본문만 반환.
    반환: (본문, 해시태그 리스트)."""
    lines = ig_caption.strip("\n").split("\n")
    tags: list[str] = []
    body_lines: list[str] = []
    for ln in lines:
        s = ln.strip()
        if re.fullmatch(r"(#\S+\s*){2,}", s):
            tags = re.findall(r"#\S+", s)
            continue
        if "프로필 링크" in s and "문의" in s:
            continue
        body_lines.append(ln)
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    return "\n".join(body_lines), tags


# ─────────────────────────────────────────────────────────────────
# 규칙기반 폴백 — claude CLI 불가/실패 시 최소 동작 보장
# ─────────────────────────────────────────────────────────────────
def _fallback_channel_bodies(ig_caption: str, topic_title: str) -> dict[str, str]:
    """LLM 불가 시 IG 본문을 구조만 채널별로 재배치(문장 자체는 원문 재사용 — 지어내기 없음)."""
    body, tags = _strip_ig_footer(ig_caption)
    blog_tag_line = " ".join(tags)
    cafe_tags = [t for t in tags if t not in _CAFE_EXCLUDE_TAGS]
    cafe_tag_line = " ".join(cafe_tags)

    blog = "\n\n".join([p for p in [body, CLEAN_CTA_TEXT, blog_tag_line] if p]).strip()
    cafe = "\n\n".join([p for p in [body, CLEAN_CTA_TEXT, cafe_tag_line] if p]).strip()
    kakao = "\n\n".join([p for p in [body, CLEAN_CTA_TEXT] if p]).strip()

    danggn_title = topic_title.strip() if topic_title else next(
        (l.strip() for l in body.split("\n") if l.strip()), "웰페리온 소식"
    )
    danggn = "\n".join([danggn_title, "---", body, "", CLEAN_CTA_TEXT]).strip()

    return {"blog": blog, "cafe": cafe, "kakao": kakao, "danggn": danggn}


# ─────────────────────────────────────────────────────────────────
# LLM 경로 — claude CLI(model_router.run_claude) 재사용
# ─────────────────────────────────────────────────────────────────
_FEWSHOT_IG = """마음이 급한 사람일수록, 제일 늦게 느는 운동이 있어요.

세게 치려는 날은 어김없이 망하고,
힘을 뺀 날은 공이 곱게 나가요.
마음 연습이 따로 없더라고요.

어제 되던 게 오늘은 안 되기도 해요.
사람을 겸손하게 만드는 운동이에요.

그런데 신기하죠.
힘을 뺄 줄 아는 사람이 공을 더 멀리 보내요.
골프도, 삶도 그렇더라고요.

한남동에서 서두르지 않고, 힘 빼는 법부터 천천히 배우는 실내 골프 강습.

프로필 링크로 편하게 문의해 주세요.

#한남동골프 #실내골프 #성인골프강습 #골프레슨 #한남동 #스포츠클럽 #프리미엄스포츠클럽 #웰페리온 #WELLPERION"""

_FEWSHOT_BLOG = """마음이 급한 사람일수록, 제일 늦게 느는 운동이 있습니다.

세게 치려는 날은 어김없이 망하고, 오히려 힘을 뺀 날 공이 곱게 나갑니다. 골프에는 이상하게 마음 연습이 따로 없습니다.

어제는 됐던 스윙이 오늘은 안 되기도 합니다. 실력이 꾸준히 오르기보다는, 사람을 자꾸 겸손하게 만드는 운동입니다.

그런데 신기한 건, 결국 힘을 뺄 줄 아는 사람이 공을 더 멀리 보낸다는 것입니다. 골프도 삶도 크게 다르지 않더라고요.

웰페리온은 한남동에서 서두르지 않고, 힘 빼는 법부터 천천히 배우는 실내 골프 강습을 운영합니다.

한남동에서 힘 빼는 법부터 차근히 배우고 싶다면, 편하게 문의 주세요.

문의 : wellperion.com/ko/inquiry

#한남동골프 #실내골프 #성인골프강습 #골프레슨 #한남동 #스포츠클럽 #프리미엄스포츠클럽 #웰페리온 #WELLPERION"""

_FEWSHOT_CAFE = """마음이 급한 사람일수록, 제일 늦게 느는 운동이 있습니다.

세게 치려는 날은 어김없이 망하고, 힘을 뺀 날은 공이 곱게 나갑니다. 사람을 겸손하게 만드는 운동인데, 신기하게도 결국 힘을 뺄 줄 아는 사람이 공을 더 멀리 보냅니다. 골프도 삶도 그렇더라고요.

웰페리온은 한남동에서 서두르지 않고, 힘 빼는 법부터 천천히 배우는 실내 골프 강습을 운영합니다. 편하게 문의 주세요.

문의 : wellperion.com/ko/inquiry

#한남동골프 #실내골프 #성인골프강습 #골프레슨 #한남동 #스포츠클럽 #웰페리온 #WELLPERION"""

_FEWSHOT_KAKAO = """마음이 급한 사람일수록, 제일 늦게 느는 운동이 있습니다.

세게 치려는 날은 어김없이 망하고, 힘을 뺀 날은 공이 곱게 나갑니다. 사람을 겸손하게 만드는 운동인데, 신기하게도 결국 힘을 뺄 줄 아는 사람이 공을 더 멀리 보냅니다. 골프도 삶도 그렇더라고요.

웰페리온은 한남동에서 서두르지 않고, 힘 빼는 법부터 천천히 배우는 실내 골프 강습을 운영합니다. 편하게 문의 주세요.

문의 : wellperion.com/ko/inquiry"""

_FEWSHOT_DANGGN_TITLE = "한남동 성인 골프 강습 — 힘 뺄 줄 아는 사람이 멀리 보냅니다"
_FEWSHOT_DANGGN_BODY = """마음이 급한 사람일수록, 제일 늦게 느는 운동이 있습니다. 세게 치려는 날은 어김없이 망하고, 힘을 뺀 날은 공이 곱게 나갑니다.

어제 되던 게 오늘은 안 되기도 하는, 사람을 겸손하게 만드는 운동입니다. 그런데 결국 힘을 뺄 줄 아는 사람이 공을 더 멀리 보냅니다. 골프도 삶도 그렇더라고요.

웰페리온은 한남동에서 서두르지 않고, 힘 빼는 법부터 천천히 배우는 실내 골프 강습을 운영합니다. 편하게 문의 주세요.

문의 : wellperion.com/ko/inquiry"""


def _build_prompt(ig_caption: str, topic_title: str) -> str:
    return f"""당신은 웰페리온(한남동 프리미엄 스포츠클럽) 공식 계정 콘텐츠 원고 담당자입니다.
아래 인스타그램(IG) 원고 1개를 입력받아, 이미 발행 중인 4개 채널(네이버 블로그·네이버 카페·카카오 채널·당근채널)의
원고를 각 채널의 실제 톤·구조 그대로 생성하세요. 이 형식은 실제 발행된 골프 강습편(예시)에서 그대로 학습한 것이며,
새로 발명하지 말고 예시의 구조·문장 길이·어미를 그대로 따르세요.

── 절대 규칙 ──
1. IG 원고에 없는 사실·효과·수치를 새로 만들지 마세요(문장 재구성·톤 변환만 허용, 새 정보 추가 금지).
2. 금지어: "피트니스"(→"스포츠클럽"), "하이엔드 프라이빗"·"사교" 뉘앙스 노출 금지.
3. 대놓고 마케팅·설교조 금지. "지금 등록!" 같은 세일즈 압박 금지. 압박 없이 알리는 톤.
4. 문의 안내는 반드시 정확히 이 1줄만 사용: "{CLEAN_CTA_TEXT}" (다른 URL·형식 금지)
5. 마크다운 강조기호(**, ##, _) 사용 금지. 평문만.

── 채널별 형식(예시 그대로 학습) ──
[IG 원고 예시]
{_FEWSHOT_IG}

[블로그 예시] — 격식체(-습니다), IG보다 조금 더 풀어 설명(새 사실 추가 아님, 같은 내용을 격식체로 재구성).
끝에 "{CLEAN_CTA_TEXT}" 1줄 + 해시태그 줄(IG 해시태그와 동일한 태그 구성).
{_FEWSHOT_BLOG}

[카페 예시] — 격식체, 블로그보다 압축(2문단 내외). 끝에 CTA 1줄 + 해시태그 줄
(단, "#프리미엄스포츠클럽" 류 과시적 태그는 제외 — 카페는 동네 커뮤니티 톤 유지).
{_FEWSHOT_CAFE}

[카카오 예시] — 카페 본문과 거의 동일하되 해시태그 줄만 제거.
{_FEWSHOT_KAKAO}

[당근 예시] — 첫 줄에 짧은 제목(후크), 둘째 줄은 "---" 구분선, 그다음 압축 본문(해시태그 없음),
끝에 CTA 1줄.
제목: {_FEWSHOT_DANGGN_TITLE}
본문:
{_FEWSHOT_DANGGN_BODY}

── 이번 입력 ──
[주제] {topic_title or '(제목 미지정 — IG 원고 내용으로 판단)'}
[IG 원고]
{ig_caption.strip()}

── 출력 형식 ──
아래 JSON 객체 하나만 순수 텍스트로 출력하세요(설명문·코드블록·마크다운 없이 JSON만):
{{
  "blog": "블로그 본문 전체(CTA줄+해시태그줄 포함)",
  "cafe": "카페 본문 전체(CTA줄+해시태그줄 포함, 프리미엄 계열 태그 제외)",
  "kakao": "카카오 본문 전체(CTA줄 포함, 해시태그 없음)",
  "danggn_title": "당근 제목 1줄",
  "danggn_body": "당근 본문(CTA줄 포함, 해시태그 없음, 제목·구분선 제외)"
}}"""


def _generate_via_cli(ig_caption: str, topic_title: str) -> dict[str, str] | None:
    try:
        from model_router import run_claude
    except Exception as exc:
        print(f"[WARN] model_router import 실패 — 규칙기반 폴백: {exc}")
        return None

    prompt = _build_prompt(ig_caption, topic_title)
    raw, used_model = run_claude(prompt, label="channel-copy-generator")
    if raw is None:
        print("[WARN] claude CLI 채널 원고 생성 실패(전 모델) — 규칙기반 폴백")
        return None

    try:
        cleaned = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned)
    except Exception as exc:
        print(f"[WARN] 채널 원고 JSON 파싱 실패(model={used_model}): {exc} — 규칙기반 폴백")
        return None

    try:
        blog = str(data["blog"]).strip()
        cafe = str(data["cafe"]).strip()
        kakao = str(data["kakao"]).strip()
        danggn = f"{str(data['danggn_title']).strip()}\n---\n{str(data['danggn_body']).strip()}"
    except Exception as exc:
        print(f"[WARN] 채널 원고 필드 누락({exc}) — 규칙기반 폴백")
        return None

    bodies = {"blog": blog, "cafe": cafe, "kakao": kakao, "danggn": danggn}
    hit = check_forbidden_words("\n".join(bodies.values()))
    if hit:
        print(f"[WARN] LLM 출력에 금지어 검출{hit} — 규칙기반 폴백")
        return None

    print(f"[INFO] 채널 원고 생성 모델 = {used_model}")
    return bodies


# ─────────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────────
def generate_and_write_channel_copy(
    content_folder: Path,
    topic_title: str,
    ig_caption_text: str | None = None,
    force: bool = False,
    use_llm: bool = True,
) -> dict[str, str]:
    """IG 캡션 → 4채널 본문 생성 + content_folder 하위 각 채널 서브폴더에 파일로 기록.

    - 이미 본문 파일이 존재하는 채널은 건드리지 않음(force=True 아니면 수동 작성분 보호).
    - 검수 큐 등록은 하지 않음(publish_register._auto_register_channel_siblings 가 별도 담당).
    - 반환: {채널키: 작성된 파일 경로} — 아무것도 안 썼으면 빈 dict.
    """
    content_folder = Path(content_folder)

    if ig_caption_text is None:
        ig_caption_path = content_folder / "output(인스타그램)" / "ig_caption.txt"
        if not ig_caption_path.exists():
            print(f"[WARN] IG 캡션 없음({ig_caption_path}) — 채널 원고 생성 생략")
            return {}
        ig_caption_text = ig_caption_path.read_text(encoding="utf-8")

    if not ig_caption_text or not ig_caption_text.strip():
        print("[WARN] IG 캡션이 비어있음 — 채널 원고 생성 생략")
        return {}

    targets: dict[str, Path] = {}
    for ch, subdir in CHANNEL_SUBDIR.items():
        path = content_folder / subdir / CHANNEL_FILENAME[ch]
        if path.exists() and not force:
            continue  # 이미 있는 원고는 덮어쓰지 않음(수동 작성분 보호)
        targets[ch] = path

    if not targets:
        return {}

    bodies = None
    if use_llm:
        bodies = _generate_via_cli(ig_caption_text, topic_title)
    if bodies is None:
        bodies = _fallback_channel_bodies(ig_caption_text, topic_title)

    written: dict[str, str] = {}
    for ch, path in targets.items():
        text = (bodies.get(ch) or "").strip()
        if not text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        written[ch] = str(path)
        print(f"[INFO] 채널 원고 생성 — {ch}: {path}")

    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="IG 원고 → 4채널(블로그·카페·카카오·당근) 원고 생성")
    ap.add_argument("content_folder", help="콘텐츠 폴더 경로 (예: instagram/260718_L4_필라테스)")
    ap.add_argument("--title", default="", help="콘텐츠 제목(당근 제목 훅·프롬프트 주제로 사용)")
    ap.add_argument("--force", action="store_true", help="이미 존재하는 채널 원고도 덮어쓰기")
    ap.add_argument("--no-llm", action="store_true", help="claude CLI 생략, 규칙기반 폴백만 사용")
    args = ap.parse_args()

    folder = Path(args.content_folder)
    if not folder.is_absolute():
        folder = ROOT / folder

    written = generate_and_write_channel_copy(
        folder, args.title, force=args.force, use_llm=not args.no_llm
    )
    if written:
        print(f"[DONE] {len(written)}건 생성: {list(written.keys())}")
    else:
        print("[INFO] 생성된 파일 없음(이미 전부 존재하거나 IG 캡션 없음)")


if __name__ == "__main__":
    main()
