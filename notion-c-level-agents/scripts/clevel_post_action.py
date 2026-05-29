# -*- coding: utf-8 -*-
"""
C-Level .bat 종료 직전 표준 post-action 훅 (hook) 모듈

역할(R/R): AI CTO -- IT 인프라 표준화
작성일: 2026-04-26

사용법:
    python scripts/clevel_post_action.py
        --clevel CTO
        --task-id CTO-002
        --status 완료
        --summary "PC 자동 ON/OFF v1.0 가동"
        --version v1.0
        --changelog "2026-04-26 가동 시작"

    # 실제 API 호출 없이 페이로드만 확인 (안전 검증)
    python scripts/clevel_post_action.py --dry-run
        --clevel CTO --task-id CTO-002 --status 완료
        --summary "테스트" --version v1.0 --changelog "변경 없음"
"""

import argparse
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Windows 환경에서 터미널 출력 인코딩을 UTF-8로 강제 설정
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# notion-c-level-agents 패키지 루트를 sys.path에 추가
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_PACKAGE_ROOT / ".env")
except ImportError:
    pass  # dotenv 없으면 환경 변수에서 직접 읽음

# ── 상수 ─────────────────────────────────────────────────────────────────────

TELEGRAM_CHAT_ID = "8254867551"          # @namuki_report_bot 고정 Chat ID
VALID_CLEVELS = {"CEO", "CFO", "CHRO", "CMO", "COO", "CPO", "CTO"}
VALID_STATUSES = {"진행중", "완료", "이슈"}

# 듀얼 시그널(dual-signal) 완료 판별 정규화 매핑
_DONE_ALIASES = {"완료", "DONE", "done", "Done"}

# status/<clevel>.json 파일 기본 경로 (메인 repo 루트 기준)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATUS_DIR = _REPO_ROOT / "status"

# ── 헬퍼: 로컬 상태 파일 기록 ────────────────────────────────────────────────────

def normalize_status(raw_status: str) -> str:
    """
    완료 계열 별칭을 "DONE"으로 정규화.
    그 외 값(예: "진행중", "이슈")은 원문 그대로 반환.
    """
    return "DONE" if raw_status in _DONE_ALIASES else raw_status


def write_status_file(
    clevel: str,
    task_id: str,
    title: str,
    status: str,
    artifact_url,
    note: str,
    dry_run: bool = False,
) -> bool:
    """
    status/<clevel>.json 에 듀얼 시그널(dual-signal) 용 상태를 기록한다.

    - 기존 파일의 다른 키(clevel, last_task_id 등)는 보존(read-merge).
    - status 는 normalize_status() 로 정규화 후 기록 ("DONE" 또는 원문).
    - dry_run=True 이면 기록 예정 JSON을 stdout 에 출력하고 파일 쓰기 생략.
    """
    canonical = clevel.lower()
    status_path = _STATUS_DIR / f"{canonical}.json"

    # 기존 파일 읽기 (없으면 빈 dict)
    existing: dict = {}
    if status_path.exists():
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    normalized = normalize_status(status)
    updated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # 지정된 8개 키만 덮어쓰기, 나머지 기존 키 보존
    patch = {
        "agent": canonical,
        "task_id": task_id,
        "title": title,
        "status": normalized,
        "updated_at": updated_at,
        "artifact_url": artifact_url,
        "commit": "",   # sha 는 git commit 시점에 미지수 — 빈 문자열
        "note": note,
    }
    merged = {**existing, **patch}

    if dry_run:
        print("[DRY-RUN] status 파일 기록 예정 JSON:")
        print(json.dumps(merged, ensure_ascii=False, indent=2))
        print(f"[DRY-RUN] 대상 경로: {status_path}")
        return True

    try:
        _STATUS_DIR.mkdir(parents=True, exist_ok=True)
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"[StatusFile] 기록 완료 — {status_path.name} | status={normalized}")
        return True
    except OSError as exc:
        print(f"[ERROR] status 파일 기록 실패: {exc}", file=sys.stderr)
        return False


# ── 헬퍼: Notion patch ────────────────────────────────────────────────────────

