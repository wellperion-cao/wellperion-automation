"""검수 승인 → 자동 발행 감시기 (멀티채널 v2, 2026-06-02)

흐름: 김남욱 페이지 검수 카드에서 GM이 [승인] → (역방향 중계가 큐에 status='승인' 기록)
      → 이 감시기가 채널별 분기 발행 → status 갱신 → 커밋/푸시 → 텔레그램 보고.

큐 파일(검수 카드와 공유): 3. 웰페리온 가이드/cmo/review/review_queue.json
  각 항목 필수: id, title, folder(콘텐츠 폴더 상대경로), status
  채널 분기용: channel (예: "인스타그램", "블로그", "카페", "카카오", "당근")
  status: 검수대기 → 승인 → 발행완료 / 발행실패 / 수동발행대기 / 확인필요(발행됨·URL미회수)
  ※ '확인필요(발행됨·URL미회수)'(블로그·카페) = 발행 스크립트가 게시는 진행했으나 공개 URL
    폴링(12초)에 실패한 경우. '발행실패'와 달리 재발행 대상 아님(중복 게시 방지) — 사람이
    URL을 수동 보강하거나 scripts/reconcile_published.py 로 URL만 재회수(2026-07-20 배834).

실행:
  단발(Windows 예약작업 권장): python scripts\\ig_review_publish_watcher.py --once
  반복:                         python scripts\\ig_review_publish_watcher.py --interval 300
  발행 없이 로직만(테스트):      python scripts\\ig_review_publish_watcher.py --once --dry-run

채널 분기 정책(GM 승인 2026-07-13 — 전채널 자동 공개발행):
  블로그 → naver_blog_upload_playwright.py --mode publish (exit 0=완료 · exit 8=확인필요[게시됨·URL미회수] · 그외=실패)
  카페   → cafe_upload_playwright.py --mode publish (exit 0=완료 · exit 8=확인필요[게시됨·URL미회수] · 그외=실패)
  당근   → danggn_upload_playwright.py --mode publish (공개발행, 세션 만료 시 수동 폴백)
  카카오 → kakao_channel_upload_playwright.py --mode publish (공개발행)
  나머지(인스타 등) → instagram_upload_playwright.py --mode publish
  ※ 안전망: 각 발행 스크립트가 사전점검(§1)+무결성 게이트(§2)로 깨진 글은 발행 안 함(초안 유지).
  ※ 구 정책(2026-06-05 블로그·카페 임시저장→GM 수동)은 요새화 안전망 라이브로 폐기.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound, pace
except Exception:
    def log_outbound(*a, **k):
        pass
    def pace(*a, **k):
        return None

try:  # 작업 현황 로그(best-effort) — 임포트 실패해도 발행 흐름 무영향
    from worklog import log as worklog_log
except Exception:
    def worklog_log(*a, **k):
        return False

# 동시커밋 직렬화 lock (P2, 2026-06-15) — git_lock.py는 같은 scripts/ 폴더.
# 하드 임포트(실패 시 시끄럽게): 락 없이 무방비 커밋되면 동시성 손상 방지 목적이 무력화됨.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from git_lock import GitLock
from safe_commit import safe_commit  # 스테일 트리 차단 커밋(2026-07-23 배9820)
from publish_digest import send_publish_digest  # 발행완료→문의방 통합요약 자동발신(2026-07-15)
# review_queue.json 쓰기 단일 관문(락 직렬화 · 2026-07-23 · 07-21 AI하루 10편 소실 재발방지)
from review_queue_util import merge_save_review_queue

try:  # 결정 정합 게이트 공용 신호(§4) — 가드가 옛 결정 재생을 막을 때 1줄 남긴다(best-effort)
    from decision_replay_log import append as _replay_append
except Exception:  # 로거 부재가 발행 파이프라인을 죽이면 안 된다
    def _replay_append(*_a, **_k):
        return False

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
PUBLISH_SCRIPT = ROOT / "scripts" / "instagram_upload_playwright.py"
BLOG_SCRIPT = ROOT / "scripts" / "naver_blog_upload_playwright.py"   # 블로그 발행 스크립트
CAFE_SCRIPT = ROOT / "scripts" / "cafe_upload_playwright.py"          # 카페 발행 스크립트
DANGGN_SCRIPT = ROOT / "scripts" / "danggn_upload_playwright.py"      # 당근 자동 공개발행(자동입력+이미지+게시)
KAKAO_SCRIPT = ROOT / "scripts" / "kakao_channel_upload_playwright.py"  # 카카오 채널(자동입력, publish 실구현)
PY = ROOT / ".venv" / "Scripts" / "python.exe"
NOTIFIED_FILE = ROOT / "scripts" / ".review_notified.json"  # 검수대기 알림 발송 이력
SIBLING_ALERT_NOTIFIED_FILE = ROOT / "scripts" / ".sibling_alert_notified.json"  # 형제채널 누락 경보 이력
PUBLISH_LOCK_FILE = ROOT / "scripts" / ".publish.lock"  # 발행 직렬화 락(중복/허위 알림 근본 차단, 2026-06-05)
PUBLISH_LOCK_STALE_SEC = 1200  # 락 잔존 한계(초) — 비정상 종료 시 자동 회수(발행 timeout 600초의 2배)
CARD_MSGID_STORE = ROOT / "scripts" / ".review_card_msgids.json"  # send_review_card 가 카드 보낸 id 저장

APPROVED_STATES = {"승인", "승인발행대기", "approved"}
POST_URL_RE = re.compile(r"post\s+[A-C]:\s*(https?://\S+)", re.IGNORECASE)

# ─────────────────────────────────────────────────────────────────────────────
# 종결(폐기·취소) 결정 명문 배제 — 결정정합 게이트 A2 (배9598 · 2026-07-23)
#   계약 정본: ssot/decision_contracts.json ▸ cmo-content-pipeline (pattern K · effect=제외)
#
#   [실측 출발점] 폐기·취소는 APPROVED_STATES 에 없어서 '우연히' 발행 후보가 아니었을 뿐이다.
#   승인 상태값이 하나 추가되는 순간 뚫린다 → 여기서 명시적으로 못 박는다.
#
#   종결 신호 3종(review_queue.json 전수 실측 근거, 추측 아님):
#     ① status ∈ TERMINAL_STATES — 실측 사용값은 '폐기'(라이브 1건·아카이브 2건).
#        '취소'는 계약(decision_contracts.json decision_events)에 선언된 동급 종결어라 함께 정의.
#     ② terminal 필드 truthy — 실측 1건 존재(CMO-2026-07-14-LSERIES-L3-GOLF,
#        status='발행완료' + terminal=True 인 스테일 엔트리). ★status 만 보면 이건 못 잡는다.
#        누가 이 엔트리를 다시 [승인]하면 같은 폴더가 IG 에 중복 발행된다(07-18 사고 재현).
#     ③ folder 안에 폐기 마커 .md 실존 — worklog_gaps._is_deprecated_folder 와 같은 규칙.
#        (07-20 취소편 종결에 쓰인 킬스위치가 이 형태다.)
#   ※ 종결 상태값을 새로 만들면 반드시 TERMINAL_STATES 에 추가할 것.
# ─────────────────────────────────────────────────────────────────────────────
# 인스타 발행 경로로 보낼 채널 판정 — 실측 채널값 3종 모두 '인스타그램 (…)' 접두
# ('인스타그램 (namuk.wellperion)' · '(wellperion 공식)' · '(wellperion)').
# 이 패턴에 안 맞는 채널은 dispatch_publish 의 else 에서 발행 차단(구 폴백 구멍 수리).
_IG_CHANNEL_RE = re.compile(r"인스타|instagram", re.IGNORECASE)

# 정본 = scripts/review_states.py (잎 모듈). 여기서 재정의하지 않고 그대로 재수출한다 —
# publish_digest 도 같은 집합을 봐야 하는데 이 모듈은 publish_digest 를 import 하므로
# (아래 L59) 반대 방향 import 가 순환이라 조용히 복사본으로 떨어졌다(2026-07-24 배9598).
from review_states import TERMINAL_STATES  # noqa: E402  (재수출 — 기존 호출부 무손상)
_DEPRECATED_MARKER_RE = re.compile(r"폐기|DEPRECATED", re.IGNORECASE)
# 같은 실행(run) 안에서 같은 항목을 여러 배제 지점이 중복 기록하지 않도록 하는 프로세스 로컬 dedup.
_TERMINAL_BLOCK_LOGGED: set[str] = set()


def _has_deprecated_marker(folder: str) -> bool:
    """콘텐츠 폴더에 폐기 마커 .md 가 실존하는가(worklog_gaps._is_deprecated_folder 동일 규칙)."""
    folder = (folder or "").strip()
    if not folder:
        return False
    try:
        path = ROOT / folder
        if not path.is_dir():
            return False
        return any(_DEPRECATED_MARKER_RE.search(p.name) for p in path.glob("*.md"))
    except Exception:
        return False


def terminal_reason(it: dict) -> str | None:
    """종결(폐기·취소) 항목이면 사유 문자열, 아니면 None (순수 함수 — 부작용 없음)."""
    status = str(it.get("status", "")).strip()
    if status in TERMINAL_STATES:
        return f"status='{status}'"
    if it.get("terminal"):
        return "terminal 필드=True(스테일·종결 엔트리)"
    folder = str(it.get("folder", "")).strip()
    if _has_deprecated_marker(folder):
        return f"폴더 폐기 마커 실존({folder})"
    return None


def is_terminated(it: dict) -> bool:
    """폐기·취소로 종결된 항목인가 — 발행 후보·카드 발송·dispatch 모든 지점의 단일 판정."""
    return terminal_reason(it) is not None


def block_if_terminated(it: dict, stage: str) -> bool:
    """종결 항목이면 True(=차단) + 1줄 로그 · 결정재생 차단 신호 기록.

    stage = 어느 지점에서 막았나('발행후보선정' · '카드발송' · 'dispatch진입').
    발신하지 않는다(로그·jsonl append 만) — 가드는 조용하고 결정론적이어야 한다.
    """
    reason = terminal_reason(it)
    if reason is None:
        return False
    item_id = str(it.get("id", "")) or str(it.get("folder", "")) or "(id 없음)"
    key = f"{item_id}|{stage}"
    if key not in _TERMINAL_BLOCK_LOGGED:
        _TERMINAL_BLOCK_LOGGED.add(key)
        _safe_print(f"[GUARD] 종결 항목 배제({stage}): {item_id} — {reason}")
        _replay_append(
            "cmo-content-pipeline",
            subject=item_id,
            detail=f"종결(폐기·취소) 항목 {stage} 배제 — {reason}",
        )
    return True

# 블로그·카페 공개 제목 가드 — GM 발견(2026-07-15): title='...[네이버 블로그]' 같은
# 내부 추적 라벨이 그대로 공개 게시글 제목으로 발행됨. 대괄호 채널 태그를 담은 제목은
# 절대 공개발행하지 않는다(post_title 필드로 내부라벨과 공개제목을 분리).
INTERNAL_LABEL_TITLE_RE = re.compile(
    r"\[\s*(네이버\s*)?(블로그|카페|카카오\s*채널?|당근|채널명?)\s*\]", re.IGNORECASE
)


def resolve_public_title(it: dict) -> tuple[str | None, str | None]:
    """블로그·카페 공개 발행에 실제로 쓰일 제목을 결정 + 내부 라벨 가드.

    post_title(공개 제목 전용 필드)이 있으면 우선 사용, 없으면 title로 폴백.
    반환: (공개제목, 차단사유). 차단사유가 not None이면 발행을 스킵해야 한다.
    """
    public_title = (it.get("post_title") or it.get("title") or "").strip()
    if not public_title:
        return None, "공개 제목 없음(title·post_title 모두 비어있음)"
    if INTERNAL_LABEL_TITLE_RE.search(public_title):
        return None, f"내부 라벨 패턴 포함 제목 — 공개발행 차단: {public_title!r}"
    return public_title, None

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV_KEY = "TELEGRAM_CHAT_ID"
# 웰리 검증 큐 채널(예정 수신처) — 실제로는 이 파일의 모든 telegram() 호출이 chat_id를
# 넘기지 않아 전부 TELEGRAM_CHAT_ID(GM DM) 기본값으로 간다(2026-07-22 CTO 확인, 배9424b).
# 즉 TELEGRAM_WELLY_CHAT_ID/아래 폴백은 현재 미사용(죽은 값) — 종합접수방(-5065206276,
# 2026-07-22부터 미처리 적체 리마인드 전용)과는 실사용 충돌이 없다. 향후 이 변수를 실제
# telegram(msg, chat_id=...) 호출에 연결할 때는 종합접수방(-5065206276)을 재사용하지 말 것
# — 리마인드 다이제스트에 IG 알림이 섞인다. 새 채널을 GM에게 배정받아 쓸 것.
TELEGRAM_WELLY_CHAT_ID_ENV_KEY = "TELEGRAM_WELLY_CHAT_ID"
TELEGRAM_CORE_GROUP_CHAT_ID_ENV_KEY = "TELEGRAM_CORE_GROUP_CHAT_ID"


def _load_env_val(key: str) -> str:
    """환경변수 → telegram_bot/.env 순서로 값 로드 (python-dotenv 불필요)."""
    val = os.environ.get(key, "").strip()
    if val:
        return val
    env_file = ROOT / "telegram_bot" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


TELEGRAM_CHAT_ID: str = _load_env_val(TELEGRAM_CHAT_ID_ENV_KEY)  # telegram_bot/.env SSOT
# 웰리 검증 큐 채널 — TELEGRAM_WELLY_CHAT_ID 미설정 시 종합 접수처(내부 운영방)로 폴백
TELEGRAM_WELLY_CHAT_ID: str = (
    _load_env_val(TELEGRAM_WELLY_CHAT_ID_ENV_KEY)
    or _load_env_val(TELEGRAM_CORE_GROUP_CHAT_ID_ENV_KEY)
    or "-5065206276"
)


def _safe_print(text: str) -> None:
    """cp949 등 좁은 콘솔 인코딩에서 인코딩 불가 문자를 '?'로 대체해 출력."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))


