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
import shutil
import subprocess
import sys
import tempfile
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

# 시리즈 정의 — 정본은 코드가 아니라 아래 JSON 한 파일이다(약속 L01).
#   접수 화면(cmo/sunday/GM의일요일.html)이 같은 파일을 읽어 고를 목록을 만들고,
#   여기서는 이름·해시태그·폴더·계정을 뽑는다. 새 시리즈 = JSON 한 칸 추가, 코드 무변경.
# ★2026-08-23 GM 확정 두 가지가 이 구조의 이유다.
#   ①"GM의 일요일" → "어떤 하루" — 요일과 사람 이름을 뺐다(평일에도 쓰고, 누구의 하루로도 읽히게).
#   ②"둘다" — 올리는 사람도 넓히고(이름을 적어 넣는다) 시리즈도 넓힌다(목록에서 고른다).
SERIES_FILE = ROOT / "3. 웰페리온 가이드" / "cmo" / "sunday" / "series.json"


def _load_series() -> list:
    """시리즈 목록. 파일이 깨지거나 없으면 기본 1건으로 버틴다 — 접수 자체가 멈추면 안 된다."""
    try:
        rows = json.loads(SERIES_FILE.read_text(encoding="utf-8")).get("series") or []
        if rows:
            return rows
    except Exception as exc:
        print(f"[WARN] 시리즈 목록을 못 읽었습니다(기본값으로 진행): {exc}", file=sys.stderr)
    return [{"key": "어떤 하루", "name": "어떤 하루", "tag": "#어떤하루", "slug": "어떤하루",
             "account": "namuk.wellperion", "channel": "인스타그램 (namuk.wellperion)",
             "aka": ["GM의 일요일"], "brief": "", "enabled": True}]


SERIES_LIST = _load_series()


def series_of(team: str) -> dict | None:
    """접수 행의 분류 값 → 시리즈 정의. 옛 이름(aka)으로 들어온 건도 찾아 준다."""
    t = (team or "").strip()
    for s in SERIES_LIST:
        if t == s.get("key") or t == s.get("name") or t in (s.get("aka") or []):
            return s
    return None


# 기본 시리즈(목록 첫 줄) — 시리즈를 못 찾은 자리에서 쓰는 폴백값.
_S0 = SERIES_LIST[0]
SERIES_NAME = _S0.get("name", "어떤 하루")
SERIES_TAG = _S0.get("tag", "#어떤하루")
SERIES_SLUG = _S0.get("slug", "어떤하루")
SUNDAY_TEAM = SERIES_NAME
# 시리즈 슬로건 (GM 확정 2026-08-05) — 이 시리즈 글이 향하는 한 문장.
SUNDAY_SLOGAN = "행복은 특별한 날에 오는 게 아니라, 평범한 하루를 함께 보낼 때 온다."
# 글의 기준 (GM 2026-08-05) — 설명글이 아니라 기록이다.
SUNDAY_STANDARD = "남에게 보이는 글이면서, 나중에 내가 다시 읽을 기록"
_SUNDAY_LINE_RE = re.compile(r"^(\d{2})(?:\s+(.*))?$")   # 02·03·…·10 (빈 문장도 자리를 지킨다)
_SUNDAY_THINK_RE = re.compile(r"^생각\s*·\s*(.*)$")
_PUBLISH_AT_RE = re.compile(r"발행시점\s*·\s*(\S+)")
# 표지에서 보여줄 지점(0~1) — 화면에서 끌어 맞춘 값. 없으면 가운데(0.5,0.5).
_FACT_RE = re.compile(  # 사진으로 알 수 없는 사실(접수 화면 입력) — 키를 먼저 alternation 으로
    r"^(컨셉|슬로건|장소|날짜|추천 시간|추천|누구와|좋았던 점|비용·준비물|다시 간다면)\s*·\s*(.+)$"
)
_COVER_FOCUS_RE = re.compile(r"표지위치\s*·\s*([0-9.]+)\s*,\s*([0-9.]+)(?:\s*,\s*([0-9.]+))?")
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
    """접수 1건의 고유 id. ★날짜에 더해 '시각'까지 넣는다.

    2026-08-05 실사고: 같은 사람이 같은 분류로 하루에 두 번 올리면 id 가 똑같아
    (날짜+성함+분류) 두 번째 접수가 '이미 등록됨'으로 조용히 버려졌다. GM 이 12:39 에
    올린 뒤 16:35 에 정보를 다 채워 다시 올렸는데 그 두 번째가 통째로 무시됐다.
    시각(HHMM)을 넣어 같은 날 여러 번 올려도 각각 살아 있게 한다.
    접수일시는 시트에 고정된 값이라 멱등성(같은 행 = 같은 id)은 그대로다.
    """
    ts = str(row.get("접수일시") or "")
    digits = re.sub(r"[^0-9]", "", ts)
    if len(digits) >= 12:
        stamp = digits[:8] + "-" + digits[8:12]      # YYYYMMDD-HHMM
    elif len(digits) >= 8:
        stamp = digits[:8]
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
    name = _id_safe(row.get("성함"))
    cat = _id_safe(row.get("분류"))
    return f"CMO-INTAKE-{stamp}-{name}-{cat}"


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
# "GM의 일요일" 분기 — 사진+문장 접수를 캐러셀로 제작해 검수대기로 등록.
# 장수는 올린 사진이 정한다: 표지 1 + 나머지 사진 1장당 문장 카드 1 + 생각 1.
# 다른 분류(강사소개 등)는 위 build_item()/접수검토 경로 그대로(회귀 0).
# ---------------------------------------------------------------------------
def is_sunday_row(row: dict) -> bool:
    return series_of(row.get("분류") or "") is not None


