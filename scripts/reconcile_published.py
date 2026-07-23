# scripts/reconcile_published.py
# 발행 대조·URL 백필 (비파괴·멱등)
#
# review_queue.json을 스캔해 retrieve_post_url 엔진으로 누락 URL을 채운다.
#
# 정책:
#   - 긍정 일치(URL 실제로 찾음)일 때만 기록. 못 찾으면 무변경(stderr 로그만).
#   - 이미 post_url 있는 행은 건드리지 않음 (멱등).
#   - 못 찾은 행을 '미발행'으로 바꾸지 않음.
#   - 변경 발생 시 review_queue.json.bak_YYYYMMDD_HHMMSS 백업 먼저 저장 후 원본 갱신.
#   - JSON 구조·다른 필드 보존, 들여쓰기 2칸 유지.
#
# CLI:
#   --dry-run                  변경 없이 '채울 수 있는 URL 목록' 출력
#   --channels blog,cafe,kakao 대상 채널 쉼표 구분 (기본: 전체)
#   --limit N                  처리 건수 제한
#   --max-seconds N            1회 실행 시간 상한 — 넘으면 남은 건은 다음 회차로 (무인 편승용)
#   --headful                  브라우저 창 표시 (디버그)

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_SCRIPTS_DIR_FOR_WORKLOG = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR_FOR_WORKLOG not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR_FOR_WORKLOG)

try:  # 작업 현황 로그(best-effort) — 임포트 실패해도 대조·백필 흐름 무영향
    from worklog import log as worklog_log
except Exception:
    def worklog_log(*a, **k):
        return False

sys.path.insert(0, str(Path(__file__).resolve().parent))
# review_queue.json 쓰기 단일 관문(락 직렬화 · 2026-07-23 · 07-21 AI하루 10편 소실 재발방지)
from review_queue_util import merge_save_review_queue  # noqa: E402

ROOT        = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE_PATH  = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
SCRIPTS_DIR = ROOT / "scripts"
NOTIFY_SCRIPT = SCRIPTS_DIR / "notify_published_links.py"

KST = timezone(timedelta(hours=9))

# 채널 표시명 → retrieve_url 엔진 채널명
CHANNEL_MAP: dict[str, str] = {
    "네이버 블로그":             "blog",
    "네이버 카페 (동부이촌동)":  "cafe",
    "카카오 채널":               "kakao",
    "당근채널":                  "danggn",
}

# 임시저장완료→손게시 탐지 후보 대상 채널 (블로그·카페만)
DRAFT_DETECT_CHANNELS = {"blog", "cafe"}

# '확인필요(발행됨·URL미회수)' 상태(2026-07-20 배834) — 게시는 됐으나 URL 폴링 실패한 건.
# 재발행 대상 아님(워처가 절대 재발행 안 함) — URL만 재회수해 발행완료로 전환.
STATUS_URL_UNCONFIRMED = "확인필요(발행됨·URL미회수)"


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _now_kst() -> str:
    return datetime.now(tz=KST).strftime("%Y-%m-%d")


def _backup_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return QUEUE_PATH.with_suffix(f".json.bak_{ts}")


# 제목 끝에 붙는 '글 내용이 아닌' 괄호 접미사 — 채널명 + 발행상태.
# (2026-07-23 배9578 실측: '(임시저장)'·'(발행완료)'가 이 목록에 없어 안 떨어졌다.
#  큐 실제 사용 접미사 전수: 개인계정·개인계정·공식디자인·카카오 채널·네이버 블로그·
#  네이버 카페·동부이촌동·당근채널·당근·회사공식·공식·임시저장·발행완료.)
# ⚠ '(수영장)'·'(디지털 디톡스)'처럼 제목의 일부인 괄호는 절대 지우면 안 되므로
#   아래 열거된 표식이 들어있는 괄호만 지운다.
_TITLE_SUFFIX_RE = re.compile(
    r"\s*\([^)]*(?:채널|블로그|카페|계정|인스타|IG|동부이촌동|당근|공식디자인"
    r"|임시저장|발행완료|발행대기|미발행|초안|예약)[^)]*\)\s*$"
)