# ----------------------------------------------------------------------
def telegram(message: str, chat_id: str | None = None) -> None:
    """텔레그램 1줄 보고 — 토큰 stdout 노출 금지 (메모리 feedback_no_token_in_stdout).

    chat_id 미지정 시 TELEGRAM_CHAT_ID(GM) 사용.
    성공 요약·IG 검증 알림은 TELEGRAM_WELLY_CHAT_ID(웰리/종합 접수처)를 명시해 호출.
    실패·결정 필요 알림은 기본값(GM) 유지.
    """
    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    token = os.environ.get(TELEGRAM_TOKEN_ENV_KEY, "").strip()
    if not token:
        _safe_print("[WARN] 텔레그램 토큰 미설정 — 보고 생략")
        return
    try:
        import urllib.parse
        import urllib.request
        data = urllib.parse.urlencode({
            "chat_id": target_chat_id, "text": message,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
        pace()
        with urllib.request.urlopen(req, timeout=10) as resp:
            _safe_print(f"[INFO] 텔레그램 보고 {'성공' if resp.status == 200 else '실패'} chat_id={target_chat_id}")
            log_outbound(message, chat_id=target_chat_id, source="ig_review_publish_watcher.telegram", ok=(resp.status == 200), kind="sendMessage")
    except Exception:
        log_outbound(message, chat_id=target_chat_id, source="ig_review_publish_watcher.telegram", ok=False, kind="sendMessage")
        _safe_print("[WARN] 텔레그램 보고 실패 (토큰 trace 노출 방지로 상세 미출력)")


def _notify_published(folder: str) -> None:
    """발행완료 직후 '링크 모음' 텔레그램 알림 (비차단 서브프로세스, 실패 무시).
    기존 발행 요약 텔레그램과 별개 메시지 — GM 명시 요청(2026-06-26)."""
    if not folder:
        return
    notify_script = ROOT / "scripts" / "notify_published_links.py"
    try:
        subprocess.Popen(
            [str(PY), str(notify_script), "--folder", folder],
            cwd=str(ROOT),
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        _safe_print(f"[WARN] 링크 모음 알림 서브프로세스 실행 실패(발행 흐름 무영향): {exc}")


def _dispatch_publish_digest(approved: list[dict]) -> int:
    """이번 사이클에 '발행완료'로 전환된 항목만 모아 통합요약 1장 자동발신
    (scripts/publish_digest.py → 문의·컨택·등록 알림방). GM 루틴: '콘텐츠 1건 = 통합요약 한 장'
    (기존 per-channel _notify_published 와 별개). 실패해도 발행 파이프라인(커밋·푸시)엔 영향 없음."""
    newly_published = [it for it in approved if it.get("status") == "발행완료"]
    if not newly_published:
        return 0
    try:
        return send_publish_digest(newly_published)
    except Exception as exc:
        _safe_print(f"[WARN] 발행완료 통합요약 발신 실패(발행 흐름 무영향): {exc}")
        return 0


def load_notified() -> set:
    """이미 검수대기 알림을 발송한 id 집합 로드."""
    if not NOTIFIED_FILE.exists():
        return set()
    try:
        data = json.loads(NOTIFIED_FILE.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def save_notified(notified: set) -> None:
    """검수대기 알림 발송 이력 저장."""
    NOTIFIED_FILE.write_text(
        json.dumps(sorted(notified), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_carded() -> set:
    """send_review_card 가 인라인 카드를 이미 보낸 id 집합. 카드=알림이므로 중복 텍스트 알림 억제."""
    if not CARD_MSGID_STORE.exists():
        return set()
    try:
        data = json.loads(CARD_MSGID_STORE.read_text(encoding="utf-8"))
        return set(data.keys()) if isinstance(data, dict) else set()
    except Exception:
        return set()


def notify_pending_review(items: list) -> None:
    """검수대기 항목 중 아직 알림 안 보낸 건만 텔레그램 발송 후 이력 기록.
    단, 이미 검수카드(인라인 버튼)를 보낸 id 는 건너뜀 — 중복 알림이 텔레그램을 복잡하게 만듦(GM 2026-06-05)."""
    notified = load_notified()
    carded = load_carded()
    newly_notified: list[str] = []
    for it in items:
        if it.get("status") != "검수대기":
            continue
        item_id = it.get("id", "")
        if not item_id or item_id in notified or item_id in carded:
            continue
        # [A2 명문 배제] 종결(폐기·취소) 항목은 승인 카드/알림 자체를 보내지 않는다 —
        # 07-20 취소편이 승인카드 재발송으로 되살아난 사고의 구조적 차단선.
        # 차단한 id 는 notified 에 넣어 매 사이클 재로깅하지 않는다(1회만).
        if block_if_terminated(it, "카드발송"):
            newly_notified.append(item_id)
            continue
        title = it.get("title", item_id)
        channel = it.get("channel", "")
        msg = (
            f"🔎 검수 대기 등록\n"
            f"{title} ({channel}) — 웰페리온 ERP M1에서 미리보기·승인\n"
            f"https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#M1"
        )
        telegram(msg)
        newly_notified.append(item_id)
        _safe_print(f"[INFO] 검수대기 알림 발송: {item_id}")
    if newly_notified:
        notified.update(newly_notified)
        save_notified(notified)


# ─────────────────────────────────────────────────────────────────────────────
# 형제 채널 누락 경보 (배834-A, 2026-07-20 필라테스 L4 사고 재발방지)
#   공식계정(wellperion) IG 엔트리인데 블로그·카페·카카오·당근 형제 엔트리가 하나도
#   없으면 GM 업무보고봇방(TELEGRAM_CHAT_ID)에 1줄 경보. id 당 1회만(파일 dedup) —
#   같은 누락을 매 사이클 재알림하지 않는다.
# ─────────────────────────────────────────────────────────────────────────────
_SIBLING_CHANNEL_KEYWORDS = ("블로그", "카페", "카카오", "당근")


def _load_sibling_alert_notified() -> set:
    if not SIBLING_ALERT_NOTIFIED_FILE.exists():
        return set()
    try:
        data = json.loads(SIBLING_ALERT_NOTIFIED_FILE.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _save_sibling_alert_notified(notified: set) -> None:
    try:
        SIBLING_ALERT_NOTIFIED_FILE.write_text(
            json.dumps(sorted(notified), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        _safe_print(f"[WARN] 형제채널 경보 이력 저장 실패(다음 사이클 재알림 가능): {exc}")


def find_missing_channel_siblings(items: list) -> list:
    """공식계정(wellperion) IG 단독 엔트리 중 블로그·카페·카카오·당근 형제가 하나도
    없는 항목을 반환(순수 함수 — 부작용 없음, 테스트/검증용으로 직접 호출 가능).

    형제 판정: 같은 콘텐츠 폴더를 가리키며(folder 완전일치 또는 'folder/' 하위 서브폴더)
    채널명에 블로그/카페/카카오/당근 키워드가 있는 엔트리가 review_queue 에 존재하는지.
    (두 folder 표기 관례 모두 지원 — register_channels()=베이스 폴더 공유,
     기존 수동등록 관례=채널별 서브폴더.)
    """
    gaps = []
    for it in items:
        if it.get("account") != "wellperion":
            continue
        # [A2 명문 배제] 종결(폐기·취소) 엔트리는 '형제 채널 누락'이 아니다 — 경보 대상 제외.
        if is_terminated(it):
            continue
        channel = it.get("channel", "")
        if "인스타그램" not in channel:
            continue
        item_id = it.get("id", "")
        folder = it.get("folder", "")
        if not item_id or not folder:
            continue
        has_sibling = any(
            other is not it
            and (
                str(other.get("folder", "")) == folder
                or str(other.get("folder", "")).startswith(folder + "/")
            )
            and any(kw in str(other.get("channel", "")) for kw in _SIBLING_CHANNEL_KEYWORDS)
            for other in items
        )
        if not has_sibling:
            gaps.append(it)
    return gaps


def check_missing_channel_siblings(items: list) -> None:
    """find_missing_channel_siblings 결과 중 미경보 건만 GM 채널에 1줄 경보 후 이력 기록."""
    notified = _load_sibling_alert_notified()
    gaps = [g for g in find_missing_channel_siblings(items) if g.get("id") not in notified]
    if not gaps:
        return
    ids_label = ", ".join(g.get("id", "") for g in gaps[:8])
    extra = f" 외 {len(gaps) - 8}건" if len(gaps) > 8 else ""
    msg = (
        f"⚠️ IG 단독 등록(형제 4채널 블로그·카페·카카오·당근 없음) {len(gaps)}건 — "
        f"{ids_label}{extra} · review_channel 형제 등록 확인 요망"
    )
    telegram(msg)
    notified.update(g.get("id", "") for g in gaps)
    _save_sibling_alert_notified(notified)


def git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def pull_latest() -> None:
    """승인 신호 동기화 — dirty tree여도 autostash로 안전 rebase (메모리 git 원샷 원칙)."""
    with GitLock(holder="ig_review_publish:pull", repo_root=str(ROOT)):
        git("fetch", "origin", "master")
        r = git("pull", "--rebase", "--autostash", "origin", "master")
    _safe_print(f"[INFO] git pull: {(r.stdout + r.stderr).strip().splitlines()[-1:] or ['(no output)']}")


def load_queue() -> list:
    if not QUEUE.exists():
        return []
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[ERROR] 큐 파싱 실패: {e}")
        return []


def save_queue(items: list) -> None:
    """락 임계구역에서 디스크 최신본과 id 병합 저장.

    load_queue() → 발행(수 분) → save_queue() 사이에 다른 프로세스가 큐에 추가한
    신규 항목을 스테일 사본으로 덮어써 지우는 사고(2026-07-21 AI하루 10편) 차단.
    """
    merge_save_review_queue(items, holder="ig_review_publish_watcher")


def publish_item(it: dict) -> tuple[str | None, int]:
    """발행 서브프로세스 실행 → (게시 URL|None, exit code) 반환.
    it 에서 folder / location / mentions / account / collaborators 를 추출해 발행기에 CLI 인자로 전달."""
    folder: str = it.get("folder", "")
    location: str = it.get("location", "").strip()
    account: str = it.get("account", "").strip()

    raw_mentions = it.get("mentions", [])
    # mentions 는 리스트 또는 콤마 문자열 모두 허용
    if isinstance(raw_mentions, list):
        mentions_str = ",".join(m.strip() for m in raw_mentions if m.strip())
    else:
        mentions_str = str(raw_mentions).strip()

    raw_collaborators = it.get("collaborators", [])
    # collaborators 는 리스트 또는 콤마 문자열 모두 허용
    if isinstance(raw_collaborators, list):
        collab_str = ",".join(c.strip() for c in raw_collaborators if c.strip())
    else:
        collab_str = str(raw_collaborators).strip()

    cmd = [str(PY), str(PUBLISH_SCRIPT), "--mode", "publish", "--content-folder", folder]
    if account:
        cmd += ["--account", account]
    if location:
        cmd += ["--location", location]
    if mentions_str:
        cmd += ["--mentions", mentions_str]
    if collab_str:
        cmd += ["--collaborators", collab_str]

    # 입력 단일화 (2026-06-04) — 큐의 caption 을 임시파일로 발행기에 전달.
    # 콘텐츠 폴더에 큐레이션_추천.md 가 없어도 review_queue.caption 으로 발행 가능
    # → '큐레이션 누락' FileNotFoundError 즉사 재발방지(오늘 실패 원인 #1).
    # 폴더에 큐레이션_추천.md 가 있으면 발행기가 그쪽을 우선 사용(이 파일 무시).
    caption_text: str = it.get("caption", "") or ""
    caption_tmp: Path | None = None
    if caption_text.strip():
        try:
            import tempfile
            fd, tmp_name = tempfile.mkstemp(prefix="ig_caption_", suffix=".txt")
            os.close(fd)
            caption_tmp = Path(tmp_name)
            caption_tmp.write_text(caption_text, encoding="utf-8")
            cmd += ["--caption-file", str(caption_tmp)]
        except Exception as exc:
            print(f"[WARN] caption 임시파일 생성 실패(큐레이션 md 폴백 의존): {exc}")
            caption_tmp = None

    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", IG_SUPPRESS_TELEGRAM="1")
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env, timeout=600)
    finally:
        if caption_tmp is not None:
            try:
                caption_tmp.unlink()
            except Exception:
                pass
    out = (proc.stdout or "") + (proc.stderr or "")
    _safe_print(out)
    m = POST_URL_RE.search(out)
    url = m.group(1).rstrip("/") + "/" if m else None
    return url, proc.returncode


# 블로그·카페 발행 스크립트 결과 3분류 (2026-07-20 배834 — 재발방지):
#   완료   = exit 0 (공개 URL 실측 회수까지 성공)
#   확인필요 = exit 8 (게시는 진행됐으나 URL 폴링[12초] 실패 — 발행실패 아님, 재발행 금지)
#   실패   = 그 외(exit 7 예외 등)
PUBLISH_RESULT_DONE = "완료"
PUBLISH_RESULT_UNCONFIRMED = "확인필요"
PUBLISH_RESULT_FAILED = "실패"
STATUS_URL_UNCONFIRMED = "확인필요(발행됨·URL미회수)"


def publish_blog(it: dict, public_title: str) -> tuple[str, str | None]:
    """블로그 발행 서브프로세스 실행.
    public_title: resolve_public_title()로 가드 통과한 공개 게시글 제목(내부 라벨 아님).
    반환: (PUBLISH_RESULT_* , url|None)
    """
    cmd = [
        str(PY), str(BLOG_SCRIPT),
        "--mode", "publish",
        "--title", public_title,
        "--body-file", str(ROOT / it["body_file"]),
        "--image-dir", str(ROOT / it["image_dir"]),
        "--sticker-count", "0",  # 하이엔드 브랜드 — GIF 스티커 자동삽입 금지(본문 깨짐 방지, GM 2026-06-05)
        "--i-am-sure",
    ]
    # image_glob 필드가 있으면 추가
    if it.get("image_glob"):
        cmd += ["--image-glob", it["image_glob"]]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=600)
    out = (proc.stdout or "") + (proc.stderr or "")
    _safe_print(out)
    m = POST_URL_RE.search(out)
    url = m.group(1).rstrip("/") + "/" if m else None
    if proc.returncode == 0:
        return PUBLISH_RESULT_DONE, url
    if proc.returncode == 8:
        return PUBLISH_RESULT_UNCONFIRMED, url
    return PUBLISH_RESULT_FAILED, url


def publish_cafe(it: dict, public_title: str) -> tuple[str, str | None]:
    """카페 발행 서브프로세스 실행.
    public_title: resolve_public_title()로 가드 통과한 공개 게시글 제목(내부 라벨 아님).
    반환: (PUBLISH_RESULT_*, url|None)
    """
    cmd = [
        str(PY), str(CAFE_SCRIPT),
        "--mode", "publish",
        "--title", public_title,
        "--body-file", str(ROOT / it["body_file"]),
        "--image-dir", str(ROOT / it["image_dir"]),
        "--sticker-count", "0",  # 하이엔드 브랜드 — GIF 스티커 자동삽입 금지(본문 깨짐 방지, GM 2026-06-05)
        "--i-am-sure",
    ]
    # menuid 필드가 있으면 추가
    if it.get("menuid"):
        cmd += ["--menuid", str(it["menuid"])]
    # image_glob 필드가 있으면 추가
    if it.get("image_glob"):
        cmd += ["--image-glob", it["image_glob"]]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=600)
    out = (proc.stdout or "") + (proc.stderr or "")
    _safe_print(out)
    m = POST_URL_RE.search(out)
    url = m.group(1).rstrip("/") + "/" if m else None
    if proc.returncode == 0:
        return PUBLISH_RESULT_DONE, url
    if proc.returncode == 8:
        return PUBLISH_RESULT_UNCONFIRMED, url
    return PUBLISH_RESULT_FAILED, url


def publish_danggn(it: dict) -> tuple[bool, str]:
    """당근 실 발행 (자동입력+이미지+게시). danggn_upload_playwright.py --mode publish --i-am-sure.
    당근은 당일 QR 로그인 세션 필요 — 세션 만료(exit 5)면 (False, '세션만료')로 폴백.
    반환: (성공여부, 사유). 발레 2026-06-05 사진 7장 자동게시 실증 — 발행완료 처리."""
    folder = it.get("folder", "")
    body_file = it.get("body_file", "")
    cmd = [
        str(PY), str(DANGGN_SCRIPT),
        "--mode", "publish",
        "--i-am-sure",
        "--content-dir", folder,
    ]
    # body_file 필드가 있으면 명시 전달 (2026-07-18 수정) — 미지정 시 스크립트가
    # content-dir 루트의 danggn_copy.md만 찾아 output(당근)/ 하위 파일을 못 읽고
    # "본문 없음"으로 실패했던 결함 수정. publish_kakao와 동일 패턴.
    if body_file:
        cmd += ["--body-file", str(ROOT / body_file)]
    if it.get("image_dir"):
        cmd += ["--image-dir", str(ROOT / it["image_dir"])]
    if it.get("image_glob"):
        cmd += ["--image-glob", it["image_glob"]]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env, timeout=600)
    except Exception as exc:
        return False, f"실행예외:{exc}"
    _safe_print((proc.stdout or "") + (proc.stderr or ""))
    if proc.returncode == 0:
        return True, "ok"
    if proc.returncode == 5:
        return False, "세션만료"  # 당일 QR 로그인 필요
    return False, f"exit={proc.returncode}"


def publish_kakao(it: dict) -> tuple[bool, str]:
    """카카오 채널 실 발행 (publish 실구현). kakao_channel_upload_playwright.py --mode publish --i-am-sure.
    세션(persistent profile) 필요 — 만료/실패 시 (False, 사유)로 폴백.
    ※ 2026-06-05 도입 — 발행 모드 첫 실전은 월요일 바레로 검증 예정."""
    folder = it.get("folder", "")
    body_file = it.get("body_file", "")
    cmd = [
        str(PY), str(KAKAO_SCRIPT),
        "--mode", "publish",
        "--content-dir", folder,
        "--i-am-sure",
    ]
    if body_file:
        cmd += ["--body-file", str(ROOT / body_file)]
    if it.get("image_dir"):
        cmd += ["--image-dir", str(ROOT / it["image_dir"])]
    if it.get("image_glob"):
        cmd += ["--image-glob", it["image_glob"]]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env, timeout=600)
    except Exception as exc:
        return False, f"실행예외:{exc}"
    _safe_print((proc.stdout or "") + (proc.stderr or ""))
    if proc.returncode == 0:
        return True, "ok"
    return False, f"exit={proc.returncode}"


def dispatch_publish(it: dict, events: list) -> None:
    """채널 분기 발행 디스패처.

    ch(channel 필드) 기준:
      블로그 → publish_blog (exit 0 = 완료, URL 있으면 기록)
      카페   → publish_cafe (exit 0 = 완료, URL 있으면 기록)
      카카오·당근 → 자동발행 안 함, 텔레그램 수동 알림 + status='수동발행대기'
      인스타그램 → 기존 publish_item (URL 회수 필수)
      그 외(알 수 없는 채널) → 발행하지 않고 경고 (2026-07-23 배9598)

    it 딕셔너리를 직접 변경(status, post_url, published_at, note).
    events 리스트에 결과 문자열 추가.
    """
    title = it.get("title", it.get("id", "?"))
    ch = it.get("channel", "")

    # [A2 명문 배제 · 최종 방어선] 앞단 필터가 뚫려도 여기서 발행을 막는다.
    # 종결 결정(status 폐기·취소 / terminal / 폴더 폐기 마커)은 status 를 덮어쓰지 않고
    # 그대로 보존한 채 조용히 반환한다(결정 원문 훼손 금지).
    if block_if_terminated(it, "dispatch진입"):
        events.append(f"🛑 {title}: 종결(폐기·취소) 항목 — 발행 안 함")
        return

    if "블로그" in ch:
        # 블로그 자동 공개발행 (GM 승인 2026-07-13 — 전채널 자동발행 표준·요새화 안전망 라이브 후 활성)
        # 공개 제목 가드: 내부 라벨(예 '...[네이버 블로그]')이 그대로 나가는 걸 발행 직전 차단.
        public_title, block_reason = resolve_public_title(it)
        if block_reason:
            it["status"] = "발행보류(제목확인)"
            it["note"] = block_reason
            telegram(f"🚫 [블로그] 공개 제목 가드 차단 — {title}\n사유: {block_reason}")
            events.append(f"🚫 {title} 블로그 발행 보류(제목확인) — {block_reason}")
            worklog_log("cmo", "발행", f"{title} 블로그 발행 보류(제목확인)", result="fail",
                        detail=block_reason, ref=it.get("id", ""))
        else:
            result, url = publish_blog(it, public_title)
            if result == PUBLISH_RESULT_DONE:
                it["status"] = "발행완료"
                if url:
                    it["post_url"] = url
                it["published_at"] = datetime.now().isoformat(timespec="seconds")
                it.pop("note", None)
                events.append(f"✅ {title} 블로그 발행완료" + (f" — {url}" if url else " (URL 회수 불안정·본문 게시됨)"))
                worklog_log("cmo", "발행", f"{title} 블로그 발행완료", result="ok",
                            ref=it.get("id", ""), url=url or "")
            elif result == PUBLISH_RESULT_UNCONFIRMED:
                # 게시는 진행됐으나 공개 URL 폴링(12초) 실패 — '발행실패' 아님. 재발행 절대 금지
                # (중복 게시 방지). URL은 사람이 보강하거나 reconcile_published.py 로 재회수(배834).
                it["status"] = STATUS_URL_UNCONFIRMED
                if url:
                    it["post_url"] = url
                it["published_at"] = datetime.now().isoformat(timespec="seconds")
                it["note"] = "[재발방지 2026-07-20] 블로그 게시는 진행됐으나 공개 URL 폴링 실패 — 재발행 금지, URL 수동 보강/재회수 필요"
                events.append(f"⏳ {title} 블로그 발행됨(URL 미회수) — 확인필요, 재발행 안 함")
                worklog_log("cmo", "발행", f"{title} 블로그 발행됨(URL 미회수)", result="warn",
                            detail="확인필요·재발행 안 함", ref=it.get("id", ""), url=url or "")
            else:
                it["status"] = "발행실패"
                it["note"] = "블로그 발행 스크립트 exit≠0(무결성 게이트 차단 가능 — 초안 유지)"
                events.append(f"⚠️ {title} 블로그 발행 실패 — exit code 비정상")
                worklog_log("cmo", "발행", f"{title} 블로그 발행 실패", result="fail",
                            detail="exit code 비정상", ref=it.get("id", ""))

    elif "카페" in ch:
        # 카페 자동 공개발행 (GM 승인 2026-07-13 — 전채널 자동발행 표준·요새화 안전망 라이브 후 활성)
        # 공개 제목 가드: 내부 라벨(예 '...[네이버 카페]')이 그대로 나가는 걸 발행 직전 차단.
        public_title, block_reason = resolve_public_title(it)
        if block_reason:
            it["status"] = "발행보류(제목확인)"
            it["note"] = block_reason
            telegram(f"🚫 [카페] 공개 제목 가드 차단 — {title}\n사유: {block_reason}")
            events.append(f"🚫 {title} 카페 발행 보류(제목확인) — {block_reason}")
            worklog_log("cmo", "발행", f"{title} 카페 발행 보류(제목확인)", result="fail",
                        detail=block_reason, ref=it.get("id", ""))
        else:
            result, url = publish_cafe(it, public_title)
            if result == PUBLISH_RESULT_DONE:
                it["status"] = "발행완료"
                if url:
                    it["post_url"] = url
                it["published_at"] = datetime.now().isoformat(timespec="seconds")
                it.pop("note", None)
                events.append(f"✅ {title} 카페 발행완료" + (f" — {url}" if url else " (URL 회수 불안정·본문 게시됨)"))
                worklog_log("cmo", "발행", f"{title} 카페 발행완료", result="ok",
                            ref=it.get("id", ""), url=url or "")
            elif result == PUBLISH_RESULT_UNCONFIRMED:
                # 게시는 진행됐으나 공개 URL 폴링(12초) 실패 — '발행실패' 아님. 재발행 절대 금지
                # (중복 게시 방지). URL은 사람이 보강하거나 reconcile_published.py 로 재회수(배834).
                it["status"] = STATUS_URL_UNCONFIRMED
                if url:
                    it["post_url"] = url
                it["published_at"] = datetime.now().isoformat(timespec="seconds")
                it["note"] = "[재발방지 2026-07-20] 카페 게시는 진행됐으나 공개 URL 폴링 실패 — 재발행 금지, URL 수동 보강/재회수 필요"
                events.append(f"⏳ {title} 카페 발행됨(URL 미회수) — 확인필요, 재발행 안 함")
                worklog_log("cmo", "발행", f"{title} 카페 발행됨(URL 미회수)", result="warn",
                            detail="확인필요·재발행 안 함", ref=it.get("id", ""), url=url or "")
            else:
                it["status"] = "발행실패"
                it["note"] = "카페 발행 스크립트 exit≠0(무결성 게이트 차단 가능 — 초안 유지)"
                events.append(f"⚠️ {title} 카페 발행 실패 — exit code 비정상")
                worklog_log("cmo", "발행", f"{title} 카페 발행 실패", result="fail",
                            detail="exit code 비정상", ref=it.get("id", ""))

    elif "당근" in ch:
        # 당근 실 발행 — 자동입력+이미지+게시(발레 2026-06-05 사진 7장 실증).
        # 당일 QR 로그인 세션 필요 — 세션 만료 시 수동 알림으로 안전 폴백.
        ok, reason = publish_danggn(it)
        folder = it.get("folder", "(폴더 미지정)")
        if ok:
            it["status"] = "발행완료"
            it["published_at"] = datetime.now().isoformat(timespec="seconds")
            it.pop("note", None)
            events.append(f"✅ {title} 당근 발행 완료")
            worklog_log("cmo", "발행", f"{title} 당근 발행완료", result="ok", ref=it.get("id", ""))
            _notify_published(it.get("folder", ""))
        else:
            it["status"] = "수동발행대기"
            it["note"] = f"당근 자동 발행 실패({reason}) — 수동 업로드 필요"
            telegram(
                f"📦 [당근채널] 승인됨 — 수동 업로드 필요({reason})\n"
                f"폴더: {folder}\n본문: {it.get('body_file','(본문파일 미지정)')}"
            )
            events.append(f"📦 {title}: 당근 수동 업로드 대기(GM) — {reason}")
            worklog_log("cmo", "발행", f"{title} 당근 수동 업로드 대기", result="warn",
                        detail=reason, ref=it.get("id", ""))

    elif "카카오" in ch:
        # 카카오 채널 — 승인=바로 발행 (publish 실구현, GM 2026-06-05). 실패 시 수동 알림 폴백.
        # ※ 발행 모드 첫 실전 = 월요일 바레로 검증 예정.
        ok, reason = publish_kakao(it)
        folder = it.get("folder", "(폴더 미지정)")
        if ok:
            it["status"] = "발행완료"
            it["published_at"] = datetime.now().isoformat(timespec="seconds")
            it.pop("note", None)
            events.append(f"✅ {title} 카카오 채널 발행 완료")
            worklog_log("cmo", "발행", f"{title} 카카오 채널 발행완료", result="ok", ref=it.get("id", ""))
            _notify_published(it.get("folder", ""))
        else:
            it["status"] = "수동발행대기"
            it["note"] = f"카카오 자동 발행 실패({reason}) — 수동 업로드 필요"
            telegram(
                f"📦 [카카오 채널] 승인됨 — 자동발행 실패({reason}), 수동 업로드 필요\n"
                f"폴더: {folder}\n본문: {it.get('body_file','(본문파일 미지정)')}"
            )
            events.append(f"📦 {title}: 카카오 수동 업로드 대기(GM) — {reason}")
            worklog_log("cmo", "발행", f"{title} 카카오 수동 업로드 대기", result="warn",
                        detail=reason, ref=it.get("id", ""))

    elif _IG_CHANNEL_RE.search(ch):
        # [계정 가드 2026-06-16] IG 교차발행 차단 — 공식 콘텐츠가 account 누락으로 개인계정에
        # (또는 그 반대로) 잘못 발행되는 것을 구조적으로 막는다. 발행기 기본 폴백=namuk.wellperion(개인)이라
        # 공식 채널은 account='wellperion'을 명시해야만 발행. (GM 지시 박제)
        channel = it.get("channel", "")
        account_l = (it.get("account", "") or "").strip()
        effective = account_l or "namuk.wellperion"  # 발행기 미지정 시 폴백 계정
        mismatch = None
        if "공식" in channel and effective != "wellperion":
            mismatch = f"공식 채널인데 발행계정='{effective}' (개인계정 폴백 위험)"
        elif "namuk" in channel and effective == "wellperion":
            mismatch = "개인 채널인데 발행계정='wellperion' (공식 오발행 위험)"
        if mismatch:
            it["status"] = "발행보류(계정확인)"
            it["note"] = f"[계정 가드] {mismatch} — review_queue 의 account 를 채널에 맞게 지정 후 재승인."
            telegram(
                f"⛔ [계정 가드] {title}\n{mismatch}\n"
                f"교차발행 방지로 발행을 막았습니다. review_queue 의 account 를 바로잡고 다시 [승인]하세요."
            )
            events.append(f"⛔ {title}: 계정 가드 발동 — {mismatch}")
            worklog_log("cmo", "발행", f"{title} 계정 가드 발동(발행 차단)", result="fail",
                        detail=mismatch, ref=it.get("id", ""))
            return
        # 기존 IG 경로 — publish_item 결과(URL, exit code) 기준으로 성공 판정
        url, rc = publish_item(it)
        if url:
            it["status"] = "발행검증대기"
            it["post_url"] = url
            it["published_at"] = datetime.now().isoformat(timespec="seconds")
            it.pop("note", None)
            events.append(f"✅ {title} 발행 완료 — {url}")
            worklog_log("cmo", "발행", f"{title} 인스타 발행완료", result="ok",
                        ref=it.get("id", ""), url=url)
        elif rc == 9:
            # (CTO 2026-06-11) rc==9 = 성공 토스트 확인됨 = 발행 동작 자체는 성공.
            # 신규 shortcode(게시 URL) 회수만 캐시지연으로 윈도우 내 미확정 — 개인계정의
            # '알려진 false-negative'. 발행 동작이 성공했으므로 status='발행완료' 도장.
            # (검증 근거 = 발행 동작 성공[토스트]이지, 별도 URL 재조회가 아니다.)
            # ⚠️ 자동 재발행 절대 금지 — 한 번 [승인]=한 번 발행. URL은 GM/추후 수동 보강 가능.
            it["status"] = "발행검증대기"
            it["published_at"] = datetime.now().isoformat(timespec="seconds")
            it["note"] = "[봇 자동검증] pub 콜백 발행성공 → 발행검증대기(개인계정 URL회수 false-negative 무관)"
            events.append(f"✅ {title} 발행 완료 — 성공 토스트 확인(URL 캐시지연, 수동 보강 가능)")
            worklog_log("cmo", "발행", f"{title} 인스타 발행", result="warn",
                        detail="성공 토스트 확인·주소 미회수", ref=it.get("id", ""))
        else:
            it["status"] = "발행실패"
            it["note"] = "게시 URL 미회수 — 수동 점검 필요"
            events.append(f"⚠️ {title} 발행 실패 — 게시 URL 미회수")
            worklog_log("cmo", "발행", f"{title} 인스타 발행 실패", result="fail",
                        detail="게시 URL 미회수", ref=it.get("id", ""))

    else:
        # [채널 가드 2026-07-23 배9598] 구 코드의 else 폴백은 '나머지 전부'를 IG 발행기로
        # 보냈다 — 콘텐츠 접수 등 비발행 항목이나 오타 채널명이 승인되면 그대로 인스타에
        # 발행된다. 예상 채널(블로그·카페·당근·카카오·인스타) 밖이면 발행하지 않고 경고만.
        unknown = ch.strip() or "(채널 미지정)"
        it["status"] = "발행보류(채널확인)"
        it["note"] = (
            f"[채널 가드] 알 수 없는 채널 '{unknown}' — 자동 발행 경로 없음. "
            "review_queue 의 channel 을 블로그·카페·당근·카카오·인스타그램 중 하나로 바로잡고 재승인."
        )
        telegram(
            f"⛔ [채널 가드] {title}\n알 수 없는 채널: {unknown}\n"
            f"발행 경로가 없어 발행을 막았습니다. review_queue 의 channel 을 확인하세요."
        )
        events.append(f"⛔ {title}: 채널 가드 발동 — 알 수 없는 채널 '{unknown}'")
        worklog_log("cmo", "발행", f"{title} 채널 가드 발동(발행 차단)", result="fail",
                    detail=f"알 수 없는 채널 '{unknown}'", ref=it.get("id", ""))


def process_queue(items: list, dry_run: bool) -> tuple[list, list]:
    """승인 건 처리. (변경된 items, 이벤트 로그) 반환. dry_run이면 발행 안 함."""
    events: list[str] = []
    for it in items:
        if it.get("status") not in APPROVED_STATES:
            continue
        # [A2 명문 배제] 승인 목록에 들어왔더라도 종결(폐기·취소) 신호가 있으면 발행하지 않는다.
        if block_if_terminated(it, "발행후보선정"):
            continue
        title = it.get("title", it.get("id", "?"))
        folder = it.get("folder")
        if not folder:
            it["status"] = "발행실패"
            it["note"] = "folder 필드 없음 — 발행 대상 폴더 미지정"
            events.append(f"⛔ {title}: folder 미지정")
            continue
        if dry_run:
            ch_info = it.get("channel", "")
            location_info = it.get("location", "")
            mentions_info = it.get("mentions", [])
            events.append(
                f"🔎 [dry-run] 발행 대상: {title} (folder={folder}"
                + (f", channel={ch_info!r}" if ch_info else "")
                + (f", location={location_info!r}" if location_info else "")
                + (f", mentions={mentions_info}" if mentions_info else "")
                + ")"
            )
            continue
        # 채널 분기 디스패처 — IG/블로그/카페/카카오·당근 분기 처리
        dispatch_publish(it, events)
    return items, events


def acquire_publish_lock() -> bool:
    """발행 직렬화 락 획득. 다른 발행 프로세스(승인 클릭 --once + 상시 watcher)가
    동시에 같은 큐를 처리해 (a) lost-update로 status 되돌림 (b) 동일 업로드 동시 실행 →
    한쪽 exit≠0을 '실패'로 오보 하는 사고 근본 차단(2026-06-05 발레 4채널 사고).
    획득 실패 시 False 반환(이번 사이클은 조용히 스킵 — 이미 다른 프로세스가 처리 중)."""
    try:
        if PUBLISH_LOCK_FILE.exists():
            age = time.time() - PUBLISH_LOCK_FILE.stat().st_mtime
            if age > PUBLISH_LOCK_STALE_SEC:
                print(f"[WARN] 발행 락 stale({int(age)}s) 회수")
                try:
                    PUBLISH_LOCK_FILE.unlink()
                except FileNotFoundError:
                    pass
        # O_EXCL: 원자적 배타 생성 — 동시 두 프로세스 중 하나만 성공
        fd = os.open(str(PUBLISH_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        print("[INFO] 다른 발행 프로세스 진행 중 - 이번 사이클 스킵(중복 발행/알림 방지).")
        return False
    except Exception as exc:
        print(f"[WARN] 발행 락 획득 예외({exc}) — 안전상 스킵")
        return False


def release_publish_lock() -> None:
    try:
        PUBLISH_LOCK_FILE.unlink()
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f"[WARN] 발행 락 해제 예외({exc})")


def run_once(dry_run: bool) -> int:
    # dry-run은 발행/알림이 없으므로 락 불필요(로직만 점검).
    if dry_run:
        return _run_once_inner(dry_run)
    if not acquire_publish_lock():
        return 0
    try:
        return _run_once_inner(dry_run)
    finally:
        release_publish_lock()


def _run_once_inner(dry_run: bool) -> int:
    if not dry_run:
        pull_latest()
    items = load_queue()
    # 검수대기 신규 항목 텔레그램 알림 (중복 방지 이력 기반)
    notify_pending_review(items)
    # 형제 채널 누락 경보 (배834-A) — dry_run 여부와 무관하게 로직만 점검(부작용은 알림 1건뿐).
    try:
        check_missing_channel_siblings(items)
    except Exception as exc:
        _safe_print(f"[WARN] 형제채널 누락 점검 예외(발행 흐름 무영향): {exc}")
    # [A2 명문 배제] 발행 후보 선정 = 승인 상태 AND 종결(폐기·취소) 아님. 두 조건 모두 명시.
    approved = [
        it for it in items
        if it.get("status") in APPROVED_STATES and not block_if_terminated(it, "발행후보선정")
    ]
    if not approved:
        _safe_print("[INFO] 발행할 승인 건 없음.")
        return 0
    _safe_print(f"[INFO] 승인 건 {len(approved)}개 처리 시작 (dry_run={dry_run})")
    items, events = process_queue(items, dry_run)
    for e in events:
        _safe_print("  " + e)
    published = [e for e in events if e.startswith("✅")]
    manual = [e for e in events if e.startswith("📦")]
    if not dry_run and events:
        save_queue(items)
        # 콘텐츠 폴더 동반 add (2026-07-14 시토 · CTO-2026-07-14-AUTOCOMMIT-UNTRACKED-CONTENT) —
        # 기존엔 QUEUE(review_queue.json) 만 add 해서 status는 커밋되는데 발행된 실제 콘텐츠 폴더
        # (instagram/**, 신규 untracked 디렉토리 포함)는 빠짐 → 수일간 미커밋 누적 → 무인 러너
        # 클린트리 가드 발동(skip) 원인이 됨. approved 처리 대상의 folder/image_dir/body_file
        # 경로를 콘텐츠 루트로 스코프해 함께 add(git add -A 아님 — 무관 WIP 혼입 방지).
        content_paths: set[str] = set()
        for it in approved:
            for key in ("folder", "image_dir", "body_file"):
                v = it.get(key)
                if v:
                    content_paths.add(str(v))
        # 안전 커밋터(2026-07-23 배9820) — 기존엔 라이브 인덱스에 add 후 pathspec 없는
        # `git commit` 이라 그 순간 남이 stage 해둔 무관 파일까지 통째로 실렸고(이력 귀속
        # 어긋남), 옛 트리 스냅샷 위에 커밋되면 그 사이 들어온 파일이 '삭제'로 기록됐다
        # (2026-07-21 AI하루 190파일 삭제). safe_commit 은 임시 인덱스(read-tree HEAD)로
        # 지정 경로만 담고, 커밋 직전 HEAD 재검증 + update-ref CAS 로 원자 커밋한다.
        # push 는 기존 post_commit_push.py 를 그대로 호출(update-ref 는 post-commit 훅
        # 미발화). pull --rebase 는 뺐다 — 매 사이클 시작의 pull_latest() 가 이미 동기화하고,
        # 공용 작업트리에서의 rebase 자체가 사고 원인이었다.
        commit_paths = [str(QUEUE)] + [
            str(ROOT / rel) for rel in sorted(content_paths) if (ROOT / rel).exists()
        ]
        res = safe_commit(
            commit_paths,
            f"auto(cmo): 검수 승인 건 발행 {len(published)}건 / 수동대기 {len(manual)}건",
            holder="ig_review_publish:commit",
        )
        _safe_print(f"[{'INFO' if res['ok'] else 'WARN'}] 커밋: {res['reason']}"
                    + (f" · 혼입 {res['foreign']}" if res["foreign"] else ""))

        # 알림 라우팅 원칙(GM 지시 2026-06-24):
        # - 실패·수동대기 포함 → GM 채널 발송.
        # - 성공 요약 → GM 채널 발송(항상 1건 전달).
        # - IG 발행검증대기(shortcode 미회수 등) → 텔레그램 발송 없음. 로그·큐 상태로만 처리.
        failed_events = [e for e in events if e.startswith("⚠️") or e.startswith("⛔")]
        verify_events = [e for e in events if "발행검증대기" in e]

        summary_text = "📲 멀티채널 발행 결과\n" + "\n".join(events)
        # 성공/실패 모두 GM 채널로 1건 발송
        telegram(summary_text)

        # 발행완료 → 콘텐츠 1건 통합요약 자동발신(문의·컨택·등록 알림방, GM 루틴 박제 2026-07-15)
        _dispatch_publish_digest(approved)

        # IG 발행검증대기 — 텔레그램 발송 없음(GM 노이즈 0). 로그만.
        if verify_events:
            for v in verify_events:
                _safe_print(f"[INFO] 발행검증대기(로그전용): {v}")
    return len(published)


def main() -> None:
    p = argparse.ArgumentParser(description="인스타 검수 승인 → 자동 발행 감시기")
    p.add_argument("--once", action="store_true", help="단발 실행 (예약작업 권장)")
    p.add_argument("--interval", type=int, default=300, help="반복 주기(초), --once 없을 때")
    p.add_argument("--dry-run", action="store_true", help="발행 없이 로직만")
    args = p.parse_args()

    if args.once:
        run_once(args.dry_run)
        return
    print(f"[INFO] 감시기 시작 — {args.interval}s 주기 (Ctrl+C 종료)")
    while True:
        try:
            run_once(args.dry_run)
        except Exception as e:
            print(f"[ERROR] 사이클 예외: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