def _parse_sunday_benefit(benefit: str) -> dict:
    """GM의일요일.html 이 만든 benefit 텍스트를 문장 리스트·생각·본문 캡션·해시태그로 분해.

    형식: '02 문장\\n03 문장\\n…\\n생각 · 문장\\n\\n캡션…\\n\\n#해시태그…\\n\\n계정 @…'
    문장 카드는 사진 수만큼 번호가 붙고(02부터), 생각은 항상 한 장이라 번호 대신 이름으로 온다.

    구 형식('02/03/04' 셋뿐 · 생각 줄 없음)은 마지막 번호를 생각으로 읽는다 — 이미 시트에
    쌓인 접수분이 새 코드에서 깨지면 안 된다.
    """
    lines = (benefit or "").replace("\r\n", "\n").split("\n")
    numbered: list[str] = []
    think = ""
    header_end = 0
    for i, line in enumerate(lines):
        s = line.strip()
        m = _SUNDAY_LINE_RE.match(s)
        tm = _SUNDAY_THINK_RE.match(s)
        if m:
            numbered.append((m.group(2) or "").strip())
            header_end = i + 1
        elif tm:
            think = tm.group(1).strip()
            header_end = i + 1
        elif numbered or think:
            break  # 문장 블록 종료(빈 줄 등)

    if not think and len(numbered) == 3:      # 구 형식 — 04 가 '생각'이었다
        think = numbered.pop()

    rest = lines[header_end:]

    # cut_idx = 캡션이 끝나는 지점 / hashtag_idx = 해시태그 줄(있을 때만)
    hashtag_idx = None
    cut_idx = None
    for i, line in enumerate(rest):
        s = line.strip()
        if s.startswith("#"):
            hashtag_idx = cut_idx = i
            break
        if s.startswith("계정 @") or s.startswith("발행시점") or s.startswith("표지위치") or _FACT_RE.match(s):
            cut_idx = i              # 해시태그가 없어도 여기서 캡션을 끊는다
            break

    # 해시태그가 없어도 '계정 @…'·'발행시점 · …' 앞에서 캡션을 끊는다(내부 표기가 게시글 본문에 새지 않게).
    caption_lines = rest[:cut_idx] if cut_idx is not None else list(rest)
    caption_lines = [ln for ln in caption_lines
                     if not (ln.strip().startswith("발행시점") or ln.strip().startswith("표지위치") or _FACT_RE.match(ln.strip()))]
    while caption_lines and not caption_lines[0].strip():
        caption_lines.pop(0)
    while caption_lines and not caption_lines[-1].strip():
        caption_lines.pop()

    pub_m = _PUBLISH_AT_RE.search(benefit or "")
    pub_raw = pub_m.group(1) if pub_m else ""
    publish_at = "" if pub_raw in ("", "즉시") else pub_raw

    # 표지 배치 = (좌우 0~1, 상하 0~1, 배율). 배율 1 = 칸을 꽉 채우는 크기(종전 동작).
    facts = {}
    for ln in lines:
        mf = _FACT_RE.match(ln.strip())
        if mf:
            facts[mf.group(1)] = mf.group(2).strip()

    fm = _COVER_FOCUS_RE.search(benefit or "")
    try:
        if fm:
            cover_focus = (min(1.0, max(0.0, float(fm.group(1)))),
                           min(1.0, max(0.0, float(fm.group(2)))),
                           min(4.0, max(0.2, float(fm.group(3)))) if fm.group(3) else 1.0)
        else:
            cover_focus = (0.5, 0.5, 1.0)
    except ValueError:
        cover_focus = (0.5, 0.5, 1.0)

    return {
        "lines": numbered,          # 문장 카드 — 사진 순서 그대로
        "think": think,             # 생각 한 장(사진 없음)
        "caption": "\n".join(caption_lines).strip(),
        "hashtags": rest[hashtag_idx].strip() if hashtag_idx is not None else "",
        "publish_at": publish_at,
        "cover_focus": cover_focus,
        "facts": facts,
    }


def _clean_title(t: str) -> str:
    """표지 제목을 시안 모양(두 줄)으로 다듬는다.

    프롬프트로 규칙을 줘도 모델이 'GM의 일요일 — …' 처럼 시리즈 이름을 붙여 오는 일이
    실측으로 반복됐다(표지에 라벨이 이미 있어 두 번 나온다). 말로만 막지 않고 여기서 깎는다.
    줄바꿈이 없으면 가운데에 가장 가까운 띄어쓰기에서 두 줄로 나눈다.
    """
    t = (t or "").strip()
    for lead in (SERIES_NAME, "GM의 일요일", "GM 의 일요일"):
        if t.startswith(lead):
            t = t[len(lead):]
    t = t.lstrip(" -—–·:|").strip()
    if not t:
        return ""
    if "\n" in t:
        return "\n".join(x.strip() for x in t.split("\n")[:2] if x.strip())
    t = t.replace("—", " ").replace("–", " ")
    t = " ".join(t.split())
    if len(t) <= 12 or " " not in t:
        return t
    mid = len(t) // 2
    cut = min((i for i, c in enumerate(t) if c == " "), key=lambda i: abs(i - mid))
    return t[:cut].strip() + "\n" + t[cut:].strip()