def _title_keyword(item: dict) -> str:
    """
    title에서 채널·상태 접미사를 제거한 핵심 구절을 추출한다.

    1) 끝 '(…)' 접미사 제거 — 두 개 이상 겹쳐 붙어도 전부(=반복) 제거
       "… — 네이버 블로그 (임시저장)" → "… — 네이버 블로그"
    2) 앞머리 시리즈 표식 "[필라테스편] " 제거 — 실제 게시 제목엔 안 들어간다
    3) em-dash(—)/hyphen(-)으로 분리해 첫 부분 사용
       "바레 런칭 — 네이버 블로그" → "바레 런칭"

    최대 28자 (검색 노이즈 방지).
    """
    title = (item.get("title") or "").strip()
    if not title:
        return ""
    # Step 1: 끝 괄호 접미사 반복 제거
    for _ in range(4):
        stripped = _TITLE_SUFFIX_RE.sub("", title).strip()
        if stripped == title:
            break
        title = stripped
    # Step 2: 앞머리 시리즈 표식 제거
    # (2026-07-23 배9578: 이 대괄호 때문에 카페·카카오·당근 3건이 통째로 빗나갔다)
    title = re.sub(r"^(?:\s*\[[^\]]*\])+\s*", "", title).strip()
    # Step 3: em-dash(—) 또는 hyphen(-)으로 분리 → 첫 부분이 핵심 키워드
    base = re.split(r"\s*[—\-]\s*", title)[0].strip()
    return base[:28] if len(base) >= 4 else ""


def _body_keyword(item: dict) -> str:
    """
    body 첫 핵심 구절 — 채널이 제목을 바꿔 단 경우(카카오 등)의 폴백 키워드.
    제목 기반이 실패했을 때만 쓴다.
    """
    body = item.get("body", "")
    if not isinstance(body, str) or not body.strip():
        return ""
    for line in body.splitlines():
        cleaned = line.strip().lstrip("▍•·-—□■◆▶👉📌💬👀 ").strip()
        # 해시태그·CTA·링크 줄은 키워드로 부적합 → 건너뜀
        if not cleaned or cleaned.startswith("#") or "wellperion.com" in cleaned or "http" in cleaned:
            continue
        if len(cleaned) >= 6:
            # 첫 문장부호 전까지 또는 16자
            snippet = re.split(r"[.!?。\n]", cleaned)[0].strip()
            out = snippet[:16] if len(snippet) >= 6 else cleaned[:16]
            # 16자 컷이 '— '·', ' 같은 연결부에서 끊기면 꼬리가 대조를 방해한다
            # (2026-07-23 배9578 실측: '운동과 회복이 한 곳에서 — ').
            return out.rstrip(" ,·—-–~:;")
    return ""


def _folder_keyword(item: dict) -> str:
    """최종 폴백: folder 이름에서 날짜 접두사 제거."""
    folder      = item.get("folder", "")
    folder_name = Path(folder).name if folder else ""
    m           = re.match(r"^\d{6}_(.+)", folder_name)
    if m:
        return m.group(1)[:28].replace("_", " ")
    return folder_name[:28] if folder_name else ""


def _keyword_candidates(item: dict) -> list[str]:
    """
    대조 키워드 후보 — 시도 순서대로.

    ★제목이 1순위다. 목록(블로그 글목록·카페 게시판·카카오 발행목록)에 뜨는 건 제목이고,
      본문 소제목에서 뽑은 키워드는 목록의 제목과 구조적으로 안 맞는다.
      (2026-07-23 배9578 실측: CINQ-EP1 이 body 소제목 '운동 다음의 시간 — 파리의'로
       뽑혀 실제 블로그 제목 '생크몽드 Ep.1 — 파리의 회복 의식이…'과 빗나갔다.)
    본문 기반은 채널이 제목을 바꿔 단 경우(카카오)의 폴백으로 뒤에 남긴다 —
    후보마다 여전히 '긍정 일치'를 요구하므로 대조가 느슨해지지는 않는다.
    """
    out: list[str] = []
    for kw in (_title_keyword(item), _body_keyword(item)):
        kw = (kw or "").strip()
        if kw and kw not in out:
            out.append(kw)
    if not out:
        # folder 는 'output(블로그)' 같은 비콘텐츠 이름이 섞여 대조 키워드로 약하다.
        # 제목·본문이 모두 없을 때만 쓰는 최종 폴백으로 남긴다(기존 동작 유지).
        fallback = _folder_keyword(item).strip()
        if fallback:
            out.append(fallback)
    return out


def _extract_keyword(item: dict) -> str:
    """1순위 키워드(하위호환 단일값)."""
    cands = _keyword_candidates(item)
    return cands[0] if cands else ""


