#!/usr/bin/env python3
"""콘텐츠 접수(강사·직원 등) → 검수큐 배선 + GM 카드 발신 (2026-07-24 · 배9888)

흐름: 접수 폼(3. 웰페리온 가이드/cmo/intake/instructor_intake.html)이 GAS 시트
      ('마케팅 접수' 탭)에 쌓는 접수 건을 조회 액션(action=rows)으로 가져와
      review_queue.json(cmo/review/)에 status="접수검토" 로 추가하고, 신규 건만
      GM 업무보고방(TELEGRAM_CHAT_ID)에 텔레그램 카드 1장을 보낸다.

★ status="접수검토" 는 기존 발행 파이프라인이 쓰는 "검수대기"·APPROVED_STATES
  ({"승인","승인발행대기","approved"}) 어디에도 속하지 않는다 — ig_review_publish_watcher.py
  (검수대기 필터)·ai_daily_series_card.py(검수대기+AIDAY 필터)·publish_digest.py
  (발행완료 그룹 다이제스트, folder 없는 단독 id 그룹이라 애초에 대상 밖)에 걸리지 않는다.
  근거는 이 파일 하단 주석(§근거) 참조.

GAS exec URL은 하드코딩하지 않는다 — instructor_intake.html 안의 GAS_PROD 상수를
정규식으로 읽어 단일 출처를 유지한다(그 파일이 배포 URL의 정본).

토큰(INTAKE_READ_TOKEN)·봇 토큰(TELEGRAM_BOT_TOKEN)·챗ID(TELEGRAM_CHAT_ID)는 전부
telegram_bot/.env 에서만 읽는다(코드·커밋에 값 금지). INTAKE_READ_TOKEN 미설정이면
"미설정" 안내만 하고 정상 종료(0)한다 — 에러로 취급하지 않는다.

멱등: id = "CMO-INTAKE-{YYYYMMDD}-{성함}-{분류}"(특수문자·공백 제거). review_queue.json에
이미 같은 id가 있으면 재추가하지 않는다. 텔레그램 카드도 scripts/.intake_card_sent.json
에 id를 기록해 재발송하지 않는다.

배 등록(2026-08-04 GM 승인 · 배9888 후속 사고): 텔레그램 카드는 발송 순간을 놓치면
묻힌다(강사 이수지 접수 5일 방치 실측 — 알림은 갔지만 밤 9시반 한 번뿐이라 안 보임).
신규 접수마다 queue_dispatch.py 를 서브프로세스로 호출해 시모(CMO) 배로도 등록한다
(약속 L15 — 큐에 없으면 항로에도 없다). 배 등록 여부도 scripts/.intake_card_sent.json
같은 항목에 ship_created 키로 기록(멱등). 배 생성이 실패해도 접수 등록·카드 발송
흐름은 죽지 않는다(try/except로 격리).

플래그: --dry-run(큐 추가·텔레그램 발송 없이 무엇을 할지만 출력) · --once(1회 실행 ·
반복 루프 없음, 향후 스케줄러 연동 대비 플래그만 수용) · --include-test(테스트 접수행 포함)
· --limit N(조회 건수, 기본 500).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
INTAKE_HTML = ROOT / "3. 웰페리온 가이드" / "cmo" / "intake" / "instructor_intake.html"
ENV_FILE = ROOT / "telegram_bot" / ".env"
SENT_STATE_PATH = ROOT / "scripts" / ".intake_card_sent.json"
QUEUE_DISPATCH_PATH = ROOT / "scripts" / "queue_dispatch.py"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_queue_util import (  # noqa: E402
    load_review_queue,
    mutate_review_queue,
    SkipSave,
    QueueLockTimeout,
)

try:  # 발신 공용 관문(페이싱+429재시도+검수+로깅) — best-effort
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(token, chat_id, text, **k):
        return False

try:  # GM의 일요일 승인 카드 — 기존 검수카드 발송기 재사용(새 텔레그램 호출 금지)
    from send_review_card import send_card as _send_review_card
except Exception:
    def _send_review_card(item, **k):
        return False

# 시트 헤더 정본(.deploy-instructor/instructor_intake.js INTAKE_HEADER 와 동일 순서) —
# 헤더가 깨져 조회 응답이 col1..col9 로 올 때 이 순서로 이름을 되붙인다.
INTAKE_HEADER = ["접수일시", "성함", "분류", "한줄소개", "회원이얻는것", "사진링크", "영상링크", "드라이브폴더", "상태"]

_TEST_MARKERS = ("__TEST__", "__배포검증__", "__폼검증__")
_ID_SAFE_RE = re.compile(r"[^0-9A-Za-z가-힣]+")
_GAS_URL_RE = re.compile(r'GAS_PROD\s*=\s*"([^"]+)"')

# "GM의 일요일" 접수(분류 값 정확히 이 문자열) — 다른 분류는 기존 접수검토 경로 그대로.
SUNDAY_TEAM = "GM의 일요일"
_SUNDAY_LINE_RE = re.compile(r"^0([234])\s+(.*)$")
_PUBLISH_AT_RE = re.compile(r"발행시점\s*·\s*(\S+)")
_DRIVE_ID_RE = re.compile(r"/d/([a-zA-Z0-9_-]{10,})")
_DRIVE_ID_QS_RE = re.compile(r"[?&]id=([a-zA-Z0-9_-]{10,})")
_SUNDAY_ASPECT = (1080, 1350)
_SUNDAY_CREAM = (0xF4, 0xF1, 0xEA)
_SUNDAY_DARK = (0x23, 0x20, 0x1C)
_SUNDAY_ORANGE = (0xF0, 0xB2, 0x7A)


# ---------------------------------------------------------------------------
# .env 로더 (publish_digest.py 와 동형 — os.environ 우선, 없으면 telegram_bot/.env)
# ---------------------------------------------------------------------------
def _load_env_val(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if val:
        return val
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


def _extract_gas_url() -> str:
    """접수 폼 HTML에서 GAS_PROD exec URL을 뽑는다(단일 출처 — 하드코딩 금지)."""
    if not INTAKE_HTML.exists():
        return ""
    text = INTAKE_HTML.read_text(encoding="utf-8")
    m = _GAS_URL_RE.search(text)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# GAS 조회
# ---------------------------------------------------------------------------
def fetch_intake_rows(gas_url: str, token: str, limit: int = 500):
    """action=rows 조회. 반환: (rows list, error_message). 실패 시 rows=None."""
    qs = urllib.parse.urlencode({"action": "rows", "token": token, "limit": str(limit)})
    url = f"{gas_url}?{qs}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:  # urllib 은 GET 리다이렉트 기본 추적
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        return None, f"GAS 조회 네트워크 오류: {e}"
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return None, f"GAS 응답 JSON 파싱 실패: {e}"
    if not data.get("ok"):
        return None, f"GAS 조회 실패 응답: {data.get('error') or data.get('err') or data}"
    return data.get("rows") or [], None


def normalize_row(row: dict) -> dict:
    """실제 헤더명(호환)·col1..col9 폴백(헤더 깨짐) 둘 다 흡수해 표준 키로 통일."""
    out = {}
    for i, key in enumerate(INTAKE_HEADER, start=1):
        if key in row and row[key] not in (None, ""):
            out[key] = row[key]
        else:
            out[key] = row.get(f"col{i}", "")
    out["_row"] = row.get("_row")
    return out


def is_test_row(row: dict) -> bool:
    combined = f"{row.get('성함', '')}{row.get('분류', '')}"
    return any(marker in combined for marker in _TEST_MARKERS)


def _id_safe(s: str) -> str:
    return _ID_SAFE_RE.sub("", str(s or "").strip())


def make_id(row: dict) -> str:
    ts = str(row.get("접수일시") or "")
    date_part = re.sub(r"[^0-9]", "", ts[:10]) or datetime.now().strftime("%Y%m%d")
    date_part = date_part[:8] if len(date_part) >= 8 else date_part
    name = _id_safe(row.get("성함"))
    cat = _id_safe(row.get("분류"))
    return f"CMO-INTAKE-{date_part}-{name}-{cat}"


def build_item(row: dict, item_id: str) -> dict:
    """review_queue.json 기존 스키마(title/channel/account/folder/slides/caption/
    location/collaborators/mentions/status/preview/id/note)에 맞춘 신규 항목.
    접수 원문은 intake 키에 보존(기존 항목 필드는 건드리지 않음)."""
    photo_first = (row.get("사진링크") or "").split("\n")[0].strip()
    return {
        "title": f"콘텐츠 접수 — {row.get('성함', '')} ({row.get('분류', '')})",
        "channel": "콘텐츠 접수",
        "account": "wellperion",
        "folder": "",
        "slides": [],
        "caption": "",
        "location": "",
        "collaborators": [],
        "mentions": [],
        "status": "접수검토",
        "preview": photo_first,
        "id": item_id,
        "note": f"[콘텐츠 접수 {row.get('접수일시', '')}] cmo_intake_to_review.py 자동 수집(배9888)",
        "intake": {
            "성함": row.get("성함", ""),
            "분류": row.get("분류", ""),
            "한줄소개": row.get("한줄소개", ""),
            "회원이얻는것": row.get("회원이얻는것", ""),
            "사진링크": row.get("사진링크", ""),
            "영상링크": row.get("영상링크", ""),
            "드라이브폴더": row.get("드라이브폴더", ""),
            "접수일시": row.get("접수일시", ""),
        },
    }


# ---------------------------------------------------------------------------
# "GM의 일요일" 분기 — 사진+문장 접수를 캐러셀 4장으로 제작해 검수대기로 등록.
# 다른 분류(강사소개 등)는 위 build_item()/접수검토 경로 그대로(회귀 0).
# ---------------------------------------------------------------------------
def is_sunday_row(row: dict) -> bool:
    return (row.get("분류") or "").strip() == SUNDAY_TEAM


def _parse_sunday_benefit(benefit: str) -> dict:
    """GM의일요일.html 이 만든 benefit 텍스트를 문장1~3·본문 캡션·해시태그로 분해.
    형식(정확히 이 모양): '02 문장1\\n03 문장2\\n04 문장3\\n\\n캡션…\\n\\n#해시태그…\\n\\n계정 @…'"""
    lines = (benefit or "").replace("\r\n", "\n").split("\n")
    numbered: dict[str, str] = {}
    header_end = 0
    for i, line in enumerate(lines):
        m = _SUNDAY_LINE_RE.match(line.strip())
        if m:
            numbered[m.group(1)] = m.group(2).strip()
            header_end = i + 1
        elif numbered:
            break  # 02/03/04 블록 종료(빈 줄 등)

    rest = lines[header_end:]

    # cut_idx = 캡션이 끝나는 지점 / hashtag_idx = 해시태그 줄(있을 때만)
    hashtag_idx = None
    cut_idx = None
    for i, line in enumerate(rest):
        s = line.strip()
        if s.startswith("#"):
            hashtag_idx = cut_idx = i
            break
        if s.startswith("계정 @") or s.startswith("발행시점"):
            cut_idx = i              # 해시태그가 없어도 여기서 캡션을 끊는다
            break

    # 해시태그가 없어도 '계정 @…'·'발행시점 · …' 앞에서 캡션을 끊는다(내부 표기가 게시글 본문에 새지 않게).
    caption_lines = rest[:cut_idx] if cut_idx is not None else list(rest)
    caption_lines = [ln for ln in caption_lines if not ln.strip().startswith("발행시점")]
    while caption_lines and not caption_lines[0].strip():
        caption_lines.pop(0)
    while caption_lines and not caption_lines[-1].strip():
        caption_lines.pop()

    pub_m = _PUBLISH_AT_RE.search(benefit or "")
    pub_raw = pub_m.group(1) if pub_m else ""
    publish_at = "" if pub_raw in ("", "즉시") else pub_raw

    return {
        "line1": numbered.get("2", ""),
        "line2": numbered.get("3", ""),
        "line3": numbered.get("4", ""),
        "caption": "\n".join(caption_lines).strip(),
        "hashtags": rest[hashtag_idx].strip() if hashtag_idx is not None else "",
        "publish_at": publish_at,
    }


def _drive_file_id(url: str) -> str:
    m = _DRIVE_ID_RE.search(url) or _DRIVE_ID_QS_RE.search(url)
    return m.group(1) if m else ""


def _download_drive_image(url: str, dest: Path) -> bool:
    """드라이브 공유 URL → 파일ID 추출 → uc?export=download 로 원본 저장.
    HTML(용량초과 확인 페이지 등) 응답이면 실패로 본다(조용히 성공 처리 금지)."""
    fid = _drive_file_id(url)
    if not fid:
        return False
    dl_url = f"https://drive.google.com/uc?export=download&id={fid}"
    try:
        req = urllib.request.Request(dl_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            ctype = resp.headers.get("Content-Type", "")
            data = resp.read()
    except Exception:
        return False
    looks_html = "text/html" in ctype.lower() or data[:15].strip().lower().startswith(b"<!doctype") \
        or data[:5].lower() == b"<html"
    if looks_html:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def _compose_sunday_cover(photo: Path, title: str, output: Path) -> None:
    """post_1 — 표지: 사진 + 위→아래 그라디언트 + 하단 제목(줄바꿈 유지) + 상단 라벨."""
    from slide_compositor import load_and_fit, apply_dark_gradient, load_font, draw_text_block
    from brand_constants import BRAND_PRESETS

    w, h = _SUNDAY_ASPECT
    img = load_and_fit(photo, w, h)
    img = apply_dark_gradient(img, BRAND_PRESETS["main"], "bottom")
    draw = ImageDraw.Draw(img)
    margin = int(w * 0.07)

    label_font = load_font("medium", int(w * 0.026))
    cx = margin
    label_y = int(h * 0.06)
    for ch in "GM의 일요일":
        draw.text((cx, label_y), ch, font=label_font, fill=(255, 255, 255))
        bb = label_font.getbbox(ch)
        cx += (bb[2] - bb[0]) + int(label_font.size * 0.15)

    title_font = _sunday_serif(int(w * 0.078))          # GM 시안 = 세리프 제목
    lines = (title or "GM의 일요일").split("\n")
    line_h = int(title_font.size * 1.32)
    ty = h - len(lines) * line_h - int(h * 0.09)
    draw_text_block(draw, lines, title_font, (255, 255, 255), margin, ty, line_spacing=1.32)

    output.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(output, "JPEG", quality=92, optimize=True)


def _sunday_serif(size: int):
    """GM 시안이 제목·문장에 쓰는 한글 세리프(Gowun Batang).

    브랜드 폰트는 Pretendard(고딕)뿐이라 세리프를 따로 들였다(OFL · 같은 폰트 폴더).
    폰트가 없으면 조용히 깨지지 말고 기존 고딕으로 떨어진다 — 글자가 두부(□)로 나가는 것보다
    낫고, 사람이 알아볼 수 있게 경고를 남긴다.
    """
    from slide_compositor import load_font
    from brand_constants import FONT_DIR

    path = FONT_DIR / "GowunBatang-Bold.ttf"
    if not path.exists():
        print(f"[WARN] 세리프 폰트 없음({path}) — 고딕으로 대체", file=sys.stderr)
        return load_font("semibold", size)
    return ImageFont.truetype(str(path), size)


def _compose_sunday_photo_card(photo: Path, caption: str, output: Path) -> None:
    """post_2/post_3 — 사진(상단 62%) + 문장(하단, 크림 배경)."""
    from slide_compositor import load_and_fit, load_font, wrap_text, draw_text_block

    w, h = _SUNDAY_ASPECT
    photo_h = int(h * 0.62)
    canvas = Image.new("RGB", (w, h), _SUNDAY_CREAM)
    canvas.paste(load_and_fit(photo, w, photo_h), (0, 0))

    draw = ImageDraw.Draw(canvas)
    margin = int(w * 0.09)
    body_font = _sunday_serif(int(w * 0.042))           # GM 시안 = 세리프 문장
    lines = wrap_text(caption or "", body_font, w - 2 * margin)
    line_h = int(body_font.size * 1.5)
    text_y = photo_h + max(0, (h - photo_h - len(lines) * line_h) // 2)
    draw_text_block(draw, lines, body_font, _SUNDAY_DARK, margin, text_y, line_spacing=1.5)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "JPEG", quality=92, optimize=True)


def _compose_sunday_think(caption: str, output: Path) -> None:
    """post_4 — 사진 없음: 어두운 배경(#23201C) + 주황(#F0B27A) 바 + 문장3."""
    from slide_compositor import load_font, wrap_text, draw_text_block

    w, h = _SUNDAY_ASPECT
    canvas = Image.new("RGB", (w, h), _SUNDAY_DARK)
    draw = ImageDraw.Draw(canvas)
    margin = int(w * 0.10)
    body_font = _sunday_serif(int(w * 0.046))           # GM 시안 = 세리프 문장
    lines = wrap_text(caption or "", body_font, w - 2 * margin)
    line_h = int(body_font.size * 1.6)
    total_h = len(lines) * line_h
    bar_w, bar_h = int(w * 0.06), 4
    start_y = max(0, (h - total_h) // 2 - int(h * 0.03))
    draw.rectangle([(margin, start_y), (margin + bar_w, start_y + bar_h)], fill=_SUNDAY_ORANGE)
    draw_text_block(draw, lines, body_font, (255, 255, 255), margin, start_y + int(h * 0.05), line_spacing=1.6)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "JPEG", quality=92, optimize=True)


def _compose_sunday_montage(slides: list[Path], output: Path) -> None:
    """검수 카드용 몽타주 — 완성 슬라이드를 한 장으로 이어 붙인다.

    GM 이 텔레그램 카드에서 '실제로 올라갈 그림'을 보고 승인하게 하는 것이 목적이다.
    파일 이름은 send_review_card._preview_photo 가 찾는 규약(_검수_미리보기_*.png)을 따른다.
    """
    imgs = [Image.open(p).convert("RGB") for p in slides if p.exists()]
    if not imgs:
        raise FileNotFoundError("몽타주로 붙일 슬라이드가 없다")
    cell_w = 540
    cells = [im.resize((cell_w, int(im.height * cell_w / im.width))) for im in imgs]
    gap = 12
    total_w = sum(c.width for c in cells) + gap * (len(cells) - 1)
    total_h = max(c.height for c in cells)
    canvas = Image.new("RGB", (total_w, total_h), _SUNDAY_CREAM)
    x = 0
    for c in cells:
        canvas.paste(c, (x, 0))
        x += c.width + gap
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PNG", optimize=True)


def build_sunday_item(row: dict, item_id: str) -> dict | None:
    """'GM의 일요일' 접수 1건 → review_queue 항목(검수대기) 빌드. 사진 0장이거나
    다운로드가 전부 실패하면 None(경고는 여기서 stderr 로 남김 — 조용한 성공 처리 금지)."""
    intro = (row.get("한줄소개") or "").strip()
    parsed = _parse_sunday_benefit(row.get("회원이얻는것") or "")
    links = [u.strip() for u in (row.get("사진링크") or "").split("\n") if u.strip()]
    if not links:
        print(f"[WARN] GM의 일요일 접수 사진 0장 — 제작 불가: {item_id}", file=sys.stderr)
        return None

    date8 = re.sub(r"[^0-9]", "", str(row.get("접수일시") or ""))[:8]
    date6 = date8[2:8] if len(date8) == 8 else datetime.now().strftime("%y%m%d")
    slug = _id_safe(intro)[:24] or "무제"
    folder_rel = f"instagram/namuk.wellperion/{date6}_GM일요일_{slug}"
    src_dir = ROOT / folder_rel / "src"
    out_dir = ROOT / folder_rel / "output"

    downloaded: list[Path] = []
    for i, url in enumerate(links, start=1):
        dest = src_dir / f"src_{i:02d}.jpg"
        if _download_drive_image(url, dest):
            downloaded.append(dest)
        else:
            print(f"[WARN] GM의 일요일 사진 다운로드 실패(건너뜀): {item_id} #{i} {url}", file=sys.stderr)

    if not downloaded:
        print(f"[WARN] GM의 일요일 접수 다운로드 전량 실패 — 제작 불가: {item_id}", file=sys.stderr)
        return None

    def pick(idx: int) -> Path:
        return downloaded[idx] if idx < len(downloaded) else downloaded[-1]

    slides_rel = []
    try:
        _compose_sunday_cover(pick(0), intro, out_dir / "post_1.jpg")
        slides_rel.append(f"{folder_rel}/output/post_1.jpg")
        _compose_sunday_photo_card(pick(1), parsed["line1"], out_dir / "post_2.jpg")
        slides_rel.append(f"{folder_rel}/output/post_2.jpg")
        _compose_sunday_photo_card(pick(2), parsed["line2"], out_dir / "post_3.jpg")
        slides_rel.append(f"{folder_rel}/output/post_3.jpg")
        _compose_sunday_think(parsed["line3"], out_dir / "post_4.jpg")
        slides_rel.append(f"{folder_rel}/output/post_4.jpg")
    except Exception as exc:
        print(f"[WARN] GM의 일요일 슬라이드 제작 실패: {item_id}: {exc}", file=sys.stderr)
        return None

    # 검수 카드에 붙일 몽타주 — send_review_card._preview_photo 가 찾는 이름 규약
    # (folder/output/_검수_미리보기_*.png)을 그대로 따른다. 이 파일이 없으면 카드가
    # 이미지 없이 글자로만 나가, GM 이 '결과물'을 못 보고 승인해야 한다.
    try:
        _compose_sunday_montage(
            [ROOT / s for s in slides_rel], out_dir / "_검수_미리보기_4장.png"
        )
    except Exception as exc:                       # 몽타주 실패가 접수 자체를 죽이면 안 된다
        print(f"[WARN] GM의 일요일 검수 미리보기 생성 실패(카드는 글자로 나갑니다): {item_id}: {exc}",
              file=sys.stderr)

    caption_full = parsed["caption"]
    if parsed["hashtags"]:
        caption_full = f"{caption_full}\n\n{parsed['hashtags']}" if caption_full else parsed["hashtags"]
    (ROOT / folder_rel / "caption.md").write_text(caption_full, encoding="utf-8")

    return {
        "title": f"GM의 일요일 — {intro}",
        "channel": "인스타그램 (namuk.wellperion)",
        "account": "namuk.wellperion",
        "folder": folder_rel,
        "slides": slides_rel,
        "caption": caption_full,
        "location": "웰페리온 스포츠클럽",
        "collaborators": [],
        "mentions": [],
        "status": "검수대기",
        "preview": slides_rel[0],
        "id": item_id,
        "publish_at": parsed["publish_at"],
        "note": f"[GM의 일요일 접수 {row.get('접수일시', '')}] cmo_intake_to_review.py 자동 제작(GM의일요일 분기)",
    }


# ---------------------------------------------------------------------------
# 텔레그램 카드 (GM 업무보고방 · 버튼 없음)
# ---------------------------------------------------------------------------
def _send_telegram_card(bot_token: str, chat_id: str, item: dict) -> bool:
    intake = item.get("intake") or {}
    lines = [
        f"🎬 새 콘텐츠 접수 — {intake.get('성함', '')} ({intake.get('분류', '')})",
        "",
    ]
    if intake.get("한줄소개"):
        lines.append(f"한줄소개: {intake['한줄소개']}")
    if intake.get("회원이얻는것"):
        lines.append(f"회원이 얻는 것: {intake['회원이얻는것']}")
    if intake.get("드라이브폴더"):
        lines.append(f"드라이브 폴더: {intake['드라이브폴더']}")
    if intake.get("접수일시"):
        lines.append(f"접수일시: {intake['접수일시']}")
    message = "\n".join(lines)
    return _tg_send(bot_token, chat_id, message, source="cmo_intake_to_review",
                     extra={"disable_web_page_preview": "true"}, timeout=10)


# ---------------------------------------------------------------------------
# 시모(CMO) 배 등록 — 기존 배 생성 관문(queue_dispatch.py)을 서브프로세스로 재사용.
# 큐 락 직렬화·중복 방지·배번호 부여는 전부 그쪽 소유(새 큐 쓰기 코드 금지 · 약속 L01·L21).
# ---------------------------------------------------------------------------
def _create_review_ship(item: dict) -> str:
    """접수 1건을 시모 배로 큐(status/_queue.json)에 올린다. 실패 시 예외 전파
    (호출부에서 try/except로 흡수 — 배 생성 실패가 접수 흐름을 죽이면 안 된다)."""
    intake = item.get("intake") or {}
    name = intake.get("성함", "")
    cat = intake.get("분류", "")
    note = "\n".join([
        f"한줄소개: {intake.get('한줄소개', '') or '(없음)'}",
        f"회원이 얻는 것: {intake.get('회원이얻는것', '') or '(없음)'}",
        f"사진: {'있음' if intake.get('사진링크') else '없음'} / 영상: {'있음' if intake.get('영상링크') else '없음'}",
        f"드라이브 폴더: {intake.get('드라이브폴더', '') or '(없음)'}",
        f"접수일시: {intake.get('접수일시', '')}",
    ])
    # ★--sender 는 역할명이 아니라 "콘텐츠접수" 를 넘긴다.
    #   --sender cmo 는 쓸 수 없고(queue_dispatch 는 to==sender 를 --mine 없이는 거부),
    #   기본값(ceo)을 쓰면 note 접두가 "[웰리 → 시모 전달]" 로 찍혀 **웰리가 보낸 것처럼 보인다**
    #   — 사람이 나중에 "웰리가 왜 이걸 보냈지"로 오해한다. --mine("자가점검")도 사실이 아니다.
    #   queue_dispatch 는 ROLES 에 없는 sender 값을 원문 그대로 접두에 쓰므로
    #   "[콘텐츠접수 → 시모 전달 …]" 이 되어 출처가 정확해진다(관문 수정 0).
    args = [
        sys.executable, str(QUEUE_DISPATCH_PATH),
        "--to", "cmo",
        "--sender", "콘텐츠접수",
        "--title", f"콘텐츠 접수 — {name} ({cat})",
        "--note", note,
        "--next", "사진 확인 → 슬라이드 제작 → 검수큐(검수대기)로 올려 GM 승인 카드 발송",
        "--priority", "⛵돛단배",
        "--audience", "office",
        "--reversible", "yes",
        "--work-type", "update",
    ]
    proc = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"rc={proc.returncode}: {(proc.stderr or proc.stdout).strip()[:200]}")
    out = proc.stdout.strip()
    return out.splitlines()[0] if out else "ok"


