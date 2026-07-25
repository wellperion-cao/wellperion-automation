# -*- coding: utf-8 -*-
"""
실전사례(종합접수처 등, @namuk.wellperion 개인계정) 07:30 반자동 발송 오케스트레이션.

설계: docs/superpowers/specs/2026-07-10-namuk-실전사례-반자동-0730-design.md

★ 이 스크립트에는 헤드리스 claude(창작) 호출 코드가 **존재하지 않는다** — 정직 가드가 구조적.
  대본·캡션은 사람(시모)이 미리 만들어 폴더에 쌓아둔 파일에서만 읽는다. 파일이 없으면
  만들 방법이 코드에 없다(빈 카드·지어낸 카드 발송 절대 금지).

동작 개요 (재고표 = instagram/_실전사례_2주플랜.md '## 재고' 표):
  ① 재고표 파싱 → 요일 게이트(월~금='평일' / 토·일='주말GM' 행 있을 때만) → 다음 편 선정
  ② 대본 불량 검증(html 6장·caption.md 존재) → 렌더(이미 6장+미리보기 있으면 재사용, 없으면
     render_hand_slides.py 호출)
  ③ publish_register.register_publish → M1 review_queue '검수대기' 등록(+montage 텔레그램)
  ④ send_review_card.py --id → GM 텔레그램 [✅승인]/[❌반려] 버튼 카드(무폴링 발행 트리거)
  ⑤ 재고표 해당 행 상태 → '검수발송(YYYY-MM-DD)' 마킹(다음날 중복 재선정 차단)
  재고 0건(대상 트랙에 '재고(대본완료)' 없음)이면 평일엔 "📭 재고 소진" 텔레그램만 내고 종료,
  주말(주말GM 행 없음)은 조용히 종료(알림 스팸 금지).

발행 트리거 = 오직 GM 텔레그램 [✅승인] 탭(bot.py pub: 콜백 → watcher --once). 이 스크립트는
발행을 절대 하지 않는다. review_queue 폴링 감시기 부활 금지.

사용:
  실가동:              python scripts\\case_series_dispatch.py
  로직만(무전송):       python scripts\\case_series_dispatch.py --dry-run   (렌더·등록·카드 없음)
  선정 결과만 출력:      python scripts\\case_series_dispatch.py --plan-only

종료코드: 0=성공(또는 소진/무재고로 정상 종료) / 1=오류(텔레그램 경고 발송됨).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
INVENTORY = ROOT / "instagram" / "_실전사례_2주플랜.md"
NAMUK_DIR = ROOT / "instagram" / "namuk.wellperion"
REVIEW_QUEUE_PATH = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
ENV_PATH = ROOT / "telegram_bot" / ".env"

sys.path.insert(0, str(ROOT / "scripts"))

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound, pace
except Exception:
    def log_outbound(*a, **k):
        pass
    def pace(*a, **k):
        return None

try:  # 결정 정합 게이트 공용 신호(§4) — 가드가 재생을 막을 때 1줄 남긴다(best-effort)
    from decision_replay_log import append as _replay_append
except Exception:
    def _replay_append(*a, **k):
        return False

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV_KEY = "TELEGRAM_CHAT_ID"

STOCK_STATUS = "재고(대본완료)"  # 이 상태만 발송 후보
_DONE_STATUS_KW = ("검수발송", "발행완료", "보류")  # 안전망 — 이 키워드 포함 행은 후보 제외

WEEKDAY_TRACK = "평일"
WEEKEND_TRACK = "주말GM"

# 실제 카드 발송 SSOT — send_review_card.py 가 발송 성공 시 이 파일에 item_id 를 키로 적는다.
# (2026-07-19 재발방지 · CASE13 사고) "review_queue 에 존재" ≠ "카드 발송 완료" — 반드시
# 이 파일로 실발송 여부를 확인한다. review_queue 존재만 보고 스킵하면 send_card=False 로
# 선등록(카드 보류)된 편이 영영 카드를 못 받는다.
CARD_MSGID_STORE = ROOT / "scripts" / ".review_card_msgids.json"
_GM_CONFIRM_RE = re.compile(r"\[GM\s*확인")  # 대본/캡션에 남아있으면 아직 GM 확인 대기(보류 유지)


# ─────────────────────────────────────────────────────────────────────────────
# 텔레그램 (토큰 stdout 노출 금지)
# ─────────────────────────────────────────────────────────────────────────────
def _load_env_value(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if val:
        return val
    try:
        if ENV_PATH.exists():
            for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


TELEGRAM_CHAT_ID: str = _load_env_value(TELEGRAM_CHAT_ID_ENV_KEY)


def telegram(message: str) -> None:
    """1줄 텔레그램 보고. 실패해도 죽지 않음(토큰 trace 미출력)."""
    token = _load_env_value(TELEGRAM_TOKEN_ENV_KEY)
    if not token:
        print("[WARN] 텔레그램 토큰 미설정 — 보고 생략")
        return
    try:
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode(
            {"chat_id": TELEGRAM_CHAT_ID, "text": message, "disable_web_page_preview": "true"}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST"
        )
        pace()
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[INFO] 텔레그램 보고 {'성공' if resp.status == 200 else '실패'}")
            log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="case_series_dispatch.telegram",
                         ok=(resp.status == 200), kind="sendMessage")
    except Exception:
        log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="case_series_dispatch.telegram",
                     ok=False, kind="sendMessage")
        print("[WARN] 텔레그램 보고 실패 (토큰 trace 노출 방지)")


# ─────────────────────────────────────────────────────────────────────────────
# 재고표 파싱 + 다음 편 선정
# ─────────────────────────────────────────────────────────────────────────────
class InventoryError(Exception):
    """재고표 파싱·구조 이상 (상위에서 텔레그램 경고 + 중단)."""


def parse_inventory_rows(text: str) -> list[dict]:
    """'## 재고' 표(| 편 | 트랙 | 제목 | 폴더 | 상태 |)를 파싱해 dict 리스트 반환.

    '## 재고'로 시작하는 섹션 안의 표만 대상(다른 표와 섞이지 않게 섹션 범위 한정).
    """
    lines = text.splitlines()
    start = None
    for i, raw in enumerate(lines):
        if raw.strip().startswith("## 재고"):
            start = i
            break
    if start is None:
        raise InventoryError("'## 재고' 섹션을 재고표 파일에서 찾지 못함")

    rows: list[dict] = []
    for raw in lines[start + 1:]:
        stripped = raw.strip()
        if stripped.startswith("## ") and not stripped.startswith("## 재고"):
            break  # 다음 섹션 진입 — 재고 섹션 종료
        if not stripped.startswith("|"):
            continue
        if set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            continue  # 구분선(|---|---|...)
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 5:
            continue
        m = re.match(r"^\s*(\d+)", cells[0])
        if not m:
            continue  # 헤더 행('편') 등 제외
        rows.append(
            {
                "num": int(m.group(1)),
                "num_raw": cells[0],
                "track": cells[1],
                "title": cells[2],
                "folder": cells[3],
                "status": cells[4],
            }
        )
    if not rows:
        raise InventoryError("재고표에서 유효한 편 행을 1건도 못 찾음(표 구조 변경 의심)")
    return rows


def _queue_items() -> list[dict]:
    if not REVIEW_QUEUE_PATH.exists():
        return []
    try:
        data = json.loads(REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


_CASE_MARKER_RE = re.compile(r"-CASE(\d{2})-")

# 시리즈 종결 킬스위치(2026-07-22 신설) — 재고표에 이 마커가 있으면 디스패처는
# 선정·복구·발송 없이 휴면한다. "시리즈를 종결한다"는 전날 결정이 큐(ship)·폴더에만
# 남고 이 표(디스패처 유일 실행 SSOT)에는 안 박혀 옛 편이 재발송되던 사고의 구조적 차단 —
# 종결 = 표 상단에 한 줄(예: `시리즈 상태: 종결(YYYY-MM-DD)`) 박으면 코드가 강제한다.
#
# ★적용 범위 = 평일(실전사례) 트랙 한정 (2026-07-25 수정).
#   원래 이 마커는 '평일 실전사례 라인업 완결'을 뜻했는데 트랙 구분 없이 전체를 껐다.
#   그 바람에 같은 표 안에서 따로 살아있던 `주말GM` 트랙(토=문제 보완 / 일=쉼·가족)까지
#   함께 죽어 2026-07-25(토) 개인계정 발행이 0건이 됐다(GM 지적).
#   → 주말에는 마커가 있어도 주말GM 트랙 선정을 계속한다. 다만 복구 패스는 트랙 무관
#     전수 대상이라 종결된 평일 편을 되살릴 수 있어, 마커가 있으면 주말에도 건너뛴다.
_SERIES_TERMINATED_RE = re.compile(r"시리즈\s*상태\s*[:：]\s*(종결|중단|폐기)")


def _extract_case_num(item_id: str) -> int | None:
    """id 문자열에서 편 번호(-CASE{NN}-)를 추출. 마커 없으면 None."""
    m = _CASE_MARKER_RE.search(item_id)
    return int(m.group(1)) if m else None


def _find_queued_item(num: int) -> dict | None:
    """같은 편 번호(CASE{NN})의 review_queue 항목(검수대기/발행완료/폐기)을 반환. 없으면 None.

    ★'폐기' 포함(2026-07-22 재발방지): GM이 취소(폐기)한 편은 '아직 큐에 없는 새 후보'가
    아니다. 폐기를 빼면 pick_next_case 가 취소된 편을 매일 새 날짜 id로 재선정·재등록하고
    승인카드까지 재발송한다(CASE08 동종 사고: 2026-06-14 골프 → 07-19 CASE13 → 07-20/22 CASE08).
    폐기도 '이미 처리된 편'으로 취급해 재선정을 원천 차단한다.
    """
    marker = f"-CASE{num:02d}-"
    for item in _queue_items():
        item_id = str(item.get("id", ""))
        if marker in item_id and item.get("status") in ("검수대기", "발행완료", "폐기"):
            return item
    return None


def _case_already_queued(num: int) -> bool:
    """같은 편 번호(CASE{NN})가 review_queue 에 이미 검수대기/발행완료로 있으면 True.

    3중 가드 ②: 재고표 마킹이 실패했더라도 큐에 이미 올라가 있으면 재등록(중복 등록) 사고를 막는다.
    ⚠️ 이건 "새로 register_publish 해도 되는가"만 판정한다 — 카드 발송 여부는 별개
    (.review_card_msgids.json 이 SSOT, _card_sent_ids 참고). 2026-07-19 CASE13 사고:
    이 함수의 True 를 "카드까지 이미 나갔다"로 오인해 선등록(카드 보류) 편이 영영
    스킵되던 버그 — recover_stalled_cards() 가 그 틈을 별도로 메운다.
    """
    return _find_queued_item(num) is not None


def _card_sent_ids() -> set:
    """실제 카드 발송 SSOT(.review_card_msgids.json) 키 집합. 파일에 없으면 카드 미발송."""
    try:
        if not CARD_MSGID_STORE.exists():
            return set()
        raw = json.loads(CARD_MSGID_STORE.read_text(encoding="utf-8"))
        return set(raw.keys()) if isinstance(raw, dict) else set()
    except Exception:
        return set()


def _card_sent_case_nums() -> set:
    """카드 발송 SSOT 키들에서 편 번호(CASE{NN})만 뽑은 집합 (2026-07-20 8편 재발송 재발방지).

    .review_card_msgids.json 키는 발송 당시 등록id(날짜 포함, 예: CMO-2026-07-17-CASE08-...)
    그대로다. 같은 편이 다음날 재고표 재선정으로 새 날짜 id(CMO-2026-07-20-CASE08-...)로
    다시 등록되면 완전일치 비교(item_id in sent_ids)가 실패해 "미발송"으로 오판 →
    recover_stalled_cards() 가 재발송한다(동종 3회: 6/14 골프 → 7/19 CASE13 → 7/20 CASE08).
    편 번호만 추출해 비교하면 등록id의 날짜가 바뀌어도 같은 편으로 인식 — _find_queued_item()
    이 이미 -CASE{NN}- 마커로 조회하는 것과 같은 기준으로 맞춘 것. CASE 마커 없는 구형 id
    (예: AI 시리즈, 채널별 개별 id)는 조용히 건너뛴다(그 편들은 원래 완전일치로만 판정됨 —
    이 함수는 recover_stalled_cards 안에서 완전일치 폴백과 함께 쓰인다).
    """
    nums = set()
    for item_id in _card_sent_ids():
        n = _extract_case_num(item_id)
        if n is not None:
            nums.add(n)
    return nums


def _gm_confirm_pending(case: dict) -> bool:
    """대본 html·caption.md 에 '[GM 확인' 플레이스홀더가 남아있으면 True.

    True 면 GM이 아직 빈칸을 안 채운 것 — 카드 발송은 여전히 보류해야 한다
    (선등록 단계에서 의도적으로 send_card=False 로 남겨둔 상태와 동일 취급).
    """
    folder = ROOT / case["folder"]
    diary_html = folder / f"ep{case['num']:02d}_diary_source.html"
    caption_md = folder / "caption.md"
    for p in (diary_html, caption_md):
        try:
            if p.exists() and _GM_CONFIRM_RE.search(p.read_text(encoding="utf-8")):
                return True
        except Exception:
            continue
    return False


def recover_stalled_cards(rows: list[dict], today_iso: str, dry_run: bool) -> None:
    """선등록(send_card=False)된 채 카드 미발송으로 방치된 편을 복구 (2026-07-19 CASE13 재발방지).

    요일 게이트와 무관하게 재고표 전체를 훑는다(평일/주말 어느 트랙이든 같은 사고가 날 수 있음).
    편별 3가지 상태를 명확히 구분:
      ① review_queue 미등록            → 여기서 손대지 않음(정상 신규 후보, pick_next_case 몫)
      ② 등록됨 + 카드 이미 발송(SSOT)   → 멱등: 재발송 안 함. 재고표만 뒤늦게 마킹.
      ③ 등록됨 + 카드 미발송 + GM확인 대기(플레이스홀더 남음) → 여전히 보류(정상, 카드 안 보냄)
      ④ 등록됨 + 카드 미발송 + GM확인 완료             → 카드 발송 트리거 + 재고표 마킹

    ②판정 키 = 편 번호(CASE{NN}) 기준(2026-07-20 8편 재발송 재발방지). 등록id 완전일치
    (구형 id·CASE 마커 없는 케이스 하위호환)와 편 번호 추출(_card_sent_case_nums, 재등록으로
    id 날짜가 바뀌어도 인식) 둘 다로 판정 — 하나라도 걸리면 이미 발송된 것으로 본다.
    """
    sent_ids = _card_sent_ids()
    sent_case_nums = _card_sent_case_nums()
    for r in rows:
        if r["status"] != STOCK_STATUS:
            continue  # 재고표 상태가 이미 다음 단계로 넘어간 행은 여기서 안 건드림
        item = _find_queued_item(r["num"])
        if item is None:
            continue  # ① 아직 등록도 안 됨 — 정상 신규 후보(별도 흐름)
        item_id = str(item.get("id", ""))
        if item_id in sent_ids or r["num"] in sent_case_nums:
            print(f"[INFO] #{r['num']} 카드 이미 발송됨(id={item_id}) — 멱등 스킵, 재고표만 갱신 시도.")
            if not dry_run:
                mark_case_dispatched(r, today_iso)
            else:
                print(f"[DRY-RUN] #{r['num']} 재고표 마킹 스킵(dry-run)")
            continue
        if _gm_confirm_pending(r):
            print(f"[INFO] #{r['num']} 선등록(카드 보류) — GM 확인 미완료([GM 확인] 남음), 보류 유지.")
            continue
        print(f"[INFO] #{r['num']} 선등록 완료 + GM 확인 완료 + 카드 미발송 → 카드 발송 트리거(id={item_id})")
        if dry_run:
            print(f"[DRY-RUN] #{r['num']} 카드 발송 스킵(dry-run) — 실제 미발송")
            continue
        if send_review_card(item_id):
            mark_case_dispatched(r, today_iso)
        else:
            telegram(
                f"⚠️ 실전사례 {r['num']:02d} 선등록 카드 발송 재시도 실패 — id={item_id}. "
                f"수동: send_review_card.py --id {item_id}"
            )


def pick_next_case(rows: list[dict], track: str, log_replay: bool = False) -> dict | None:
    """지정 트랙에서 '재고(대본완료)' 중 편 번호가 가장 빠른 1건 반환. 없으면 None(소진).

    3중 가드: ①상태 완전일치 ②안전망 키워드 미포함 ③review_queue 중복 없음.
    log_replay=True(실가동)면 '폐기'편 재선정 차단 시 공용 로그(§4)에 1줄 남긴다.
    """
    candidates: list[dict] = []
    for r in rows:
        if r["track"] != track:
            continue
        if r["status"] != STOCK_STATUS:
            continue
        if any(kw in r["status"] for kw in _DONE_STATUS_KW):
            continue
        queued = _find_queued_item(r["num"])
        if queued is not None:
            print(f"[INFO] #{r['num']} 은 '{STOCK_STATUS}'이나 review_queue에 이미 존재 — 재선정 스킵(중복 차단).")
            # 결정 정합 신호(§4): '폐기'(GM이 취소한 편)를 재선정 후보에서 차단한 경우만
            # 로그(CASE08 동종 사고 원천차단 증거). 검수대기/발행완료는 정상 dedup — 미로그.
            if log_replay and queued.get("status") == "폐기":
                _replay_append(
                    "cmo-case-series-dispatch",
                    subject=f"CASE{r['num']:02d}",
                    detail=f"GM 폐기편 재선정 차단(id={queued.get('id', '?')}) — 재발송 원천차단",
                )
            continue
        candidates.append(r)
    if not candidates:
        return None
    candidates.sort(key=lambda r: r["num"])
    return candidates[0]


# ─────────────────────────────────────────────────────────────────────────────
# 대본 불량 검증 + 렌더(재사용 우선)
# ─────────────────────────────────────────────────────────────────────────────
def _count_pads(html: str) -> int:
    """render_hand_slides.extract_pads 와 동일 판정(.pad 블록 개수)."""
    return len(re.findall(r'<div class="pad [a-z]+">', html))


def validate_case_folder(case: dict) -> tuple[bool, str, Path | None, Path | None]:
    """대본 불량 검증. 반환: (ok, 사유_또는_공백, diary_html_path, caption_path)."""
    folder = ROOT / case["folder"]
    diary_html = folder / f"ep{case['num']:02d}_diary_source.html"
    caption_md = folder / "caption.md"

    if not folder.is_dir():
        return False, f"제작 폴더 미존재: {case['folder']}", None, None
    if not diary_html.exists():
        return False, f"대본 html 미존재: {diary_html.name}", None, None
    try:
        html = diary_html.read_text(encoding="utf-8")
    except Exception as exc:
        return False, f"대본 html 읽기 실패: {exc}", None, None
    pad_count = _count_pads(html)
    if pad_count != 6:
        return False, f".pad 블록 {pad_count}장(6장 아님)", diary_html, None
    if not caption_md.exists():
        return False, "caption.md 미존재", diary_html, None
    caption_text = caption_md.read_text(encoding="utf-8").strip()
    if not caption_text:
        return False, "caption.md 공백", diary_html, caption_md
    return True, "", diary_html, caption_md


def render_reuse_or_build(case: dict, diary_html: Path) -> tuple[bool, str, Path | None]:
    """output/post_1..6.jpg + 미리보기 6장 모두 있으면 재사용, 아니면 render_hand_slides.py 호출.

    반환: (ok, 사유, montage_path)
    """
    folder = ROOT / case["folder"]
    out_dir = folder / "output"
    posts = [out_dir / f"post_{i}.jpg" for i in range(1, 7)]
    montage = out_dir / "_검수_미리보기_6장.png"

    if all(p.exists() for p in posts) and montage.exists():
        print(f"[INFO] #{case['num']} 렌더 재사용(이미 6장+미리보기 존재) — 렌더 생략")
        return True, "", montage

    print(f"[INFO] #{case['num']} 렌더 필요 — render_hand_slides.py 호출")
    script = ROOT / "scripts" / "render_hand_slides.py"
    try:
        proc = subprocess.run(
            [str(PY), str(script),
             "--diary-html", str(diary_html),
             "--out-dir", str(out_dir),
             "--prefix", "post"],
            cwd=str(ROOT), timeout=180,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.stdout:
            print(proc.stdout.strip())
        if proc.returncode != 0:
            if proc.stderr:
                print(proc.stderr.strip())
            return False, f"render_hand_slides.py 실패(rc={proc.returncode})", None
    except Exception as exc:
        return False, f"render_hand_slides.py 예외: {exc}", None

    if not (all(p.exists() for p in posts) and montage.exists()):
        return False, "렌더 후에도 post_1..6.jpg/미리보기 6장 확인 실패", None
    return True, "", montage


# ─────────────────────────────────────────────────────────────────────────────
# 등록 + 검수 카드
# ─────────────────────────────────────────────────────────────────────────────
def make_slug(case: dict) -> str:
    """폴더명 마지막 '_' 이후 조각을 슬러그로(예: ..._실전사례04_매일활용 → 매일활용)."""
    base = Path(case["folder"]).name
    parts = base.split("_")
    return parts[-1] if parts else base


def make_queue_id(case: dict, today_iso: str) -> str:
    return f"CMO-{today_iso}-CASE{case['num']:02d}-{make_slug(case)}"


def _case_discarded_before_send(queue_id: str) -> bool:
    """카드 발송 직전 최종 폐기가드(2026-07-22, CASE08 동종 사고 이중방어).

    재선정 가드(pick_next_case의 _find_queued_item)가 폐기편을 이미 걸러내지만, 결정이
    표에 늦게 박히는 지연 구간(재고표엔 재고 상태로 남았는데 review_queue엔 폐기가 이미
    올라온 순간)에는 recover_stalled_cards() 경로로 카드 발송까지 도달할 수 있다.
    발송 직전에 같은 편(CASE{NN})의 review_queue 항목 중 status=='폐기'가 하나라도 있으면
    True — 그 경우 호출부는 카드를 쏘지 않는다."""
    num = _extract_case_num(queue_id)
    if num is None:
        return False
    marker = f"-CASE{num:02d}-"
    for item in _queue_items():
        if marker in str(item.get("id", "")) and item.get("status") == "폐기":
            return True
    return False


def send_review_card(queue_id: str) -> bool:
    """scripts/send_review_card.py --id <queue_id> 호출(무폴링 발행 트리거 카드).

    ★ 발송 직전 폐기가드: 같은 편이 review_queue에 이미 status='폐기'로 존재하면 카드
    자체를 쏘지 않고 True(=스킵을 정상 처리로 간주, 호출부의 실패 경고 텔레그램을
    유발하지 않음)를 반환한다. 호출부(run()/recover_stalled_cards())는 그대로 정상
    종료 경로를 탄다(exit 0)."""
    if _case_discarded_before_send(queue_id):
        print(f"[INFO] 폐기가드 — 같은 편(폐기) 항목이 review_queue에 존재, 카드 발송 스킵(id={queue_id}).")
        return True

    script = ROOT / "scripts" / "send_review_card.py"
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run(
            [str(PY), str(script), "--id", queue_id],
            cwd=str(ROOT), timeout=60, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.stdout:
            print(proc.stdout.strip())
        if proc.returncode != 0:
            if proc.stderr:
                print(proc.stderr.strip())
            return False
        return True
    except Exception as exc:
        print(f"[WARN] send_review_card 예외: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 재고표 마킹
# ─────────────────────────────────────────────────────────────────────────────
def mark_case_dispatched(case: dict, today_iso: str) -> bool:
    """재고표 해당 행 상태 → '검수발송(YYYY-MM-DD)'. 현재 상태가 STOCK_STATUS 인 행만 손댄다."""
    try:
        text = INVENTORY.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"[WARN] 재고표 읽기 실패 — 마킹 건너뜀: {exc}")
        return False

    lines = text.splitlines()
    out_lines: list[str] = []
    in_section = False
    updated = False
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("## 재고"):
            in_section = True
            out_lines.append(raw)
            continue
        if in_section and stripped.startswith("## ") and not stripped.startswith("## 재고"):
            in_section = False
        if updated or not in_section or not stripped.startswith("|"):
            out_lines.append(raw)
            continue
        if set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            out_lines.append(raw)
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 5:
            out_lines.append(raw)
            continue
        m = re.match(r"^\s*(\d+)", cells[0])
        if not m or int(m.group(1)) != case["num"]:
            out_lines.append(raw)
            continue
        if cells[4] != STOCK_STATUS:
            print(f"[INFO] 재고표 #{case['num']} 행 상태='{cells[4]}'({STOCK_STATUS} 아님) — 마킹 생략(강등 금지).")
            out_lines.append(raw)
            updated = True
            continue
        cells[4] = f"검수발송({today_iso})"
        out_lines.append("| " + " | ".join(cells) + " |")
        updated = True
        print(f"[INFO] 재고표 #{case['num']} 행 갱신 → 상태=검수발송({today_iso})")

    if not updated:
        print(f"[WARN] 재고표에서 #{case['num']} 행을 찾지 못함 — 마킹 실패(다음날 중복 위험).")
        return False
    try:
        new_text = "\n".join(out_lines)
        if text.endswith("\n") and not new_text.endswith("\n"):
            new_text += "\n"
        INVENTORY.write_text(new_text, encoding="utf-8")
        return True
    except Exception as exc:
        print(f"[WARN] 재고표 쓰기 실패 — 마킹 미반영: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────
def run(dry_run: bool, plan_only: bool) -> int:
    now = datetime.now()
    today_iso = now.strftime("%Y-%m-%d")
    print(f"[INFO] === 실전사례 07:30 디스패처 시작 === {now.isoformat(timespec='seconds')} "
          f"(dry_run={dry_run}, plan_only={plan_only})")

    is_weekend = now.weekday() >= 5  # 5=토, 6=일
    track = WEEKEND_TRACK if is_weekend else WEEKDAY_TRACK

    # 1) 재고표 파싱 (실패 시 경고 + 중단)
    try:
        if not INVENTORY.exists():
            raise InventoryError(f"재고표 파일 부재: {INVENTORY}")
        rows = parse_inventory_rows(INVENTORY.read_text(encoding="utf-8"))
    except InventoryError as exc:
        msg = f"⚠️ 실전사례 디스패처 중단 — 재고표 파싱 실패: {exc}"
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    # 1.4) 시리즈 종결 킬스위치 — 표에 '시리즈 상태: 종결' 마커가 있으면 **평일 트랙만** 휴면.
    #      주말GM 트랙은 별도 트랙이라 계속 돈다(2026-07-25 범위 수정 · 상세 = 정규식 정의부 주석).
    terminated = False
    try:
        terminated = bool(_SERIES_TERMINATED_RE.search(INVENTORY.read_text(encoding="utf-8")))
    except Exception:
        terminated = False

    if terminated and not is_weekend:
        print("[INFO] 시리즈 종결 마커 감지 — 평일 디스패처 휴면(선정·복구·발송 없음). "
              "후속 시리즈는 신규 편성표로 별도 운영.")
        # 결정 정합 신호(§4): 종결 마커에도 아직 '재고(대본완료)' 편이 표에 남아
        # 있으면(휴면이 없었다면 재선정·재발송됐을 편) 실제 재생 차단으로 1줄 남긴다.
        #   plan-only/dry-run(검사 모드)은 공용 로그를 더럽히지 않도록 제외.
        if not (dry_run or plan_only):
            pending = [r["num_raw"] for r in rows
                       if r.get("status") == STOCK_STATUS and r.get("track") == WEEKDAY_TRACK]
            if pending:
                _replay_append(
                    "cmo-case-series-dispatch",
                    subject="실전사례 시리즈(종결)",
                    detail=f"종결 마커로 평일 디스패처 휴면 — 재선정 차단된 잔여 재고편: {pending}",
                )
        return 0

    if terminated:
        print(f"[INFO] 시리즈 종결 마커 있음 — 평일 트랙만 휴면. 오늘은 주말이라 "
              f"{WEEKEND_TRACK} 트랙은 계속 진행한다.")

    # 1.5) 선등록(카드 보류) 복구 패스 — 요일 게이트·트랙과 무관하게 재고표 전체 대상.
    #      plan_only 는 부작용 없이 상태만 보여주므로 dry_run 취급(2026-07-19 CASE13 재발방지).
    #      ★종결 마커가 있으면 주말에도 건너뛴다 — 전수 대상이라 종결된 평일 편을 되살릴 수 있다.
    if terminated:
        print("[INFO] 종결 마커 — 복구 패스 생략(종결된 평일 편 부활 방지).")
    else:
        recover_stalled_cards(rows, today_iso, dry_run=(dry_run or plan_only))

    # 2) 다음 편 선정 (소진 시 생성 금지)
    nxt = pick_next_case(rows, track, log_replay=not (dry_run or plan_only))
    if nxt is None:
        if is_weekend:
            print(f"[INFO] 주말({track}) 재고 없음 — 조용히 종료(알림 스팸 금지).")
            return 0
        stock_nums = [r["num_raw"] for r in rows if r["track"] == track and r["status"] == STOCK_STATUS]
        print(f"[INFO] 실전사례 대본 재고 소진 — 생성 금지. (재고 상태였던 잔여: {stock_nums})")
        telegram("📭 실전사례 대본 재고 소진 — 시모 대본 제작 필요(재고표: instagram/_실전사례_2주플랜.md)")
        return 0

    print(f"[INFO] 다음 편 선정 → #{nxt['num']:02d} 「{nxt['title']}」 / 폴더: {nxt['folder']}")

    if plan_only:
        print("[PLAN-ONLY] 선정만 출력하고 종료(검증·렌더·등록 안 함).")
        return 0

    # 3) 대본 불량 검증
    ok, reason, diary_html, caption_md = validate_case_folder(nxt)
    if not ok:
        msg = f"⚠️ 실전사례 {nxt['num']:02d} 대본 불량({reason}) — 미등록"
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    if dry_run:
        print(f"[DRY-RUN] 검증 통과(대본 html={diary_html.name}, caption.md 확인됨). "
              f"렌더·M5 등록·검수카드 호출 없이 종료.")
        return 0

    # 4) 렌더(재사용 우선)
    ok, reason, montage = render_reuse_or_build(nxt, diary_html)
    if not ok:
        msg = f"⚠️ 실전사례 {nxt['num']:02d} 렌더 실패({reason}) — 미등록"
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    # 5) 등록 (M1 review_queue '검수대기')
    queue_id = make_queue_id(nxt, today_iso)
    caption_text = caption_md.read_text(encoding="utf-8").strip()
    folder_path = ROOT / nxt["folder"]
    folder_rel = folder_path.relative_to(ROOT).as_posix()
    slides = [f"{folder_rel}/output/post_{i}.jpg" for i in range(1, 7)]

    try:
        from publish_register import register_publish

        register_publish(
            content_folder=folder_path,
            slug=make_slug(nxt),
            montage_path=montage,
            caption=caption_text,
            location="웰페리온 스포츠클럽",
            mentions=[],
            account="namuk.wellperion",
            slides=slides,
            queue_id=queue_id,
            title=f"실전사례 {nxt['num']:02d} — {nxt['title']}(개인계정)",
            channel="인스타그램 (namuk.wellperion)",
            send_card=False,  # 카드는 아래 6)에서 별도 호출(중복 방지 — producer 동일 관례)
        )
    except Exception as exc:
        msg = f"⚠️ 실전사례 {nxt['num']:02d} M5 등록 실패: {exc}"
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    # 6) 검수 카드 발송 — [✅승인]/[❌반려] 버튼(무폴링 발행 트리거). 실패해도 등록은 유효(경고만).
    if not send_review_card(queue_id):
        telegram(
            f"⚠️ 실전사례 {nxt['num']:02d} 검수 카드(버튼) 발송 실패 — id={queue_id}. "
            f"M5 등록은 됨. 수동 카드 발송: send_review_card.py --id {queue_id}"
        )

    # 7) 재고표 마킹 (실패해도 등록·카드는 이미 완료 — 경고만)
    if not mark_case_dispatched(nxt, today_iso):
        telegram(
            f"⚠️ 실전사례 {nxt['num']:02d} 재고표 자동표시 실패 — 다음날 같은 편 재선정 위험. "
            f"재고표 #{nxt['num']:02d} 행 상태 수동 확인 요망."
        )

    # 8) 발행은 GM 텔레그램 [✅승인] 탭 시 봇 pub: 콜백이 즉시 수행(무폴링). 이 스크립트는 발행 안 함.
    print(
        f"[OK] 실전사례 {nxt['num']:02d} 「{nxt['title']}」 M5 검수대기 등록 + 검수 카드 발송 완료. "
        f"발행은 GM 텔레그램 [✅승인] 탭 → 봇 pub: 즉시 발행(무폴링). (이 스크립트는 발행 안 함)"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="실전사례(종합접수처 등) 다음 편 07:30 반자동 발송 — 발행 절대 자동 아님"
    )
    ap.add_argument("--dry-run", action="store_true",
                     help="렌더·M5 등록·검수카드 없이 선정·검증만 검증")
    ap.add_argument("--plan-only", action="store_true",
                     help="다음 편 선정 결과만 출력하고 즉시 종료")
    args = ap.parse_args()
    return run(dry_run=args.dry_run, plan_only=args.plan_only)


if __name__ == "__main__":
    sys.exit(main())