def _iter_targets(items: list[dict], target_channels: set[str]) -> list[tuple[int, dict]]:
    """
    처리 대상 (인덱스, 항목) 쌍 반환.
    조건:
      A) status=='발행완료' AND post_url 없음
      B) status=='임시저장완료' AND 채널이 blog/cafe (손게시 탐지 후보)
      C) status==STATUS_URL_UNCONFIRMED AND post_url 없음 (배834 — URL 미회수 재회수 대상)
    """
    result: list[tuple[int, dict]] = []
    for idx, item in enumerate(items):
        channel_name = item.get("channel", "")
        engine_ch    = CHANNEL_MAP.get(channel_name)
        if not engine_ch or engine_ch not in target_channels:
            continue
        has_url = bool((item.get("post_url") or "").strip())
        status  = item.get("status", "")
        if status == "발행완료" and not has_url:
            result.append((idx, item))
        elif status == "임시저장완료" and engine_ch in DRAFT_DETECT_CHANNELS:
            result.append((idx, item))
        elif status == STATUS_URL_UNCONFIRMED and not has_url:
            result.append((idx, item))
    return result


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="발행 대조·URL 백필 (비파괴·멱등)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="변경 없이 회수 가능 목록 출력",
    )
    parser.add_argument(
        "--channels", default="blog,cafe,kakao,danggn",
        help="대상 채널 쉼표 구분 (기본: 전체)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="처리 건수 제한",
    )
    parser.add_argument(
        "--max-seconds", type=int, default=None,
        help="1회 실행 시간 상한(초) — 넘으면 남은 건은 다음 회차로 (무인 편승용)",
    )
    parser.add_argument(
        "--headful", action="store_true",
        help="브라우저 창 표시 (디버그)",
    )
    args = parser.parse_args()

    target_channels = {ch.strip() for ch in args.channels.split(",") if ch.strip()}

    # retrieve_post_url 엔진 임포트
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from retrieve_post_url import _retrieve_url_async  # noqa: PLC0415
    except ImportError as e:
        print(f"[ERROR] retrieve_post_url 임포트 실패: {e}", file=sys.stderr)
        return 1

    # 큐 로드
    try:
        raw = QUEUE_PATH.read_text(encoding="utf-8")
        items: list[dict] = json.loads(raw)
    except Exception as e:
        print(f"[ERROR] review_queue.json 로드 실패: {e}", file=sys.stderr)
        return 1

    targets = _iter_targets(items, target_channels)
    if args.limit:
        targets = targets[: args.limit]

    if not targets:
        print(f"[INFO] 처리 대상 없음 (channels: {args.channels})")
        return 0

    print(
        f"[INFO] 처리 대상 {len(targets)}건 "
        f"(channels={args.channels}, dry-run={args.dry_run})"
    )

    # 수정 작업
    modified_items  = [dict(it) for it in items]  # 원본 보존용 복사
    recovered_log: list[dict] = []                # dry-run 결과 수집
    updated_count   = 0
    failed_count    = 0                           # 시도했으나 미회수(세션만료·글 없음 등)
    deferred_count  = 0                           # 시간 상한으로 이번 회차 미처리 → 다음 회차
    newly_published: list[dict] = []              # 임시저장→발행완료 전환 건
    # ★저장 시 '이번에 실제로 바꾼 항목'만 넘긴다 — 큐 전체를 넘기면 merge 저장이 id 마다
    #   이 프로세스의 스테일 사본으로 덮어써, 크롤이 도는 몇 분 사이 다른 프로세스가 채운
    #   값이 지워진다(2026-07-23 배9578 실측: 회수기가 채운 URL 을 IG 대조 스윕이 되돌림).
    changed_entries: list[dict] = []
    started_at      = time.monotonic()

    for pos, (idx, item) in enumerate(targets):
        # 시간 상한 — 크롤이 오래 걸려도 예약작업 본체를 붙잡지 않는다.
        # 남은 건은 다음 회차가 다시 대상으로 잡는다(멱등이라 중복 처리 무해).
        if args.max_seconds and (time.monotonic() - started_at) >= args.max_seconds:
            deferred_count = len(targets) - pos
            print(f"[INFO] 시간 상한 {args.max_seconds}초 도달 — 남은 {deferred_count}건은 다음 회차로")
            break

        channel_name = item.get("channel", "")
        engine_ch    = CHANNEL_MAP.get(channel_name, "")
        item_id      = item.get("id") or item.get("title") or f"idx={idx}"
        old_status   = item.get("status", "")
        account      = item.get("account", "wellperion")

        # 계정 정규화: 블로그·카페는 항상 wellperion 계정
        if engine_ch in ("blog", "cafe"):
            account = "wellperion"

        candidates = _keyword_candidates(item)
        if not candidates:
            print(f"  [SKIP] keyword 추출 실패: {item_id}", file=sys.stderr)
            failed_count += 1
            continue

        # 제목 → 본문 → 폴더 순으로 시도. 후보마다 긍정 일치를 요구하므로
        # 후보가 늘어도 대조가 느슨해지지 않는다(못 찾으면 그대로 무변경).
        found_url, reason, keyword = None, "", candidates[0]
        for kw in candidates:
            keyword = kw
            print(f"  [시도] {item_id} | ch={engine_ch} | kw={kw!r}")
            try:
                found_url, reason = asyncio.run(
                    _retrieve_url_async(engine_ch, kw, account, args.headful)
                )
            except Exception as exc:
                found_url, reason = None, f"예외: {exc}"
            if found_url:
                break

        if not found_url:
            # 못 찾음 → 무변경, stderr에 사유만 기록
            print(f"  [미회수] {item_id} | {reason}", file=sys.stderr)
            failed_count += 1
            continue

        print(f"  [회수] {found_url}")

        if args.dry_run:
            recovered_log.append(
                {
                    "id":      item_id,
                    "channel": channel_name,
                    "keyword": keyword,
                    "url":     found_url,
                    "was_status": old_status,
                }
            )
        else:
            # 원본 배열에서 해당 인덱스 업데이트
            entry = modified_items[idx]
            entry["post_url"] = found_url

            # 임시저장완료 / 확인필요(URL미회수) → 발행완료 전환
            if old_status in ("임시저장완료", STATUS_URL_UNCONFIRMED):
                entry["status"] = "발행완료"
                newly_published.append(entry)

            # note 끝에 자동대조 기록 append
            date_str   = _now_kst()
            note_new   = f"[자동대조 {date_str}] URL 회수·발행확인"
            if old_status == "임시저장완료":
                note_new += " (임시저장→발행완료 전환)"
            elif old_status == STATUS_URL_UNCONFIRMED:
                note_new += " (확인필요→발행완료 전환)"
            existing_note = (entry.get("note") or "").strip()
            entry["note"] = (existing_note + " | " + note_new).lstrip(" | ")

            modified_items[idx] = entry
            changed_entries.append(entry)
            updated_count += 1

            worklog_log("cmo", "발행", f"{item_id} 주소 회수·발행완료", result="ok",
                        detail=f"채널={channel_name}", ref=str(item_id), url=found_url)

    # ── dry-run 결과 출력 ──────────────────────────────
    if args.dry_run:
        print(f"\n=== dry-run 결과: 회수 가능 {len(recovered_log)}건 ===")
        for r in recovered_log:
            was = f" (구 상태: {r['was_status']})" if r["was_status"] != "발행완료" else ""
            print(f"  [{r['channel']}] {r['id']}{was}")
            print(f"    keyword={r['keyword']!r} → {r['url']}")
        not_found_count = len(targets) - len(recovered_log)
        if not_found_count:
            print(f"  (미회수 {not_found_count}건 — stderr 참조)")
        print("\n[INFO] dry-run: 실제 파일 변경 없음")
        return 0

    # ── 1회 실행 요약 1줄 기록 (성공/미회수 건수) ──────────
    worklog_log(
        "cmo", "발행",
        f"발행 주소 자동 회수 — 성공 {updated_count}건 / 미회수 {failed_count}건",
        result=("ok" if updated_count else "warn"),
        detail=f"대상 {len(targets)}건 · 채널={args.channels}"
               + (f" · 다음 회차 이월 {deferred_count}건" if deferred_count else ""),
        ref="CMO-2026-07-22-PUBLISH-URL-RECOVERY-3CH",
    )

    # ── 실제 갱신 ─────────────────────────────────────
    if updated_count == 0:
        print("[INFO] 회수된 URL 없음 — 파일 무변경")
        return 0

    # 백업 먼저
    bak = _backup_path()
    bak.write_bytes(QUEUE_PATH.read_bytes())
    print(f"[INFO] 백업: {bak.name}")

    # 갱신 쓰기 — 락 안에서 디스크 최신본 재로드 후 id 병합 저장
    # (2026-07-23 · 07-21 AI하루 10편 소실 재발방지: 네트워크 대조 중 추가된 신규 항목 보존)
    payload = changed_entries if all(e.get("id") for e in changed_entries) else modified_items
    merge_save_review_queue(payload, holder="reconcile_published")
    print(f"[INFO] 갱신 완료: {updated_count}건 → {QUEUE_PATH.name}")

    # 임시저장→발행완료 전환된 건 텔레그램 통지
    if NOTIFY_SCRIPT.exists() and newly_published:
        for entry in newly_published:
            folder = entry.get("folder", "")
            if not folder:
                continue
            try:
                result = subprocess.run(
                    [sys.executable, str(NOTIFY_SCRIPT), "--folder", folder],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding="utf-8",
                )
                if result.returncode == 0:
                    print(f"  [통지 완료] {folder}")
                else:
                    print(
                        f"  [통지 실패] {folder}: {result.stderr.strip()}",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(f"  [통지 오류] {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