def _load_sent_state() -> dict:
    if not SENT_STATE_PATH.exists():
        return {}
    try:
        data = json.loads(SENT_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_sent_state(state: dict) -> None:
    SENT_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="콘텐츠 접수 → 검수큐 배선 + GM 카드 발신")
    ap.add_argument("--dry-run", action="store_true", help="큐 추가·텔레그램 발송 없이 무엇을 할지만 출력")
    ap.add_argument("--once", action="store_true", help="1회 실행(반복 루프 없음 — 현재 기본 동작과 동일)")
    ap.add_argument("--include-test", action="store_true", help="테스트 접수행(__TEST__ 등)도 포함")
    ap.add_argument("--limit", type=int, default=500, help="GAS 조회 건수(기본 500)")
    args = ap.parse_args()

    gas_url = _extract_gas_url()
    if not gas_url:
        print(f"[ERROR] GAS_PROD URL을 {INTAKE_HTML} 에서 찾지 못함")
        return 1

    token = _load_env_val("INTAKE_READ_TOKEN")
    if not token:
        print("[INFO] INTAKE_READ_TOKEN 미설정 — telegram_bot/.env 에 값 추가 필요(정상 종료)")
        return 0

    raw_rows, err = fetch_intake_rows(gas_url, token, args.limit)
    if err:
        print(f"[ERROR] {err}")
        return 1

    rows = [normalize_row(r) for r in raw_rows]
    total_fetched = len(rows)

    skipped_test = 0
    if not args.include_test:
        kept = [r for r in rows if not is_test_row(r)]
        skipped_test = len(rows) - len(kept)
        rows = kept

    existing = load_review_queue()
    existing_ids = {it.get("id") for it in existing if isinstance(it, dict)}

    candidates = []
    for row in rows:
        item_id = make_id(row)
        if item_id in existing_ids:
            continue
        candidates.append((item_id, row))

    print(
        f"[INFO] 조회 {total_fetched}건 · 테스트제외 {skipped_test}건 · "
        f"기존등록 {len(rows) - len(candidates)}건 · 신규후보 {len(candidates)}건"
    )
    for item_id, row in candidates:
        print(f"  - {item_id}: 성함={row.get('성함')} 분류={row.get('분류')} 접수일시={row.get('접수일시')}")

    if not candidates:
        print("[INFO] 신규 접수 없음 — 종료")
        return 0

    if args.dry_run:
        print("[DRY-RUN] review_queue.json 추가·텔레그램 발송·GM의 일요일 제작 전부 생략")
        return 0

    # GM의 일요일 분기 — 다운로드·슬라이드 제작(무거운 작업)은 큐 락 밖에서 미리 끝낸다.
    # 실패(사진 0장·다운로드 전량 실패·합성 예외)는 build_sunday_item 이 None 을 반환하며
    # stderr 에 이미 경고를 남긴다 — 이번 실행에서는 등록하지 않고 다음 폴링에서 재시도.
    sunday_items: dict[str, dict] = {}
    other_candidates = []
    for item_id, row in candidates:
        if is_sunday_row(row):
            try:
                built = build_sunday_item(row, item_id)
            except Exception as exc:
                built = None
                print(f"[WARN] GM의 일요일 처리 중 예외(건너뜀, 다른 접수는 계속): {item_id}: {exc}", file=sys.stderr)
            if built is not None:
                sunday_items[item_id] = built
        else:
            other_candidates.append((item_id, row))

    added_items: list[dict] = []

    def _mutator(items: list) -> list:
        current_ids = {it.get("id") for it in items if isinstance(it, dict)}
        for item_id, item in sunday_items.items():
            if item_id in current_ids:
                continue
            items.append(item)
            added_items.append(item)
        for item_id, row in other_candidates:
            if item_id in current_ids:
                continue
            item = build_item(row, item_id)
            items.append(item)
            added_items.append(item)
        if not added_items:
            raise SkipSave
        return items

    try:
        mutate_review_queue(_mutator, holder="cmo_intake_to_review")
    except QueueLockTimeout as e:
        print(f"[ERROR] review_queue 락 획득 실패 — 저장 중단: {e}")
        return 1

    if not added_items:
        print("[INFO] 락 안 재확인 결과 신규 없음(동시 실행으로 이미 추가됨) — 종료")
        return 0

    print(f"[INFO] review_queue.json 에 {len(added_items)}건 추가 완료(status=접수검토)")

    sent_state = _load_sent_state()

    # 시모(CMO) 배 등록 — GM의 일요일은 건너뛴다(승인 카드가 곧 할 일이라 배가 겹친다).
    # 다른 분류는 텔레그램 발송 성공 여부와 무관하게 시도(알림이 묻혀도 배는 항로에
    # 남아야 한다 · 배9888 후속 사고). 항목별 try/except로 격리.
    ship_count = 0
    non_sunday_added = [it for it in added_items if it["id"] not in sunday_items]
    for item in non_sunday_added:
        iid = item["id"]
        entry = sent_state.setdefault(iid, {})
        if entry.get("ship_created"):
            continue
        try:
            result = _create_review_ship(item)
            entry["ship_created"] = True
            entry["ship_result"] = result
            ship_count += 1
        except Exception as e:
            entry["ship_created"] = False
            print(f"[WARN] 시모 배 생성 실패(접수 흐름은 계속 진행): {iid}: {e}")
    print(f"[INFO] 시모(CMO) 배 등록 {ship_count}/{len(non_sunday_added)}건")

    bot_token = _load_env_val("TELEGRAM_BOT_TOKEN")
    chat_id = _load_env_val("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("[WARN] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 미설정 — 카드 발송 생략")
        _save_sent_state(sent_state)
        return 0

    # GM의 일요일 = 승인카드(send_review_card, ✅/❌ 버튼) / 그 외 = 기존 단순 알림 카드.
    # 단순 알림(_send_telegram_card)을 GM의 일요일에 같이 보내면 중복 발신이 된다.
    sent_count = 0
    review_card_count = 0
    for item in added_items:
        iid = item["id"]
        entry = sent_state.setdefault(iid, {})
        if entry.get("sent_at"):
            continue
        if iid in sunday_items:
            ok = _send_review_card(item)
            if ok:
                review_card_count += 1
            else:
                print(f"[WARN] GM의 일요일 승인 카드 발송 실패: {iid}")
        else:
            ok = _send_telegram_card(bot_token, chat_id, item)
            if ok:
                sent_count += 1
            else:
                print(f"[WARN] 텔레그램 카드 발송 실패: {iid}")
        entry["sent_at"] = datetime.now().isoformat(timespec="seconds")
        entry["ok"] = ok
    _save_sent_state(sent_state)
    print(f"[INFO] GM 업무보고방 카드 발송 {sent_count}/{len(non_sunday_added)}건 · "
          f"GM의 일요일 승인카드 {review_card_count}/{len(sunday_items)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# §근거 — status="접수검토" 가 기존 발행 파이프라인에 걸리지 않는 이유
# ---------------------------------------------------------------------------
# 1) scripts/ig_review_publish_watcher.py:336
#      `if it.get("status") != "검수대기": continue`  ← "접수검토" != "검수대기" → 스킵.
# 2) scripts/ig_review_publish_watcher.py:908
#      `if it.get("status") not in APPROVED_STATES: ...`
#      APPROVED_STATES(83행) = {"승인", "승인발행대기", "approved"} ← "접수검토" 미포함.
# 3) scripts/ai_daily_series_card.py:76
#      `if item.get("status") == "검수대기"` 이면서 id 에 "-AIDAY" 포함 요구(70행 주석) —
#      이중으로 걸러짐("접수검토"도 아니고 id 도 "CMO-INTAKE-" 접두라 AIDAY 아님).
# 4) scripts/publish_digest.py
#      send_publish_digest() 는 watcher 가 "이번 실행에서 발행완료로 전환된 항목"만 넘겨
#      호출(위 1·2 에서 이미 걸러진 항목은 애초에 여기 도달 안 함). 설사 그룹 판정이
#      돌아도 _base_key()(136행)는 folder 가 빈 문자열이면 id 로 그룹키를 만들어
#      (141행) 우리 항목만의 고유 그룹이 되므로 다른 콘텐츠 발행 판정과 섞이지 않는다.
