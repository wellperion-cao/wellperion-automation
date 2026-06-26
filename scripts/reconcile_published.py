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
#   --headful                  브라우저 창 표시 (디버그)

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

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


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _now_kst() -> str:
    return datetime.now(tz=KST).strftime("%Y-%m-%d")


def _backup_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return QUEUE_PATH.with_suffix(f".json.bak_{ts}")


def _extract_keyword(item: dict) -> str:
    """
    title에서 채널 접미사를 제거한 핵심 구절을 추출한다.

    처리 순서:
    1) 끝 '(채널명)' 괄호 제거: "... (카카오 채널)" → "..."
    2) em-dash(—)로 분리해 첫 부분 사용: "바레 런칭 — 네이버 블로그" → "바레 런칭"
       "생크몽드 Ep.3 — 운동과 회복..." → "생크몽드 Ep.3"
    3) 폴백: folder 이름에서 날짜 접두사 제거

    최대 28자 (검색 노이즈 방지).
    """
    # 0) 본문(body) 우선 — 카카오·당근은 게시 본문이 제목과 달라(제목 'Ep.3'가 본문엔 없음),
    #    실제 게시글 텍스트와 대조하려면 body 첫 핵심구절이 맞다(오늘 회수 성공 패턴).
    body = item.get("body", "")
    if isinstance(body, str) and body.strip():
        for line in body.splitlines():
            cleaned = line.strip().lstrip("▍•·-—□■◆▶👉📌💬👀 ").strip()
            # 해시태그·CTA·링크 줄은 키워드로 부적합 → 건너뜀
            if not cleaned or cleaned.startswith("#") or "wellperion.com" in cleaned or "http" in cleaned:
                continue
            if len(cleaned) >= 6:
                # 첫 문장부호 전까지 또는 16자
                snippet = re.split(r"[.!?。\n]", cleaned)[0].strip()
                return snippet[:16] if len(snippet) >= 6 else cleaned[:16]

    title = item.get("title", "").strip()
    if title:
        # Step 1: 끝 괄호 채널명 제거 "(카카오 채널)", "(개인계정)" 등
        title = re.sub(
            r"\s*\([^)]*(?:채널|블로그|카페|계정|인스타|IG)[^)]*\)\s*$",
            "",
            title,
        ).strip()
        # Step 2: em-dash(—) 또는 hyphen(-)으로 분리 → 첫 부분이 핵심 키워드
        parts = re.split(r"\s*[—\-]\s*", title)
        base  = parts[0].strip()
        if len(base) >= 4:
            return base[:28]

    # 폴백: folder 이름에서 날짜 접두사 제거
    folder      = item.get("folder", "")
    folder_name = Path(folder).name if folder else ""
    m           = re.match(r"^\d{6}_(.+)", folder_name)
    if m:
        return m.group(1)[:28].replace("_", " ")

    return folder_name[:28] if folder_name else ""


def _iter_targets(items: list[dict], target_channels: set[str]) -> list[tuple[int, dict]]:
    """
    처리 대상 (인덱스, 항목) 쌍 반환.
    조건:
      A) status=='발행완료' AND post_url 없음
      B) status=='임시저장완료' AND 채널이 blog/cafe (손게시 탐지 후보)
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
    newly_published: list[dict] = []              # 임시저장→발행완료 전환 건

    for idx, item in targets:
        channel_name = item.get("channel", "")
        engine_ch    = CHANNEL_MAP.get(channel_name, "")
        item_id      = item.get("id") or item.get("title") or f"idx={idx}"
        old_status   = item.get("status", "")
        account      = item.get("account", "wellperion")

        # 계정 정규화: 블로그·카페는 항상 wellperion 계정
        if engine_ch in ("blog", "cafe"):
            account = "wellperion"

        keyword = _extract_keyword(item)
        if not keyword:
            print(f"  [SKIP] keyword 추출 실패: {item_id}", file=sys.stderr)
            continue

        print(f"  [시도] {item_id} | ch={engine_ch} | kw={keyword!r}")

        # URL 회수 시도
        try:
            found_url, reason = asyncio.run(
                _retrieve_url_async(engine_ch, keyword, account, args.headful)
            )
        except Exception as exc:
            found_url, reason = None, f"예외: {exc}"

        if not found_url:
            # 못 찾음 → 무변경, stderr에 사유만 기록
            print(f"  [미회수] {item_id} | {reason}", file=sys.stderr)
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

            # 임시저장완료 → 발행완료 전환
            if old_status == "임시저장완료":
                entry["status"] = "발행완료"
                newly_published.append(entry)

            # note 끝에 자동대조 기록 append
            date_str   = _now_kst()
            note_new   = f"[자동대조 {date_str}] URL 회수·발행확인"
            if old_status == "임시저장완료":
                note_new += " (임시저장→발행완료 전환)"
            existing_note = (entry.get("note") or "").strip()
            entry["note"] = (existing_note + " | " + note_new).lstrip(" | ")

            modified_items[idx] = entry
            updated_count += 1

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

    # ── 실제 갱신 ─────────────────────────────────────
    if updated_count == 0:
        print("[INFO] 회수된 URL 없음 — 파일 무변경")
        return 0

    # 백업 먼저
    bak = _backup_path()
    bak.write_bytes(QUEUE_PATH.read_bytes())
    print(f"[INFO] 백업: {bak.name}")

    # 갱신 쓰기 (들여쓰기 2칸, ensure_ascii=False, 개행 마무리)
    QUEUE_PATH.write_text(
        json.dumps(modified_items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
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