def build_notion_payload(
    task_id: str,
    status: str,
    version: str,
    changelog: str,
    patch_status: bool,
) -> dict:
    """
    업무자동화DB 레코드 patch 페이로드(payload, 전송 데이터) 구성.

    설계 원칙 (2026-05-21 CTO 가드 회귀 진단 후 정정):
    - 메모리 feedback_no_status_regression_on_body_patch 정합 — 본문/버전 patch 시
      `상태` 필드 동시 patch 금지. `--patch-status` 플래그 명시 시에만 포함.
    - 메모리 feedback_db_changelog_summary_only 정합 — `Changelog` 속성은 폐기,
      본문 토글 단일 운영. patch에서 제거. (changelog 인자는 본문 append 용도로만 사용)
    - 자동화DB `상태` 필드는 select 타입 — `status` 타입 patch는 default reset 유발.
    """
    properties: dict = {
        "버전": {"rich_text": [{"text": {"content": version}}]},
    }
    if patch_status:
        # 자동화DB `상태` = select 타입 (status 타입 아님). 회귀 원인 차단.
        properties["상태"] = {"select": {"name": status}}
    return {
        "target": task_id,
        "properties": properties,
        "_meta": {
            "patch_status": patch_status,
            "changelog_skipped": True,  # 본문 토글 단일 운영 — 별도 호출자가 본문 append 책임
        },
    }


def patch_notion(
    task_id: str,
    status: str,
    version: str,
    changelog: str,
    dry_run: bool,
    patch_status: bool,
) -> bool:
    """Notion 페이지 patch 실행. dry_run=True 이면 stdout 출력만."""
    payload = build_notion_payload(task_id, status, version, changelog, patch_status)

    if dry_run:
        print("[DRY-RUN] Notion patch 페이로드 (payload, 전송 데이터):")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return True

    # task_id가 UUID 형식인지 간단 판별 (하이픈 제거 후 32자리 hex)
    raw_id = task_id.replace("-", "")
    if len(raw_id) == 32 and all(c in "0123456789abcdefABCDEF" for c in raw_id):
        try:
            from notion_client import Client as NotionSDKClient
            api_key = os.getenv("NOTION_API_KEY", "")
            if not api_key:
                print("[ERROR] NOTION_API_KEY 환경 변수가 설정되지 않았습니다.", file=sys.stderr)
                return False
            client = NotionSDKClient(auth=api_key)
            client.pages.update(page_id=task_id, properties=payload["properties"])
            print(f"[Notion] patch 완료 — page_id: {task_id}, 상태: {status}, 버전: {version}")
            return True
        except Exception as exc:
            print(f"[ERROR] Notion patch 실패: {exc}", file=sys.stderr)
            return False
    else:
        # UUID가 아닌 식별자(예: CTO-002)는 검색 후 수동 확인 안내
        print(
            f"[Notion] task-id '{task_id}' 는 UUID 형식이 아닙니다.\n"
            "  Notion 업무자동화DB에서 해당 레코드를 검색하여 page_id를 확인 후 재실행하거나,\n"
            "  CEO가 직접 상태를 수동 갱신하세요."
        )
        return True  # 경고이지만 치명적 실패는 아님


# ── 헬퍼: 텔레그램(Telegram) 보고 ─────────────────────────────────────────────

def build_telegram_message(clevel: str, task_id: str, status: str, summary: str) -> str:
    """표준 보고 메시지 문자열 생성."""
    return f"[{clevel}] {task_id} {status} - {summary}"


def send_telegram(clevel: str, task_id: str, status: str, summary: str, dry_run: bool) -> bool:
    """@namuki_report_bot 으로 단일 보고 라인 발송."""
    message = build_telegram_message(clevel, task_id, status, summary)

    if dry_run:
        print(f"[DRY-RUN] 텔레그램(Telegram) 발송 예정 메시지:\n  Chat ID : {TELEGRAM_CHAT_ID}\n  본문    : {message}")
        return True

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("[ERROR] TELEGRAM_BOT_TOKEN 환경 변수가 설정되지 않았습니다.", file=sys.stderr)
        return False

    try:
        import httpx
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        result = resp.json()
        if result.get("ok"):
            print(f"[Telegram] 보고 완료: {message}")
            try:
                import sys as _s
                _s.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "telegram_bot"))
                from message_store import append_message as _inbox_log
                _inbox_log("out", clevel, message, msg_type="report")
            except Exception:
                pass
            return True
        else:
            print(f"[ERROR] 텔레그램(Telegram) 발송 실패: {result}", file=sys.stderr)
            return False
    except Exception as exc:
        print(f"[ERROR] 텔레그램(Telegram) 발송 예외: {exc}", file=sys.stderr)
        return False