def _parse_copy_json(raw: str, n_lines: int, card_names: "list[str] | None" = None) -> dict | None:
    """AI 응답 텍스트 → 캐러셀 글 dict. 실패하면 None(예외를 밖으로 던지지 않는다).

    코드블록 펜스(```json …```)나 앞뒤 설명이 섞여 와도 첫 '{' ~ 마지막 '}' 만 떼어 읽는다.
    lines 는 표지를 뺀 사진 수(n_lines)와 정확히 맞춘다 — 모자라면 빈 문장으로 채우고
    (사진만 나가는 카드가 된다), 넘치면 잘라 버린다. 둘 다 stderr 에 남긴다.

    ★lines 는 파일 이름을 키로 하는 객체로 받는다(card_names 순서대로 꺼낸다).
      2026-08-16 실사고 — 배열로 받았더니 문장이 사진보다 한 칸씩 밀려 유모차 사진에
      '저도 물에 들어가 엎어졌어요' 가 붙어 나갔다. 키로 매면 밀릴 수가 없다.
      옛 배열 응답도 계속 받아 준다(모델이 지시를 어겨도 글이 통째로 날아가지 않게) —
      다만 그때는 밀림을 못 막으므로 stderr 에 경고를 남긴다.
    """
    s = (raw or "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        print("[WARN] GM의 일요일 AI 글 — JSON 덩어리를 못 찾음", file=sys.stderr)
        return None
    try:
        data = json.loads(s[i:j + 1])
    except json.JSONDecodeError as exc:
        print(f"[WARN] GM의 일요일 AI 글 JSON 파싱 실패: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        return None

    raw_lines = data.get("lines")
    if isinstance(raw_lines, dict):
        # 파일 이름 키 → 사진 순서대로 꺼낸다. 키를 못 찾으면 그 카드는 문장을 비운다
        # (사진만 나가는 카드가 된다 — 엉뚱한 문장이 붙는 것보다 낫다).
        lookup = {str(k).strip().lower(): str(v).strip() for k, v in raw_lines.items()}
        lines, missed = [], []
        for name in (card_names or []):
            key = str(name).strip().lower()
            if key in lookup:
                lines.append(lookup[key])
            else:
                lines.append("")
                missed.append(name)
        if missed:
            print(f"[WARN] GM의 일요일 AI 문장 — 사진 키 미매칭 {len(missed)}장(문장 비움): {missed}",
                  file=sys.stderr)
        if not card_names:
            lines = [v for _, v in sorted(lookup.items())]
    else:
        lines = [str(x).strip() for x in (raw_lines or []) if isinstance(x, (str, int, float))]
        if lines:
            print("[WARN] GM의 일요일 AI 문장 — 배열로 왔다(파일 키 객체 아님). "
                  "사진↔문장 밀림을 막을 수 없으니 검수에서 한 장씩 대조할 것.", file=sys.stderr)
    if len(lines) > n_lines:
        print(f"[WARN] GM의 일요일 AI 문장 {len(lines) - n_lines}개 초과 — 잘라 맞춤", file=sys.stderr)
        lines = lines[:n_lines]
    elif len(lines) < n_lines:
        print(f"[WARN] GM의 일요일 AI 문장 {n_lines - len(lines)}개 부족 — 빈 문장으로 채움", file=sys.stderr)
        lines += [""] * (n_lines - len(lines))

    return {
        "title": _clean_title(str(data.get("title") or "")),
        "lines": lines,
        "think": str(data.get("think") or "").strip(),
        "caption": str(data.get("caption") or "").strip(),
        "hashtags": str(data.get("hashtags") or "").strip(),
        # 정보 슬라이드에 인쇄할 값 — 접수 메모를 밖에 낼 말로 다듬은 것. 없으면 빈 dict.
        "info": {str(k).strip(): str(v).strip()
                 for k, v in (data.get("info") or {}).items() if str(v).strip()}
        if isinstance(data.get("info"), dict) else {},
    }


def _write_sunday_copy(photos: list[Path], video: bool, facts: dict | None = None,
                       series: dict | None = None) -> dict | None:
    """내려받은 사진을 실제로 열어 보고 캐러셀 글(제목·문장·생각·캡션·해시태그)을 쓴다.

    사람이 접수 화면에서 문장을 미리 채우는 대신, 올라온 사진에서 글이 나오게 하는 경로
    (GM 지시 2026-08-05). claude CLI 의 Read 도구를 열어 주면(--allowedTools Read) 로컬
    이미지를 직접 보고 답한다 — GM 의 Claude Code 구독을 재사용하므로 API 비용 0.

    photos[0] = 표지. 반환 dict 에 사용 모델을 model 키로 담는다.
    실패(CLI 실패·파싱 실패)면 None — 호출부가 접수 원문(은행)으로 폴백한다.
    """
    if not photos:
        return None
    try:
        from model_router import run_claude
    except Exception as exc:
        print(f"[WARN] GM의 일요일 AI 글 — model_router 임포트 실패: {exc}", file=sys.stderr)
        return None

    s = series or _S0
    s_name, s_tag = s.get("name", SERIES_NAME), s.get("tag", SERIES_TAG)
    s_brief = (s.get("brief") or "").strip()
    n = len(photos) - 1  # 표지를 뺀 나머지 = 문장 카드 수
    prompt = "\n".join([
        f"너는 인스타그램 계정 @{s.get('account', 'namuk.wellperion')} 에 올라갈",
        f"'{s_name}' 캐러셀 글을 쓴다.",
        # 시리즈의 성격은 series.json 의 brief 가 정한다 — 코드에 시리즈별 문구를 박지 않는다.
        f"  {s_brief}" if s_brief else "",
        "",
        f"이 글의 기준: {SUNDAY_STANDARD}.",
        "  남에게 설명하는 글이 아니라, 몇 년 뒤 본인이 다시 읽었을 때 그날이 되살아나는 글이다.",
        "  '저희는 이렇게 합니다' 같은 설명조는 기록이 아니다 — 그날 있었던 장면을 적는다.",
        f"이 시리즈가 향하는 한 문장: {SUNDAY_SLOGAN}",
        "  이 문장을 글에 그대로 베껴 넣지 마라. 글이 이 방향을 향하기만 하면 된다.",
        "",
        "아래 사진 파일을 Read 도구로 전부 열어 실제로 보고 써라.",
        "★[표지] 는 문장을 달지 않는다. [카드] 만 문장을 단다.",
        f"  [표지] {photos[0]}",
        *[f"  [카드] {p}" for p in photos[1:]],
        "",
        "규칙:",
        "- 사진에 실제로 보이는 것만 쓴다. 안 보이는 사실(가족 구성·장소 이름·감정의 근거)을 지어내지 마라.",
        "- ★말투 = GM 이 늘 쓰던 말투 그대로. 존댓말 구어체('~해요' '~습니다' '~더라고요').",
        "  실제 예: '일요일엔 계획을 안 세웁니다. 평일엔 아침마다 오늘 할 일부터 정하거든요.",
        "  그 버릇이 주말까지 따라오더라고요.' — 이 결을 따라간다.",
        "  ★문어체 '~다' 로 끝내지 마라. 시·수필처럼 쓰지 마라. 예쁘게 쓰려 하지 마라.",
        "  금지: 미문·비유·여운·'~에 있었다' 류의 문학적 마무리. 과장·감탄사·이모지·광고 문구.",
        "  그냥 그날 있었던 걸 아는 사람한테 말하듯 담담하게 적는다.",
        "  ★낱말 짝이 어색하면 안 된다. 한국어로 실제로 쓰는 표현인지 스스로 읽어 보고 써라",
        "  (실제 사고: '과일이랑 간식 폈어요' — '펴다'는 돗자리에나 쓴다).",
        "- title = 두 줄. 반드시 줄바꿈 문자 1개로 나눈다. 각 줄 12자 안팎.",
        f"  제목에 '{s_name}' 같은 시리즈 이름을 넣지 마라(표지에 이미 있다). 줄표(—)로 잇지 마라.",
        f"- lines = [카드] 사진 {n}장에 대한 문장. ★배열이 아니라 **파일 이름을 키로 하는 객체**로 낸다."
        "  (2026-08-16 실사고: 배열로 받았더니 문장이 사진보다 한 칸씩 밀려, 유모차에 앉은 아기 사진에"
        "  '저도 물에 들어가 엎어졌어요' 가 붙어 나갔다. 키로 매어 두면 밀릴 수가 없다.)"
        "  각 한 문장 25자 안팎. 그 사진에 실제로 보이는 것만 담담하게 적는다(같은 말투)."
        " 사진마다 다른 이야기이고, 꾸미는 말을 붙이지 않는다.",
        "- ★시간·횟수를 지어내지 마라 — '종일'·'반나절'·'또 왔는데'·'매번' 처럼"
        "  사진 한 장으로는 알 수 없는 말은 쓰지 않는다.",
        "- think = 그날 느낀 것 한 줄. 같은 말투(존댓말 구어체). 교훈조·설교조·미문 금지.",
        "- caption = 인스타 본문 5~8줄. 순서는 ①그날 있었던 일(기록) ②읽는 사람이 따라 해볼 수 있는"
        " 정보(아래 '사진으로는 알 수 없는 사실'에 적힌 것만 — 없으면 그 부분은 아예 쓰지 않는다.",
        "  지어내지 마라) ③마지막 줄은 독자에게 던지는 질문 한 줄. 정보는 나열식 광고 문구가 아니라"
        " 문장 속에 자연스럽게 녹인다.",
        f"- hashtags = 5개 안팎이고 맨 앞 3개가 가장 중요하다. {s_tag} 를 반드시 포함한다.",
        "- info = 정보 슬라이드에 그대로 인쇄될 값. 아래 '사진으로는 알 수 없는 사실'의"
        "  각 항목을 **밖에 내보낼 말로 다듬어** 같은 키로 돌려준다."
        "  ★접수 메모는 GM 이 본인에게 적은 쪽지다 — 그대로 인쇄하면 안 된다."
        "  (2026-08-16 실사고: '저번 백운계곡 테스트도 성공 이번도 성공' 이 그대로 발행돼 나갔다.)"
        "  내부 표현·업무 용어·중복은 걷어내고, 읽는 사람에게 뜻이 통하는 짧은 말로 바꾼다."
        "  값이 없거나 밖에 낼 말이 아니면 그 키를 아예 빼라(빈 칸이 잘못된 칸보다 낫다).",
        "- 금지어: '피트니스'(→'스포츠클럽'), '하이엔드프라이빗', '사교'.",
        *(["- 사진 외에 영상도 함께 올라가지만 영상은 보지 못하니 언급하지 마라."] if video else []),
        "",
        *( ["", f"이번 편 컨셉: {(facts or {}).get('컨셉')}. 글 전체가 이 컨셉을 따라간다."]
           if (facts or {}).get("컨셉") else [] ),
        *( ["",
            f"마지막 장에 들어갈 문장은 이미 정해져 있다: {(facts or {}).get('슬로건')}",
            "  think 에는 이 문장을 **한 글자도 바꾸지 말고 그대로** 넣어라(다듬지 마라).",
            "  대신 앞의 문장·캡션이 이 문장으로 자연스럽게 이어지게 쓴다."]
           if (facts or {}).get("슬로건") else [] ),
        *( ["", "아래는 사진으로는 알 수 없는 사실이다. 지어낸 것이 아니니 글에 자연스럽게 녹여라",
           "(억지로 다 넣지 말고, 기록으로 남을 값이 있는 것만):"]
           + [f"- {k}: {v}" for k, v in (facts or {}).items() if k not in ("컨셉", "슬로건")]
           if facts and any(k not in ("컨셉", "슬로건") for k in facts) else [] ),
        "",
        "출력은 JSON 한 덩어리만. 설명·코드블록 없이 { 로 시작해 } 로 끝낸다.",
        '{"title":"두 줄 제목(\\n 포함)","lines":{'
        + ", ".join(f'"{p.name}":"그 사진 문장"' for p in photos[1:])
        + '},"think":"생각 한 줄","caption":"본문 캡션","hashtags":"#태그 #태그",'
          '"info":{"장소":"다듬은 값","좋았던 점":"다듬은 값"}}',
    ])

    raw, used_model = run_claude(
        prompt, label="sunday-carousel-copy", extra_args=["--allowedTools", "Read"]
    )
    if not raw:
        print("[WARN] GM의 일요일 AI 글 생성 실패(전 모델) — 접수 원문으로 폴백", file=sys.stderr)
        return None
    parsed = _parse_copy_json(raw, n, [p.name for p in photos[1:]])
    if parsed is None:
        return None
    # ★마지막 장은 슬로건 자리다(GM 지시 2026-08-05). GM 이 준 게 있으면 그것을,
    #   없으면 시리즈 슬로건을 그대로 쓴다 — AI 가 지어낸 마무리로 덮지 않는다.
    parsed["think"] = (facts or {}).get("슬로건") or SUNDAY_SLOGAN
    parsed["model"] = used_model or ""
    return parsed


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


def _render_sunday_html(variant: str, output: Path, text: str,
                        photo: Path | None = None, label: str = "") -> bool:
    """HTML/CSS 엔진(compose_html)으로 슬라이드 1장 렌더 → output. 실패하면 False.

    HTML 쪽이 자간·행간·균형 줄바꿈·밴딩 없는 그라디언트에서 Pillow 를 이긴다. 다만
    Playwright/Chromium 이 없거나 렌더가 막히는 날이 있어, 실패를 예외로 올리지 않고
    호출부가 기존 Pillow 합성으로 떨어지게 한다 — 검수 카드가 통째로 안 나가는 것보다 낫다.
    """
    # 라벨(표지 좌상단 시리즈 이름)은 여기서 명시적으로 넘긴다 — 엔진 쪽 기본값에 기대면
    # 이름이 두 파일에 살게 되고, 한쪽만 바뀌면 어긋난다(약속 L01).
    slide = {"type": "sunday", "variant": variant, "text": text or "",
             "label": label or SERIES_NAME}
    if photo is not None:
        slide["photo"] = str(photo)
    try:
        from compose_html import render_carousel
        with tempfile.TemporaryDirectory() as tmp:
            made = render_carousel(
                {"account": "personal", "size": "1080x1350", "slides": [slide]},
                Path(tmp), fmt="jpg", concurrency=1)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(made[0]), str(output))
        return True
    except Exception as exc:
        print(f"[WARN] HTML 슬라이드 렌더 실패({variant}) — Pillow 합성으로 대체: {exc}",
              file=sys.stderr)
        return False


def _focus_crop(photo: Path, focus: tuple, dest: Path, fit: bool = True,
                top_align: bool = False) -> Path:
    """사진을 1080x1350 한 장으로 미리 앉혀 둔다 — 이후 합성기(HTML 엔진·Pillow 폴백)가
    둘 다 '가운데 꽉 채워 자르기'라, 여기서 최종 크기·비율로 만들어 두면 그 다음 자르기가
    아무것도 바꾸지 않는다(칸과 크기가 이미 같아서). 합성기를 건드리지 않고 앉히는 그림만 바꾼다.

    fit=True(기본) — 원본 전체를 담는다(자르지 않음). 남는 칸은 같은 사진을 키워
    블러+살짝 어둡게 깐 배경으로 채운다(단색 배경은 시리즈 톤이 깨져 쓰지 않는다).
    GM 지적 2026-08-09: "또 인스타그램 사진 짤렸네" — 가장자리 사람(손·발·머리)이 잘리던 것을 없앤다.

    fit=False — GM 이 표지 배치를 직접 맞춘 경우(cover_focus 커스텀) 전용. 종전처럼 꽉 채워 자른다
    — GM 이 정한 배치를 그대로 존중한다.

    top_align — 문장 카드 전용. 남는 세로 여백을 전부 아래로 몰아 사진을 카드 맨 위에
    붙인다. 이유 둘 — ①카드 아래쪽은 글자가 읽히도록 어두운 그라디언트가 덮는데
    (compose_html.SUNDAY_GRADS['card']), 사진을 가운데 두면 사진 아랫부분이 그 어둠에
    묻힌다 ②가운데 두면 사진 위에도 흐릿한 띠가 생겨, 원본에서 이미 프레임에 걸린 사람
    얼굴이 그 띠에 잘린 것처럼 보인다(GM 지적 2026-08-23 "형주 얼굴 짤렸어" — 원본 자체가
    머리 위를 안 담고 있었는데, 위 띠가 경계를 만들어 우리가 자른 것처럼 읽혔다).
    맨 위에 붙이면 사진 위 경계가 카드 경계와 같아져 그 착시가 사라지고, 남는 자리는
    전부 글자 몫이 된다. 세로 사진처럼 여백이 없으면 아무것도 달라지지 않는다.

    focus = (x, y, zoom) · x·y 는 0~1(남는 공간을 어느 쪽으로 밀지) · zoom 1 = 꽉 채우기.
    실패하면 원본을 그대로 쓴다(표지가 아예 안 나오는 것보다 낫다).
    """
    try:
        from PIL import ImageOps, ImageFilter, ImageEnhance
        img = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
        tw, th = _SUNDAY_ASPECT
        fx, fy = float(focus[0]), float(focus[1])
        zoom = float(focus[2]) if len(focus) > 2 else 1.0
        sw, sh = img.size

        if fit:
            # 배경 = 같은 사진을 꽉 채워 키운 뒤 블러+어둡게 — 여백을 시안 톤으로 자연스럽게 채운다.
            bscale = max(tw / sw, th / sh)
            bg = img.resize((max(1, round(sw * bscale)), max(1, round(sh * bscale))), Image.LANCZOS)
            bx, by = (bg.width - tw) // 2, (bg.height - th) // 2
            canvas = ImageEnhance.Brightness(
                bg.crop((bx, by, bx + tw, by + th)).filter(ImageFilter.GaussianBlur(40))
            ).enhance(0.72)
            scale = min(tw / sw, th / sh) * zoom          # 원본 전체가 들어가는 축소율
        else:
            canvas = Image.new("RGB", (tw, th), _SUNDAY_DARK)
            scale = max(tw / sw, th / sh) * zoom

        nw, nh = max(1, round(sw * scale)), max(1, round(sh * scale))
        free = th - nh
        if fit and top_align and free > 0:
            fy = 0.0                      # 남는 세로는 전부 아래(글자 자리)로
        canvas.paste(img.resize((nw, nh), Image.LANCZOS),
                     (round((tw - nw) * fx), round(free * fy)))
        dest.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(dest, "JPEG", quality=95, optimize=True)
        return dest
    except Exception as exc:
        print(f"[WARN] 표지 배치 실패(원본 그대로 씁니다): {exc}", file=sys.stderr)
        return photo


def _compose_sunday_cover(photo: Path, title: str, output: Path,
                          series: dict | None = None) -> None:
    """post_1 — 표지: 사진 + 위→아래 그라디언트 + 하단 제목(줄바꿈 유지) + 상단 라벨.
    라벨 = 시리즈 이름. series 를 안 주면 기본 시리즈로 찍는다."""
    name = (series or _S0).get("name", SERIES_NAME)
    if _render_sunday_html("cover", output, title or name, photo, label=name):
        return
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
    for ch in name:
        draw.text((cx, label_y), ch, font=label_font, fill=(255, 255, 255))
        bb = label_font.getbbox(ch)
        cx += (bb[2] - bb[0]) + int(label_font.size * 0.15)

    title_font = _sunday_serif(int(w * 0.078))          # GM 시안 = 세리프 제목
    lines = (title or name).split("\n")
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
    if _render_sunday_html("card", output, caption, photo):
        return
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


# 정보 슬라이드에 올릴 항목 — 접수에서 받은 답변 중 '남이 따라 할 수 있는 것'만, 이 순서로.
SUNDAY_INFO_KEYS = ["장소", "날짜", "누구와", "추천 시간", "비용·준비물", "좋았던 점", "다시 간다면"]
SUNDAY_INFO_LABELS = {"장소": "어디", "날짜": "언제", "누구와": "누구와",
                      "추천 시간": "가기 좋은 때", "비용·준비물": "비용·준비물",
                      "좋았던 점": "좋았던 점", "다시 간다면": "다음엔"}


def _sunday_info_rows(facts: dict | None) -> list:
    """접수 답변 → 정보 슬라이드 줄. 적힌 것만 뽑는다(빈 항목은 아예 만들지 않는다)."""
    rows = []
    for k in SUNDAY_INFO_KEYS:
        v = str((facts or {}).get(k, "")).strip()
        if not v:
            continue
        label = SUNDAY_INFO_LABELS[k]
        if k == "날짜":
            v = _human_date(v)
        if v.startswith(label):            # '다음엔 / 다음엔 점심을…' 처럼 라벨이 겹쳐 읽히는 것 방지
            v = v[len(label):].lstrip(" ·:-").strip() or v
        rows.append((label, v))
    return rows


def _human_date(v: str) -> str:
    """2026-08-03 → '8월 3일 일요일'. 형식이 다르면 원문 그대로 둔다."""
    try:
        d = datetime.strptime(v[:10], "%Y-%m-%d")
    except ValueError:
        return v
    week = "월화수목금토일"[d.weekday()]
    return f"{d.month}월 {d.day}일 {week}요일"


def _compose_sunday_info(rows: list, output: Path, photo: Path | None = None) -> bool:
    """정보 슬라이드 1장. 줄이 2개 미만이면 만들지 않는다(빈 장을 끼우지 않는다).

    GM 지적 2026-08-05: '정보들은 하나도 없네 — 이러면 정보를 왜 받은거야?'
    받은 답변이 캡션 안에만 묻혀 있어 슬라이드로는 보이지 않던 것을 한 장으로 세운다.
    """
    if len(rows) < 2:
        return False
    try:
        from compose_html import render_carousel
        # ★임시 폴더에 렌더한 뒤 옮긴다. 결과 폴더에 바로 렌더하면 엔진이 첫 장을 항상
        #   post_1.jpg 로 쓰기 때문에 이미 만들어 둔 표지(post_1.jpg)를 덮어쓰고 옮겨 간다
        #   — 2026-08-05 실사고: 표지 파일이 사라져 M1 미리보기가 통째로 깨졌다.
        with tempfile.TemporaryDirectory() as tmp:
            made = render_carousel(
                {"account": "personal", "size": "1080x1350",
                 "slides": [dict({"type": "sunday", "variant": "info", "rows": rows},
                                 **({"photo": str(photo)} if photo else {}))]},
                Path(tmp), fmt="jpg", concurrency=1)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(made[0]), str(output))
        return True
    except Exception as exc:
        print(f"[WARN] 정보 슬라이드 렌더 실패(건너뜀): {exc}", file=sys.stderr)
        return False