# ── 인자 파싱(parsing, 분석) ───────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="C-Level .bat post-action 표준 훅 (hook) — Notion patch + 텔레그램(Telegram) 보고"
    )
    parser.add_argument(
        "--clevel",
        required=True,
        choices=sorted(VALID_CLEVELS),
        help="실행 주체 C-Level (예: CTO)",
    )
    parser.add_argument(
        "--task-id",
        required=True,
        help="업무자동화DB 레코드 식별자 또는 Notion page UUID (예: CTO-002 또는 3ab1...)",
    )
    parser.add_argument(
        "--status",
        required=True,
        choices=sorted(VALID_STATUSES),
        help="처리 상태: 진행중 | 완료 | 이슈",
    )
    parser.add_argument(
        "--summary",
        required=True,
        help='텔레그램(Telegram) 보고 요약 1줄 (예: "PC 자동 ON/OFF v1.0 가동")',
    )
    parser.add_argument(
        "--version",
        default="v1.0",
        help="버전 문자열 (예: v1.1). 기본값: v1.0",
    )
    parser.add_argument(
        "--changelog",
        default="",
        help='Changelog 항목 1줄 (예: "2026-04-26 가동 시작")',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 API 호출 없이 페이로드(payload)만 stdout 출력 (안전 검증 모드)",
    )
    parser.add_argument(
        "--patch-status",
        action="store_true",
        help=(
            "업무자동화DB `상태` 필드를 patch에 포함 (기본 OFF). "
            "본문/버전만 갱신하는 routine 호출은 OFF 유지 — 메모리 "
            "feedback_no_status_regression_on_body_patch 정합. "
            "진행중→완료 등 명시 상태 전환 시에만 ON."
        ),
    )
    parser.add_argument(
        "--artifact-url",
        default=None,
        help="산출물 URL (예: Notion 페이지 링크). 없으면 null 기록.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="작업 제목. 생략 시 --summary 값으로 대체.",
    )
    return parser.parse_args()


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    dry_run: bool = args.dry_run

    if dry_run:
        print("=" * 60)
        print("[DRY-RUN MODE] 실제 Notion/텔레그램(Telegram) API 호출 없음")
        print("=" * 60)

    ok_notion = patch_notion(
        task_id=args.task_id,
        status=args.status,
        version=args.version,
        changelog=args.changelog or f"{datetime.now().strftime('%Y-%m-%d')} {args.status}",
        dry_run=dry_run,
        patch_status=args.patch_status,
    )

    ok_tg = send_telegram(
        clevel=args.clevel,
        task_id=args.task_id,
        status=args.status,
        summary=args.summary,
        dry_run=dry_run,
    )

    # 듀얼 시그널(dual-signal) 프로듀서(producer): 로컬 status/<clevel>.json 기록
    # Notion 상태 필드는 건드리지 않음 (feedback_no_status_regression_on_body_patch 정합)
    ok_status = write_status_file(
        clevel=args.clevel,
        task_id=args.task_id,
        title=args.title if args.title else args.summary,
        status=args.status,
        artifact_url=args.artifact_url,
        note=args.summary,
        dry_run=dry_run,
    )

    if dry_run:
        print("=" * 60)
        print("[DRY-RUN] 검증 결과: Notion 페이로드(payload) OK /", "텔레그램(Telegram) 메시지 OK / StatusFile OK")
        print("=" * 60)

    # 셋 중 하나라도 실패 시 exit code(종료 코드) 1 반환
    return 0 if (ok_notion and ok_tg and ok_status) else 1


if __name__ == "__main__":
    sys.exit(main())