def _compose_sunday_think(caption: str, output: Path) -> None:
    """post_4 — 사진 없음: 어두운 배경(#23201C) + 주황(#F0B27A) 바 + 문장3."""
    if _render_sunday_html("think", output, caption):
        return
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
    # 한 줄로 이어 붙이면 8장에서 가로:세로가 6.5:1 이 된다 — 텔레그램이 그런 사진을
    # 잘라 보여 줘 GM 이 '또 짤렸다'고 본다(2026-08-09). 격자로 접어 비율을 눕힌다.
    cols = min(4, len(cells))
    rows = (len(cells) + cols - 1) // cols
    row_h = max(c.height for c in cells)
    total_w = cols * cell_w + gap * (cols - 1)
    total_h = rows * row_h + gap * (rows - 1)
    canvas = Image.new("RGB", (total_w, total_h), _SUNDAY_CREAM)
    for i, c in enumerate(cells):
        canvas.paste(c, ((i % cols) * (cell_w + gap), (i // cols) * (row_h + gap)))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PNG", optimize=True)


def build_sunday_item(row: dict, item_id: str) -> dict | None:
    """'GM의 일요일' 접수 1건 → review_queue 항목(검수대기) 빌드. 사진 0장이거나
    다운로드가 전부 실패하면 None(경고는 여기서 stderr 로 남김 — 조용한 성공 처리 금지)."""
    series = series_of(row.get("분류") or "") or _S0
    writer = (row.get("성함") or "").strip()          # 올린 사람 — 접수 화면이 적어 보낸다
    intro = (row.get("한줄소개") or "").strip()
    parsed = _parse_sunday_benefit(row.get("회원이얻는것") or "")
    links = [u.strip() for u in (row.get("사진링크") or "").split("\n") if u.strip()]
    if not links:
        print(f"[WARN] 하루 기록 접수 사진 0장 — 제작 불가: {item_id}", file=sys.stderr)
        return None

    date8 = re.sub(r"[^0-9]", "", str(row.get("접수일시") or ""))[:8]
    date6 = date8[2:8] if len(date8) == 8 else datetime.now().strftime("%y%m%d")
    slug = _id_safe(intro)[:24] or series["slug"]
    folder_rel = f"instagram/{series['account']}/{date6}_{series['slug']}_{slug}"
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

    # 사진 수가 슬라이드 수를 정한다 — 표지 1장 + 나머지 사진 1장당 문장 카드 1장 + 생각 1장.
    cards = downloaded[1:]

    # 글은 사진을 보고 쓴다(주경로). 접수 화면이 보낸 문장(은행)은 AI 가 실패했을 때의 폴백이다.
    ai = _write_sunday_copy(downloaded, bool((row.get("영상링크") or "").strip()),
                            parsed.get("facts"), series)
    if ai:
        intro = ai["title"] or intro
        texts, think = ai["lines"], ai["think"]
        caption_body, hashtags = ai["caption"], ai["hashtags"]
        copy_note = f"글=사진 보고 AI 작성({ai['model'] or '모델미상'})"
    else:
        texts, think = parsed["lines"], parsed["think"]
        caption_body, hashtags = parsed["caption"], parsed["hashtags"]
        copy_note = "글=접수 원문 폴백(AI 생성 실패)"
        # 새 접수 화면은 문장을 아예 안 보낸다 — 폴백할 원문도 없으면 빈 슬라이드를 만들지 않는다.
        if not (any(t.strip() for t in texts) or think.strip()):
            print(f"[WARN] GM의 일요일 AI 글 실패 + 접수 문장도 없음 — 제작 불가(다음 폴링 재시도): {item_id}",
                  file=sys.stderr)
            return None

    if len(texts) > len(cards):
        print(f"[WARN] GM의 일요일 문장 {len(texts) - len(cards)}개 버림(사진이 모자람): {item_id}",
              file=sys.stderr)

    slides_rel = []

    def _add(name: str) -> Path:
        slides_rel.append(f"{folder_rel}/output/{name}")
        return out_dir / name

    try:
        # GM 이 손댄 배치(zoom≠1 또는 x·y≠0.5)만 종전 '꽉 채워 자르기'를 존중 — 그 외 전부
        # 원본 전체가 들어가는 fit(안 잘림).
        cover_fit = parsed["cover_focus"] == (0.5, 0.5, 1.0)
        cover_src = _focus_crop(downloaded[0], parsed["cover_focus"], src_dir / "cover_focus.jpg",
                                 fit=cover_fit)
        _compose_sunday_cover(cover_src, intro, _add("post_1.jpg"), series)
        fit_cards = [_focus_crop(p, (0.5, 0.5, 1.0), src_dir / f"fit_{i + 1}.jpg",
                                 top_align=True)
                     for i, p in enumerate(cards)]
        for i, photo in enumerate(fit_cards):
            # 문장이 없는 사진은 사진만 넣는다 — 없는 문장을 지어내지 않는다.
            _compose_sunday_photo_card(photo, texts[i] if i < len(texts) else "",
                                       _add(f"post_{i + 2}.jpg"))
        nxt = len(cards) + 2
        # 정보는 따로 글자 페이지를 만들지 않고 '마지막 사진 위'에 얹는다(GM 지시 2026-08-05:
        # '정보를 따로 페이지로 만드는 것보다, 그냥 사진 페이지에 정리하는 게 낫다').
        # 그 사진의 문장 카드를 정보 카드로 갈아 끼우므로 장수는 늘지 않는다.
        # 정보 슬라이드 값 = AI 가 밖에 낼 말로 다듬은 것(ai["info"]) 우선, 없으면 접수 원문.
        # ★접수 메모를 그대로 인쇄하면 안 된다 — 2026-08-16 '테스트도 성공' 이 그대로 나갔다.
        # AI 가 info 를 냈으면 그것만 쓴다 — 모델이 뺀 키는 '밖에 낼 말이 아니라' 뺀 것이므로
        # 원문으로 되살리지 않는다(되살리면 애초 사고가 그대로 재발한다).
        _polished = (ai or {}).get("info") or {}
        info_rows = _sunday_info_rows(_polished or (parsed or {}).get("facts"))
        if info_rows and fit_cards:
            last_rel = slides_rel[-1]
            if _compose_sunday_info(info_rows, out_dir / Path(last_rel).name, fit_cards[-1]):
                nxt = len(cards) + 2          # 문장 카드 자리를 그대로 쓴다(추가 없음)
            else:
                print("[WARN] 정보 카드 렌더 실패 — 문장 카드 그대로 둔다", file=sys.stderr)
        _compose_sunday_think(think, _add(f"post_{nxt}.jpg"))
    except Exception as exc:
        print(f"[WARN] GM의 일요일 슬라이드 제작 실패: {item_id}: {exc}", file=sys.stderr)
        return None

    # 검수 카드에 붙일 몽타주 — send_review_card._preview_photo 가 찾는 이름 규약
    # (folder/output/_검수_미리보기_*.png)을 그대로 따른다. 이 파일이 없으면 카드가
    # 이미지 없이 글자로만 나가, GM 이 '결과물'을 못 보고 승인해야 한다.
    try:
        _compose_sunday_montage(
            [ROOT / s for s in slides_rel], out_dir / f"_검수_미리보기_{len(slides_rel)}장.png"
        )
    except Exception as exc:                       # 몽타주 실패가 접수 자체를 죽이면 안 된다
        print(f"[WARN] GM의 일요일 검수 미리보기 생성 실패(카드는 글자로 나갑니다): {item_id}: {exc}",
              file=sys.stderr)

    # ★미리보기는 가이드 트리 안에 둔다(cmo/review/…).
    #   깃허브 페이지는 "3. 웰페리온 가이드" 를 루트로 서비스하므로, 저장소 루트 기준
    #   instagram/… 경로는 M1 화면에서 아예 닿지 않는다 — 2026-08-05 GM 지적
    #   'm1에 미리보기도 안나오고' 의 원인. 기존 항목 규약(cmo/review/*.png)을 따른다.
    preview_rel = ""
    try:
        mont = out_dir / f"_검수_미리보기_{len(slides_rel)}장.png"
        if mont.exists():
            dest = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / f"{item_id}_preview.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(mont, dest)
            preview_rel = f"cmo/review/{dest.name}"
    except Exception as exc:
        print(f"[WARN] 미리보기 복사 실패(카드는 폴더 몽타주로 폴백): {exc}", file=sys.stderr)

    caption_full = caption_body
    if hashtags:
        caption_full = f"{caption_full}\n\n{hashtags}" if caption_full else hashtags
    (ROOT / folder_rel / "caption.md").write_text(caption_full, encoding="utf-8")

    # 원본·중간물은 완성본이 나온 뒤 지운다(GM 확정 2026-08-25 A안). 원본은 접수 때
    # 구글 드라이브 '마케팅 접수' 폴더에 그대로 남아 있으므로 PC 에 두면 두 벌이 된다.
    # 완성본이 실제로 만들어졌을 때만 지운다 — 실패한 회차의 원본까지 날리면 재시도가 막힌다.
    if src_dir.exists() and any(out_dir.glob("post_*.jpg")):
        shutil.rmtree(src_dir, ignore_errors=True)

    return {
        # 표지 제목은 두 줄(\n)이지만 큐·검수카드 제목은 한 줄이어야 한다 — 줄바꿈만 편다.
        "title": f"{series['name']} — " + " ".join(intro.split()),
        "channel": series["channel"],
        "account": series["account"],
        "folder": folder_rel,
        "slides": slides_rel,
        "caption": caption_full,
        "location": "웰페리온 스포츠클럽",
        "collaborators": [],
        "mentions": [],
        "status": "검수대기",
        "preview": preview_rel or slides_rel[0],
        # 정보 슬라이드에 실제로 인쇄될 값 — 승인 카드에 글자로도 실린다(몽타주에선 안 읽힌다).
        "info_lines": [f"{label} · {val}" for label, val in info_rows],
        "id": item_id,
        "publish_at": parsed["publish_at"],
        "writer": writer,
        "note": (f"[{series['name']} 접수 {row.get('접수일시', '')}"
                 + (f" · 올린이 {writer}" if writer else "")
                 + f"] cmo_intake_to_review.py 자동 제작 · {copy_note}"),
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
    ap.add_argument("--selftest", action="store_true",
                    help="시리즈 분기만 검사하고 끝낸다(네트워크·큐 접촉 0)")
    args = ap.parse_args()

    if args.selftest:
        # 여기가 깨지면 접수가 조용히 유실된다 — 옛 이름으로 들어온 건이 경로를 잃거나,
        # 남의 분류(강사소개 등)를 이 경로로 끌고 오거나. 둘 다 아무 에러 없이 일어난다.
        assert SERIES_LIST, "시리즈 목록이 비었다"
        assert series_of(SERIES_NAME), "현재 이름으로 시리즈를 못 찾는다"
        assert series_of("GM의 일요일"), "옛 이름(aka) 접수가 경로를 잃는다"
        assert series_of("강사소개") is None, "남의 분류를 이 경로로 끌고 온다"
        assert is_sunday_row({"분류": "GM의 일요일"}) and not is_sunday_row({"분류": "강사소개"})
        print("[OK] 시리즈 분기 검사 통과 —", ", ".join(s["name"] for s in SERIES_LIST))
        return 0

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
    # 검수큐만 보면, 큐에서 지운 접수가 다음 폴링에 되살아난다(2026-08-25 실측 — 폐기건
    # 정리 직후 같은 건이 신규후보로 다시 떴다). 이미 한 번 처리한 접수는 발신 원장에
    # 남으므로 그것도 함께 무덤돌로 쓴다 — 새 파일을 만들지 않는다(약속 L21).
    handled_ids = existing_ids | set(_load_sent_state())

    candidates = []
    for row in rows:
        item_id = make_id(row)
        if item_id in handled_ids:
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
